from __future__ import annotations

import json
import shutil
import subprocess
from fastapi import APIRouter, HTTPException

router = APIRouter()


def _yt_dlp() -> str:
    return shutil.which("yt-dlp") or "yt-dlp"


@router.get('/subtitles')
def get_subtitles(url: str, lang: str = 'en'):
    """List available subtitle tracks and return a downloadable URL for the
    requested language (falls back to the first available)."""
    if not url.strip():
        raise HTTPException(400, "No URL provided")
    cmd = [_yt_dlp(), '--no-warnings', '--skip-download', '--dump-json', url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "yt-dlp timed out")
    if out.returncode != 0:
        raise HTTPException(502, "yt-dlp failed to fetch subtitle metadata")

    info = {}
    for line in out.stdout.splitlines():
        try:
            info = json.loads(line)
        except json.JSONDecodeError:
            continue

    subtitles = info.get('subtitles') or info.get('automatic_captions') or {}
    languages = sorted(subtitles.keys())

    def _best_url(entries):
        for ext in ('vtt', 'srt', 'ass'):
            for e in entries:
                if e.get('ext') == ext and e.get('url'):
                    return e['url']
        for e in entries:
            if e.get('url'):
                return e['url']
        return None

    subtitle_url = None
    if languages:
        subtitle_url = _best_url(subtitles.get(lang, [])) or \
            _best_url(subtitles.get(languages[0], []))

    return {
        'url': url,
        'languages': languages,
        'subtitle_url': subtitle_url,
    }