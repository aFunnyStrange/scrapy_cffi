#!/usr/bin/env bash
set -euxo pipefail

python -m pip install --upgrade pip build twine

# Clean
find . -type d -name '__pycache__' -exec rm -rf {} +
find . -type f -name '*.py[co]' -delete

# Build
python -m build
