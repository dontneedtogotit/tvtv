# Phase 2: Main Dashboard GUI — superseded, partly shipped

The shell shipped in `src/frontend/index.html` (rail, six sections, spatial
focus nav, now-playing bar, search, AI page). The tasks below are the parts
that did not, each pointing at the phase that now owns it.

Tasks
- [x] top bar with status, time, network
- [x] keyboard and CEC spatial focus navigation
- [x] sections: home, search, library, apps, settings
- [x] now playing overlay
- [~] continue watching with resume — UI exists, but nothing checkpoints
  playback position so it never advances past the first seek.
  → Phase 9, task P9-2
- [~] remote web app integration — `src/frontend/remote.html` ships, but its
  camera button points at an unregistered app (404).
  → Phase 7, task P7-11
- [ ] offline shell with cached metadata — no service worker, no cache layer.
  → Phase 9, task P9-9
- [ ] player overlay controls (scrubber, tracks, speed, PiP)
  → Phase 9, task P9-4
- [ ] multi-level back-stack semantics
  → Phase 17
