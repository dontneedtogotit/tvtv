from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class MediaMetadata(BaseModel):
    title: str
    year: Optional[int] = None
    overview: Optional[str] = None
    poster: Optional[str] = None

def _parse_filename(name: str) -> dict:
    stem = Path(name).stem
    m = re.search(r'(.*?)[\s\.]*(19\d{2}|20\d{2})', stem)
    title = stem
    year = None
    if m:
        title = re.sub(r'[\s\.]+', ' ', m.group(1)).strip()
        try:
            year = int(m.group(2))
        except ValueError:
            year = None
    return {'title': title, 'year': year}

@router.get('/metadata/providers')
def metadata_providers():
    return {
        'providers': [
            {'id': 'tmdb', 'name': 'TMDB', 'enabled': False},
            {'id': 'omdb', 'name': 'OMDB', 'enabled': False},
            {'id': 'musicbrainz', 'name': 'MusicBrainz', 'enabled': False},
        ]
    }

@router.get('/metadata/lookup')
def metadata_lookup(path: str):
    target = Path(path)
    parsed = _parse_filename(target.name)
    return MediaMetadata(
        title=parsed.get('title') or target.name,
        year=parsed.get('year'),
        overview=None,
        poster=None,
    ).model_dump()
