#!/usr/bin/env bash
# Serve the tvtv-yt autoinstall config over HTTP for netboot (Option B).
#
# Boot a stock Ubuntu Server 24.04 ISO on the NUC and, at the GRUB menu, edit
# the "Install Ubuntu Server" entry and append:
#
#     autoinstall ds=nocloud-net;s=http://<THIS-HOST-IP>:8000/
#
# The repo is cloned from GitHub during install (see iso/autoinstall/user-data),
# so this only needs to serve user-data + meta-data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOINSTALL_DIR="$(cd "$SCRIPT_DIR/../iso/autoinstall" && pwd)"
PORT="${PORT:-8000}"

# Detect the LAN IP (first non-loopback IPv4 on the default-route interface).
LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1)"
if [ -z "$LAN_IP" ]; then
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [ -z "$LAN_IP" ]; then
  echo "Could not detect LAN IP; set LAN_IP= manually." >&2
  exit 1
fi

if [ ! -f "$AUTOINSTALL_DIR/user-data" ] || [ ! -f "$AUTOINSTALL_DIR/meta-data" ]; then
  echo "Missing autoinstall files in: $AUTOINSTALL_DIR" >&2
  exit 1
fi

cat <<EOF
================================================================
tvtv-yt netboot autoinstall server
Serving:   $AUTOINSTALL_DIR
URL:       http://$LAN_IP:$PORT/

On the NUC, boot the stock Ubuntu Server 24.04 ISO and append
this to the GRUB "Install Ubuntu Server" entry:

    autoinstall ds=nocloud-net;s=http://$LAN_IP:$PORT/

(repo is cloned from https://github.com/dontneedtogotit/tvtv
 during install -- no need to serve it here)
================================================================
EOF

exec python3 -m http.server "$PORT" --directory "$AUTOINSTALL_DIR"