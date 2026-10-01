"""System Update app backend.

P7-14: Proxies status, update checks, and rollback commands to the standalone
tvtv-updater service on port 8001.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

UPDATER_URL = 'http://127.0.0.1:8001'


def _updater_get(path: str, timeout: float = 6.0) -> dict:
    try:
        with urllib.request.urlopen(UPDATER_URL + path, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {
            'installed_version': 'unknown',
            'latest_version': 'unknown',
            'update_available': False,
            'rollback_available': False,
            'previous_version': None,
            'release_url': '',
            'release_notes': f'Updater service not reachable on port 8001 ({e}).',
        }


def _updater_post(path: str, data: dict, timeout: float = 300.0) -> dict:
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        UPDATER_URL + path,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err_text = e.read().decode()
        try:
            return json.loads(err_text)
        except Exception:
            raise HTTPException(e.code, detail=f"Updater error: {err_text or e.reason}")
    except Exception as e:
        raise HTTPException(503, detail=f"Updater service unavailable: {e}")


@router.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@router.get('/status')
def status():
    return _updater_get('/api/status')


@router.get('/check')
def check_update():
    s = _updater_get('/api/status')
    if s.get('update_available'):
        return {'status': 'ok', 'message': f"Update available: {s.get('latest_version')}"}
    return {'status': 'ok', 'message': 'No updates available.'}


class RollbackBody(BaseModel):
    reboot: bool = False


@router.post('/rollback')
def rollback(body: Optional[RollbackBody] = None):
    data = (body.model_dump() if body else {'reboot': False})
    return _updater_post('/api/rollback', data)
