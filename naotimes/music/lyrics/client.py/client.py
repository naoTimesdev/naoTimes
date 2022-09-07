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

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, overload

import aiohttp
import wavelink

from naotimes.music.lyrics.genius import GeniusAPI
from naotimes.music.lyrics.musixmatch import MusixmatchClient
from naotimes.music.lyrics.netease import NetEaseClient, parse_netease_lrc
from naotimes.music.tracks.bandcamp import BandcampDirectLink
from naotimes.music.tracks.soundcloud import SoundcloudDirectLink
from naotimes.music.tracks.tidal import TidalDirectLink
from naotimes.music.tracks.twitch import TwitchDirectLink
from naotimes.utils import complex_walk

from ..tracks import SingleTrackResult, SpotifyDirectTrack

__all__ = (
    "LyricFetchResult",
    "LyricSource",
    "naoTimesLyricsClient",
    "naoTimesLyricsConfig",
    "naoTimesLyricsResult",
)


@dataclass
class naoTimesLyricsConfig:
    musixmatch_api_key: Optional[str] = None
    genius_client: Optional[str] = None
    genius_key: Optional[str] = None


class LyricSource(Enum):
    SPOTIFY = "spotify"
    GENIUS = "genius"
    MUSIXMATCH = "musixmatch"
    QQ = "qq"
    AZLYRICS = "azlyrics"
    NETEASE = "netease"


class LyricFetchResult(Enum):
    Success = 0
    NotFound = 1
    Unsupported = 2

    def to_string(self) -> str:
        if self.value == 0:
            return "Success"
        elif self.value == 1:
            return "Tidak dapat hasil"
        elif self.value == 2:
            return "Source tidak didukung"
        return "Terjadi kesalahan internal!"


@dataclass
class naoTimesLyricProxy:
    url: str
    method: str
    title: str
    parser: Callable[[Any, int], List[str]] = None


@dataclass
class naoTimesLyricsResult:
    lyrics: Union[List[str], naoTimesLyricProxy]
    title: str
    source: LyricSource


def parse_mxm_lyrics(data: dict, _: int) -> List[str]:
    status_code = complex_walk(data, "message.header.status_code")
    if status_code != 200:
        return ["Unable to fetch lyrics from Musixmatch"]
    lyrics = complex_walk(data, "message.body.lyrics.lyrics_body")
    if not lyrics:
        return ["Unable to fetch lyrics from Musixmatch"]
    return lyrics.split("\n")


def parse_netease_lyrics(data: dict, _: int) -> List[str]:
    actual_lrc = complex_walk(data, "lrc.lyric")
    if not actual_lrc:
        return ["Unable to fetch lyrics from NetEase"]
    return parse_netease_lrc(actual_lrc)


class naoTimesLyricsClient:
    def __init__(self, config: naoTimesLyricsConfig, session: aiohttp.ClientSession = None):
        self.__config = config
        self._outside_session = True
        self._session = session
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"  # noqa
                }
            )
            self._outside_session = False
        self.logger = logging.getLogger("naoTimes.LyricsClient")

        self._genius: GeniusAPI = None
        self._mxm: MusixmatchClient = None
        self._netease = NetEaseClient(self._session)

    async def initialize(self, genius_token: Optional[str] = None):
        if self.__config.genius_client:
            self._genius = GeniusAPI(self.__config.genius_client, self.__config.genius_key, self._session)
            if genius_token is not None:
                self._genius._token = genius_token
            await self._genius.authorize()
        if self.__config.musixmatch_api_key:
            self._mxm = MusixmatchClient(self.__config.musixmatch_api_key, self._session)

    async def close(self):
        """
        Closes the session
        """
        if self._genius is not None:
            await self._genius.close()
        if self._mxm is not None:
            await self._mxm.close()
        await self._netease.close()
        if not self._outside_session:
            await self._session.clsoe()

    def _default_parser(self, data: str, _: int) -> List[str]:
        return data.split("\n")

    @property
    def config(self):
        return self.__config

    def get_spotilava_host(self) -> Optional[str]:
        nodes: Dict[str, wavelink.Node] = wavelink.NodePool._nodes
        for node_data in nodes.values():
            if node_data._spotify is None:
                continue
            spotify_url = getattr(node_data._spotify, "_url_host", None)
            if spotify_url is not None:
                return spotify_url
        return None

    @staticmethod
    def _clean_url(url: str, append: str) -> str:
        if url.endswith("/"):
            url = url[:-1]
        if append.startswith("/"):
            append = append[1:]
        return f"{url}/{append}"

    async def _genius_search(
        self, track: SingleTrackResult, force_query: Optional[str] = None
    ) -> List[naoTimesLyricsResult]:
        self.logger.info(f"GeniusLyrics: Searching for {track.title}")
        if self._genius is None:
            self.logger.warning(f"GeniusLyrics<{track.id}>: Not configured!")
            return []

        search_query = f"{track.author} - {track.title}"
        if getattr(track, "source", None) == "youtube":
            search_query = track.title
        search_query = force_query or search_query

        results, error_msg = await self._genius.find_lyrics(search_query)
        if error_msg is not None:
            self.logger.error(f"GeniusLyrics<{track.id}>: {error_msg}")
            return []
        as_proxy_lyrics: List[naoTimesLyricsResult] = []
        for result in results:
            song_path = result.path
            if song_path.startswith("/"):
                song_path = song_path[1:]
            genius_http = f"https://naotimes-og.glitch.me/lyrics/{song_path}"
            as_proxy_lyrics.append(
                naoTimesLyricsResult(
                    naoTimesLyricProxy(genius_http, "GET", result.title, parse_mxm_lyrics),
                    result.title,
                    LyricSource.GENIUS,
                )
            )
        return as_proxy_lyrics

    async def _musixmatch_search(
        self, track: SingleTrackResult, force_query: Optional[str] = None
    ) -> List[naoTimesLyricsResult]:
        self.logger.info(f"MusixmatchLyrics: Searching for {track.title}")
        if self._mxm is None:
            self.logger.warning(f"MusixmatchLyrics<{track.id}>: Not configured!")
            return []

        valid_track_artist = (
            BandcampDirectLink,
            SoundcloudDirectLink,
            TidalDirectLink,
        )

        track_title = force_query or track.title
        track_artist = None
        if isinstance(track, valid_track_artist):
            track_artist = track.author

        results = await self._mxm.search(track_title, track_artist)
        if not results:
            self.logger.error(f"MusixmatchLyrics<{track.id}>: No results!")
            return []

        as_proxy_lyrics: List[naoTimesLyricsResult] = []
        for result in results:
            as_proxy_lyrics.append(
                naoTimesLyricsResult(
                    naoTimesLyricProxy(result.request_url, "GET", result.title),
                    result.title,
                    LyricSource.MUSIXMATCH,
                )
            )
        return as_proxy_lyrics

    async def _qq_music_search(
        self, track: SingleTrackResult, force_query: Optional[str] = None
    ) -> List[naoTimesLyricsResult]:
        self.logger.info(f"QQMusicLyrics: Searching for {track.title}")
        return []

    async def _netease_search(
        self, track: SingleTrackResult, force_query: Optional[str] = None
    ) -> List[naoTimesLyricsResult]:
        self.logger.info(f"NeteaseLyrics: Searching for {track.title}")

        valid_track_artist = (
            BandcampDirectLink,
            SoundcloudDirectLink,
            TidalDirectLink,
        )

        track_title = track.title
        track_artist = None
        if isinstance(track, valid_track_artist):
            track_artist = track.author

        from_track = track_title
        if track_artist:
            from_track = f"{track_artist} {track_title}"
        query_search = force_query or from_track
        results = await self._netease.search(query_search)
        if not results:
            self.logger.error(f"NeteaseLyrics<{track.id}>: No results!")
            return []

        as_proxy_lyrics: List[naoTimesLyricsResult] = []
        for result in results:
            netease_lrc = f"{self._netease.BASE_URL}/song/lyric?tv=-1&kv=-1&lv=-1&os=pc&id={result.track_id}"
            as_proxy_lyrics.append(
                naoTimesLyricsResult(
                    naoTimesLyricProxy(netease_lrc, "GET", result.title, parse_netease_lyrics),
                    result.title,
                    LyricSource.NETEASE,
                )
            )
        return as_proxy_lyrics

    async def _multi_lyrics_search(
        self, track: SingleTrackResult, force_query: Optional[str] = None
    ) -> List[naoTimesLyricsResult]:
        self.logger.info("MultiLyrics: Initiating multiple coroutines searches...")
        genius_coro = self._genius_search(track, force_query)
        mxm_coro = self._musixmatch_search(track, force_query)
        qqm_coro = self._qq_music_search(track, force_query)
        netease_coro = self._netease_search(track, force_query)
        lyrics_fut = asyncio.gather(genius_coro, mxm_coro, qqm_coro, netease_coro)
        self.logger.info("MultiLyrics: Executing coroutines futures...")
        genius_res, mxm_result, qqm_result, netease_result = await lyrics_fut
        # Merge result and return
        lyrics_results = genius_res + mxm_result + qqm_result + netease_result
        self.logger.info(f"MultiLyrics: Found {len(lyrics_results)} results from multiple sources!")
        return lyrics_results

    async def _spotify_lyrics_search(self, track: SpotifyDirectTrack):
        if not track.direct_spotify:
            self.logger.warning("SpotifyLyrics: Not using custom spotify player!")
            return await self._multi_lyrics_search(track)

        track_id = track.internal_id
        spotify_url = self.get_spotilava_host()
        if spotify_url is None:
            self.logger.warning(f"SpotifyLyrics<{track_id}>: Internal Spotify URL cannot be found!")
            return await self._multi_lyrics_search(track)
        fetch_url = self._clean_url(spotify_url, f"{track_id}/lyrics")
        async with self._session.get(fetch_url, headers={"User-Agent": "naoTimesLyrics/1.0"}) as resp:
            if resp.status != 200:
                self.logger.warning(
                    f"SpotifyLyrics<{track_id}>: Cannot fetch lyrics from Spotify! ({resp.status})"
                )
                return await self._multi_lyrics_search(track)
            data = await resp.json()

        split_lyrics = data["data"]
        return [naoTimesLyricsResult(split_lyrics, track.title, LyricSource.SPOTIFY)]

    async def find_lyrics(
        self, track: SingleTrackResult, force_query: Optional[str] = None
    ) -> Tuple[List[naoTimesLyricsResult], LyricFetchResult]:
        not_supported = (TwitchDirectLink,)

        if isinstance(track, not_supported):
            self.logger.warning(f"Lyrics<{track.id}>: Not supported!")
            return [], LyricFetchResult.Unsupported

        if isinstance(track, SpotifyDirectTrack):
            results = await self._spotify_lyrics_search(track)
            success_status = LyricFetchResult.Success
            if len(results) < 1:
                success_status = LyricFetchResult.NotFound
            return results, success_status

        return await self._multi_lyrics_search(track, force_query)

    @overload
    async def lookup_lyrics(self, proxy_lyric: List[str]) -> List[str]:
        ...

    @overload
    async def lookup_lyrics(self, proxy_lyric: naoTimesLyricProxy) -> List[str]:
        ...

    async def lookup_lyrics(self, proxy_lyric: Union[List[str], naoTimesLyricProxy]) -> List[str]:
        if isinstance(proxy_lyric, list):
            return proxy_lyric

        async with self._session.request(proxy_lyric.method, proxy_lyric.url) as resp:
            res = await resp.text()
            parser = proxy_lyric.parser
            if not callable(parser):
                parser = self._default_parser
            return parser(res, resp.status)
