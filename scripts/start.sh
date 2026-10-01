#!/usr/bin/env bash
set -euo pipefail

# tvtv-yt launch script
# Starts the FastAPI backend which also serves the frontend HTML.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/src/backend"
VENV="$PROJECT_DIR/.venv"
PORT="${TVTV_PORT:-8000}"

# Try project venv first
if [ -x "$VENV/bin/uvicorn" ]; then
  UVICORN_CMD=("$VENV/bin/uvicorn")
elif [ -d "$VENV" ] && [ -x "$VENV/bin/python" ]; then
  UVICORN_CMD=("$VENV/bin/python" "-m" "uvicorn")
elif command -v uvicorn >/dev/null 2>&1; then
  UVICORN_CMD=("uvicorn")
else
  # Attempt venv creation if writable
  if python3 -m venv "$VENV" 2>/dev/null && "$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q 2>/dev/null; then
    UVICORN_CMD=("$VENV/bin/uvicorn")
  else
    UVICORN_CMD=("python3" "-m" "uvicorn")
  fi
fi

cd "$PROJECT_DIR"
exec "${UVICORN_CMD[@]}" server:app \
  --app-dir "$BACKEND_DIR" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info
