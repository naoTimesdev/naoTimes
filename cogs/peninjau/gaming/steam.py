import logging
from collections.abc import Callable, Mapping
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.paginator import DiscordPaginatorUI

HTTPMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


def _mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, dict):
        return None
    return value


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _display(value: object, fallback: str) -> str:
    if isinstance(value, (str, int, float)):
        return str(value)
    return fallback


def _platform_names(value: object) -> list[str]:
    platforms = _mapping(value)
    if platforms is None:
        return []
    names = []
    for key, name in (("windows", "Windows"), ("mac", "macOS"), ("linux", "Linux")):
        if platforms.get(key) is True:
            names.append(name)
    return names


def _descriptions(value: object) -> list[str]:
    return [description for item in _mapping_list(value) if isinstance((description := item.get("description")), str)]


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def clean_description(desc: str) -> str:
    mappings = {
        "&quot;": '"',
        "&amp;": "&",
        "&lt;": "<",
        "&rt;": ">",
        "&apos;": "'",
    }
    for src, dest in mappings.items():
        desc = desc.replace(src, dest)
    return desc


class PeninjauGameSteam(commands.Cog):
    steam = app_commands.Group(
        name="steam",
        description=app_commands.locale_str("Informasi game dan layanan Steam", key="peninjau.steam.group_description"),
        guild_only=True,
    )

    IHABASE = "https://api.ihateani.me/v1/games/"
    APP_FORMAT = "https://store.steampowered.com/app/{}/"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.Gaming.Steam")

    async def _requests(
        self,
        method: HTTPMethod,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        t: Callable[..., str],
    ) -> tuple[Mapping[str, object] | None, str]:
        session = self.bot.aiosession
        if session is None:
            return None, t("steam.http_unavailable")
        request = {
            "GET": session.get,
            "POST": session.post,
            "PUT": session.put,
            "PATCH": session.patch,
            "DELETE": session.delete,
        }[method]
        async with request(url, params=params) as response:
            res = await response.json()
            payload = _mapping(res)
            if payload is None:
                return None, t("steam.invalid_response")
            if response.status != 200:
                return None, _display(payload.get("error"), f"HTTP {response.status}")
            if "error" in payload:
                return None, _display(payload.get("error"), t("steam.request_failed"))
            return payload, "Success"

    @steam.command(
        name="cari",
        description=app_commands.locale_str("Cari game di Steam", key="peninjau.steam.cari_description"),
    )
    @app_commands.describe(pencarian=app_commands.locale_str("Judul game", key="peninjau.steam.cari_option"))
    async def _peninjau_game_steam_cari(self, inter: discord.Interaction, pencarian: str):
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        self.logger.info(f"Searching for: {pencarian}")
        request_param = {"q": pencarian}
        results, msg = await self._requests("GET", self.IHABASE + "steam/search", params=request_param, t=ctx.t)
        if results is None:
            self.logger.warning(f"{pencarian}: error: {msg}.")
            return await ctx.send(msg)

        search_results = _mapping_list(results.get("results"))
        if not search_results:
            self.logger.warning(f"{pencarian}: not found.")
            return await ctx.send(ctx.t("steam.no_results"))

        def _stylize_embed(data: Mapping[str, object]):
            game_id = _display(data.get("id"), "0")
            embed = discord.Embed(
                title=_display(data.get("title"), ctx.t("steam.unknown")),
                url=self.APP_FORMAT.format(game_id),
            )
            descriptions = []
            descriptions.append(" | ".join(_platform_names(data.get("platforms"))))
            if data.get("is_free") is True:
                price_data = ctx.t("steam.price_free")
            else:
                price_data = ctx.t("steam.price", price=_display(data.get("price"), ctx.t("steam.unknown")))

            descriptions.append(price_data)
            descriptions.append(
                ctx.t("steam.support", support=_display(data.get("controller_support"), ctx.t("steam.unknown")))
            )
            embed.description = "\n".join(descriptions)
            thumbnail = data.get("thumbnail")
            if isinstance(thumbnail, str):
                embed.set_thumbnail(url=thumbnail)
            embed.set_footer(
                text=ctx.t("steam.footer_store", id=game_id),
                icon_url="https://steamstore-a.akamaihd.net/public/shared/images/responsive/share_steam_logo.png",
            )
            return embed

        self.logger.info(f"{pencarian}: sending info...")
        ui_gen = DiscordPaginatorUI(ctx, items=search_results, timeout=30.0)
        ui_gen.attach(_stylize_embed)
        await ui_gen.interact()

    @steam.command(
        name="info",
        description=app_commands.locale_str("Lihat informasi game/app Steam", key="peninjau.steam.info_description"),
    )
    @app_commands.describe(app_id=app_commands.locale_str("AppID Steam", key="peninjau.steam.info_option"))
    async def _peninjau_gaming_steam_info(self, inter: discord.Interaction, app_id: str):
        self.logger.info(f"Getting info for {app_id}")
        ctx = await self.bot.get_context(inter)
        if not app_id.isdigit():
            return await inter.response.send_message(ctx.t("steam.invalid_app_id"), ephemeral=True)
        await ctx.defer()

        result, msg = await self._requests("GET", self.IHABASE + "steam/game/" + app_id, t=ctx.t)
        if result is None:
            self.logger.warning(f"{app_id}: error: {msg}.")
            return await ctx.send(msg)
        if not result:
            self.logger.warning(f"{app_id}: no result.")
            return await ctx.send(ctx.t("steam.app_not_found"))

        genres_list = _descriptions(result.get("genres"))
        category_list = _descriptions(result.get("category"))

        self.logger.info(f"{app_id}: formatting results...")
        embed = discord.Embed(
            title=_display(result.get("title"), ctx.t("steam.unknown")),
            url=self.APP_FORMAT.format(_display(result.get("id"), "0")),
        )
        embed_desc = []
        description = result.get("description")
        if isinstance(description, str):
            embed_desc.append(clean_description(description))
        if result.get("is_free") is True:
            price_data = ctx.t("steam.price_free")
        else:
            price_info = _mapping(result.get("price_data"))
            if price_info is not None:
                price_data = ctx.t("steam.price", price=_display(price_info.get("price"), ctx.t("steam.unknown")))
                if price_info.get("discount"):
                    price_data += ctx.t(
                        "steam.discount", discounted=_display(price_info.get("discounted"), ctx.t("steam.unknown"))
                    )
                    price_data += ctx.t(
                        "steam.price_original",
                        price=_display(price_info.get("original_price"), ctx.t("steam.unknown")),
                    )
            else:
                price_data = ctx.t("steam.price_tbd")
        embed_desc.append(price_data)
        embed_desc.append(" | ".join(_platform_names(result.get("platforms"))))
        if "total_achivements" in result:
            embed_desc.append(ctx.t("steam.total_achievements", count=result["total_achivements"]))
        embed.description = "\n".join(embed_desc)
        thumbnail = result.get("thumbnail")
        if isinstance(thumbnail, str):
            embed.set_thumbnail(url=thumbnail)
        developer = ", ".join(_string_values(result.get("developer")))
        publisher = ", ".join(_string_values(result.get("publisher")))
        embed.add_field(
            name=ctx.t("steam.field_developer"),
            value=ctx.t("steam.developer_value", developer=developer, publisher=publisher),
            inline=False,
        )
        if category_list:
            embed.add_field(name=ctx.t("steam.field_category"), value=", ".join(category_list), inline=False)
        if genres_list:
            embed.add_field(name=ctx.t("steam.field_genre"), value=", ".join(genres_list), inline=False)
        rls_date = result.get("released")
        if rls_date is None:
            rls_date = ctx.t("steam.coming_soon")
        embed.set_footer(
            text=ctx.t("steam.footer_info", released=_display(rls_date, ctx.t("steam.unknown"))),
            icon_url="https://steamdb.info/static/logos/512px.png",
        )
        await ctx.send(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(PeninjauGameSteam(bot))
