from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import verify_client_access

log = logging.getLogger('tvtv.settings')

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / 'config'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / 'settings.json'

# Auth: all settings routes require client verification (P8-1). Verify passes
# silently for loopback, so the kiosk UI on-device is unaffected.
router = APIRouter(dependencies=[Depends(verify_client_access)])

class Settings(BaseModel):
    sponsorblock: bool = True
    default_quality: str = '1080p'
    tv_mode: str = '1080p@60'
    firewall_posture: str = 'kiosk'

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

def _apply_firewall_posture(posture: str) -> None:
    """P8-10: apply the kiosk/open posture via the firewall script.

    The appliance grants the backend passwordless sudo; on dev machines
    without the script or without privileges this is a no-op (settings are
    still saved). The posture is validated against the allowed values first.
    """
    if posture not in ('kiosk', 'open'):
        log.warning('firewall_posture %r not in (kiosk, open) — ignored', posture)
        return
    script = Path(__file__).resolve().parent.parent.parent / 'scripts' / 'firewall-posture.sh'
    if not script.exists():
        log.info('firewall-posture.sh not present — posture %r saved only', posture)
        return
    try:
        subprocess.run(
            ['sudo', '-n', str(script), posture],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception as exc:
        log.warning('firewall posture apply failed: %r', exc)


@router.post('/settings')
def save_settings(settings: Settings) -> dict:
    data = settings.model_dump()
    previous = _read_settings().get('firewall_posture')
    _write_settings(data)
    # Only touch the firewall when the posture actually changed, so routine
    # settings saves don't re-run sudo ufw on the appliance.
    if data.get('firewall_posture') != previous:
        _apply_firewall_posture(data.get('firewall_posture', 'kiosk'))
    return {'status': 'ok'}
