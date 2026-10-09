"""System Update app backend.

P7-14: Proxies status, update checks, updates, and rollback commands to the standalone
tvtv-updater service on port 8001, falling back to direct in-process updater logic.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

log = logging.getLogger('tvtv.app.system-update')
router = APIRouter()

UPDATER_URL = 'http://127.0.0.1:8001'
UPDATER_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'updater'
if str(UPDATER_DIR) not in sys.path:
    sys.path.insert(0, str(UPDATER_DIR))

import importlib.util
UPDATER_SCRIPT = UPDATER_DIR / 'server.py'
direct_updater = None
if UPDATER_SCRIPT.is_file():
    try:
        spec = importlib.util.spec_from_file_location('tvtv_updater_server', str(UPDATER_SCRIPT))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules['tvtv_updater_server'] = mod
            spec.loader.exec_module(mod)
            direct_updater = mod
    except Exception as e:
        log.warning('Could not import direct updater: %s', e)


def _updater_get(path: str, timeout: float = 6.0) -> dict:
    try:
        with urllib.request.urlopen(UPDATER_URL + path, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        # Fallback to in-process updater if standalone service on 8001 isn't running
        if direct_updater:
            try:
                if path in ('/api/status', '/status'):
                    st = direct_updater.status()
                    return st.model_dump() if hasattr(st, 'model_dump') else st.dict()
                elif path in ('/api/check', '/check'):
                    st = direct_updater.check()
                    return st.model_dump() if hasattr(st, 'model_dump') else st.dict()
                elif path in ('/api/logs', '/logs'):
                    return direct_updater.logs()
            except Exception as direct_err:
                log.warning('In-process updater get %s failed: %s', path, direct_err)
        return {
            'installed_version': 'unknown',
            'latest_version': 'unknown',
            'update_available': False,
            'rollback_available': False,
            'previous_version': None,
            'release_url': '',
            'release_notes': f'Updater check failed ({e}).',
        }


def _updater_post(path: str, data: dict, timeout: float = 300.0, request: Optional[Request] = None) -> dict:
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
    except Exception as e:
        # Fallback to direct in-process updater
        if direct_updater:
            try:
                if path in ('/api/update', '/update'):
                    req_obj = direct_updater.UpdateRequest(**data)
                    res = direct_updater.update(req_obj, request=request)
                    return res.model_dump() if hasattr(res, 'model_dump') else res.dict()
                elif path in ('/api/rollback', '/rollback'):
                    req_obj = direct_updater.RollbackRequest(**data)
                    res = direct_updater.rollback(req_obj, request=request)
                    return res.model_dump() if hasattr(res, 'model_dump') else res.dict()
                elif path in ('/api/reboot', '/reboot'):
                    return direct_updater.reboot(request=request)
            except Exception as direct_err:
                log.warning('In-process updater post %s failed: %s', path, direct_err)
                raise HTTPException(500, detail=str(direct_err))
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
        return {'status': 'ok', 'message': f"Update available: {s.get('latest_version')}", 'update_available': True, 'latest_version': s.get('latest_version')}
    return {'status': 'ok', 'message': 'No updates available.', 'update_available': False}


class UpdateBody(BaseModel):
    reboot: bool = False


@router.post('/update')
def apply_update(body: Optional[UpdateBody] = None, request: Request = None):
    data = (body.model_dump() if body else {'reboot': False})
    return _updater_post('/api/update', data, request=request)


class RollbackBody(BaseModel):
    reboot: bool = False


@router.post('/rollback')
def rollback(body: Optional[RollbackBody] = None, request: Request = None):
    data = (body.model_dump() if body else {'reboot': False})
    return _updater_post('/api/rollback', data, request=request)


@router.get('/logs')
def get_logs(lines: int = 50):
    return _updater_get(f'/api/logs?lines={lines}')


@router.post('/reboot')
def reboot_system(request: Request = None):
    return _updater_post('/api/reboot', {}, request=request)
