"""Settings app backend.

P7-9: this was a 7-line `/health` stub. Persistence lives in
src/backend/settings.py (`GET/POST /settings`); this router adds the
settings *view* the app needs: what the current values are, what the system
can actually do, and whether the helpers it depends on exist — so the app
shows real state instead of three toggles that change nothing.
"""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()

BACKEND_DIR = Path(__file__).resolve().parents[3] / 'src' / 'backend'


def _backend_on_path() -> None:
    """App routers load by file path, so core modules aren't importable yet."""
    if str(BACKEND_DIR) not in sys_path():
        import sys
        sys.path.insert(0, str(BACKEND_DIR))


def sys_path() -> list[str]:
    import sys
    return sys.path


def _tv_profile() -> dict[str, Any]:
    _backend_on_path()
    try:
        from profile import profile_summary
        return profile_summary()
    except Exception:
        return {}


def _service_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url + '/api/health', timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


@router.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@router.get('/overview')
def overview() -> dict:
    """Everything Settings shows on one screen, read from real state."""
    _backend_on_path()
    from settings import _read_settings

    def which(cmd: str) -> str:
        return shutil.which(cmd) or ''

    return {
        'settings': _read_settings(),
        'tv_profile': _tv_profile(),
        'hardware': {
            'mpv': which('mpv'),
            'yt_dlp': which('yt-dlp'),
            'chromium': which('chromium') or which('chromium-browser'),
            'cec_client': which('cec-client'),
            'ydotool': which('ydotool'),
            'wpctl': which('wpctl'),
            'pactl': which('pactl'),
            'nmcli': which('nmcli'),
        },
        'services': {
            'updater': _service_reachable('http://127.0.0.1:8001'),
            'camera_scanner': _service_reachable('http://127.0.0.1:8002'),
        },
        'ports': {
            'app': os.environ.get('TVTV_PORT', '8000'),
            'updater': os.environ.get('TVTV_UPDATER_PORT', '8001'),
            'camera': '8002',
        },
    }


@router.get('/capabilities')
def capabilities() -> dict:
    """What this install can actually offer, computed rather than assumed."""
    def has(cmd: str) -> bool:
        return bool(shutil.which(cmd))

    tv = _tv_profile()
    return {
        'audio': {
            'passthrough': tv.get('audio_passthrough', False),
            'night_mode': tv.get('night_mode', False),
            'output_picker': has('wpctl'),
            # pactl may be absent on a PipeWire-only install; the doctor used it.
            'pactl_available': has('pactl'),
            'bluetooth': has('bluetoothctl'),
        },
        'display': {
            'mode': tv.get('tv_mode'),
            'scale': tv.get('tv_scale'),
            'theme': tv.get('theme'),
        },
        'remote': {
            'cec': tv.get('cec'),
            'virtual_input': has('ydotool'),
        },
        'network': {
            'wifi_config': has('nmcli'),
            'vpn': has('wg') or has('nmcli'),
        },
        'storage': {
            'samba_client': has('mount.cifs'),
            'nfs_client': has('mount.nfs'),
            'auto_mount': has('systemctl'),
        },
        'ai': {
            'configured': bool(os.environ.get('KILO_API_KEY')),
        },
    }
