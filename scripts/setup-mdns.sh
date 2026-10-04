#!/usr/bin/env bash
# setup-mdns.sh: Advertise tvtv via mDNS/Bonjour for discovery (P14-7).
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "setup-mdns: must run as root" >&2
  exit 1
fi

# Install avahi-daemon if not present
if ! command -v avahi-daemon >/dev/null 2>&1; then
  apt-get install -y -qq avahi-daemon >/dev/null 2>&1 || true
fi

# Publish _tvtv._tcp service on the appliance port
mkdir -p /etc/avahi/services
cat > /etc/avahi/services/tvtv.service <<'EOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="tvtv on %h</name>
  <service>
    <type>_tvtv._tcp</type>
    <port>8000</port>
  </service>
</service-group>
EOF

systemctl enable avahi-daemon 2>/dev/null || true
systemctl restart avahi-daemon 2>/dev/null || true
echo "mDNS advertisement configured: _tvtv._tcp on port 8000"
