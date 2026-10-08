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

# --- extract the full base tree -------------------------------------------
# The whole base tree is extracted and rebuilt with `xorriso -as mkisofs`,
# replaying the base's own boot-geometry flags (captured from
# -report_system_area as_mkisofs below). That reproduces the stock-Ubuntu
# hybrid layout: BIOS El Torito (boot.catalog + i386-pc), the UEFI appended
# ESP registered as a GPT EFI-system partition, the GRUB2 MBR template,
# partition_offset 16, and the Joliet descriptor.
#
# Why not edit the base in place (-indev X -outdev X -map ...)? The previous
# build did that and it silently corrupts the hybrid geometry: the replayed
# GPT gets anchored at the session end while the file is padded past it, so
# the backup GPT header does NOT sit at end-of-device (fdisk: "GPT PMBR size
# mismatch" / "backup GPT table is not on the end of the device"), the base's
# 16-sector partition offset is lost, and the Joliet descriptor is dropped.
# UEFI firmwares and Ventoy then report the image as not x64-UEFI-bootable.
#
# Needs ~2.4G in WORK_DIR during the build; freed again afterwards.
FULL_TREE="$WORK_DIR/fulltree"
rm -rf "$FULL_TREE" 2>/dev/null || true
mkdir -p "$FULL_TREE"
echo "Extracting full base ISO tree (includes the ~2.4G squashfs) ..."
# NOTE: in-repo xorriso is 1.5.8.pl02, which rejects the newer
# "-osirrox on:disk_dev=off" mode; plain "on" is fine here (the Ubuntu
# live-server ISO tree carries no device nodes -- they live in the squashfs).
xorriso -osirrox on -indev "$BASE_ISO" -extract / "$FULL_TREE"
[ -s "$FULL_TREE/boot/grub/grub.cfg" ] || { echo "ERROR: base tree extraction failed" >&2; exit 1; }
# xorriso extracts ISO9660 files mode 444; make the tree writable for patching.
chmod -R u+w "$FULL_TREE"
# mkisofs generates the boot catalog itself; a stale extracted copy collides.
rm -f "$FULL_TREE/boot.catalog"

# --- patch GRUB (bake autoinstall args) ----------------------------------
echo "Patching GRUB ..."
if [ "$AUTOINSTALL_MODE" = "self-contained" ]; then
  "$PATCH_GRUB" "$FULL_TREE/boot/grub/grub.cfg" --self-contained --timeout "$GRUB_TIMEOUT"
  "$PATCH_GRUB" "$FULL_TREE/boot/grub/loopback.cfg" --self-contained --timeout "$GRUB_TIMEOUT"
else
  "$PATCH_GRUB" "$FULL_TREE/boot/grub/grub.cfg" --url "$AUTOINSTALL_URL" --timeout "$GRUB_TIMEOUT"
  "$PATCH_GRUB" "$FULL_TREE/boot/grub/loopback.cfg" --url "$AUTOINSTALL_URL" --timeout "$GRUB_TIMEOUT"
fi
# Verify the patches actually landed before shipping the ISO.
for f in "$FULL_TREE/boot/grub/grub.cfg" "$FULL_TREE/boot/grub/loopback.cfg"; do
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
grep -i "ds=" "$FULL_TREE/boot/grub/grub.cfg" || true

# --- stage tvtv repo for embedding into ISO ------------------------------
REPO_ROOT="$(cd "$ISO_DIR/.." && pwd)"
STAGE_DIR="$FULL_TREE/tvtv"
rm -rf "$STAGE_DIR" 2>/dev/null || true
mkdir -p "$STAGE_DIR"
echo "Staging clean tvtv codebase for offline installer image ..."
tar -C "$REPO_ROOT" \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='iso/iso-work' \
  --exclude='iso/iso-tools' \
  --exclude='iso-output' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  -cf - . | tar -C "$STAGE_DIR" -xf -

# --- rebuild the ISO with the base's own boot geometry --------------------
OUT_ISO="$OUTPUT_DIR/tvtv-installer.iso"
echo "Building $OUT_ISO (full -as mkisofs rebuild, stock hybrid boot geometry) ..."
# Capture the exact mkisofs flags describing the base ISO's hybrid boot
# layout: GRUB2 MBR template, protective MBR, GPT, partition offset, the
# appended ESP (GPT EFI-system partition) and both El Torito entries (BIOS
# i386-pc + UEFI). -report_system_area as_mkisofs emits one option or
# option+value per line, designed to be fed back to -as mkisofs; the numbers
# (interval ranges, sizes) are re-derived from the cached base on every
# build, so a newer point release adapts automatically.
# The base path is passed ABSOLUTE so the quoted interval sources inside the
# captured lines are valid verbatim after quote-stripping (paths containing
# spaces would break the word-split below).
BASE_ABS="$(readlink -f "$BASE_ISO")"
# NOTE: the report's option lines go to stdout; the xorriso NOTE/UPDATE
# chatter goes to stderr and is discarded. The awk drops the chatter before
# the first option line and prints every line from there on.
mapfile -t SA_LINES < <(xorriso -indev "$BASE_ABS" -report_system_area as_mkisofs 2>/dev/null | awk '/^-/{p=1} p')
[ "${#SA_LINES[@]}" -gt 0 ] || { echo "ERROR: failed to capture boot flags from the base ISO" >&2; exit 1; }
# Turn the captured lines into argv elements. A value wholly wrapped in
# single quotes stays one argument; anything else is word-split after
# stripping embedded quotes (interval sources carry quoted paths).
SA_ARGS=()
for _ln in "${SA_LINES[@]}"; do
  _flag="${_ln%% *}"
  _rest=""
  if [ "$_ln" != "$_flag" ]; then _rest="${_ln#* }"; fi
  if [ -n "$_rest" ]; then
    case "$_rest" in
      \'*\') SA_ARGS+=("$_flag" "${_rest//\'/}") ;;
      *) read -r -a _words <<< "${_rest//\'/}"
         SA_ARGS+=("$_flag" "${_words[@]}") ;;
    esac
  else
    SA_ARGS+=("${_flag//\'/}")
  fi
done
# The captured set must contain the UEFI-critical options, or the output
# cannot be x64-UEFI-bootable no matter what we map into it.
for _need in -append_partition -appended_part_as_gpt -partition_offset -e; do
  printf '%s\n' "${SA_ARGS[@]}" | grep -qx -- "$_need" \
    || { echo "ERROR: base ISO boot flags missing '$_need'" >&2; exit 1; }
done
echo "Replaying ${#SA_ARGS[@]} boot-geometry arguments captured from the base ISO."
# Bake the autoinstall seed into the tree (self-contained mode only).
if [ "$AUTOINSTALL_MODE" = "self-contained" ]; then
  mkdir -p "$FULL_TREE/autoinstall"
  cp "$ISO_DIR/autoinstall/user-data" "$FULL_TREE/autoinstall/user-data"
  cp "$ISO_DIR/autoinstall/meta-data" "$FULL_TREE/autoinstall/meta-data"
fi
rm -f "$OUT_ISO"
# -iso-level 3 for the 2.4G squashfs, -r for Rock Ridge, -J -joliet-long so
# long /tvtv names survive the Joliet descriptor the base also carries.
xorriso -as mkisofs -iso-level 3 -r -J -joliet-long "${SA_ARGS[@]}" \
  -o "$OUT_ISO" "$FULL_TREE"

# --- verify the hybrid boot layout survived --------------------------------
# Fail loudly instead of shipping a dead image. Grepping for the words
# BIOS/UEFI is NOT enough: the old in-place build false-passed that check
# while its GPT sat short of end-of-file, so firmwares rejected it.
echo "Verifying hybrid boot layout ..."
fail_build() { echo "ERROR: $1" >&2; exit 1; }
BOOT_REPORT="$(xorriso -indev "$OUT_ISO" -report_el_torito plain 2>&1 || true)"
SA_OUT="$(xorriso -indev "$OUT_ISO" -report_system_area plain 2>&1 || true)"
[ -n "$BOOT_REPORT" ] || fail_build "cannot read El Torito report from $OUT_ISO"
printf '%s\n' "$BOOT_REPORT" | grep -Eq 'El Torito boot img :+[[:space:]]+[0-9]+[[:space:]]+BIOS' \
  || fail_build "El Torito BIOS boot image missing"
printf '%s\n' "$BOOT_REPORT" | grep -Eq 'El Torito boot img :+[[:space:]]+[0-9]+[[:space:]]+UEFI' \
  || fail_build "El Torito UEFI boot image missing"
# GPT must be anchored at the true end of the file: if the backup GPT header
# sits short of EOF, UEFI firmware and Ventoy reject the image as not
# x64-UEFI-bootable.
IMG_SECTORS=$(( $(stat -c %s "$OUT_ISO") / 512 ))
GPT_BACKUP="$(printf '%s\n' "$SA_OUT" | awk '/^GPT lba range/ {print $NF}')"
[ -n "$GPT_BACKUP" ] || fail_build "output has no GPT (UEFI via appended ESP lost)"
[ "$((GPT_BACKUP + 1))" -eq "$IMG_SECTORS" ] \
  || fail_build "backup GPT at sector $GPT_BACKUP but image ends at sector $((IMG_SECTORS-1)) (GPT not anchored at end-of-file)"
# Partition offset must match the base (16 on 24.04.x); losing it breaks
# loaders that mount the ISO9660 partition directly.
POFF_OUT="$(printf '%s\n' "$SA_OUT" | awk '/^Partition offset/ {print $4}')"
POFF_BASE="$(xorriso -indev "$BASE_ISO" -report_system_area plain 2>/dev/null | awk '/^Partition offset/ {print $4}')"
[ "$POFF_OUT" = "$POFF_BASE" ] || fail_build "partition offset $POFF_OUT != base $POFF_BASE"
# Joliet descriptor must survive; some loaders enumerate the tree via Joliet.
xorriso -indev "$OUT_ISO" -toc 2>&1 | grep -q 'Joliet' || fail_build "Joliet descriptor missing"
# The fallback UEFI loader file must be present in the ISO tree.
xorriso -indev "$OUT_ISO" -find /EFI -type f 2>/dev/null | grep -qi '/EFI/boot/bootx64.efi' \
  || fail_build "/EFI/boot/bootx64.efi missing from output"
if command -v fdisk >/dev/null 2>&1; then
  if fdisk -l "$OUT_ISO" 2>&1 | grep -qiE 'size mismatch|not on the end'; then
    fail_build "fdisk reports GPT/PMBR inconsistency in $OUT_ISO"
  fi
fi
echo "Boot records intact: BIOS El Torito + UEFI appended ESP; GPT anchored at EOF; Joliet present."
# Best-effort cleanup of the full tree (~2.4G in WORK_DIR).
rm -rf "$FULL_TREE" 2>/dev/null || true
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