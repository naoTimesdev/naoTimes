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

from typing import List, Literal, Optional, Union

from naotimes.utils import AttributeDict

__all__ = ("NHDoujinInfo", "NHQueryInfo", "NHQuerySearch", "NHQueryLatest")

ImageType = Literal["image", "thumbnail"]


class _NHPageInfo(AttributeDict):
    total: int


class _NHDoujinTitleInfo(AttributeDict):
    simple: Optional[str]
    english: Optional[str]
    japanese: Optional[str]


class _NHDoujinImageInfo(AttributeDict):
    type: ImageType
    url: str
    original_url: str
    sizes: List[int]


class _NHDoujinTagBase(AttributeDict):
    name: str
    amount: int


class _NHDoujinTagCollection(AttributeDict):
    artists: List[_NHDoujinTagBase]
    characters: List[_NHDoujinTagBase]
    categories: List[_NHDoujinTagBase]
    groups: List[_NHDoujinTagBase]
    languages: List[_NHDoujinTagBase]
    parodies: List[_NHDoujinTagBase]
    tags: List[_NHDoujinTagBase]


class NHDoujinInfo(AttributeDict):
    id: Union[str, int]
    media_id: str
    title: _NHDoujinTitleInfo
    cover_art: _NHDoujinImageInfo
    tags: _NHDoujinTagCollection
    images: List[_NHDoujinImageInfo]
    url: str
    publishedAt: str
    favorites: int
    total_pages: int


class _NHQuerySearchResult(AttributeDict):
    results: List[NHDoujinInfo]
    pageInfo: _NHPageInfo


class NHQueryInfo(AttributeDict):
    info: NHDoujinInfo


class NHQuerySearch(AttributeDict):
    search: _NHQuerySearchResult


class NHQueryLatest(AttributeDict):
    latest: _NHQuerySearchResult
