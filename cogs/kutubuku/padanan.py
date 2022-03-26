import logging
from typing import List, Literal, NamedTuple, Union
from urllib.parse import quote_plus

import disnake
from bs4 import BeautifulSoup
from bs4.element import NavigableString, ResultSet, Tag
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesAppContext, naoTimesContext
from naotimes.paginator import DiscordPaginatorUI

BSElement = Union[NavigableString, Tag, None]

RanahKataKateglo = Literal[
    "*Umum*",
    "Agama",
    "Agama Islam",
    "Antropologi",
    "Arkeologi",
    "Arsitektur",
    "Asuransi",
    "Biologi",
    "Ekonomi",
    "Elektronika",
    "Farmasi",
    "Filsafat",
    "Fisika",
    "Fotografi",
    "Geologi",
    "Hukum",
    "Kedokteran",
    "Kedokteran Hewan",
    "Keuangan",
    "Kimia",
    "Komunikasi Massa",
    "Konstruksi",
    "Kristen",
    "Linguistik",
    "Manajemen",
    "Matematika",
    "Mesin",
    "Militer",
    "Minyak & Gas",
    "Olahraga",
    "Otomotif",
    "Pajak",
    "Pariwisata",
    "Paten",
    "Pelayaran",
    "Pelelangan",
    "Pendidikan",
    "Penerbangan",
    "Perbankan",
    "Perhutanan",
    "Perikanan",
    "Perkapalan",
    "Pertambangan",
    "Pertanian",
    "Peternakan",
    "Politik",
    "Psikologi",
    "Saham",
    "Sastra",
    "Sosiologi",
    "Statistika",
    "Teknik",
    "Teknik Kimia",
    "Teknologi Informasi",
    "Transportasi",
]


class PadananKata(NamedTuple):
    id: str
    basis: str
    padanan: str
    ranah: RanahKataKateglo


class PadananCari(NamedTuple):
    kueri: str
    hasil: List[PadananKata]


class KutubukuPadananAsing(commands.Cog):
    BASE_API = "https://kateglo.com/"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.PadananAsing")

    def _build_url(self, id_kata: str):
        params = {
            "mod": "glossary",
            "op": "1",
            "phrase": quote_plus(id_kata),
            "dc": "",
            "lang": "",
            "src": "",
            "srch": "Cari",
        }
        build_params = [f"{k}={v}" for k, v in params.items()]
        return f"{self.BASE_API}?{'&'.join(build_params)}"

    async def _cari_padanan_asing(self, kata_asing: str) -> PadananCari:
        """
        Mencari padanan asing dari kata asing menggunakan API Kateglo

        :param kata_asing: Kata asing
        :return: Padanan
        """
        QUERY_PAYLOAD = {
            "mod": "glossary",
            "op": "1",
            "phrase": kata_asing,
            "dc": "",
            "lang": "",
            "src": "",
            "srch": "Cari",
        }
        async with self.bot.aiosession.get(self.BASE_API, params=QUERY_PAYLOAD) as resp:
            if resp.status != 200:
                self.logger.error(f"{resp.status} {resp.reason}")
                return PadananCari(kata_asing, [])
            html_page = await resp.text()

        soup = BeautifulSoup(html_page, "html.parser")
        table_body = soup.find("table", {"class": "table table-condensed table-hover"})
        all_tr_sections: ResultSet = table_body.find_all("tr", recursive=False)

        all_results: List[PadananKata] = []
        for nn, tr_sect in enumerate(all_tr_sections):
            if nn == 00:
                continue
            tds = tr_sect.find_all("td", recursive=False)

            asing = tds[1].text.strip()
            indonesia = tds[2].text.strip()
            ranah_kata = tds[4].text.strip().replace("&amp;", "&")
            all_results.append(PadananKata(f"{asing}-{nn}", asing, indonesia, ranah_kata))
        return PadananCari(kata_asing, all_results)

    def _design_padanan_embed(self, hasil: PadananKata):
        embed = disnake.Embed(color=0x110063)
        url_data = self._build_url(hasil.basis)
        embed.set_author(
            name=hasil.basis,
            url=url_data,
            icon_url="https://p.ihateani.me/mkafjgqo.png",
        )
        description_part = []
        description_part.append(f"**Istilah Asing**: {hasil.basis}")
        description_part.append(f"**Istilah Indonesia**: {hasil.padanan}")
        description_part.append(f"**Ranah kata**: {hasil.ranah}")
        embed.description = "\n".join(description_part)

        embed.set_footer(text="Diprakasai dengan SPAI + Kateglo")
        return embed

    @commands.command(name="padanan", aliases=["padananasing"])
    async def _kutubuku_padanan(self, ctx: naoTimesContext, *, kata_pencarian: str):
        kata_pencarian = kata_pencarian.lower()
        self.logger.info(f"Querying: {kata_pencarian}")

        hasil_data = await self._cari_padanan_asing(kata_pencarian)
        if len(hasil_data.hasil) < 1:
            await ctx.send(f"Tidak dapat menemukan hasil yang cocok untuk kata `{kata_pencarian}` di SPAI!")
            return

        ui_paginate = DiscordPaginatorUI(ctx, hasil_data.hasil, 25.0)
        ui_paginate.attach(self._design_padanan_embed)
        await ui_paginate.interact()

    @commands.slash_command(name="padanan")
    async def _kutubuku_padanan_slash(self, ctx: naoTimesAppContext, kata: str):
        """Mencari padanan bahasa Indonesia untuk bahasa asing.

        Parameters
        ----------
        kata: Padanan kata yang ingin dicari
        """
        kata_pencarian = kata.lower()
        self.logger.info(f"Querying: {kata_pencarian}")
        await ctx.defer()

        hasil_data = await self._cari_padanan_asing(kata_pencarian)
        if len(hasil_data.hasil) < 1:
            await ctx.send(f"Tidak dapat menemukan hasil yang cocok untuk kata `{kata_pencarian}` di SPAI!")
            return

        gen_first = self._design_padanan_embed(hasil_data.hasil[0])
        await ctx.send(embed=gen_first)


def setup(bot: naoTimesBot):
    bot.add_cog(KutubukuPadananAsing(bot))
