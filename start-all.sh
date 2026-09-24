#!/usr/bin/env bash
# tvtv-launcher — start all tvtv services with one command.
# Usage: ./start-all.sh [service]
#   service: all (default), app, updater, camera, stop

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PID_DIR="$SCRIPT_DIR/.pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

start_app() {
  echo "Starting tvtv-yt app…"
  cd "$SCRIPT_DIR"
  bash scripts/start.sh > "$LOG_DIR/app.log" 2>&1 &
  echo $! > "$PID_DIR/app.pid"
  echo "  → PID: $!  Log: $LOG_DIR/app.log"
}

start_updater() {
  echo "Starting tvtv-updater…"
  cd "$SCRIPT_DIR/updater"
  bash start.sh > "$LOG_DIR/updater.log" 2>&1 &
  echo $! > "$PID_DIR/updater.pid"
  echo "  → PID: $!  Log: $LOG_DIR/updater.log"
}

start_camera() {
  echo "Starting tvtv-camera-setup…"
  cd "$SCRIPT_DIR/camera-setup"
  bash start.sh > "$LOG_DIR/camera.log" 2>&1 &
  echo $! > "$PID_DIR/camera.pid"
  echo "  → PID: $!  Log: $LOG_DIR/camera.log"
}

stop_service() {
  local name=$1
  local pid_file="$PID_DIR/${name}.pid"
  if [ -f "$pid_file" ]; then
    local pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name (PID: $pid)…"
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    else
      echo "$name is not running"
    fi
    rm -f "$pid_file"
  else
    echo "$name is not running"
  fi
}

stop_all() {
  stop_service app
  stop_service updater
  stop_service camera
  echo "All services stopped"
}

status() {
  echo "Service Status:"
  echo "==============="
  for service in app updater camera; do
    local pid_file="$PID_DIR/${service}.pid"
    if [ -f "$pid_file" ]; then
      local pid=$(cat "$pid_file")
      if kill -0 "$pid" 2>/dev/null; then
        echo "  $service: running (PID: $pid)"
      else
        echo "  $service: stopped (stale PID file)"
      fi
    else
      echo "  $service: stopped"
    fi
  done
}

case "${1:-all}" in
  all)
    stop_all 2>/dev/null || true
    start_app
    sleep 2
    start_updater
    sleep 1
    start_camera
    echo ""
    echo "All services starting…"
    echo "  tvtv-yt app:       http://localhost:8000"
    echo "  tvtv-updater:      http://localhost:8001"
    echo "  tvtv-camera-setup: http://localhost:8002"
    echo ""
    echo "Logs: $LOG_DIR"
    echo "Stop all: $0 stop"
    ;;
  app)
    start_app
    ;;
  updater)
    start_updater
    ;;
  camera)
    start_camera
    ;;
  stop)
    stop_all
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 [all|app|updater|camera|stop|status]"
    exit 1
    ;;
esac
