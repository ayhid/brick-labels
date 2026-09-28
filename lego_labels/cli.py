"""Command-line interface for LEGO label generator."""

import sys
import subprocess
from pathlib import Path
import click

from . import config
from .fetcher import PartFetcher
from .generator import LabelGenerator
from .raster import RasterLabelGenerator, parse_label_size


def _validate_label_size(ctx, param, value):
    """Click callback: parse '<width>x<length>' in mm and check the D101 range, or 'auto'."""
    if value is None:
        return None
    if value.strip().lower() == 'auto':
        return 'auto'
    try:
        return parse_label_size(value)
    except ValueError as e:
        raise click.BadParameter(str(e))


@click.command()
@click.argument('references', nargs=-1)
@click.option('--file', '-f', 'input_file', type=click.Path(exists=True),
              help='Read part references from file (one per line)')
@click.option('--interactive', '-i', is_flag=True,
              help='Interactive mode: enter part references one by one')
@click.option('--output', '-o', default=config.DEFAULT_OUTPUT_FILE,
              help=f'Output PDF file (default: {config.DEFAULT_OUTPUT_FILE})')
@click.option('--width', type=float,
              help=f'Label width in mm (default: {config.DEFAULT_LABEL_WIDTH})')
@click.option('--height', type=float,
              help=f'Label height in mm (default: {config.DEFAULT_LABEL_HEIGHT})')
@click.option('--preview', '-p', is_flag=True,
              help='Open PDF automatically after generation')
@click.option('--verbose', '-v', is_flag=True,
              help='Show detailed progress information')
@click.option('--printer', type=click.Choice(config.PRINTER_PROFILES),
              help='Printer profile: output print-ready PNGs instead of a PDF')
@click.option('--label-size', callback=_validate_label_size, metavar='WxL|auto',
              help=f'Label size in mm, width x length (default: {config.D101_DEFAULT_WIDTH_MM}x'
                   f'{config.D101_DEFAULT_LENGTH_MM}, width {config.D101_MIN_WIDTH_MM} to '
                   f'{config.D101_MAX_WIDTH_MM}), or auto to read it from the loaded roll. '
                   f'Requires --printer')
@click.option('--out', 'out_dir', type=click.Path(file_okay=False),
              help=f'Output directory for label PNGs (default: {config.DEFAULT_OUT_DIR}). Requires --printer')
@click.option('--sheet', is_flag=True,
              help=f'Also write a contact sheet ({config.CONTACT_SHEET_FILE}) for preview. Requires --printer')
@click.option('--print', 'print_labels', is_flag=True,
              help='Send the labels to the printer (needs the niimprint library). Requires --printer')
@click.option('--port',
              help='USB serial port of the printer (default: auto-detect). Used with --print and --label-size auto')
@click.option('--bt-address',
              help='Bluetooth MAC address of the printer (Linux only). Used with --print and --label-size auto')
@click.option('--density', type=click.IntRange(1, 3),
              help=f'Print density from 1 to 3 (default: {config.D101_DENSITY}). Used with --print')
def main(references, input_file, interactive, output, width, height, preview, verbose,
         printer, label_size, out_dir, sheet, print_labels, port, bt_address, density):
    """
    Generate printable labels for LEGO parts.

    Examples:

      lego-labels 3037 3003 3001

      lego-labels --file parts.txt

      lego-labels 3037 3003 --preview --verbose

      lego-labels 3037 --width 80 --height 80

      lego-labels --file parts.txt --printer niimbot-d101 --label-size 25x30 --out labels-d101 --sheet

      lego-labels --file parts.txt --printer niimbot-d101 --label-size auto --print
    """
    # Printer-only options make no sense for the PDF output
    if not printer:
        printer_options = {
            '--label-size': label_size is not None,
            '--out': out_dir is not None,
            '--sheet': sheet,
            '--print': print_labels,
            '--port': port is not None,
            '--bt-address': bt_address is not None,
            '--density': density is not None,
        }
        used = [name for name, is_set in printer_options.items() if is_set]
        if used:
            raise click.UsageError(f"{', '.join(used)} require(s) --printer niimbot-d101")

    # Collect part references from different sources
    part_refs = []

    # From command line arguments
    if references:
        part_refs.extend(references)

    # From file
    if input_file:
        if verbose:
            print(f"Reading part references from {input_file}")
        with open(input_file, 'r') as f:
            file_refs = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            part_refs.extend(file_refs)

    # Interactive mode
    if interactive:
        print("Interactive mode - Enter part references (empty line to finish):")
        while True:
            ref = input("> ").strip()
            if not ref:
                break
            if not ref.startswith('#'):
                part_refs.append(ref)

    # Validate we have something to work with
    if not part_refs:
        click.echo("Error: No part references provided.", err=True)
        click.echo("Use 'lego-labels --help' for usage information.", err=True)
        sys.exit(1)

    # Remove duplicates while preserving order
    part_refs = list(dict.fromkeys(part_refs))

    # Connect to the printer before fetching parts, so connection problems fail fast
    client = roll = None
    if printer and (label_size == 'auto' or print_labels):
        # Imported here so the printing module stays optional
        from . import niimbot
        client = niimbot.connect(port=port, bt_address=bt_address, verbose=verbose)
        roll = client.read_roll()
        if label_size == 'auto':
            label_size = niimbot.roll_label_size(roll)
            print(f"Detected label roll {roll['barcode']}: {label_size[0]:g}x{label_size[1]:g} mm, "
                  f"{niimbot.labels_left(roll)} label(s) left")

    if verbose:
        print(f"\nProcessing {len(part_refs)} part(s)...")

    # Fetch part information
    fetcher = PartFetcher(verbose=verbose)
    parts_data = fetcher.fetch_multiple_parts(part_refs)

    if not parts_data:
        click.echo("Error: Could not fetch information for any parts.", err=True)
        sys.exit(1)

    # Printer profile: one print-ready PNG per part
    if printer:
        ignored = [name for name, is_set in (('--width', width is not None),
                                             ('--height', height is not None),
                                             ('--preview', preview)) if is_set]
        if ignored:
            click.echo(f"Warning: {', '.join(ignored)} ignored with --printer, use --label-size.", err=True)

        width_mm, length_mm = label_size or (config.D101_DEFAULT_WIDTH_MM, config.D101_DEFAULT_LENGTH_MM)
        generator = RasterLabelGenerator(width_mm=width_mm, length_mm=length_mm, verbose=verbose)
        paths = generator.create_labels(parts_data, out_dir or config.DEFAULT_OUT_DIR, sheet=sheet)

        if print_labels and paths:
            left = niimbot.labels_left(roll)
            if left is not None and left < len(paths):
                click.echo(f"Warning: printing {len(paths)} label(s) but only {left} left on the roll.", err=True)
            client.print_images(paths, density=density or config.D101_DENSITY)
        return

    # Generate PDF
    generator = LabelGenerator(label_width=width, label_height=height, verbose=verbose)
    generator.create_labels(parts_data, output)

    # Preview if requested
    if preview:
        if verbose:
            print(f"Opening {output}...")
        try:
            if sys.platform == 'darwin':  # macOS
                subprocess.run(['open', output], check=True)
            elif sys.platform == 'win32':  # Windows
                subprocess.run(['start', output], shell=True, check=True)
            else:  # Linux and others
                subprocess.run(['xdg-open', output], check=True)
        except subprocess.CalledProcessError:
            click.echo(f"Warning: Could not open {output} automatically.", err=True)
        except FileNotFoundError:
            click.echo(f"Warning: Could not find command to open {output}.", err=True)


if __name__ == '__main__':
    main()
