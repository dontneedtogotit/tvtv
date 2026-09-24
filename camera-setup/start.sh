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
  # Find and force-kill anything on the port
  local pids
  pids=$(lsof -ti ":${port}" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Killing existing process(es) on port $port: $pids"
    echo "$pids" | xargs kill -9 2>/dev/null || true
  fi
  # Wait for port to actually be released
  local attempts=0
  while [ $attempts -lt 10 ]; do
    if ! lsof -ti ":${port}" >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  echo "Warning: port $port still in use after waiting"
}

kill_port "$PORT"

cd "$SCRIPT_DIR"
echo "Starting camera-setup on $HOST:$PORT…"
exec "$VENV/bin/uvicorn" backend.server:app \
  --host "$HOST" \
  --port "$PORT" \
  --log-level info
