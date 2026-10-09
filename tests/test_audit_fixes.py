"""Comprehensive verification test for tvtv OS audit fixes:
- Camera app router & endpoints
- YouTube search & play canonicalization
- System updater endpoints & branch detection
- Ubuntu app store catalog & package search
- Native Chromium browser app & endpoints
"""
from __future__ import annotations

import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

import server as core_server
from apps import AppRegistry


def check(label: str, ok: bool, detail: str = '') -> None:
    status = 'PASS' if ok else 'FAIL'
    msg = f'{status}  {label}'
    if detail:
        msg += f'  — {detail}'
    print(msg)
    if not ok:
        raise AssertionError(label)


def test_audit_fixes():
    print("=== Running Audit Verification Tests ===")

    # 1. App Registry Loads All 10 Apps
    reg = core_server.registry
    check('AppRegistry loads all 10 apps with no errors', len(reg.load_errors) == 0, f"{len(reg.apps)} apps loaded")
    for app_id in ['camera-setup', 'chromium', 'file-manager', 'history', 'installer', 'media-library', 'remote', 'settings', 'store', 'system-update']:
        check(f'App {app_id} is registered', app_id in reg.apps)

    client = TestClient(core_server.app)

    # 2. Camera Setup Endpoints (Loopback client)
    r_cam_status = client.get('/apps/camera-setup/status')
    check('Camera setup /status responds 200', r_cam_status.status_code == 200, str(r_cam_status.json()))
    
    r_cam_health = client.get('/apps/camera-setup/api/health')
    check('Camera setup /api/health responds 200', r_cam_health.status_code == 200)

    r_cam_brands = client.get('/apps/camera-setup/api/brands')
    check('Camera setup /api/brands lists brands', r_cam_brands.status_code == 200 and 'Hikvision' in r_cam_brands.json())

    r_cam_qr = client.post('/apps/camera-setup/api/qr', json={'data': 'rtsp://admin:12345@192.168.1.100:554/live'})
    check('Camera setup /api/qr generates QR code', r_cam_qr.status_code == 200 and r_cam_qr.json().get('success') is True)

    # 3. System Update Endpoints
    r_upd_status = client.get('/apps/system-update/status')
    check('System update /status responds 200', r_upd_status.status_code == 200, str(r_upd_status.json()))
    check('System update detects branch master/main', r_upd_status.json().get('branch') in ('master', 'main'))

    r_upd_check = client.get('/apps/system-update/check')
    check('System update /check responds 200', r_upd_check.status_code == 200, str(r_upd_check.json()))

    # 4. App Store & Ubuntu Catalog
    r_store_list = client.get('/apps/store/list')
    check('App store /list responds 200', r_store_list.status_code == 200)
    store_data = r_store_list.json()
    check('App store includes ubuntu_apps', 'ubuntu_apps' in store_data and len(store_data['ubuntu_apps']) > 0)

    r_ubuntu_apps = client.get('/apps/store/ubuntu/apps')
    check('App store /ubuntu/apps responds 200', r_ubuntu_apps.status_code == 200)
    ubuntu_ids = [a['id'] for a in r_ubuntu_apps.json().get('apps', [])]
    check('Ubuntu catalog includes chromium, kodi, vlc, retroarch', all(k in ubuntu_ids for k in ['chromium', 'kodi', 'vlc', 'retroarch']))

    r_ubuntu_search = client.get('/apps/store/ubuntu/search?q=video')
    check('App store /ubuntu/search responds 200', r_ubuntu_search.status_code == 200)

    # 5. Native Chromium App
    r_chrom_status = client.get('/apps/chromium/status')
    check('Chromium app /status responds 200', r_chrom_status.status_code == 200, str(r_chrom_status.json()))

    r_chrom_bm = client.get('/apps/chromium/bookmarks')
    check('Chromium app /bookmarks lists streaming web apps', r_chrom_bm.status_code == 200 and len(r_chrom_bm.json().get('bookmarks', [])) > 0)

    # 6. YouTube URL Canonicalization in Search
    search_items = core_server._search_yt('test', limit=2)
    check('YouTube search returns list of items', isinstance(search_items, list))
    for it in search_items:
        check(f'Search item has full valid URL ({it.get("url")})', it.get('url', '').startswith('http://') or it.get('url', '').startswith('https://'))

    print("\nALL AUDIT VERIFICATIONS PASSED!\n")


if __name__ == '__main__':
    test_audit_fixes()
