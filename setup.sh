#!/usr/bin/env bash
# Step 1 – create the virtual environment and install everything (Linux / macOS).
#
#   ./setup.sh     creates .venv, installs CPU-only PyTorch + requirements.txt and downloads the model (~1 GB, once)
#
# Safe to run again: steps that are already done are skipped.
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-}" in
  "") ;;
  -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
  *) echo "Unknown option: $1 (see ./setup.sh --help)"; exit 2 ;;
esac
say() { printf '\n==> %s\n' "$1"; }

say "Checking Python"
command -v python3 >/dev/null 2>&1 || { echo "python3 not found. Install Python 3.10 or newer."; exit 1; }
python3 -c 'import sys; v=sys.version_info; sys.exit(0 if v >= (3, 10) else f"Python 3.10+ required, found {sys.version.split()[0]}. On macOS: brew install python@3.12, or the installer from python.org"); ' \
  && python3 -c 'import sys; print("Python", sys.version.split()[0])'

if [ ! -x .venv/bin/python ]; then
  say "Creating virtual environment in .venv"
  python3 -m venv .venv || { echo "Could not create .venv. On Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
else
  say "Virtual environment .venv already exists"
fi
PY=".venv/bin/python"

if ! "$PY" -c "import jinja2, sentence_transformers, langdetect" >/dev/null 2>&1; then
  say "Installing packages (PyTorch without GPU libraries, then requirements.txt)"
  "$PY" -m pip install --upgrade pip
  if [ "$(uname -s)" = "Darwin" ]; then
    # macOS: the regular PyPI wheel has no GPU libraries anyway (CPU / Apple Silicon)
    "$PY" -m pip install torch
  else
    # Linux: the CPU-only build avoids several GB of GPU libraries
    "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
  fi
  "$PY" -m pip install -r requirements.txt
else
  say "Packages already installed"
fi

say "Downloading the embedding model if needed (~470 MB, once)"
# the model named in config/app.json, so setup and the app always use the same one
"$PY" -c "import json; from sentence_transformers import SentenceTransformer; \
SentenceTransformer(json.load(open('config/app.json'))['semantic']['model'])" >/dev/null

say "Checking input files"
"$PY" app.py --check
say "Setup complete. Next: ./start.sh"
