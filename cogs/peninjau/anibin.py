import logging
from typing import Optional, Tuple

import discord
from bs4 import BeautifulSoup
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.utils import sync_wrap

async_bs4 = sync_wrap(BeautifulSoup)


class PeninjauAnibin(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.Anibin")

    async def _query_anibin(self, query: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        async with self.bot.aiosession.get(f"http://anibin.blogspot.com/search?q={query}") as resp:
            response = await resp.text()

        soup_data: BeautifulSoup = await async_bs4(response, "html.parser")
        query_list = soup_data.find_all("div", attrs={"class": "date-posts"})

        if not query_list:
            return None, None, None
        if query_list[0].find("table"):
            if len(query_list) < 2:
                return None, None, None
            first_query = query_list[1]
        else:
            first_query = query_list[0]

        query_title = first_query.find("h3", attrs={"class": "post-title entry-title"}).text
        if not query_title:
            return None, None, None
        query_title = query_title.strip()

        content_data = str(first_query.find("div", attrs={"class": "post-body entry-content"}))
        n_from = content_data.find("評価:")
        if n_from == -1:
            return None, None, None

        nat_res = content_data[n_from + 3 :]
        nat_res = nat_res[: nat_res.find("<br/>")]

        n_from2 = content_data.find("制作:")

        if n_from2 == -1:
            return [query_title, nat_res, "Unknown"]

        studio = content_data[n_from2 + 3 :]
        studio = studio[: studio.find("<br/>")]

        return query_title, nat_res, studio

    @commands.command(name="anibin")
    async def _peninjau_anibin(self, ctx: naoTimesContext, *, query: str):
        """Mencari native resolution sebuah anime di anibin"""
        self.logger.info("Querying anibin...")
        title, native_res, studio = await self._query_anibin(query)

        if not title:
            self.logger.warning(f"{query}: No results found")
            return await ctx.send(
                "Tidak dapat menemukan anime yang diberikan, mohon gunakan kanji jika belum."
            )

        self.logger.info(f"{query}: sending results...")
        embed = discord.Embed(title="Anibin Native Resolution", color=0xFFAE00)
        embed.add_field(name=title, value=native_res)
        embed.set_footer(text=f"Studio Animasi: {studio}")
        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(PeninjauAnibin(bot))
