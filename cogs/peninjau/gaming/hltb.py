import logging

import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.paginator import DiscordPaginatorUI


class PeninjauGameHLTB(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.Gaming.HLTB")

    @commands.command(name="hltb", aliases=["howlongtobeat"])
    @commands.guild_only()
    async def _peninjau_gaming_hltb(self, ctx: naoTimesContext, *, game_title: str):
        self.logger.info(f"Searching: {game_title}")
        URL = "https://api.ihateani.me/v1/games/hltb"
        async with self.bot.aiosession.get(URL, params={"q": game_title}) as resp:
            try:
                data = await resp.json()
            except ValueError:
                self.logger.error(f"{game_title}: An error occured while trying to unpack json data!")
                return await ctx.send("Terjadi kesalahan ketika meminta data JSON dari HLTB")

        hltb_results = data["results"]
        if len(hltb_results) < 1:
            self.logger.warning(f"{game_title}: No results...")
            return await ctx.send("Tidak ada hasil!")

        def _merge_image(image_url: str):
            if image_url.startswith("/"):
                return f"https://howlongtobeat.com{image_url}"
            return f"https://howlongtobeat.com/{image_url}"

        def _generate_embed(hltb_data: dict):
            embed = disnake.Embed(
                title=hltb_data["title"], url=hltb_data["url"], color=hltb_data.get("color", 0x858585)
            )
            embed.set_thumbnail(url=_merge_image(hltb_data["image"]))
            hltbs = hltb_data["hltb"]
            hltb_text = ""
            if hltbs["main"] is not None:
                hltb_text += "**Bagian Utama**: {}\n".format(hltbs["main"])
            if hltbs["main_extra"] is not None:
                hltb_text += "**Bagian Utama + Ekstra**: {}\n".format(hltbs["main_extra"])
            if hltbs["complete"] is not None:
                hltb_text += "**Perfeksionis**: {}\n".format(hltbs["complete"])
            hltb_text = hltb_text.rstrip("\n")
            hltb_text += f"\n\n*(Info lebih lanjut? [Klik Di sini]({hltb_data['url']}))*"  # noqa: E501

            embed.add_field(
                name="Seberapa lama untuk diselesaikan?",
                value=hltb_text,
                inline=False,
            )
            stats_data = []
            if hltb_data["stats"]:
                for st_name, st_stats in hltb_data["stats"].items():
                    txt = f"**{st_name.capitalize()}**: {st_stats}"
                    stats_data.append(txt)
            if stats_data != []:
                embed.add_field(name="Statistik", value="\n".join(stats_data), inline=False)
            embed.set_footer(
                text="Diprakasi oleh HowLongToBeat.com",
                icon_url="https://howlongtobeat.com/img/hltb_brand.png",
            )
            return embed

        self.logger.info(f"{game_title}: starting paginator...")
        ui_gen = DiscordPaginatorUI(ctx, hltb_results, 30.0)
        ui_gen.attach(_generate_embed)
        await ui_gen.interact()


def setup(bot: naoTimesBot):
    bot.add_cog(PeninjauGameHLTB(bot))
