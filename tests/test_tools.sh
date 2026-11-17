#!/usr/bin/env bash
# Runs the pka-tools unit and command tests (tests/tools/test_*.py).
#
# They are Python `unittest` modules: each one installs the plugin's tool into
# a temporary workspace with `pka-tools install` and then drives the vendored
# `.pka/bin/pka-tools`, so the code under test is the code a workspace runs.

set -u
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PKA_TEST_PYTHON:-python3}"

echo "pka-tools tests under $("$PYTHON" --version 2>&1)"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s "$THIS_DIR/tools" -t "$THIS_DIR/tools" -p 'test_*.py'
