
from pydantic import BaseModel
from typing import Optional, List

class Episode(BaseModel):
    id: str
    series_id: str
    season_number: int
    episode_number: int
    title: str
    overview: Optional[str] = None
    air_date: Optional[str] = None
    watched: bool = False

class Series(BaseModel):
    id: str
    title: str
    overview: Optional[str] = None
    poster: Optional[str] = None
    episodes: List[Episode] = []
    next_air_date: Optional[str] = None
