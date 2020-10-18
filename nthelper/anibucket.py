import asyncio
import logging

import aiohttp


class AnilistBucket:
    """
    A connection handler for Anilist that will make sure it safe from Rate limiting
    """

    BASE_API = "https://graphql.anilist.co"

    def __init__(self):
        self._rate_left = 90

        self.logger = logging.getLogger("nthelper.anibucket.AnilistBucket")

    async def _handle_rate_limit(self):
        if self._rate_left <= 5:
            self.logger.warning("Request bucket being handled, sleeping for 30 seconds...")
            await asyncio.sleep(30)

    async def handle(self, query, variables):
        query_to_send = {"query": query, "variables": variables}
        async with aiohttp.ClientSession(
            headers={"User-Agent": "naoTimes/2.0.1a (https://github.com/noaione/naoTimes)"}
        ) as session:
            try:
                await self._handle_rate_limit()
                async with session.post(self.BASE_API, json=query_to_send) as resp:
                    rate_left = resp.headers["x-ratelimit-remaining"]
                    if isinstance(rate_left, str):
                        rate_left = int(rate_left)
                    self._rate_left = rate_left
                    try:
                        data = await resp.json()
                    except IndexError:
                        return "Tidak dapat memparsing hasil dari request API Anilist."
                    if resp.status != 200:
                        if resp.status == 404:
                            return "Anilist tidak dapat menemukan anime tersebut."
                        if resp.status == 500:
                            return "Anilist mengalami kesalahan internal, mohon coba sesaat lagi."
                    try:
                        _ = data["data"]
                    except IndexError:
                        return "Tidak ada hasil."
            except aiohttp.ClientError:
                return "Terjadi kesalahan koneksi."
        return data["data"]
