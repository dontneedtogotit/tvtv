#!/usr/bin/env bash
# setup-identity.sh: Branded `tvtv-os` identity for appliance.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "setup-identity: must run as root" >&2
  exit 1
fi

# 1. /etc/os-release
cat > /etc/os-release <<EOF
PRETTY_NAME="tvtv OS 0.1.0"
NAME="tvtv-os"
ID="tvtv-os"
VERSION="0.1.0"
VERSION_ID="0.1.0"
EOF

# 2. hostname
hostnamectl set-hostname tvtv-os

# 3. /etc/issue
echo "tvtv OS \l" > /etc/issue
echo "" >> /etc/issue

# 4. Boot branding (if Plymouth exists)
if command -v plymouth >/dev/null 2>&1; then
  # Simple branding: overwrite the default splash
  echo "[Daemon]" > /etc/plymouth/plymouthd.conf
  echo "Theme=spinner" >> /etc/plymouth/plymouthd.conf
  plymouth-set-default-theme -R spinner
fi
