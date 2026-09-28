"""Talk to a Niimbot D101: detect the loaded roll and print labels.

This module is optional: niimprint is imported only when a printer is used, so
label generation works without it and without a printer attached.

niimprint provides the transports (USB serial, Bluetooth), the packet framing
and the RFID query. Its print_image() implements the old D11 print sequence,
which the D101 does not answer. The D101 uses the "B1" print sequence of
niimbluelib (https://github.com/MultiMote/niimbluelib), implemented here.
"""

import socket
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
from PIL import Image

from . import config

INSTALL_HINT = (
    "pip install -e '.[print]' && "
    "pip install --no-deps --ignore-requires-python git+https://github.com/AndBondStyle/niimprint"
)

# Request command -> response command (niimbluelib packets/commands.ts)
CMD_PRINT_START = (0x01, 0x02)
CMD_PAGE_START = (0x03, 0x04)
CMD_SET_PAGE_SIZE = (0x13, 0x14)
CMD_PAGE_END = (0xE3, 0xE4)
CMD_PRINT_END = (0xF3, 0xF4)
CMD_PRINT_STATUS = (0xA3, 0xB3)
CMD_SET_DENSITY = (0x21, 0x31)
CMD_SET_LABEL_TYPE = (0x23, 0x33)
# Image data packets get no response
PKT_BITMAP_ROW = 0x85
PKT_EMPTY_ROWS = 0x84
# Response types signalling an error
ERROR_TYPES = (0x00, 0xDB)

LABEL_TYPE_WITH_GAPS = 1
PAGE_COLOR_SINGLE = 0
MAX_ROW_REPEAT = 255

PACKET_INTERVAL = 0.01      # seconds between packets, the printer drops data sent faster
REPLY_TIMEOUT = 5.0         # seconds to wait for a command reply
PAGE_END_TIMEOUT = 10.0     # seconds to wait for the page end reply
STATUS_POLL_INTERVAL = 0.3  # seconds between print status polls
PRINT_TIMEOUT_PER_PAGE = 15.0


def _load_niimprint():
    """Import niimprint, or fail with an installation hint."""
    try:
        import niimprint
    except ImportError:
        raise click.ClickException(
            f"Using the printer requires the niimprint library. Install it with:\n  {INSTALL_HINT}"
        )
    return niimprint


def _list_serial_ports():
    """List serial ports with pyserial (installed with niimprint)."""
    from serial.tools.list_ports import comports
    return comports()


def detect_port() -> str:
    """
    Find the serial port of the printer among the USB serial devices.

    Built-in ports without a USB id (macOS debug console, Bluetooth incoming
    port) are ignored. A port with the known D101 USB id wins over others.

    Returns:
        Device path, e.g. /dev/cu.usbmodem00000000050C1

    Raises:
        click.ClickException: If no port or several candidate ports are found
    """
    usb_ports = [p for p in _list_serial_ports() if p.vid is not None]
    known = [p for p in usb_ports if (p.vid, p.pid) in config.D101_USB_IDS]
    candidates = known or usb_ports

    if len(candidates) == 1:
        return candidates[0].device

    if not candidates:
        raise click.ClickException("No printer found over USB. Is the D101 plugged in and switched on?")

    listing = "\n".join(f"  {p.device} : {p.description}" for p in candidates)
    raise click.ClickException(f"Several USB serial ports found, pick one with --port:\n{listing}")


def u16(value: int) -> bytes:
    """Encode an unsigned 16-bit integer, big endian."""
    return value.to_bytes(2, "big")


def encode_image(image: Image.Image) -> List[Tuple[int, bytes]]:
    """
    Encode a label image into D101 image data packets.

    Each image row is one printer row across the print head. Black pixels are
    set bits, most significant bit first. Identical consecutive rows are sent
    once with a repeat count, blank rows as "empty rows" packets.

    Args:
        image: Label image, at most D101_HEAD_PX wide, rows along the paper feed

    Returns:
        List of (packet type, packet data)
    """
    img = image.convert("1")
    row_bytes = (img.width + 7) // 8
    raw = img.tobytes()  # mode "1": MSB first, bit set = white
    chunk = config.D101_HEAD_PX // 8 // 3  # pixel counts are split in three head sections

    runs = []  # [first_row, repeat, black_row_data or None for blank]
    for y in range(img.height):
        row = raw[y * row_bytes:(y + 1) * row_bytes]
        black = bytearray(~b & 0xFF for b in row)
        if img.width % 8:
            # Padding bits at the end of the row are not pixels, keep them white
            black[-1] &= (0xFF << (8 - img.width % 8)) & 0xFF
        black = bytes(black)
        data = black if any(black) else None

        if runs and runs[-1][2] == data and runs[-1][1] < MAX_ROW_REPEAT:
            runs[-1][1] += 1
        else:
            runs.append([y, 1, data])

    packets = []
    for first_row, repeat, data in runs:
        if data is None:
            packets.append((PKT_EMPTY_ROWS, u16(first_row) + bytes((repeat,))))
            continue
        if len(data) <= chunk * 3:
            counts = [sum(bin(b).count("1") for b in data[i * chunk:(i + 1) * chunk]) for i in range(3)]
        else:
            total = sum(bin(b).count("1") for b in data)
            counts = [0, total & 0xFF, (total >> 8) & 0xFF]
        packets.append((PKT_BITMAP_ROW, u16(first_row) + bytes(counts) + bytes((repeat,)) + data))

    return packets


class D101Printer:
    """Niimbot D101 connection: roll detection and batch printing."""

    def __init__(self, niimprint, transport, verbose: bool = False):
        self._packet_cls = niimprint.packet.NiimbotPacket
        self._transport = transport
        self._client = niimprint.PrinterClient(transport)
        self._buffer = bytearray()
        self.verbose = verbose

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"  {message}")

    def _send(self, packet_type: int, data: bytes):
        """Send one packet without waiting for a reply, paced like niimbluelib."""
        time.sleep(PACKET_INTERVAL)
        self._transport.write(self._packet_cls(packet_type, data).to_bytes())

    def _receive(self) -> list:
        """Read available bytes and return the complete packets received."""
        self._buffer.extend(self._transport.read(1024))
        packets = []
        while True:
            start = self._buffer.find(b"\x55\x55")
            if start < 0:
                self._buffer.clear()
                break
            del self._buffer[:start]
            if len(self._buffer) < 4 or len(self._buffer) < self._buffer[3] + 7:
                break
            size = self._buffer[3] + 7
            try:
                packets.append(self._packet_cls.from_bytes(bytes(self._buffer[:size])))
            except AssertionError:
                # Corrupt frame: skip the header and resynchronize
                del self._buffer[:2]
                continue
            del self._buffer[:size]
        return packets

    def _request(self, command: Tuple[int, int], data: bytes = b"\x01", timeout: float = REPLY_TIMEOUT):
        """
        Send a command and wait for its reply.

        Args:
            command: (request type, response type)
            data: Packet data
            timeout: Seconds to wait for the reply

        Returns:
            Reply packet

        Raises:
            click.ClickException: On printer error or timeout
        """
        request, response = command
        self._send(request, data)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for packet in self._receive():
                if packet.type == response:
                    return packet
                if packet.type in ERROR_TYPES:
                    raise click.ClickException(f"Printer rejected command 0x{request:02x}")
        raise click.ClickException(
            f"No reply from the printer to command 0x{request:02x}. Make sure no phone or "
            "computer is connected to it over Bluetooth, then unplug and replug the USB cable."
        )

    def read_roll(self) -> Optional[Dict]:
        """
        Read the RFID tag of the loaded label roll.

        Returns:
            Dict with 'barcode', 'serial', 'used_len', 'total_len', 'type' keys,
            or None if the roll has no readable tag
        """
        try:
            return self._client.get_rfid()
        except Exception:
            return None

    def print_status(self) -> Dict:
        """Current print status: number of pages printed and error code."""
        data = self._request(CMD_PRINT_STATUS).data
        status = {'page': int.from_bytes(data[0:2], "big"), 'error': 0}
        if len(data) == 10:
            status['error'] = data[6]
        return status

    def print_images(self, paths: List[Path], density: int = config.D101_DENSITY):
        """
        Print label images as one print job, one label per image.

        Args:
            paths: Paths to print-ready images (at most D101_HEAD_PX wide)
            density: Print density, 1 (light) to 3 (dark)
        """
        images = []
        for path in paths:
            image = Image.open(path)
            if image.width > config.D101_HEAD_PX:
                raise click.ClickException(
                    f"{path} is {image.width} px wide, the D101 prints at most {config.D101_HEAD_PX} px"
                )
            images.append(image)

        total = len(images)
        try:
            self._request(CMD_SET_DENSITY, bytes((density,)))
            self._request(CMD_SET_LABEL_TYPE, bytes((LABEL_TYPE_WITH_GAPS,)))
            self._request(CMD_PRINT_START, u16(total) + bytes((0, 0, 0, 0, PAGE_COLOR_SINGLE)))

            for i, (path, image) in enumerate(zip(paths, images), start=1):
                self._log(f"Printing {path} ({i}/{total})")
                self._request(CMD_PAGE_START)
                cols = (image.width + 7) // 8 * 8  # rows are sent in whole bytes
                self._request(CMD_SET_PAGE_SIZE, u16(image.height) + u16(cols) + u16(1))
                for packet_type, data in encode_image(image):
                    self._send(packet_type, data)
                self._request(CMD_PAGE_END, timeout=PAGE_END_TIMEOUT)

            deadline = time.monotonic() + PRINT_TIMEOUT_PER_PAGE * total
            while True:
                status = self.print_status()
                if status['error']:
                    raise click.ClickException(f"Printer error {status['error']} (label roll, lid or paper)")
                if status['page'] >= total:
                    break
                if time.monotonic() > deadline:
                    raise click.ClickException(f"Printing timed out after {status['page']}/{total} label(s)")
                time.sleep(STATUS_POLL_INTERVAL)
        finally:
            # Always close the job so the printer is not left waiting
            try:
                self._request(CMD_PRINT_END)
            except click.ClickException:
                pass

        print(f"✓ Printed {total} label(s)")


def connect(port: Optional[str] = None, bt_address: Optional[str] = None, verbose: bool = False) -> D101Printer:
    """
    Connect to the printer over USB serial, or Bluetooth if an address is given.

    Args:
        port: Serial port for USB, or None / 'auto' to detect it
        bt_address: Bluetooth MAC address (Linux only), overrides port
        verbose: Show detailed progress information

    Returns:
        Connected D101Printer
    """
    niimprint = _load_niimprint()

    if bt_address:
        if not hasattr(socket, "AF_BLUETOOTH"):
            raise click.ClickException(
                f"Bluetooth printing is not supported by Python on {sys.platform} "
                "(needs Linux). Connect the D101 over USB and use --port instead."
            )
    elif not port or port == "auto":
        port = detect_port()

    try:
        if bt_address:
            transport = niimprint.BluetoothTransport(bt_address)
        else:
            transport = niimprint.SerialTransport(port=port)
        return D101Printer(niimprint, transport, verbose=verbose)
    except Exception as e:
        raise click.ClickException(f"Could not connect to the printer: {e}")


def roll_label_size(roll: Optional[Dict]) -> Tuple[float, float]:
    """
    Look up the label size of a roll from its RFID barcode.

    Args:
        roll: Result of D101Printer.read_roll

    Returns:
        Tuple (width_mm, length_mm)

    Raises:
        click.ClickException: If the roll has no tag or its barcode is unknown
    """
    if not roll:
        raise click.ClickException(
            "Could not read the label roll's RFID tag. Pass the size with --label-size WxL."
        )

    size = config.D101_ROLLS.get(roll['barcode'])
    if size is None:
        raise click.ClickException(
            f"Unknown label roll, barcode {roll['barcode']}. Add it to D101_ROLLS in "
            f"lego_labels/config.py with the size printed on the box, e.g.\n"
            f"  \"{roll['barcode']}\": (15, 50),\n"
            f"or pass the size with --label-size WxL."
        )
    return size


def labels_left(roll: Optional[Dict]) -> Optional[int]:
    """Number of unused labels on the roll, or None if unknown."""
    if not roll:
        return None
    return roll['total_len'] - roll['used_len']
