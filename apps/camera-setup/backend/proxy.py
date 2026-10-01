"""Camera-setup app router.

The camera scanner is a self-contained FastAPI service on port 8002 with its
own venv (it needs `qrcode`, which the main app does not depend on). It was
never registered as an app, so `/apps-frontend/camera-setup/` 404s and the
remote's Cameras button went nowhere.

Rather than merge the scanner into the main app and drag its dependencies in,
this router reverse-proxies the app's frontend-facing API surface to that
service. The frontend is then served from the registry like every other app,
its `const API = window.location.origin` calls resolve to the main origin,
and the same-origin paths all land here.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

log = logging.getLogger('tvtv.app.camera-setup')

router = APIRouter()

UPSTREAM = 'http://127.0.0.1:8002'

# Long scans (subnet sweep) and QR generation both outrun the default budget.
UPSTREAM_TIMEOUT_S = 300.0


@router.get('/status')
def status() -> dict:
    """Whether the camera scanner is reachable — shown in the app header."""
    try:
        with urllib.request.urlopen(f'{UPSTREAM}/api/health', timeout=3) as r:
            return {'upstream': 'up', 'detail': json.loads(r.read())}
    except Exception as e:
        return {
            'upstream': 'down',
            'detail': str(e),
            'hint': 'Start the scanner with: bash apps/camera-setup/start.sh',
        }


async def _proxy(request: Request) -> Response:
    body = await request.body()
    target = f"{UPSTREAM}{request.url.path.replace('/apps/camera-setup', '')}"
    if request.url.query:
        target += f"?{request.url.query}"
    req = urllib.request.Request(
        target,
        data=body or None,
        method=request.method,
        headers={'Content-Type': request.headers.get('content-type', 'application/json')},
    )
    try:
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT_S) as r:
            raw = r.read()
            return Response(
                content=raw,
                status_code=r.status,
                media_type=r.headers.get('content-type', 'application/json'),
            )
    except urllib.error.HTTPError as e:
        detail = e.read()
        return Response(
            content=detail or json.dumps({'detail': str(e)}).encode(),
            status_code=e.code,
            media_type='application/json',
        )
    except Exception as e:
        log.warning('camera-setup upstream %s failed: %s', target, e)
        return JSONResponse(
            {
                'detail': 'Camera scanner service is not reachable',
                'upstream': UPSTREAM,
                'error': str(e),
            },
            status_code=503,
        )


for _path in (
    '/api/health',
    '/api/system',
    '/api/brands',
    '/api/brands/{brand_name}',
    '/api/scan',
    '/api/probe',
    '/api/camera-notes',
    '/api/camera-notes/{ip}',
    '/api/qr',
    '/api/qr/{data}',
):
    router.add_api_route(_path, _proxy, methods=['GET', 'POST'], include_in_schema=False)
