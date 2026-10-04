"""P18-5: Config schema validation for tv.conf and settings.json."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

VALID_TV_CONF_KEYS = {
    "TV_USER", "WLR_OUTPUT", "WLR_MODE", "TV_SCALE", "TV_FONT_SIZE",
    "TV_AUDIO", "TV_NIGHT_MODE", "TV_CEC", "TV_THEME", "TV_SHELL",
    "TV_AUDIO_PASSTHROUGH", "TV_WALLPAPER", "MPV_VO", "MPV_HWDEC",
    "MPV_SCALE", "KIOSK_URL", "TVTV_MODE",
}

VALID_SETTINGS_KEYS = {
    "sponsorblock", "default_quality", "tv_mode", "firewall_posture",
    "theme", "ui_scale",
}


def validate_tv_conf(path: Path | None = None) -> list[str]:
    """Validate a tv.conf file. Returns a list of error messages (empty = valid)."""
    if path is None:
        path = ROOT / "config" / "tv.conf"
    errors: list[str] = []
    if not path.exists():
        return errors  # absent is valid

    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'export\s+([A-Z_]+)=["\']?(.*)["\']?', line)
        if not m:
            errors.append(f"{path}:{i}: not an export line: {line!r}")
            continue
        key = m.group(1)
        if key not in VALID_TV_CONF_KEYS:
            errors.append(f"{path}:{i}: unknown key '{key}'")
    return errors


def validate_settings(path: Path | None = None) -> list[str]:
    """Validate settings.json. Returns a list of error messages (empty = valid)."""
    if path is None:
        path = ROOT / "config" / "settings.json"
    errors: list[str] = []
    if not path.exists():
        return errors

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"{path}: invalid JSON: {e}"]

    if not isinstance(data, dict):
        return [f"{path}: root is not an object"]

    for key in data:
        if key not in VALID_SETTINGS_KEYS:
            errors.append(f"{path}: unknown key '{key}'")

    # Type checks
    if "firewall_posture" in data and data["firewall_posture"] not in ("kiosk", "open"):
        errors.append(f"{path}: firewall_posture must be 'kiosk' or 'open', got {data['firewall_posture']!r}")

    return errors


def validate_all() -> list[str]:
    """Validate all config files. Returns list of all errors."""
    errors = validate_tv_conf()
    errors.extend(validate_settings())
    return errors
