#!/usr/bin/env bash
# tvtv-camera-setup launcher with reliable port conflict handling
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PORT="${CAMERA_SETUP_PORT:-8002}"
HOST="${CAMERA_SETUP_HOST:-0.0.0.0}"

if [ ! -d "$VENV" ]; then
  echo "Creating camera-setup venv…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
fi

# Reliably kill anything on the target port
kill_port() {
  local port=$1
  # Try fuser first, fallback to lsof
  fuser -k "${port}/tcp" 2>/dev/null || true
  sleep 1
  lsof -ti ":${port}" 2>/dev/null | xargs kill -9 2>/dev/null || true
  sleep 1
}

kill_port "$PORT"

cd "$SCRIPT_DIR"
echo "Starting camera-setup on $HOST:$PORT…"
exec "$VENV/bin/uvicorn" backend.server:app \
  --host "$HOST" \
  --port "$PORT" \
  --log-level info
