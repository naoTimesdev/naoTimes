"""
A simple Anilist rate limiting handling

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

from math import ceil
from typing import Optional

import aiohttp
from aiolimiter import AsyncLimiter

from ..utils import complex_walk
from .gql import GraphQLClient, GraphQLResult

__all__ = ("AnilistBucket",)


class AnilistBucket:
    """
    A connection bucket to handle Anilist rate limiting.
    This class will make sure it's safe to request Anilist and avoid rate limiting...
    """

    BASE_API = "https://graphql.anilist.co"

    def __init__(self, session: aiohttp.ClientSession, rate_limit: int = 90):
        self._sesi = session

        self._limiter = AsyncLimiter(rate_limit, 60)
        self._next_reset = -1
        self._rate_left = rate_limit

        self._requester = GraphQLClient(self.BASE_API, session)

    async def handle(self, query: str, variables: dict = {}, operation_name: Optional[str] = None) -> GraphQLResult:
        async with self._limiter:
            requested = await self._requester.query(query, variables, operation_name)
            return requested

    async def paginate(self, query: str, variables: dict = {}):
        def internal_function(data: Optional[dict]):
            if data is None:
                return False, None, "page"
            page_info = complex_walk(data, "Page.pageInfo")
            if page_info is None:
                return False, None, "page"
            has_next_page = page_info.get("hasNextPage", False)
            current_page = page_info.get("currentPage")
            per_page = page_info.get("perPage")
            total_data = page_info.get("total")
            total_pages = ceil(total_data / per_page)
            if current_page == total_pages:
                has_next_page = False
            return has_next_page, current_page + 1, "page"

        await self._limiter.acquire()
        async for result, pageInfo in self._requester.paginate(query, internal_function, variables):
            yield result
            if pageInfo.hasMore:
                await self._limiter.acquire()
            else:
                break

    async def close(self):
        await self._requester.close()
