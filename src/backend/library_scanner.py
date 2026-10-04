"""P10-1: Recursive media file scanner with SQLite indexing, duration/codec probing, and NFO support."""
from __future__ import annotations
import sqlite3
import json
import subprocess
from pathlib import Path
from typing import Any, Optional
from nfo_parser import parse_nfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = PROJECT_ROOT / 'var' / 'library'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'library.db'

EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov'}

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                type TEXT NOT NULL,
                duration REAL,
                codec TEXT,
                metadata TEXT
            )
        """)
        conn.commit()

init_db()

def _probe(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(path)],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        duration = float(data.get('format', {}).get('duration', 0))
        # Take first video stream codec
        video_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        codec = video_streams[0].get('codec_name') if video_streams else None
        return {'duration': duration, 'codec': codec}
    except Exception:
        return {'duration': 0, 'codec': None}

def scan(root: Path) -> None:
    conn = _get_connection()
    for path in root.rglob('*'):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            stats = path.stat()
            probe_data = _probe(path)
            
            # Check for NFO
            nfo_path = path.with_suffix('.nfo')
            metadata: Optional[str] = None
            if nfo_path.exists():
                metadata = json.dumps(parse_nfo(nfo_path))

            try:
                conn.execute("""
                    INSERT INTO media_files (path, mtime, size, type, duration, codec, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        mtime=excluded.mtime,
                        size=excluded.size,
                        duration=excluded.duration,
                        codec=excluded.codec,
                        metadata=excluded.metadata
                """, (str(path), stats.st_mtime, stats.st_size, path.suffix.lower(), 
                      probe_data['duration'], probe_data['codec'], metadata))
            except sqlite3.Error:
                pass
    conn.commit()
    conn.close()
