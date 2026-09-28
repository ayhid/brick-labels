"""Configuration and constants for LEGO label generator."""

import os
from pathlib import Path

# URLs
BRICKARCHITECT_PART_URL = "https://brickarchitect.com/parts/{reference}"
BRICKARCHITECT_IMAGE_URL = "https://brickarchitect.com/content/parts-large/{reference}.png"

# Cache settings
CACHE_DIR = Path.home() / ".cache" / "lego-labels"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Rate limiting
REQUEST_DELAY = 0.5  # seconds between requests

# Label dimensions (in mm)
DEFAULT_LABEL_WIDTH = 46
DEFAULT_LABEL_HEIGHT = 24
DEFAULT_LABEL_PADDING = 1

# Page settings (A4)
PAGE_WIDTH = 210  # mm
PAGE_HEIGHT = 297  # mm
PAGE_MARGIN = 5  # mm
LABEL_GAP_H = 0  # mm - no gap for cutting grid
LABEL_GAP_V = 0  # mm - no gap for cutting grid

# Layout - calculate columns/rows to fit A4
COLUMNS_PER_PAGE = 4  # 46mm × 4 = 184mm < 200mm available
ROWS_PER_PAGE = 12    # 24mm × 12 = 288mm < 287mm available

# Label sections (heights in mm for 24mm height label)
TITLE_HEIGHT = 7      # Top section for title (compact, 2 lines max)
IMAGE_HEIGHT = 12     # Middle section for image (scaled to fit)
REFERENCE_HEIGHT = 5  # Bottom section for reference number (bold)

# Colors - white background with black text
COLOR_TITLE_BG = "#ffffff"
COLOR_TITLE_TEXT = "#000000"
COLOR_REFERENCE_BG = "#ffffff"
COLOR_REFERENCE_TEXT = "#000000"
COLOR_BORDER = "#000000"
COLOR_GRID = "#cccccc"  # Light gray for cutting grid

# Fonts
FONT_TITLE_SIZE = 6
FONT_REFERENCE_SIZE = 7

# Border
BORDER_WIDTH = 0.5  # points - thinner border
GRID_WIDTH = 0.25   # points - thin cutting grid

# Output
DEFAULT_OUTPUT_FILE = "labels.pdf"

# Printer profiles
PRINTER_PROFILES = ("niimbot-d101",)

# Niimbot D101 thermal printer (203 dpi, 8 px/mm, 192 px print head)
D101_DPI = 203
D101_PX_PER_MM = 8
D101_HEAD_PX = 192           # print head width, perpendicular to paper feed
D101_MIN_WIDTH_MM = 12
D101_MAX_WIDTH_MM = 25
D101_MIN_LENGTH_MM = 10
D101_MAX_LENGTH_MM = 100
D101_DEFAULT_WIDTH_MM = 25
D101_DEFAULT_LENGTH_MM = 30
D101_ROTATION = 270          # degrees counter-clockwise (270 = 90 clockwise, niimbluelib "left" direction)
D101_MARGIN_SIDE_PX = 8       # 1 mm along the long edges of the label
D101_MARGIN_END_PX = 20       # 2.5 mm at both ends of the label (die-cut edges)
D101_SIDE_BY_SIDE_RATIO = 1.6  # length/width ratio from which image goes left, text right
D101_FONT_TITLE_PX = 22
D101_FONT_REFERENCE_PX = 30
D101_FONT_MIN_PX = 12
D101_DENSITY = 3             # 1 (light) to 3 (dark)
D101_USB_IDS = ((0x0483, 0x5743),)  # USB VID:PID of the D101 serial port

# Known Niimbot label rolls, used by --label-size auto.
# RFID barcode -> (width_mm, length_mm). Read a new roll's barcode with --label-size auto.
D101_ROLLS = {
    "6972842743596": (15, 50),  # T 15x50 white
}

DEFAULT_OUT_DIR = "labels-d101"
CONTACT_SHEET_FILE = "sheet.png"
