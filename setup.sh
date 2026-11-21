#!/usr/bin/env bash
# Step 1 – create the virtual environment (Linux / macOS).
#
#   ./setup.sh               keyword search (default): creates .venv, no packages needed
#   ./setup.sh --semantic    also installs CPU-only PyTorch + sentence-transformers and the model (~0.8 GB, once)
#
# Safe to run again: steps that are already done are skipped.
set -euo pipefail
cd "$(dirname "$0")"

SEMANTIC=0
case "${1:-}" in
  "") ;;
  --semantic) SEMANTIC=1 ;;
  -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
  *) echo "Unknown option: $1 (see ./setup.sh --help)"; exit 2 ;;
esac
MODEL="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
say() { printf '\n==> %s\n' "$1"; }

say "Checking Python"
command -v python3 >/dev/null 2>&1 || { echo "python3 not found. Install Python 3.10 or newer."; exit 1; }
python3 -c 'import sys; v=sys.version_info; sys.exit(0 if v >= (3, 10) else f"Python 3.10+ required, found {sys.version.split()[0]}"); ' \
  && python3 -c 'import sys; print("Python", sys.version.split()[0])'

if [ ! -x .venv/bin/python ]; then
  say "Creating virtual environment in .venv"
  python3 -m venv .venv || { echo "Could not create .venv. On Debian/Ubuntu: sudo apt install python3-venv"; exit 1; }
else
  say "Virtual environment .venv already exists"
fi
PY=".venv/bin/python"

if [ "$SEMANTIC" = "1" ]; then
  if ! "$PY" -c "import sentence_transformers" >/dev/null 2>&1; then
    say "Installing semantic-search packages (CPU-only PyTorch + sentence-transformers)"
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    "$PY" -m pip install -r requirements-semantic.txt
  else
    say "Semantic-search packages already installed"
  fi
  say "Downloading the embedding model if needed (~470 MB, once)"
  "$PY" -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('$MODEL')" >/dev/null
else
  say "Keyword mode needs no packages (standard library only)"
fi

say "Checking input files"
"$PY" app.py --check
say "Setup complete. Next: ./start.sh$([ "$SEMANTIC" = "1" ] && echo " --semantic")"
