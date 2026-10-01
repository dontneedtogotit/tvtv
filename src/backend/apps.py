from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger('tvtv.apps')

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PLUGINS_DIR = PROJECT_ROOT / 'plugins'
APPS_DIR = PROJECT_ROOT / 'apps'

REQUIRED_FIELDS = ('id', 'name', 'version', 'entry')
REQUIRED_ENTRY_FIELDS = ('frontend', 'backend')

KNOWN_PERMISSIONS = {
    'storage.read', 'storage.list', 'storage.write',
    'playback.control',
    'network.scan', 'network.configure',
    'metadata.read',
    'history.read', 'history.write',
    'settings.read', 'settings.write',
    'system.install', 'system.update',
    'plugins.manage',
}


class AppManifestError(Exception):
    pass


def _validate_manifest(data: Any, source: Path) -> None:
    """Check the invariants the loader actually depends on.

    A JSON Schema lives at plugins/manifest.schema.json, but validating
    against it needs a jsonschema dependency. These checks cover the fields
    the loader dereferences and catch the failure modes that used to take
    the whole server down: a missing required field and a non-dict `entry`.
    """
    if not isinstance(data, dict):
        raise AppManifestError(f'{source}: manifest is not an object')

    for field in REQUIRED_FIELDS:
        if field not in data:
            raise AppManifestError(f'{source}: missing required field "{field}"')

    entry = data['entry']
    if not isinstance(entry, dict):
        raise AppManifestError(f'{source}: "entry" must be an object')
    for field in REQUIRED_ENTRY_FIELDS:
        if not entry.get(field):
            raise AppManifestError(f'{source}: missing entry.{field}')

    app_id = data['id']
    if not isinstance(app_id, str) or not app_id:
        raise AppManifestError(f'{source}: id must be a non-empty string')

    perms = data.get('permissions', [])
    if not isinstance(perms, list):
        raise AppManifestError(f'{source}: permissions must be an array')
    for p in perms:
        if not isinstance(p, str) or not p:
            raise AppManifestError(f'{source}: permission entries must be non-empty strings')

    # The id must match the directory name: routers, frontends and the store
    # all resolve paths from the directory, so a mismatch silently points at
    # the wrong app.
    dir_name = source.parent.name
    if app_id != dir_name:
        raise AppManifestError(
            f'{source}: id "{app_id}" does not match directory "{dir_name}"'
        )


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(manifest_path.read_text())
    except Exception as e:
        raise AppManifestError(f'Bad manifest {manifest_path}: {e}')
    _validate_manifest(data, manifest_path)
    return data


class AppRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, Any]] = {}
        self._apps: dict[str, dict[str, Any]] = {}
        self.load_errors: list[str] = []

    def _load_dir(self, base: Path, target: dict[str, dict[str, Any]], kind: str) -> None:
        if not base.exists():
            return
        for manifest_path in sorted(base.glob('*/manifest.json')):
            try:
                data = _load_manifest(manifest_path)
            except AppManifestError as e:
                # One bad manifest must not take down the whole OS UI.
                msg = f'{kind} manifest rejected: {e}'
                self.load_errors.append(msg)
                log.error('%s', msg)
                continue
            target[data['id']] = data

    def load_plugins(self) -> None:
        self._load_dir(PLUGINS_DIR, self._plugins, 'plugin')

    def load_apps(self) -> None:
        self._load_dir(APPS_DIR, self._apps, 'app')

    @property
    def plugins(self) -> dict[str, dict[str, Any]]:
        return self._plugins

    @property
    def apps(self) -> dict[str, dict[str, Any]]:
        return self._apps

    def get_app_permissions(self, app_id: str) -> list[str]:
        app_data = self._apps.get(app_id)
        if not app_data:
            return []
        return list(app_data.get('permissions', []))

    def has_permission(self, app_id: str, permission: str) -> bool:
        return permission in self.get_app_permissions(app_id)

    def backend_path(self, app_id: str) -> Path | None:
        data = self._apps.get(app_id)
        if not data:
            return None
        path = APPS_DIR / app_id / data['entry']['backend']
        return path if path.exists() else None

    def app_router(self, app_id: str) -> Any | None:
        backend_path = self.backend_path(app_id)
        if backend_path is None:
            return None
        module_name = f'tvtv_app_{app_id.replace("-", "_")}'
        spec = importlib.util.spec_from_file_location(module_name, str(backend_path))
        mod = importlib.util.module_from_spec(spec)
        # Register before exec: pydantic resolves annotations by looking the
        # defining module up in sys.modules. An unregistered module leaves
        # every model in it "not fully defined" under `from __future__ import
        # annotations` on Python 3.13+, which breaks /openapi.json and any
        # route that touches the model.
        sys.modules[module_name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            # Previously swallowed: a broken app silently vanished from the
            # UI with no clue why. Surface it in the log and the error list.
            sys.modules.pop(module_name, None)
            msg = f'app "{app_id}" backend failed to import: {e!r}'
            self.load_errors.append(msg)
            log.error('%s (%s)', msg, backend_path)
            return None
        return getattr(mod, 'router', None)
