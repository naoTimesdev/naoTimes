import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.paginator import DiscordPaginatorUI


class PeninjauGamingSteamDB(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.Game.SteamDB")

    async def _quick_request(self, params: dict, t: Callable[..., str]):
        if self.bot.aiosession is None:
            return None, t("steamdb.http_unavailable")
        async with self.bot.aiosession.get("https://api.ihateani.me/games/steamdb/search", params=params) as response:
            res = await response.json()
            if response.status != 200:
                err_msg = res["error"]
                return None, err_msg
            if "error" in res:
                return None, res["error"]
            return res, "Success"

    @app_commands.command(
        name="steamdb",
        description=app_commands.locale_str("Cari game/app di SteamDB", key="peninjau.steamdb.description"),
    )
    @app_commands.describe(
        kueri=app_commands.locale_str("Game/app/DLC yang ingin dicari", key="peninjau.steamdb.option_query"),
        dengan_dlc=app_commands.locale_str("Tambahkan DLC ke pencarian", key="peninjau.steamdb.option_dlc"),
        dengan_app=app_commands.locale_str("Tambahkan Applications ke pencarian", key="peninjau.steamdb.option_app"),
        dengan_musik=app_commands.locale_str("Tambahkan Music ke pencarian", key="peninjau.steamdb.option_music"),
    )
    async def _peninjau_gaming_steamdb(
        self,
        inter: discord.Interaction,
        kueri: str,
        dengan_dlc: bool = False,
        dengan_app: bool = False,
        dengan_musik: bool = False,
    ):
        """Cari game/app di SteamDB"""
        STORE_APP = "https://store.steampowered.com/app/{}/"
        THUMB = "https://cdn.cloudflare.steamstatic.com/steam/apps/{}/header.jpg"
        args = SimpleNamespace(kueri=kueri, add_dlc=dengan_dlc, add_app=dengan_app, add_music=dengan_musik)
        ctx = await self.bot.get_context(inter)
        await ctx.defer()

        def _true_false(arg: Any):
            if arg:
                return "1"
            return "0"

        params = {
            "q": args.kueri,
            "dlc": _true_false(args.add_dlc),
            "app": _true_false(args.add_app),
            "music": _true_false(args.add_music),
        }
        self.logger.info(f"searching: {args.kueri}")
        self.logger.info(
            f"{args.kueri}: with opts:\n>> DLC: {args.add_dlc}\n>> App: {args.add_app}\n>> Musik: {args.add_music}"
        )

        results, msg = await self._quick_request(params, ctx.t)
        if not results:
            self.logger.warning(f"{args.kueri}: error\n{msg}")
            return await ctx.send(msg)
        sdb_results = results["results"]
        if not sdb_results:
            self.logger.warning(f"{args.kueri}: not found")
            return await ctx.send(ctx.t("steamdb.no_results"))

        def _generate_embed(sdb_data: dict):
            embed = discord.Embed(title=sdb_data["title"], url=STORE_APP.format(sdb_data["id"]))
            description = []
            if "price" in sdb_data:
                description.append(ctx.t("steamdb.price", price=sdb_data["price"]))
            if "user_score" in sdb_data:
                description.append(ctx.t("steamdb.score", score=sdb_data["user_score"]))
            platform = sdb_data["platforms"]
            platforms = []
            if platform["windows"]:
                platforms.append("Windows")
            if platform["mac"]:
                platforms.append("macOS")
            if platform["linux"]:
                platforms.append("Linux")
            description.append(" | ".join(platforms))
            embed.set_thumbnail(url=THUMB.format(sdb_data["id"]))
            embed.description = "\n".join(description)
            developer = ", ".join(sdb_data["developer"]) or ctx.t("steamdb.none")
            publisher = ", ".join(sdb_data["publisher"]) or ctx.t("steamdb.none")
            embed.add_field(
                name=ctx.t("steamdb.field_developer"),
                value=f"**Developer**: {developer}\n**Publisher**: {publisher}",
                inline=False,
            )
            embed.add_field(
                name=ctx.t("steamdb.field_category"),
                value=", ".join(sdb_data["categories"]),
                inline=False,
            )
            embed.add_field(name=ctx.t("steamdb.field_tags"), value=", ".join(sdb_data["tags"]), inline=False)
            embed.set_footer(
                text=ctx.t(
                    "steamdb.footer",
                    released=sdb_data["released"],
                    type=sdb_data["type"].capitalize(),
                    id=sdb_data["id"],
                ),
                icon_url="https://steamdb.info/static/logos/512px.png",
            )
            return embed

        self.logger.info(f"{args.kueri}: starting paginator...")
        ui_gen = DiscordPaginatorUI(ctx, sdb_results, 30.0)
        ui_gen.attach(_generate_embed)
        await ui_gen.interact()


async def setup(bot: naoTimesBot):
    await bot.add_cog(PeninjauGamingSteamDB(bot))
