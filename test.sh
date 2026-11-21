#!/usr/bin/env bash
# Step 3 (optional) – run the test suite (run ./setup.sh first).
#
#   ./test.sh        all tests, verbose
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
[ -x "$PY" ] || { echo "No .venv found. Run ./setup.sh first."; exit 1; }
exec "$PY" -m unittest discover -s tests -v
