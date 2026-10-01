# tvtv — 10-foot HTPC Operating System & Media Appliance

A custom, LibreELEC-like HTPC operating system and media appliance for living-room TVs and Intel Mini PCs / NUCs.
Zero Google API keys. Self-hosted. Agentic AI assistant, full HDMI-CEC remote integration, multi-app ecosystem, camera scanner, and unattended ISO installer.

---

## System Architecture

| Component | Port | Service / Path | Purpose |
|---|---|---|---|
| **tvtv-yt (Core)** | `8000` | `src/backend/server.py` | FastAPI app, MPV session management, YouTube scraping, AI gateway, App Registry |
| **tvtv-updater** | `8001` | `updater/server.py` | Standalone git-based self-updater with backup & rollback |
| **tvtv-camera-setup** | `8002` | `apps/camera-setup/backend/server.py` | LAN camera discovery, MAC OUI fingerprinting, ONVIF/RTSP probing |
| **10-Foot Dashboard** | `8000` | `src/frontend/index.html` | High-contrast 70"+ TV UI with spatial D-pad navigation |
| **Phone Web Remote** | `8000/remote` | `src/frontend/remote.html` | Mobile remote with virtual D-pad, playback controls, text typing |

---

## Built-in Apps (`apps/<id>/`)

All apps are declared with `manifest.json` and mounted into the shell:

1. `media-library` (`/apps-frontend/media-library/`) — Browse and scan local and network media with path confinement.
2. `file-manager` (`/apps-frontend/file-manager/`) — Confined file explorer for local recordings and downloads.
3. `camera-setup` (`/apps-frontend/camera-setup/`) — LAN IP camera surveillance and discovery hub.
4. `remote` (`/apps-frontend/remote/` or `/remote`) — Web remote control companion.
5. `store` (`/apps-frontend/store/`) — App Store with real install state, permission inspection, and app toggling.
6. `system-update` (`/apps-frontend/system-update/`) — OTA OS & application update manager with 1-click rollback.
7. `settings` (`/apps-frontend/settings/`) — Display, audio passthrough, night mode, and hardware capability overview.
8. `history` (`/apps-frontend/history/`) — Keyed watch history and resume position manager.
9. `installer` (`/apps-frontend/installer/`) — 10-foot OS installation wizard and unattended ISO generator.

---

## Quick Start (Development)

```bash
cd /home/z/Projects/tvtv
bash start-all.sh          # Starts core (8000), updater (8001), camera-setup (8002)
# Open http://localhost:8000 in your browser
```

To run individual services:
```bash
bash scripts/start.sh                    # Core app only (8000)
bash updater/start.sh                    # Updater only (8001)
bash apps/camera-setup/start.sh          # Camera setup only (8002)
```

---

## Core API Endpoints

### Playback & Media
- `GET /api/health` — Status, detected hardware, active TV profile, and registered apps
- `GET /api/search?q=...&limit=20` — Fast YouTube search via yt-dlp
- `GET /api/trending?limit=20` — Trending videos
- `GET /api/formats?url=...` — Available audio/video stream formats
- `POST /api/play` — Launch MPV with TV profile (`--vo`, `--hwdec`, `--video-scale`, passthrough, subtitles)
- `POST /api/control` — Send playback (`pause`, `seek±10`, `vol±`, `mute`) or virtual D-pad (`up`, `down`, `enter`, `type:<text>`)
- `GET /api/position` — Live MPV playback position, duration, and paused state
- `POST /api/checkpoint` — Flush current playback position to watch history

### Watch History & Settings
- `GET /history` — Watch history items with position and duration
- `POST /history` — Save or update history item (keyed merge)
- `DELETE /history` — Clear history
- `GET /settings` — Read appliance settings (`settings.json`)
- `POST /settings` — Save settings (preserves unknown/future keys)

### Agentic AI Assistant
- `POST /api/ai/chat` — AI chat with free model rotation (Kilo Gateway)
- `POST /api/ai/chat/stream` — Real-time token streaming (SSE)
- `POST /api/ai/voice` — Fast local regex parser for voice commands

---

## Appliance Installation

### Option 1: Unattended Bootable USB (Recommended)

```bash
# Build custom ISO and flash to USB
sudo ./install.sh --make-usb /dev/sdX

# Boot NUC from USB: installs automatically with zero manual GRUB edits
```

### Option 2: CLI System Convergence on Existing Linux

```bash
# Run convergence installer
sudo ./install.sh --update

# Verify convergence status
./install.sh --check
```

---

## Hardware Target

| Component | Specification |
|---|---|
| **Target Hardware** | Intel NUC (e.g. NUC7i5BNH / i5-7260U, HD 620, 16GB RAM) |
| **Display** | 70"+ TV (HDMI 1.4a/2.0), 1080p@60Hz / 4K UHD |
| **Compositor** | Labwc (Wayland) / Bigscreen, <200MB RAM footprint |
| **Audio Subsystem** | PipeWire low-latency audio with Night Mode EQ and HDMI passthrough |
| **Remote Control** | HDMI-CEC (Pulse-Eight / onboard CEC) mapped to uinput virtual keys |
