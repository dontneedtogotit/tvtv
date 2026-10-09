"""YouTube account authentication for MPV playback.

MPV resolves yt-dlp on PATH and shells out to it for every YouTube URL. To
play age-restricted or account-specific content, yt-dlp must be given the
account's cookies. We keep a Netscape ``cookies.txt`` in the backend's own
writable config dir (not the read-only ``~/.config`` sandbox path) and hand it
to the yt-dlp hook via ``--ytdl-raw-options=cookies=<file>``.

Users get the file by exporting it from any logged-in browser
("cookies.txt" extension: Copy as header / Netscape), pasting it into Settings
→ Account, or importing it straight from the local kiosk Chromium profile.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sqlite3
import struct
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger('tvtv.yt_auth')

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / 'config'
COOKIE_FILE = CONFIG_DIR / 'yt-cookies.txt'
COOKIE_SHEBANG = '# Netscape HTTP Cookie File'

_VENV_BIN = Path(__file__).resolve().parent.parent.parent / '.venv' / 'bin'
YTDLP = str(_VENV_BIN / 'yt-dlp') if (_VENV_BIN / 'yt-dlp').exists() else 'yt-dlp'


def cookies_path() -> Path:
    return COOKIE_FILE


def cookies_present() -> bool:
    return COOKIE_FILE.is_file() and COOKIE_FILE.stat().st_size > 0


def save_cookie_text(text: str) -> dict:
    """Store a pasted Netscape cookies.txt (or raw lines).

    Returns {'ok', 'cookies': n}. Rejects empty or non-cookie input.
    """
    if not text or not text.strip():
        return {'ok': False, 'detail': 'Empty cookie text'}
    if not text.lstrip().startswith(COOKIE_SHEBANG):
        text = COOKIE_SHEBANG + '\n' + text
    # Validate: need at least one well-formed Netscape line
    # (host  name  value, minimum 6 tab/comma-ish fields with a dotted host).
    cookies = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) < 6:
            fields = line.split()
        if len(fields) >= 6 and '.' in fields[0] and fields[1]:
            cookies += 1
    if cookies == 0:
        return {'ok': False,
                'detail': 'No valid Netscape cookie lines found '
                          '(need host + name per line; export a cookies.txt)'}
    COOKIE_DIR = COOKIE_FILE.parent
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(text.rstrip() + '\n')
    COOKIE_FILE.chmod(0o600)
    return {'ok': True, 'cookies': cookies}


def clear_cookies() -> dict:
    try:
        COOKIE_FILE.unlink()
        return {'ok': True}
    except FileNotFoundError:
        return {'ok': True, 'detail': 'not present'}


def _run_ytdlp(args: list[str], timeout: int) -> tuple[int, str]:
    cmd = [YTDLP] + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    except FileNotFoundError:
        return 127, 'yt-dlp binary not found'
    except subprocess.TimeoutExpired:
        return 124, 'timed out'


def verify_login(timeout: int = 30) -> dict:
    """Confirm the stored cookies authenticate to a YouTube account.

    ``yt-dlp --cookies <file> --simulate --extractor-args
    youtube:player_client=default "https://www.youtube.com/"`` reports the
    logged-in uploader for a signed-in profile.
    """
    if not cookies_present():
        return {'ok': False, 'logged_in': False, 'detail': 'No cookies saved'}
    rc, out = _run_ytdlp(
        ['--cookies', str(COOKIE_FILE), '--simulate',
         '--extractor-args', 'youtube:player_client=default',
         'https://www.youtube.com/'],
        timeout=timeout,
    )
    # The home page has no video; yt-dlp errors out, but a signed-in session
    # surfaces the account handle in the extractor error / output.
    import re
    m = re.search(r'(?:@|on YouTube as )([A-Za-z0-9._-]{2,})', out)
    if rc != 0:
        # Distinguish "not logged in / anonymous" (still extracts) from a
        # real failure (no network, cookies rejected).
        if 'sign in' in out.lower() or 'age' in out.lower() or 'age-restricted' in out.lower():
            return {'ok': True, 'logged_in': False, 'detail': 'Cookies accepted, no account detected'}
        return {'ok': False, 'logged_in': False, 'detail': out.strip()[-200:] or f'exit {rc}'}
    return {'ok': True, 'logged_in': bool(m), 'account': m.group(1) if m else None}


def _chrome_decrypt_value(enc: bytes, key: Optional[bytes]) -> Optional[str]:
    """Decrypt a Chrome (Linux) encrypted cookie value.

    Chrome Linux prefix: b'v10' + 16-byte IV + AES-CBC ciphertext.
    With a Local State ``encrypted_key`` the key is PBKDF2-SHA1(key, 'salt',
    1, 16). Without one (no keyring daemon, e.g. a headless kiosk) Chrome
    falls back to the literal passphrase 'peanuts'.
    """
    if not enc or not enc.startswith(b'v10'):
        # Plaintext cookie — return as-is.
        try:
            return enc.decode('utf-8')
        except UnicodeDecodeError:
            return None
    if key is None:
        key = hashlib.pbkdf2_hmac('sha1', b'peanuts', b'salt', 1, 16)
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        iv, blob = enc[3:3 + 16], enc[3 + 16:]
        d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        plain = d.update(blob) + d.finalize()
        pad = plain[-1]
        if 1 <= pad <= 16:
            plain = plain[:-pad]
        return plain.decode('utf-8')
    except Exception as e:  # noqa: BLE001 - decryption is best-effort per cookie
        log.debug('cookie decrypt failed: %s', e)
        return None


def _read_chrome_cookies(profile: Path) -> list[tuple]:
    db = profile / 'Default' / 'Cookies'
    if not db.is_file():
        return []
    # Encrypted key (may be absent on a kiosk with no keyring daemon).
    key: Optional[bytes] = None
    ls = profile / 'Local State'
    try:
        data = json.loads(ls.read_text())
        b64 = data.get('os_crypt', {}).get('encrypted_key')
        if b64:
            raw = base64.b64decode(b64)
            if raw[:3] == b'v10':
                key = hashlib.pbkdf2_hmac('sha1', raw[3:], b'salt', 1, 16)
    except Exception:  # noqa: BLE001
        key = None
    rows: list[tuple] = []
    try:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        cur = con.execute(
            'SELECT host_key, name, value, encrypted_value, path, expires_utc, '
            'is_secure, is_httponly FROM cookies'
        )
        for host, name, value, enc, path, expires, secure, httponly in cur:
            val = value or _chrome_decrypt_value(enc, key)
            if val is None:
                continue
            # Chrome epoch (µs since 1601-01-01) → unix seconds.
            ts = int((expires - 11644473600000000) / 1_000_000) if expires else 0
            rows.append((host, name, val, path, ts, bool(secure), bool(httponly)))
        con.close()
    except sqlite3.DatabaseError as e:
        log.warning('could not read Chromium cookie DB %s: %s', db, e)
    return rows


def _chrome_profile_dirs() -> list[Path]:
    home = Path.home()
    dirs = [
        home / '.config' / 'chromium',
        home / '.var' / 'app' / 'org.chromium.Chromium',
        # snap chromium (kiosk default) — confirmed on the NUC:
        #   /home/tv/snap/chromium/common/chromium/Default/Cookies,
        #   no keyring, no os_crypt.encrypted_key → 'peanuts' fallback key.
        home / 'snap' / 'chromium' / 'common' / 'chromium',
        home / '.snap' / 'chromium' / 'common' / 'chromium',
        home / '.config' / 'google-chrome',
        home / '.config' / 'chromium-browser',
    ]
    return [d for d in dirs if d.is_dir()]


def import_from_browser() -> dict:
    """Extract cookies from the local (kiosk) Chromium profile.

    Works unattended only when the profile stores cookies unencrypted (no
    keyring daemon) or the key can be read from Local State. Returns the
    imported count, or a clear error when no usable profile is found.
    """
    for profile in _chrome_profile_dirs():
        rows = _read_chrome_cookies(profile)
        if rows:
            netscape = _to_netscape(rows)
            save_cookie_text(netscape)
            yt = [r for r in rows if 'youtube' in r[0] or 'google' in r[0]]
            return {'ok': True, 'cookies': len(rows), 'youtube': len(yt),
                    'profile': str(profile)}
    return {'ok': False, 'detail': 'No Chromium profile with cookies found'}


def _to_netscape(rows: list[tuple]) -> str:
    lines = [COOKIE_SHEBANG,
             '# http://curl.haxx.se/docs/http-cookies.html']
    for host, name, val, path, ts, secure, httponly in rows:
        dom = host if host.startswith('.') else '.' + host
        lines.append('\t'.join([
            dom, 'TRUE' if dom.startswith('.') else 'FALSE',
            path or '/', 'TRUE' if secure else 'FALSE',
            str(ts), name, val,
        ]))
    return '\n'.join(lines) + '\n'


def mpv_cookie_args() -> list[str]:
    """Extra MPV args that hand the cookie file to the yt-dlp hook.

    ``--ytdl-raw-options=KEY=VALUE`` is forwarded to the spawned yt-dlp as
    ``--KEY VALUE``. Verified against mpv 0.37: the hook runs
    ``yt-dlp --no-warnings -J ... --cookies <file> <url>``. (mpv 0.37 has no
    standalone ``--cookies`` option — only the ytdl-raw-options path works.)
    """
    if not cookies_present():
        return []
    return ['--ytdl-raw-options=cookies=' + str(COOKIE_FILE)]
