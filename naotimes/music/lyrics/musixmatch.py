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

import logging
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlencode

import aiohttp
import orjson

from naotimes.utils import complex_walk

__all__ = (
    "MusixmatchClient",
    "MusixmatchResult",
)


@dataclass
class MusixmatchResult:
    title: str
    request_url: str


class MusixmatchClient:
    BASE_URL = "https://apic-desktop.musixmatch.com/ws/1.1/"
    COMMON_PARAMS: ClassVar[dict[str, str]] = {"user_language": "en", "app_id": "web-desktop-app-v1.0"}

    def __init__(self, api_key: str, session: aiohttp.ClientSession | None = None) -> None:
        self.logger = logging.getLogger("naoTimes.LyricsClient.Musixmatch")
        self.api_key = api_key
        self._outside_session = session is None
        self._session = session if session is not None else aiohttp.ClientSession()

    async def close(self):
        """
        Closes the session
        """
        if not self._outside_session:
            await self._session.close()

    def _build_url(self, commontrack_id: int):
        base_url = f"{self.BASE_URL}track.lyrics.get"
        query_params = {
            **self.COMMON_PARAMS,
            "commontrack_id": str(commontrack_id),
            "usertoken": self.api_key,
        }
        # Make to url
        return f"{base_url}?{urlencode(query_params)}"

    def _cleanup_query(self, query: str) -> str:
        """
        Cleans up the query
        """

        to_be_extracted = [
            "(official)",
            "(Official)",
            "(cover)",
            "(Cover)",
            "[MV]",
            "(MV)",
            "【MV】",
            "- Instrumental",
            "- instrumental",
            "(Instrumental)",
            "(instrumental)",
            "(inst)",
            "(Inst)",
        ]
        for item in to_be_extracted:
            query = query.replace(item, "")
        return query.strip()

    async def search(self, title: str, artist: str | None = None) -> list[MusixmatchResult]:
        req_url = f"{self.BASE_URL}track.search"
        query_params = {
            **self.COMMON_PARAMS,
            "q_track": self._cleanup_query(title),
        }
        if artist is not None:
            query_params["q_artist"] = artist
        query_params["usertoken"] = self.api_key

        self.logger.info(f"Searching for {title} by {artist}")
        async with self._session.get(req_url, params=query_params) as response:
            result = await response.json()

        status_code = complex_walk(result, "message.header.status_code")
        if status_code != 200:
            self.logger.warning(f"Musixmatch search failed with status code {status_code}")
            self.logger.warning(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode("utf-8"))
            return []

        all_hits = complex_walk(result, "message.body.track_list")
        if not isinstance(all_hits, list):
            return []
        compiled_results: list[MusixmatchResult] = []
        for hit in all_hits:
            if not isinstance(hit, dict):
                continue
            common_track = complex_walk(hit, "track.commontrack_id")
            track_title = complex_walk(hit, "track.track_name")
            artist_name = complex_walk(hit, "track.artist_name")
            if not isinstance(common_track, int) or isinstance(common_track, bool):
                continue
            safe_title = track_title if isinstance(track_title, str) else "Unknown title"
            safe_artist = artist_name if isinstance(artist_name, str) else ""
            final_title = safe_artist
            if not final_title:
                final_title = safe_title
            else:
                final_title += f" - {safe_title}"

            compiled_results.append(MusixmatchResult(final_title, self._build_url(common_track)))
        self.logger.info(f"Found {len(compiled_results)} hits")
        return compiled_results
