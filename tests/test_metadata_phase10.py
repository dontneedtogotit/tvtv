"""Unit tests for Phase 10 Library Metadata Providers."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

from metadata_providers import TMDBProvider

def check(label: str, ok: bool, detail: str = '') -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ''))
    if not ok:
        sys.exit(1)

def main() -> int:
    # We can't actually call TMDB without a real key.
    # We test that the provider is initialized as 'disabled' if no key is set.
    provider = TMDBProvider()
    check('TMDB disabled if no key', provider.enabled is False)
    
    # Test lookup returns None if disabled
    check('TMDB lookup disabled', provider.lookup('Test Movie') is None)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
