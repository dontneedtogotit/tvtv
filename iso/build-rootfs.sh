#!/usr/bin/env bash
set -euo pipefail

ROOTFS_DIR="${1:-iso/rootfs}"
MIRROR="${TVTV_MIRROR:-http://archive.ubuntu.com/ubuntu/}"
SUITE="${TVTV_SUITE:-noble}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root"
  exit 1
fi

mkdir -p "$ROOTFS_DIR"
if ! command -v debootstrap >/dev/null 2>&1; then
  echo "debootstrap not found. Install it first: apt-get install -y debootstrap"
  exit 1
fi

echo "Building rootfs (suite=$SUITE) in $ROOTFS_DIR ..."
debootstrap --variant=minbase "$SUITE" "$ROOTFS_DIR" "$MIRROR" >/dev/null 2>&1 || {
  echo "debootstrap failed. Check the mirror and network."
  exit 1
}

cat > "$ROOTFS_DIR/first-boot.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
echo "Running tvtv first-boot setup..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip mpv yt-dlp labwc swaybg polkitd cec-utils ir-keytable fonts-noto fonts-noto-color-emoji xdg-utils wget curl git >/dev/null 2>&1 || true
useradd -m -s /bin/bash -G audio,video,render,input htpc || true
mkdir -p /home/htpc/media
echo "First boot complete."
EOS
chmod +x "$ROOTFS_DIR/first-boot.sh"

echo "Rootfs created at $ROOTFS_DIR"
