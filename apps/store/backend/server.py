"""App Store backend.

P7-8: the previous version reported every app as `installed: True` with no
lifecycle behind it. This reports the truth — what is actually present and
loadable — and exposes enable/disable state. Install/remove from a remote
repository is Phase 16 (task P16-1); nothing here pretends to do it.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
log = logging.getLogger('tvtv.app.store')

APPS_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = Path(__file__).resolve().parent.parent / 'frontend'

# Apps shipped with the OS. They are part of the install, so "removing"
# them is not supported — the store reports them as built-in rather than
# pretending an uninstall would work.
BUILT_IN = {
    'camera-setup', 'file-manager', 'history', 'installer',
    'media-library', 'remote', 'settings', 'store', 'system-update',
}

# Disabled state lives here so it survives restarts and is inspectable.
STATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'var' / 'store'
STATE_PATH = STATE_DIR / 'state.json'


class DisableRequest(BaseModel):
    app_id: str = Field(..., description="App id to enable or disable")
    disabled: bool = Field(True, description="True to disable, False to enable")


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _disabled() -> set[str]:
    return set(_read_state().get('disabled', []))


def _describe(mf: Path) -> dict | None:
    """Describe one installed app, or None if its manifest is unusable."""
    try:
        d = json.loads(mf.read_text())
    except Exception as e:
        log.warning('skipping unreadable manifest %s: %s', mf, e)
        return None
    if not isinstance(d, dict) or not d.get('id'):
        log.warning('skipping malformed manifest %s', mf)
        return None

    app_id = d['id']
    entry = d.get('entry') or {}
    backend = mf.parent / entry.get('backend', '')
    frontend = mf.parent / entry.get('frontend', '')

    # P16-1: disk accounting — sum the app directory size.
    disk_bytes = 0
    for f in mf.parent.rglob('*'):
        if f.is_file():
            try:
                disk_bytes += f.stat().st_size
            except OSError:
                pass

    return {
        'id': app_id,
        'name': d.get('name') or app_id,
        'description': d.get('description', ''),
        'version': d.get('version', ''),
        'author': d.get('author', ''),
        'icon': d.get('icon', ''),
        'categories': d.get('categories', []),
        'permissions': d.get('permissions', []),
        # Reported from what is on disk, not assumed.
        'installed': True,
        'built_in': app_id in BUILT_IN,
        'disabled': app_id in _disabled(),
        'has_frontend': frontend.is_file(),
        'has_backend': backend.is_file(),
        'frontend_url': f'/apps-frontend/{app_id}/' if frontend.is_file() else '',
        'disk_bytes': disk_bytes,
    }


@router.get('/list')
def list_apps():
    disabled = _disabled()
    apps: list[dict] = []
    unreadable: list[str] = []
    for mf in sorted(APPS_DIR.glob('*/manifest.json')):
        described = _describe(mf)
        if described is None:
            unreadable.append(mf.parent.name)
            continue
        described['disabled'] = described['id'] in disabled
        apps.append(described)
    return {
        'apps': apps,
        'unreadable_manifests': unreadable,
        # No remote repository exists yet (Phase 16). Say so rather than
        # returning an empty list that looks like "nothing available".
        'available_to_install': [],
        'repository': None,
        'note': 'All apps ship with the OS. Remote install arrives in Phase 16.',
    }


@router.post('/state')
def set_state(req: DisableRequest) -> dict:
    app_id = req.app_id
    if not (APPS_DIR / app_id / 'manifest.json').is_file():
        raise HTTPException(404, f'No such app: {app_id}')
    if req.disabled and app_id == 'store':
        # Disabling the store would remove the only way to re-enable it.
        raise HTTPException(400, 'The App Store cannot be disabled')

    state = _read_state()
    disabled = set(state.get('disabled', []))
    if req.disabled:
        disabled.add(app_id)
    else:
        disabled.discard(app_id)
    state['disabled'] = sorted(disabled)
    _write_state(state)
    return {'status': 'ok', 'app_id': app_id, 'disabled': req.disabled}


@router.get('/state')
def get_state() -> dict:
    return {'disabled': sorted(_disabled())}


@router.post('/refresh')
def refresh() -> dict:
    """Re-read manifests. The registry only loads at import time, so a newly
    dropped-in app directory needs a backend restart to mount; this reports
    what would be picked up rather than claiming it already is."""
    return {
        'status': 'ok',
        'message': 'Restart tvtv-yt.service to mount newly added apps',
        'manifests': sorted(p.parent.name for p in APPS_DIR.glob('*/manifest.json')),
    }


@router.get('/health')
def app_health() -> dict:
    """P16-5: App health monitoring — check each app's backend importability."""
    import importlib.util
    health: list[dict] = []
    for mf in sorted(APPS_DIR.glob('*/manifest.json')):
        try:
            d = json.loads(mf.read_text())
            app_id = d.get('id', mf.parent.name)
            entry = d.get('entry') or {}
            backend_path = mf.parent / entry.get('backend', '')
            if not backend_path.is_file():
                health.append({'id': app_id, 'healthy': True, 'note': 'no backend'})
                continue
            # Try importing to detect broken backends
            mod_name = f'_health_check_{app_id.replace("-", "_")}'
            spec = importlib.util.spec_from_file_location(mod_name, str(backend_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                import sys
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                sys.modules.pop(mod_name, None)
                health.append({'id': app_id, 'healthy': True})
            else:
                health.append({'id': app_id, 'healthy': False, 'error': 'cannot load'})
        except Exception as e:
            health.append({'id': mf.parent.name, 'healthy': False, 'error': repr(e)})
    return {'apps': health}
