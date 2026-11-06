import logging
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.http import KategloError, KategloTipe, kateglo_relasi


class KutubukuKateglo(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Kateglo")

    @app_commands.command(
        name="sinonim",
        description=app_commands.locale_str("Cari sinonim sebuah kata", key="kutubuku.sinonim.description"),
    )
    @app_commands.describe(
        kata=app_commands.locale_str("Kata yang ingin dicari", key="kutubuku.sinonim.option_kata"),
    )
    async def _kutubuku_sinonim(self, inter: discord.Interaction, kata: str):
        """Cari sinonim sebuah kata"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
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
            return await ctx.send(ctx.t("sinonim.not_found", kata=kata))

        self.logger.info(f"Found {len(results_txt)} matches for {kata}")
        URL_KATEGLO = "https://kateglo.com/?mod=dictionary&action=view&phrase={}#panelRelated"

        result = ", ".join(results_txt)
        embed = discord.Embed(
            title=ctx.t("sinonim.embed_title", kata=kata), color=0x81E28D, url=URL_KATEGLO.format(quote(kata))
        )
        embed.set_footer(text=ctx.t("kateglo.footer"))
        if not result:
            embed.add_field(name=kata, value=ctx.t("kateglo.no_result"), inline=False)
            return await ctx.send(embed=embed)

        embed.add_field(name=kata, value=result, inline=False)
        await ctx.send(embed=embed)

    @app_commands.command(
        name="antonim",
        description=app_commands.locale_str("Cari antonim sebuah kata", key="kutubuku.antonim.description"),
    )
    @app_commands.describe(
        kata=app_commands.locale_str("Kata yang ingin dicari", key="kutubuku.antonim.option_kata"),
    )
    async def _kutubuku_antonim(self, inter: discord.Interaction, kata: str):
        """Cari antonim sebuah kata"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
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
            return await ctx.send(ctx.t("antonim.not_found", kata=kata))

        self.logger.info(f"Found {len(results_txt)} matches for {kata}")
        URL_KATEGLO = "https://kateglo.com/?mod=dictionary&action=view&phrase={}#panelRelated"

        result = ", ".join(results_txt)
        embed = discord.Embed(
            title=ctx.t("antonim.embed_title", kata=kata), color=0x81E28D, url=URL_KATEGLO.format(quote(kata))
        )
        embed.set_footer(text=ctx.t("kateglo.footer"))
        if not result:
            embed.add_field(name=kata, value=ctx.t("kateglo.no_result"), inline=False)
            return await ctx.send(embed=embed)

        embed.add_field(name=kata, value=result, inline=False)
        await ctx.send(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuKateglo(bot))
