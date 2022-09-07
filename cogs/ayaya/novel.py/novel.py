from dataclasses import dataclass
from typing import List

import aiohttp
from bs4 import BeautifulSoup, Tag
from discord.ext import commands

from naotimes.bot import naoTimesBot

__UA__ = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36"  # noqa


@dataclass
class NovelResult:
    title: str
    thumbnail: str
    url: str

    def __post_init__(self):
        self.title = self.title.capitalize()
        if self.thumbnail.startswith("//"):
            self.thumbnail = f"https:{self.thumbnail}"


class AyayaNovel(commands.Cog):
    AJAXAPI = "ttps://www.novelupdates.com/wp-admin/admin-ajax.php"

    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot

    async def _search_novel(self, query: str):
        aio_form = aiohttp.FormData()
        aio_form.add_field("action", "nd_ajaxsearchmain")
        aio_form.add_field("strOne", query)
        aio_form.add_field("strType", "desktop")
        aio_form.add_field("strSearchType", "series")

        headers = {
            "Referer": "https://www.novelupdates.com/",
            "Origin": "https://www.novelupdates.com",
            "User-Agent": __UA__,
            "x-requested-with": "XMLHttpRequest",
        }
        async with self.bot.aiosession.post(self.AJAXAPI, data=aio_form, headers=headers) as resp:
            html_res = await resp.text()

        soup = BeautifulSoup(html_res, "html.parser")
        all_results = soup.find_all("li", attrs={"class": "search_li_results"})

        data_results: List[NovelResult] = []
        for result in all_results:
            a_link: Tag = result.find("a")
            link_href = a_link.get("href")
            text_data = a_link.get_text().strip()
            img_profile: Tag = result.find("img", attrs={"class": "search_profile_image"})
            img_src = img_profile.get("src")
            img_src = img_src.replace("/img/", "/imgmid/")
            data_results.append(NovelResult(text_data, img_src, link_href))
        return data_results


async def setup(bot: naoTimesBot) -> None:
    await bot.add_cog(AyayaNovel(bot))
