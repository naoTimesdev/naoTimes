import logging
import random
from typing import List, Union

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import complex_walk, cutoff_text

IMAGEBOORU_SCHEMAS = """
query BooruSearch($tags:[String],$page:Int! = 1,$engine:[BoardEngine!]! = [danbooru],$safe:Boolean) {
    imagebooru {
        search(tags:$tags,engine:$engine,page:$page,safeVersion:$safe) {
            results {
                id
                title
                image_url
                source
                engine
            }
            total
        }
    }
}

query BooruRandom($tags:[String],$page:Int! = 1,$engine:[BoardEngine!]! = [danbooru],$safe:Boolean) {
    imagebooru {
        random(tags:$tags,engine:$engine,page:$page,safeVersion:$safe) {
            results {
                id
                title
                image_url
                source
                engine
            }
            total
        }
    }
}
"""


def snake_caseify(tags: List[str]):
    return [t.replace(" ", "_") for t in tags]


class NSFWImageBooru(commands.Cog):
    POST_BASE_URL = {
        "danbooru": "https://danbooru.donmai.us/posts/",
        "gelbooru": "https://gelbooru.com/index.php?page=post&s=view&id=",
        "e621": "https://e621.net/posts/",
        "konachan": "https://konachan.net/post/show/",
    }

    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("NSFW.ImageBooru")

    @staticmethod
    def clean_title(text: str) -> str:
        split_spaces = text.split(" ")
        cleaned = []
        for txt in split_spaces:
            tx = txt.split("_")
            cleaned.append(" ".join(tx))
        return ", ".join(cleaned)

    async def _request_booru(
        self, board: str, tags: List[str], sfw=False, is_random=False
    ) -> Union[str, List[dict]]:
        self.logger.info(f"Querying {tags} on board {board}")
        variables = {
            "tags": snake_caseify(tags),
            "engine": [board],
            "safe": sfw,
        }
        op_name = "BooruSearch" if not is_random else "BooruRandom"
        if not tags and is_random:
            see_page = random.randint(1, 10)
            variables["page"] = see_page

        gql_result = await self.bot.ihaapi.query(IMAGEBOORU_SCHEMAS, variables, op_name)
        if gql_result.errors:
            error_msg = gql_result.errors[0].message
            if error_msg is None:
                return "Terjadi kesalahan ketika ingin menghubungi API"
            return f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`"

        traverse_text = "imagebooru.search.results"
        if is_random:
            traverse_text = "imagebooru.random.results"

        traversed = complex_walk(gql_result.data, traverse_text)
        if not traversed:
            return "Tidak ada hasil"
        return traversed

    def _generate_ib_embed(self, dataset: dict) -> discord.Embed:
        engine = dataset["engine"].capitalize()
        paralink = self.POST_BASE_URL.get(engine.lower()) + str(dataset["id"])
        embed = discord.Embed(title=cutoff_text(self.clean_title(dataset["title"]), 256), color=0x19212D)
        embed.set_author(name=engine, url=paralink, icon_url="https://api.ihateani.me/assets/favicon.png")
        description = [f"**Laman**: {paralink}"]
        sources = dataset.get("source")
        if sources:
            description.append(f"**Sumber**: [Klik]({sources})")
        embed.description = "\n".join(description)
        embed.set_image(url=dataset["image_url"])
        embed.set_footer(
            text=f"Engine: {engine} | Diprakasi ole ihaAPI",
            icon_url="https://api.ihateani.me/assets/favicon.png",
        )
        return embed

    async def _internal_booru_helper(
        self, ctx: naoTimesContext, engine: str, tags_query: str = None, sfw=False
    ):
        is_random = False
        if tags_query:
            split_query = tags_query.split(" ")
            real_query = split_query
            randomize = False
            if len(split_query) > 1:
                if split_query[0].lower() in ["r", "rng", "random", "order:random", "order:r", "rand"]:
                    real_query = split_query[1:]
                    randomize = True
            elif len(split_query) == 1:
                if split_query[0].lower() in ["r", "rng", "random", "order:random", "order:r", "rand"]:
                    real_query = split_query
                    randomize = True
                    is_random = True
            self.logger.info(f"Searching {engine} with tags: {real_query} (safe: {sfw})")
            results = await self._request_booru(engine, real_query, sfw, randomize)
        else:
            self.logger.info(f"Searching {engine} with randomized data! (safe: {sfw})")
            # Request GQL
            results = await self._request_booru(engine, None, sfw, True)
            is_random = True

        if isinstance(results, str):
            return await ctx.send(results)

        if len(results) < 1:
            return await ctx.send("Tidak dapat hasil!")

        if is_random:
            picked = random.choice(results)
            picked_first = self._generate_ib_embed(picked)
            return await ctx.send(embed=picked_first)

        main_gen = DiscordPaginatorUI(ctx, results, 30.0)
        main_gen.attach(self._generate_ib_embed)
        await main_gen.interact()

    @commands.command(name="danbooru")
    @commands.guild_only()
    @commands.is_nsfw()
    async def _nsfw_ib_danbooru(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "danbooru", tags_query)

    @commands.command(name="safebooru", aliases=["safedanbooru"])
    @commands.guild_only()
    async def _nsfw_ib_danbooru_sfw(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "danbooru", tags_query, True)

    @commands.command(name="konachan")
    @commands.guild_only()
    @commands.is_nsfw()
    async def _nsfw_ib_konachan(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "konachan", tags_query)

    @commands.command(name="safekonachan")
    @commands.guild_only()
    async def _nsfw_ib_konachan_sfw(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "konachan", tags_query, True)

    @commands.command(name="e621")
    @commands.guild_only()
    @commands.is_nsfw()
    async def _nsfw_ib_e621(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "e621", tags_query)

    @commands.command(name="safee621")
    @commands.guild_only()
    async def _nsfw_ib_e621_sfw(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "e621", tags_query, True)

    @commands.command(name="gelbooru")
    @commands.guild_only()
    @commands.is_nsfw()
    async def _nsfw_ib_gelbooru(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "gelbooru", tags_query)

    @commands.command(name="safegelbooru")
    @commands.guild_only()
    async def _nsfw_ib_gelbooru_sfw(self, ctx: naoTimesContext, *, tags_query: str = None):
        await self._internal_booru_helper(ctx, "gelbooru", tags_query, True)


def setup(bot: naoTimesBot):
    bot.add_cog(NSFWImageBooru(bot))
