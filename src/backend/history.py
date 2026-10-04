from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import verify_client_access

HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / 'var' / 'history' / 'watch-history.json'
HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
if not HISTORY_PATH.exists():
    HISTORY_PATH.write_text('[]')

# Auth: all history routes require client verification (P8-1). Verify passes
# silently for loopback, so the kiosk UI on-device is unaffected.
router = APIRouter(dependencies=[Depends(verify_client_access)])

MAX_HISTORY = 200

class HistoryItem(BaseModel):
    url: str
    title: str
    position: float = 0
    duration: float = 0
    channel: str | None = None
    thumbnail: str | None = None
    watched_at: str | None = None

def _load() -> list:
    try:
        data = json.loads(HISTORY_PATH.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save(items: list) -> None:
    try:
        HISTORY_PATH.write_text(json.dumps(items))
    except Exception as e:
        # Losing history must never take the API down mid-playback.
        from logging import getLogger
        getLogger('tvtv.history').warning('could not write history: %s', e)

def _append_history(item: HistoryItem) -> None:
    """Insert or update an entry keyed by URL, newest first.

    Keyed merge rather than blind insert: position checkpoints arrive every
    few seconds for the same video, and inserting blindly would fill the
    list with dozens of near-identical entries and push out real history.
    """
    from datetime import datetime, timezone
    items = _load()
    entry = item.model_dump()
    entry['watched_at'] = entry.get('watched_at') or datetime.now(timezone.utc).isoformat()
    items = [existing for existing in items if existing.get('url') != item.url]
    items.insert(0, entry)
    _save(items[:MAX_HISTORY])

def _remove_history(url: str) -> None:
    _save([existing for existing in _load() if existing.get('url') != url])

@router.get('/history')
def get_history():
    return {'items': _load()}

@router.post('/history')
def add_history(item: HistoryItem):
    _append_history(item)
    return {'status': 'ok'}

@router.delete('/history')
def clear_history():
    _save([])
    return {'status': 'ok'}

@router.delete('/history/item')
def delete_history_item(url: str):
    _remove_history(url)
    return {'status': 'ok'}
