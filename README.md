# tvtv-yt — 10-foot YouTube HTPC (no API keys)

LibreELEC-like appliance for YouTube on a 2013 Samsung TV + Intel NUC7i5BNH.
Zero Google API keys. Self-hosted. AI-assisted dashboard.

## Components

| File | Purpose |
|---|---|
| `src/backend/server.py` | FastAPI microservice — wraps yt-dlp + MPV |
| `src/frontend/index.html` | 10-foot UI (keyboard/CEC navigation, search grid) |
| `scripts/start.sh` | Development launcher (creates venv, runs uvicorn) |
| `scripts/setup.sh` | First-boot installer — systemd, Labwc, autologin |
| `scripts/tvtv-yt.service` | systemd unit for production |
| `docker-compose.yml` | Optional: self-hosted Invidious (search backend) |
| `scripts/detect-tv.sh` | Detect connected TV EDID/modes via DRM/KMS |
| `scripts/setup-cec.sh` | Configure CEC/Anynet+ for TV remote control |
| `scripts/tv-profile.sh` | Write default TV display/boot profile |

## Quick start (dev)

```bash
cd /home/z/Projects/tvtv
bash scripts/start.sh
# Open http://localhost:8000 in browser
```

## Installation

### Option 1: Bootable USB (recommended)

```bash
# On any Linux machine with the tvtv-yt repo:
sudo ./iso/create-usb.sh /dev/sdX

# Boot NUC from USB, select "tvtv-yt Auto Install"
# Installation takes ~10 minutes, then auto-reboots to HTPC interface
```

### Option 2: Manual install on existing Ubuntu

```bash
# As root, after copying this repo to /home/htpc/tvtv:
bash scripts/setup.sh
# Reboot. Auto-logs in, starts Labwc + Chromium kiosk.
```

## API

- `GET /api/health` — backend status
- `GET /api/search?q=...&limit=20` — search YouTube
- `GET /api/trending?limit=20` — trending videos
- `GET /api/formats?url=...` — list formats for a URL
- `POST /api/play` — `{"url": "https://youtube.com/watch?v=...", "fullscreen": true}` → launches MPV

## Hardware

| Component | Spec |
|---|---|
| TV | Samsung 70" (2013), HDMI 1.4a, Anynet+ CEC |
| NUC | i5-7260U, HD 620, 16GB RAM |
| OS | Ubuntu Server 24.04 LTS + Labwc (Wayland) |

## Why this approach

- No Google API keys (yt-dlp scrapes directly)
- MPV handles 4K/HD with hardware decode on HD 620
- Labwc is ~10MB, boots in seconds
- 16GB RAM is massive headroom for future services
- Entire stack is transparent and fixable if yt-dlp breaks
