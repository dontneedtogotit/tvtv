#!/usr/bin/env bash
# install.sh — Unified tvtv HTPC Appliance OS Installer & Convergence Engine
# Target: Intel NUC / Mini PC + 70"+ TV over HDMI (Ubuntu 24.04 Noble LTS)
# Repo: https://github.com/dontneedtogotit/tvtv
#
# Usage:
#   sudo ./install.sh                     Full system installation & interactive 10-foot setup
#   sudo ./install.sh --update            Converge system state + update packages
#   sudo ./install.sh --no-packages       Converge system state only (no apt)
#   ./install.sh --check                  Report convergence state (read-only)
#   sudo ./install.sh --customize         Apply 70"+ TV couch UI, display scaling & theme
#   sudo ./install.sh --make-usb /dev/sdX Create bootable USB installer
#   sudo ./install.sh --prepare-ventoy /dev/sdX Prepare Ventoy partition with ISO
#   sudo ./install.sh --bake-iso          Remaster unattended ISO with current config
#   sudo ./install.sh --preset [livingroom|4k|kiosk|full]  Non-interactive preset deployment
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color definitions
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_CYAN=$'\033[0;36m'
  C_GREEN=$'\033[0;32m'
  C_YELLOW=$'\033[0;33m'
  C_RED=$'\033[0;31m'
  C_MAGENTA=$'\033[0;35m'
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_NC=$'\033[0m'
else
  C_CYAN="" C_GREEN="" C_YELLOW="" C_RED="" C_MAGENTA="" C_BOLD="" C_DIM="" C_NC=""
fi

log_info() { printf '%s→%s %s\n' "$C_CYAN" "$C_NC" "$1"; }
log_ok()   { printf '%s✓%s %s\n' "$C_GREEN" "$C_NC" "$1"; }
log_warn() { printf '%s⚠%s %s\n' "$C_YELLOW" "$C_NC" "$1"; }
log_err()  { printf '%s✗%s %s\n' "$C_RED" "$C_NC" "$1" >&2; }

print_banner() {
  printf '\n%s%s' "$C_CYAN" "$C_BOLD"
  printf '%s\n' "╔═══════════════════════════════════════════════════════════════════════╗"
  printf '%s\n' "║              tvtv OS — 10-Foot HTPC Appliance Installer               ║"
  printf '%s\n' "║                 Ubuntu 24.04 Noble LTS • 70\"+ TV Edition              ║"
  printf '%s\n' "╚═══════════════════════════════════════════════════════════════════════╝"
  printf '%s\n' "$C_NC"
}

# ---------------------------------------------------------------------------
# CLI Argument Parsing
# ---------------------------------------------------------------------------
MODE="install"
DO_PACKAGES=1
PRESET_CHOICE=""
TARGET_USB=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --update|-u)       MODE="update" ;;
    --check)           MODE="check" ;;
    --no-packages)     MODE="update"; DO_PACKAGES=0 ;;
    --customize)       MODE="customize" ;;
    --bake-iso)        MODE="bake-iso" ;;
    --make-usb)        MODE="make-usb"; shift; TARGET_USB="${1:-}" ;;
    --prepare-ventoy)  MODE="prepare-ventoy"; shift; TARGET_USB="${1:-}" ;;
    --doctor)          MODE="doctor" ;;
    --preset)          shift; PRESET_CHOICE="${1:-livingroom}" ;;
    --install)         MODE="install" ;;
    -h|--help|help)
      print_banner
      cat <<'EOF'
Usage:
  sudo ./install.sh                     Full system installation / setup
  sudo ./install.sh --update            Converge system state + update packages
  sudo ./install.sh --no-packages       Converge system state only (no apt)
  ./install.sh --check                  Report convergence state (read-only)
  sudo ./install.sh --customize         Apply couch UI & theme tweaks
  sudo ./install.sh --make-usb /dev/sdX Create bootable USB installer
  sudo ./install.sh --prepare-ventoy /dev/sdX Prepare Ventoy partition
  sudo ./install.sh --bake-iso          Remaster unattended ISO
  sudo ./install.sh --preset [preset]   Deploy specific preset non-interactively
                                        (livingroom | 4k | kiosk | full)
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
  shift
done

# Load existing configuration if present
PROFILE_DIR="/home/htpc/.config/tvtv"
if [[ -r "$PROFILE_DIR/tv.conf" ]]; then
  # shellcheck source=/dev/null
  . "$PROFILE_DIR/tv.conf"
fi
HTPC_USER="${TV_USER:-htpc}"

require_root() {
  if [[ $EUID -ne 0 ]]; then
    log_err "Please run as root: sudo $0 $*"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Bad Files & Anti-Stall Cleanup
# ---------------------------------------------------------------------------
BAD_FILES=(
  /etc/X11/xorg.conf.d/20-intel.conf
  /etc/pipewire/pipewire.conf.d/90-hdmi-pin.conf
  /etc/sddm.conf.d/autologin.conf
)

cleanup_bad_files() {
  log_info "Cleaning up deprecated/breaking configs..."
  for f in "${BAD_FILES[@]}"; do
    if [[ -f "$f" ]]; then
      rm -f "$f"
      log_ok "Removed obsolete $f"
    fi
  done
}

# ---------------------------------------------------------------------------
# System Convergence State Items
# ---------------------------------------------------------------------------
check_convergence() {
  print_banner
  log_info "Running read-only system convergence check..."
  echo ""

  local all_good=1

  # Check 1: User & Groups
  if id "$HTPC_USER" &>/dev/null; then
    local missing_groups=()
    for g in audio video render input dialout; do
      if ! id -nG "$HTPC_USER" | grep -qw "$g"; then missing_groups+=("$g"); fi
    done
    if [ ${#missing_groups[@]} -eq 0 ]; then
      log_ok "User '$HTPC_USER' exists with correct hardware groups (render, video, audio, input, dialout)"
    else
      log_warn "User '$HTPC_USER' is missing groups: ${missing_groups[*]}"
      all_good=0
    fi
  else
    log_warn "User '$HTPC_USER' does not exist yet"
    all_good=0
  fi

  # Check 2: Passwordless sudo
  if [[ -f /etc/sudoers.d/90-tvtv ]]; then
    log_ok "Passwordless sudo is configured in /etc/sudoers.d/90-tvtv"
  else
    log_warn "Passwordless sudo is NOT configured"
    all_good=0
  fi

  # Check 3: Screen Locking Disabled
  if [[ -f /etc/xdg/kscreenlockerrc ]] && grep -q "Autolock=false" /etc/xdg/kscreenlockerrc 2>/dev/null; then
    log_ok "TV screen lock and power blanking are disabled"
  else
    log_warn "TV screen locking is NOT disabled"
    all_good=0
  fi

  # Check 4: Password aging
  if chage -l "$HTPC_USER" 2>/dev/null | grep -q "Password expires.*never"; then
    log_ok "Password aging is disabled (autologin will never expire)"
  else
    log_warn "Password aging might cause autologin stalls"
    all_good=0
  fi

  # Check 5: Uinput & CEC rules
  if [[ -f /etc/udev/rules.d/80-uinput.rules ]] && [[ -f /etc/udev/rules.d/99-cec-adapter.rules ]]; then
    log_ok "HDMI-CEC and uinput udev rules are present"
  else
    log_warn "HDMI-CEC / uinput udev rules missing"
    all_good=0
  fi

  # Check 6: Services
  for s in tvtv-yt.service tvtv-updater.service; do
    if systemctl is-enabled "$s" &>/dev/null; then
      log_ok "Systemd service $s is enabled"
    else
      log_warn "Systemd service $s is NOT enabled"
      all_good=0
    fi
  done

  # Check 7: tv.conf
  if [[ -f "$PROFILE_DIR/tv.conf" ]]; then
    log_ok "TV profile exists at $PROFILE_DIR/tv.conf"
  else
    log_warn "TV profile $PROFILE_DIR/tv.conf not found"
    all_good=0
  fi

  echo ""
  if [[ $all_good -eq 1 ]]; then
    log_ok "System is fully converged and ready for 70\"+ TV couch operation!"
  else
    log_warn "System has unapplied convergence items. Run: sudo ./install.sh --update"
  fi
}

# ---------------------------------------------------------------------------
# Core Installation & Convergence Steps
# ---------------------------------------------------------------------------
apply_convergence() {
  require_root
  print_banner
  log_info "Converging system to tvtv HTPC appliance state..."

  # 1. User & Groups
  if ! id "$HTPC_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$HTPC_USER"
    log_ok "Created user '$HTPC_USER'"
  fi
  for grp in audio video render input dialout uinput nopasswdlogin sudo adm plugdev; do
    groupadd -f "$grp" 2>/dev/null || true
    usermod -aG "$grp" "$HTPC_USER" 2>/dev/null || true
  done
  log_ok "User '$HTPC_USER' granted hardware & media group permissions"

  # 2. Sudoers
  mkdir -p /etc/sudoers.d
  cat > /etc/sudoers.d/90-tvtv <<EOF
%sudo ALL=(ALL) NOPASSWD: ALL
$HTPC_USER ALL=(ALL) NOPASSWD: ALL
EOF
  chmod 0440 /etc/sudoers.d/90-tvtv
  log_ok "Passwordless sudo configured"

  # 3. Bad files removal
  cleanup_bad_files

  # 4. Kernel cmdline (no splash)
  if [[ -f /etc/default/grub ]]; then
    sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet"/' /etc/default/grub
    if command -v update-grub &>/dev/null; then
      update-grub >/dev/null 2>&1 || true
    fi
    log_ok "Kernel command line updated (quiet, no plymouth stall)"
  fi

  # 5. Disable screen locking, autolock, and kwalletrc
  mkdir -p /etc/xdg
  cat > /etc/xdg/kscreenlockerrc <<'EOF'
[Daemon]
Autolock=false
LockGrace=0
LockOnResume=false
Timeout=0
EOF
  cat > /etc/xdg/kwalletrc <<'EOF'
[Wallet]
Enabled=false
First Use=false
EOF
  log_ok "Screen locking & wallet prompts disabled"

  # 6. Disable password aging
  chage -M 99999 -m 0 "$HTPC_USER" 2>/dev/null || true
  log_ok "Password expiry disabled for $HTPC_USER"

  # 7. Systemd logind ignore lid/idle
  mkdir -p /etc/systemd/logind.conf.d
  cat > /etc/systemd/logind.conf.d/10-tvtv.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF
  log_ok "Logind lid switch & idle actions ignored"

  # 8. Uinput and CEC udev rules
  mkdir -p /etc/modules-load.d /etc/udev/rules.d
  echo uinput > /etc/modules-load.d/uinput.conf
  modprobe uinput 2>/dev/null || true

  cat > /etc/udev/rules.d/80-uinput.rules <<'EOF'
KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0660", GROUP="uinput", OPTIONS+="static_node=uinput"
EOF

  cat > /etc/udev/rules.d/99-cec-adapter.rules <<'EOF'
KERNEL=="cec[0-9]*", SUBSYSTEM=="cec", MODE="0666", GROUP="dialout"
KERNEL=="ttyACM[0-9]*", SUBSYSTEM=="tty", MODE="0666", GROUP="dialout"
KERNEL=="ttyUSB[0-9]*", SUBSYSTEM=="tty", MODE="0666", GROUP="dialout", ATTRS{idVendor}=="1a44"
EOF
  udevadm control --reload-rules 2>/dev/null || true
  udevadm trigger 2>/dev/null || true
  log_ok "Uinput & HDMI-CEC udev rules installed"

  # 9. Packages (if requested)
  if [[ $DO_PACKAGES -eq 1 ]]; then
    log_info "Installing appliance system packages (apt-get)..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq \
      linux-firmware linux-generic-hwe-24.04 intel-microcode iucode-tool \
      thermald lm-sensors curl wget git \
      python3 python3-venv python3-pip \
      mpv yt-dlp labwc cage swaybg polkitd seatd dbus-x11 xwayland \
      mesa-va-drivers intel-media-va-driver-non-free \
      chromium-browser chromium \
      cec-utils ir-keytable ydotool ydotoold playerctl \
      pipewire pipewire-audio-client-libraries wireplumber alsa-utils \
      fonts-noto fonts-noto-color-emoji xdg-utils zram-tools chrony openssh-server \
      > /dev/null 2>&1 || true
    log_ok "Appliance packages installed"
  fi

  # 10. ZRAM swap
  if [[ -f /etc/default/zramswap ]]; then
    cat > /etc/default/zramswap <<'EOF'
PERCENTAGE=50
PRIORITY=100
EOF
    systemctl restart zramswap 2>/dev/null || true
    log_ok "ZRAM compressed in-memory swap configured"
  fi

  # 11. tv.conf & display setup
  mkdir -p "$PROFILE_DIR"
  if [[ ! -f "$PROFILE_DIR/tv.conf" ]]; then
    bash "$REPO_ROOT/scripts/tv-profile.sh"
    log_ok "Generated default TV profile at $PROFILE_DIR/tv.conf"
  fi
  chown -R "$HTPC_USER:$HTPC_USER" "/home/$HTPC_USER/.config" 2>/dev/null || true

  # 12. Systemd services installation
  log_info "Installing systemd units & session scripts..."
  mkdir -p /usr/local/bin
  if [[ -f "$REPO_ROOT/scripts/tvtv-session.sh" ]]; then
    cp "$REPO_ROOT/scripts/tvtv-session.sh" /usr/local/bin/tvtv-session
    chmod +x /usr/local/bin/tvtv-session
    log_ok "Installed /usr/local/bin/tvtv-session"
  fi

  cp "$REPO_ROOT/scripts/tvtv-yt.service" /etc/systemd/system/
  cp "$REPO_ROOT/updater/tvtv-updater.service" /etc/systemd/system/

  # Ydotoold daemon service
  HTPC_UID="$(id -u "$HTPC_USER" 2>/dev/null || echo 1000)"
  HTPC_GID="$(id -g "$HTPC_USER" 2>/dev/null || echo 1000)"
  cat > /etc/systemd/system/ydotoold.service <<EOF
[Unit]
Description=ydotool daemon (virtual input device for CEC remote)
After=multi-user.target

[Service]
Type=simple
RuntimeDirectory=ydotoold
RuntimeDirectoryMode=0755
ExecStart=/usr/bin/ydotoold --socket-path=/run/ydotoold/socket --socket-own=$HTPC_UID:$HTPC_GID
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

  # CEC Remote Listener Script & Service
  cat > /usr/local/bin/tvtv-cec-remote <<'EOF'
#!/usr/bin/env bash
# tvtv-cec-remote — maps CEC remote key events to desktop controls
set -uo pipefail
export YDOTOOL_SOCKET="/run/ydotoold/socket"

send_key() {
  local code="$1"
  if command -v ydotool >/dev/null 2>&1; then
    ydotool key "${code}:1" 2>/dev/null && sleep 0.04 && ydotool key "${code}:0" 2>/dev/null && return 0
  fi
}

handle_key() {
  case "$1" in
    44|45) playerctl play-pause 2>/dev/null || send_key 164 ;; # Play/Pause
    46)    playerctl stop       2>/dev/null || send_key 128 ;; # Stop
    47)    playerctl next       2>/dev/null || send_key 208 ;; # Fastforward
    48)    playerctl previous   2>/dev/null || send_key 168 ;; # Rewind
    00)    send_key 28  ;; # Select/OK -> Return
    01)    send_key 103 ;; # Up
    02)    send_key 108 ;; # Down
    03)    send_key 105 ;; # Left
    04)    send_key 106 ;; # Right
    0d)    send_key 1   ;; # Back -> Escape
    *)     ;;
  esac
}

if command -v cec-client >/dev/null 2>&1; then
  cec-client -d 8 2>&1 | while read -r line; do
    if [[ "$line" =~ key\ pressed:\ (.+)\ \(([0-9a-fA-F]+)\) ]]; then
      handle_key "${BASH_REMATCH[2]}"
    fi
  done
fi
EOF
  chmod +x /usr/local/bin/tvtv-cec-remote

  cat > /etc/systemd/system/tvtv-cec-remote.service <<EOF
[Unit]
Description=tvtv HDMI-CEC Remote Navigation Listener
After=ydotoold.service
Wants=ydotoold.service

[Service]
Type=simple
User=$HTPC_USER
ExecStart=/usr/local/bin/tvtv-cec-remote
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload 2>/dev/null || true
  systemctl enable tvtv-yt.service tvtv-updater.service ydotoold.service tvtv-cec-remote.service >/dev/null 2>&1 || true
  log_ok "Systemd units enabled (tvtv-yt, tvtv-updater, ydotoold, tvtv-cec-remote)"

  # 13. Autologin setup
  mkdir -p /etc/systemd/system/getty@tty1.service.d
  cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $HTPC_USER --noclear %I \$TERM
Type=idle
EOF

  # 14. .bash_profile for htpc
  cat > "/home/$HTPC_USER/.bash_profile" <<'EOF'
# tvtv HTPC graphical session launcher on tty1
if [ -z "$WAYLAND_DISPLAY" ] && [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
  if [ -x /usr/local/bin/tvtv-session ]; then
    exec /usr/local/bin/tvtv-session
  elif [ -f /home/htpc/tvtv/scripts/tvtv-session.sh ]; then
    exec bash /home/htpc/tvtv/scripts/tvtv-session.sh
  fi
fi
EOF
  chown "$HTPC_USER:$HTPC_USER" "/home/$HTPC_USER/.bash_profile" 2>/dev/null || true

  # 15. Labwc autostart
  mkdir -p "/home/$HTPC_USER/.config/labwc"
  cat > "/home/$HTPC_USER/.config/labwc/autostart" <<'EOF'
#!/usr/bin/env bash
# tvtv-yt Labwc autostart
sleep 2

PROFILE="/home/htpc/.config/tvtv/tv.conf"
if [ -f "$PROFILE" ]; then
  . "$PROFILE"
fi

if [ -n "${WLR_OUTPUT:-}" ] || [ -n "${WLR_MODE:-}" ]; then
  export WLR_OUTPUT WLR_MODE
fi

# Launch Chromium kiosk pointing at local tvtv dashboard
exec chromium --kiosk --noerrdialogs --disable-infobars \
     --disable-features=Translate \
     http://localhost:8000/
EOF
  chmod +x "/home/$HTPC_USER/.config/labwc/autostart"
  chown -R "$HTPC_USER:$HTPC_USER" "/home/$HTPC_USER/.config"

  log_ok "Session autostart and autologin configured"
  echo ""
  log_ok "Installation & state convergence complete!"
}

# ---------------------------------------------------------------------------
# Customize (UI & 70"+ TV scaling)
# ---------------------------------------------------------------------------
do_customize() {
  require_root
  print_banner
  log_info "Configuring 70\"+ TV 10-Foot UI parameters..."

  echo "Select Base UI Scale for 70\"+ TV:"
  echo "  1) 13pt — 65\"-70\" Living Room TV (Recommended)"
  echo "  2) 16pt — 75\"-85\" Large Screen TV"
  echo "  3) 20pt — 85\"+ Stadium / High Distance"
  echo "  4) 10pt — Plasma Bigscreen Native"
  read -r -p "Selection [1-4, default 1]: " SCALE_SEL

  case "${SCALE_SEL:-1}" in
    2) TV_SCALE=16 ;;
    3) TV_SCALE=20 ;;
    4) TV_SCALE=10 ;;
    *) TV_SCALE=13 ;;
  esac

  mkdir -p "$PROFILE_DIR"
  cat > "$PROFILE_DIR/tv.conf" <<EOF
# tvtv HTPC Operating System Configuration
export TV_USER="$HTPC_USER"
export WLR_OUTPUT="HDMI-A-1"
export WLR_MODE="1920x1080@60"
export TV_SCALE="$TV_SCALE"
export TV_FONT_SIZE="$TV_SCALE"
export TV_AUDIO="hdmi"
export TV_NIGHT_MODE="1"
export TV_CEC="yes"
export TV_THEME="estuary"
export TV_SHELL="labwc"
export MPV_VO="gpu"
export MPV_HWDEC="auto-safe"
export KIOSK_URL="http://localhost:8000"
EOF
  chown -R "$HTPC_USER:$HTPC_USER" "$PROFILE_DIR"
  log_ok "Saved TV configuration with UI scale ${TV_SCALE}pt to $PROFILE_DIR/tv.conf"
}

# ---------------------------------------------------------------------------
# USB Creation
# ---------------------------------------------------------------------------
do_make_usb() {
  require_root
  local dev="$1"
  if [[ -z "$dev" ]] || [[ ! -b "$dev" ]]; then
    log_err "Please provide a valid block device (e.g. /dev/sdX)"
    exit 1
  fi
  print_banner
  log_info "Preparing bootable USB installer on $dev..."

  ISO_FILE="$REPO_ROOT/iso-output/tvtv-installer.iso"
  if [[ ! -f "$ISO_FILE" ]]; then
    log_info "Remastered ISO not found, building now..."
    bash "$REPO_ROOT/iso/remaster.sh"
  fi

  log_warn "ALL DATA ON $dev WILL BE ERASED!"
  read -r -p "Type 'yes' to proceed: " CONFIRM
  if [[ "$CONFIRM" != "yes" ]]; then
    log_err "Aborted by user."
    exit 1
  fi

  dd if="$ISO_FILE" of="$dev" bs=4M status=progress oflag=sync
  log_ok "Bootable USB created successfully on $dev!"
}

# ---------------------------------------------------------------------------
# Ventoy USB Preparation
# ---------------------------------------------------------------------------
do_prepare_ventoy() {
  require_root
  local part="$1"
  if [[ -z "$part" ]]; then
    log_err "Usage: sudo $0 --prepare-ventoy /dev/sdXN (the Ventoy data partition)"
    exit 1
  fi
  print_banner
  bash "$REPO_ROOT/iso/create-usb.sh" "$part"
}

# ---------------------------------------------------------------------------
# Bake ISO
# ---------------------------------------------------------------------------
do_bake_iso() {
  print_banner
  log_info "Baking unattended remastered ISO..."
  bash "$REPO_ROOT/iso/remaster.sh"
}

# ---------------------------------------------------------------------------
# Main Routing
# ---------------------------------------------------------------------------
case "$MODE" in
  doctor)
    bash "$REPO_ROOT/scripts/tvtv-doctor.sh"
    ;;
  check)
    check_convergence
    ;;
  update)
    apply_convergence
    ;;
  customize)
    do_customize
    ;;
  make-usb)
    do_make_usb "$TARGET_USB"
    ;;
  prepare-ventoy)
    do_prepare_ventoy "$TARGET_USB"
    ;;
  bake-iso)
    do_bake_iso
    ;;
  install)
    apply_convergence
    ;;
  *)
    log_err "Unknown mode: $MODE"
    exit 1
    ;;
esac
