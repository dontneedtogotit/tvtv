"""Unit tests for Phase 10 User Metadata."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import user_db

def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        sys.exit(1)

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        user_db.DB_PATH = tmp_dir / 'test_user.db'
        user_db.init_db()

        user_db.favourite('/media/movie1.mp4')
        favs = user_db.list_favourites()
        check('Favourite recorded', '/media/movie1.mp4' in favs)

        user_db.unfavourite('/media/movie1.mp4')
        favs = user_db.list_favourites()
        check('Unfavourite works', '/media/movie1.mp4' not in favs)

    return 0

if __name__ == '__main__':
    sys.exit(main())
