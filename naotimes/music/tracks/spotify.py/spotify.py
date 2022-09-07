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
import time
from typing import List, Literal, Match, Optional, Tuple, Type, Union
from urllib.parse import urlparse

import aiohttp
import wavelink
from wavelink.ext.spotify import SpotifyClient, SpotifySearchType, SpotifyTrack
from wavelink.pool import Node
from wavelink.utils import MISSING

from naotimes.utils import complex_walk

from ..errors import SpotifyUnavailable, UnsupportedURLFormat
from ._types import SpotifyEpisodePayload, SpotifyTrackPayload

SPOTIFY_REGEX2 = re.compile(r"https://open\.spotify\.com/(?P<entity>.+)/(?P<identifier>.+)")

__all__ = (
    "SpotifyPartialTrack",
    "SpotifyDirectTrack",
)


class SpotifyPartialTrackFilled(wavelink.Track):
    internal_id: str
    extra_data: SpotifyTrackPayload
    _int_thumbnail: Optional[str]

    source: Literal["spotify"] = "spotify"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.direct_spotify: bool = True
        self.is_podcast: bool = False
        self.source = "spotify"

    def inject_data(self, payload: SpotifyTrackPayload):
        self.extra_data = payload
        self.internal_id = payload["id"]
        self._int_thumbnail = payload["image"]
        self.duration = payload["duration"]
        if self.is_podcast:
            self.author = payload.get("publisher") or "Unknown"
            self.description = payload.get("description") or "No description"
        else:
            self.author = ", ".join(payload.get("artists", [])) or "Unknown Artist"
            self.description = None

    @property
    def thumbnail(self):
        return self._int_thumbnail


class SpotifyPartialEpisodeFilled(SpotifyPartialTrackFilled):
    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.is_podcast: bool = True


class SpotifyPartialTrack(wavelink.PartialTrack):
    source: Literal["spotify"] = "spotify"

    def __init__(
        self,
        *,
        query: str,
        node: Optional[Node] = MISSING,
        cls: Optional[wavelink.Track] = MISSING,
        extra_info: SpotifyTrackPayload = MISSING,
    ):
        self.query: str = query
        self.title: str = query
        self._node: Node = node
        self._cls: wavelink.Track = cls

        self.extra_data = extra_info
        self.title = extra_info["title"]
        self.is_podcast = "show" in extra_info
        if self.is_podcast:
            self.author = extra_info.get("publisher") or "Unknown"
            self.description = extra_info.get("description") or "No description"
        else:
            self.author = ", ".join(extra_info.get("artists", [])) or "Unknown Artist"
            self.description = None
        self.duration = extra_info["duration"]
        self.uri = f"https://open.spotify.com/track/{extra_info['id']}"
        self.source = "spotify"

    def __str__(self):
        return self.title

    async def _search(self):
        node = self._node
        if node is MISSING:
            node = wavelink.NodePool.get_node()

        cls = SpotifyPartialTrackFilled
        if self.is_podcast:
            cls = SpotifyPartialEpisodeFilled

        tracks = await node.get_tracks(cls, query=self.query)
        first_track = tracks[0]
        first_track.inject_data(self.extra_data)
        return first_track


PartialResult = Union[
    SpotifyTrack,
    List[SpotifyTrack],
    List[SpotifyPartialTrack],
]


class SpotifyDirectTrack(SpotifyTrack, SpotifyPartialTrackFilled):
    """A track that implements a direct search track"""

    @staticmethod
    def _clean_url(url: str, append: str) -> str:
        if url.endswith("/"):
            url = url[:-1]
        if append.startswith("/"):
            append = append[1:]
        return f"{url}/{append}"

    async def _spotify_get_track_api(self, track_id: str, base_url: str) -> Optional[SpotifyTrackPayload]:
        fetch_url = self._clean_url(base_url, track_id)
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data")

    async def _spotify_get_playlist_api(
        self, playlist_id: str, base_url: str
    ) -> Optional[List[SpotifyTrackPayload]]:
        fetch_url = self._clean_url(base_url, f"playlist/{playlist_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data.tracks") or []

    async def _spotify_get_album_api(
        self, album_id: str, base_url: str
    ) -> Optional[List[SpotifyTrackPayload]]:
        fetch_url = self._clean_url(base_url, f"album/{album_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data.tracks") or []

    async def _spotify_get_episode_api(
        self, episode_id: str, base_url: str
    ) -> Optional[SpotifyEpisodePayload]:
        fetch_url = self._clean_url(base_url, f"episode/{episode_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data")

    async def _spotify_get_show_api(
        self, show_id: str, base_url: str
    ) -> Optional[List[SpotifyEpisodePayload]]:
        fetch_url = self._clean_url(base_url, f"show/{show_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data.episodes") or []

    async def _spotify_get_artist_top_api(
        self, artist_id: str, base_url: str
    ) -> Optional[List[SpotifyTrackPayload]]:
        fetch_url = self._clean_url(base_url, f"artist/{artist_id}")
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        return complex_walk(data, "data.tracks") or []

    def _build_track_url(self, track_id: str, spoti_url: str):
        return self._clean_url(spoti_url, f"{track_id}/listen")

    def _build_episode_url(self, episode_id: str, spoti_url: str):
        return self._clean_url(spoti_url, f"episode/{episode_id}/listen")

    def _match_spotify_url(url: str) -> Tuple[Optional[Match[str]], str]:
        if "open.spotify.com" not in url:
            return None, url

        parsed_url = urlparse(url)
        recreate_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        regex_res = SPOTIFY_REGEX2.match(recreate_url)
        return regex_res, recreate_url

    @classmethod
    async def search(
        cls: Type[SpotifyDirectTrack],
        query: str,
        *,
        type: SpotifySearchType = SpotifySearchType.track,
        node: Node = MISSING,
        spotify: SpotifyClient = MISSING,
        return_first: bool = False,
    ) -> Optional[Union[PartialResult, SpotifyDirectTrack, List[SpotifyDirectTrack]]]:
        if node is MISSING:
            node = wavelink.NodePool.get_node()

        if node._spotify is None and spotify is MISSING:
            raise SpotifyUnavailable

        spoti: SpotifyClient = node._spotify
        if spoti is None and spotify is not MISSING:
            spoti = spotify

        regex_res, new_query_url = cls._match_spotify_url(query)
        if not regex_res:
            raise UnsupportedURLFormat(query, "Link Spotify yang diberikan tidak valid!")

        entity: Literal["track", "album", "playlist"] = regex_res["entity"]
        identifier: str = regex_res["identifier"]

        spotify_url: Optional[str] = getattr(spoti, "_url_host", None)
        if spotify_url is None:
            # Use Youtube mirroring
            results = await SpotifyTrack.search(
                new_query_url + "?si=123", type=type, node=node, return_first=return_first
            )
            if not isinstance(results, list):
                results = [results]
            for res in results:
                setattr(res, "direct_spotify", False)
                setattr(res, "internal_id", identifier)
                setattr(res, "source", "youtube")
            return results

        if not spoti._bearer_token or time.time() > spoti._expiry:
            await spoti._get_bearer_token()

        is_podcast = False
        if entity == "track":
            results = await cls._spotify_get_track_api(cls, identifier, spotify_url)
            if results is None:
                return []

            track_url = cls._build_track_url(cls, results["id"], spotify_url)
            tracks = await node.get_tracks(cls, track_url)
            first_track = tracks[0]
            first_track.inject_data(results)
            return first_track
        elif entity == "episode":
            results = await cls._spotify_get_episode_api(cls, identifier, spotify_url)
            if results is None:
                return []
            episode_url = cls._build_episode_url(cls, results["id"], spotify_url)
            tracks = await node.get_tracks(cls, episode_url)
            first_track = tracks[0]
            first_track.is_podcast = True
            first_track.inject_data(results)
            return first_track
        elif entity == "album":
            results = await cls._spotify_get_album_api(cls, identifier, spotify_url)
        elif entity == "playlist":
            results = await cls._spotify_get_playlist_api(cls, identifier, spotify_url)
        elif entity == "show":
            results = await cls._spotify_get_show_api(cls, identifier, spotify_url)
            is_podcast = True
        elif entity == "artist":
            results = await cls._spotify_get_artist_top_api(cls, identifier, spotify_url)
        else:
            raise UnsupportedURLFormat(query, "Tipe URL Spotify tersebut tidak dapat disupport!")

        merged_tracks: List[SpotifyPartialTrack] = []
        for track in results:
            if is_podcast:
                query_new = cls._build_episode_url(cls, track["id"], spotify_url)
            else:
                query_new = cls._build_track_url(cls, track["id"], spotify_url)
            partial_track_search = SpotifyPartialTrack(
                query=query_new,
                node=node,
                extra_info=track,
            )
            merged_tracks.append(partial_track_search)
        return merged_tracks
