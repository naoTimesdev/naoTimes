import logging
import random
from typing import List, Union

import aiohttp
import discord
from discord.ext import commands

from nthelper.bot import naoTimesBot
from nthelper.utils import DiscordPaginator, traverse

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


async def nsfw_channel(ctx):
    if ctx.guild:
        return ctx.channel.is_nsfw()
    raise commands.NoPrivateMessage("Perintah tidak bisa dipakai di private message.")


class ImageBooru(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("cogs.imagebooru.ImageBooru")

    @staticmethod
    def is_msg_empty(msg: str, thr: int = 3) -> bool:
        split_msg: List[str] = msg.split(" ")
        split_msg = [m for m in split_msg if m != ""]
        if len(split_msg) < thr:
            return True
        return False

    async def request_gql(self, board, tags, safe_version=False, is_random=False) -> Union[str, List[dict]]:
        self.logger.info(f"Querying {tags} on board {board}")
        query_to_send = {
            "query": IMAGEBOORU_SCHEMAS,
            "variables": {"tags": tags, "engine": [board], "safe": safe_version},
            "operationName": "BooruSearch" if not is_random else "BooruRandom",
        }
        if not tags and is_random:
            see_page = random.randint(1, 10)
            query_to_send["variables"]["page"] = see_page
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{self.bot.semver} (https://github.com/noaione/naoTimes)"}
        ) as session:
            try:
                async with session.post("https://api.ihateani.me/v2/graphql", json=query_to_send) as resp:
                    try:
                        res = await resp.json()
                    except (ValueError, IndexError, KeyError, AttributeError):
                        return "Mendapatkan respon teks dari API."
                    if resp.status != 200:
                        if resp.status == 404:
                            return "Tidak dapat hasil"
                        if resp.status == 500:
                            return "Terjadi kesalahan internal server, mohon coba sesaat lagi"
                        return (
                            f"Terjadi kesalahan ketika menghubungi API, mendapatkan HTTP code {resp.status}"
                        )
                    traversal_text = "data.imagebooru.search.results"
                    if is_random:
                        traversal_text = "data.imagebooru.random.results"
                    try:
                        return traverse(res, traversal_text)
                    except (ValueError, KeyError, IndexError, AttributeError):
                        return "Tidak ada hasil."
            except aiohttp.ClientError:
                return "Terjadi kesalahan ketika menghubungi API."

    @staticmethod
    def limit_size(text: str, limit: int) -> str:
        if len(text) >= limit:
            text = text[0 : limit - 5] + " ..."
        return text

    @staticmethod
    def clean_title(text: str) -> str:
        split_spaces = text.split(" ")
        cleaned = []
        for txt in split_spaces:
            tx = txt.split("_")
            cleaned.append(" ".join(tx))
        return ", ".join(cleaned)

    async def _generate_ib_embed(self, dataset: dict) -> discord.Embed:
        engine_base_url = {
            "danbooru": "https://danbooru.donmai.us/posts/",
            "gelbooru": "https://gelbooru.com/index.php?page=post&s=view&id=",
            "e621": "https://e621.net/posts/",
            "konachan": "https://konachan.net/post/show/",
        }
        engine = dataset["engine"].capitalize()
        paralink = engine_base_url.get(engine.lower()) + str(dataset["id"])
        embed = discord.Embed(title=self.limit_size(self.clean_title(dataset["title"]), 256), color=0x19212D)
        embed.set_author(name=engine, url=paralink, icon_url="https://api.ihateani.me/assets/favicon.png")
        desc = f"**Laman**: {paralink}"
        if "source" in dataset and dataset["source"]:
            desc += f"\n**Source**: [Klik]({dataset['source']})"
        embed.description = desc
        embed.set_image(url=dataset["image_url"])
        embed.set_footer(
            text=f"Engine: {engine} | Diprakasai dengan ihaAPI",
            icon_url="https://api.ihateani.me/assets/favicon.png",
        )
        return embed

    async def _internal_helper(
        self, ctx: commands.Context, engine: str, tags_query: str = None, safe_version=False
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
            self.logger.info(f"Searching {engine} with tags: {real_query} (safe: {safe_version})")
            results = await self.request_gql(engine, real_query, safe_version, randomize)
        else:
            self.logger.info(f"Searching {engine} with randomized data! (safe: {safe_version})")
            results = await self.request_gql(engine, None, safe_version, True)
            is_random = True

        if isinstance(results, str):
            return await ctx.send(results)

        if len(results) < 1:
            return await ctx.send("Tidak dapat hasil.")

        if is_random:
            picked = random.choice(results)
            parsed_first = await self._generate_ib_embed(picked)
            return await ctx.send(embed=parsed_first)

        main_gen = DiscordPaginator(self.bot, ctx)
        main_gen.checker()
        main_gen.breaker()
        main_gen.set_generator(self._generate_ib_embed)
        await main_gen.start(results, 30.0)

    @commands.command(name="danbooru")
    @commands.guild_only()
    @commands.check(nsfw_channel)
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _danbooru_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "danbooru", tags_query)

    @commands.command(name="safebooru")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _safebooru_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "danbooru", tags_query, True)

    @commands.command(name="gelbooru")
    @commands.guild_only()
    @commands.check(nsfw_channel)
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _gelbooru_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "gelbooru", tags_query)

    @commands.command(name="safegelbooru")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _safegelbooru_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "gelbooru", tags_query, True)

    @commands.command(name="konachan")
    @commands.guild_only()
    @commands.check(nsfw_channel)
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _konachan_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "konachan", tags_query)

    @commands.command(name="safekonachan")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _safekonachan_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "konachan", tags_query, True)

    @commands.command(name="e621")
    @commands.guild_only()
    @commands.check(nsfw_channel)
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _e621_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "e621", tags_query)

    @commands.command(name="safee621")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def _safee621_main(self, ctx: commands.Context, *, tags_query=None):
        await self._internal_helper(ctx, "e621", tags_query, True)

    @_danbooru_main.error
    @_safebooru_main.error
    @_gelbooru_main.error
    @_safegelbooru_main.error
    @_konachan_main.error
    @_safekonachan_main.error
    @_e621_main.error
    @_safee621_main.error
    async def ib_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            perms = ["Manage Messages", "Embed Links", "Read Message History", "Add Reactions"]
            await ctx.send("Bot tidak memiliki salah satu dari perms ini:\n" + "\n".join(perms))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Perintah ini hanya bisa dijalankan di server.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(
                "Untuk menggunakan perintah ini, dibutuhkan channel yang sudah diaktifkan mode NSFW-nya.\n"
                "Atau bisa menjalankan versi 'aman'-nya"
            )


def setup(bot: naoTimesBot):
    bot.add_cog(ImageBooru(bot))
