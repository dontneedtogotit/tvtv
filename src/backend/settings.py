from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / 'config'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / 'settings.json'

router = APIRouter()

class Settings(BaseModel):
    sponsorblock: bool = True
    default_quality: str = '1080p'
    tv_mode: str = '1080p@60'

DEFAULTS = Settings()

def _read_settings() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return DEFAULTS.model_dump()

def _write_settings(data: dict[str, Any]) -> None:
    """Write settings without dropping keys this module doesn't model.

    Later phases add settings keys owned by other modules. Serialising only
    the known fields would erase them on every save, so merge the known
    fields over whatever is already on disk.
    """
    merged = _read_settings()
    merged.update(data)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2) + "\n")

@router.get('/settings')
def get_settings() -> dict:
    return _read_settings()

@router.post('/settings')
def save_settings(settings: Settings) -> dict:
    _write_settings(settings.model_dump())
    return {'status': 'ok'}
