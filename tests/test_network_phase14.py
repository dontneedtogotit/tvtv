"""Unit tests for Phase 14 Network endpoints."""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

from fastapi.testclient import TestClient

def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        sys.exit(1)

def main() -> int:
    import server as appmod
    client = TestClient(appmod.app)

    # P14-1: Wi-Fi scan endpoint exists and responds (loopback)
    r = client.get('/wifi/scan')
    check('P14-1 wifi/scan responds', r.status_code in (200, 503), f'status {r.status_code}')

    # P14-3: WoL endpoint validates MAC
    r = client.post('/wol', json={'mac': '00:11:22:33:44:55'})
    check('P14-3 wol sends magic packet', r.status_code == 200, f'status {r.status_code}')

    r = client.post('/wol', json={'mac': 'invalid'})
    check('P14-3 wol rejects bad MAC', r.status_code == 400, f'status {r.status_code}')

    return 0

if __name__ == '__main__':
    sys.exit(main())
