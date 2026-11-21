#!/usr/bin/env bash
# Runs the tests of the eval runner (tests/evals/test_*.py).
#
# They cover evals/run.py itself: the setup vocabulary, transcript and diff
# capture, the judge-response parser, result aggregation and --dry-run. The
# Claude Code CLI is replaced by tests/evals/fake_claude.py, so no model is
# called and nothing touches the network. The evals themselves are not run
# here: that costs money and is started by hand (see evals/README.md).

set -u
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PKA_TEST_PYTHON:-python3}"

echo "eval runner tests under $("$PYTHON" --version 2>&1)"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m unittest discover -s "$THIS_DIR/evals" -t "$THIS_DIR/evals" -p 'test_*.py'
