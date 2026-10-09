#!/usr/bin/env bash
# tvtv-session — 10-Foot HTPC Wayland Graphical Shell Session Launcher
# Manages Labwc compositor, Wayland environment, hardware decode, and kiosk shell.
set -uo pipefail

LOG_DIR="${HOME}/.cache/tvtv"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/session.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Starting tvtv HTPC Graphical Session [$(date '+%Y-%m-%d %H:%M:%S')] ==="

# ── 1. Setup XDG & D-Bus Runtime Environment ──────────────────────────────────
USER_ID="$(id -u)"
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
  export XDG_RUNTIME_DIR="/run/user/$USER_ID"
fi
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR" 2>/dev/null || true

export XDG_SESSION_TYPE="wayland"
export XDG_CURRENT_DESKTOP="labwc"
export GDK_BACKEND="wayland,x11"
export QT_QPA_PLATFORM="wayland;xcb"
export MOZ_ENABLE_WAYLAND="1"
export ELECTRON_OZONE_PLATFORM_HINT="auto"
export SDL_VIDEODRIVER="wayland"
export _JAVA_AWT_WM_NONREPARENTING="1"

if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
  if command -v dbus-launch >/dev/null 2>&1; then
    eval "$(dbus-launch --sh-syntax --exit-with-session 2>/dev/null || true)"
    echo "  Initialized D-Bus session: $DBUS_SESSION_BUS_ADDRESS"
  fi
fi

# ── 2. Load TV Profile Configuration ──────────────────────────────────────────
PROFILE_DIR="${HOME}/.config/tvtv"
PROFILE="${PROFILE_DIR}/tv.conf"
if [ ! -f "$PROFILE" ] && [ -f "/home/htpc/.config/tvtv/tv.conf" ]; then
  PROFILE="/home/htpc/.config/tvtv/tv.conf"
fi

if [ -f "$PROFILE" ]; then
  echo "  Loading TV profile: $PROFILE"
  # shellcheck source=/dev/null
  . "$PROFILE"
fi

WLR_OUTPUT="${WLR_OUTPUT:-HDMI-A-1}"
WLR_MODE="${WLR_MODE:-1920x1080@60}"
TV_SCALE="${TV_SCALE:-13}"
TV_THEME="${TV_THEME:-estuary}"
TV_SHELL="${TV_SHELL:-labwc}"
KIOSK_URL="${KIOSK_URL:-http://localhost:8000/}"

export WLR_OUTPUT WLR_MODE TV_SCALE TV_THEME TV_SHELL KIOSK_URL

# ── 3. Configure Labwc Kiosk Profile ──────────────────────────────────────────
LABWC_DIR="${HOME}/.config/labwc"
mkdir -p "$LABWC_DIR"

# Labwc Environment
cat > "${LABWC_DIR}/environment" <<'EOF'
XCURSOR_THEME=Adwaita
XCURSOR_SIZE=24
MOZ_ENABLE_WAYLAND=1
QT_QPA_PLATFORM=wayland;xcb
GDK_BACKEND=wayland,x11
ELECTRON_OZONE_PLATFORM_HINT=auto
EOF

# Labwc rc.xml (Window Rules for 10-Foot TV Kiosk)
cat > "${LABWC_DIR}/rc.xml" <<'EOF'
<?xml version="1.0"?>
<labwc_config>
  <core>
    <decoration>none</decoration>
    <gap>0</gap>
    <reuseOutputMode>yes</reuseOutputMode>
  </core>
  <theme>
    <name>Clearlooks</name>
    <cornerRadius>0</cornerRadius>
    <borderWidth>0</borderWidth>
  </theme>
  <keyboard>
    <default />
    <!-- TV Remote & Media Keybindings -->
    <keybind key="XF86AudioPlay"><action name="Execute" command="playerctl play-pause" /></keybind>
    <keybind key="XF86AudioPause"><action name="Execute" command="playerctl pause" /></keybind>
    <keybind key="XF86AudioStop"><action name="Execute" command="playerctl stop" /></keybind>
    <keybind key="XF86AudioNext"><action name="Execute" command="playerctl next" /></keybind>
    <keybind key="XF86AudioPrev"><action name="Execute" command="playerctl previous" /></keybind>
    <keybind key="XF86AudioRaiseVolume"><action name="Execute" command="wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+" /></keybind>
    <keybind key="XF86AudioLowerVolume"><action name="Execute" command="wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-" /></keybind>
    <keybind key="XF86AudioMute"><action name="Execute" command="wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle" /></keybind>
  </keyboard>
  <mouse>
    <default />
  </mouse>
  <windowRules>
    <windowRule identifier="*" serverDecoration="no" />
  </windowRules>
</labwc_config>
EOF

# Labwc autostart (Launches backend, CEC listener, background, and Chromium kiosk)
# NOTE: labwc spawns this via /bin/sh (it ignores the shebang), so it MUST stay
# POSIX-sh compatible: no bashisms (pipefail, brace expansion, arrays).
cat > "${LABWC_DIR}/autostart" <<'EOF'
#!/bin/sh
# tvtv Labwc 10-foot session autostart (POSIX sh — labwc ignores the shebang)
set -u

# 1. Background Wallpaper
if command -v swaybg >/dev/null 2>&1; then
  swaybg -c '#060a12' >/dev/null 2>&1 &
fi

# 2. TV Display Resolution.
# The profile's WLR_OUTPUT may not match the hardware (a NUC wired over HDMI
# reports DP-1, not HDMI-A-1), so fall back to the first enabled output and
# persist the detected name to tv.conf so reboots stay stable.
if command -v wlr-randr >/dev/null 2>&1; then
  _out="${WLR_OUTPUT:-}"
  if [ -z "$_out" ] || ! wlr-randr 2>/dev/null | grep -q " ${_out} "; then
    # wlr-randr output: name lines start at column 0, properties are indented.
    _out=$(wlr-randr 2>/dev/null | awk '!/^ / && NF { name = $1 } /^  Enabled: yes/ { if (name != "") { print name; exit } }')
  fi
  if [ -n "$_out" ]; then
    if [ -n "${WLR_MODE:-}" ]; then
      # --mode best = the TV's preferred mode; used when the profile's mode
      # is absent from the EDID list (wlr-randr errors on unknown modes).
      wlr-randr --output "$_out" --mode "${WLR_MODE}" >/dev/null 2>&1 || \
        wlr-randr --output "$_out" --mode best >/dev/null 2>&1 || true
    fi
    if [ "$_out" != "${WLR_OUTPUT:-}" ] && [ -f "${HOME}/.config/tvtv/tv.conf" ]; then
      sed -i "s|^export WLR_OUTPUT=.*|export WLR_OUTPUT=\"${_out}\"|" "${HOME}/.config/tvtv/tv.conf" 2>/dev/null || true
    fi
  fi
fi

# 3. Ensure tvtv backend service is up
if ! curl -s --max-time 1 http://localhost:8000/api/health >/dev/null 2>&1; then
  echo "Backend not responding on :8000, starting local server..."
  REPO_ROOT="${HOME}/tvtv"
  if [ -d "$REPO_ROOT" ] && [ -f "$REPO_ROOT/src/backend/server.py" ]; then
    (cd "$REPO_ROOT" && bash scripts/start.sh) >/dev/null 2>&1 &
  fi
fi

# 4. Start Virtual Input & CEC Remote daemon if available
if command -v ydotoold >/dev/null 2>&1 && ! pgrep -x ydotoold >/dev/null 2>&1; then
  ydotoold --socket-path=/run/ydotoold/socket >/dev/null 2>&1 &
fi
if [ -f /usr/local/bin/tvtv-cec-remote ] && ! pgrep -f tvtv-cec-remote >/dev/null 2>&1; then
  /usr/local/bin/tvtv-cec-remote >/dev/null 2>&1 &
fi

# 5. Wait for backend ready
for i in {1..30}; do
  if curl -s --max-time 1 http://localhost:8000/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

# 5b. Backend watchdog (P12-3): if the dashboard/backend dies, restart it
# so a crashed FastAPI process no longer means a dead box.
(
  while true; do
    if ! curl -s --max-time 3 http://localhost:8000/api/health >/dev/null 2>&1; then
      echo "[watchdog] backend down, restarting..."
      REPO_ROOT="${HOME}/tvtv"
      if [ -d "$REPO_ROOT" ] && [ -f "$REPO_ROOT/scripts/start.sh" ]; then
        (cd "$REPO_ROOT" && bash scripts/start.sh) >/dev/null 2>&1 &
      fi
    fi
    sleep 10
  done
) &
WATCHDOG_PID=$!

# 6. Resolve best available browser for Kiosk
BROWSER=""
for b in chromium chromium-browser google-chrome-stable google-chrome brave-browser epiphany-browser cog firefox; do
  if command -v "$b" >/dev/null 2>&1; then
    BROWSER="$b"
    break
  fi
done

KIOSK_TARGET="${KIOSK_URL:-http://localhost:8000/}"

# 7. Launch Kiosk in a continuous supervisor loop
if [ -n "$BROWSER" ]; then
  echo "Launching Kiosk shell with $BROWSER -> $KIOSK_TARGET"
  while true; do
    case "$BROWSER" in
      *cog*)
        cog --platform=wl --kiosk-mode "$KIOSK_TARGET"
        ;;
      *epiphany*)
        epiphany-browser --application-mode --kiosk "$KIOSK_TARGET"
        ;;
      *firefox*)
        "$BROWSER" --kiosk "$KIOSK_TARGET"
        ;;
      *)
        "$BROWSER" \
          --kiosk \
          --noerrdialogs \
          --disable-infobars \
          --disable-gpu \
          --disable-features=Translate,InterestFeedContentSuggestions \
          --check-for-update-interval=31536000 \
          --disable-pinch \
          --overscroll-history-navigation=0 \
          --autoplay-policy=no-user-gesture-required \
          --enable-features=VaapiVideoDecodeLinuxGL,VaapiVideoDecoder \
          --ignore-gpu-blocklist \
          --enable-zero-copy \
          --ozone-platform=x11 \
          "$KIOSK_TARGET"
        ;;
    esac
    echo "Browser exited, restarting in 2 seconds..."
    sleep 2
  done
else
  echo "WARNING: No browser binary found for kiosk!"
fi
EOF
chmod +x "${LABWC_DIR}/autostart"

# ── 4. Launch Wayland Compositor ──────────────────────────────────────────────
if command -v labwc >/dev/null 2>&1; then
  echo "Executing labwc Wayland compositor..."
  exec labwc
elif command -v cage >/dev/null 2>&1; then
  echo "Executing cage kiosk compositor fallback..."
  CAGE_BROWSER=""
  for b in chromium chromium-browser google-chrome-stable epiphany-browser cog firefox; do
    if command -v "$b" >/dev/null 2>&1; then
      CAGE_BROWSER="$b"
      break
    fi
  done
  if [ -n "$CAGE_BROWSER" ]; then
    exec cage -- "$CAGE_BROWSER" --kiosk --ozone-platform=wayland "$KIOSK_URL"
  else
    exec cage -- xdg-open "$KIOSK_URL"
  fi
elif command -v startx >/dev/null 2>&1 || command -v xinit >/dev/null 2>&1; then
  echo "Executing X11 fallback..."
  exec startx
else
  echo "ERROR: Neither labwc nor cage nor X11 compositor is installed." >&2
  exit 1
fi
