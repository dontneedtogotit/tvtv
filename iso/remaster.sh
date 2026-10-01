#!/usr/bin/env bash
# Remaster a stock Ubuntu Server 24.04 ISO into a custom tvtv-yt installer.
#
# Bakes the autoinstall kernel args into the default GRUB boot entry so you
# flash the ISO, boot the NUC, and it auto-installs tvtv-yt -- no GRUB editing.
set -euo pipefail
#
# TWO MODES:
#   1. Self-contained (DEFAULT): bake `ds=nocloud;` and embed user-data/meta-data
#      on the ISO. The NUC installs with NO external server required.
#      Just flash the ISO to Ventoy/USB and boot.
#   2. LAN-served (OPT-IN): bake `ds=nocloud-net;s=http://<IP>:8000/` and serve
#      the autoinstall config from this machine at boot time. Requires the
#      build host to be powered on and running scripts/serve-autoinstall.sh
#      when the NUC boots.
#
# Usage:
#   # Self-contained (recommended; no LAN server needed):
#   ./iso/remaster.sh
#   # -> iso-output/tvtv-installer.iso  (or OUTPUT_DIR= override)
#   # Flash to Ventoy/USB, boot NUC, done.
#
#   # LAN-served (legacy; build host must be on at NUC boot):
#   AUTOINSTALL_MODE=lan ./scripts/serve-autoinstall.sh &
#   AUTOINSTALL_MODE=lan ./iso/remaster.sh
#   # -> iso-output/tvtv-installer.iso
#   # Boot NUC while serve-autoinstall.sh is still running.
#
# Env overrides:
#   AUTOINSTALL_MODE     "self-contained" (default) or "lan"
#   AUTOINSTALL_IP       bake this IP instead of auto-detecting the LAN IP (LAN mode)
#   PORT                 config-server port (default 8000, LAN mode only)
#   BASE_ISO_URL         full URL to a stock 24.04 live-server ISO
#   WORK_DIR             scratch dir (default iso/iso-work)
#   OUTPUT_DIR           output dir (default iso-output; use /tmp on full /home)
#   GRUB_TIMEOUT         GRUB menu timeout in seconds (default 10)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISO_DIR="$SCRIPT_DIR"

# Prefer a project-local xorriso (iso/iso-tools) so the build needs neither a
# system package nor root/sudo.
if [ -d "$ISO_DIR/iso-tools/usr/bin" ]; then
  export PATH="$ISO_DIR/iso-tools/usr/bin:$PATH"
  export LD_LIBRARY_PATH="$ISO_DIR/iso-tools/usr/lib:${LD_LIBRARY_PATH:-}"
fi

AUTOINSTALL_MODE="${AUTOINSTALL_MODE:-self-contained}"
OUTPUT_DIR="${OUTPUT_DIR:-$ISO_DIR/../iso-output}"
WORK_DIR="${WORK_DIR:-$ISO_DIR/iso-work}"
GRUB_TIMEOUT="${GRUB_TIMEOUT:-10}"
PATCH_GRUB="$ISO_DIR/patch-grub.py"

# --- tool check -----------------------------------------------------------
if ! command -v xorriso >/dev/null 2>&1; then
  echo "xorriso not found. Install it once with:" >&2
  echo "    sudo apt-get install -y xorriso" >&2
  exit 1
fi

# --- resolve autoinstall URL for LAN mode --------------------------------
if [ "$AUTOINSTALL_MODE" = "lan" ]; then
  if [ -z "${AUTOINSTALL_IP:-}" ]; then
    AUTOINSTALL_IP="$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1)"
    [ -z "$AUTOINSTALL_IP" ] && AUTOINSTALL_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  if [ -z "$AUTOINSTALL_IP" ]; then
    echo "Could not detect LAN IP; set AUTOINSTALL_IP= manually." >&2
    exit 1
  fi
  PORT="${PORT:-8000}"
  AUTOINSTALL_URL="http://$AUTOINSTALL_IP:$PORT/"
  echo "Baking autoinstall URL (LAN mode): $AUTOINSTALL_URL"
else
  echo "Building self-contained ISO (no LAN server required at NUC boot)"
  AUTOINSTALL_URL=""
fi

# --- fetch the base ISO ---------------------------------------------------
# Resolve the latest 24.04 point release. Older point releases get moved to
# old-releases.ubuntu.com (24.04.2 is already gone), so auto-detect from the
# live /24.04/ index and fall back to the newest known release.
BASE_ISO_NAME="${BASE_ISO_NAME:-}"
BASE_ISO_URL="${BASE_ISO_URL:-}"
if [ -z "$BASE_ISO_NAME" ] || [ -z "$BASE_ISO_URL" ]; then
  _idx="$(wget -qO- --timeout=30 https://releases.ubuntu.com/24.04/ 2>/dev/null || true)"
  _latest="$(printf '%s\n' "$_idx" | grep -oE 'ubuntu-24\.04\.[0-9]+-live-server-amd64\.iso' | sort -V | tail -1)"
  [ -z "$_latest" ] && _latest="ubuntu-24.04.5-live-server-amd64.iso"
  BASE_ISO_NAME="${BASE_ISO_NAME:-$_latest}"
  BASE_ISO_URL="${BASE_ISO_URL:-https://releases.ubuntu.com/24.04/$BASE_ISO_NAME}"
fi
BASE_ISO_FALLBACK_URL="https://old-releases.ubuntu.com/releases/24.04/$BASE_ISO_NAME"

mkdir -p "$WORK_DIR" "$OUTPUT_DIR"
BASE_ISO="$WORK_DIR/$BASE_ISO_NAME"

# `--show-progress` only makes sense on a TTY; in a non-interactive/background
# run it floods the output buffer (and can trip tcsetattr). Go quiet there.
# Download with curl -C - (NOT wget -O: wget -c -O truncates on open, so an
# interrupted run destroys the partial). curl -C - resumes from the existing
# file size and never truncates. Retry on network hiccups.
if [ -t 1 ]; then
  _curl_opts=(-C - --retry 10 --retry-delay 3 --retry-all-errors)
else
  _curl_opts=(-C - -sS --retry 10 --retry-delay 3 --retry-all-errors)
fi
echo "Fetching $BASE_ISO_NAME (resumes if partial) ..."
# A file already matching the server's advertised size is complete -- skip the
# fetch entirely. Without this, curl -C - still issues a request on every run
# and a renamed/leftover base image (e.g. base.iso) gets re-downloaded from
# scratch, wasting the full 4GB.
_expected_size="$(curl -sIL --max-time 30 "$BASE_ISO_URL" 2>/dev/null \
  | tr -d '\r' | sed -n 's/^[Cc]ontent-[Ll]ength: *\([0-9]\+\).*$/\1/p' | tail -1)"
if [ -n "$_expected_size" ] && [ -f "$BASE_ISO" ] \
   && [ "$(stat -c %s "$BASE_ISO" 2>/dev/null || echo 0)" = "$_expected_size" ]; then
  echo "  already complete ($_expected_size bytes), skipping download"
else
  for _attempt in 1 2 3 4 5 6 7 8 9 10; do
    curl "${_curl_opts[@]}" -o "$BASE_ISO" "$BASE_ISO_URL" && break
    echo "Download attempt $_attempt from primary failed, trying fallback ..." >&2
    curl "${_curl_opts[@]}" -o "$BASE_ISO" "$BASE_ISO_FALLBACK_URL" && break
    echo "Both URLs failed on attempt $_attempt; waiting 10s and retrying ..." >&2
    sleep 10
  done
fi
# Hard check: a partial file means every attempt failed.
[ -s "$BASE_ISO" ] || { echo "Base ISO download failed: $BASE_ISO is missing/empty" >&2; exit 1; }

# --- extract the files we patch -------------------------------------------
# Only grub.cfg and loopback.cfg leave the ISO. Targeted single-file extracts
# avoid leaving a 550M read-only tree behind (xorriso extracts ISO9660 files
# 444; whole-tree cleanup then fights permissions and wastes disk).
# The base is edited IN PLACE (xorriso -indev base -map ... -outdev): this
# preserves its exact hybrid boot layout -- BIOS El Torito (boot.catalog +
# i386-pc) plus the UEFI APPENDED ESP partition and the GRUB2 MBR template --
# while swapping only the files we change. Recreating from a tree with
# `-as mkisofs` drops the appended ESP unless the El Torito `-e` interval is
# byte-perfect, which is fragile across point releases.
EXTRACT_DIR="$WORK_DIR/extract"
rm -rf "$EXTRACT_DIR" 2>/dev/null || true
mkdir -p "$EXTRACT_DIR/boot/grub"
echo "Extracting GRUB configs ..."
for f in grub.cfg loopback.cfg; do
  xorriso -osirrox on -indev "$BASE_ISO" -extract "/boot/grub/$f" "$EXTRACT_DIR/boot/grub/$f"
  [ -s "$EXTRACT_DIR/boot/grub/$f" ] || { echo "ERROR: failed to extract /boot/grub/$f" >&2; exit 1; }
  chmod u+w "$EXTRACT_DIR/boot/grub/$f"
done

# --- patch GRUB (bake autoinstall args) ----------------------------------
echo "Patching GRUB ..."
if [ "$AUTOINSTALL_MODE" = "self-contained" ]; then
  "$PATCH_GRUB" "$EXTRACT_DIR/boot/grub/grub.cfg" --self-contained --timeout "$GRUB_TIMEOUT"
  "$PATCH_GRUB" "$EXTRACT_DIR/boot/grub/loopback.cfg" --self-contained --timeout "$GRUB_TIMEOUT"
else
  "$PATCH_GRUB" "$EXTRACT_DIR/boot/grub/grub.cfg" --url "$AUTOINSTALL_URL" --timeout "$GRUB_TIMEOUT"
  "$PATCH_GRUB" "$EXTRACT_DIR/boot/grub/loopback.cfg" --url "$AUTOINSTALL_URL" --timeout "$GRUB_TIMEOUT"
fi
# Verify the patches actually landed before shipping the ISO.
for f in "$EXTRACT_DIR/boot/grub/grub.cfg" "$EXTRACT_DIR/boot/grub/loopback.cfg"; do
  if [ ! -s "$f" ]; then
    echo "ERROR: $f is missing/empty after patching" >&2
    exit 1
  fi
  if ! grep -q "ds=" "$f" 2>/dev/null; then
    echo "ERROR: $f was not patched (missing ds=)" >&2
    exit 1
  fi
done
echo "GRUB patch verified:"
grep -i "ds=" "$EXTRACT_DIR/boot/grub/grub.cfg" || true

# --- update the base ISO in place ----------------------------------------
OUT_ISO="$OUTPUT_DIR/tvtv-installer.iso"
echo "Building $OUT_ISO (in-place update of base ISO) ..."
# Remove any prior output first (the copy below overwrites it). The in-place
# update then keeps the base's MBR, El Torito BIOS+UEFI boot entries, and
# appended ESP intact.
# Build method (verified): a single `xorriso -indev BASE -outdev OUT` re-
# serialises the image and DROPS the hybrid boot record (BIOS El Torito +
# appended UEFI ESP + GRUB MBR) -- the output comes out with zero El Torito
# boot images and an all-zero MBR, i.e. unbootable. The reliable path is to
# COPY the base to the output first, then open that same file read-write and
# -map the patched files in place (indev==outdev). Updating an existing image
# keeps its boot record byte-for-byte intact.
rm -f "$OUT_ISO"
cp "$BASE_ISO" "$OUT_ISO"
XORRISO_ARGS=(
  -osirrox on
  -indev "$OUT_ISO"
  -outdev "$OUT_ISO"
  -map "$EXTRACT_DIR/boot/grub/grub.cfg" /boot/grub/grub.cfg
  -map "$EXTRACT_DIR/boot/grub/loopback.cfg" /boot/grub/loopback.cfg
)
if [ "$AUTOINSTALL_MODE" = "self-contained" ]; then
  XORRISO_ARGS+=(-map "$ISO_DIR/autoinstall/user-data" /autoinstall/user-data)
  XORRISO_ARGS+=(-map "$ISO_DIR/autoinstall/meta-data" /autoinstall/meta-data)
fi
# Re-register the hybrid boot record (BIOS El Torito + appended UEFI ESP +
# MBR) exactly as found in the base image. Without this, the in-place -map
# update discards the El-Torito boot information and the output is
# unbootable. Per the xorriso man page, replay must come AFTER all file
# manipulations are done, just before -close.
XORRISO_ARGS+=(-boot_image any replay)
XORRISO_ARGS+=(-close)
xorriso "${XORRISO_ARGS[@]}"

# --- verify boot records survived -----------------------------------------
# A bootable hybrid image must still carry BOTH El Torito boot images
# (BIOS + UEFI) after the in-place update. If they were discarded, the ISO
# will not boot on the NUC -- fail loudly instead of shipping a dead image.
BOOT_REPORT="$(xorriso -indev "$OUT_ISO" -report_el_torito plain 2>/dev/null || true)"
BIOS_IMG="$(printf '%s\n' "$BOOT_REPORT" | grep -c 'BIOS' || true)"
UEFI_IMG="$(printf '%s\n' "$BOOT_REPORT" | grep -c 'UEFI' || true)"
if [ "$BIOS_IMG" -lt 1 ] || [ "$UEFI_IMG" -lt 1 ]; then
  echo "ERROR: output ISO is missing boot records (BIOS=$BIOS_IMG UEFI=$UEFI_IMG)." >&2
  echo "The in-place update dropped the hybrid boot layout; $OUT_ISO is unbootable." >&2
  printf '%s\n' "$BOOT_REPORT" >&2
  exit 1
fi
echo "Boot records intact: BIOS El Torito + UEFI (appended ESP) present."
# Best-effort cleanup of the extract tree (may leave read-only remnants; not
# a build failure -- just wastes ~500M in WORK_DIR).
chmod -R u+w "$EXTRACT_DIR" 2>/dev/null || true
rm -rf "$EXTRACT_DIR" 2>/dev/null || true
echo "Build complete; freed extract tree:"
df -h "$WORK_DIR" | tail -1

echo
echo "Custom installer built: $OUT_ISO"
echo "Flash it and boot the NUC -- the autoinstall runs unattended."
echo "  sudo dd if=$OUT_ISO of=/dev/sdX bs=4M status=progress oflag=sync"
if [ "$AUTOINSTALL_MODE" = "lan" ]; then
  echo "Config server must be reachable at: $AUTOINSTALL_URL"
else
  echo "Self-contained: no config server needed at boot."
fi