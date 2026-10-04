from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import verify_client_access

router = APIRouter(dependencies=[Depends(verify_client_access)])

from credentials import get_secret

class MediaMetadata(BaseModel):
    title: str
    year: Optional[int] = None
    overview: Optional[str] = None
    poster: Optional[str] = None

class MetadataProvider:
    def lookup(self, title: str, year: Optional[int] = None) -> Optional[MediaMetadata]:
        raise NotImplementedError

import httpx

import logging
log = logging.getLogger('tvtv.metadata')

class TMDBProvider(MetadataProvider):
    def __init__(self) -> None:
        self.api_key = get_secret('TMDB_API_KEY')
        self.enabled = bool(self.api_key)
        self.base_url = "https://api.themoviedb.org/3"
    
    def lookup(self, title: str, year: Optional[int] = None) -> Optional[MediaMetadata]:
        if not self.enabled:
            return None
        
        params: dict[str, str | int] = {"api_key": self.api_key, "query": title}
        if year:
            params["year"] = year
        
        try:
            with httpx.Client(timeout=5) as client:
                res = client.get(f"{self.base_url}/search/movie", params=params)
                res.raise_for_status()
                data = res.json()
                results = data.get('results', [])
                if not results:
                    return None
                
                # Take first result
                movie = results[0]
                release_date = movie.get('release_date')
                return MediaMetadata(
                    title=movie['title'],
                    year=int(release_date[:4]) if release_date and len(release_date) >= 4 else None,
                    overview=movie.get('overview'),
                    poster=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get('poster_path') else None
                )
        except Exception as e:
            log.error("TMDB lookup failed: %s", e)
            return None

class OMDBProvider(MetadataProvider):
    def __init__(self) -> None:
        self.api_key = get_secret('OMDB_API_KEY')
        self.enabled = bool(self.api_key)
        self.base_url = "http://www.omdbapi.com/"
        
    def lookup(self, title: str, year: Optional[int] = None) -> Optional[MediaMetadata]:
        if not self.enabled:
            return None
        
        params: dict[str, str | int] = {"apikey": self.api_key, "t": title}
        if year:
            params["y"] = year
        
        try:
            with httpx.Client(timeout=5) as client:
                res = client.get(self.base_url, params=params)
                res.raise_for_status()
                data = res.json()
                if data.get('Response') == 'False':
                    return None
                
                return MediaMetadata(
                    title=data['Title'],
                    year=int(data['Year']) if data.get('Year') and data['Year'].isdigit() else None,
                    overview=data.get('Plot'),
                    poster=data.get('Poster') if data.get('Poster') != 'N/A' else None
                )
        except Exception as e:
            log.error("OMDB lookup failed: %s", e)
            return None

class MusicBrainzProvider(MetadataProvider):
    def __init__(self) -> None:
        self.user_agent = get_secret('MUSICBRAINZ_USER_AGENT', 'tvtv-app/0.1.0')
        self.enabled = True # Public API, no key needed
        self.base_url = "https://musicbrainz.org/ws/2"
        
    def lookup(self, title: str, year: Optional[int] = None) -> Optional[MediaMetadata]:
        # MusicBrainz is for music, but the interface requires lookup(title)
        return None

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
    tmdb = TMDBProvider()
    omdb = OMDBProvider()
    musicbrainz = MusicBrainzProvider()
    return {
        'providers': [
            {'id': 'tmdb', 'name': 'TMDB', 'enabled': tmdb.enabled},
            {'id': 'omdb', 'name': 'OMDB', 'enabled': omdb.enabled},
            {'id': 'musicbrainz', 'name': 'MusicBrainz', 'enabled': musicbrainz.enabled},
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
