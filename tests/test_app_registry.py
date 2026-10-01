"""Unit tests for manifest validation and app-registry resilience.

These run without booting the server: the failure modes under test (a
malformed manifest, an app whose backend raises on import) would otherwise
require corrupting the real apps/ directory to observe.

Run from the repo root:  .venv/bin/python tests/test_app_registry.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import apps as apps_module  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        FAILURES.append(label)


def write_app(base: Path, app_id: str, manifest: dict | str, backend: str = '') -> Path:
    d = base / app_id
    (d / 'backend').mkdir(parents=True, exist_ok=True)
    (d / 'manifest.json').write_text(
        manifest if isinstance(manifest, str) else json.dumps(manifest)
    )
    if backend:
        (d / 'backend' / 'server.py').write_text(backend)
    return d / 'manifest.json'


def valid(app_id: str) -> dict:
    return {
        'id': app_id,
        'name': app_id.title(),
        'version': '0.1.0',
        'entry': {'frontend': 'frontend/index.html', 'backend': 'backend/server.py'},
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)

        # --- manifest validation -------------------------------------------
        cases = [
            ('missing id', {'name': 'x', 'version': '1', 'entry': {'frontend': 'f', 'backend': 'b'}}, 'id'),
            ('missing entry', {'id': 'a1', 'name': 'x', 'version': '1'}, 'entry'),
            ('entry not an object', {'id': 'a2', 'name': 'x', 'version': '1', 'entry': 'nope'}, 'object'),
            ('entry missing backend', {'id': 'a3', 'name': 'x', 'version': '1', 'entry': {'frontend': 'f'}}, 'backend'),
            ('id/directory mismatch', valid('mismatch'), 'directory'),
            ('permissions not an array', {**valid('a4'), 'permissions': 'read'}, 'array'),
            ('manifest not an object', '"just a string"', 'object'),
            ('invalid json', '{ this is not json', 'Bad manifest'),
        ]
        for label, manifest, expect in cases:
            path = write_app(base, f'app-{len(cases)}', manifest)
            try:
                apps_module._load_manifest(path)
                check(f'rejects {label}', False, 'accepted an invalid manifest')
            except apps_module.AppManifestError as e:
                check(f'rejects {label}', expect in str(e), str(e))
            except Exception as e:
                check(f'rejects {label}', False, f'wrong exception: {e!r}')

        # A valid manifest passes.
        good = write_app(base, 'good-app', valid('good-app'))
        try:
            apps_module._load_manifest(good)
            check('accepts a valid manifest', True)
        except Exception as e:
            check('accepts a valid manifest', False, str(e))

        # --- registry resilience -------------------------------------------
        bad = base / 'registry-test'
        bad.mkdir()
        write_app(bad, 'ok-app', valid('ok-app'), 'from fastapi import APIRouter\nrouter = APIRouter()\n')
        write_app(bad, 'broken-app', valid('broken-app'), 'raise RuntimeError("boom")\n')
        write_app(bad, 'bad-manifest', {'id': 'bad-manifest', 'name': 'x', 'version': '1'})

        orig_apps, orig_plugins = apps_module.APPS_DIR, apps_module.PLUGINS_DIR
        apps_module.APPS_DIR = bad
        apps_module.PLUGINS_DIR = bad / 'nonexistent'
        try:
            reg = apps_module.AppRegistry()
            reg.load_apps()
            # broken-app has a VALID manifest, so it loads; only its backend
            # import fails, and that happens lazily in app_router().
            check('bad manifest does not abort the load',
                  set(reg.apps) == {'ok-app', 'broken-app'},
                  f'loaded {sorted(reg.apps)}')
            check('bad manifest is reported', len(reg.load_errors) == 1,
                  str(reg.load_errors))
            check('bad manifest error names the app',
                  'bad-manifest' in reg.load_errors[0], str(reg.load_errors))

            check('good app router imports', reg.app_router('ok-app') is not None)
            check('import failure returns None', reg.app_router('broken-app') is None)
            check('import failure is reported', len(reg.load_errors) == 2,
                  str(reg.load_errors))
            check('import failure names the exception',
                  'boom' in reg.load_errors[1], str(reg.load_errors))
            check('unknown app returns None', reg.app_router('nope') is None)
        finally:
            apps_module.APPS_DIR, apps_module.PLUGINS_DIR = orig_apps, orig_plugins

        print()
        print(f'{len(FAILURES)} failure(s)' if FAILURES else 'ALL CHECKS PASSED')
        return 1 if FAILURES else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
