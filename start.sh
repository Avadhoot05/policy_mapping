#!/usr/bin/env bash
# Step 2 – start the app (run ./setup.sh first).
#
#   ./start.sh               keyword search (default)  → http://127.0.0.1:8000/
#   ./start.sh --semantic    hybrid search (needs ./setup.sh --semantic)
#   ./start.sh --port 8080   use another port
set -euo pipefail
cd "$(dirname "$0")"

MODE="keyword"; PORT="8000"
while [ $# -gt 0 ]; do
  case "$1" in
    --semantic) MODE="hybrid" ;;
    --port) PORT="${2:?--port needs a number}"; shift ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see ./start.sh --help)"; exit 2 ;;
  esac
  shift
done

PY=".venv/bin/python"
[ -x "$PY" ] || { echo "No .venv found. Run ./setup.sh first."; exit 1; }
"$PY" -c "import jinja2" >/dev/null 2>&1 || { echo "Required packages are missing. Run ./setup.sh first."; exit 1; }
if [ "$MODE" = "hybrid" ] && ! "$PY" -c "import sentence_transformers" >/dev/null 2>&1; then
  echo "Semantic packages are not installed. Run ./setup.sh --semantic first."; exit 1
fi
"$PY" app.py --check
printf '\n==> Starting the app (%s search) – open http://127.0.0.1:%s/  (Ctrl+C to stop)\n' "$MODE" "$PORT"
exec "$PY" app.py --port "$PORT" --search-mode "$MODE"
