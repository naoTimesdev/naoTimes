import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.kalkuajaib import GagalKalkulasi, KalkulatorAjaib


class KutubukuKalkulator(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Kalkulator")

    @app_commands.command(
        name="kalkulator",
        description=app_commands.locale_str("Kalkulator ajaib", key="kutubuku.kalkulator.description"),
    )
    @app_commands.describe(
        teks=app_commands.locale_str(
            "Ekspresi matematika yang ingin dihitung",
            key="kutubuku.kalkulator.option_teks",
        ),
    )
    async def _kutubuku_kalkulator(self, inter: discord.Interaction, teks: str):
        """Kalkulator ajaib"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        try:
            hasil = KalkulatorAjaib.kalkulasi(teks)
        except GagalKalkulasi:
            return await ctx.send(ctx.t("kalkulator.failed", teks=teks))
        except SyntaxError:
            return await ctx.send(ctx.t("kalkulator.syntax_error", teks=teks))
        except ZeroDivisionError:
            return await ctx.send(ctx.t("kalkulator.zero_division"))

        embed = discord.Embed(title=ctx.t("kalkulator.embed_title"), color=0x22A273)
        embed.description = ctx.t("kalkulator.embed_description", teks=teks, hasil=hasil)
        embed.set_footer(text=ctx.t("kalkulator.experimental_footer", owner=str(self.bot._owner)))
        await ctx.send(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuKalkulator(bot))
