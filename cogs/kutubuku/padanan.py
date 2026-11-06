import logging
from dataclasses import dataclass
from functools import partial
from typing import Callable
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.paginator import DiscordPaginatorUI


@dataclass
class PadananKata:
    id: str
    basis: str
    padanan: str
    ranah: str


@dataclass
class PadananCari:
    kueri: str
    hasil: list[PadananKata]


class KutubukuPadananAsing(commands.Cog):
    BASE_API = "https://kateglo.org/api/publik/glosarium"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.PadananAsing")

    def _build_url(self, id_kata: str):
        return f"{self.BASE_API}/detail/{quote(id_kata, safe='')}"

    async def _cari_padanan_asing(self, kata_asing: str) -> PadananCari:
        """
        Mencari padanan asing dari kata asing menggunakan API Kateglo

        :param kata_asing: Kata asing
        :return: Padanan
        """
        if self.bot.aiosession is None:
            return PadananCari(kata_asing, [])
        url_cari = f"{self.BASE_API}/cari/{quote(kata_asing, safe='')}"
        async with self.bot.aiosession.get(url_cari, params={"limit": "100"}) as resp:
            if resp.status != 200:
                self.logger.error(f"{resp.status} {resp.reason}")
                return PadananCari(kata_asing, [])
            response_data = await resp.json()

        if not isinstance(response_data, dict):
            return PadananCari(kata_asing, [])
        records = response_data.get("data")
        if not isinstance(records, list):
            records = response_data.get("persis")
        if not isinstance(records, list):
            return PadananCari(kata_asing, [])

        all_results: list[PadananKata] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            asing = record.get("asing")
            indonesia = record.get("indonesia")
            if not isinstance(asing, str) or not isinstance(indonesia, str):
                continue
            bidang = record.get("bidang")
            ranah_kata = bidang if isinstance(bidang, str) and bidang else "*Umum*"
            record_id = record.get("id")
            id_kata = str(record_id) if isinstance(record_id, int | str) else f"{asing}-{index}"
            all_results.append(PadananKata(id_kata, asing, indonesia, ranah_kata))
        return PadananCari(kata_asing, all_results)

    def _design_padanan_embed(self, hasil: PadananKata, t: Callable[..., str]):
        embed = discord.Embed(color=0x110063)
        url_data = self._build_url(hasil.basis)
        embed.set_author(
            name=hasil.basis,
            url=url_data,
            icon_url="https://p.ihateani.me/ewwsfdfd.png",
        )
        description_part = []
        description_part.append(t("padanan.foreign_term", value=hasil.basis))
        description_part.append(t("padanan.indonesian_term", value=hasil.padanan))
        description_part.append(t("padanan.domain", value=hasil.ranah))
        embed.description = "\n".join(description_part)

        embed.set_footer(text=t("padanan.footer"))
        return embed

    @app_commands.command(
        name="padanan",
        description=app_commands.locale_str(
            "Mencari padanan bahasa Indonesia untuk bahasa asing.",
            key="kutubuku.padanan.description",
        ),
    )
    @app_commands.describe(
        kata=app_commands.locale_str("Padanan kata yang ingin dicari", key="kutubuku.padanan.option_kata"),
    )
    async def _kutubuku_padanan_slash(self, inter: discord.Interaction, kata: str):
        """Mencari padanan bahasa Indonesia untuk bahasa asing."""
        ctx = await self.bot.get_context(inter)
        kata_pencarian = kata.lower()
        self.logger.info(f"Querying: {kata_pencarian}")
        await ctx.defer()

        hasil_data = await self._cari_padanan_asing(kata_pencarian)
        if len(hasil_data.hasil) < 1:
            await ctx.send(ctx.t("padanan.not_found", kata=kata_pencarian))
            return

        ui_paginate = DiscordPaginatorUI(ctx, hasil_data.hasil, 25.0)
        ui_paginate.attach(partial(self._design_padanan_embed, t=ctx.t))
        await ui_paginate.interact()


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuPadananAsing(bot))
