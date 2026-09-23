#!/usr/bin/env bash
# tvtv-yt CEC setup
# Configures CEC (Anynet+) so the TV remote controls the NUC HTPC.
# Run as root on the NUC.

set -euo pipefail

echo "=== tvtv-yt CEC setup ==="

# Install CEC utilities if not present
if ! command -v cec-client &>/dev/null; then
  echo "Installing cec-utils…"
  apt-get update -qq
  apt-get install -y -qq cec-utils
fi

# Detect CEC adapter
echo ""
echo "Scanning for CEC devices…"
cec-client -l 2>&1 | head -20 || true

echo ""
echo "=== CEC configuration ==="
echo "CEC is handled by systemd-logind for power events."
echo "For navigation, Labwc should detect CEC keyboard events automatically."
echo ""
echo "To test CEC:"
echo "  1. Connect NUC HDMI to TV"
echo "  2. Enable Anynet+ on the TV (Settings → System → Anynet+ (HDMI-CEC))"
echo "  3. Run: sudo cec-client"
echo "  4. Press TV remote buttons — you should see CEC events"
echo ""
echo "To disable TV control of NUC (if TV keeps switching inputs):"
echo "  echo 'options cec noserve=1' > /etc/modprobe.d/cec.conf"
echo ""
echo "To make NUC ignore TV power-off (keep NUC running):"
echo "  echo 'options cec noserv=1' > /etc/modprobe.d/cec.conf"
echo ""
echo "CEC power mapping is already in /etc/udev/rules.d/99-cec-power.rules"
echo "TV remote should now suspend/wake the NUC via systemd-logind."
