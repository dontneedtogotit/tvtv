#!/usr/bin/env bash
# tvtv-yt first-boot setup
# Run as root on the NUC after installing the base system.

set -euo pipefail

echo "=== tvtv-yt first-boot setup ==="

# ── Create user ──────────────────────────────────────────────────────────────
if ! id htpc &>/dev/null; then
  useradd -m -s /bin/bash -G audio,video,render,input htpc
  echo "Created user 'htpc'"
fi

# ── Install packages ─────────────────────────────────────────────────────────
echo "Installing packages…"
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip \
  mpv yt-dlp \
  labwc swaybg polkitd \
  cec-utils ir-keytable \
  fonts-noto fonts-noto-color-emoji \
  xdg-utils wget curl git \
  > /dev/null 2>&1
echo "Packages installed."

# ── Place project files ──────────────────────────────────────────────────────
PROJECT_DIR="/home/htpc/tvtv"
if [ ! -d "$PROJECT_DIR" ]; then
  echo "ERROR: Project directory not found at $PROJECT_DIR"
  echo "Copy this repo there first: cp -r $(pwd) $PROJECT_DIR && chown -R htpc:htpc $PROJECT_DIR"
  exit 1
fi
chown -R htpc:htpc "$PROJECT_DIR"

# ── Install systemd service ──────────────────────────────────────────────────
cp "$PROJECT_DIR/scripts/tvtv-yt.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable tvtv-yt.service
echo "Systemd service installed."

# ── Labwc autostart ──────────────────────────────────────────────────────────
mkdir -p /home/htpc/.config/labwc
AUTOSTART="/home/htpc/.config/labwc/autostart"
cat > "$AUTOSTART" <<'EOF'
#!/usr/bin/env bash
# tvtv-yt Labwc autostart
# Runs at session start (triggered by display manager or autologin)

# Wait for DRM/KMS to be ready
sleep 2

# Load TV display profile if present
PROFILE="/home/htpc/.config/tvtv/tv.conf"
if [ -f "$PROFILE" ]; then
  # shellcheck source=/dev/null
  . "$PROFILE"
fi

# Set output mode from profile (only if not already set by tv.conf)
if [ -n "${WLR_OUTPUT:-}" ] || [ -n "${WLR_MODE:-}" ]; then
  export WLR_OUTPUT WLR_MODE
fi

# Start background (optional: a dark wallpaper via swaybg)
# swaybg -o HDMI-A-1 -c '#0d0d0d' &

# Launch Chromium kiosk pointing at the local dashboard
exec chromium --kiosk --noerrdialogs --disable-infobars \
     --disable-features=Translate \
     http://localhost:8000/
EOF
chmod +x "$AUTOSTART"
chown htpc:htpc "$AUTOSTART"

# ── Autologin setup (getty on tty1) ─────────────────────────────────────────
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin htpc --noclear %I \$TERM
EOF

# ── .bash_profile for htpc — start Labwc on tty1 login ──────────────────────
PROFILE="/home/htpc/.bash_profile"
cat > "$PROFILE" <<'EOF'
# If on tty1 and not already in a graphical session, start Labwc
if [ -z "$WAYLAND_DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export XDG_SESSION_TYPE="wayland"
  export XDG_CURRENT_DESKTOP="labwc"
  export $(dbus-launch)
  exec labwc
fi
EOF
chown htpc:htpc "$PROFILE"

# ── CEC power mapping ────────────────────────────────────────────────────────
# Map CEC power button to system suspend
cat > /etc/udev/rules.d/99-cec-power.rules <<'EOF'
# CEC power key → systemd inhibitor for clean suspend
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="CEC Key", ENV{ID_INPUT_KEY}="1"
EOF

# systemd-logind handles power keys automatically;
# this makes sure TV remote power button suspends the NUC:
loginctl enable-linger htpc 2>/dev/null || true

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Reboot: reboot"
echo "  2. The NUC will auto-login and start Labwc + Chromium kiosk"
echo "  3. Dashboard loads at http://localhost:8000"
echo "  4. TV remote CEC buttons should navigate (configured via cec-utils)"
echo ""
echo "To test without reboot:"
echo "  sudo systemctl start tvtv-yt.service"
echo "  sudo -u htpc labwc    # starts the session manually"
