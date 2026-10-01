# Built-in Apps & Plugin Ecosystem

tvtv features an extensible app system where each application lives under `apps/<id>/` and declares a `manifest.json`.

---

## App Directory

| App ID | Name | Category | Permissions | Description |
|---|---|---|---|---|
| `media-library` | Media Library | `media` | `storage.read`, `metadata.read` | Scans local & attached storage for movies, videos, and music with strict path confinement. |
| `file-manager` | File Manager | `utility` | `storage.read`, `storage.list` | Confined file browser for local recordings, downloads, and storage volumes. |
| `camera-setup` | Cameras | `utility` | `network.scan`, `storage.read` | IP camera discovery hub with ONVIF/RTSP probing and QR code streaming configs. |
| `remote` | Remote | `utility` | `playback.control` | Web remote companion for mobile devices with virtual D-pad and typing. |
| `store` | App Store | `system` | `system.install`, `plugins.manage` | Inspect installed apps, verify declared permissions, and toggle app availability. |
| `system-update` | System Update | `system` | `system.update` | Check for updates from GitHub releases/main, trigger OTA updates, or 1-click rollback. |
| `settings` | Settings | `system` | `settings.write` | Configure display mode, UI scale, night mode audio, SponsorBlock, and inspect system capabilities. |
| `history` | History | `media` | `history.read` | View watch history and resume in-progress videos at exact timestamp. |
| `installer` | tvtv Installer | `system` | `system.install`, `network.configure` | 10-foot TV OS installation wizard, hardware preset applicator, and ISO baker. |

---

## App Structure

Each app is self-contained:
```
apps/<app-id>/
├── manifest.json       # App metadata, entry points, permissions
├── frontend/           # HTML/CSS/JS single-page interface
│   └── index.html
└── backend/            # FastAPI router backend
    └── server.py       # (or proxy.py for companion services)
```

### Manifest Schema (`plugins/manifest.schema.json`)
```json
{
  "id": "my-app",
  "name": "My App",
  "version": "1.0.0",
  "description": "App description",
  "author": "tvtv",
  "entry": {
    "frontend": "frontend/index.html",
    "backend": "backend/server.py"
  },
  "permissions": ["storage.read"],
  "categories": ["utility"],
  "icon": "📺"
}
```

Apps are lazily imported and mounted at `/apps/<id>/` (backend) and `/apps-frontend/<id>/` (frontend).
