"""TV profile loader.

The installer writes `~/.config/tvtv/tv.conf` (a shell file of `export`
lines) and several services source it. The backend runs under systemd and
never had those variables, so every profile setting (MPV_VO, MPV_HWDEC,
audio passthrough, ...) was written by the installer and read by nothing.

This module reads that file directly, so the backend honours the same
profile the compositor does without depending on the environment.

Resolution order:
  1. $TVTV_TV_CONF (explicit override, used by tests and dev)
  2. ~/.config/tvtv/tv.conf
  3. /home/htpc/.config/tvtv/tv.conf (the NUC appliance path)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger('tvtv.profile')

EXPORT_RE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$')


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    override = os.environ.get('TVTV_TV_CONF')
    if override:
        paths.append(Path(override))
    home = Path.home() / '.config' / 'tvtv' / 'tv.conf'
    paths.append(home)
    appliance = Path('/home/htpc/.config/tvtv/tv.conf')
    if appliance != home:
        paths.append(appliance)
    return paths


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def load_tv_conf() -> dict[str, str]:
    """Parse the first readable tv.conf into a dict. Never raises."""
    for path in _candidate_paths():
        try:
            if not path.is_file():
                continue
            values: dict[str, str] = {}
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                m = EXPORT_RE.match(line)
                if m:
                    values[m.group(1)] = _strip_quotes(m.group(2))
            log.debug('loaded TV profile from %s (%d keys)', path, len(values))
            return values
        except Exception as e:
            log.warning('could not read TV profile %s: %s', path, e)
    return {}


def profile_value(key: str, default: str = '') -> str:
    """Look up a key, preferring the process environment.

    systemd units and `install.sh --customize` can both set the variable
    directly; the environment wins when both are present.
    """
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    return load_tv_conf().get(key, default)


def _flag(key: str, default: bool = False) -> bool:
    raw = profile_value(key, '1' if default else '0').strip().lower()
    return raw in ('1', 'true', 'yes', 'on')


def mpv_args() -> list[str]:
    """MPV arguments derived from the TV profile.

    The profile stores bare values (`gpu`, `auto-safe`) for VO/HWDEC and a
    ready-made flag for scale. Prefixes are added here rather than in the
    installer so the file stays readable.
    """
    args: list[str] = []

    vo = profile_value('MPV_VO', 'gpu').strip()
    if vo:
        args.append(f'--vo={vo}')

    hwdec = profile_value('MPV_HWDEC', 'auto-safe').strip()
    if hwdec:
        args.append(f'--hwdec={hwdec}')

    scale = profile_value('MPV_SCALE', '').strip()
    if scale:
        # Already flag-shaped (e.g. "--video-scale=bilinear") in tv.conf.
        args.append(scale if scale.startswith('-') else f'--video-scale={scale}')

    if _flag('TV_AUDIO_PASSTHROUGH', False):
        # Let the filter graph pass bitstreams through untouched. MPV still
        # needs hwdec off for passthrough to be legal for most formats.
        args += ['--audio-passthrough=yes', '--hwdec=no']

    if _flag('TV_AUDIO_NIGHT_MODE', _flag('TV_NIGHT_MODE', False)):
        args.append('--audio-normalize-downmix=no')

    return args


def profile_summary() -> dict[str, object]:
    """What the backend actually resolved — surfaced by /api/health."""
    conf = load_tv_conf()
    path = next((p for p in _candidate_paths() if p.is_file()), None)
    return {
        'path': str(path) if path else None,
        'tv_mode': profile_value('WLR_MODE') or profile_value('TVTV_MODE'),
        'tv_scale': profile_value('TV_SCALE'),
        'theme': profile_value('TV_THEME'),
        'cec': profile_value('TV_CEC'),
        'audio_passthrough': _flag('TV_AUDIO_PASSTHROUGH', False),
        'night_mode': _flag('TV_NIGHT_MODE', False),
        'web_remote': _flag('WEB_REMOTE', False),
        'camera_hub': _flag('CAMERA_HUB', False),
        'keys_loaded': sorted(conf.keys()),
    }
