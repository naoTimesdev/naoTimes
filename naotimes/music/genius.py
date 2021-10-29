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
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import aiohttp

from naotimes.utils import complex_walk

__all__ = ("GeniusAPI", "GeniusLyricHit")


@dataclass
class GeniusLyricHit:
    path: str
    title: str
    image: Optional[str] = None


class GeniusAPI:

    HOST = "https://api.genius.com/"

    def __init__(self, client_id: str, client_secret: str, session: aiohttp.ClientSession):
        self.client_id = client_id
        self.client_secret = client_secret
        self._session = session
        self._outside_session = True
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._outside_session = False
        self._token: Optional[str] = None

    async def authorize(self):
        form_data = aiohttp.FormData()
        form_data.add_field("client_id", self.client_id)
        form_data.add_field("client_secret", self.client_secret)
        form_data.add_field("grant_type", "client_credentials")
        async with self._session.post(f"{self.HOST}oauth/token", data=form_data) as response:
            result = await response.json()
        self._token = complex_walk(result, "access_token")

    async def ensure_token(self):
        """
        Ensures the token is valid
        """
        if self._token is None:
            await self.authorize()

    async def close(self):
        """
        Closes the session
        """
        if not self._outside_session:
            await self._session.clsoe()

    async def get_lyrics(self, song_path: str) -> str:
        """
        Gets lyrics from genius.com
        """
        if song_path.startswith("/"):
            song_path = song_path[1:]

        await self.ensure_token()

        headers = {"Authorization": f"Bearer {self._token}"}

        async with self._session.get(
            f"https://naotimes-og.glitch.me/lyrics/{song_path}",
            headers=headers,
        ) as response:
            result = await response.text()
            if response.status != 200:
                return "*Gagal mengambil lirik, mohon coba lagi*"
            return result

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

    async def find_lyrics(self, search_query: str) -> Tuple[List[GeniusLyricHit], Optional[str]]:
        """
        Finds lyrics from genius.com
        """
        headers = {"Authorization": f"Bearer {self._token}"}
        await self.ensure_token()

        async with self._session.get(
            f"{self.HOST}search", params={"q": self._cleanup_query(search_query)}, headers=headers
        ) as response:
            result = await response.json()

        meta = complex_walk(result, "meta.status")
        if meta != 200:
            return [], complex_walk(result, "meta.message")

        response_hits = complex_walk(result, "response.hits") or []
        if not response_hits:
            return [], "Tidak ada hasil yang cocok"

        parsed_hits: List[GeniusLyricHit] = []
        for hit in response_hits:
            lyric_path = complex_walk(hit, "result.path")
            if not lyric_path:
                continue
            song_artwork = complex_walk(hit, "result.song_art_image_url") or complex_walk(
                hit, "result.song_art_image_thumbnail_url"
            )
            song_title = complex_walk(hit, "result.full_title")
            parsed_hits.append(
                GeniusLyricHit(
                    lyric_path,
                    song_title,
                    song_artwork,
                )
            )
        return parsed_hits, None
