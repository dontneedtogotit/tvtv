#!/usr/bin/env bash
# setup-storage.sh: Configure dedicated media partition (P11-3).
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "setup-storage: must run as root" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. Mount point
mkdir -p /mnt/tvtv-media

# 2. Install unit files
cp "$REPO_ROOT/infra/systemd/mnt-tvtv-media.mount" /etc/systemd/system/
cp "$REPO_ROOT/infra/systemd/mnt-tvtv-media.automount" /etc/systemd/system/

systemctl daemon-reload
systemctl enable mnt-tvtv-media.automount
systemctl start mnt-tvtv-media.automount
echo "TVTV Media storage configured at /mnt/tvtv-media"
