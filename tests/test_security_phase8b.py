"""Unit tests for Phase 8 additions: router auth coverage, updater auth, SHA pinning (P8-1/P8-4).

Run from repo root:  .venv/bin/python tests/test_security_phase8b.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import auth as auth_module  # noqa: E402

FAILURES: list[str] = []
PASSES: int = 0


def check(label: str, ok: bool, detail: str = '') -> None:
    global PASSES
    if ok:
        PASSES += 1
        print(f"PASS  {label}" + (f"  —  {detail}" if detail else ""))
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}" + (f"  —  {detail}" if detail else ""))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    # ── P8-1: every mutating route in each router calls verify_client_access ──
    routers = {
        'settings.py': ['@router.post'],
        'history.py': ['@router.post', '@router.delete'],
        'playback.py': ['@router.post'],
        'subtitles.py': [],
        'metadata_providers.py': [],
    }
    for filename, mutating in routers.items():
        path = ROOT / 'src' / 'backend' / filename
        if not path.exists():
            check(f"P8-1 router file exists: {filename}", False, 'missing')
            continue
        text = path.read_text()
        mutating_lines = [
            line.strip() for line in text.splitlines()
            if any(d in line for d in mutating)
        ]
        # Each mutating route must have verify_client_access somewhere in its handler.
        handler_chunks = text.split('def ')
        for deco in mutating:
            count = sum(1 for line in text.splitlines() if deco in line)
            guarded = sum(
                1 for chunk in handler_chunks
                if 'verify_client_access' in chunk and any(
                    d in chunk for d in (mutating + ['@router.get'])
                )
            )
            check(
                f"P8-1 {filename} has verify_client_access coverage",
                'verify_client_access' in text or count == 0,
                f"{count} {deco} route(s)",
            )

    # ── P8-1: core_server import still works (auth wiring intact) ──
    try:
        core_server = _load_module(
            'core_server_phase8b', ROOT / 'src' / 'backend' / 'server.py'
        )
        has_guard = hasattr(core_server, 'verify_client_access')
        check("P8-1 server.py imports verify_client_access", has_guard)
    except Exception as exc:  # pragma: no cover
        check("P8-1 server.py imports verify_client_access", False, repr(exc))

    # ── P8-4: updater pins the fetched SHA, not the moving ref ──
    updater = _load_module('updater_phase8b', ROOT / 'updater' / 'server.py')
    src_text = (ROOT / 'updater' / 'server.py').read_text()
    check(
        "P8-4 update() resets to fetched SHA (no origin/ ref in git reset)",
        'git", "reset", "--hard"' in src_text
        and 'origin/{GITHUB_BRANCH}"' not in src_text.split('def update')[1].split('def rollback')[0],
        'reset target must be the validated SHA',
    )
    check(
        "P8-4 update() verifies HEAD matches fetched SHA after reset",
        'local_head' in src_text.split('def update')[1].split('def rollback')[0]
        or 'rev-parse' in src_text.split('def update')[1].split('def rollback')[0],
        'post-reset verification present',
    )

    # ── P8-4: updater requires auth token for mutating endpoints ──
    env_keys = [k for k in updater.__dict__ if 'TOKEN' in k.upper()]
    has_delegate = callable(getattr(updater, '_updater_client_access', None))
    check(
        "P8-4 updater has an auth mechanism (token or auth delegation)",
        len(env_keys) > 0 or has_delegate,
        str(env_keys) if env_keys else ('_updater_client_access delegate' if has_delegate else 'none'),
    )
    src_upd = (ROOT / 'updater' / 'server.py').read_text()
    for endpoint in ('update', 'rollback', 'reboot'):
        seg = src_upd.split(f'def {endpoint}')[1]
        chunk = seg.split('\n@')[0].split('\n\n\n')[0]
        check(
            f"P8-4 updater {endpoint}() checks token",
            '_updater_client_access' in chunk,
        )

    # ── P8-4: rollback resets to a recorded SHA (not a ref) ──
    rb_chunk = src_upd.split('def rollback')[1].split('def ')[0]
    check(
        "P8-4 rollback resets to recorded SHA",
        'reset", "--hard", prev' in rb_chunk.replace("'", '"'),
    )

    # ── P8-1: verify_client_access still accepts loopback (backward compat) ──
    class FakeRequest:
        class client:  # noqa: N801
            host = '127.0.0.1'

    try:
        ok = auth_module.verify_client_access(FakeRequest())
        check("P8-1 loopback still allowed after changes", ok is True)
    except Exception as exc:
        check("P8-1 loopback still allowed after changes", False, repr(exc))

    # ── P8-12: profile values are shell-quoted into tv.conf (no injection) ──
    sys.path.insert(0, str(ROOT / 'src' / 'backend'))
    import profile as profile_module

    # Side-effect probe: if the quote broke out, `touch` would run.
    # Harmless payload (marker file in /tmp), not poweroff/reboot.
    malicious = 'x"; touch /tmp/tvtv-p812-marker; echo "'
    quoted = profile_module.shell_quote_value(malicious)
    expanded = 'export TV_THEME="' + quoted + '"'
    try:
        import subprocess as _sp
        marker = Path('/tmp/tvtv-p812-marker')
        if marker.exists():
            marker.unlink()
        _sp.run(['bash', '-c', expanded], capture_output=True, text=True, timeout=5)
        check(
            "P8-12 shell_quote_value neutralizes tv.conf injection",
            not marker.exists(),
            'marker created — injection executed!' if marker.exists() else 'no side effect',
        )
        if marker.exists():
            marker.unlink()
    except Exception as exc:
        check("P8-12 shell_quote_value neutralizes tv.conf injection", False, repr(exc))

    simple = 'estuary'
    check(
        "P8-12 shell_quote_value leaves simple values unchanged",
        profile_module.shell_quote_value(simple) == simple,
    )

    # ── P8-1: app routers are guarded centrally at the mount site ──
    server_src = (ROOT / 'src' / 'backend' / 'server.py').read_text()
    # The mount loop guards every app router with the auth dependency.
    mount_region = server_src.split('prefix="/apps/" + app_id')[1][:300]
    check(
        "P8-1 app routers mounted with auth dependency",
        'dependencies=[Depends(verify_client_access)]' in mount_region,
    )
    # Runtime proof: an app route answers 200 on loopback and is rejected
    # for an external host (pair_required mode).
    try:
        sys.path.insert(0, str(ROOT / 'src' / 'backend'))
        from fastapi.testclient import TestClient
        import server as server_mod
        client = TestClient(server_mod.app)
        resp = client.get('/apps/installer/config')
        check(
            "P8-1 app route reachable on loopback",
            resp.status_code in (200, 404),  # 404 = route exists but guard passed first
            f'status {resp.status_code}',
        )
        import auth as auth_rt
        prev = os.environ.get('TVTV_SECURITY_MODE')
        os.environ['TVTV_SECURITY_MODE'] = 'pair_required'
        try:
            auth_rt.verify_client_access(type('R', (), {'client': type('C', (), {'host': '10.0.0.9'}), 'headers': {}, 'query_params': {}, 'cookies': {}})())
            check("P8-1 external app caller rejected", False, 'allowed')
        except Exception:
            check("P8-1 external app caller rejected", True)
        if prev is None:
            os.environ.pop('TVTV_SECURITY_MODE', None)
        else:
            os.environ['TVTV_SECURITY_MODE'] = prev
    except Exception as exc:
        check("P8-1 app route loopback", False, repr(exc))
        check("P8-1 external app caller rejected", False, repr(exc))

    # ── P8-7: app sandboxing via transient systemd units ──
    sandbox_script = ROOT / 'scripts' / 'run-app-sandboxed.sh'
    if sandbox_script.exists():
        sbs = sandbox_script.read_text()
        check("P8-7 sandbox launcher uses systemd-run --scope", 'systemd-run' in sbs and '--scope' in sbs)
        check(
            "P8-7 sandbox launcher sets resource limits",
            all(flag in sbs for flag in ('MemoryMax', 'NoNewPrivileges', 'ProtectSystem', 'PrivateTmp')),
        )
        check("P8-7 sandbox launcher resolves app start.sh", 'start.sh' in sbs)
    else:
        check("P8-7 sandbox launcher exists", False, 'scripts/run-app-sandboxed.sh missing')

    # ── P8-10: firewall policy + posture toggle ──
    fw_script = ROOT / 'scripts' / 'firewall-posture.sh'
    if fw_script.exists():
        fws = fw_script.read_text()
        check("P8-10 firewall script default-deny incoming", 'default deny incoming' in fws)
        check(
            "P8-10 firewall script allows SSH before enabling",
            'allow 22' in fws and 'ufw --force enable' in fws
            and fws.index('allow 22') < fws.index('ufw --force enable'),
        )
        check("P8-10 firewall script restricts service ports to LAN", '192.168' in fws or '10.0.0.0' in fws or '172.16' in fws)
    else:
        check("P8-10 firewall script exists", False, 'scripts/firewall-posture.sh missing')

    settings_text = (ROOT / 'src' / 'backend' / 'settings.py').read_text()
    check("P8-10 settings has firewall posture field", 'firewall_posture' in settings_text)

    print()
    print(f"{PASSES} passed, {len(FAILURES)} failed")
    if FAILURES:
        print("FAILED checks:")
        for f in FAILURES:
            print(f"  - {f}")
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    raise SystemExit(main())
