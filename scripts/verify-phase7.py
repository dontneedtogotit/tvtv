#!/usr/bin/env python3
"""End-to-end verification of the Phase 7 wiring changes.

Boots the real uvicorn on a free port, then exercises:
  * /api/health exposes the resolved TV profile + app load errors
  * settings POST preserves keys it does not model (P7-11)
  * history merge is keyed by URL, not append-only (P7-7 support)
  * position checkpoint writes through a mock MPV IPC socket (P7-7)
  * a malformed app manifest is rejected without killing the server (P7-12)
  * MPV args from tv.conf actually reach the launch argv (P7-2)

Run from the repo root:  .venv/bin/python scripts/verify-phase7.py
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get('VERIFY_PORT', '8099'))
BASE = f'http://127.0.0.1:{PORT}'
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        FAILURES.append(label)


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read())


def post(path: str, payload: dict | None = None):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        BASE + path, data=data, headers={'Content-Type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def delete(path: str):
    req = urllib.request.Request(BASE + path, method='DELETE')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def wait_for_health(tries: int = 60) -> bool:
    for _ in range(tries):
        try:
            if get('/api/health')['status'] == 'ok':
                return True
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            time.sleep(0.5)
    return False


class MockMpv(threading.Thread):
    """Minimal MPV JSON IPC server: answers get_property, records commands."""

    def __init__(self, path: str, props: dict):
        super().__init__(daemon=True)
        self.path = path
        self.props = props
        self.commands: list[str] = []
        # A crashed run leaves the socket file behind; bind() then fails with
        # EADDRINUSE even though nothing is listening.
        with suppress(OSError):
            os.unlink(path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(path)
        self._sock.listen(8)
        self._stop = False

    def run(self) -> None:
        self._sock.settimeout(0.5)
        while not self._stop:
            try:
                conn, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(3)
            try:
                raw = b''
                while b'\n' not in raw:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                line = raw.split(b'\n', 1)[0].decode().strip()
                if not line:
                    return
                if line.startswith('{'):
                    req = json.loads(line)
                    cmd = req.get('command', [])
                    if cmd and cmd[0] == 'get_property':
                        prop = cmd[1]
                        if prop in self.props:
                            conn.sendall((json.dumps(
                                {'error': 'success', 'data': self.props[prop]}
                            ) + '\n').encode())
                        else:
                            conn.sendall((json.dumps(
                                {'error': 'property unavailable', 'data': None}
                            ) + '\n').encode())
                        return
                self.commands.append(line)
                conn.sendall(b'\n')
            except Exception:
                pass

    def shutdown(self) -> None:
        self._stop = True
        try:
            self._sock.close()
        except OSError:
            pass
        with suppress(OSError):
            os.unlink(self.path)


def write_tv_conf(tmp: Path) -> None:
    tmp.write_text(
        '# test profile\n'
        'export WLR_MODE="1920x1080@60"\n'
        'export TV_SCALE="16"\n'
        'export TV_THEME="midnight"\n'
        'export MPV_VO="gpu"\n'
        'export MPV_HWDEC="auto-safe"\n'
        'export MPV_SCALE="--video-scale=bilinear"\n'
        'export TV_AUDIO_PASSTHROUGH="1"\n'
    )


def main() -> int:
    conf = Path(tempfile.mkdtemp()) / 'tv.conf'
    write_tv_conf(conf)

    history_path = ROOT / 'var' / 'history' / 'watch-history.json'
    settings_path = ROOT / 'config' / 'settings.json'
    history_backup = history_path.read_text() if history_path.exists() else None
    settings_backup = settings_path.read_text() if settings_path.exists() else None

    mock = MockMpv('/tmp/mpv-ipc.sock', {
        'path': 'https://youtu.be/verifyVideo',
        'time-pos': 123.5,
        'duration': 600.0,
        'pause': False,
        'media-title': 'Verify Video',
    })
    mock.start()

    env = {
        **os.environ,
        'TVTV_TV_CONF': str(conf),
        'TVTV_PORT': str(PORT),
        'PYTHONPATH': str(ROOT / 'src' / 'backend'),
    }
    proc = subprocess.Popen(
        [str(ROOT / '.venv' / 'bin' / 'uvicorn'), 'server:app',
         '--app-dir', str(ROOT / 'src' / 'backend'),
         '--host', '127.0.0.1', '--port', str(PORT), '--log-level', 'warning'],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    try:
        if not wait_for_health():
            print('FAIL  server never became healthy')
            print(proc.stdout.read() if proc.stdout else '')
            return 1

        # P7-2 / P7-1: TV profile resolved and reported
        health = get('/api/health')
        prof = health.get('tv_profile', {})
        check('P7-2 tv.conf parsed by backend', prof.get('path') == str(conf), str(prof.get('path')))
        check('P7-3 TV_SCALE surfaced', prof.get('tv_scale') == '16', str(prof.get('tv_scale')))
        check('P7-1 passthrough flag read', prof.get('audio_passthrough') is True)
        expected_apps = {
            'camera-setup', 'file-manager', 'history', 'installer',
            'media-library', 'remote', 'settings', 'store', 'system-update',
        }
        registered = set(health.get('apps', []))
        check('P7-12 all apps registered', registered == expected_apps,
              f'missing={sorted(expected_apps - registered)} extra={sorted(registered - expected_apps)}')
        check('P7-12 no manifest load errors', health.get('app_load_errors') == [],
              str(health.get('app_load_errors')))

        # P7-2: profile args reach the play response
        played = post('/api/play', {
            'url': 'https://youtu.be/verifyVideo',
            'title': 'Verify Video',
            'duration': 600.0,
            'sponsorblock': False,
        })
        args = played.get('profile_args', [])
        check('P7-2 --vo from tv.conf', '--vo=gpu' in args, str(args))
        check('P7-2 --hwdec from tv.conf', '--hwdec=auto-safe' in args, str(args))
        check('P7-2 video-scale from tv.conf', '--video-scale=bilinear' in args, str(args))
        check('P7-1 passthrough forces hwdec=no',
              '--audio-passthrough=yes' in args and '--hwdec=no' in args, str(args))
        check('P7-6 no subtitle when none requested', played.get('subtitles') is False)

        # P7-6: explicit subtitle URL becomes --sub-file
        with_sub = post('/api/play', {
            'url': 'https://youtu.be/verifyVideo',
            'title': 'Verify Video',
            'subtitle_url': 'https://example.com/en.vtt',
        })
        check('P7-6 subtitle request recorded', with_sub.get('subtitles') is True)

        # P7-7: position checkpoint writes to history
        delete('/history')
        chk = post('/api/checkpoint')
        check('P7-7 checkpoint endpoint reachable', chk.get('status') == 'ok', str(chk))
        items = get('/history').get('items', [])
        check('P7-7 checkpoint wrote a history entry', len(items) == 1, f'{len(items)} items')
        if items:
            check('P7-7 position persisted', abs(items[0]['position'] - 123.5) < 0.01,
                  str(items[0].get('position')))
            check('P7-7 duration persisted', abs(items[0]['duration'] - 600.0) < 0.01)
            check('P7-7 now-playing status playing',
                  get('/now-playing').get('status') == 'playing')

        # P7-7: history is keyed by URL, not append-only
        post('/api/checkpoint')
        items2 = get('/history').get('items', [])
        check('P7-7 repeat checkpoint merges, not duplicates', len(items2) == 1,
              f'{len(items2)} items after 2nd checkpoint')

        # P7-7: position endpoint reflects mock MPV
        pos = get('/api/position')
        check('P7-7 /api/position reads MPV directly',
              pos.get('playing') is True and abs(pos['time'] - 123.5) < 0.01, str(pos))

        # P7-7: control reaches MPV over the socket
        post('/api/control', {'action': 'pause'})
        time.sleep(0.3)
        check('P7-7 control command reached MPV', 'cycle pause' in mock.commands,
              str(mock.commands))

        # P7-11: settings POST preserves unknown keys
        post('/settings', {'sponsorblock': True, 'default_quality': '720p', 'tv_mode': '1080p@60'})
        on_disk = json.loads(settings_path.read_text())
        on_disk['future_phase_key'] = 'keep-me'
        settings_path.write_text(json.dumps(on_disk, indent=2))
        post('/settings', {'sponsorblock': False, 'default_quality': '1080p', 'tv_mode': '1080p@60'})
        after = json.loads(settings_path.read_text())
        check('P7-11 unknown settings keys survive a save',
              after.get('future_phase_key') == 'keep-me', str(after))

        # P7-5: camera app the remote links to must resolve
        remote_html = urllib.request.urlopen(BASE + '/remote', timeout=10).read().decode()
        import re
        links = set(re.findall(r"/apps-frontend/([a-z0-9-]+)/", remote_html))
        dead = []
        for app_id in links:
            try:
                urllib.request.urlopen(BASE + f'/apps-frontend/{app_id}/', timeout=5)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    dead.append(app_id)
        check('P7-5 remote app links all resolve', not dead,
              f'404: {dead}' if dead else f'checked {sorted(links)}')

        # P7-5: camera app is in the store and proxies (503 when the scanner
        # service is down is correct behaviour, not a missing route).
        store = get('/apps/store/list').get('apps', [])
        store_ids = {a['id'] for a in store}
        check('P7-5 camera-setup appears in the app store',
              'camera-setup' in store_ids, f'store has {sorted(store_ids)}')
        cam_status = get('/apps/camera-setup/status')
        check('P7-5 camera proxy reports upstream state',
              cam_status.get('upstream') in ('up', 'down'), str(cam_status.get('upstream')))
        if cam_status.get('upstream') == 'down':
            check('P7-5 camera proxy explains how to start the scanner',
                  'start.sh' in str(cam_status.get('hint', '')), str(cam_status.get('hint')))
        cam_page = urllib.request.urlopen(BASE + '/apps-frontend/camera-setup/', timeout=5)
        check('P7-5 camera frontend served from the registry', cam_page.status == 200)

        # Regression guard: app routers load by file path, so their pydantic
        # models were previously unresolvable and /openapi.json raised.
        spec = get('/openapi.json')
        routes = set(spec.get('paths', {}).keys())
        expected_routes = {
            '/apps/history/in-progress', '/apps/history/recent', '/apps/history/play',
            '/apps/remote/capabilities', '/apps/settings/overview',
            '/apps/settings/capabilities', '/apps/store/state', '/apps/camera-setup/status',
            '/history/item', '/api/checkpoint',
        }
        missing = sorted(expected_routes - routes)
        check('P7-13 openapi schema builds with app routers mounted', not missing,
              f'missing {missing}' if missing else f'{len(routes)} routes')

        # P7-9: the stub backends now answer real requests
        caps = get('/apps/remote/capabilities')
        check('P7-9 remote capabilities reports apps and controls',
              len(caps.get('apps', [])) >= 9 and 'pause' in caps.get('playback_controls', []),
              f"{len(caps.get('apps', []))} apps")
        overview = get('/apps/settings/overview')
        check('P7-9 settings overview reports real state',
              'settings' in overview and 'tv_profile' in overview,
              f"mpv={'yes' if overview.get('hardware', {}).get('mpv') else 'no'}")
        store_data = get('/apps/store/list')
        first = store_data['apps'][0]
        check('P7-8 store reports real install state',
              first.get('installed') is True and 'built_in' in first and 'disabled' in first,
              str({k: first.get(k) for k in ('id', 'installed', 'built_in', 'disabled')}))
        check('P7-8 store admits there is no remote repository',
              store_data.get('repository') is None and 'available_to_install' in store_data,
              str(store_data.get('note')))
        # Disabling is a real state change, and the store refuses to lock itself out.
        post('/apps/store/state', {'app_id': 'remote', 'disabled': True})
        check('P7-8 disable state persists',
              get('/apps/store/state')['disabled'] == ['remote'],
              str(get('/apps/store/state')))
        post('/apps/store/state', {'app_id': 'remote', 'disabled': False})
        try:
            post('/apps/store/state', {'app_id': 'store', 'disabled': True})
            check('P7-8 store cannot disable itself', False, 'it allowed it')
        except urllib.error.HTTPError as e:
            check('P7-8 store cannot disable itself', e.code == 400, f'HTTP {e.code}')
        check('P7-8 disable state cleared',
              get('/apps/store/state')['disabled'] == [], str(get('/apps/store/state')))

        # P7-9: resume lookup reflects stored positions
        delete('/history')
        post('/history', {'url': 'https://youtu.be/resumeMe', 'title': 'Resume Me',
                          'position': 300.0, 'duration': 900.0})
        resume = post('/apps/history/play', {'url': 'https://youtu.be/resumeMe'})
        check('P7-9 resume resolves stored position',
              resume.get('resumable') is True and resume['seek'] == 300.0, str(resume.get('seek')))
        post('/history', {'url': 'https://youtu.be/finished', 'title': 'Finished',
                          'position': 890.0, 'duration': 900.0})
        done = post('/apps/history/play', {'url': 'https://youtu.be/finished'})
        check('P7-9 near-complete video does not offer resume',
              done.get('resumable') is False and done['seek'] == 0.0, str(done.get('seek')))
        in_prog = get('/apps/history/in-progress')
        check('P7-9 in-progress filters out completed items',
              [i['url'] for i in in_prog['items']] == ['https://youtu.be/resumeMe'],
              str([i['url'] for i in in_prog['items']]))

        # P7-4: /api/trending route exists
        trend = get('/api/trending?limit=2')
        check('P7-4 /api/trending returns results',
              trend.get('query') == 'trending' and 'results' in trend, str(trend.get('query')))

        # P7-10: path confinement on media-library and file-manager
        try:
            get('/apps/media-library/scan?root=/etc')
            check('P7-10 media-library blocks scanning /etc', False, 'allowed /etc')
        except urllib.error.HTTPError as e:
            check('P7-10 media-library blocks scanning /etc', e.code == 403, f'HTTP {e.code}')

        try:
            get('/apps/file-manager/list?path=/etc')
            check('P7-10 file-manager blocks listing /etc', False, 'allowed /etc')
        except urllib.error.HTTPError as e:
            check('P7-10 file-manager blocks listing /etc', e.code == 403, f'HTTP {e.code}')

        # Confined valid directory scan succeeds
        med_scan = get('/apps/media-library/scan')
        check('P7-10 media-library scans default media root',
              'items' in med_scan and 'root' in med_scan, str(med_scan.get('root')))

        fm_list = get('/apps/file-manager/list')
        check('P7-10 file-manager lists default storage root',
              'items' in fm_list and 'path' in fm_list, str(fm_list.get('path')))

        # P7-14: .version file exists and is populated
        v_file = ROOT / '.version'
        check('P7-14 .version file exists', v_file.exists() and len(v_file.read_text().strip()) >= 7,
              v_file.read_text().strip() if v_file.exists() else 'missing')

        # System update status route exposes rollback availability
        sys_status = get('/apps/system-update/status')
        check('P7-14 system-update exposes status and rollback metadata',
              'installed_version' in sys_status and 'rollback_available' in sys_status,
              str(sys_status.get('installed_version')))

        # Phase 9: Queue API Endpoints (P9-8)
        delete('/api/queue')
        q_item = post('/api/queue', {
            'url': 'https://youtu.be/queuedVideo',
            'title': 'Queued Video',
            'duration': 240.0,
        })
        check('P9-8 enqueue endpoint returns item', q_item.get('status') == 'ok' and 'item' in q_item)
        q_list = get('/api/queue')
        check('P9-8 get queue returns item list', len(q_list.get('queue', [])) == 1)
        delete('/api/queue')
        check('P9-8 clear queue empties list', len(get('/api/queue').get('queue', [])) == 0)

        # Phase 9: Player Tracks API (P9-3)
        tracks = get('/api/player/tracks')
        check('P9-3 player tracks endpoint responds', 'audio' in tracks and 'subtitles' in tracks)

        print()
        print(f'{len(FAILURES)} failure(s)' if FAILURES else 'ALL CHECKS PASSED')
        return 1 if FAILURES else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        mock.shutdown()
        if history_backup is not None:
            history_path.write_text(history_backup)
        if settings_backup is not None:
            settings_path.write_text(settings_backup)


if __name__ == '__main__':
    sys.exit(main())
