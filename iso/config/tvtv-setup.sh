#!/usr/bin/env bash
# Thin wrapper: runs the canonical first-boot setup.
# The repo must already be present at /home/htpc/tvtv (baked by iso/Makefile
# or copied by the autoinstall late-commands).
set -euo pipefail
if [ -f /home/htpc/tvtv/scripts/setup.sh ]; then
  exec bash /home/htpc/tvtv/scripts/setup.sh
else
  echo "tvtv-setup: repo not found at /home/htpc/tvtv" >&2
  exit 1
fi
