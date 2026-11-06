"""
Asynchronous client for the VNDB Kana API.

---

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

import random
import re
from typing import Literal, TypedDict, cast

import aiohttp

__all__ = ("VNDBClient", "VNDBEntry", "VNDBResponse")


class VNDBImage(TypedDict, total=False):
    url: str | None
    sexual: float | None


class VNDBScreenshot(TypedDict, total=False):
    url: str | None
    sexual: float | None


class VNDBRelation(TypedDict):
    id: str
    title: str


class VNDBEntryBase(TypedDict):
    id: str


class VNDBEntry(VNDBEntryBase, total=False):
    title: str
    aliases: list[str]
    image: VNDBImage | None
    length: Literal[1, 2, 3, 4, 5] | None
    length_minutes: int | None
    description: str | None
    rating: float | None
    languages: list[str]
    platforms: list[str]
    screenshots: list[VNDBScreenshot]
    relations: list[VNDBRelation]
    released: str | None
    has_anime: bool


class VNDBResponse(TypedDict, total=False):
    results: list[VNDBEntry]
    more: bool


class VNDBQuery(TypedDict, total=False):
    filters: list[object]
    fields: str
    sort: str
    reverse: bool
    results: int


class VNDBClient:
    """Small client for VNDB API v2 (Kana)."""

    BASE_URL = "https://api.vndb.org/kana"
    VN_FIELDS = (
        "title, aliases, image{url,sexual}, length, length_minutes, description, rating, "
        "languages, platforms, screenshots{url,sexual}, relations{id,title}, released"
    )

    def __init__(self, session: aiohttp.ClientSession, token: str | None = None):
        self._session = session
        self._token = token.strip() if token else None

    async def _query_vn(self, payload: VNDBQuery) -> VNDBResponse:
        headers = {"Authorization": f"Token {self._token}"} if self._token else None
        async with self._session.post(f"{self.BASE_URL}/vn", json=payload, headers=headers) as response:
            if response.status >= 400:
                message = await response.text()
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=message or response.reason or "VNDB API request failed",
                    headers=response.headers,
                )
            return cast(VNDBResponse, await response.json())

    async def _add_anime_flags(self, entries: list[VNDBEntry]) -> list[VNDBEntry]:
        """Kana exposes anime availability as a filter, not as a VN response field."""
        if not entries:
            return entries

        id_filters = [["id", "=", entry["id"]] for entry in entries]
        if len(id_filters) == 1:
            filters: list[object] = ["and", id_filters[0], ["has_anime", "=", 1]]
        else:
            filters = ["or", *[["and", entry_filter, ["has_anime", "=", 1]] for entry_filter in id_filters]]

        response = await self._query_vn({"filters": filters, "fields": "id", "results": len(entries)})
        anime_ids = {entry["id"] for entry in response.get("results", [])}
        for entry in entries:
            entry["has_anime"] = entry.get("id") in anime_ids
        return entries

    async def search(self, query: str) -> list[VNDBEntry]:
        query = query.strip()
        if re.fullmatch(r"v?\d+", query, flags=re.IGNORECASE):
            vn_id = f"v{int(query.removeprefix('v').removeprefix('V'))}"
            filters: list[object] = ["id", "=", vn_id]
            sort = "id"
        else:
            filters = ["search", "=", query]
            sort = "searchrank"

        response = await self._query_vn({"filters": filters, "fields": self.VN_FIELDS, "sort": sort, "results": 10})
        return await self._add_anime_flags(response.get("results", []))

    async def random_vn(self) -> list[VNDBEntry]:
        latest_response = await self._query_vn({"fields": "id", "sort": "id", "reverse": True, "results": 1})
        latest_entries = latest_response.get("results", [])
        if not latest_entries:
            return []

        latest_id = int(latest_entries[0]["id"][1:])
        target_id = random.randint(1, latest_id)
        response = await self._query_vn({
            "filters": ["id", ">=", f"v{target_id}"],
            "fields": self.VN_FIELDS,
            "sort": "id",
            "results": 1,
        })
        return await self._add_anime_flags(response.get("results", []))
