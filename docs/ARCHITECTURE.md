# tvtv Architecture

## Architecture Overview

tvtv is structured as a modular HTPC operating system appliance with separated service boundaries:

```
                  ┌────────────────────────────────────────┐
                  │        Chromium Kiosk (Wayland)        │
                  │  http://localhost:8000 (10-foot UI)   │
                  └───────────────────┬────────────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            │                                                   │
┌───────────▼───────────┐   ┌───────────────────────┐   ┌───────▼───────────────┐
│     tvtv-yt Core      │   │     tvtv-updater      │   │   tvtv-camera-setup   │
│       Port 8000       │   │       Port 8001       │   │       Port 8002       │
├───────────────────────┤   ├───────────────────────┤   ├───────────────────────┤
│ • FastAPI Backend     │   │ • Git-based OTA       │   │ • LAN Subnet Scanner  │
│ • App Registry Router │   │ • Automatic Backup    │   │ • MAC OUI Probing     │
│ • MPV IPC Controller  │   │ • 1-Click Rollback    │   │ • ONVIF/RTSP Prober   │
│ • Profile Resolver    │   │ • Service Restarter   │   │ • QR Code Generator   │
│ • AI Assistant        │   └───────────────────────┘   └───────────────────────┘
│ • Shared Focus Shell  │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────┐
│                     App Registry                          │
│               `apps/<app-id>/manifest.json`               │
├───────────────────────────────────────────────────────────┤
│ • media-library   • file-manager    • camera-setup (proxy)│
│ • remote          • store           • system-update       │
│ • settings        • history         • installer           │
└───────────────────────────────────────────────────────────┘
```

## Core Modules (`src/backend/`)

- `server.py`: Primary FastAPI application, endpoint router, static frontend mounts, and background checkpoint loop.
- `profile.py`: Reads and parses `/home/htpc/.config/tvtv/tv.conf` or environment overrides. Resolves hardware options (`MPV_VO`, `MPV_HWDEC`, `MPV_SCALE`, `TV_SCALE`, `TV_AUDIO_PASSTHROUGH`, `TV_NIGHT_MODE`).
- `mpv.py`: In-process Unix domain socket IPC client for MPV player control and automatic position checkpointing.
- `apps.py`: Dynamic `AppRegistry` loader with manifest validation, error isolation, and `sys.modules` registration.
- `history.py`: Keyed watch history storage (`var/history/watch-history.json`) with resume metadata.
- `settings.py`: Atomic settings store (`config/settings.json`) that merges updates without dropping unmodeled keys.
- `subtitles.py`: Subtitle extraction and track selection helper.
- `playback.py`: Live playback state tracker.
- `ai_assistant.py`: Agentic AI assistant with free model rotation via Kilo Gateway.

## Shared Frontend Shell (`shared/frontend-shell/`)

- `focus-nav.js`: 2D spatial focus navigation engine for arrow keys and CEC remotes.
- `theme-tokens.css`: Shared high-contrast theme variables, border radius, spacing, and glowing focus rings.

## System Services (`/etc/systemd/system/`)

- `tvtv-yt.service`: Main backend service running on port 8000 as `htpc` user.
- `tvtv-updater.service`: Self-updater service running on port 8001.
- `ydotoold.service`: Virtual input daemon for remote and CEC key simulation.
- `tvtv-cec-remote.service`: CEC remote key listener.
