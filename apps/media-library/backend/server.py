"""Media Library backend with path confinement.

P7-10: Confines browsing to allowed media directories to prevent traversal
into arbitrary filesystem paths (e.g. /etc, /root, /home/user/.ssh).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEDIA_DIR = Path(os.environ.get('TVTV_MEDIA_DIR', '/home/htpc/media'))
VAR_MEDIA_DIR = PROJECT_ROOT / 'var' / 'media'
VAR_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def _allowed_roots() -> list[Path]:
    roots = [DEFAULT_MEDIA_DIR, VAR_MEDIA_DIR]
    home = Path.home()
    for extra in ('media', 'Videos', 'Music', 'Downloads'):
        p = home / extra
        if p.exists():
            roots.append(p)
    return [r.resolve() for r in roots]


def _is_confined(target: Path) -> bool:
    try:
        resolved = target.resolve()
        for root in _allowed_roots():
            try:
                if resolved == root or resolved.is_relative_to(root):
                    return True
            except AttributeError:
                # Python < 3.9 fallback
                if str(resolved).startswith(str(root)):
                    return True
        return False
    except Exception:
        return False


def _get_default_root() -> Path:
    if DEFAULT_MEDIA_DIR.exists() and DEFAULT_MEDIA_DIR.is_dir():
        return DEFAULT_MEDIA_DIR.resolve()
    return VAR_MEDIA_DIR.resolve()


@router.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@router.get('/scan')
def scan(root: Optional[str] = Query(default=None)):
    target = Path(root).resolve() if root else _get_default_root()

    if not _is_confined(target):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: path '{target}' is outside allowed media roots"
        )

    if not target.exists() or not target.is_dir():
        return {'items': [], 'root': str(target), 'exists': False}

    items = []
    try:
        for child in sorted(target.iterdir())[:200]:
            try:
                items.append({
                    'name': child.name,
                    'path': str(child),
                    'type': 'directory' if child.is_dir() else 'file',
                    'size': child.stat().st_size if child.is_file() else None,
                })
            except Exception:
                pass
    except Exception:
        pass

    return {
        'items': items,
        'root': str(target),
        'allowed_roots': [str(r) for r in _allowed_roots() if r.exists()],
    }
