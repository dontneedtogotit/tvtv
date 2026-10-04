from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'backend'))

from media import Series, Episode

def test_series_episode_models():
    e1 = Episode(id="e1", series_id="s1", season_number=1, episode_number=1, title="Pilot")
    s1 = Series(id="s1", title="Test Series", episodes=[e1])
    
    assert s1.episodes[0].title == "Pilot"
    assert s1.episodes[0].watched == False
    assert s1.next_air_date == None
    print("ALL TESTS PASSED")

if __name__ == "__main__":
    test_series_episode_models()
