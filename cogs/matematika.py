import logging
import discord
from discord.ext import commands, tasks

from nthelper.bot import naoTimesBot
from nthelper.kalkuajaib import KalkulatorAjaib, GagalKalkulasi
from nthelper.wolfram import WolframAPI


class Matematika(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.kalkulasi = KalkulatorAjaib.kalkulasi
        self.logger = logging.getLogger("cogs.matematika.Matematika")
        wolfram_app_id = self.bot.botconf.get("wolfram", {}).get("app_id")
        if isinstance(wolfram_app_id, str):
            self.logger.info("Creating WolframAlpha connection...")
            self.wolfram = WolframAPI(wolfram_app_id)
        else:
            self.wolfram = None

    def cog_unload(self):
        self.cog_unload_async.start()
        self.cog_unload_async.stop()

    @tasks.loop(seconds=1, count=1)
    async def cog_unload_async(self):
        if self.wolfram is not None:
            self.logger.info("Closing WolframAlpha connection...")
            await self.wolfram.close()

    @commands.command(
        name="kalkulator", aliases=["kalku", "calc", "calculate", "calculator", "kalkulasi", "kalkulasikan"]
    )
    async def kalkulasi_cmd(self, ctx: commands.Context, *, teks: str):
        try:
            hasil = self.kalkulasi(teks)
        except GagalKalkulasi:
            return await ctx.send(f"Gagal melakukan kalkulasi untuk input:\n`{teks}`")
        except SyntaxError:
            return await ctx.send(f"Format penulisan tidak bisa dimengerti:\n`{teks}`")
        except ZeroDivisionError:
            return await ctx.send("Tidak dapat melakukan pembagian dengan dividen 0")

        embed = discord.Embed(title="⚙ Kalkulator", color=0x22A273)
        embed.description = f"▶ `{teks}`\n{hasil}"
        owner = f"{self.bot.owner.name}#{self.bot.owner.discriminator}"
        embed.set_footer(
            text=f"Ini merupakan command experimental, mohon lapor kepada {owner} jika ada masalah."
        )
        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(Matematika(bot))
