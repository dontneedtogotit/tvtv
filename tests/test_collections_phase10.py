"""Unit tests for Phase 10 Smart Collections."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
import sqlite3
import json

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import queue_db
import library_scanner
import user_db
import library_collections
import importlib

def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        sys.exit(1)

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        library_scanner.DB_PATH = tmp_dir / 'test_lib_col.db'
        user_db.DB_PATH = tmp_dir / 'test_user_col.db'
        # Force re-import of connection paths
        importlib.reload(library_collections)
        
        library_scanner.init_db()
        user_db.init_db()

        # Add media
        media_root = tmp_dir / 'media'
        media_root.mkdir()
        (media_root / 'v1.mp4').write_bytes(b'dummy')
        (media_root / 'v2.mp4').write_bytes(b'dummy')
        library_scanner.scan(media_root)

        # Mark watched
        conn = sqlite3.connect(user_db.DB_PATH)
        conn.execute("INSERT INTO watched (media_path) VALUES (?)", (str(media_root / 'v1.mp4'),))
        conn.commit()

        # Check unwatched
        unwatched = library_collections.get_unwatched()
        check('Unwatched has 1 item', len(unwatched) == 1)

    return 0

if __name__ == '__main__':
    sys.exit(main())
