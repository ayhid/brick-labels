"""PNG generation of print-ready 1-bit labels for thermal label printers (Niimbot D101)."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import reportlab
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import config

# TrueType fonts shipped with ReportLab (Bitstream Vera), so no extra dependency
FONT_DIR = Path(reportlab.__file__).parent / "fonts"
FONT_REGULAR = FONT_DIR / "Vera.ttf"
FONT_BOLD = FONT_DIR / "VeraBd.ttf"

# Pixel values for mode "1" images
WHITE = 255
BLACK = 0

# Pillow >= 9.1 exposes enums, older versions only the module constants
_DITHER = getattr(Image, "Dither", Image).FLOYDSTEINBERG
_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

_SIZE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*$")


def mm_to_px(value_mm: float) -> int:
    """
    Convert millimeters to printer pixels (8 px/mm at 203 dpi).

    Args:
        value_mm: Length in millimeters

    Returns:
        Length in pixels, rounded to the nearest pixel
    """
    return int(round(value_mm * config.D101_PX_PER_MM))


def label_width_px(width_mm: float) -> int:
    """
    Printable label width in pixels, clamped to the print head width.

    Args:
        width_mm: Label width in millimeters (perpendicular to paper feed)

    Returns:
        Width in pixels, at most config.D101_HEAD_PX
    """
    return min(mm_to_px(width_mm), config.D101_HEAD_PX)


def parse_label_size(value: str) -> Tuple[float, float]:
    """
    Parse and validate a '<width>x<length>' label size in mm.

    Args:
        value: Size string such as '25x30'

    Returns:
        Tuple (width_mm, length_mm)

    Raises:
        ValueError: If the format is invalid or the size is out of the D101 range
    """
    match = _SIZE_PATTERN.match(value or "")
    if not match:
        raise ValueError(f"invalid label size '{value}', expected <width>x<length> in mm, e.g. 25x30")

    width, length = float(match.group(1)), float(match.group(2))

    if not config.D101_MIN_WIDTH_MM <= width <= config.D101_MAX_WIDTH_MM:
        raise ValueError(
            f"label width {width:g} mm is out of range "
            f"({config.D101_MIN_WIDTH_MM} to {config.D101_MAX_WIDTH_MM} mm)"
        )
    if not config.D101_MIN_LENGTH_MM <= length <= config.D101_MAX_LENGTH_MM:
        raise ValueError(
            f"label length {length:g} mm is out of range "
            f"({config.D101_MIN_LENGTH_MM} to {config.D101_MAX_LENGTH_MM} mm)"
        )

    return width, length


def safe_filename(text: str) -> str:
    """Replace characters that are unsafe in file names with underscores."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("_") or "part"


def prepare_image(image_path: str, max_width: int, max_height: int) -> Optional[Image.Image]:
    """
    Load a part image and convert it to a dithered 1-bit image fitting a box.

    Transparency is flattened onto white, the image is cropped to its content,
    converted to grayscale, contrast-stretched, scaled and then dithered with
    Floyd-Steinberg so shaded renders keep their volume instead of turning black.

    Args:
        image_path: Path to the part image
        max_width: Box width in pixels
        max_height: Box height in pixels

    Returns:
        Mode "1" image, or None if the image cannot be used
    """
    if not image_path or not Path(image_path).exists() or max_width < 1 or max_height < 1:
        return None

    img = Image.open(image_path)
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        background.alpha_composite(img)
        img = background

    gray = img.convert("L")

    # Crop surrounding white space so the part uses the whole box
    bbox = ImageOps.invert(gray).getbbox()
    if bbox:
        gray = gray.crop(bbox)

    gray = ImageOps.autocontrast(gray, cutoff=1)

    scale = min(max_width / gray.width, max_height / gray.height)
    size = (max(1, int(gray.width * scale)), max(1, int(gray.height * scale)))
    gray = gray.resize(size, _LANCZOS)

    return gray.convert("1", dither=_DITHER)


class RasterLabelGenerator:
    """Creates print-ready 1-bit PNG labels for the Niimbot D101."""

    def __init__(self, width_mm: float = None, length_mm: float = None, verbose: bool = False):
        self.width_mm = width_mm or config.D101_DEFAULT_WIDTH_MM
        self.length_mm = length_mm or config.D101_DEFAULT_LENGTH_MM
        self.width_px = label_width_px(self.width_mm)
        self.length_px = mm_to_px(self.length_mm)
        self.verbose = verbose

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"  {message}")

    def _font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Load the regular or bold label font at a pixel size."""
        return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)

    def _line_height(self, font: ImageFont.FreeTypeFont) -> int:
        """Height of one text line for a font."""
        ascent, descent = font.getmetrics()
        return ascent + descent

    def _fit_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> List[str]:
        """
        Split text into multiple lines to fit within max_width.

        Same word wrapping as LabelGenerator._fit_text, measured in pixels.

        Args:
            text: Text to fit
            font: Pillow font
            max_width: Maximum width in pixels

        Returns:
            List of text lines
        """
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])

            if font.getlength(test_line) <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Single word is too long, add it anyway
                    lines.append(word)

        if current_line:
            lines.append(' '.join(current_line))

        return lines

    def _truncate(self, text: str, font: ImageFont.FreeTypeFont, max_width: float, ellipsis: bool) -> str:
        """Shorten text until it fits max_width, optionally ending with '...'."""
        suffix = "..." if ellipsis else ""
        while text and font.getlength(text + suffix) > max_width:
            text = text[:-1]
        return text.rstrip() + suffix

    def _layout_text(self, text: str, max_width: int, max_height: int, start_size: int,
                     max_lines: int, bold: bool = False) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
        """
        Find the largest font size at which text fits a box, wrapping on words.

        Falls back to the minimum font size with truncated lines and an ellipsis.

        Args:
            text: Text to lay out
            max_width: Box width in pixels
            max_height: Box height in pixels
            start_size: Largest font size to try, in pixels
            max_lines: Maximum number of lines
            bold: Use the bold font

        Returns:
            Tuple (font, lines)
        """
        size = max(start_size, config.D101_FONT_MIN_PX)
        while True:
            font = self._font(size, bold)
            allowed = max(1, min(max_lines, max_height // self._line_height(font)))
            lines = self._fit_text(text, font, max_width)
            fits = len(lines) <= allowed and all(font.getlength(line) <= max_width for line in lines)
            if fits or size <= config.D101_FONT_MIN_PX:
                break
            size -= 1

        if not fits:
            truncated = len(lines) > allowed
            lines = lines[:allowed]
            lines = [self._truncate(line, font, max_width, False) for line in lines]
            if truncated:
                lines[-1] = self._truncate(lines[-1], font, max_width, True)

        return font, lines

    def _draw_lines(self, draw: ImageDraw.ImageDraw, lines: List[str], font: ImageFont.FreeTypeFont,
                    box: Tuple[int, int, int, int]):
        """Draw lines centered in box (left, top, right, bottom), thresholded (no anti-aliasing)."""
        left, top, right, bottom = box
        line_height = self._line_height(font)
        center_x = (left + right) / 2
        y = top + (bottom - top - len(lines) * line_height) / 2 + line_height / 2

        for line in lines:
            draw.text((center_x, y), line, font=font, fill=BLACK, anchor="mm")
            y += line_height

    def _paste_image(self, canvas: Image.Image, image_path: Optional[str], box: Tuple[int, int, int, int],
                     reference: str):
        """Paste the dithered part image centered in box (left, top, right, bottom)."""
        left, top, right, bottom = box
        try:
            img = prepare_image(image_path, right - left, bottom - top)
        except Exception as e:
            self._log(f"Error adding image for {reference}: {e}")
            return
        if img is None:
            return

        x = left + (right - left - img.width) // 2
        y = top + (bottom - top - img.height) // 2
        canvas.paste(img, (x, y))

    def render_landscape(self, part_data: Dict) -> Image.Image:
        """
        Render a label in landscape orientation (length x print head width).

        The canvas is exactly the label size. Labels narrower than the 192 px
        head are placed on the paper by the printer, as in NiimBlue.

        Args:
            part_data: Dict with 'title', 'reference', 'image_path' keys

        Returns:
            Mode "1" image of size (length_px, width_px)
        """
        title = part_data['title']
        reference = str(part_data['reference'])
        image_path = part_data.get('image_path')

        canvas = Image.new("1", (self.length_px, self.width_px), WHITE)
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"

        # Keep clear of the die-cut edges: wider margins at both ends of the label
        pad = config.D101_MARGIN_SIDE_PX
        left, top = config.D101_MARGIN_END_PX, pad
        right, bottom = self.length_px - config.D101_MARGIN_END_PX, self.width_px - pad
        inner_height = bottom - top

        if self.length_mm / self.width_mm >= config.D101_SIDE_BY_SIDE_RATIO:
            # Side by side: square image on the left, name and reference on the right
            image_box = (left, top, left + inner_height, bottom)
            text_left = image_box[2] + pad
            ref_height = int(inner_height * 0.35)
            title_box = (text_left, top, right, bottom - ref_height)
            ref_box = (text_left, bottom - ref_height, right, bottom)
            title_lines_max = 3
        else:
            # Stacked like the PDF label: name, image, reference
            total = config.TITLE_HEIGHT + config.IMAGE_HEIGHT + config.REFERENCE_HEIGHT
            title_height = int(inner_height * config.TITLE_HEIGHT / total)
            ref_height = int(inner_height * config.REFERENCE_HEIGHT / total)
            title_box = (left, top, right, top + title_height)
            image_box = (left, top + title_height, right, bottom - ref_height)
            ref_box = (left, bottom - ref_height, right, bottom)
            title_lines_max = 2

        font, lines = self._layout_text(title, title_box[2] - title_box[0], title_box[3] - title_box[1],
                                        config.D101_FONT_TITLE_PX, title_lines_max)
        self._draw_lines(draw, lines, font, title_box)

        self._paste_image(canvas, image_path, image_box, reference)

        font, lines = self._layout_text(reference, ref_box[2] - ref_box[0], ref_box[3] - ref_box[1],
                                        config.D101_FONT_REFERENCE_PX, 1, bold=True)
        self._draw_lines(draw, lines, font, ref_box)

        return canvas

    def render_label(self, part_data: Dict) -> Image.Image:
        """
        Render a print-ready label: landscape layout rotated to the print orientation.

        Args:
            part_data: Dict with 'title', 'reference', 'image_path' keys

        Returns:
            Mode "1" image of size (width_px, length_px)
        """
        return self.render_landscape(part_data).rotate(config.D101_ROTATION, expand=True)

    def write_contact_sheet(self, images: List[Image.Image], output_path: Path, columns: int = 4,
                            gap: int = 12):
        """
        Assemble landscape labels into a single preview image.

        Args:
            images: Landscape label images
            output_path: Path to output PNG file
            columns: Number of labels per row
            gap: Space between labels in pixels
        """
        columns = max(1, min(columns, len(images)))
        rows = (len(images) + columns - 1) // columns
        cell_w, cell_h = self.length_px, self.width_px

        sheet = Image.new("L", (gap + columns * (cell_w + gap), gap + rows * (cell_h + gap)), 255)
        draw = ImageDraw.Draw(sheet)

        for i, img in enumerate(images):
            x = gap + (i % columns) * (cell_w + gap)
            y = gap + (i // columns) * (cell_h + gap)
            sheet.paste(img.convert("L"), (x, y))
            # Outline the label edges
            draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline=160)

        sheet.save(output_path)

    def create_labels(self, parts_data: List[Dict], out_dir: str, sheet: bool = False) -> List[Path]:
        """
        Create one print-ready PNG per part, named <index>-<reference>.png.

        Args:
            parts_data: List of dicts with part information
            out_dir: Output directory (created if missing)
            sheet: Also write a contact sheet for preview

        Returns:
            List of paths to the generated label images
        """
        if not parts_data:
            print("No parts to generate labels for.")
            return []

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        self._log(f"Generating {len(parts_data)} label(s) of {self.width_mm:g}x{self.length_mm:g} mm "
                  f"({self.width_px}x{self.length_px} px)...")

        paths = []
        landscapes = []
        for i, part_data in enumerate(parts_data, start=1):
            reference = part_data['reference']
            self._log(f"Adding label for part {reference} ({i}/{len(parts_data)})")

            landscape = self.render_landscape(part_data)
            label = landscape.rotate(config.D101_ROTATION, expand=True)

            path = out_path / f"{i:03d}-{safe_filename(reference)}.png"
            label.save(path, dpi=(config.D101_DPI, config.D101_DPI))
            paths.append(path)
            if sheet:
                landscapes.append(landscape)

        if sheet:
            sheet_path = out_path / config.CONTACT_SHEET_FILE
            self.write_contact_sheet(landscapes, sheet_path)
            self._log(f"Contact sheet saved to: {sheet_path}")

        print(f"✓ Generated {len(paths)} label(s) in {out_path}")
        return paths
