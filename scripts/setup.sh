#!/usr/bin/env bash
# tvtv HTPC Operating System — First-Boot Setup & Convergence Engine
# Target: 70"+ TV Appliance (Ubuntu 24.04 Noble LTS)
# Run as root during installation or first-boot.
set -uo pipefail

echo "=== tvtv HTPC OS First-Boot Setup ==="

# Load TV profile if present
PROFILE_DIR="/home/htpc/.config/tvtv"
PROFILE="$PROFILE_DIR/tv.conf"
if [ -f "$PROFILE" ]; then
  # shellcheck source=/dev/null
  . "$PROFILE"
fi

HTPC_USER="${TV_USER:-htpc}"
TV_SHELL="${TV_SHELL:-labwc}"
TV_THEME="${TV_THEME:-estuary}"
TV_SCALE="${TV_SCALE:-13}"
WLR_OUTPUT="${WLR_OUTPUT:-HDMI-A-1}"
WLR_MODE="${WLR_MODE:-1920x1080@60}"
TV_NIGHT_MODE="${TV_NIGHT_MODE:-1}"
TV_CEC="${TV_CEC:-yes}"

# ── 1. Create User & Hardware Permissions ─────────────────────────────────────
if ! id "$HTPC_USER" &>/dev/null; then
  useradd -m -s /bin/bash "$HTPC_USER"
  echo "Created user '$HTPC_USER'"
fi

for grp in audio video render input dialout uinput nopasswdlogin sudo adm plugdev; do
  groupadd -f "$grp" 2>/dev/null || true
  usermod -aG "$grp" "$HTPC_USER" 2>/dev/null || true
done

# Passwordless sudo
mkdir -p /etc/sudoers.d
cat > /etc/sudoers.d/90-tvtv <<EOF
%sudo ALL=(ALL) NOPASSWD: ALL
$HTPC_USER ALL=(ALL) NOPASSWD: ALL
EOF
chmod 0440 /etc/sudoers.d/90-tvtv

# ── 2. Clean Up Breaking/Deprecated Configs ───────────────────────────────────
for bad in /etc/X11/xorg.conf.d/20-intel.conf /etc/pipewire/pipewire.conf.d/90-hdmi-pin.conf; do
  [ -f "$bad" ] && rm -f "$bad"
done

# Disable screen blanking, sleep, and wallet
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

# Disable password aging so autologin never expires
chage -M 99999 -m 0 "$HTPC_USER" 2>/dev/null || true

# Ignore lid switch & idle actions
mkdir -p /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/10-tvtv.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF

# ── 3. Uinput & HDMI-CEC Setup ───────────────────────────────────────────────
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

# ── 4. Verify Project Files & Dependencies ────────────────────────────────────
PROJECT_DIR="/home/$HTPC_USER/tvtv"
if [ ! -d "$PROJECT_DIR" ]; then
  if [ -d "$(pwd)" ] && [ -f "$(pwd)/src/backend/server.py" ]; then
    mkdir -p "$PROJECT_DIR"
    cp -a "$(pwd)/." "$PROJECT_DIR/"
  else
    echo "Cloning tvtv repository..."
    git clone --depth 1 https://github.com/dontneedtogotit/tvtv.git "$PROJECT_DIR" || true
  fi
fi
chown -R "$HTPC_USER:$HTPC_USER" "$PROJECT_DIR" 2>/dev/null || true

# Setup Python Virtual Environment
VENV="$PROJECT_DIR/.venv"
if [ ! -d "$VENV" ]; then
  echo "Setting up Python virtual environment..."
  python3 -m venv "$VENV" 2>/dev/null || true
  if [ -f "$PROJECT_DIR/src/backend/requirements.txt" ] && [ -x "$VENV/bin/pip" ]; then
    "$VENV/bin/pip" install -r "$PROJECT_DIR/src/backend/requirements.txt" -q 2>/dev/null || true
  fi
fi
chown -R "$HTPC_USER:$HTPC_USER" "$VENV" 2>/dev/null || true

# ── 5. Install System Session & Helper Scripts ────────────────────────────────
mkdir -p /usr/local/bin

if [ -f "$PROJECT_DIR/scripts/tvtv-session.sh" ]; then
  cp "$PROJECT_DIR/scripts/tvtv-session.sh" /usr/local/bin/tvtv-session
  chmod +x /usr/local/bin/tvtv-session
fi

# CEC Remote Listener Script
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

# ── 6. Install Systemd Units ──────────────────────────────────────────────────
echo "Installing appliance systemd units..."
if [ -f "$PROJECT_DIR/scripts/tvtv-yt.service" ]; then
  cp "$PROJECT_DIR/scripts/tvtv-yt.service" /etc/systemd/system/
fi
if [ -f "$PROJECT_DIR/updater/tvtv-updater.service" ]; then
  cp "$PROJECT_DIR/updater/tvtv-updater.service" /etc/systemd/system/
fi

# Inject KILO_API_KEY into tvtv-yt.service if present in environment
if [ -n "${KILO_API_KEY:-}" ]; then
  sed -i "/^Environment=TVTV_PORT/a Environment=KILO_API_KEY=$KILO_API_KEY" /etc/systemd/system/tvtv-yt.service 2>/dev/null || true
  echo "  KILO_API_KEY injected into tvtv-yt.service for agentic AI assistant"
fi

# Ydotoold service
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

# CEC Remote Service
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

# Safe reload and enable (fails gracefully inside chroot/installer environments)
systemctl daemon-reload 2>/dev/null || true
systemctl enable tvtv-yt.service tvtv-updater.service ydotoold.service tvtv-cec-remote.service 2>/dev/null || true

# ── 7. TV Profile Configuration ───────────────────────────────────────────────
mkdir -p "$PROFILE_DIR"
if [ ! -f "$PROFILE" ]; then
  cat > "$PROFILE" <<EOF
# tvtv HTPC Operating System Configuration
export TV_USER="$HTPC_USER"
export WLR_OUTPUT="$WLR_OUTPUT"
export WLR_MODE="$WLR_MODE"
export TV_SCALE="$TV_SCALE"
export TV_FONT_SIZE="$TV_SCALE"
export TV_AUDIO="hdmi"
export TV_NIGHT_MODE="$TV_NIGHT_MODE"
export TV_CEC="$TV_CEC"
export TV_THEME="$TV_THEME"
export TV_SHELL="$TV_SHELL"
export MPV_VO="gpu"
export MPV_HWDEC="auto-safe"
export KIOSK_URL="http://localhost:8000"
EOF
fi
chown -R "$HTPC_USER:$HTPC_USER" "$PROFILE_DIR" 2>/dev/null || true

# ── 8. Autologin & 10-Foot Graphic Shell Startup ──────────────────────────────
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $HTPC_USER --noclear %I \$TERM
Type=idle
EOF

# User .bash_profile executes tvtv-session
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

# Ensure labwc config directory is created
mkdir -p "/home/$HTPC_USER/.config/labwc"
chown -R "$HTPC_USER:$HTPC_USER" "/home/$HTPC_USER/.config" 2>/dev/null || true

echo "=== tvtv HTPC OS Setup Complete ==="
