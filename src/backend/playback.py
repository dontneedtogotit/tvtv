from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

VAR_DIR = Path(__file__).resolve().parent.parent.parent / 'var' / 'history'
STATE_PATH = VAR_DIR / 'playback-state.json'
NOW_PLAYING_PATH = VAR_DIR / 'now-playing.json'
VAR_DIR.mkdir(parents=True, exist_ok=True)
if not STATE_PATH.exists():
    STATE_PATH.write_text('{}')
if not NOW_PLAYING_PATH.exists():
    NOW_PLAYING_PATH.write_text('{}')


class PlaybackState(BaseModel):
    url: str
    title: Optional[str] = None
    channel: Optional[str] = None
    thumbnail: Optional[str] = None
    position: float = 0
    duration: float = 0
    active: bool = False
    status: str = 'idle'  # idle|playing|paused|stopped
    updated_at: Optional[str] = None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data) -> None:
    try:
        path.write_text(json.dumps(data))
    except Exception:
        pass


def _read_state() -> dict:
    return _read_json(STATE_PATH)


def set_now_playing_state(state: PlaybackState) -> None:
    """Programmatic helper used by the play endpoint (no HTTP involved)."""
    _write_json(NOW_PLAYING_PATH, state.model_dump())


@router.get('/now-playing')
def now_playing():
    return _read_json(NOW_PLAYING_PATH)


@router.post('/now-playing')
def set_now_playing(state: PlaybackState):
    state.updated_at = state.updated_at or None
    _write_json(NOW_PLAYING_PATH, state.model_dump())
    return {'status': 'ok'}


@router.post('/playback/state')
def set_state(state: PlaybackState):
    data = _read_state()
    data[state.url] = state.model_dump()
    _write_json(STATE_PATH, data)
    return {'status': 'ok'}


@router.get('/playback/state')
def get_state(url: str):
    data = _read_state()
    return data.get(url, {'url': url, 'position': 0, 'duration': 0, 'active': False})


@router.delete('/playback/state')
def clear_state(url: str):
    data = _read_state()
    data.pop(url, None)
    _write_json(STATE_PATH, data)
    return {'status': 'ok'}