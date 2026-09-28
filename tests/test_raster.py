"""Tests for the Niimbot D101 PNG label generation."""

import pytest
from PIL import Image

from lego_labels import config
from lego_labels.raster import (RasterLabelGenerator, label_width_px, mm_to_px, parse_label_size,
                                prepare_image, safe_filename)


@pytest.fixture
def part_image(tmp_path):
    """A transparent RGBA part image with a horizontal gray gradient."""
    img = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    for x in range(40, 260):
        shade = 30 + (x - 40) * 190 // 220
        for y in range(40, 160):
            img.putpixel((x, y), (shade, shade, shade, 255))
    path = tmp_path / "part.png"
    img.save(path)
    return str(path)


@pytest.fixture
def part_data(part_image):
    """Part dict as returned by PartFetcher."""
    return {'title': '45° 2×4 Slope w/ 4-Studs', 'reference': '3037', 'image_path': part_image}


def pixel_values(img):
    """Set of pixel values present in an image."""
    histogram = img.convert("L").histogram()
    return {value for value, count in enumerate(histogram) if count}


def black_ratio(img):
    """Fraction of black pixels in a mode "1" image."""
    histogram = img.convert("L").histogram()
    return histogram[0] / (img.width * img.height)


class TestConversion:
    """mm to px conversion."""

    @pytest.mark.parametrize("mm, px", [(1, 8), (12, 96), (15, 120), (30, 240), (50, 400), (12.5, 100)])
    def test_mm_to_px(self, mm, px):
        assert mm_to_px(mm) == px

    def test_label_width_clamped_to_head(self):
        assert label_width_px(25) == config.D101_HEAD_PX
        assert label_width_px(24) == 192
        assert label_width_px(12) == 96


class TestParseLabelSize:
    """--label-size parsing and D101 range validation."""

    @pytest.mark.parametrize("value, expected", [
        ("25x30", (25.0, 30.0)),
        ("12X40", (12.0, 40.0)),
        (" 15 x 50 ", (15.0, 50.0)),
        ("22.5x30", (22.5, 30.0)),
    ])
    def test_valid(self, value, expected):
        assert parse_label_size(value) == expected

    @pytest.mark.parametrize("value", ["", "25", "25x", "x30", "25*30", "abc", "25x30x40"])
    def test_invalid_format(self, value):
        with pytest.raises(ValueError, match="invalid label size"):
            parse_label_size(value)

    @pytest.mark.parametrize("value", ["11x30", "26x30", "50x30"])
    def test_width_out_of_range(self, value):
        with pytest.raises(ValueError, match="width"):
            parse_label_size(value)

    @pytest.mark.parametrize("value", ["25x5", "25x500"])
    def test_length_out_of_range(self, value):
        with pytest.raises(ValueError, match="length"):
            parse_label_size(value)


class TestRender:
    """Rendered label dimensions, bit depth, rotation and centering."""

    @pytest.mark.parametrize("width_mm, length_mm, size", [
        (25, 30, (192, 240)),
        (25, 50, (192, 400)),
        (12, 30, (96, 240)),
        (15, 50, (120, 400)),
        (12.5, 30, (100, 240)),
    ])
    def test_output_dimensions(self, part_data, width_mm, length_mm, size):
        label = RasterLabelGenerator(width_mm, length_mm).render_label(part_data)
        assert label.size == size

    def test_landscape_dimensions(self, part_data):
        landscape = RasterLabelGenerator(25, 30).render_landscape(part_data)
        assert landscape.size == (240, 192)

    def test_output_is_one_bit(self, part_data):
        label = RasterLabelGenerator(25, 30).render_label(part_data)
        assert label.mode == "1"
        assert pixel_values(label) <= {0, 255}
        assert pixel_values(label) == {0, 255}

    def test_rotation(self, part_data):
        generator = RasterLabelGenerator(25, 30)
        landscape = generator.render_landscape(part_data)
        label = generator.render_label(part_data)

        # 90 degrees clockwise: landscape (x, y) -> label (height - 1 - y, x)
        assert config.D101_ROTATION == 270
        for x, y in [(0, 0), (10, 30), (120, 96), (200, 170), (239, 191)]:
            assert label.getpixel((landscape.height - 1 - y, x)) == landscape.getpixel((x, y))

    def test_margins_are_blank(self, part_data):
        landscape = RasterLabelGenerator(15, 50).render_landscape(part_data)
        end, side = config.D101_MARGIN_END_PX, config.D101_MARGIN_SIDE_PX

        assert pixel_values(landscape.crop((0, 0, end, landscape.height))) == {255}
        assert pixel_values(landscape.crop((landscape.width - end, 0, landscape.width, landscape.height))) == {255}
        assert pixel_values(landscape.crop((0, 0, landscape.width, side))) == {255}
        assert pixel_values(landscape.crop((0, landscape.height - side, landscape.width, landscape.height))) == {255}

    def test_missing_image(self, part_data):
        part_data['image_path'] = None
        label = RasterLabelGenerator(25, 30).render_label(part_data)
        assert label.size == (192, 240)
        assert 0 in pixel_values(label)  # text still drawn

    def test_long_title_is_truncated(self, part_data):
        part_data['title'] = "Technic Beam 1 x 15 Thick with Alternating Holes and Extra Long Name"
        generator = RasterLabelGenerator(25, 30)
        font, lines = generator._layout_text(part_data['title'], 228, 52, config.D101_FONT_TITLE_PX, 2)
        assert len(lines) <= 2
        assert all(font.getlength(line) <= 228 for line in lines)


class TestPrepareImage:
    """Grayscale conversion and dithering of the part image."""

    def test_dithered_not_solid(self, part_image):
        img = prepare_image(part_image, 150, 100)
        assert img.mode == "1"
        assert 0.1 < black_ratio(img) < 0.9

    def test_mid_gray_is_dithered_to_half_tone(self, tmp_path):
        path = tmp_path / "gray.png"
        Image.new("L", (100, 100), 128).save(path)
        img = prepare_image(str(path), 100, 100)
        assert 0.35 < black_ratio(img) < 0.65

    def test_fits_box(self, part_image):
        img = prepare_image(part_image, 80, 30)
        assert img.width <= 80 and img.height <= 30

    def test_missing_file(self, tmp_path):
        assert prepare_image(str(tmp_path / "nope.png"), 50, 50) is None
        assert prepare_image(None, 50, 50) is None


class TestCreateLabels:
    """Batch output."""

    def test_batch_files(self, part_data, tmp_path):
        parts = [part_data, dict(part_data, reference='3001'), dict(part_data, reference='32523/x')]
        out_dir = tmp_path / "out"

        paths = RasterLabelGenerator(25, 30).create_labels(parts, str(out_dir))

        assert [p.name for p in paths] == ["001-3037.png", "002-3001.png", "003-32523_x.png"]
        for path in paths:
            img = Image.open(path)
            assert img.mode == "1"
            assert img.size == (192, 240)
            assert round(img.info['dpi'][0]) == config.D101_DPI
        assert not (out_dir / config.CONTACT_SHEET_FILE).exists()

    def test_contact_sheet(self, part_data, tmp_path):
        parts = [dict(part_data, reference=str(i)) for i in range(5)]
        RasterLabelGenerator(25, 30).create_labels(parts, str(tmp_path), sheet=True)

        sheet = Image.open(tmp_path / config.CONTACT_SHEET_FILE)
        # 4 columns x 2 rows of landscape labels with 12 px gaps
        assert sheet.size == (12 + 4 * (240 + 12), 12 + 2 * (192 + 12))

    def test_empty(self, tmp_path):
        assert RasterLabelGenerator().create_labels([], str(tmp_path)) == []

    def test_safe_filename(self):
        assert safe_filename("3037") == "3037"
        assert safe_filename("973pb/01 c") == "973pb_01_c"
