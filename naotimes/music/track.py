"""
MIT License

Copyright (c) 2019-2021 naoTimesdev

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

This implements some extra tracks for the music player.
"""

from __future__ import annotations

import time
from typing import List, Literal, Optional, Type, Union
from urllib.parse import quote_plus

import aiohttp
import wavelink
from wavelink.ext.spotify import URLREGEX as SPOTIFY_REGEX
from wavelink.ext.spotify import SpotifyClient, SpotifySearchType, SpotifyTrack
from wavelink.pool import Node
from wavelink.utils import MISSING

from naotimes.utils import complex_walk

from ._types import SpotifyTrackPayload
from .errors import SpotifyUnavailable, UnsupportedURLFormat

__all__ = (
    "YoutubeDirectLinkTrack",
    "TwitchDirectLink",
    "SoundcloudDirectLink",
    "BandcampDirectLink",
    "SpotifyPartialTrack",
    "SpotifyPartialTrackFilled",
    "SpotifyDirectTrack",
)


def _parse_playlist(data: dict):
    tracks = data["tracks"]
    return tracks


class YoutubeDirectLinkTrack(wavelink.YouTubeTrack):
    """A track that implements a direct search track"""

    _int_thumbnail: str
    source: Literal["youtube"] = "youtube"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.source = "youtube"

    @classmethod
    async def search(
        cls: Type[YoutubeDirectLinkTrack], query: str, *, node: Node = MISSING, return_first: bool = False
    ) -> Union[YoutubeDirectLinkTrack, List[YoutubeDirectLinkTrack]]:
        """Search for a track on YouTube"""

        if node is MISSING:
            node = wavelink.NodePool.get_node()

        is_ytmusic = "music.youtube" in query.lower()

        is_playlist = False
        if "/playlist" in query:
            is_playlist = True

        if is_playlist:
            playlists_data = []
            playlist_append = lambda x: playlists_data.extend(_parse_playlist(x))  # noqa: E731

            await node.get_playlist(playlist_append, query)
            parsed_tracks = [cls(track["track"], track["info"]) for track in playlists_data]
            for track in parsed_tracks:
                video_id = track.identifier
                if is_ytmusic:
                    setattr(track, "_int_thumbnail", f"https://naotimes-og.glitch.me/ytm/{video_id}")
                else:
                    setattr(track, "_int_thumbnail", f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
            if return_first:
                parsed_tracks[0]
            return parsed_tracks

        tracks = await node.get_tracks(cls, query)
        for track in tracks:
            video_id = track.identifier
            if is_ytmusic:
                setattr(track, "_int_thumbnail", f"https://naotimes-og.glitch.me/ytm/{video_id}")
            else:
                setattr(track, "_int_thumbnail", f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
        if return_first:
            return tracks[0]
        return tracks


class TwitchDirectLink(wavelink.Track):
    """A track that implements a direct link fetch of Twitch.tv stream"""

    _int_thumbnail: str
    source: Literal["twitch"] = "twitch"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.source = "twitch"

    @classmethod
    async def search(
        cls: Type[TwitchDirectLink], query: str, *, node: Node = MISSING, return_first: bool = False
    ) -> Union[TwitchDirectLink, List[TwitchDirectLink]]:
        """Search for a track on YouTube"""

        if node is MISSING:
            node = wavelink.NodePool.get_node()

        tracks = await node.get_tracks(cls, query)
        for track in tracks:
            author = track.author
            setattr(track, "_int_thumbnail", f"https://ttvthumb.glitch.me/{author}")
        if return_first:
            return tracks[0]
        return tracks


class SoundcloudDirectLink(wavelink.Track):
    """A track that implements a direct link fetch of Soundcloud"""

    _int_thumbnail: str
    source: Literal["soundcloud"] = "soundcloud"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)

        replace_url = info["uri"].replace("https://", "").replace("http://", "")
        find_first_slash = replace_url.find("/")
        replace_url = replace_url[find_first_slash:]

        self._int_thumbnail = f"https://naotimes-og.glitch.me/soundcloud{replace_url}"
        self.source = "soundcloud"

    @classmethod
    async def search(
        cls: Type[SoundcloudDirectLink], query: str, *, node: Node = MISSING, return_first: bool = False
    ) -> Union[SoundcloudDirectLink, List[SoundcloudDirectLink]]:
        """Search for a track on Soundcloud"""

        if node is MISSING:
            node = wavelink.NodePool.get_node()

        is_playlist = False
        if "/sets/" in query:
            is_playlist = True

        if is_playlist:
            playlists_data = []
            playlist_append = lambda x: playlists_data.extend(_parse_playlist(x))  # noqa: E731

            await node.get_playlist(playlist_append, query)
            parsed_tracks = [cls(track["track"], track["info"]) for track in playlists_data]
            if return_first:
                parsed_tracks[0]
            return parsed_tracks

        tracks = await node.get_tracks(cls, query)
        if return_first:
            return tracks[0]
        return tracks


class BandcampDirectLink(wavelink.Track):
    """A track that implements a direct link fetch of Bandcamp"""

    _int_thumbnail: str
    source: Literal["bandcamp"] = "bandcamp"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        encoded_url = quote_plus(info["uri"])

        self._int_thumbnail = f"https://naotimes-og.glitch.me/bandcampthumb?url={encoded_url}"
        self.source = "bandcamp"

    @classmethod
    async def search(
        cls: Type[SoundcloudDirectLink], query: str, *, node: Node = MISSING, return_first: bool = False
    ) -> Union[BandcampDirectLink, List[BandcampDirectLink]]:
        """Search for a track on Bandcamp"""

        if node is MISSING:
            node = wavelink.NodePool.get_node()

        is_playlist = False
        if "/album/" in query:
            is_playlist = True

        if is_playlist:
            playlists_data = []
            playlist_append = lambda x: playlists_data.extend(_parse_playlist(x))  # noqa: E731

            await node.get_playlist(playlist_append, query)
            parsed_tracks = [cls(track["track"], track["info"]) for track in playlists_data]
            if return_first:
                parsed_tracks[0]
            return parsed_tracks

        tracks = await node.get_tracks(cls, query)
        if return_first:
            return tracks[0]
        return tracks


class SpotifyPartialTrackFilled(wavelink.Track):
    internal_id: str
    extra_data: SpotifyTrackPayload
    _int_thumbnail: Optional[str]

    source: Literal["spotify"] = "spotify"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.direct_spotify: bool = True
        self.source = "spotify"

    def inject_data(self, payload: SpotifyTrackPayload):
        self.extra_data = payload
        self.internal_id = payload["id"]
        self._int_thumbnail = payload["image"]
        self.duration = payload["duration"]

    @property
    def thumbnail(self):
        return self._int_thumbnail


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
        self.author = ", ".join(extra_info.get("artists", [])) or "Unknown Artist"
        self.duration = extra_info["duration"]
        self.source = "spotify"

    def __str__(self):
        return self.title

    async def _search(self):
        node = self._node
        if node is MISSING:
            node = wavelink.NodePool.get_node()

        tracks = await node.get_tracks(SpotifyPartialTrackFilled, query=self.query)
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

    def _build_track_url(self, track_id: str, spoti_url: str):
        return self._clean_url(spoti_url, f"{track_id}/listen")

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

        regex_res = SPOTIFY_REGEX.match(query)
        if not regex_res:
            raise UnsupportedURLFormat(query, "Unable to match the URL to another Spotify URL.")

        entity: Literal["track", "album", "playlist"] = regex_res["entity"]
        identifier: str = regex_res["identifier"]

        spotify_url: Optional[str] = getattr(spoti, "_url_host", None)
        if spotify_url is None:
            # Use Youtube mirroring
            results = await SpotifyTrack.search(query, type=type, node=node, return_first=return_first)
            if not isinstance(results, list):
                results = [results]
            for res in results:
                setattr(res, "direct_spotify", False)
                setattr(res, "internal_id", identifier)
                setattr(res, "source", "youtube")
            return results

        if not spoti._bearer_token or time.time() > spoti._expiry:
            await spoti._get_bearer_token()

        if entity == "track":
            results = await cls._spotify_get_track_api(cls, identifier, spotify_url)
            if results is None:
                return []

            track_url = cls._build_track_url(cls, results["id"], spotify_url)
            tracks = await node.get_tracks(cls, track_url)
            first_track = tracks[0]
            first_track.inject_data(results)
            return first_track
        elif entity == "album":
            results = await cls._spotify_get_album_api(cls, identifier, spotify_url)
        elif entity == "playlist":
            results = await cls._spotify_get_playlist_api(cls, identifier, spotify_url)
        else:
            raise UnsupportedURLFormat(query, "Tipe URL Spotify tersebut tidak dapat disupport!")

        merged_tracks: List[SpotifyPartialTrack] = []
        for track in results:
            query_new = cls._build_track_url(cls, track["id"], spotify_url)
            partial_track_search = SpotifyPartialTrack(
                query=query_new,
                node=node,
                extra_info=track,
            )
            merged_tracks.append(partial_track_search)
        return merged_tracks
