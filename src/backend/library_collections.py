"""P10-6: Smart collection queries."""
from __future__ import annotations
import sqlite3
from library_scanner import DB_PATH as LIBRARY_DB_PATH
from user_db import DB_PATH as USER_DB_PATH

def _get_library_conn():
    conn = sqlite3.connect(str(LIBRARY_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _get_user_conn():
    conn = sqlite3.connect(str(USER_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_recently_added(limit: int = 10) -> list[dict]:
    with _get_library_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM media_files ORDER BY mtime DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_unwatched() -> list[dict]:
    with _get_library_conn() as lib_conn, _get_user_conn() as user_conn:
        all_media = lib_conn.execute("SELECT * FROM media_files").fetchall()
        watched = user_conn.execute("SELECT media_path FROM watched").fetchall()
        watched_paths = {r['media_path'] for r in watched}
        
        return [dict(r) for r in all_media if r['path'] not in watched_paths]
