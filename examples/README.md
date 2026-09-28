# Examples

Outputs generated from [`parts.txt`](parts.txt) (six common parts). Part images come from [BrickArchitect](https://brickarchitect.com), see the [credits](../README.md#credits).

| Path | What it is |
|---|---|
| `d101-15x50/` | Print-ready Niimbot D101 labels for a 15x50 mm roll: one 1-bit PNG per part (120x400 px, 203 dpi), named `<index>-<reference>.png`, plus `sheet.png` |
| `d101-25x30/` | The same for a 25x30 mm roll (192x240 px) |
| `labels.pdf` | Default A4 PDF output (46x24 mm labels, 4x12 grid) |
| `*-preview.png` | Images used in the main README |

The PNGs in `d101-*/` are rotated for the printer. `sheet.png` shows them in reading orientation.

To regenerate them from the repository root:

```bash
lego-labels --file examples/parts.txt --printer niimbot-d101 --label-size 15x50 --out examples/d101-15x50 --sheet
lego-labels --file examples/parts.txt --printer niimbot-d101 --label-size 25x30 --out examples/d101-25x30 --sheet
lego-labels --file examples/parts.txt --output examples/labels.pdf
```

The `*-preview.png` files were made from the same outputs: the D101 sheets laid out with fewer columns, the print-ready label enlarged 2x, and the first rows of the PDF page rendered to PNG.
