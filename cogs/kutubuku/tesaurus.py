import logging
from functools import partial as ftpartial
from typing import Dict, List

import discord
from discord.ext import app, commands
from tesaurus import Lema, LemaEntri, TerjadiKesalahan, TesaurusGalat, TidakDitemukan

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.paginator import DiscordPaginator, DiscordPaginatorUI

_IKON = "https://raw.githubusercontent.com/noaione/tesaurus-python/master/assets/tesaurustematis_logo.png"
_KELAS_KATA = ["adjektiva", "adverbia", "konjungsi", "nomina", "numeralia", "partikel", "verba"]


class KutubukuTesaurus(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Tesaurus")

    def _generate_embed(
        self, dataset: Lema, position: int, total_data: int, kelas_kata: str, kata: str
    ) -> discord.Embed:
        gen_title = f"{dataset.label} ({position + 1}/{total_data}) [{kata}]"
        build_url = f"http://tesaurus.kemdikbud.go.id/tematis/lema/{kata}/{kelas_kata}"
        embed = discord.Embed(title=gen_title, colour=0xAF2A2A)
        embed.set_author(
            name="Tesaurus Tematis",
            icon_url=_IKON,
            url=build_url,
        )
        starting_desc = f"**Kelas Kata:** {kelas_kata}"
        if dataset.sublabel:
            starting_desc += f"\n**Sublabel**: {dataset.sublabel}"
        starting_desc += f"\n\n{', '.join(self.highlights(lema, kata) for lema in dataset.lema)}"
        embed.description = starting_desc
        embed.set_footer(text="Diprakasai oleh Tesaurus Tematis", icon_url=_IKON)
        return embed

    @staticmethod
    def _group_lema(dataset: List[LemaEntri]) -> Dict[str, List[LemaEntri]]:
        grouped: Dict[str, List[LemaEntri]] = {}
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

    @app.slash_command(
        name="tesaurus",
        description="Cari sinonim/antonim sebuah kata bahasa Indonesia",
    )
    @app.option("kata", str, description="Kata yang ingin dicari")
    @app.option(
        "kelas",
        str,
        description="Batasi hasil ke kelas kata tertentu",
        choices=list(map(lambda x: app.OptionChoice(x, x.capitalize()), _KELAS_KATA)),
        required=False,
    )
    async def _tesaurus_slash_cmd(self, ctx: app.ApplicationContext, kata: str, kelas: str):
        if not kata:
            return await ctx.send("Mohon berikan kata yang ingin dicari!")

        self.logger.info(f"Mencari kata `{kata}` dengan kelas kata `{kelas}`")
        await ctx.defer()

        try:
            await self.bot.tesaurus.cari(kata, kelas)
        except TidakDitemukan:
            self.logger.error(f"Tidak dapat hasil untuk pencarian {kata}")
            err_msg = f"Tidak dapat menemukan kata `{kata}`"
            if kelas:
                err_msg += f" pada kelas kata `{kelas}`"
            return await ctx.send(err_msg)
        except TerjadiKesalahan:
            self.logger.error(f"Tidak dapat menghubungi Tesaurus Tematis untuk pencarian {kata}")
            return await ctx.send("Gagal menhubungi Tesaurus Tematis, mohon coba sesaat lagi.")
        except TesaurusGalat as teg:
            self.logger.error(f"Terjadi kesalahan ketika melakukan pencarian {kata}")
            return await ctx.send(f"Terjadi kesalahan internal :(\nGalat: `{str(teg)}`")

        if len(self.bot.tesaurus.entri) < 1:
            return await ctx.send("Tidak dapat hasil untuk pencarian anda!")

        first_entry = self.bot.tesaurus.entri[0]
        lema_entri = first_entry.entri[0]
        kelas_kata = first_entry.kelas_kata

        embed = self._generate_embed(lema_entri, 0, 1, kelas_kata, kata)
        await ctx.send(embed=embed)

    @commands.command(name="tesaurus")
    async def _tesaurus_cmd(self, ctx: naoTimesContext, *, kata: str):
        if not kata:
            return await ctx.send("Mohon berikan kata yang ingin dicari!")

        split_kata = kata.split(" ")
        tes_kelas = split_kata[0].lower()
        kelas_kata = None
        real_kata = kata
        if tes_kelas in _KELAS_KATA:
            kelas_kata = tes_kelas
            real_kata = " ".join(split_kata[1:])
        self.logger.info(f"Mencari kata `{real_kata}` dengan kelas kata `{kelas_kata}`")

        try:
            await self.bot.tesaurus.cari(real_kata, kelas_kata)
        except TidakDitemukan:
            self.logger.error(f"Tidak dapat hasil untuk pencarian {kata}")
            err_msg = f"Tidak dapat menemukan kata `{real_kata}`"
            if kelas_kata:
                err_msg += f" pada kelas kata `{kelas_kata}`"
            return await ctx.send(err_msg)
        except TerjadiKesalahan:
            self.logger.error(f"Tidak dapat menghubungi Tesaurus Tematis untuk pencarian {kata}")
            return await ctx.send("Gagal menhubungi Tesaurus Tematis, mohon coba sesaat lagi.")
        except TesaurusGalat as teg:
            self.logger.error(f"Terjadi kesalahan ketika melakukan pencarian {kata}")
            return await ctx.send(f"Terjadi kesalahan internal :(\nGalat: `{str(teg)}`")

        if len(self.bot.tesaurus.entri) < 1:
            return await ctx.send("Tidak dapat hasil untuk pencarian anda!")

        if self.bot.tesaurus.kelas_kata:
            self.logger.info(f"Melakukan mode kelas kata untuk pencarian {kata}")
            embed_gen = ftpartial(
                self._generate_embed,
                total_data=len(self.bot.tesaurus.entri[0].entri),
                kelas_kata=self.bot.tesaurus.kelas_kata,
                kata=self.bot.tesaurus.kata,
            )
            paginator = DiscordPaginatorUI(ctx, self.bot.tesaurus.entri[0].entri)
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

        grouped_entri = self._group_lema(self.bot.tesaurus.entri)

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
            embed.add_field(name="Pilih Kelas Kata", value=val)
            embed.set_footer(text="Diprakasai oleh Tesaurus Tematis", icon_url=_IKON)
            return embed

        async def generator_tesaurus(dataset, _, message: discord.Message, emote: str):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return None, message
            kelas_kata_group: List[LemaEntri] = dataset[list(dataset.keys())[emote_pos]]
            embed_gen = ftpartial(
                self._generate_embed,
                total_data=len(kelas_kata_group[0].entri),
                kelas_kata=kelas_kata_group[0].kelas_kata,
                kata=self.bot.tesaurus.kata,
            )
            paginator = DiscordPaginator(self.bot, ctx, kelas_kata_group[0].entri)
            paginator.set_generator(embed_gen)
            paginator.remove_at_trashed = False
            timeout = await paginator.paginate(30.0, message)
            return None, message, timeout

        main_gen = DiscordPaginator(self.bot, ctx, [grouped_entri])
        main_gen.remove_at_trashed = False
        main_gen.set_generator(_generate_main)
        for n, _ in enumerate(list(grouped_entri.keys())):
            main_gen.add_handler(emote_list[n], lambda x: True, generator_tesaurus)
        await main_gen.paginate(30.0)


def setup(bot: naoTimesBot):
    bot.add_cog(KutubukuTesaurus(bot))
