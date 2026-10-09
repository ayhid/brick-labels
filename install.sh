#!/bin/sh
# Install lego-labels as a global command with uv, with direct printing support.
# Run it again after changing setup.py dependencies; code changes need no reinstall.
set -e

cd "$(dirname "$0")"

uv tool install --force --editable '.[print]'

# niimprint is not on PyPI and pins Python 3.11, so it goes into the tool's
# environment from git without its pinned dependencies (see README).
uv pip install --python "$(uv tool dir)/lego-labels/bin/python" --no-deps \
    git+https://github.com/AndBondStyle/niimprint

echo "Installed: $(command -v lego-labels || echo "lego-labels (add $(uv tool dir --bin) to your PATH)")"
