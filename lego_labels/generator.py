"""PDF generation logic for creating printable LEGO labels."""

from pathlib import Path
from typing import List, Dict
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from PIL import Image

from . import config


class LabelGenerator:
    """Creates PDF labels for LEGO parts."""

    def __init__(self, label_width: float = None, label_height: float = None, verbose: bool = False):
        self.label_width = (label_width or config.DEFAULT_LABEL_WIDTH) * mm
        self.label_height = (label_height or config.DEFAULT_LABEL_HEIGHT) * mm
        self.verbose = verbose

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"  {message}")

    def _hex_to_color(self, hex_color: str):
        """Convert hex color string to ReportLab color."""
        return HexColor(hex_color)

    def _fit_text(self, c: canvas.Canvas, text: str, max_width: float, font_name: str, font_size: float) -> List[str]:
        """
        Split text into multiple lines to fit within max_width.

        Args:
            c: ReportLab canvas
            text: Text to fit
            max_width: Maximum width in points
            font_name: Font name
            font_size: Font size

        Returns:
            List of text lines
        """
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            width = c.stringWidth(test_line, font_name, font_size)

            if width <= max_width:
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

    def add_label(self, c: canvas.Canvas, x: float, y: float, part_data: Dict):
        """
        Add a single label to the PDF at position (x, y).

        Args:
            c: ReportLab canvas
            x: X position (bottom-left corner)
            y: Y position (bottom-left corner)
            part_data: Dict with 'title', 'reference', 'image_path' keys
        """
        title = part_data['title']
        reference = part_data['reference']
        image_path = part_data.get('image_path')

        padding = config.DEFAULT_LABEL_PADDING * mm
        title_height = config.TITLE_HEIGHT * mm
        image_height = config.IMAGE_HEIGHT * mm
        ref_height = config.REFERENCE_HEIGHT * mm

        # Fill white background
        c.setFillColor(self._hex_to_color(config.COLOR_TITLE_BG))
        c.rect(x, y, self.label_width, self.label_height, fill=1, stroke=0)

        # Draw border
        c.setStrokeColor(self._hex_to_color(config.COLOR_BORDER))
        c.setLineWidth(config.BORDER_WIDTH)
        c.rect(x, y, self.label_width, self.label_height, fill=0, stroke=1)

        # Title section (top)
        title_y = y + self.label_height - title_height

        # Title text - smaller font for compact labels
        c.setFillColor(self._hex_to_color(config.COLOR_TITLE_TEXT))
        c.setFont("Helvetica", config.FONT_TITLE_SIZE)

        # Fit title text - limit to 2 lines for small label
        max_text_width = self.label_width - (2 * padding)
        title_lines = self._fit_text(c, title, max_text_width, "Helvetica", config.FONT_TITLE_SIZE)

        # Limit to 2 lines max for compact display
        if len(title_lines) > 2:
            title_lines = title_lines[:2]
            # Add ellipsis to second line if truncated
            if len(title_lines[1]) > 3:
                title_lines[1] = title_lines[1][:-3] + "..."

        # Center and draw title lines
        line_height = config.FONT_TITLE_SIZE + 1
        total_text_height = len(title_lines) * line_height
        text_start_y = title_y + (title_height / 2) + (total_text_height / 2) - line_height / 2

        for line in title_lines:
            text_width = c.stringWidth(line, "Helvetica", config.FONT_TITLE_SIZE)
            text_x = x + (self.label_width - text_width) / 2
            c.drawString(text_x, text_start_y, line)
            text_start_y -= line_height

        # Image section (middle)
        image_y = y + ref_height
        if image_path and Path(image_path).exists():
            try:
                img = Image.open(image_path)
                img_width, img_height = img.size

                # Calculate scaling to fit within constraints
                max_img_width = self.label_width - (2 * padding)
                max_img_height = image_height - (2 * padding)

                scale = min(max_img_width / img_width, max_img_height / img_height)
                scaled_width = img_width * scale
                scaled_height = img_height * scale

                # Center image
                img_x = x + (self.label_width - scaled_width) / 2
                img_y_pos = image_y + (image_height - scaled_height) / 2

                c.drawImage(ImageReader(image_path), img_x, img_y_pos,
                          width=scaled_width, height=scaled_height,
                          preserveAspectRatio=True, mask='auto')

            except Exception as e:
                self._log(f"Error adding image for {reference}: {e}")
        # Skip placeholder for cleaner look on small labels

        # Reference section (bottom)
        c.setFillColor(self._hex_to_color(config.COLOR_REFERENCE_TEXT))
        c.setFont("Helvetica-Bold", config.FONT_REFERENCE_SIZE)

        ref_text = str(reference)
        text_width = c.stringWidth(ref_text, "Helvetica-Bold", config.FONT_REFERENCE_SIZE)
        text_x = x + (self.label_width - text_width) / 2
        text_y = y + (ref_height / 2) - (config.FONT_REFERENCE_SIZE / 2)
        c.drawString(text_x, text_y, ref_text)

    def draw_cutting_grid(self, c: canvas.Canvas, cols: int, rows: int, margin: float,
                          page_width: float, page_height: float):
        """
        Draw a cutting grid on the page.

        Args:
            c: ReportLab canvas
            cols: Number of columns
            rows: Number of rows
            margin: Page margin
            page_width: Page width
            page_height: Page height
        """
        c.setStrokeColor(self._hex_to_color(config.COLOR_GRID))
        c.setLineWidth(config.GRID_WIDTH)

        # Draw vertical lines
        for col in range(cols + 1):
            x = margin + col * self.label_width
            c.line(x, margin, x, page_height - margin)

        # Draw horizontal lines
        for row in range(rows + 1):
            y = page_height - margin - row * self.label_height
            c.line(margin, y, margin + cols * self.label_width, y)

    def create_labels(self, parts_data: List[Dict], output_path: str):
        """
        Create PDF with labels for all parts.

        Args:
            parts_data: List of dicts with part information
            output_path: Path to output PDF file
        """
        if not parts_data:
            print("No parts to generate labels for.")
            return

        self._log(f"Generating PDF with {len(parts_data)} label(s)...")

        c = canvas.Canvas(output_path, pagesize=A4)
        page_width, page_height = A4

        margin = config.PAGE_MARGIN * mm
        gap_h = config.LABEL_GAP_H * mm
        gap_v = config.LABEL_GAP_V * mm

        # Use fixed layout from config
        cols = config.COLUMNS_PER_PAGE
        rows = config.ROWS_PER_PAGE

        labels_per_page = cols * rows

        # Track current page to draw grid only once per page
        current_page = 0

        for i, part_data in enumerate(parts_data):
            # Check if we need a new page
            if i > 0 and i % labels_per_page == 0:
                c.showPage()
                current_page += 1

            # Draw cutting grid on first label of each page
            if i % labels_per_page == 0:
                self.draw_cutting_grid(c, cols, rows, margin, page_width, page_height)

            # Calculate position on current page
            page_index = i % labels_per_page
            row = page_index // cols
            col = page_index % cols

            x = margin + col * (self.label_width + gap_h)
            # Y coordinates in ReportLab start from bottom
            y = page_height - margin - (row + 1) * self.label_height - row * gap_v

            self._log(f"Adding label for part {part_data['reference']} ({i+1}/{len(parts_data)})")
            self.add_label(c, x, y, part_data)

        c.save()
        self._log(f"PDF saved to: {output_path}")
        print(f"✓ Generated {len(parts_data)} label(s) in {output_path}")
