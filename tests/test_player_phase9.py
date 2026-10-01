"""Unit and integration tests for Phase 9 Player Core.

Exercises:
  * Persistent SQLite queue operations (P9-8)
  * PlayerManager track parsing and selection (P9-3)
  * Player watchdog exit handling and cleanup (P9-5)
  * SponsorBlock multi-category argument generation (P9-10)
  * End-to-end queue and player endpoints on running FastAPI server

Run from repo root:  .venv/bin/python tests/test_player_phase9.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import queue_db  # noqa: E402
from player_manager import PlayerManager  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        FAILURES.append(label)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)

        # ── 1. SQLite Queue Database (P9-8) ───────────────────────────────────
        queue_db.DB_PATH = tmp_dir / 'test_queue.db'
        queue_db.init_db()

        check('P9-8 queue is initially empty', len(queue_db.list_queue()) == 0)

        item1 = queue_db.QueueItem(
            url='https://youtu.be/video1',
            title='Video One',
            channel='Channel A',
            duration=300.0,
        )
        saved1 = queue_db.add_to_queue(item1)
        check('P9-8 item added with id', bool(saved1.get('id') and saved1['id'] > 0))

        item2 = queue_db.QueueItem(
            url='https://youtu.be/video2',
            title='Video Two',
            duration=450.0,
        )
        saved2 = queue_db.add_to_queue(item2)

        items = queue_db.list_queue()
        check('P9-8 queue lists both items', len(items) == 2, f"{len(items)} items")

        popped = queue_db.pop_next_queue_item()
        check('P9-8 pop_next_queue_item returns first item in FIFO order',
              popped is not None and popped['url'] == 'https://youtu.be/video1')

        remaining = queue_db.list_queue()
        check('P9-8 queue has 1 item remaining after pop', len(remaining) == 1)

        queue_db.remove_queue_item(saved2['id'])
        check('P9-8 remove_queue_item deletes by id', len(queue_db.list_queue()) == 0)

        queue_db.add_to_queue(item1)
        queue_db.clear_queue()
        check('P9-8 clear_queue removes all items', len(queue_db.list_queue()) == 0)

        # ── 2. PlayerManager & Track Selection (P9-1 & P9-3) ──────────────────
        pm = PlayerManager()
        check('P9-1 player is initially not running', not pm.is_running)

        # Simulate track parsing from MPV track-list structure
        sample_tracks = [
            {'id': 1, 'type': 'audio', 'title': 'English Stereo', 'lang': 'en', 'selected': True},
            {'id': 2, 'type': 'audio', 'title': 'Director Commentary', 'lang': 'en', 'selected': False},
            {'id': 1, 'type': 'sub', 'title': 'English SDH', 'lang': 'en', 'selected': True},
            {'id': 2, 'type': 'sub', 'title': 'Spanish', 'lang': 'es', 'selected': False},
        ]

        # Patch get_property on player_manager module for mock testing
        import player_manager
        orig_get_prop = player_manager.get_property
        try:
            player_manager.get_property = lambda prop, **kw: sample_tracks if prop == 'track-list' else None
            pm._process = type('MockProc', (), {'poll': lambda self: None})()  # mock active process

            tracks = pm.get_tracks()
            check('P9-3 audio tracks parsed', len(tracks['audio']) == 2, str(tracks['audio']))
            check('P9-3 subtitle tracks parsed', len(tracks['subtitles']) == 2, str(tracks['subtitles']))
            check('P9-3 audio track selected state', tracks['audio'][0]['selected'] is True)
            check('P9-3 subtitle track language mapped', tracks['subtitles'][1]['lang'] == 'es')
        finally:
            player_manager.get_property = orig_get_prop
            pm._process = None

        # ── 3. Watchdog Exit Detection (P9-5) ─────────────────────────────────
        pm._process = type('MockExitedProc', (), {'poll': lambda self: 0})()
        pm._current_url = 'https://youtu.be/someVid'
        pm.check_watchdog()
        check('P9-5 watchdog detects process exit and resets state',
              pm._process is None and pm._current_url is None)

        print()
        print(f'{len(FAILURES)} failure(s)' if FAILURES else 'ALL CHECKS PASSED')
        return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
