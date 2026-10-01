"""History app backend.

P7-9: this was a 7-line `/health` stub. The frontend calls `GET /history`
(core router) and `POST /api/play`, so those already exist — this router
owns the history-specific views plus a resume lookup, so "Resume" means
something. Shared history storage lives in src/backend/history.py.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Below this, a stored position is just the start of a video.
MIN_RESUME_S = 10.0

# A video this close to the end counts as finished; don't offer to resume.
COMPLETED_RATIO = 0.97


class ResumeRequest(BaseModel):
    url: str
    title: str = ''
    duration: float = 0.0
    channel: Optional[str] = None
    thumbnail: Optional[str] = None


def _is_resumable(item: dict) -> bool:
    position = float(item.get('position') or 0)
    duration = float(item.get('duration') or 0)
    if position < MIN_RESUME_S:
        return False
    return not (duration > 0 and position >= duration * COMPLETED_RATIO)


@router.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@router.get('/in-progress')
def in_progress():
    """History entries with a resumable position, newest first."""
    from history import get_history
    items = [i for i in get_history().get('items', []) if _is_resumable(i)]
    return {'items': items}


@router.get('/recent')
def recent(limit: int = 30):
    from history import get_history
    items = get_history().get('items', [])
    return {'items': items[:max(1, min(limit, 200))]}


@router.post('/play')
def play(req: ResumeRequest) -> dict:
    """Resolve a resume request to a concrete seek offset.

    Returns the payload for `POST /api/play` rather than launching MPV
    itself, so the launch path stays in one place.
    """
    from history import get_history

    if not req.url.strip():
        raise HTTPException(400, "No URL provided")

    entry = next(
        (i for i in get_history().get('items', []) if i.get('url') == req.url),
        None,
    ) or {}

    seek = float(entry.get('position') or 0.0)
    if not _is_resumable(entry):
        seek = 0.0

    return {
        'url': req.url,
        'title': req.title or entry.get('title') or req.url,
        'seek': seek,
        'duration': req.duration or float(entry.get('duration') or 0.0),
        'channel': req.channel or entry.get('channel'),
        'thumbnail': req.thumbnail or entry.get('thumbnail'),
        'resumable': seek > 0,
    }
