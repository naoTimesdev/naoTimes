import logging
import random
from functools import partial
from typing import ClassVar

import discord
from discord import app_commands
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


def snake_caseify(tags: list[str]):
    if not tags:
        return []
    return [t.replace(" ", "_") for t in tags]


class NSFWImageBooru(commands.Cog):
    POST_BASE_URL: ClassVar[dict[str, str]] = {
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

    async def _request_booru(self, i18n, board: str, tags: list[str], sfw=False, is_random=False) -> str | list[dict]:
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

        if self.bot.ihaapi is None:
            return i18n.t("booru.api_unavailable")
        gql_result = await self.bot.ihaapi.query(IMAGEBOORU_SCHEMAS, variables, op_name)
        if gql_result.errors:
            error_msg = gql_result.errors[0].message
            if error_msg is None:
                return i18n.t("booru.api_contact_error")
            return i18n.t("booru.api_process_error", error=error_msg)

        traverse_text = "imagebooru.search.results"
        if is_random:
            traverse_text = "imagebooru.random.results"

        if gql_result.data is None:
            return i18n.t("booru.empty_result")
        traversed = complex_walk(gql_result.data, traverse_text)
        if not isinstance(traversed, list):
            return i18n.t("booru.empty_result")
        return [item for item in traversed if isinstance(item, dict)]

    def _generate_ib_embed(self, dataset: dict, i18n) -> discord.Embed:
        engine = dataset["engine"].capitalize()
        base_url = self.POST_BASE_URL.get(engine.lower())
        if base_url is None:
            base_url = ""
        paralink = base_url + str(dataset["id"])
        embed = discord.Embed(title=cutoff_text(self.clean_title(dataset["title"]), 256), color=0x19212D)
        embed.set_author(name=engine, url=paralink, icon_url="https://api.ihateani.me/assets/favicon.png")
        description = [i18n.t("booru.embed_page", link=paralink)]
        sources = dataset.get("source")
        if sources:
            description.append(i18n.t("booru.embed_source", source=sources))
        embed.description = "\n".join(description)
        embed.set_image(url=dataset["image_url"])
        embed.set_footer(
            text=i18n.t("booru.embed_footer", engine=engine),
            icon_url="https://api.ihateani.me/assets/favicon.png",
        )
        return embed

    async def _internal_booru_helper(
        self, ctx: naoTimesContext, engine: str, tags_query: str | None = None, sfw=False, random_order=False
    ):
        i18n = self.bot.i18n_for(ctx.guild, "bahaya")
        tags = tags_query.split() if tags_query else []
        is_random = random_order or not tags
        self.logger.info(f"Searching {engine} with tags: {tags} (safe: {sfw}, random: {is_random})")
        results = await self._request_booru(i18n, engine, tags, sfw, is_random)

        if isinstance(results, str):
            return await ctx.send(results)

        if len(results) < 1:
            return await ctx.send(i18n.t("booru.no_results"))

        if is_random:
            picked = random.choice(results)
            return await ctx.send(embed=self._generate_ib_embed(picked, i18n))

        main_gen = DiscordPaginatorUI(ctx, results, 30.0)
        main_gen.attach(partial(self._generate_ib_embed, i18n=i18n))
        await main_gen.interact()

    @app_commands.command(
        name="booru",
        description=app_commands.locale_str("Cari gambar di situs imageboard (booru)", key="bahaya.booru.description"),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        engine=app_commands.locale_str("Situs booru yang ingin dicari", key="bahaya.booru.option_engine"),
        tags=app_commands.locale_str(
            "Tag pencarian, pisahkan dengan spasi (kosongkan untuk gambar acak)", key="bahaya.booru.option_tags"
        ),
        acak=app_commands.locale_str("Ambil satu gambar acak", key="bahaya.booru.option_acak"),
        aman=app_commands.locale_str(
            "Hanya hasil aman (SFW). Hasil non-aman hanya bisa di kanal NSFW.", key="bahaya.booru.option_aman"
        ),
    )
    @app_commands.choices(
        engine=[
            app_commands.Choice(name="Danbooru", value="danbooru"),
            app_commands.Choice(name="Konachan", value="konachan"),
            app_commands.Choice(name="e621", value="e621"),
            app_commands.Choice(name="Gelbooru", value="gelbooru"),
        ]
    )
    async def _nsfw_ib_booru(
        self,
        inter: discord.Interaction,
        engine: app_commands.Choice[str],
        tags: str | None = None,
        acak: bool = False,
        aman: bool = True,
    ):
        """Cari gambar di situs imageboard (booru)"""
        i18n = self.bot.i18n_for(inter.guild, "bahaya")
        if not aman:
            channel = inter.channel
            if not (isinstance(channel, (discord.TextChannel, discord.Thread)) and channel.is_nsfw()):
                return await inter.response.send_message(i18n.t("booru.nsfw_only"), ephemeral=True)
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        await self._internal_booru_helper(ctx, engine.value, tags, aman, acak)


async def setup(bot: naoTimesBot):
    await bot.add_cog(NSFWImageBooru(bot))
