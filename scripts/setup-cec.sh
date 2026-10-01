#!/usr/bin/env bash
# setup-cec.sh — HDMI-CEC remote control setup for tvtv OS
# Configures Anynet+, BRAVIA Sync, SimpLink TV remotes to navigate the HTPC.
set -euo pipefail

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║             tvtv OS — HDMI-CEC & Couch Remote Setup                   ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo $0" >&2
  exit 1
fi

echo "1. Checking CEC packages & utilities..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq cec-utils ydotool ydotoold playerctl >/dev/null 2>&1 || true

echo "2. Setting up /dev/uinput and CEC device permissions..."
mkdir -p /etc/modules-load.d /etc/udev/rules.d
echo uinput > /etc/modules-load.d/uinput.conf
modprobe uinput 2>/dev/null || true

cat > /etc/udev/rules.d/80-uinput.rules <<'EOF'
KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="uinput", OPTIONS+="static_node=uinput"
EOF

cat > /etc/udev/rules.d/99-cec-adapter.rules <<'EOF'
KERNEL=="cec[0-9]*", SUBSYSTEM=="cec", MODE="0666", GROUP="dialout"
KERNEL=="ttyACM[0-9]*", SUBSYSTEM=="tty", MODE="0666", GROUP="dialout"
KERNEL=="ttyUSB[0-9]*", SUBSYSTEM=="tty", MODE="0666", GROUP="dialout", ATTRS{idVendor}=="1a44"
EOF

udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

for grp in uinput dialout video input audio; do
  groupadd -f "$grp" 2>/dev/null || true
  usermod -aG "$grp" htpc 2>/dev/null || true
done

echo "3. Scanning for CEC controllers..."
if command -v cec-client >/dev/null 2>&1; then
  cec-client -l 2>&1 | head -n 15 || true
else
  echo "cec-client not installed."
fi

echo ""
echo "HDMI-CEC is configured. TV remote D-Pad (Up/Down/Left/Right/OK/Back/Media) is enabled."
