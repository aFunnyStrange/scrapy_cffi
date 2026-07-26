#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON:-python3}
exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/verify_release.py" "$@"
