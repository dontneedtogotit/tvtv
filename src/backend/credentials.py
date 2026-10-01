"""Credentials and secrets loader.

P8-8: Keeps API keys and tokens out of systemd unit files and environment
dumps by reading from a mode 0600 credentials file (~/.config/tvtv/credentials.json).

Lookup priority:
  1. Process environment (e.g. $KILO_API_KEY)
  2. Path pointed to by $TVTV_CREDENTIALS
  3. ~/.config/tvtv/credentials.json
  4. /home/htpc/.config/tvtv/credentials.json
  5. <repo-root>/config/credentials.json
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger('tvtv.credentials')

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _candidate_credential_paths() -> list[Path]:
    paths: list[Path] = []
    override = os.environ.get('TVTV_CREDENTIALS')
    if override:
        paths.append(Path(override))
    home = Path.home() / '.config' / 'tvtv' / 'credentials.json'
    paths.append(home)
    appliance = Path('/home/htpc/.config/tvtv/credentials.json')
    if appliance != home:
        paths.append(appliance)
    paths.append(PROJECT_ROOT / 'config' / 'credentials.json')
    return paths


def load_credentials() -> dict[str, Any]:
    """Load the first readable credentials JSON file."""
    for path in _candidate_credential_paths():
        try:
            if not path.is_file():
                continue
            # Warn if credentials file is world-readable
            st = path.stat()
            if bool(st.st_mode & stat.S_IROTH):
                log.warning('Credentials file %s is world-readable! Run: chmod 0600 %s', path, path)
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except Exception as e:
            log.warning('Failed to read credentials from %s: %s', path, e)
    return {}


def get_secret(key: str, default: str = "") -> str:
    """Retrieve secret key, checking env var first, then credentials file."""
    # Check env var (both uppercase and lowercase)
    env_val = os.environ.get(key) or os.environ.get(key.upper())
    if env_val:
        return env_val
    creds = load_credentials()
    val = creds.get(key) or creds.get(key.lower()) or creds.get(key.upper())
    return str(val) if val is not None else default


def save_secret(key: str, value: str) -> None:
    """Save secret to the user's ~/.config/tvtv/credentials.json with mode 0600."""
    target = Path.home() / '.config' / 'tvtv' / 'credentials.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    current = load_credentials()
    current[key] = value
    target.write_text(json.dumps(current, indent=2) + "\n")
    try:
        target.chmod(0o600)
    except Exception:
        pass
