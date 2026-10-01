# tvtv — HTPC OS Roadmap

Goal: turn this repo into a complete, LibreELEC-like HTPC operating system
with a custom 10-foot web GUI, app ecosystem, media management, and
installable appliance image.

Status legend: `[x]` shipped · `[~]` partially shipped (stub, dead flag, or
unwired config) · `[ ]` not started. Every `[~]` names what is missing.

---

## Vision

- Bootable HTPC appliance image with read-only root + A/B update slots
- Auto-setup: network, display, CEC/remote, storage, audio
- LibreELEC-style 10-foot interface with app tiles
- Custom GUI apps for media, settings, updates, remote control
- Extensible, sandboxed app/plugin system with a permission model
- Watch history, resume playback, user profiles
- OTA self-update for OS + apps, with rollback
- Zero Google API keys; self-hosted and repairable end to end

---

## Where we are

Phases 0, 1 and 6 shipped a working unattended install path: remastered ISO,
Ubuntu autoinstall user-data generator, Ventoy config, Labwc autologin,
Chromium kiosk, four FastAPI services (app 8000, updater 8001, camera 8002),
CEC→ydotool remote bridge, yt-dlp/MPV playback, AI assistant, and 8
registered apps.

Phases 2–5 are **not** done. What exists is a good-looking shell plus stubs:
most app backends are a single `/health` route, `metadata_providers` reports
three providers with `enabled: False` and makes no HTTP calls, the store has
no lifecycle, several installer options write environment variables that
nothing reads, and there is no test suite, no CI, no API auth, and no
systemd hardening. Phases 7–18 below close that gap in priority order.

---

## Shipped phases

### Phase 0: Foundation — done
`roadmap/phase-0.md` — repo structure, plugin manifest schema, shared frontend
shell (focus nav, theme tokens), backend app registry, ISO build + QEMU smoke
test, first bootable dashboard image.

### Phase 1: Core OS & Installer — done
`roadmap/phase-1.md` — preseeded image builder, auto-partition + user
creation, network manager integration, EDID/display + audio configuration,
CEC remote + power events, storage auto-mount, systemd units, Ventoy-ready
installer app with hardware presets.

### Phase 6: Ventoy/USB Installer — done
`roadmap/phase-6.md` — installer app UI, full autoinstall user-data generator
(validated against the canonical subiquity schema), GRUB patcher +
`remaster.sh` for both BIOS and UEFI, Ventoy menu config, USB copy script,
and fully baked self-contained `iso-output/tvtv-installer.iso` (3.9GB).
`[ ]` hardware boot test on the physical NUC is ready when user flashes USB.

---

## Phased delivery

| Phase | Scope | File | Status |
|---|---|---|---|
| 0 | Foundation | `roadmap/phase-0.md` | done |
| 1 | Core OS & Installer | `roadmap/phase-1.md` | done |
| 6 | Ventoy/USB Installer | `roadmap/phase-6.md` | done, hardware test open |
| 7 | Honesty & Wiring | `roadmap/phase-7.md` | done |
| 8 | Security & Isolation | `roadmap/phase-8.md` | in progress |
| 9 | Player Core | `roadmap/phase-9.md` | not started |
| 10 | Library & Metadata | `roadmap/phase-10.md` | not started |
| 11 | OS Identity, Rootfs & Storage | `roadmap/phase-11.md` | not started |
| 12 | Boot, Session & Display | `roadmap/phase-12.md` | not started |
| 13 | Audio Engine | `roadmap/phase-13.md` | not started |
| 14 | Network, Remote & Casting | `roadmap/phase-14.md` | not started |
| 15 | Live TV & PVR | `roadmap/phase-15.md` | not started |
| 16 | App Ecosystem | `roadmap/phase-16.md` | not started |
| 17 | UX, Accessibility & i18n | `roadmap/phase-17.md` | not started |
| 18 | Quality & Release | `roadmap/phase-18.md` | not started |

---

## Phase 7: Honesty & Wiring

Kill every gap where the UI or installer promises something the backend never
delivers. Cheapest real wins in the repo — mostly wiring code that already
exists. Full task list in `roadmap/phase-7.md`.

- Installer/API options that are declared but never read: night mode,
  passthrough, CEC wake, web remote, camera hub, `MPV_VO`, `MPV_HWDEC`,
  `MPV_SCALE`, `TV_SCALE`.
- Subtitle endpoint that returns URLs MPV never loads.
- Resume/continue-watching that never advances because nothing checkpoints
  playback position.
- App Store with a hardcoded `installed: True` and no lifecycle endpoints.
- `history`, `remote`, `settings` backends reduced to `/health` stubs.
- Remote's camera button pointing at an unregistered app (404).
- README advertising `/api/trending`, which does not exist.
- Updater running as root with no backup/rollback and no `.version` file.
- Unvalidated app manifests: a malformed one kills the whole server.
- `settings.json` POST that deletes every unknown key on save.
- No `.gitignore`; compiled `.pyc` files tracked in git.

## Phase 8: Security & Isolation

Turn an open LAN appliance into a locked-down one. Highest-severity work in
the roadmap — the API currently has no auth, CORS is `*`, and every service
binds `0.0.0.0`.

- API authentication + session handling, shared by app and updater.
- systemd hardening on every unit (`ProtectSystem=strict`, `PrivateTmp`,
  `NoNewPrivileges`, `MemoryMax`, `CPUQuota`, `ReadWritePaths=` for `var/`).
- Updater off root via a narrow polkit/privileged helper.
- Signed/verified updates before applying a payload.
- CORS restricted to loopback + real LAN origin.
- App sandboxing (per-app process, `systemd-run`/bubblewrap, resource caps).
- Enforce the `permissions` field that every manifest already declares.
- Secrets out of unit files into a 0600 credentials file / keyring.
- Optional-SSH and firewall policy; "kiosk-locked vs open" posture toggle.

## Phase 9: Player Core

Replace fire-and-forget `Popen` with a managed MPV session. This is the
keystone that unlocks resume, track selection, overlay controls, and
transcode fallback.

- Persistent MPV IPC session with property observation and a single instance.
- Periodic position checkpoint → history → resume prompt in the UI.
- Track selection: audio tracks, subtitle tracks, external `--sub-file`.
- Player overlay: scrubber, speed, PiP, stop/close.
- Watchdog + crash restart with last-position recovery.
- Transcode fallback ladder (`auto-safe` → `no` → libav) with visible notice.
- Format ladder per device capability, not a static string.
- Server-side queue in SQLite so it survives browser restart and syncs TV ↔
  phone remote.
- Offline download cache; per-category SponsorBlock toggles.
- Local cover-art extraction and thumbnail cache.

## Phase 10: Library & Metadata

`iterdir()` becomes a real library.

- Recursive scanner with size/duration/codec probe and an mtime index in
  SQLite.
- TMDB / OMDB / MusicBrainz actually implemented (HTTP + caching).
- Series/episode model: seasons, episodes, watched flags, next-air.
- NFO scraping and manual metadata override.
- Favourites, watchlists, playlists, smart collections.
- Music app (album/artist/genre, gapless, ReplayGain) and Photos app
  (slideshow, ambient).
- Multi-source aggregation: local + SMB + NFS + Jellyfin/Emby as a library.

## Phase 11: OS Identity, Rootfs & Storage

Make it an OS rather than a service on Ubuntu.

- Read-only root (squashfs/erofs) with an overlay upper; writable `/var`.
- A/B root partitions with slot flipping — prerequisite for real OTA.
- Dedicated `TVTV_MEDIA` partition with a systemd `.mount` unit; drop the
  hardcoded `/home/htpc/media`.
- Branded `tvtv-os` identity: `/etc/os-release`, hostname, `/etc/issue`,
  splash, kernel cmdline.
- Rootfs integrity verification at boot (`dm-verity` or checksum).
- Proper `/etc/fstab` discipline for zram, samba, ssh.
- Disk-space guard for `var/` and `~/.cache`, which grow unbounded today.
- Journald caps, logrotate, vacuum job.
- State snapshot/restore before OTA.
- Optional LUKS media volume; USB storage as a first-class source; flash
  write-endurance policy for NUC eMMC/SD.

## Phase 12: Boot, Session & Display

- Measured boot budget (`systemd-analyze`) with a CI gate.
- `labwc.service` + `tvtv-session.target` replacing
  `agetty → .bash_profile → labwc`, so a crashed compositor restarts.
- Watchdog: Chromium or dashboard death no longer means a dead box.
- EDID-driven mode selection wired into the install path.
- HDR/color mode, multi-output, frame-rate switching.
- Hardened kiosk profile under `/var/lib/tvtv`, no first-run wizard, no
  crash-restore UI.
- Idle/ambient mode and screen-off on long idle (screen blanking is only
  disabled today).
- Boot splash with progress so a 15s boot doesn't read as a hang.
- CEC one-touch-play input switching; CEC volume sync; user-editable CEC
  key map with long-press and repeat-rate.

## Phase 13: Audio Engine

- Night mode as a real PipeWire/WirePlumber filter chain (loudness +
  dialogue-band EQ) instead of a dead `TV_NIGHT_MODE` export.
- Passthrough wired to real profile switching incl. TrueHD/DTS-HD/AC3, gated
  on display-port audio capability probing.
- Output picker UI via `wpctl` (the doctor uses `pactl`, which PipeWire may
  not even provide).
- Reconcile the HDMI audio pin: `install.sh` deletes
  `90-hdmi-pin.conf` as obsolete while the design calls pinning a feature.
- Per-app volume offsets, notification ducking, master limiter.
- Bluetooth output pairing and switching; persisted per-output EQ;
  lip-sync delay compensation.

## Phase 14: Network, Remote & Casting

- Wi-Fi join from the TV UI (`nmcli` scan exists only in the installer app).
- VPN client (WireGuard) with UI and per-app routing.
- Wake-on-LAN and "wake the box to play this".
- Chromecast / DLNA / AirPlay receiver — the phone becomes a sender.
- On-screen keyboard and real text entry on the TV (today only
  `ydotool type:` from the phone).
- Local speech-to-text for voice commands (`/api/ai/voice` parses text but
  nothing captures audio).
- Firewall and service-exposure policy; mDNS advertisement for discovery.

## Phase 15: Live TV & PVR

- IPTV/M3U tuner + EPG grid with timeshift.
- Live TV app with guide-grid UI and channel logos.
- Recordings manager with disk budgeting.
- Hardware tuner support (HDHomeRun, USB DVB) via `dvbv5`/`tvheadend`.
- Scheduled recording daemon as a systemd timer.

## Phase 16: App Ecosystem

- Real lifecycle: install, remove, update, enable, disable, disk accounting.
- Remote app repository with signing; today everything is local and assumed
  installed.
- Plugin isolation with resource limits.
- App navigation contract: focus order, back-stack, where `Escape` goes.
- App health monitoring and restart from the GUI.
- Fold camera-setup into the app registry (currently a parallel service on
  8002 with duplicated frontend code, outside `start-all.sh`'s model).
- Logs/debug viewer app and one-button diagnostic bundle export.

## Phase 17: UX, Accessibility & i18n

- Accessibility pass: the main UI has **zero** `aria-*` attributes, no focus
  trap, no screen-reader mode, no high-contrast theme, no reduced motion.
  A D-pad UI needs real roles.
- i18n: `locale` is set in the autoinstall identity and never reaches the UI.
- Long-press and context menus (CEC remotes emit long-press).
- Predictable multi-level back-stack semantics.
- Notification center for updates, low storage, network loss.
- First-boot onboarding wizard in the UI for manually installed boxes.
- User profiles with per-profile playback limits and a kid mode.
- Theme store (`TV_THEME` ships exactly one theme).
- Home-rail live widgets: weather, system temp, now-playing, camera status.
- Parental controls / content filtering.

## Phase 18: Quality & Release

- A test suite. There is none today — every previous verification in this repo
  was ad-hoc.
- CI: `bash -n`, `py_compile`, pytest, ISO build on push. No `.github/` yet.
- Manifest schema validation in CI, not only in `plugins/`.
- One source of truth for systemd units — `install.sh` and
  `scripts/setup.sh` both write units independently and have drifted.
- Config schema validation for `tv.conf` and `settings.json`.
- Boot-time and memory regression budgets in CI.
- Structured logging with request IDs; replace the pervasive
  `except Exception: pass`.
- Version manifest surfaced at `/api/health` for updater and store.
- Generated support matrix from `install.sh --check` + `tvtv-doctor.sh`.

---

## Milestones

- **M0** repo reorganized, roadmap complete — done
- **M1** bootable ISO boots to the dashboard shell — done
- **M2** media search + playback end to end — done (but no resume/position)
- **M3** Phase 7+8 complete: nothing on the LAN is unauthenticated, and no
  declared feature is dead — **current**
- **M4** Phase 9+10 complete: real player session and real library
- **M5** Phase 11+12 complete: read-only rootfs, A/B slots, measured boot
- **M6** first-party apps installable and sandboxed (Phase 16)
- **M7** public beta release (Phase 18)
