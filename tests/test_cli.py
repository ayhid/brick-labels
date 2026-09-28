"""Tests for the command-line interface options."""

import sys
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from PIL import Image

from lego_labels import config
from lego_labels.cli import main


@pytest.fixture
def parts(tmp_path):
    """Fetched parts with a synthetic image, so no network is used."""
    image_path = tmp_path / "part.png"
    Image.new("L", (100, 60), 100).save(image_path)
    return [
        {'title': '2×4 Brick', 'reference': '3001', 'image_path': str(image_path)},
        {'title': '2×2 Brick', 'reference': '3003', 'image_path': str(image_path)},
    ]


@pytest.fixture
def run(parts):
    """Invoke the CLI with PartFetcher mocked."""
    def invoke(args):
        with patch('lego_labels.cli.PartFetcher') as fetcher_cls:
            fetcher_cls.return_value.fetch_multiple_parts.return_value = parts
            return CliRunner().invoke(main, args)
    return invoke


class TestDefaultBehavior:
    """Without --printer the PDF output is unchanged."""

    def test_pdf_output(self, run, tmp_path):
        output = tmp_path / "labels.pdf"
        result = run(['3001', '3003', '--output', str(output)])
        assert result.exit_code == 0, result.output
        assert output.read_bytes().startswith(b"%PDF")

    @pytest.mark.parametrize("args", [
        ['--label-size', '25x30'],
        ['--out', 'somewhere'],
        ['--sheet'],
        ['--print'],
        ['--density', '2'],
    ])
    def test_printer_options_require_printer(self, run, args):
        result = run(['3001'] + args)
        assert result.exit_code == 2
        assert "require(s) --printer" in result.output


class TestPrinterProfile:
    """--printer niimbot-d101 batch PNG output."""

    def test_batch_default_size(self, run, tmp_path):
        out_dir = tmp_path / "d101"
        result = run(['3001', '3003', '--printer', 'niimbot-d101', '--out', str(out_dir)])

        assert result.exit_code == 0, result.output
        files = sorted(p.name for p in out_dir.iterdir())
        assert files == ["001-3001.png", "002-3003.png"]
        img = Image.open(out_dir / files[0])
        assert img.mode == "1"
        assert img.size == (192, 240)  # default 25x30 mm

    def test_label_size_and_sheet(self, run, tmp_path):
        out_dir = tmp_path / "d101"
        result = run(['3001', '--printer', 'niimbot-d101', '--label-size', '25x50',
                      '--out', str(out_dir), '--sheet'])

        assert result.exit_code == 0, result.output
        assert Image.open(out_dir / "001-3001.png").size == (192, 400)
        assert (out_dir / config.CONTACT_SHEET_FILE).exists()

    def test_default_out_dir(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run(['3001', '--printer', 'niimbot-d101'])
        assert result.exit_code == 0, result.output
        assert (tmp_path / config.DEFAULT_OUT_DIR / "001-3001.png").exists()

    @pytest.mark.parametrize("size", ["30x30", "10x30", "25", "25x5", "big"])
    def test_invalid_label_size(self, run, size):
        result = run(['3001', '--printer', 'niimbot-d101', '--label-size', size])
        assert result.exit_code == 2
        assert "--label-size" in result.output

    def test_unknown_printer(self, run):
        result = run(['3001', '--printer', 'dymo'])
        assert result.exit_code == 2

    def test_pdf_options_ignored_with_warning(self, run, tmp_path):
        result = run(['3001', '--printer', 'niimbot-d101', '--out', str(tmp_path), '--width', '40'])
        assert result.exit_code == 0
        assert "--width ignored" in result.output


class TestPrint:
    """--print and --label-size auto go through the niimbot module."""

    ROLL = {'uuid': '881d01ece28c0000', 'barcode': '6972842743596', 'serial': 'PC0G403332011481',
            'used_len': 14, 'total_len': 156, 'type': 1}

    @pytest.fixture
    def printer(self):
        """A mocked D101 connection with the 15x50 roll loaded."""
        with patch('lego_labels.niimbot.connect') as connect:
            connect.return_value.read_roll.return_value = dict(self.ROLL)
            yield connect

    def test_print(self, run, tmp_path, printer):
        result = run(['3001', '3003', '--printer', 'niimbot-d101', '--out', str(tmp_path), '--print'])

        assert result.exit_code == 0, result.output
        printer.assert_called_once_with(port=None, bt_address=None, verbose=False)
        paths = printer.return_value.print_images.call_args.args[0]
        assert [p.name for p in paths] == ["001-3001.png", "002-3003.png"]
        assert printer.return_value.print_images.call_args.kwargs['density'] == config.D101_DENSITY

    def test_print_explicit_port_and_density(self, run, tmp_path, printer):
        result = run(['3001', '--printer', 'niimbot-d101', '--out', str(tmp_path),
                      '--print', '--port', '/dev/cu.usbmodem9', '--density', '3'])

        assert result.exit_code == 0, result.output
        assert printer.call_args.kwargs['port'] == '/dev/cu.usbmodem9'
        assert printer.return_value.print_images.call_args.kwargs['density'] == 3

    def test_invalid_density(self, run):
        result = run(['3001', '--printer', 'niimbot-d101', '--print', '--density', '4'])
        assert result.exit_code == 2

    def test_label_size_auto(self, run, tmp_path, printer):
        result = run(['3001', '--printer', 'niimbot-d101', '--label-size', 'auto', '--out', str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "15x50 mm, 142 label(s) left" in result.output
        assert Image.open(tmp_path / "001-3001.png").size == (120, 400)
        printer.return_value.print_images.assert_not_called()

    def test_label_size_auto_unknown_roll(self, run, tmp_path, printer):
        printer.return_value.read_roll.return_value = dict(self.ROLL, barcode='123')
        result = run(['3001', '--printer', 'niimbot-d101', '--label-size', 'auto', '--out', str(tmp_path)])

        assert result.exit_code == 1
        assert "Unknown label roll, barcode 123" in result.output

    def test_label_size_auto_no_tag(self, run, tmp_path, printer):
        printer.return_value.read_roll.return_value = None
        result = run(['3001', '--printer', 'niimbot-d101', '--label-size', 'auto', '--out', str(tmp_path)])

        assert result.exit_code == 1
        assert "Could not read the label roll" in result.output

    def test_warns_when_roll_runs_out(self, run, tmp_path, printer):
        printer.return_value.read_roll.return_value = dict(self.ROLL, used_len=155)
        result = run(['3001', '3003', '--printer', 'niimbot-d101', '--out', str(tmp_path), '--print'])

        assert result.exit_code == 0, result.output
        assert "only 1 left on the roll" in result.output

    def test_print_without_niimprint(self, run, tmp_path):
        with patch.dict(sys.modules, {'niimprint': None}):
            result = run(['3001', '--printer', 'niimbot-d101', '--out', str(tmp_path), '--print'])

        assert result.exit_code == 1
        assert "requires the niimprint library" in result.output
