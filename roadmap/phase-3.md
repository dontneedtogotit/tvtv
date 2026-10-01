# Phase 3: Media and Metadata — superseded, mostly stubbed

Filename-parse-only metadata and a directory listing shipped. The real work
moved to Phase 10, with playback-related items in Phase 9.

Tasks
- [~] media scanner for movies, TV, music, photos — `iterdir()`, single
  level, 200 items, no media-type detection.
  → Phase 10, task P10-1
- [~] TMDB/OMDB/MusicBrainz integration — `/metadata/providers` reports all
  three with `enabled: False` and makes zero HTTP calls.
  → Phase 10, task P10-2
- [~] watch history plus resume — history file exists; no position
  checkpointing, so resume is inert.
  → Phase 9, task P9-2
- [~] subtitle download and selection — the endpoint lists tracks and returns
  URLs, but MPV is never given `--sub-file`, so nothing loads.
  → Phase 9, task P9-3
- [ ] playlists and watchlists
  → Phase 10, task P10-5
- [ ] transcoding fallback
  → Phase 9, task P9-6
- [ ] series/episode model, seasons, watched flags
  → Phase 10, task P10-3
- [ ] music app and photos app
  → Phase 10, task P10-7
