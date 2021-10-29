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
