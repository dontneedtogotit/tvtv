# tvtv-camera-setup

Modern camera detection and setup app for the tvtv HTPC stack.

Detects every camera brand via MAC OUI lookup, HTTP banner fingerprinting, ONVIF probing, and port scanning. Provides a clean, modern web UI for camera setup.

## Features

- **Multi-method detection**: MAC OUI, HTTP banners, ONVIF, port scanning
- **27+ brand database**: Hikvision, Dahua, TP-Link, Reolink, Axis, Foscam, Ezviz, and more
- **Modern UI**: Animated gradients, glassmorphism cards, toast notifications, stats dashboard
- **Export**: JSON/CSV export, copy all RTSP URLs
- **Persistence**: Scan results saved to localStorage
- **Details modal**: Full camera info with copy-to-clipboard RTSP URLs
- **Keyboard support**: Press Enter to scan from network/timeout fields

## Quick start

```bash
cd /home/z/Projects/tvtv/camera-setup
bash start.sh
# Open http://localhost:8002
```

## Unified launcher

```bash
cd /home/z/Projects/tvtv
bash start-all.sh          # start all services
bash start-all.sh camera   # start only camera setup
bash start-all.sh stop     # stop all services
bash start-all.sh status   # check service status
```

## API

- `GET /api/health` — health check
- `GET /api/brands` — list supported brands
- `POST /api/scan` — scan network for cameras
- `POST /api/probe` — probe specific camera for RTSP/ONVIF

## Network setup

The scanner accepts standard CIDR notation (e.g., `192.168.1.0/24`). Make sure your camera is on the same network and ONVIF/RTSP is enabled.
