import logging
from typing import Any

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.converters import Arguments, CommandArgParse
from naotimes.paginator import DiscordPaginatorUI

steamdb_args = Arguments("steamdb")
steamdb_args.add_args("kueri", help="game/app/dlc yang ingin dicari.")
steamdb_args.add_args(
    "--dengan-dlc",
    "-dlc",
    required=False,
    dest="add_dlc",
    action="store_true",
    help="Tambahkan DLC ke kueri pencarian",
)
steamdb_args.add_args(
    "--dengan-app",
    "-app",
    required=False,
    dest="add_app",
    action="store_true",
    help="Tambahkan Applications ke kueri pencarian",
)
steamdb_args.add_args(
    "--dengan-musik",
    "-musik",
    required=False,
    dest="add_music",
    action="store_true",
    help="Tambahkan Music ke kueri pencarian",
)
steamdb_converter = CommandArgParse(steamdb_args)


class PeninjauGamingSteamDB(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.Game.SteamDB")

    async def _quick_request(self, params: dict):
        async with self.bot.aiosession.get(
            "https://api.ihateani.me/games/steamdb/search", params=params
        ) as response:
            res = await response.json()
            if response.status != 200:
                err_msg = res["error"]
                return None, err_msg
            if "error" in res:
                return None, res["error"]
            return res, "Success"

    @commands.command(name="steamdb")
    async def _peninjau_gaming_steamdb(
        self, ctx: naoTimesContext, *, args: steamdb_converter = steamdb_converter.show_help()
    ):
        STORE_APP = "https://store.steampowered.com/app/{}/"
        THUMB = "https://cdn.cloudflare.steamstatic.com/steam/apps/{}/header.jpg"

        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

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
            f"{args.kueri}: with opts:\n"
            f">> DLC: {args.add_dlc}\n>> App: {args.add_app}"
            f"\n>> Musik: {args.add_music}"
        )

        results, msg = await self._quick_request(params)
        if not results:
            self.logger.warning(f"{args.kueri}: error\n{msg}")
            return await ctx.send(msg)
        sdb_results = results["results"]
        if not sdb_results:
            self.logger.warning(f"{args.kueri}: not found")
            return await ctx.send("Tidak ada hasil yang cocok")

        def _generate_embed(sdb_data: dict):
            embed = discord.Embed(title=sdb_data["title"], url=STORE_APP.format(sdb_data["id"]))
            description = []
            if "price" in sdb_data:
                description.append("Harga: {}".format(sdb_data["price"]))
            if "user_score" in sdb_data:
                description.append("Skor: {}".format(sdb_data["user_score"]))
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
            developer = ", ".join(sdb_data["developer"]) or "*Tidak ada*"
            publisher = ", ".join(sdb_data["publisher"]) or "*Tidak ada*"
            embed.add_field(
                name="Developer",
                value=f"**Developer**: {developer}\n**Publisher**: {publisher}",
                inline=False,
            )
            embed.add_field(
                name="Kategori",
                value=", ".join(sdb_data["categories"]),
                inline=False,
            )
            embed.add_field(name="Label", value=", ".join(sdb_data["tags"]), inline=False)
            embed.set_footer(
                text="Rilis: {} | {}-{} | Diprakasai oleh SteamDB".format(
                    sdb_data["released"],
                    sdb_data["type"].capitalize(),
                    sdb_data["id"],
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
