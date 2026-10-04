#!/usr/bin/env bash
# run-app-sandboxed.sh — launch a tvtv app backend as an isolated transient
# systemd unit with resource limits (P8-7).
#
# Usage:
#   scripts/run-app-sandboxed.sh <app-id> [extra args...]
#
# The app's own start.sh is executed inside a systemd-run --scope transient
# unit so it gets the same isolation posture as the system services:
# MemoryMax, NoNewPrivileges, ProtectSystem, PrivateTmp.
# Falls back to a plain exec when systemd-run is unavailable (dev machines),
# preserving the pre-sandbox behaviour.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="${1:-}"
if [ -z "$APP_ID" ]; then
  echo "usage: $0 <app-id> [extra args...]" >&2
  exit 2
fi
shift || true

APP_DIR="$REPO_ROOT/apps/$APP_ID"
START_SH="$APP_DIR/start.sh"
if [ ! -x "$START_SH" ]; then
  echo "run-app-sandboxed: no executable start.sh at $START_SH" >&2
  exit 1
fi

if command -v systemd-run >/dev/null 2>&1; then
  exec systemd-run --scope \
    --unit="tvtv-app-${APP_ID}" \
    -p MemoryMax=1G \
    -p NoNewPrivileges=yes \
    -p ProtectSystem=strict \
    -p ProtectHome=read-only \
    -p PrivateTmp=yes \
    -- "$START_SH" "$@"
else
  # No systemd (e.g. dev container): run directly, same as before P8-7.
  exec "$START_SH" "$@"
fi