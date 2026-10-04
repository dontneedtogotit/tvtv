#!/usr/bin/env bash
# firewall-posture.sh — UFW firewall policy for the tvtv appliance (P8-10).
#
# Usage:
#   scripts/firewall-posture.sh kiosk   # default: LAN + SSH only
#   scripts/firewall-posture.sh open    # allow all RFC1918 LAN incoming
#   scripts/firewall-posture.sh status  # print current posture
#
# kiosk posture:
#   - default deny incoming
#   - allow loopback
#   - allow SSH (22/tcp) from anywhere (admin escape hatch)
#   - allow appliance service ports 8000-8002 from RFC1918 LAN ranges only
#
# open posture: same default-deny, but the whole RFC1918 LAN may reach any
# port on the appliance (services, admin, debugging).
#
# Idempotent: rules are only added when missing; enabling UFW twice is a no-op.
# Requires root (install.sh runs it with sudo; the Settings toggle uses
# passwordless sudo on the appliance).
set -euo pipefail

POSTURE="${1:-kiosk}"
LAN_RANGES=("192.168.0.0/16" "10.0.0.0/8" "172.16.0.0/12")
SERVICE_PORTS=(8000 8001 8002)

if ! command -v ufw >/dev/null 2>&1; then
  echo "firewall-posture: ufw is not installed (install it via install.sh or: apt-get install -y ufw)" >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "firewall-posture: must run as root (use sudo)" >&2
  exit 1
fi

case "$POSTURE" in
  status)
    ufw status verbose
    exit 0
    ;;
  kiosk|open)
    ;;
  *)
    echo "usage: $0 {kiosk|open|status}" >&2
    exit 2
    ;;
esac

# ── Always-on basics (applied before enable so SSH is never locked out) ──
if ! ufw status 2>/dev/null | grep -q "22/tcp"; then
  ufw allow 22/tcp
fi
if ! ufw status 2>/dev/null | grep -q " on lo "; then
  ufw allow on lo
fi
ufw default deny incoming
ufw default allow outgoing

# ── Posture-specific rules ──
if [ "$POSTURE" = "kiosk" ]; then
  for port in "${SERVICE_PORTS[@]}"; do
    for lan in "${LAN_RANGES[@]}"; do
      if ! ufw status 2>/dev/null | grep -qE "${port}/tcp.*${lan}"; then
        ufw allow from "$lan" to any port "$port" proto tcp
      fi
    done
  done
else
  for lan in "${LAN_RANGES[@]}"; do
    if ! ufw status 2>/dev/null | grep -qE "ALLOW IN.*${lan}"; then
      ufw allow from "$lan"
    fi
  done
fi

ufw --force enable
echo "firewall-posture: applied '$POSTURE' posture"
ufw status | head -25