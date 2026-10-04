"""Unit tests for Phase 18 Config Validation."""
from __future__ import annotations
import sys
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

from config_validator import validate_tv_conf, validate_settings

def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        sys.exit(1)

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Valid tv.conf
        good_conf = tmp / "good_tv.conf"
        good_conf.write_text('export TV_THEME="estuary"\nexport WLR_MODE="1920x1080@60"\n')
        errors = validate_tv_conf(good_conf)
        check('Valid tv.conf passes', len(errors) == 0, str(errors))

        # Invalid key
        bad_conf = tmp / "bad_tv.conf"
        bad_conf.write_text('export UNKNOWN_KEY="x"\nexport TV_THEME="estuary"\n')
        errors = validate_tv_conf(bad_conf)
        check('Invalid tv.conf key detected', len(errors) == 1 and 'UNKNOWN_KEY' in errors[0])

        # Valid settings.json
        good_settings = tmp / "good_settings.json"
        good_settings.write_text(json.dumps({"sponsorblock": True, "firewall_posture": "kiosk"}))
        errors = validate_settings(good_settings)
        check('Valid settings.json passes', len(errors) == 0, str(errors))

        # Invalid firewall_posture
        bad_settings = tmp / "bad_settings.json"
        bad_settings.write_text(json.dumps({"firewall_posture": "invalid"}))
        errors = validate_settings(bad_settings)
        check('Invalid firewall_posture detected', len(errors) == 1 and 'firewall_posture' in errors[0])

        # Invalid JSON
        broken = tmp / "broken.json"
        broken.write_text("{not valid json")
        errors = validate_settings(broken)
        check('Broken JSON detected', len(errors) == 1 and 'invalid JSON' in errors[0])

    return 0

if __name__ == '__main__':
    sys.exit(main())
