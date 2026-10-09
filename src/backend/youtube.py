"""YouTube account login API (P9): cookie import, verification, status."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

import youtube_auth

log = logging.getLogger('tvtv.youtube')

router = APIRouter(prefix='/api/youtube', tags=['youtube'])


class CookieText(BaseModel):
    text: str = ''


@router.get('/status')
def status() -> dict:
    info = {
        'cookies_present': youtube_auth.cookies_present(),
        'account': None,
    }
    if info['cookies_present']:
        v = youtube_auth.verify_login(timeout=20)
        info['logged_in'] = v.get('logged_in', False)
        info['account'] = v.get('account')
        info['detail'] = v.get('detail')
    return info


@router.post('/cookies')
def save_cookies(body: CookieText) -> dict:
    return youtube_auth.save_cookie_text(body.text)


@router.post('/import')
def import_browser() -> dict:
    """Pull cookies from the local kiosk Chromium profile (works when the
    user logs into youtube.com in the kiosk browser)."""
    return youtube_auth.import_from_browser()


@router.post('/verify')
def verify() -> dict:
    return youtube_auth.verify_login(timeout=30)


@router.delete('/cookies')
def clear_cookies() -> dict:
    return youtube_auth.clear_cookies()
