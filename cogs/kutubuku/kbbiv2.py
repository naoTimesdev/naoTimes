import logging
from functools import partial
from typing import List, Optional

import arrow
import discord
from discord.ext import app, commands, tasks
from kbbi.kbbi import BatasSehari, TerjadiKesalahan, TidakDitemukan

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.http import GagalKoneksi
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import cutoff_text


class KBBIDictBase(object):
    def __getitem__(self, key: str):
        _name = type(self).__name__
        attr = getattr(self, key, None)
        if attr is None:
            raise KeyError(f"`{key}` not found in this `{_name}` class")
        return attr

    def __repr__(self):
        _name = type(self).__name__
        base_data = "<" + _name
        for key in self.__dict__:
            value = getattr(self, key, None)
            if not value:
                continue
            if isinstance(value, str):
                value = f'"{value}"'
            keys = key.split("_")
            nice_key = []
            for k in keys:
                nice_key.append(k.capitalize())
            nk = "".join(nice_key)
            base_data += f" {nk}={value}"
        base_data += ">"
        return base_data


class KBBIKelas(KBBIDictBase):
    kode: str
    nama: str
    deskripsi: str

    def __init__(self, kelas: dict):
        for key, value in kelas.items():
            if value:
                setattr(self, key, value)


class KBBIEtimologi(KBBIDictBase):
    bahasa: str
    kelas: List[str] = []
    asal_kata: str
    pelafalan: str
    arti: List[str] = []

    def __init__(self, etimologi: dict):
        for key, value in etimologi.items():
            if value:
                setattr(self, key, value)

    def __str__(self):
        base = f"[{self.bahasa}]"
        if self.kelas:
            base += f" {self.kelas}"
        if self.asal_kata:
            base += f" {self.asal_kata}"
        if self.pelafalan:
            base += f" {self.pelafalan}"
        if self.arti:
            base += ": " + "; ".join(self.arti)
        return base


class KBBIMakna(KBBIDictBase):
    kelas: List[KBBIKelas] = []
    submakna: List[str] = []
    info: Optional[str] = None
    contoh: List[str] = []

    def __init__(self, makna: dict):
        _SPECIAL_KEY = {
            "kelas": [KBBIKelas],
        }
        for key, value in makna.items():
            if key in _SPECIAL_KEY and value:
                _SP = _SPECIAL_KEY[key]
                if isinstance(_SP, list):
                    concat = []
                    for val in value:
                        if value:
                            concat.append(_SP[0](val))
                    setattr(self, key, concat)
                else:
                    if value:
                        setattr(self, key, _SP(value))
                continue
            if value:
                setattr(self, key, value)

    def __str__(self):
        all_kelas = []
        for kelas in self.kelas:
            all_kelas.append(f"*({kelas.kode})*")
        base = " ".join(all_kelas)
        if base:
            base += " "
        base += "; ".join(self.submakna)
        if self.info:
            base += f" {self.info}"
        return base


class KBBIEntri(KBBIDictBase):
    nama: str
    nomor: Optional[str] = None
    kata_dasar: List[str] = []
    pelafalan: Optional[str] = None
    bentuk_tidak_baku: List[str] = []
    varian: List[str] = []
    makna: List[KBBIMakna] = []
    etimologi: Optional[KBBIEtimologi] = None

    # Terkait
    kata_turunan: List[str] = []
    gabungan_kata: List[str] = []
    peribahasa: List[str] = []
    idiom: List[str] = []

    def __init__(self, makna: dict):
        _SPECIAL_KEY = {
            "makna": [KBBIMakna],
            "etimologi": KBBIEtimologi,
        }
        for key, value in makna.items():
            if key in _SPECIAL_KEY and value:
                _SP = _SPECIAL_KEY[key]
                if isinstance(_SP, list):
                    concat = []
                    for val in value:
                        if value:
                            concat.append(_SP[0](val))
                    setattr(self, key, concat)
                else:
                    if value:
                        setattr(self, key, _SP(value))
                continue
            if value:
                setattr(self, key, value)

    def __str__(self):
        base = f"{self.nama}"
        if self.nomor:
            base += f" ({self.nomor})"
        return base


class KBBIHasil:
    """
    A attribute based for KBBI result.
    """

    kueri: str
    pranala: str
    entri: List[KBBIEntri]

    def __init__(self, kueri: str, pranala: str, entries: List[dict]):
        self.kueri = kueri
        self.pranala = pranala
        _entri_parsed: List[KBBIEntri] = []
        for entri in entries:
            _entri = KBBIEntri(entri)
            _entri_parsed.append(_entri)
        self.entri = _entri_parsed

    def __repr__(self):
        text_base = f'<KBBIHasil Kueri="{self.kueri}" Entri=['
        all_name = []
        for entri in self.entri:
            all_name.append(entri.nama)
        text_base += ", ".join(all_name)
        text_base += "]>"
        return text_base

    def __iter__(self):
        for entri in self.entri:
            yield entri

    def __getitem__(self, key: int):
        if not isinstance(key, int):
            raise ValueError("`key` must be an integer")
        return self.entri[key]


class KutubukuKBBIv2(commands.Cog):
    """
    Version 2 of KBBI cogs module.
    This is a imporved version of KBBI module
    and less scuffed.
    """

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.KBBIv2")
        self._use_auth = self.bot.kbbi.terautentikasi
        self._first_run = True

        self._kutubuku_kbbi_check_auth.start()

    def cog_unload(self):
        self.logger.info("Unloading cog, cancelling tasks...")
        self._kutubuku_kbbi_check_auth.cancel()

    @staticmethod
    def _highlight_specific(word_data: str, highlight: str):
        tokenized = word_data.split()
        for index, word in enumerate(tokenized):
            if highlight in word:
                if word.endswith("; "):
                    tokenized[index] = f"***{word[:-2]}***; "
                elif word.endswith(";"):
                    tokenized[index] = f"***{word[:-1]}***;"
                elif word.startswith("; "):
                    tokenized[index] = f"; ***{word[2:]}***"
                elif word.startswith(";"):
                    tokenized[index] = f";***{word[1:]}***"
                else:
                    tokenized[index] = f"***{word}***"
        return " ".join(tokenized)

    async def _query_kbbi(self, kata_pencarian: str):
        try:
            await self.bot.kbbi.cari(kata_pencarian)
        except TidakDitemukan as te:
            return None, "Tidak dapat menemukan kata tersebut di KBBI.", te.objek.saran_entri
        except TerjadiKesalahan:
            return None, "Terjadi kesalahan komunikasi dengan server KBBI.", []
        except BatasSehari:
            return None, "Bot telah mencapai batas pencarian harian, mohon coba esok hari lagi.", []
        except GagalKoneksi:
            return None, "Tidak dapat terhubung dengan KBBI, kemungkinan KBBI daring sedang down.", []
        except Exception as error:
            self.bot.echo_error(error)
            return None, "Terjadi kesalahan ketika memparsing hasil dari KBBI, mohon kontak N4O.", []

        hasil_kbbi = self.bot.kbbi.serialisasi()
        pranala = hasil_kbbi["pranala"]
        semua_entri = hasil_kbbi["entri"]
        saran_entri = []
        if "saran_entri" in hasil_kbbi:
            saran_entri = hasil_kbbi["saran_entri"]
        return KBBIHasil(kata_pencarian, pranala, semua_entri), None, saran_entri

    def _design_embed(self, entri: KBBIEntri, pranala: str, kueri: str):
        embed = discord.Embed(color=0x110063)
        embed.set_author(
            name=str(entri),
            url=pranala,
            icon_url="https://p.n4o.xyz/i/kbbi192.png",
        )
        all_desc = []
        btb_varian = []
        if entri.pelafalan:
            all_desc.append("**Pelafalan**: " + entri.pelafalan)
        if entri.etimologi:
            all_desc.append("**Etimologi**: " + str(entri.etimologi))
        if entri.kata_dasar:
            all_desc.append("**Kata dasar**: " + "; ".join(entri.kata_dasar))
        if entri.bentuk_tidak_baku:
            btb_varian.append("**Bentuk tak baku**: " + "; ".join(entri.bentuk_tidak_baku))
        if entri.varian:
            btb_varian.append("**Varian**: " + "; ".join(entri.varian))
        if all_desc:
            embed.description = cutoff_text("\n".join(all_desc), 2048)

        entri_terkait = []
        if entri.kata_turunan:
            entri_terkait.append("**Kata Turunan**: " + "; ".join(entri.kata_turunan))
        if entri.gabungan_kata:
            entri_terkait.append("**Gabungan Kata**: " + "; ".join(entri.gabungan_kata))
        if entri.peribahasa:
            peri_ha = "; ".join(entri.peribahasa)
            peri_ha = self._highlight_specific(peri_ha, kueri)
            entri_terkait.append("**Peribahasa**: " + peri_ha)
        if entri.idiom:
            idiom_ha = "; ".join(entri.idiom)
            idiom_ha = self._highlight_specific(idiom_ha, kueri)
            entri_terkait.append("**Idiom**: " + idiom_ha)

        makna_table = []
        contoh_table = []
        for n, makna in enumerate(entri.makna, 1):
            makna_table.append(f"**{n}**. {makna}")
            contoh_text = f"**{n}**. "
            if makna.contoh:
                contoh_text += "; ".join(makna.contoh)
            else:
                contoh_text += "*Tidak ada*"
            contoh_table.append(contoh_text)

        embed.add_field(name="Makna", value=cutoff_text("\n".join(makna_table), 1024), inline=False)
        embed.add_field(name="Contoh", value=cutoff_text("\n".join(contoh_table), 1024), inline=False)
        if entri_terkait:
            embed.add_field(
                name="Entri Terkait", value=cutoff_text("\n".join(entri_terkait), 1024), inline=False
            )
        if btb_varian:
            embed.add_field(
                name="Bentuk tak baku/Varian", value=cutoff_text("\n".join(btb_varian), 1024), inline=False
            )
        embed.set_footer(text="Diprakasai oleh KBBI Daring versi 3.6.0")
        return embed

    @tasks.loop(hours=24)
    async def _kutubuku_kbbi_check_auth(self):
        if self._first_run:
            self._first_run = False
            return
        if not self._use_auth:
            return

        current_time = arrow.utcnow().int_timestamp
        do_reauth = False
        kbbi_data = self.bot.kbbi.get_cookies
        self.logger.info("auth_check: checking kbbi cookie expiry...")
        if current_time >= kbbi_data["expires"]:
            self.logger.warning("auth_check: Cookie expired!")
            do_reauth = True
        if not do_reauth:
            self.logger.info("auth_check: checking directly to KBBI...")
            do_reauth = await self.bot.kbbi.cek_auth()
            self.logger.info(f"auth_check: test results if it needs reauth: {do_reauth}")
        if not do_reauth:
            self.logger.warning("auth_check: cookie is not expired yet, skipping run...")
            return

        self.logger.info("auth_check: re-authenticating...")
        await self.bot.kbbi.reautentikasi()
        self.logger.info("auth_check: authenticated, saving cache...")
        await self.bot.redisdb.set("ntconfig_kbbiauth", self.bot.kbbi.get_cookies)
        self.logger.info("auth_check: done")

    @commands.command(name="kbbi")
    async def _kutubuku_kbbi(self, ctx: naoTimesContext, *, kata_pencarian: str):
        kata_pencarian = kata_pencarian.lower()
        self.logger.info(f"Querying: {kata_pencarian}")

        hasil_data, error_msg, saran_entri = await self._query_kbbi(kata_pencarian)
        if hasil_data is None:
            self.logger.error(f"{kata_pencarian}: error\n{error_msg}")
            if len(saran_entri) > 0:
                saran = ", ".join(saran_entri)
                return await ctx.send(
                    f"Tidak dapat menemukan kata tersebut.\n**Mungkin maksud anda**: {saran}"
                )
            return await ctx.send(error_msg)

        if not hasil_data.entri:
            self.logger.warning(f"{kata_pencarian}: no results...")
            if len(saran_entri) > 0:
                saran = ", ".join(saran_entri)
                return await ctx.send(
                    f"Tidak dapat menemukan kata tersebut.\n**Mungkin maksud anda**: {saran}"
                )
            return await ctx.send("Tidak dapat menemukan kata tersebut di KBBI")

        self.logger.info("Sending result...")
        embed_gen = partial(
            self._design_embed,
            pranala=hasil_data.pranala,
            kueri=kata_pencarian,
        )
        ui_paginate = DiscordPaginatorUI(ctx, hasil_data.entri, 20.0)
        ui_paginate.attach(embed_gen)
        await ui_paginate.interact()

    @app.slash_command(
        name="kbbi",
        description="Cari definisi kata di KBBI",
    )
    @app.option("kata", str, description="Kata yang ingin dicari")
    async def _kutubuku_kbbi_slash(self, ctx: app.ApplicationContext, kata: str):
        kata_pencarian: str = kata.lower()
        self.logger.info(f"Querying for: {kata_pencarian}")
        await ctx.defer()

        hasil_data, error_msg, saran_entri = await self._query_kbbi(kata_pencarian)
        if hasil_data is None:
            self.logger.error(f"{kata_pencarian}: error\n{error_msg}")
            if len(saran_entri) > 0:
                saran = ", ".join(saran_entri)
                return await ctx.send(
                    f"Tidak dapat menemukan kata tersebut.\n**Mungkin maksud anda**: {saran}"
                )
            return await ctx.send(error_msg)

        if not hasil_data.entri:
            self.logger.warning(f"{kata_pencarian}: no results...")
            if len(saran_entri) > 0:
                saran = ", ".join(saran_entri)
                return await ctx.send(
                    f"Tidak dapat menemukan kata tersebut.\n**Mungkin maksud anda**: {saran}"
                )
            return await ctx.send("Tidak dapat menemukan kata tersebut di KBBI")

        self.logger.info("Sending result...")
        first_data = hasil_data.entri[0]
        await ctx.send(embed=self._design_embed(first_data, hasil_data.pranala, kata_pencarian))


def setup(bot: naoTimesBot):
    bot.add_cog(KutubukuKBBIv2(bot))
