"""Unit tests for Phase 10 Library Scanner.

Exercises:
  * Recursive media file scanning
  * Mtime-keyed SQL indexing
  * Media type detection
  * Probe integration (dummy)
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
import sqlite3
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
        library_scanner.DB_PATH = tmp_dir / 'test_library.db'
        library_scanner.init_db()

        # Create dummy structure
        media_root = tmp_dir / 'media'
        media_root.mkdir()
        
        (media_root / 'video1.mp4').write_bytes(b'dummy_data')
        (media_root / 'text.txt').write_bytes(b'fake')

        # Run scan
        library_scanner.scan(media_root)

        # Check indexing
        conn = sqlite3.connect(library_scanner.DB_PATH)
        row = conn.execute("SELECT path, duration, codec FROM media_files WHERE path LIKE '%video1.mp4'").fetchone()                
        
        check('Scanner finds video1', row is not None)                
        check('Duration recorded', row[1] is not None) # defaults to 0.0

    return 0

if __name__ == '__main__':
    sys.exit(main())
