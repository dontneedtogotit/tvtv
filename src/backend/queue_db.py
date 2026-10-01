"""Server-side persistent playback queue (SQLite backed).

P9-8: Replaces localStorage-only frontend queue with a shared server-side
queue stored in SQLite (`var/queue/queue.db`). Syncs across the TV UI and
mobile remotes, and survives browser restarts.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = PROJECT_ROOT / 'var' / 'queue'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'queue.db'


class QueueItem(BaseModel):
    id: Optional[int] = None
    url: str
    title: str = ""
    channel: Optional[str] = None
    duration: Optional[float] = None
    duration_str: Optional[str] = None
    thumbnail: Optional[str] = None
    added_at: Optional[float] = Field(default_factory=time.time)


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playback_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT,
                channel TEXT,
                duration REAL,
                duration_str TEXT,
                thumbnail TEXT,
                added_at REAL
            )
        """)
        conn.commit()


init_db()


def list_queue() -> list[dict[str, Any]]:
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM playback_queue ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_to_queue(item: QueueItem) -> dict[str, Any]:
    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO playback_queue (url, title, channel, duration, duration_str, thumbnail, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.url,
                item.title or item.url,
                item.channel or "",
                item.duration,
                item.duration_str or "",
                item.thumbnail or "",
                item.added_at or time.time(),
            )
        )
        conn.commit()
        item_id = cursor.lastrowid
        return {**item.model_dump(), "id": item_id}


def pop_next_queue_item() -> Optional[dict[str, Any]]:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM playback_queue ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        conn.execute("DELETE FROM playback_queue WHERE id = ?", (item["id"],))
        conn.commit()
        return item


def remove_queue_item(item_id: int) -> bool:
    with _get_connection() as conn:
        cursor = conn.execute("DELETE FROM playback_queue WHERE id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0


def clear_queue() -> None:
    with _get_connection() as conn:
        conn.execute("DELETE FROM playback_queue")
        conn.commit()
