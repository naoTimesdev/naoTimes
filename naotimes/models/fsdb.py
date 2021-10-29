from typing import List, Literal, Optional

from naotimes.utils import AttributeDict

ShowType = Literal["TV", "Movie", "ONA", "OVA", "Special"]
FansubType = Literal["Anime", "Drama", "Tokusatsu", "Manga"]
FansubStatus = Literal["Aktif", "Nonaktif"]
ProjectReleaseType = Literal["TV", "BD", "Web-DL", "DVD"]
ProjectSubType = Literal["Softsub", "Semi-Hardsub", "Hardsub"]
ProjectStatus = Literal["Jalan", "Tamat", "Tentatif", "Drop"]


__all__ = ("FSDBAnimeData", "FSDBFansubData", "FSDBProjectData")


class FSDBAnimeSeasonData(AttributeDict):
    id: int
    year: str
    season: str
    name: str
    sort: str
    status: bool


class _FSDBAnimePivotData(AttributeDict):
    anime_id: int
    genre_id: int


class FSDBAnimeInfoContentData(AttributeDict):
    id: int
    name: str
    type: str
    pivot: _FSDBAnimePivotData


class FSDBAnimeData(AttributeDict):
    id: int
    mal_id: str
    title: str
    title_alt: Optional[str]
    type: ShowType
    episodes: Optional[str]
    start_air: Optional[str]
    end_air: Optional[str]
    season_id: int
    broadcast: Optional[str]
    synopsis: Optional[str]
    image: str
    anime_season: Optional[FSDBAnimeSeasonData]
    genre: Optional[List[FSDBAnimeInfoContentData]]
    studio: Optional[List[FSDBAnimeInfoContentData]]


class FSDBFansubData(AttributeDict):
    id: int
    name: str
    alt: Optional[str]
    type: FansubType
    description: Optional[str]
    status: FansubStatus
    website: Optional[str]
    facebook: Optional[str]
    instagram: Optional[str]
    twitter: Optional[str]
    youtube: Optional[str]
    discord: Optional[str]
    rss: Optional[str]


class FSDBProjectData(AttributeDict):
    id: int
    flag: Optional[str]
    type: ProjectReleaseType
    subtitle: ProjectSubType
    status: ProjectStatus
    url: Optional[str]
    misc: Optional[str]
    anime: Optional[FSDBAnimeData]
    fansub: Optional[List[FSDBFansubData]]
