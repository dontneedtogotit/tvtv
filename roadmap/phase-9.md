# Phase 9: Player Core

Goal: replace the fire-and-forget `subprocess.Popen` in `/api/play` with a
managed MPV session. This is the keystone phase — P9-2 through P9-6 all
depend on P9-1, and resume/track selection/crash recovery are unlocked by it.

Status: in progress. Managed session manager, track inspection, SQLite queue,
and watchdog recovery implemented and verified.

Tasks

- [x] P9-1 Managed MPV session: `src/backend/player_manager.py` maintains process
      lifecycle, handles clean restarts, manages IPC socket, and sets now-playing states.
- [x] P9-2 Position checkpointing: background loop persists `time-pos` and duration
      to watch history; resume endpoint computes seek offsets with start/completion thresholds.
- [x] P9-3 Track selection: `player.get_tracks()` parses MPV audio & subtitle `track-list`;
      `/api/player/tracks` and `POST /api/player/track` allow switching aid/sid.
- [ ] P9-4 Player overlay in the shell: scrubber with seek, speed, PiP,
      stop/close, track pickers.
- [x] P9-5 Watchdog: `check_watchdog()` detects unexpected MPV termination, cleans up
      state, flushes final checkpoint, and updates now-playing status to "stopped".
- [ ] P9-6 Transcode fallback ladder: `hwdec=auto-safe` → `hwdec=no` →
      libav software decode, with a visible notice when quality degrades.
- [ ] P9-7 Format ladder from actual device capability (probe what the EDID
      / decoder supports) rather than the static
      `avc1`→`vp9`→`best` string; add AV1.
- [x] P9-8 Server-side queue in SQLite (`var/queue/queue.db` via `src/backend/queue_db.py`):
      FIFO queue with `/api/queue` endpoints, syncing TV UI and mobile remotes.
- [ ] P9-9 Offline/download cache for unreliable wifi; shell-level cache so
      the dashboard renders without network.
- [x] P9-10 SponsorBlock per-category toggles (`sponsor`, `intro`, `outro`, `selfpromo`)
      supported in `PlayRequest` and passed to MPV ytdl hook options.
- [ ] P9-11 Local cover-art extraction + thumbnail cache for library files
      (currently YouTube thumbnails only).
- [x] P9-12 Hardware-decode verification in `tvtv-doctor.sh` (VA-API DRM render node check,
      `render` group check, `vainfo` profile enumeration).

## Verification

- [x] P9-V1 `tests/test_player_phase9.py` — unit test suite for SQLite queue FIFO,
      track parsing, watchdog exit detection, and state reset (13 checks, passes).
- [x] P9-V2 `scripts/verify-phase7.py` — integration checks for `/api/queue` and
      `/api/player/tracks` on running server (53 checks, passes).
