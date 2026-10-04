#!/usr/bin/env bash
# setup-logging.sh: Harden journald and configure logrotation (P11-8).
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "setup-logging: must run as root" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. Apply journald configuration
mkdir -p /etc/systemd/journald.conf.d
cp "$REPO_ROOT/infra/systemd/journald.conf" /etc/systemd/journald.conf.d/tvtv.conf
systemctl restart systemd-journald

# 2. Configure logrotate for application logs
cat > /etc/logrotate.d/tvtv <<EOF
/home/htpc/tvtv/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}
EOF

echo "TVTV logging hardened and logrotate configured"
