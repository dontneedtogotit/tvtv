#!/usr/bin/env bash
# tvtv-yt TV output detection
# Detects the connected TV's preferred mode via EDID and prints
# the recommended wlr_output / WLR_MODE for Labwc on the NUC.
# Designed for 2013 Samsung 70" TVs which often report 1920x1080@60
# or 3840x2160@30 via HDMI 1.4a.

set -euo pipefail

echo "=== tvtv-yt TV output detection ==="
echo ""

# Check for connected displays via DRM/KMS
if [ ! -d /sys/class/drm ]; then
  echo "ERROR: /sys/class/drm not found. Is this running on the NUC?"
  exit 1
fi

echo "Connected DRM devices:"
for card in /sys/class/drm/card*; do
  [ -d "$card" ] || continue
  echo "  $(basename "$card")"
  for connector in "$card"/card*-*; do
    [ -d "$connector" ] || continue
    name=$(cat "$connector/name" 2>/dev/null || echo "unknown")
    status=$(cat "$connector/status" 2>/dev/null || echo "unknown")
    echo "    $name: $status"
    
    # If connected, read EDID and preferred mode
    if [ "$status" = "connected" ]; then
      echo ""
      echo "    EDID modes for $name:"
      if [ -f "$connector/edid" ]; then
        # Parse EDID for preferred mode
        edid=$(xxd -p "$connector/edid" | tr -d '\n')
        echo "    EDID hex length: ${#edid}/2 bytes"
        
        # Try to extract preferred timing from EDID
        # This is a simplified parse - for full parsing use edid-decode
        preferred_width=$(echo "$edid" | cut -c 79-80 2>/dev/null || echo "?")
        preferred_height=$(echo "$edid" | cut -c 81-82 2>/dev/null || echo "?")
        echo "    Preferred timing (hex): ${preferred_width}x${preferred_height}"
      fi
    fi
  done
done

echo ""
echo "=== Recommended configuration ==="
echo "For 2013 Samsung 70\" via HDMI 1.4a:"
echo ""
echo "Option 1 (1080p@60Hz — safest for HDMI 1.4a):"
echo "  export WLR_OUTPUT=\"HDMI-A-1\""
echo "  export WLR_MODE=\"1920x1080@60\""
echo ""
echo "Option 2 (4K@30Hz — if your TV supports it):"
echo "  export WLR_OUTPUT=\"HDMI-A-1\""
echo "  export WLR_MODE=\"3840x2160@30\""
echo ""
echo "To test modes manually (reboot or restart Labwc after changing):"
echo "  1. Edit ~/.config/labwc/autostart"
echo "  2. Uncomment and set WLR_OUTPUT / WLR_MODE"
echo "  3. systemctl restart tvtv-yt.service"
