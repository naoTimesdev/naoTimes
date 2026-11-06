import asyncio
import logging
import re
from functools import partial
from typing import Callable, Literal

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.http.vndb import VNDBClient, VNDBEntry
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import cutoff_text


class VNDBModel:
    def __init__(
        self,
        id: str,
        title: str,
        aliases: list[str] | None = None,
        image: str | None = None,
        description: str = "-",
        platforms: list[str] | None = None,
        languages: list[str] | None = None,
        relations: list[str] | None = None,
        screenshots: list[str] | None = None,
        duration: Literal[1, 2, 3, 4, 5] | None = None,
        score: float = 0.0,
        release_date: str | None = None,
        has_anime: bool = False,
        *,
        t: Callable[..., str],
    ):
        self._id = id
        self._title = title
        self._aliases = aliases
        self._image = image
        self._description = description
        self._platforms = platforms or []
        self._languages = languages or []
        self._duration = duration
        self._relasi = relations or []
        self._screenies = screenshots or []
        self._score = score
        self._is_released = release_date
        self._has_anime = has_anime
        self._t = t

        if self._image is None:
            if len(self._screenies) > 0:
                self._image = self._screenies[0]
            else:
                self._image = "https://s.vndb.org/linkimg/vndb1.gif"

    @property
    def id(self) -> str:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def url(self) -> str:
        return f"https://vndb.org/v{self._id}"

    @property
    def footer(self) -> str:
        return self._t("visualnovel.footer_id", id=self._id)

    @property
    def aliases(self) -> str:
        if isinstance(self._aliases, str):
            return self._aliases or self._t("visualnovel.unknown")
        elif isinstance(self._aliases, list):
            if not self._aliases:
                return self._t("visualnovel.unknown")
            return ", ".join(self._aliases)
        return self._t("visualnovel.unknown")

    @property
    def rating(self) -> str:
        return str(self._score) if self._score else self._t("visualnovel.unknown")

    @property
    def poster(self) -> str | None:
        return self._image

    @property
    def description(self) -> str:
        return self._description if self._description else self._t("visualnovel.unknown")

    @property
    def platform(self) -> str:
        if len(self._platforms) < 1:
            return self._t("visualnovel.unknown")
        platforms_map = {
            "win": "Windows",
            "lin": "Linux",
            "mac": "Mac OS",
            "web": "Website",
            "tdo": "3DO",
            "ios": "Apple iProduct",
            "and": "Android",
            "bdp": "Blu-ray Player",
            "dos": "DOS",
            "dvd": "DVD Player",
            "drc": "Dreamcast",
            "nes": "Famicom",
            "sfc": "Super Famicom",
            "fm7": "FM-7",
            "fm8": "FM-8",
            "fmt": "FM Towns",
            "gba": "Game Boy Advance",
            "gbc": "Game Boy Color",
            "msx": "MSX",
            "nds": "Nintendo DS",
            "swi": "Nintendo Switch",
            "sw2": "Nintendo Switch 2",
            "wii": "Nintendo Wii",
            "wiu": "Nintendo Wii U",
            "n3d": "Nintendo 3DS",
            "p88": "PC-88",
            "p98": "PC-98",
            "pce": "PC Engine",
            "pcf": "PC-FX",
            "psp": "PlayStation Portable",
            "ps1": "PlayStation 1",
            "ps2": "PlayStation 2",
            "ps3": "PlayStation 3",
            "ps4": "PlayStation 4",
            "ps5": "PlayStation 5",
            "psv": "PlayStation Vita",
            "smd": "Sega Mega Drive",
            "scd": "Sega Mega-CD",
            "sat": "Sega Saturn",
            "vnd": "VNDS",
            "x1s": "Sharp X1",
            "x68": "Sharp X68000",
            "xb1": "Xbox",
            "xb3": "Xbox 360",
            "xbo": "Xbox One",
            "xxs": "Xbox X/S",
            "mob": "Other (mobile)",
            "oth": "Other",
        }
        return ", ".join(map(lambda x: platforms_map.get(x, x.upper()), self._platforms))

    @property
    def language(self) -> str:
        if len(self._languages) < 1:
            return self._t("visualnovel.unknown")
        return ", ".join(self._languages)

    @property
    def relation(self) -> str:
        if len(self._relasi) < 1:
            return self._t("visualnovel.none")
        return "\n".join(self._relasi)

    @property
    def screenies(self) -> list[str]:
        return self._screenies

    @property
    def duration(self) -> str:
        duration_map = {
            1: "very_short",
            2: "short",
            3: "medium",
            4: "long",
            5: "very_long",
        }
        if self._duration is None:
            return self._t("visualnovel.unknown")
        key = duration_map.get(self._duration)
        if key is None:
            return self._t("visualnovel.unknown")
        return self._t(f"visualnovel.duration.{key}")

    @property
    def released(self) -> str:
        return self._is_released if self._is_released else self._t("visualnovel.unknown")

    @property
    def has_anime(self) -> str:
        return self._t("visualnovel.yes") if self._has_anime else self._t("visualnovel.no")


def bbcode_markdown(string: str) -> str:
    if not string:
        return "-"
    regex_lists = {
        r"\[b\](.*)\[\\b\]": "**\\1**",
        r"\[i\](.*)\[\\i\]": "*\\1*",
        r"\[u\](.*)\[\\u\]": "__\\1__",
        r"\[s\](.*)\[\\s\]": "~~\\1~~",
        r"\[code\](.*)\[\\code\]": "`\\1`",
        r"\[quote\](.*)\[\\quote\]": "```\\1```",
        r"\[quote\=.+?\](.*)\[\\quote\]": "```\\1```",
        r"\[center\](.*)\[\\center\]": "\\1",
        r"\[color\=.+?\](.*)\[\\color\]": "\\1",
        r"\[img\](.*)\[\\img\]": "![\\1](\\1)",
        r"\[img=(.+?)\](.*)\[\\img\]": "![\\2](\\1)",
        r"\[url=(.+?)\]((?:.|\n)+?)\[\/url\]": "[\\2](\\1)",
        r"\[url\]((?:.|\n)+?)\[\/url\]": "[\\1](\\1)",
    }
    for pattern, repl in regex_lists.items():
        string = re.sub(pattern, repl, string, flags=re.MULTILINE | re.IGNORECASE)
    return string


class AyayaVisualNovel(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Ayaya.VisualNovel")
        self.vnconn: VNDBClient | None = bot.vndb_client

    @staticmethod
    def _channel_is_nsfw(channel: object | None) -> bool:
        is_nsfw = getattr(channel, "is_nsfw", None)
        return bool(is_nsfw()) if callable(is_nsfw) else False

    async def _fetch_database(
        self, search: str, allow_nsfw: bool = False, *, t: Callable[..., str]
    ) -> list[VNDBModel] | str:
        vnconn = self.vnconn
        if vnconn is None:
            return t("visualnovel.vndb_unavailable")
        self.logger.info("Searching VNDB for %r", search)
        try:
            result = await asyncio.wait_for(vnconn.search(search), timeout=15.0)
        except TimeoutError:
            return t("visualnovel.timeout")
        except aiohttp.ClientError:
            self.logger.exception("VNDB search failed for %r", search)
            return t("visualnovel.search_error")

        if not result:
            self.logger.warning(f"{search}: no result found")
            return t("visualnovel.not_found")

        return self._models_from_results(result, allow_nsfw, t=t)

    @staticmethod
    def _models_from_results(
        results: list[VNDBEntry], allow_nsfw: bool = False, *, t: Callable[..., str]
    ) -> list[VNDBModel]:
        models: list[VNDBModel] = []
        for item in results:
            image_data = item.get("image") or {}
            screenshots = item.get("screenshots") or []
            relations = item.get("relations") or []
            poster = image_data.get("url")
            if not allow_nsfw and (image_sexual := image_data.get("sexual")) is not None and image_sexual > 1:
                poster = None
            screenies = []
            for image in screenshots:
                image_url = image.get("url")
                image_sexual = image.get("sexual")
                if image_url and (allow_nsfw or image_sexual is None or image_sexual <= 1):
                    screenies.append(image_url)
            models.append(
                VNDBModel(
                    item["id"].removeprefix("v"),
                    item.get("title") or t("visualnovel.unknown"),
                    item.get("aliases") or [],
                    poster,
                    bbcode_markdown(item.get("description") or ""),
                    item.get("platforms") or [],
                    [language.upper() for language in item.get("languages", [])],
                    [f"{relation['title']} ({relation['id']})" for relation in relations],
                    screenies,
                    item.get("length"),
                    item.get("rating") or 0.0,
                    item.get("released") or t("visualnovel.unknown"),
                    item.get("has_anime", False),
                    t=t,
                )
            )
        return models

    async def _random_search(self, allow_nsfw: bool = False, *, t: Callable[..., str]) -> list[VNDBModel] | str:
        vnconn = self.vnconn
        if vnconn is None:
            return t("visualnovel.vndb_unavailable")
        self.logger.info("Fetching a random VN from VNDB...")
        try:
            result = await asyncio.wait_for(vnconn.random_vn(), 15.0)
        except TimeoutError:
            return t("visualnovel.timeout_random")
        except aiohttp.ClientError:
            self.logger.exception("VNDB random entry request failed")
            return t("visualnovel.random_error")
        if not result:
            return t("visualnovel.random_not_found")
        return self._models_from_results(result, allow_nsfw, t=t)

    @staticmethod
    def _design_embed(data: VNDBModel, t: Callable[..., str]) -> discord.Embed:
        embed = discord.Embed(color=0x225588)
        embed.set_thumbnail(url=data.poster)
        embed.set_author(
            name=data.title,
            url=data.url,
            icon_url="https://ihateani.me/o/vndbico.png",
        )
        embed.set_footer(text=data.footer)

        embed.add_field(name=t("visualnovel.embed.aliases"), value=data.aliases, inline=True)
        embed.add_field(name=t("visualnovel.embed.duration"), value=data.duration, inline=True)
        embed.add_field(name=t("visualnovel.embed.language"), value=data.language, inline=True)
        embed.add_field(name=t("visualnovel.embed.platform"), value=data.platform, inline=True)
        embed.add_field(name=t("visualnovel.embed.released"), value=data.released, inline=True)
        embed.add_field(name=t("visualnovel.embed.score"), value=data.rating, inline=True)
        embed.add_field(name=t("visualnovel.embed.relations"), value=data.relation, inline=True)
        embed.add_field(name=t("visualnovel.embed.anime_adaptation"), value=data.has_anime, inline=True)
        embed.add_field(name=t("visualnovel.embed.synopsis"), value=cutoff_text(data.description, 1024), inline=False)
        return embed

    @staticmethod
    def _design_screenies(image: str, position: int, data: VNDBModel) -> discord.Embed:
        total_screenies = len(data.screenies)
        embed = discord.Embed(color=0x225588)
        embed.description = image
        embed.set_author(
            name=f"{data.title} ({position + 1}/{total_screenies})",
            url=data.url,
            icon_url="https://ihateani.me/o/vndbico.png",
        )
        embed.set_image(url=image)
        return embed

    @app_commands.command(
        name="vn",
        description=app_commands.locale_str("Cari visual novel di VNDB", key="ayaya.visualnovel.description_vn"),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul visual novel", key="ayaya.visualnovel.option_judul"),
    )
    async def _ayaya_vnmain(self, inter: discord.Interaction, judul: str):
        """Cari visual novel di VNDB"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        allow_nsfw = self._channel_is_nsfw(inter.channel)
        vnqres = await self._fetch_database(judul, allow_nsfw, t=ctx.t)
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        def _screenies_handler(data: VNDBModel, _, message: discord.Message, view: DiscordPaginatorUI):
            screen_gen = DiscordPaginatorUI(view.ctx, data.screenies)
            img_embed_gen = partial(self._design_screenies, data=data)
            screen_gen.attach(img_embed_gen)
            screen_gen.parent = view
            return screen_gen

        main_gen = DiscordPaginatorUI(ctx, vnqres)
        main_gen.attach(partial(self._design_embed, t=ctx.t))
        main_gen.add_handler(
            ctx.t("visualnovel.screenshot_handler"),
            lambda data: len(data.screenies) > 0,
            _screenies_handler,
            emoji="📸",
        )
        await main_gen.interact(30.0)

    @app_commands.command(
        name="randomvn",
        description=app_commands.locale_str(
            "Ambil visual novel acak dari VNDB",
            key="ayaya.visualnovel.description_random",
        ),
    )
    @app_commands.guild_only()
    async def _ayaya_vnrandom(self, inter: discord.Interaction):
        """Ambil visual novel acak dari VNDB"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        allow_nsfw = self._channel_is_nsfw(inter.channel)
        vnqres = await self._random_search(allow_nsfw, t=ctx.t)
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        def _screenies_handler(data: VNDBModel, _, message: discord.Message, view: DiscordPaginatorUI):
            screen_gen = DiscordPaginatorUI(view.ctx, data.screenies)
            img_embed_gen = partial(self._design_screenies, data=data)
            screen_gen.attach(img_embed_gen)
            screen_gen.parent = view
            return screen_gen

        first_r = vnqres[0]
        if len(first_r.screenies) > 0:
            main_gen = DiscordPaginatorUI(ctx, vnqres)
            main_gen.attach(partial(self._design_embed, t=ctx.t))
            main_gen.add_handler(
                ctx.t("visualnovel.screenshot_handler"),
                lambda data: len(data.screenies) > 0,
                _screenies_handler,
                emoji="📸",
            )
            await main_gen.interact(30.0)
        else:
            embed_data = self._design_embed(first_r, t=ctx.t)
            await ctx.send(embed=embed_data)


async def setup(bot: naoTimesBot):
    await bot.add_cog(AyayaVisualNovel(bot))
