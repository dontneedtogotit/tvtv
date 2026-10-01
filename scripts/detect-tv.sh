#!/usr/bin/env bash
# detect-tv.sh — TV output detection & mode recommendation for 70"+ displays
# Reads DRM/KMS EDID properties and provides recommended WLR_OUTPUT and WLR_MODE.
set -euo pipefail

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║             tvtv OS — 70\"+ TV Display & EDID Detection                ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

if [ ! -d /sys/class/drm ]; then
  echo "WARNING: /sys/class/drm not found (simulated or non-DRM environment)."
  echo "Recommended safe default: 1920x1080@60 on HDMI-A-1 (10-foot UI scale 13pt)"
  exit 0
fi

echo "Scanning connected DRM video outputs..."
CONNECTED_COUNT=0
PRIMARY_CONNECTOR="HDMI-A-1"

for card in /sys/class/drm/card*; do
  [ -d "$card" ] || continue
  for connector in "$card"/card*-*; do
    [ -d "$connector" ] || continue
    name=$(cat "$connector/name" 2>/dev/null || basename "$connector")
    status=$(cat "$connector/status" 2>/dev/null || echo "unknown")
    
    if [ "$status" = "connected" ]; then
      CONNECTED_COUNT=$((CONNECTED_COUNT + 1))
      PRIMARY_CONNECTOR="$name"
      echo "  → Output: $name [CONNECTED]"
      
      if [ -f "$connector/modes" ]; then
        echo "    Supported display modes:"
        head -n 5 "$connector/modes" | sed 's/^/      • /'
      fi
    fi
  done
done

echo ""
echo "=== Recommended 70\"+ TV Settings ==="
echo "Primary Connector: $PRIMARY_CONNECTOR"
echo ""
echo "Option 1: 1080p@60Hz (Safe Default for 2013+ Samsung/LG 70\" over HDMI 1.4a/2.0)"
echo "  export WLR_OUTPUT=\"$PRIMARY_CONNECTOR\""
echo "  export WLR_MODE=\"1920x1080@60\""
echo "  export TV_SCALE=\"13\""
echo ""
echo "Option 2: 4K UHD @ 60Hz (For 4K HDR TVs over HDMI 2.0+)"
echo "  export WLR_OUTPUT=\"$PRIMARY_CONNECTOR\""
echo "  export WLR_MODE=\"3840x2160@60\""
echo "  export TV_SCALE=\"16\""
echo ""
echo "Option 3: 4K UHD @ 30Hz (For 4K TVs over legacy HDMI 1.4b)"
echo "  export WLR_OUTPUT=\"$PRIMARY_CONNECTOR\""
echo "  export WLR_MODE=\"3840x2160@30\""
echo "  export TV_SCALE=\"16\""
