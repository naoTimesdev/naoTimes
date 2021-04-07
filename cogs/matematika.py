import logging

import discord
from discord.ext import commands, tasks

from nthelper.bot import naoTimesBot
from nthelper.kalkuajaib import GagalKalkulasi, KalkulatorAjaib
from nthelper.utils import DiscordPaginator, quote, rgb_to_color
from nthelper.wolfram import WolframAPI, WolframPod


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

    @commands.command(name="wolfram", aliases=["wolframalpha", "wa"])
    async def wolfram_cmd(self, ctx: commands.Context, *, query: str):
        if self.wolfram is None:  # Ignore if no WolframAlpha thing
            return
        results = await self.wolfram.query(query)
        if isinstance(results, str):
            return await ctx.send(results)
        SEARCH_URL = "https://www.wolframalpha.com/input/?i={}"
        QUERY_STRINGIFY = query.replace(" ", "+")

        def _create_embed(pod: WolframPod):
            embed = discord.Embed(title=pod.title, color=rgb_to_color(202, 103, 89))
            embed.set_author(
                name="WolframAlpha",
                url=SEARCH_URL.format(QUERY_STRINGIFY),
                icon_url="https://p.n4o.xyz/i/wa_icon.png",
            )
            embed.description = f"**Kueri**: `{query}`"
            first_image = None
            for n, subpod in enumerate(pod.pods, 1):
                embed.add_field(name=pod.scanner + f" ({n})", value=quote(subpod.plaintext, True))
                if subpod.image and first_image is None:
                    first_image = subpod.image
            if first_image is not None:
                embed.set_image(url=first_image)
            embed.set_footer(
                text="Diprakasai dengan WolframAlpha™", icon_url="https://p.n4o.xyz/i/wa_icon.png"
            )
            return embed

        paginator = DiscordPaginator(self.bot, ctx)
        paginator.checker()
        paginator.breaker()
        paginator.set_generator(_create_embed)
        await paginator.start(results.pods, 30.0)


def setup(bot: naoTimesBot):
    bot.add_cog(Matematika(bot))
