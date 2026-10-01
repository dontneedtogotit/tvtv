"""Unit tests for Phase 8 Security & Isolation.

Exercises:
  * Credentials loading and 0600 mode creation (P8-8)
  * Systemd service hardening directives (P8-5)
  * App permission inspection & validation (P8-6)
  * Path confinement logic for storage/media (P8-11)
  * CORS regex validation for LAN & loopback (P8-2)

Run from repo root:  .venv/bin/python tests/test_security_phase8.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import apps as apps_module  # noqa: E402
import credentials as creds_module  # noqa: E402
import server as core_server  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        FAILURES.append(label)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)

        # ── 1. Credentials loader (P8-8) ──────────────────────────────────────
        cred_file = tmp_dir / 'credentials.json'
        cred_file.write_text(json.dumps({'kilo_api_key': 'test-secret-12345'}))
        os.environ['TVTV_CREDENTIALS'] = str(cred_file)

        try:
            val = creds_module.get_secret('KILO_API_KEY')
            check('P8-8 credentials file loaded secret', val == 'test-secret-12345', val)

            cred_file.chmod(0o600)
            st = cred_file.stat()
            mode = stat.S_IMODE(st.st_mode)
            check('P8-8 credentials file mode is 0600', mode == 0o600, oct(mode))
        finally:
            os.environ.pop('TVTV_CREDENTIALS', None)

        # ── 2. Systemd hardening directives (P8-5) ───────────────────────────
        yt_service = (ROOT / 'scripts' / 'tvtv-yt.service').read_text()
        check('P8-5 tvtv-yt has NoNewPrivileges', 'NoNewPrivileges=true' in yt_service)
        check('P8-5 tvtv-yt has ProtectSystem=strict', 'ProtectSystem=strict' in yt_service)
        check('P8-5 tvtv-yt has ProtectHome=read-only', 'ProtectHome=read-only' in yt_service)
        check('P8-5 tvtv-yt has PrivateTmp=true', 'PrivateTmp=true' in yt_service)
        check('P8-5 tvtv-yt has ReadWritePaths', 'ReadWritePaths=' in yt_service)
        check('P8-5 tvtv-yt has MemoryMax', 'MemoryMax=4G' in yt_service)

        updater_service = (ROOT / 'updater' / 'tvtv-updater.service').read_text()
        check('P8-5 updater runs unprivileged (User=htpc)', 'User=htpc' in updater_service)
        check('P8-5 updater has ProtectSystem=strict', 'ProtectSystem=strict' in updater_service)
        check('P8-5 updater has PrivateTmp=true', 'PrivateTmp=true' in updater_service)

        # ── 3. Permission Inspection & Enforcement (P8-6) ─────────────────────
        reg = apps_module.AppRegistry()
        reg.load_apps()

        check('P8-6 file-manager has storage.read permission',
              reg.has_permission('file-manager', 'storage.read'))
        check('P8-6 file-manager has storage.list permission',
              reg.has_permission('file-manager', 'storage.list'))
        check('P8-6 file-manager does not have system.update permission',
              not reg.has_permission('file-manager', 'system.update'))
        check('P8-6 system-update has system.update permission',
              reg.has_permission('system-update', 'system.update'))
        check('P8-6 camera-setup has network.scan permission',
              reg.has_permission('camera-setup', 'network.scan'))

        # ── 4. Path Confinement (P8-11) ───────────────────────────────────────
        fm_server = _load_module('fm_mod', ROOT / 'apps' / 'file-manager' / 'backend' / 'server.py')
        ml_server = _load_module('ml_mod', ROOT / 'apps' / 'media-library' / 'backend' / 'server.py')

        check('P8-11 /etc is rejected by path confinement',
              not fm_server._is_confined(Path('/etc')))
        check('P8-11 /etc/shadow is rejected by path confinement',
              not fm_server._is_confined(Path('/etc/shadow')))
        check('P8-11 /root is rejected by path confinement',
              not fm_server._is_confined(Path('/root')))
        check('P8-11 var/media is allowed by path confinement',
              fm_server._is_confined(ROOT / 'var' / 'media'))

        # ── 5. CORS LAN Regex (P8-2) ──────────────────────────────────────────
        pattern = re.compile(core_server.LAN_ORIGIN_REGEX)
        valid_origins = [
            'http://localhost',
            'http://localhost:8000',
            'http://127.0.0.1:8000',
            'http://192.168.1.50:8000',
            'http://192.168.0.1',
            'http://10.0.0.12:8080',
            'http://172.16.0.1:8000',
        ]
        invalid_origins = [
            'http://evil.com',
            'https://malicious.org:8000',
            'http://192.168.1.50.attacker.com',
            'http://1.1.1.1',
            'http://8.8.8.8:8000',
        ]
        for vo in valid_origins:
            check(f'P8-2 CORS allows LAN origin {vo}', bool(pattern.match(vo)))
        for io in invalid_origins:
            check(f'P8-2 CORS blocks external origin {io}', not bool(pattern.match(io)))

        # ── 6. Auth & Pairing (P8-1 & P8-10) ──────────────────────────────────
        import auth as auth_module

        pin = auth_module.get_active_pin()
        check('P8-1 active pairing PIN is 4 digits', len(pin) == 4 and pin.isdigit(), pin)

        token = auth_module.create_paired_token("Test Phone")
        check('P8-1 paired token generated', bool(token) and len(token) >= 24)
        check('P8-1 paired token is valid', auth_module.is_token_valid(token))
        check('P8-1 unknown token is rejected', not auth_module.is_token_valid('invalid-fake-token'))

        check('P8-1 loopback host detection', auth_module.is_loopback('127.0.0.1'))
        check('P8-1 external host detection', not auth_module.is_loopback('192.168.1.100'))

        print()
        print(f'{len(FAILURES)} failure(s)' if FAILURES else 'ALL CHECKS PASSED')
        return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
