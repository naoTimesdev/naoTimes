from __future__ import annotations

import logging
from enum import Enum
from functools import partial as ftpartial
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.http.tesaurus import Lema, LemaEntri, TerjadiKesalahan, TesaurusGalat, TidakDitemukan
from naotimes.paginator import DiscordPaginatorUI

_IKON = "https://raw.githubusercontent.com/noaione/tesaurus-python/master/assets/tesaurustematis_logo.png"


class KelasKata(str, Enum):
    Adjektiva = "adjektiva"
    Adverbia = "adverbia"
    Konjungsi = "konjungsi"
    Nomina = "nomina"
    Numeralia = "numeralia"
    Partikel = "partikel"
    Verba = "verba"

    def __str__(self):
        return self.value

    @classmethod
    def to_list(cls: type[KelasKata]) -> list[str]:
        return [
            cls.Adjektiva.value,
            cls.Adverbia.value,
            cls.Konjungsi.value,
            cls.Nomina.value,
            cls.Numeralia.value,
            cls.Partikel.value,
            cls.Verba.value,
        ]


class KutubukuTesaurus(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Tesaurus")

    def _generate_embed(
        self,
        dataset: Lema,
        position: int,
        total_data: int,
        kelas_kata: str,
        kata: str,
        t: Callable[..., str],
    ) -> discord.Embed:
        gen_title = t("tesaurus.embed_title", label=dataset.label, position=position + 1, total=total_data, kata=kata)
        build_url = f"http://tesaurus.kemdikbud.go.id/tematis/lema/{kata}/{kelas_kata}"
        embed = discord.Embed(title=gen_title, colour=0xAF2A2A)
        embed.set_author(
            name=t("tesaurus.author"),
            icon_url=_IKON,
            url=build_url,
        )
        starting_desc = t("tesaurus.kelas_kata", kelas=kelas_kata)
        if dataset.sublabel:
            starting_desc += "\n" + t("tesaurus.sublabel", sublabel=dataset.sublabel)
        starting_desc += f"\n\n{', '.join(self.highlights(lema, kata) for lema in dataset.lema)}"
        embed.description = starting_desc
        embed.set_footer(text=t("tesaurus.footer"), icon_url=_IKON)
        return embed

    @staticmethod
    def _group_lema(dataset: list[LemaEntri]) -> dict[str, list[LemaEntri]]:
        grouped: dict[str, list[LemaEntri]] = {}
        for data in dataset:
            key = data.kelas_kata
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(data)
        return grouped

    @staticmethod
    def highlights(text: str, hi: str) -> str:
        tokenize = text.split(" ")
        for n, token in enumerate(tokenize):
            if hi in token:
                tokenize[n] = token.replace(hi, f"__**{hi}**__")
        return " ".join(tokenize)

    @app_commands.command(
        name="tesaurus",
        description=app_commands.locale_str(
            "Cari sinonim/antonim sebuah kata bahasa Indonesia",
            key="kutubuku.tesaurus.description",
        ),
    )
    @app_commands.describe(
        kata=app_commands.locale_str("Kata yang ingin dicari", key="kutubuku.tesaurus.option_kata"),
        kelas=app_commands.locale_str(
            "Batasi hasil ke kelas kata tertentu",
            key="kutubuku.tesaurus.option_kelas",
        ),
    )
    async def _tesaurus_slash_cmd(self, inter: discord.Interaction, kata: str, kelas: KelasKata | None = None):
        """Cari sinonim/antonim sebuah kata bahasa Indonesia"""
        ctx = await self.bot.get_context(inter)
        real_kata = kata
        kelas_kata = kelas.value if kelas is not None else None
        self.logger.info(f"Mencari kata `{real_kata}` dengan kelas kata `{kelas_kata}`")
        await ctx.defer()
        tesaurus = self.bot.tesaurus
        if tesaurus is None:
            return await ctx.send(ctx.t("tesaurus.unavailable"))

        try:
            if kelas_kata is None:
                await tesaurus.cari(real_kata)
            else:
                await tesaurus.cari(real_kata, kelas_kata)
        except TidakDitemukan:
            self.logger.error(f"Tidak dapat hasil untuk pencarian {kata}")
            if kelas_kata:
                err_msg = ctx.t("tesaurus.not_found_kelas", kata=real_kata, kelas=kelas_kata)
            else:
                err_msg = ctx.t("tesaurus.not_found", kata=real_kata)
            return await ctx.send(err_msg)
        except TerjadiKesalahan:
            self.logger.error(f"Tidak dapat menghubungi Tesaurus Tematis untuk pencarian {kata}")
            return await ctx.send(ctx.t("tesaurus.connection_failed"))
        except TesaurusGalat as teg:
            self.logger.error(f"Terjadi kesalahan ketika melakukan pencarian {kata}")
            return await ctx.send(ctx.t("tesaurus.internal_error", error=str(teg)))

        if len(tesaurus.entri) < 1:
            return await ctx.send(ctx.t("tesaurus.no_results"))

        if tesaurus.kelas_kata:
            self.logger.info(f"Melakukan mode kelas kata untuk pencarian {kata}")
            embed_gen = ftpartial(
                self._generate_embed,
                total_data=len(tesaurus.entri[0].entri),
                kelas_kata=tesaurus.kelas_kata,
                kata=tesaurus.kata,
                t=ctx.t,
            )
            paginator = DiscordPaginatorUI(ctx, tesaurus.entri[0].entri)
            paginator.attach(embed_gen)
            await paginator.interact(30.0)
            return

        emote_list = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
        ]

        grouped_entri = self._group_lema(tesaurus.entri)

        def _generate_main(_):
            build_url = f"http://tesaurus.kemdikbud.go.id/tematis/lema/{real_kata}"
            embed = discord.Embed(title=real_kata, colour=0xAF2A2A)
            embed.set_author(
                name="Tesaurus Tematis",
                icon_url=_IKON,
                url=build_url,
            )
            val = ""
            for n, data in enumerate(grouped_entri.keys()):
                val += f"{emote_list[n]} **{data}**\n"
            embed.add_field(name=ctx.t("tesaurus.select_kelas"), value=val)
            embed.set_footer(text=ctx.t("tesaurus.footer"), icon_url=_IKON)
            return embed

        def generator_tesaurus(dataset, _, __: discord.Message, view: DiscordPaginatorUI, emote: str):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return discord.Embed(description=ctx.t("tesaurus.kelas_not_found"))
            kelas_kata_group: list[LemaEntri] = dataset[list(dataset.keys())[emote_pos]]
            embed_gen = ftpartial(
                self._generate_embed,
                total_data=len(kelas_kata_group[0].entri),
                kelas_kata=kelas_kata_group[0].kelas_kata,
                kata=tesaurus.kata,
                t=ctx.t,
            )
            paginator = DiscordPaginatorUI(ctx, kelas_kata_group[0].entri)
            paginator.attach(embed_gen)
            paginator.parent = view
            paginator.timeout = 30.0
            return paginator

        main_gen = DiscordPaginatorUI(ctx, [grouped_entri])
        main_gen.attach(_generate_main)
        for idx, namae in enumerate(list(grouped_entri.keys())):
            emote = emote_list[idx]
            handler_gen = ftpartial(generator_tesaurus, emote=emote)
            main_gen.add_handler(namae, lambda x: True, handler_gen, emoji=emote)
        await main_gen.interact(30.0)


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuTesaurus(bot))
