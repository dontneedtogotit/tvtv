#!/usr/bin/env bash
# tvtv-updater launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PORT="${TVTV_UPDATER_PORT:-8001}"

if [ ! -d "$VENV" ]; then
  echo "Creating updater venv…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
fi

exec "$VENV/bin/uvicorn" server:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info
