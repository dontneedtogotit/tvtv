"""Remote app backend.

P7-9: this was a 7-line `/health` stub while the remote's frontend
(`/apps-frontend/remote/`) called `/api/control`, `/api/position`, and the
app switcher. The playback endpoints live on the core router, so this adds
what the remote specifically needs that doesn't exist yet: a discovery
endpoint so the remote can tell what the box supports, and a health
summary combining service reachability with the resolved TV profile.
"""

from __future__ import annotations

import urllib.request

from fastapi import APIRouter

router = APIRouter()

UPDATER_URL = 'http://127.0.0.1:8001'
CAMERA_URL = 'http://127.0.0.1:8002'


def _reachable(url: str, path: str = '/api/health', timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url + path, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


@router.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@router.get('/capabilities')
def capabilities() -> dict:
    """What this box can do, so the phone can hide controls it can't use."""
    from pathlib import Path
    import sys

    backend_dir = Path(__file__).resolve().parents[3] / 'src' / 'backend'
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    try:
        from profile import profile_summary
        tv = profile_summary()
    except Exception:
        tv = {}

    apps_dir = Path(__file__).resolve().parent.parent.parent
    app_ids = sorted(p.parent.name for p in apps_dir.glob('*/manifest.json'))

    return {
        'playback_controls': [
            'pause', 'stop', 'fullscreen', 'seek+10', 'seek-10',
            'seek+30', 'seek-30', 'speed+', 'speed-', 'speed1',
            'vol+', 'vol-', 'mute',
        ],
        'navigation_keys': ['up', 'down', 'left', 'right', 'enter', 'back', 'home'],
        'text_input': True,   # via type:<text> → ydotool
        'ai_assistant': True,
        'apps': app_ids,
        'tv_profile': tv,
        'services': {
            'updater': _reachable(UPDATER_URL),
            'camera_scanner': _reachable(CAMERA_URL),
        },
    }
