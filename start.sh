#!/usr/bin/env bash
# Step 2 – start the app (run ./setup.sh first).
#
#   ./start.sh               → http://127.0.0.1:8000/
#   ./start.sh --port 8080   use another port
set -euo pipefail
cd "$(dirname "$0")"

PORT="8000"
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="${2:?--port needs a number}"; shift ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see ./start.sh --help)"; exit 2 ;;
  esac
  shift
done

PY=".venv/bin/python"
[ -x "$PY" ] || { echo "No .venv found. Run ./setup.sh first."; exit 1; }
"$PY" -c "import jinja2, sentence_transformers, langdetect" >/dev/null 2>&1 || { echo "Required packages are missing. Run ./setup.sh first."; exit 1; }
"$PY" app.py --check
printf '\n==> Starting the app – open http://127.0.0.1:%s/  (Ctrl+C to stop)\n' "$PORT"
exec "$PY" app.py --port "$PORT"
