#!/usr/bin/env bash
# tvtv-camera-setup launcher with port conflict handling
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PORT="${CAMERA_SETUP_PORT:-8002}"
HOST="${CAMERA_SETUP_HOST:-0.0.0.0}"
MAX_RETRIES=3
RETRY_DELAY=2

if [ ! -d "$VENV" ]; then
  echo "Creating camera-setup venv…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
fi

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Port $port is in use by PID(s): $pids. Killing…"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep "$RETRY_DELAY"
  fi
}

# Retry loop for port binding
attempt=1
while [ $attempt -le $MAX_RETRIES ]; do
  kill_port "$PORT"
  
  cd "$SCRIPT_DIR"
  echo "Starting camera-setup on $HOST:$PORT (attempt $attempt/$MAX_RETRIES)…"
  if "$VENV/bin/uvicorn" backend.server:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info; then
    exit 0
  fi
  
  echo "Start attempt $attempt failed. Retrying in ${RETRY_DELAY}s…"
  sleep "$RETRY_DELAY"
  attempt=$((attempt + 1))
done

echo "Failed to start camera-setup after $MAX_RETRIES attempts."
exit 1
