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

from typing import Literal

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
    title_alt: str | None
    type: ShowType
    episodes: str | None
    start_air: str | None
    end_air: str | None
    season_id: int
    broadcast: str | None
    synopsis: str | None
    image: str
    anime_season: FSDBAnimeSeasonData | None
    genre: list[FSDBAnimeInfoContentData] | None
    studio: list[FSDBAnimeInfoContentData] | None


class FSDBFansubData(AttributeDict):
    id: int
    name: str
    alt: str | None
    type: FansubType
    description: str | None
    status: FansubStatus
    website: str | None
    facebook: str | None
    instagram: str | None
    twitter: str | None
    youtube: str | None
    discord: str | None
    rss: str | None


class FSDBProjectData(AttributeDict):
    id: int
    flag: str | None
    type: ProjectReleaseType
    subtitle: ProjectSubType
    status: ProjectStatus
    url: str | None
    misc: str | None
    anime: FSDBAnimeData | None
    fansub: list[FSDBFansubData] | None
