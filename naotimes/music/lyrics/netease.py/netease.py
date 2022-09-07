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
import re
from dataclasses import dataclass
from typing import List, Optional

import aiohttp

from naotimes.utils import complex_walk

__all__ = (
    "NetEaseClient",
    "NetEaseResult",
    "parse_netease_lrc",
)

LRC_REGEX = re.compile(r"(\[.*?\])|([^\[\]]+)")
CREDITS_INFO = [
    r"\\s?作?\\s*词|\\s?作?\\s*曲|\\s?编\\s*曲?|\\s?监\\s*制?",
    r".*编写|.*和音|.*和声|.*合声|.*提琴|.*录|.*工程|.*工作室|.*设计|.*剪辑|.*制作|.*发行|.*出品|.*后期|.*混音|.*缩混",
    r"原唱|翻唱|题字|文案|海报|古筝|二胡|钢琴|吉他|贝斯|笛子|鼓|弦乐",
    r"lrc|publish|vocal|guitar|program|produce|write",
]
CREDITS_REGEX = re.compile(r"^($" + "|".join(CREDITS_INFO) + r").*(:|：)", re.IGNORECASE)


@dataclass
class NetEaseResult:
    title: str
    track_id: str


def parse_netease_lrc(lrc: str) -> List[str]:
    """
    Parse the lrc string into a list of lines.
    """
    split_all_lines = lrc.split("\n")
    clean_lines = [line.rstrip() for line in split_all_lines]

    lyric_lines: List[str] = []
    for line in clean_lines:
        match = re.match(LRC_REGEX, line)
        if not match:
            continue
        spliced_line = re.sub(LRC_REGEX, r"\2", line, 0).strip()
        if re.match(CREDITS_REGEX, spliced_line) is not None:
            continue
        lyric_lines.append(spliced_line)
    return lyric_lines


class NetEaseClient:
    BASE_URL = "https://music.163.com/api"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None) -> None:
        self.logger = logging.getLogger("naoTimes.LyricsClient.NetEase")
        self._session = session
        self._outside_session = True
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._outside_session = False

    async def close(self):
        """
        Closes the session
        """
        if not self._outside_session:
            await self._session.clsoe()

    def _add_header(self):
        return {
            "Referer": "https://music.163.com/",
            "Cookie": "appver=2.0.2",
            "charset": "utf-8",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    async def search(self, search_query: str) -> List[NetEaseResult]:
        self.logger.info(f"Searching for {search_query}")
        req_url = f"{self.BASE_URL}/search/get"
        query_params = {
            "s": search_query,
            "type": 1,
            "offset": 0,
            "sub": "false",
            "limit": 5,
        }

        async with self._session.post(req_url, params=query_params, headers=self._add_header()) as resp:
            resp_json = await resp.json()

        actual_result = complex_walk(resp_json, "result.songs") or []
        if not actual_result:
            self.logger.warning(f"No results found for {search_query}")
            return []
        all_search: List[NetEaseResult] = []
        for result in actual_result:
            artist_collection = complex_walk(result, "artists.*.name") or []
            final_title = complex_walk(result, "name")
            if artist_collection:
                artist_join = ", ".join(artist_collection)
                final_title = f"{artist_join} - {final_title}"
            track_id = complex_walk(result, "id")
            if track_id is None:
                continue
            all_search.append(NetEaseResult(final_title, str(track_id)))
        self.logger.info(f"Found {len(all_search)} results for {search_query}")
        return all_search
