# Phase 15: Live TV & PVR

Goal: tuner input, guide, and recording — the parts of a TV box that YouTube
playback doesn't cover.

Status: not started. Entirely new surface; nothing exists today beyond the
CEC adapter handling power keys.

Tasks

- [ ] P15-1 IPTV/M3U tuner source with channel parsing and EPG ingestion.
- [ ] P15-2 Live TV app: guide-grid UI, now/next, channel logos.
- [ ] P15-3 Timeshift buffer with a scrub bar.
- [ ] P15-4 Recordings manager with disk budgeting.
- [ ] P15-5 Hardware tuner support (HDHomeRun, USB DVB) via `dvbv5` or
      `tvheadend`.
- [ ] P15-6 Scheduled recording daemon as a systemd timer.
- [ ] P15-7 Recordings integrate into the library (Phase 10) and into
      Continue Watching.
- [ ] P15-8 Live TV respects the same audio passthrough / player overlay
      path as file playback.
