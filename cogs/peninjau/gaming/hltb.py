import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.paginator import DiscordPaginatorUI


class PeninjauGameHLTB(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.Gaming.HLTB")

    @app_commands.command(
        name="hltb",
        description=app_commands.locale_str(
            "Lihat berapa lama untuk menamatkan sebuah game (HowLongToBeat)", key="peninjau.hltb.description"
        ),
    )
    @app_commands.describe(game_title=app_commands.locale_str("Judul game", key="peninjau.hltb.option"))
    async def _peninjau_gaming_hltb(self, inter: discord.Interaction, game_title: str):
        """Lihat berapa lama untuk menamatkan sebuah game (HowLongToBeat)"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        self.logger.info(f"Searching: {game_title}")
        URL = "https://api.ihateani.me/v1/games/hltb"
        if self.bot.aiosession is None:
            return await ctx.send(ctx.t("hltb.http_unavailable"))
        async with self.bot.aiosession.get(URL, params={"q": game_title}) as resp:
            try:
                data = await resp.json()
            except ValueError:
                self.logger.error(f"{game_title}: An error occured while trying to unpack json data!")
                return await ctx.send(ctx.t("hltb.json_error"))

        hltb_results = data["results"]
        if len(hltb_results) < 1:
            self.logger.warning(f"{game_title}: No results...")
            return await ctx.send(ctx.t("hltb.no_results"))

        def _merge_image(image_url: str):
            if image_url.startswith("/"):
                return f"https://howlongtobeat.com{image_url}"
            return f"https://howlongtobeat.com/{image_url}"

        def _generate_embed(hltb_data: dict):
            embed = discord.Embed(
                title=hltb_data["title"], url=hltb_data["url"], color=hltb_data.get("color", 0x858585)
            )
            embed.set_thumbnail(url=_merge_image(hltb_data["image"]))
            hltbs = hltb_data["hltb"]
            hltb_text = ""
            if hltbs["main"] is not None:
                hltb_text += ctx.t("hltb.main", duration=hltbs["main"])
            if hltbs["main_extra"] is not None:
                hltb_text += ctx.t("hltb.main_extra", duration=hltbs["main_extra"])
            if hltbs["complete"] is not None:
                hltb_text += ctx.t("hltb.complete", duration=hltbs["complete"])
            hltb_text = hltb_text.rstrip("\n")
            hltb_text += ctx.t("hltb.more_info", url=hltb_data["url"])

            embed.add_field(
                name=ctx.t("hltb.field_time"),
                value=hltb_text,
                inline=False,
            )
            stats_data = []
            if hltb_data["stats"]:
                for st_name, st_stats in hltb_data["stats"].items():
                    txt = f"**{st_name.capitalize()}**: {st_stats}"
                    stats_data.append(txt)
            if stats_data != []:
                embed.add_field(name=ctx.t("hltb.field_stats"), value="\n".join(stats_data), inline=False)
            embed.set_footer(
                text=ctx.t("hltb.footer"),
                icon_url="https://howlongtobeat.com/img/hltb_brand.png",
            )
            return embed

        self.logger.info(f"{game_title}: starting paginator...")
        ui_gen = DiscordPaginatorUI(ctx, hltb_results, 30.0)
        ui_gen.attach(_generate_embed)
        await ui_gen.interact()


async def setup(bot: naoTimesBot):
    await bot.add_cog(PeninjauGameHLTB(bot))
