"""Unit tests for Phase 10 Library Scanner with NFO."""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
import sqlite3
import json
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import library_scanner

def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        sys.exit(1)

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        library_scanner.DB_PATH = tmp_dir / 'test_library_nfo.db'
        library_scanner.init_db()

        # Create dummy structure
        media_root = tmp_dir / 'media'
        media_root.mkdir()
        
        video_path = media_root / 'video1.mp4'
        video_path.write_bytes(b'dummy_data')
        
        nfo_path = media_root / 'video1.nfo'
        nfo_path.write_text('<movie><title>Test Movie</title><year>2023</year></movie>')

        # Run scan
        library_scanner.scan(media_root)

        # Check indexing
        conn = sqlite3.connect(library_scanner.DB_PATH)
        row = conn.execute("SELECT metadata FROM media_files WHERE path LIKE '%video1.mp4'").fetchone()                
        
        check('Scanner finds metadata', row is not None and row[0] is not None)
        
        metadata = json.loads(row[0])
        check('Metadata correct', metadata.get('title') == 'Test Movie')

    return 0

if __name__ == '__main__':
    sys.exit(main())
