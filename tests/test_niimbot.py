"""Tests for printer port detection and label roll lookup."""

from types import SimpleNamespace
from unittest.mock import patch

import click
import pytest
from PIL import Image

from lego_labels import niimbot


def port(device, vid=None, pid=None, description="n/a"):
    """Fake pyserial port entry."""
    return SimpleNamespace(device=device, vid=vid, pid=pid, description=description)


BUILT_IN = [port("/dev/cu.debug-console"), port("/dev/cu.Bluetooth-Incoming-Port")]
D101 = port("/dev/cu.usbmodem00000000050C1", 0x0483, 0x5743, "YICHIP3121 Virtual ComPort in FS Mode")


class TestDetectPort:
    """USB serial port detection."""

    def test_ignores_built_in_ports(self):
        with patch.object(niimbot, '_list_serial_ports', return_value=BUILT_IN + [D101]):
            assert niimbot.detect_port() == "/dev/cu.usbmodem00000000050C1"

    def test_prefers_known_usb_id(self):
        other = port("/dev/cu.usbserial-1", 0x1A86, 0x7523, "USB serial")
        with patch.object(niimbot, '_list_serial_ports', return_value=[other, D101]):
            assert niimbot.detect_port() == D101.device

    def test_single_unknown_usb_port(self):
        other = port("/dev/cu.usbmodem2", 0x1234, 0x0001)
        with patch.object(niimbot, '_list_serial_ports', return_value=BUILT_IN + [other]):
            assert niimbot.detect_port() == "/dev/cu.usbmodem2"

    def test_no_printer(self):
        with patch.object(niimbot, '_list_serial_ports', return_value=BUILT_IN):
            with pytest.raises(click.ClickException, match="No printer found"):
                niimbot.detect_port()

    def test_ambiguous(self):
        ports = [port("/dev/cu.a", 0x1, 0x1), port("/dev/cu.b", 0x2, 0x2)]
        with patch.object(niimbot, '_list_serial_ports', return_value=ports):
            with pytest.raises(click.ClickException, match="--port"):
                niimbot.detect_port()


class TestRoll:
    """Label roll size lookup from the RFID tag."""

    ROLL = {'barcode': '6972842743596', 'serial': 'PC0G403332011481', 'used_len': 14, 'total_len': 156, 'type': 1}

    def test_known_roll(self):
        assert niimbot.roll_label_size(self.ROLL) == (15, 50)

    def test_unknown_roll(self):
        with pytest.raises(click.ClickException, match="barcode 42"):
            niimbot.roll_label_size(dict(self.ROLL, barcode='42'))

    def test_no_tag(self):
        with pytest.raises(click.ClickException, match="--label-size"):
            niimbot.roll_label_size(None)

    def test_labels_left(self):
        assert niimbot.labels_left(self.ROLL) == 142
        assert niimbot.labels_left(None) is None


class TestEncodeImage:
    """Image rows to D101 image data packets."""

    def make_image(self, rows):
        """192 px wide mode "1" image; rows is a list of lists of black x positions."""
        img = Image.new("1", (192, len(rows)), 255)
        for y, xs in enumerate(rows):
            for x in xs:
                img.putpixel((x, y), 0)
        return img

    def test_bitmap_row(self):
        packets = niimbot.encode_image(self.make_image([[0, 7, 100, 191]]))

        assert len(packets) == 1
        packet_type, data = packets[0]
        assert packet_type == niimbot.PKT_BITMAP_ROW
        assert data[0:2] == b"\x00\x00"          # row number
        assert list(data[2:5]) == [2, 1, 1]      # black pixels per head third (64 px each)
        assert data[5] == 1                      # repeat
        row = data[6:]
        assert len(row) == 24
        assert row[0] == 0b10000001              # x = 0 and x = 7, MSB first
        assert row[12] == 0b00001000             # x = 100
        assert row[23] == 0b00000001             # x = 191

    def test_narrow_row_padding_is_white(self):
        img = Image.new("1", (100, 1), 0)  # 12.5 mm label, fully black row
        packet_type, data = niimbot.encode_image(img)[0]

        row = data[6:]
        assert len(row) == 13
        assert row[:12] == b"\xff" * 12
        assert row[12] == 0b11110000  # 4 real pixels, 4 padding bits left white
        assert list(data[2:5]) == [64, 36, 0]

    def test_repeats_and_empty_rows(self):
        img = self.make_image([[], [], [], [5], [5], [5], [9]])
        packets = niimbot.encode_image(img)

        assert packets[0] == (niimbot.PKT_EMPTY_ROWS, b"\x00\x00\x03")
        assert packets[1][0] == niimbot.PKT_BITMAP_ROW
        assert packets[1][1][0:2] == b"\x00\x03" and packets[1][1][5] == 3
        assert packets[2][1][0:2] == b"\x00\x06" and packets[2][1][5] == 1

    def test_repeat_capped(self):
        packets = niimbot.encode_image(self.make_image([[]] * 300))
        assert packets == [(niimbot.PKT_EMPTY_ROWS, b"\x00\x00\xff"),
                           (niimbot.PKT_EMPTY_ROWS, b"\x00\xff\x2d")]  # 255 + 45 rows


class FakeTransport:
    """Simulated D101: answers every command, prints pages instantly."""

    def __init__(self, packet_cls):
        self.packet_cls = packet_cls
        self.sent = []
        self.pending = bytearray()
        self.pages = 0

    def write(self, raw):
        packet = self.packet_cls.from_bytes(raw)
        self.sent.append((packet.type, bytes(packet.data)))
        replies = {request: response for request, response in [
            niimbot.CMD_PRINT_START, niimbot.CMD_PAGE_START, niimbot.CMD_SET_PAGE_SIZE, niimbot.CMD_PAGE_END,
            niimbot.CMD_PRINT_END, niimbot.CMD_SET_DENSITY, niimbot.CMD_SET_LABEL_TYPE]}
        if packet.type == niimbot.CMD_PAGE_END[0]:
            self.pages += 1
        if packet.type == niimbot.CMD_PRINT_STATUS[0]:
            reply = self.packet_cls(niimbot.CMD_PRINT_STATUS[1], self.pages.to_bytes(2, "big") + b"\x64\x64")
        elif packet.type in replies:
            reply = self.packet_cls(replies[packet.type], b"\x01")
        else:
            return
        self.pending.extend(reply.to_bytes())

    def read(self, length):
        data = bytes(self.pending[:length])
        del self.pending[:length]
        return data


class TestPrintSequence:
    """D101 (B1) print job sequence."""

    @pytest.fixture
    def printer(self):
        niimprint = pytest.importorskip("niimprint")
        transport = FakeTransport(niimprint.packet.NiimbotPacket)
        return niimbot.D101Printer(niimprint, transport), transport

    def test_batch_job(self, printer, tmp_path):
        d101, transport = printer
        paths = []
        for i in range(2):
            path = tmp_path / f"{i}.png"
            Image.new("1", (192, 400), 255).save(path)
            paths.append(path)

        d101.print_images(paths, density=3)

        commands = [t for t, _ in transport.sent if t not in (niimbot.PKT_BITMAP_ROW, niimbot.PKT_EMPTY_ROWS)]
        page = [0x03, 0x13, 0xE3]
        assert commands[:3] == [0x21, 0x23, 0x01]
        assert commands[3:9] == page + page
        assert commands[-1] == 0xF3
        assert 0xA3 in commands

        sent = dict(transport.sent)
        assert sent[0x21] == b"\x03"                          # density
        assert sent[0x23] == b"\x01"                          # labels with gaps
        assert sent[0x01] == b"\x00\x02\x00\x00\x00\x00\x00"  # 2 pages, single color
        assert sent[0x13] == b"\x01\x90\x00\xc0\x00\x01"      # 400 rows, 192 cols, 1 copy

    def test_rejects_wrong_width(self, printer, tmp_path):
        d101, transport = printer
        path = tmp_path / "wide.png"
        Image.new("1", (384, 100), 255).save(path)

        with pytest.raises(click.ClickException, match="192 px"):
            d101.print_images([path])
        assert transport.sent == []

    def test_no_reply_times_out(self, printer, monkeypatch):
        d101, transport = printer
        monkeypatch.setattr(transport, "write", lambda raw: None)
        with pytest.raises(click.ClickException, match="No reply"):
            d101._request(niimbot.CMD_SET_DENSITY, b"\x02", timeout=0.2)
