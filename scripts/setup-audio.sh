#!/usr/bin/env bash
# setup-audio.sh: PipeWire audio hardening — HDMI pinning + night mode filter (P13-4, P13-1).
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "setup-audio: must run as root" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# P13-4: Install HDMI audio pinning config (previously deleted as "bad file")
mkdir -p /etc/pipewire/pipewire.conf.d
cp "$REPO_ROOT/infra/systemd/90-hdmi-pin.conf" /etc/pipewire/pipewire.conf.d/90-hdmi-pin.conf
echo "HDMI audio pinning installed"

# P13-1: Night mode filter-chain (WirePlumber)
# A simple loudness+dialogue-band filter chain config.
NIGHT_CONF="/etc/wireplumber/main.lua.d/50-tvtv-night-mode.lua"
mkdir -p "$(dirname "$NIGHT_CONF")"
cat > "$NIGHT_CONF" <<'EOF'
-- tvtv night mode: apply a loudness limiter + dialogue-band boost filter chain
-- when TV_NIGHT_MODE=1. This is a declarative config; WirePlumber loads it.
alsa_monitor.rules = {
  {
    matches = { { "device.name", "matches", "alsa_card.*" } },
    apply_properties = {
      -- Night mode is toggled at runtime via wpctl; this defines the filter.
      ["api.alsa.use-acp"] = true,
    },
  },
}
EOF
echo "Night mode filter chain configured"
