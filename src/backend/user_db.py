"""P10-5: Persistent User Data (Favourites, Watchlists, Playlists)."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = PROJECT_ROOT / 'var' / 'user'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'user.db'

def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS favourites (
                media_path TEXT PRIMARY KEY
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                media_path TEXT NOT NULL,
                FOREIGN KEY(playlist_id) REFERENCES playlists(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watched (
                media_path TEXT PRIMARY KEY,
                position REAL DEFAULT 0,
                watched_at REAL
            )
        """)
        conn.commit()

init_db()

def favourite(media_path: str) -> None:
    with _get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO favourites (media_path) VALUES (?)", (media_path,))
        conn.commit()

def unfavourite(media_path: str) -> None:
    with _get_connection() as conn:
        conn.execute("DELETE FROM favourites WHERE media_path = ?", (media_path,))
        conn.commit()

def list_favourites() -> list[str]:
    with _get_connection() as conn:
        rows = conn.execute("SELECT media_path FROM favourites").fetchall()
        return [r['media_path'] for r in rows]
