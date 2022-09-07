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
from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Literal, Match, Optional, Tuple, Type, Union
from urllib.parse import urlparse

import aiohttp
import wavelink

from naotimes.utils import complex_walk

from ..errors import TidalUnavailable, UnsupportedURLFormat
from ._types import TidalTrackPayload
from .util import MISSING

if TYPE_CHECKING:
    from wavelink import Node
    from wavelink.ext.spotify import SpotifyClient

TIDAL_REGEX = re.compile(r"https:\/\/(www\.)?tidal\.com\/(browse\/)?(?P<entity>.+)\/(?P<identifier>.+)")

__all__ = (
    "TidalDirectLink",
    "TidalPartialTrack",
)


class TidalPartialTrackFilled(wavelink.Track):
    internal_id: str
    extra_data: TidalTrackPayload
    _int_thumbnail: Optional[str]

    source: Literal["tidal"] = "tidal"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.source = "tidal"

    def inject_data(self, payload: TidalTrackPayload):
        self.extra_data = payload
        self.internal_id = payload["id"]
        self._int_thumbnail = payload.get("image")
        self.duration = payload["duration"]
        self.author = ", ".join(payload.get("artists", [])) or "Unknown Artist"

    @property
    def thumbnail(self):
        return self._int_thumbnail


class TidalPartialTrack(wavelink.PartialTrack):
    source: Literal["tidal"] = "tidal"

    def __init__(
        self,
        *,
        query: str,
        node: Optional[Node] = MISSING,
        cls: Optional[wavelink.Track] = MISSING,
        extra_info: TidalPartialTrack = MISSING,
    ):
        self.query: str = query
        self.title: str = query
        self._node: Node = node
        self._cls: wavelink.Track = cls

        self.extra_data = extra_info
        self.title = extra_info["title"]
        self.author = ", ".join(extra_info.get("artists", [])) or "Unknown Artist"
        self.duration = extra_info["duration"]
        self.uri = f"https://tidal.com/browse/track/{extra_info['id']}"
        self.source = "tidal"

    def __str__(self) -> str:
        return self.title

    async def _search(self):
        node = self._node
        if node is MISSING:
            node = wavelink.NodePool.get_node()

        cls = TidalPartialTrackFilled
        tracks = await node.get_tracks(cls, query=self.query)
        first_track = tracks[0]
        first_track.inject_data(self.extra_data)
        return first_track


TidalPartialResult = Union[TidalPartialTrack, List[TidalPartialTrack]]


class TidalDirectLink(TidalPartialTrackFilled):
    """A track that implements a direct Tidal link track"""

    @staticmethod
    def _clean_url(url: str, append: str) -> str:
        if url.endswith("/"):
            url = url[:-1]
        if append.startswith("/"):
            append = append[1:]
        return f"{url}/{append}"

    async def _tidal_get_track_api(self, track_id: str, base_url: str) -> Optional[TidalTrackPayload]:
        fetch_url = self._clean_url(base_url, f"tidal/{track_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data")

    async def _tidal_get_playlist_api(
        self, playlist_id: str, base_url: str
    ) -> Optional[List[TidalTrackPayload]]:
        fetch_url = self._clean_url(base_url, f"tidal/playlist/{playlist_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data.tracks") or []

    async def _tidal_get_album_api(self, album_id: str, base_url: str) -> Optional[List[TidalTrackPayload]]:
        fetch_url = self._clean_url(base_url, f"tidal/album/{album_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data.tracks") or []

    def _build_track_url(self, track_id: str, base_url: str):
        return self._clean_url(base_url, f"tidal/{track_id}/listen")

    def _match_tidal_url(url: str) -> Tuple[Optional[Match[str]], str]:
        if "tidal.com" not in url:
            return None, url

        parsed_url = urlparse(url)
        recreate_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        regex_res = TIDAL_REGEX.match(recreate_url)
        return regex_res, recreate_url

    @classmethod
    async def search(
        cls: Type[TidalDirectLink],
        query: str,
        *,
        node: Node = MISSING,
    ) -> Optional[Union[TidalPartialResult, TidalDirectLink, List[TidalDirectLink]]]:
        if node is MISSING:
            node = wavelink.NodePool.get_node()

        if node._spotify is None:
            raise TidalUnavailable

        spoti: SpotifyClient = node._spotify
        if spoti is None:
            raise TidalUnavailable

        url_host: Optional[str] = getattr(spoti, "_url_host", None)
        if url_host is None:
            raise TidalUnavailable

        regex_res, new_query_url = cls._match_tidal_url(query)
        if not regex_res:
            raise UnsupportedURLFormat(query, "Link Tidal yang diberikan tidak valid!")

        entity: Literal["track", "playlist", "album"] = regex_res["entity"]
        identifier: str = regex_res["identifier"]

        if entity == "track":
            results = await cls._tidal_get_track_api(cls, identifier, url_host)
            if results is None:
                return []

            track_url = cls._build_track_url(cls, results["id"], url_host)
            tracks = await node.get_tracks(cls, track_url)
            first_track = tracks[0]
            first_track.inject_data(results)
            return first_track
        elif entity == "playlist":
            results = await cls._tidal_get_playlist_api(cls, identifier, url_host)
        elif entity == "album":
            results = await cls._tidal_get_album_api(cls, identifier, url_host)
        else:
            raise UnsupportedURLFormat(query, "Tipe URL Tidal tersebut tidak dapat disupport!")

        merged_tracks: List[TidalPartialTrack] = []
        for track in results:
            query_new = cls._build_track_url(cls, track["id"], url_host)
            partial_track = TidalPartialTrack(
                query=query_new,
                node=node,
                extra_info=track,
            )
            merged_tracks.append(partial_track)
        return merged_tracks
