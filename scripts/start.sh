#!/usr/bin/env bash
set -euo pipefail

# tvtv-yt launch script
# Starts the FastAPI backend which also serves the frontend HTML.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/src/backend"
VENV="$PROJECT_DIR/.venv"
PORT="${TVTV_PORT:-8000}"

if [ ! -d "$VENV" ]; then
  echo "Creating venv…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q
fi

cd "$PROJECT_DIR"
exec "$VENV/bin/uvicorn" server:app \
  --app-dir "$BACKEND_DIR" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info
