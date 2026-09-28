# Quick Start Guide

## Installation

```bash
# Clone the repository
git clone https://github.com/ayhid/brick-labels.git
cd brick-labels

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the package
pip install -e .
```

## Basic Usage

```bash
# Generate labels for specific parts
lego-labels 3037 3003 3001

# Read from file
lego-labels --file parts.txt

# Interactive mode
lego-labels --interactive

# With preview and verbose output
lego-labels 3037 3003 --preview --verbose

# Custom output filename
lego-labels 3037 --output my-labels.pdf

# Custom label size (30mm × 50mm)
lego-labels 3037 --width 50 --height 30
```

## File Format (parts.txt)

```
3037
3003
3001
# Comments are ignored
3004
```

## Output

The tool generates a PDF file with printable labels:
- Default output: `labels.pdf`
- Default size: 24mm × 46mm (height × width) - compact labels
- Layout: 4 columns × 12 rows on A4 paper (48 labels per page)
- Cutting grid: Light gray lines for easy cutting
- Each label includes:
  - Part name (from BrickArchitect, compact font)
  - Part image (scaled to fit)
  - Reference number (bold)
- Colors: White background with black text

## Tips

1. **Cached images**: Images are cached in `~/.cache/lego-labels/` to speed up repeated use
2. **Verbose mode**: Use `-v` to see detailed progress
3. **Preview mode**: Use `-p` to automatically open the PDF after generation
4. **Rate limiting**: The tool respects BrickArchitect's server with 0.5s delays between requests
5. **Error handling**: Invalid parts are skipped with warnings

## Examples

### Generate labels for a collection

```bash
# Create a file with your LEGO parts
echo "3037\n3003\n3001\n3004" > my-collection.txt

# Generate labels
lego-labels --file my-collection.txt --output my-collection-labels.pdf --preview
```

### Quick single label

```bash
lego-labels 3037 --preview
```

### Custom size for larger labels

```bash
lego-labels 3037 3003 --width 100 --height 100
```

## Troubleshooting

### Part not found
If you get a "Part XXXX not found (404)" message:
- Verify the part number is correct
- Check if the part exists on https://brickarchitect.com/parts/XXXX

### Permission errors
Make sure you have write permissions in the current directory.

### Virtual environment issues
Always activate the virtual environment before running:
```bash
source venv/bin/activate  # On macOS/Linux
```

## Next Steps

- Check out the full [README.md](README.md) for more details
- Look at the example [sample-parts.txt](sample-parts.txt) file
- Explore the code in the `lego_labels/` directory
