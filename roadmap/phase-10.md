# Phase 10: Library & Metadata

Goal: `iterdir()` becomes a real media library with metadata.

Status: not started. Depends on Phase 9 for probe/reuse of the ffmpeg layer.

Tasks

- [ ] P10-1 Recursive scanner with size/duration/codec probing and an
      mtime-keyed index in SQLite. Media-type detection by extension +
      probe. Current behaviour: one level, 200 entries, no indexing.
- [ ] P10-2 TMDB / OMDB / MusicBrainz actually implemented: HTTP calls with
      caching, API keys from the credentials file, graceful degradation when
      unset. Today `/metadata/providers` reports `enabled: False` for all
      three and never makes a request.
- [ ] P10-3 Series/episode model: seasons, episodes, watched flags, next-air
      dates. There is no show concept anywhere today.
- [ ] P10-4 NFO / scraper-based local naming plus manual metadata override
      from the UI.
- [ ] P10-5 Favourites, watchlists, playlists as first-class persisted data.
- [ ] P10-6 Smart collections: unwatched, recently added, in-progress,
      by-decade/by-genre — the queries that make a library usable.
- [ ] P10-7 Music app (album/artist/genre browsing, gapless, ReplayGain) and
      Photos app (slideshow, Ken Burns, ambient mode).
- [ ] P10-8 Multi-source aggregation: local + SMB + NFS + Jellyfin/Emby as a
      library source.
- [ ] P10-9 Library UI on the existing rail: poster grids, filters, sorting,
      detail view with cast/overview.
- [ ] P10-10 Folder watcher (`inotifywait`) so the index updates without a
      manual rescan.
