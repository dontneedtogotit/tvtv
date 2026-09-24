#!/usr/bin/env bash
# tvtv-yt USB Creator
# Creates a bootable Ubuntu Server USB with tvtv-yt pre-configured.
# Usage: sudo ./create-usb.sh /dev/sdX

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: sudo $0 /dev/sdX"
  echo "Example: sudo $0 /dev/sdb"
  echo ""
  echo "WARNING: This will ERASE all data on the target device!"
  exit 1
fi

TARGET="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ISO_URL="https://releases.ubuntu.com/24.04.2/ubuntu-24.04.2-live-server-amd64.iso"
ISO_NAME="ubuntu-24.04.2-live-server-amd64.iso"
MOUNT_POINT="/mnt/tvtv-usb"
WORK_DIR="/tmp/tvtv-usb-work"

# Check root
if [ "$EUID" -ne 0 ]; then
  echo "ERROR: This script must be run as root (use sudo)"
  exit 1
fi

# Confirm target
echo "========================================="
echo "  tvtv-yt USB Creator"
echo "========================================="
echo ""
echo "Target device: $TARGET"
echo "This will ERASE all data on $TARGET"
echo ""
read -p "Are you sure? (type 'YES' to continue): " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 1
fi

# Download ISO if not present
if [ ! -f "/tmp/$ISO_NAME" ]; then
  echo "Downloading Ubuntu Server ISO…"
  wget -q --show-progress -O "/tmp/$ISO_NAME" "$ISO_URL"
fi

# Cleanup
umount "$TARGET"* 2>/dev/null || true
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# Create partition table (GPT)
echo "Creating partition table…"
parted -s "$TARGET" mklabel gpt
parted -s "$TARGET" mkpart primary fat32 1MiB 2GiB
parted -s "$TARGET" mkpart primary linux-swap 2GiB 4GiB
parted -s "$TARGET" mkpart primary ext4 4GiB 100%
parted -s "$TARGET" set 1 boot on

# Format partitions
echo "Formatting partitions…"
BOOT_PART="${TARGET}1"
SWAP_PART="${TARGET}2"
DATA_PART="${TARGET}3"

mkfs.vfat -F32 -n tvtv-boot "$BOOT_PART"
mkswap -L tvtv-swap "$SWAP_PART"
mkfs.ext4 -L tvtv-data "$DATA_PART"

# Mount and extract ISO
mkdir -p "$MOUNT_POINT"
mount "$BOOT_PART" "$MOUNT_POINT"

echo "Extracting ISO…"
mkdir -p "$WORK_DIR/iso"
mount -o loop "/tmp/$ISO_NAME" "$WORK_DIR/iso" 2>/dev/null || \
  7z x "/tmp/$ISO_NAME" -o"$WORK_DIR/iso" > /dev/null 2>&1

# Copy ISO contents to boot partition
cp -r "$WORK_DIR/iso"/* "$MOUNT_POINT/" 2>/dev/null || true
cp -r "$WORK_DIR/iso"/.* "$MOUNT_POINT/" 2>/dev/null || true

# Add autoinstall config
echo "Adding autoinstall config…"
mkdir -p "$MOUNT_POINT/autoinstall"
cp "$PROJECT_DIR/iso/autoinstall/user-data" "$MOUNT_POINT/autoinstall/"
cp "$PROJECT_DIR/iso/autoinstall/meta-data" "$MOUNT_POINT/autoinstall/"

# Modify GRUB to autoinstall
echo "Configuring bootloader…"
GRUB_CFG="$MOUNT_POINT/boot/grub/grub.cfg"
if [ -f "$GRUB_CFG" ]; then
  # Add autoinstall boot entry
  cat >> "$GRUB_CFG" <<'EOF'

menuentry "tvtv-yt Auto Install" {
  set gfxpayload=keep
  linux /casper/vmlinuz quiet autoinstall ds=nocloud-net;s=http://10.0.2.2:8000/autoinstall/ ---
  initrd /casper/initrd
}
EOF
fi

# Copy tvtv-yt project files to data partition
echo "Copying tvtv-yt files…"
mkdir -p "$MOUNT_POINT/tvtv"
cp -r "$PROJECT_DIR"/* "$MOUNT_POINT/tvtv/" 2>/dev/null || true

# Add first-boot setup script to initramfs
echo "Adding first-boot setup…"
mkdir -p "$MOUNT_POINT/scripts"
cp "$PROJECT_DIR/scripts/setup.sh" "$MOUNT_POINT/scripts/"
cp "$PROJECT_DIR/scripts/start.sh" "$MOUNT_POINT/scripts/"
cp "$PROJECT_DIR/scripts/tvtv-yt.service" "$MOUNT_POINT/scripts/"
chmod +x "$MOUNT_POINT/scripts/"*.sh

# Create README
cat > "$MOUNT_POINT/README.txt" <<'EOF'
tvtv-yt Bootable USB
====================

1. Boot from this USB on your NUC
2. Select "tvtv-yt Auto Install" from the GRUB menu
3. The installer will:
   - Install Ubuntu Server 24.04 LTS
   - Create user 'htpc' with password 'tvtv'
   - Install all dependencies (MPV, yt-dlp, Labwc, Chromium)
   - Copy tvtv-yt to /home/htpc/tvtv
   - Configure auto-login and kiosk mode
   - Reboot automatically

4. After reboot:
   - The system will auto-login and start Labwc + Chromium kiosk
   - Dashboard loads at http://localhost:8000
   - Connect your TV via HDMI

Default credentials:
  Username: htpc
  Password: tvtv

To update later:
  sudo bash /home/htpc/tvtv/scripts/start.sh
  Open http://localhost:8000

Troubleshooting:
  - If display is wrong: sudo bash /home/htpc/tvtv/scripts/detect-tv.sh
  - If CEC doesn't work: sudo bash /home/htpc/tvtv/scripts/setup-cec.sh
  - Logs: journalctl -u tvtv-yt.service
EOF

# Sync and unmount
sync
umount "$MOUNT_POINT"
umount "$WORK_DIR/iso" 2>/dev/null || true

# Cleanup
rm -rf "$WORK_DIR"

echo ""
echo "========================================="
echo "  USB Creation Complete!"
echo "========================================="
echo ""
echo "Boot from this USB on your NUC."
echo "Select 'tvtv-yt Auto Install' from the menu."
echo ""
echo "Default credentials:"
echo "  Username: htpc"
echo "  Password: tvtv"
echo ""
echo "After installation, the system will:"
echo "  1. Auto-login as htpc"
echo "  2. Start Labwc + Chromium kiosk"
echo "  3. Load dashboard at http://localhost:8000"
echo ""
