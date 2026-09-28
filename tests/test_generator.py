"""Tests for the LabelGenerator class."""

import pytest
from pathlib import Path
from lego_labels.generator import LabelGenerator
from lego_labels import config


class TestLabelGenerator:
    """Test cases for LabelGenerator."""

    def test_init(self):
        """Test LabelGenerator initialization."""
        generator = LabelGenerator(verbose=True)
        assert generator.verbose is True
        assert generator.label_width == config.DEFAULT_LABEL_WIDTH * 2.834645669  # mm to points

    def test_init_custom_size(self):
        """Test LabelGenerator with custom size."""
        generator = LabelGenerator(label_width=100, label_height=100)
        assert generator.label_width == 100 * 2.834645669  # mm to points

    def test_fit_text(self):
        """Test text fitting algorithm."""
        from reportlab.pdfgen import canvas
        from io import BytesIO

        buffer = BytesIO()
        c = canvas.Canvas(buffer)
        generator = LabelGenerator()

        text = "This is a very long text that needs to be split"
        lines = generator._fit_text(c, text, 100, "Helvetica", 10)

        assert isinstance(lines, list)
        assert len(lines) > 1

    def test_hex_to_color(self):
        """Test hex color conversion."""
        generator = LabelGenerator()
        color = generator._hex_to_color("#2c3e50")
        assert color is not None
