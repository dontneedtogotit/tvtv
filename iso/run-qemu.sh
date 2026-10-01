#!/usr/bin/env bash
set -euo pipefail
ROOTFS="${1:-iso/rootfs}"
IMG="$ROOTFS/rootfs.img"

if [ ! -d "$ROOTFS" ]; then
  echo "Missing rootfs: $ROOTFS"
  exit 1
fi

mkdir -p "$ROOTFS"
truncate -s 4G "$IMG" 2>/dev/null || true

# Note: mkfs is intentionally skipped here because filesystem formatting is
# blocked from the agent. Create the ext4 filesystem manually:
#   mkfs.ext4 -F "$IMG"
# then mount and rsync the rootfs contents.

echo "QEMU image stub prepared: $IMG"
echo "Next manual steps:"
echo "  1. mkfs.ext4 -F $IMG"
echo "  2. mount -o loop $IMG /mnt"
echo "  3. rsync -a --delete $ROOTFS/ /mnt/"
echo "  4. umount /mnt"
