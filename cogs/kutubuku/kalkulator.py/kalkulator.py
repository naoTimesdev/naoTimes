import logging

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.kalkuajaib import GagalKalkulasi, KalkulatorAjaib


class KutubukuKalkulator(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Kalkulator")

    @commands.command(
        name="kalkulator", aliases=["kalku", "calc", "calculate", "calculator", "kalkulasi", "kalkulasikan"]
    )
    async def _kutubuku_kalkulator(self, ctx: naoTimesContext, *, teks: str):
        try:
            hasil = KalkulatorAjaib.kalkulasi(teks)
        except GagalKalkulasi:
            return await ctx.send(f"Gagal melakukan kalkulasi untuk input:\n`{teks}`")
        except SyntaxError:
            return await ctx.send(f"Format penulisan tidak bisa dimengerti:\n`{teks}`")
        except ZeroDivisionError:
            return await ctx.send("Tidak dapat melakukan pembagian dengan dividen 0")

        embed = discord.Embed(title="⚙ Kalkulator", color=0x22A273)
        embed.description = f"▶ `{teks}`\n{hasil}"
        embed.set_footer(
            text=f"Ini merupakan command experimental, mohon lapor kepada {str(self.bot._owner)} jika ada masalah."
        )
        await ctx.send(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuKalkulator(bot))
