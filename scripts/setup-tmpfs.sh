#!/usr/bin/env bash
# setup-tmpfs.sh: Flash write-endurance policy (P11-12).
# Redirects logs/caches to tmpfs to reduce eMMC/SD write cycles.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "setup-tmpfs: must run as root" >&2
  exit 1
fi

# Add tmpfs entries to /etc/fstab for log/cache directories that grow unbounded.
# Only add if not already present.
if ! grep -q 'tmpfs.*/var/log' /etc/fstab; then
  echo "tmpfs /var/log tmpfs defaults,noatime,size=100M,mode=0755 0 0" >> /etc/fstab
fi

if ! grep -q 'tmpfs.*/home/htpc/.cache' /etc/fstab; then
  echo "tmpfs /home/htpc/.cache tmpfs defaults,noatime,size=200M,mode=0755,uid=1000,gid=1000 0 0" >> /etc/fstab
fi

if ! grep -q 'tmpfs.*/tmp' /etc/fstab; then
  echo "tmpfs /tmp tmpfs defaults,noatime,size=500M,mode=1777 0 0" >> /etc/fstab
fi

echo "tmpfs write-endurance policy configured (P11-12)"
