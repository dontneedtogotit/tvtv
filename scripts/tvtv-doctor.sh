#!/usr/bin/env bash
# tvtv-doctor.sh — Comprehensive HTPC appliance diagnostic & repair assistant
# Inspired by tvpc-doctor for 70"+ TV Linux setups.
set -euo pipefail

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_CYAN=$'\033[0;36m'
  C_GREEN=$'\033[0;32m'
  C_YELLOW=$'\033[0;33m'
  C_RED=$'\033[0;31m'
  C_BOLD=$'\033[1m'
  C_NC=$'\033[0m'
else
  C_CYAN="" C_GREEN="" C_YELLOW="" C_RED="" C_BOLD="" C_NC=""
fi

log_ok()   { printf '%s✓%s %s\n' "$C_GREEN" "$C_NC" "$1"; }
log_warn() { printf '%s⚠%s %s\n' "$C_YELLOW" "$C_NC" "$1"; }
log_err()  { printf '%s✗%s %s\n' "$C_RED" "$C_NC" "$1"; }

printf '\n%s%s╔═══════════════════════════════════════════════════════════════════════╗%s\n' "$C_CYAN" "$C_BOLD" "$C_NC"
printf '%s%s║                tvtv OS — 70\"+ HTPC System Doctor                      ║%s\n' "$C_CYAN" "$C_BOLD" "$C_NC"
printf '%s%s╚═══════════════════════════════════════════════════════════════════════╝%s\n\n' "$C_CYAN" "$C_BOLD" "$C_NC"

echo "=== 1. Display & DRM KMS ==="
if [ -d /sys/class/drm ]; then
  for card in /sys/class/drm/card*; do
    [ -d "$card" ] || continue
    for connector in "$card"/card*-*; do
      [ -d "$connector" ] || continue
      name=$(cat "$connector/name" 2>/dev/null || basename "$connector")
      status=$(cat "$connector/status" 2>/dev/null || echo "unknown")
      if [ "$status" = "connected" ]; then
        log_ok "Video output $name: CONNECTED"
        if [ -f "$connector/modes" ]; then
          modes=$(head -n 3 "$connector/modes" | tr '\n' ' ')
          echo "    Available modes: $modes"
        fi
      fi
    done
  done
else
  log_warn "No /sys/class/drm detected"
fi

echo ""
echo "=== 2. Audio & PipeWire ==="
if command -v pactl >/dev/null 2>&1; then
  default_sink=$(pactl get-default-sink 2>/dev/null || echo "unknown")
  log_ok "Default audio sink: $default_sink"
elif command -v wpctl >/dev/null 2>&1; then
  default_sink=$(wpctl status 2>/dev/null | grep -A 2 "Audio" | grep -m 1 "*" | tr -s ' ' || echo "unknown")
  log_ok "Default audio sink (wpctl): $default_sink"
else
  log_warn "Neither pactl nor wpctl is installed"
fi

echo ""
echo "=== 3. Hardware Video Acceleration & VA-API (P9-12) ==="
if [ -e /dev/dri/renderD128 ]; then
  log_ok "Direct Rendering Manager node exists: /dev/dri/renderD128"
  if id -nG 2>/dev/null | grep -qw "render"; then
    log_ok "Current user has 'render' hardware group access"
  else
    log_warn "Current user lacks 'render' group (required for Intel VA-API decode)"
  fi
else
  log_warn "No /dev/dri/renderD128 node found (hardware decode may be disabled)"
fi

if command -v vainfo >/dev/null 2>&1; then
  va_driver=$(vainfo 2>&1 | grep -iE 'driver|va_openDriver' | head -n 2 | tr '\n' ' ' || true)
  if [ -n "$va_driver" ]; then
    log_ok "VA-API Driver: $va_driver"
  fi
  profiles=$(vainfo 2>&1 | grep -iE 'VAProfile(H264|HEVC|VP9|AV1)' | awk '{print $1}' | sort -u | tr '\n' ' ' || true)
  if [ -n "$profiles" ]; then
    echo "    Hardware Decoders: $profiles"
  fi
else
  echo "    vainfo not installed (install 'va-driver-all vainfo' to verify codecs)"
fi

echo ""
echo "=== 4. HDMI-CEC Remote Controller ==="
if command -v cec-client >/dev/null 2>&1; then
  adapters=$(cec-client -l 2>&1 | grep -iE 'adapter|path|device' | head -n 4 || true)
  if [ -n "$adapters" ]; then
    log_ok "CEC Adapter found:"
    printf '%s\n' "$adapters" | sed 's/^/    /'
  else
    log_warn "No physical CEC adapter detected. Plug in Pulse-Eight USB-CEC adapter if NUC lacks onboard CEC."
  fi
else
  log_warn "cec-utils (cec-client) is not installed"
fi

echo ""
echo "=== 5. Appliance Systemd Services ==="
for svc in tvtv-yt.service tvtv-updater.service ydotoold.service tvtv-cec-remote.service; do
  if systemctl is-active "$svc" &>/dev/null; then
    log_ok "$svc is RUNNING"
  elif systemctl is-enabled "$svc" &>/dev/null; then
    log_warn "$svc is ENABLED but not currently running"
  else
    log_warn "$svc is not enabled / installed"
  fi
done

echo ""
echo "=== 6. Network & Phone Web Remote ==="
lan_ip=$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1)
if [ -n "$lan_ip" ]; then
  log_ok "LAN IP: $lan_ip"
  echo "    Phone Web Remote:   http://$lan_ip:8000/remote"
  echo "    tvtv Dashboard:     http://$lan_ip:8000"
  echo "    OTA Self-Updater:   http://$lan_ip:8001"
  echo "    Camera Setup:       http://$lan_ip:8002"
else
  log_warn "No active LAN IP route detected"
fi

echo ""
echo "=== 7. Storage & ZRAM Swap ==="
df -h / | tail -1 | awk '{print "    Root disk (/): " $2 " total, " $3 " used, " $4 " available (" $5 " used)"}'
if swapon --show | grep -q "zram"; then
  log_ok "ZRAM compressed in-memory swap is active"
else
  log_warn "ZRAM swap is not active"
fi

echo ""
log_ok "Doctor diagnostics complete."
