"""Authentication, Pairing, and Security Posture Module.

P8-1 & P8-10: Provides flexible local appliance security:
  - "open" (default): trusted private home LAN mode. Loopback and LAN clients
    can control playback and browse media.
  - "pair_required": requires a 4-digit PIN pairing exchange to issue a client
    token for external LAN devices (e.g. mobile phones).
  - "kiosk_only": completely blocks non-loopback control; only the local TV
    kiosk can trigger playback or modify settings.

Loopback connections (127.0.0.1 / ::1 / localhost) from the local kiosk are
always authenticated.
"""

from __future__ import annotations

import json
import logging
import os
import random
import secrets
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, Request

log = logging.getLogger('tvtv.auth')

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / 'config'
STATE_DIR = Path(__file__).resolve().parent.parent.parent / 'var' / 'auth'
STATE_DIR.mkdir(parents=True, exist_ok=True)
PAIRING_STATE_FILE = STATE_DIR / 'pairing_sessions.json'

_cached_pin: Optional[str] = None
_pin_created_at: float = 0.0


def _read_settings() -> dict:
    settings_file = CONFIG_DIR / 'settings.json'
    if settings_file.exists():
        try:
            return json.loads(settings_file.read_text())
        except Exception:
            pass
    return {}


def get_security_mode() -> str:
    """Security mode: 'open' | 'pair_required' | 'kiosk_only'."""
    mode = os.environ.get('TVTV_SECURITY_MODE')
    if mode:
        return mode.lower()
    return _read_settings().get('security_mode', 'open').lower()


def is_loopback(host: str) -> bool:
    return host in ('127.0.0.1', '::1', 'localhost', 'testclient')


def get_active_pin() -> str:
    """Get or generate the current 4-digit pairing PIN."""
    global _cached_pin, _pin_created_at
    now = time.time()
    # Regenerate PIN every 24 hours or if not set
    if not _cached_pin or (now - _pin_created_at > 86400):
        _cached_pin = f"{random.randint(1000, 9999)}"
        _pin_created_at = now
    return _cached_pin


def _load_paired_tokens() -> dict[str, dict[str, Any]]:
    if PAIRING_STATE_FILE.exists():
        try:
            return json.loads(PAIRING_STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_paired_tokens(tokens: dict[str, dict[str, Any]]) -> None:
    try:
        PAIRING_STATE_FILE.write_text(json.dumps(tokens, indent=2))
        PAIRING_STATE_FILE.chmod(0o600)
    except Exception as e:
        log.warning('Failed to save pairing tokens: %s', e)


def is_token_valid(token: str) -> bool:
    if not token:
        return False
    # Check fixed admin token if set
    admin_token = os.environ.get('TVTV_ADMIN_TOKEN')
    if admin_token and secrets.compare_digest(token, admin_token):
        return True
    tokens = _load_paired_tokens()
    entry = tokens.get(token)
    if not entry:
        return False
    # Expire after 60 days
    if time.time() - entry.get('created_at', 0) > (86400 * 60):
        return False
    return True


def create_paired_token(client_name: str = 'Remote Device') -> str:
    token = secrets.token_hex(24)
    tokens = _load_paired_tokens()
    tokens[token] = {
        'client_name': client_name,
        'created_at': time.time(),
    }
    _save_paired_tokens(tokens)
    return token


def verify_client_access(request: Request) -> bool:
    """Verify if the incoming HTTP request is permitted to access the appliance."""
    client_host = request.client.host if request.client else '127.0.0.1'
    if is_loopback(client_host):
        return True

    mode = get_security_mode()

    if mode == 'kiosk_only':
        raise HTTPException(
            status_code=403,
            detail="Access restricted: Appliance is running in Kiosk-Only mode."
        )

    if mode == 'open':
        return True

    # Mode: pair_required
    token = (
        request.headers.get('X-Auth-Token')
        or request.query_params.get('token')
        or request.cookies.get('tvtv_session')
    )
    if token and is_token_valid(token):
        return True

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        bearer = auth_header[7:].strip()
        if is_token_valid(bearer):
            return True

    raise HTTPException(
        status_code=401,
        detail="Device pairing required. Please enter the 4-digit PIN shown on the TV Settings.",
        headers={"WWW-Authenticate": "Bearer"},
    )
