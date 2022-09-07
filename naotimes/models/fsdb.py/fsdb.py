"""
MIT License

Copyright (c) 2019-2022 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

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
