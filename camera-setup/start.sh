#!/usr/bin/env bash
# tvtv-camera-setup launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PORT="${CAMERA_SETUP_PORT:-8002}"

if [ ! -d "$VENV" ]; then
  echo "Creating camera-setup venv…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
fi

cd "$SCRIPT_DIR"
exec "$VENV/bin/uvicorn" backend.server:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info
