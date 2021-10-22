import logging
from urllib.parse import quote

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.http import KategloError, KategloTipe, kateglo_relasi


class KutubukuKateglo(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Kateglo")

    @commands.command(name="sinonim", aliases=["persamaankata", "persamaan"])
    async def _kutubuku_sinonim(self, ctx: naoTimesContext, *, kata: str):
        self.logger.info(f"Searching: {kata}")
        try:
            results = await kateglo_relasi(kata)
        except KategloError as ke:
            return await ctx.send(str(ke))

        match_sinonim = filter(lambda x: x.tipe == KategloTipe.Sinonim, results)
        results_txt = []
        for sinonim in match_sinonim:
            results_txt.append(sinonim.kata)

        if len(results_txt) < 1:
            self.logger.warning(f"can't find any match for {kata}")
            return await ctx.send(f"Tidak ada sinonim yang ditemukan untuk kata `{kata}`")

        self.logger.info(f"Found {len(results_txt)} matches for {kata}")
        URL_KATEGLO = "https://kateglo.com/?mod=dictionary&action=view&phrase={}#panelRelated"

        result = ", ".join(results_txt)
        embed = discord.Embed(title=f"Sinonim: {kata}", color=0x81E28D, url=URL_KATEGLO.format(quote(kata)))
        embed.set_footer(text="Diprakasai oleh Kateglo.com")
        if not result:
            embed.add_field(name=kata, value="Tidak ada hasil", inline=False)
            return await ctx.send(embed=embed)

        embed.add_field(name=kata, value=result, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="antonim", aliases=["lawankata"])
    async def _kutubuku_antonim(self, ctx: naoTimesContext, *, kata: str):
        self.logger.info(f"Searching: {kata}")
        try:
            results = await kateglo_relasi(kata)
        except KategloError as ke:
            return await ctx.send(str(ke))

        match_antonim = filter(lambda x: x.tipe == KategloTipe.Antonim, results)
        results_txt = []
        for antonim in match_antonim:
            results_txt.append(antonim.kata)

        if len(results_txt) < 1:
            self.logger.warning(f"can't find any match for {kata}")
            return await ctx.send(f"Tidak ada sinonim yang ditemukan untuk kata `{kata}`")

        self.logger.info(f"Found {len(results_txt)} matches for {kata}")
        URL_KATEGLO = "https://kateglo.com/?mod=dictionary&action=view&phrase={}#panelRelated"

        result = ", ".join(results_txt)
        embed = discord.Embed(title=f"Antonim: {kata}", color=0x81E28D, url=URL_KATEGLO.format(quote(kata)))
        embed.set_footer(text="Diprakasai oleh Kateglo.com")
        if not result:
            embed.add_field(name=kata, value="Tidak ada hasil", inline=False)
            return await ctx.send(embed=embed)

        embed.add_field(name=kata, value=result, inline=False)
        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(KutubukuKateglo(bot))
