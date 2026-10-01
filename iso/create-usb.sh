#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: sudo $0 /dev/sdX"
  exit 1
fi

TARGET="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ISO_PATH="${ISO_PATH:-$PROJECT_DIR/iso-output/tvtv-installer.iso}"

if [ ! -f "$ISO_PATH" ]; then
  echo "Missing ISO: $ISO_PATH"
  echo "Build it first with: bash $PROJECT_DIR/iso/remaster.sh"
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root"
  exit 1
fi

echo "Copying ISO to Ventoy USB: $TARGET"
mkdir -p /mnt/tvtv-ventoy
mount "$TARGET" /mnt/tvtv-ventoy
mkdir -p /mnt/tvtv-ventoy/iso
cp "$ISO_PATH" /mnt/tvtv-ventoy/iso/tvtv-installer.iso
cp "$PROJECT_DIR/iso/ventoy/ventoy.json" /mnt/tvtv-ventoy/ventoy/
sync
umount /mnt/tvtv-ventoy
echo "Ventoy USB ready. Boot NUC from USB and select tvtv Installer."
