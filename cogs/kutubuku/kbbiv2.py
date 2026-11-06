import logging
from functools import partial
from typing import Callable

import arrow
import discord
from discord import app_commands
from discord.ext import commands, tasks
from kbbi.kbbi import BatasSehari, TerjadiKesalahan, TidakDitemukan

from naotimes.bot import naoTimesBot
from naotimes.http import GagalKoneksi
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import cutoff_text


class KBBIDictBase:
    def __getitem__(self, key: str):
        name = type(self).__name__
        attr = getattr(self, key, None)
        if attr is None:
            raise KeyError(f"`{key}` not found in this `{name}` class")
        return attr

    def __repr__(self):
        name = type(self).__name__
        base_data = "<" + name
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
    kelas: list[str]
    asal_kata: str
    pelafalan: str
    arti: list[str]

    def __init__(self, etimologi: dict):
        self.kelas = []
        self.arti = []
        for key, value in etimologi.items():
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
    kelas: list[KBBIKelas]
    submakna: list[str]
    info: str | None = None
    contoh: list[str]

    def __init__(self, makna: dict):
        self.kelas = []
        self.submakna = []
        self.contoh = []
        SPECIAL_KEY = {
            "kelas": [KBBIKelas],
        }
        for key, value in makna.items():
            if key in SPECIAL_KEY and value:
                SP = SPECIAL_KEY[key]
                if isinstance(SP, list):
                    concat = []
                    for val in value:
                        if value:
                            concat.append(SP[0](val))
                    setattr(self, key, concat)
                else:
                    if value:
                        setattr(self, key, SP(value))
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
    nomor: str | None = None
    kata_dasar: list[str]
    pelafalan: str | None = None
    bentuk_tidak_baku: list[str]
    varian: list[str]
    makna: list[KBBIMakna]
    etimologi: KBBIEtimologi | None = None

    # Terkait
    kata_turunan: list[str]
    gabungan_kata: list[str]
    peribahasa: list[str]
    idiom: list[str]

    def __init__(self, makna: dict):
        self.kata_dasar = []
        self.bentuk_tidak_baku = []
        self.varian = []
        self.makna = []
        self.kata_turunan = []
        self.gabungan_kata = []
        self.peribahasa = []
        self.idiom = []
        SPECIAL_KEY = {
            "makna": [KBBIMakna],
            "etimologi": KBBIEtimologi,
        }
        for key, value in makna.items():
            if key in SPECIAL_KEY and value:
                SP = SPECIAL_KEY[key]
                if isinstance(SP, list):
                    concat = []
                    for val in value:
                        if value:
                            concat.append(SP[0](val))
                    setattr(self, key, concat)
                else:
                    if value:
                        setattr(self, key, SP(value))
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
    entri: list[KBBIEntri]

    def __init__(self, kueri: str, pranala: str, entries: list[dict]):
        self.kueri = kueri
        self.pranala = pranala
        entri_parsed: list[KBBIEntri] = []
        for entri in entries:
            entri_ = KBBIEntri(entri)
            entri_parsed.append(entri_)
        self.entri = entri_parsed

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
        if bot.kbbi is None:
            raise RuntimeError("KBBI client is unavailable")
        self.kbbi = bot.kbbi
        self._use_auth = self.kbbi.terautentikasi
        self._first_run = True

        self._kutubuku_kbbi_check_auth.start()

    async def cog_unload(self):
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

    async def _query_kbbi(self, kata_pencarian: str, t: Callable[..., str]):
        try:
            await self.kbbi.cari(kata_pencarian)
        except TidakDitemukan as te:
            suggestions = te.objek.saran_entri if te.objek is not None else []
            return None, t("kbbi.not_found"), suggestions
        except TerjadiKesalahan:
            return None, t("kbbi.communication_error"), []
        except BatasSehari:
            return None, t("kbbi.daily_limit"), []
        except GagalKoneksi:
            return None, t("kbbi.connection_error"), []
        except Exception as error:
            self.bot.echo_error(error)
            return None, t("kbbi.parse_error"), []

        hasil_kbbi = self.kbbi.serialisasi()
        pranala = hasil_kbbi["pranala"]
        semua_entri = hasil_kbbi["entri"]
        saran_entri = []
        if "saran_entri" in hasil_kbbi:
            saran_entri = hasil_kbbi["saran_entri"]
        return KBBIHasil(kata_pencarian, pranala, semua_entri), None, saran_entri

    def _design_embed(self, entri: KBBIEntri, pranala: str, kueri: str, t: Callable[..., str]):
        embed = discord.Embed(color=0x110063)
        embed.set_author(
            name=str(entri),
            url=pranala,
            icon_url="https://p.n4o.xyz/i/kbbi192.png",
        )
        all_desc = []
        btb_varian = []
        if entri.pelafalan:
            all_desc.append(t("kbbi.embed.pronunciation", value=entri.pelafalan))
        if entri.etimologi:
            all_desc.append(t("kbbi.embed.etymology", value=str(entri.etimologi)))
        if entri.kata_dasar:
            all_desc.append(t("kbbi.embed.base_word", value="; ".join(entri.kata_dasar)))
        if entri.bentuk_tidak_baku:
            btb_varian.append(t("kbbi.embed.nonstandard_form", value="; ".join(entri.bentuk_tidak_baku)))
        if entri.varian:
            btb_varian.append(t("kbbi.embed.variant", value="; ".join(entri.varian)))
        if all_desc:
            embed.description = cutoff_text("\n".join(all_desc), 2048)

        entri_terkait = []
        if entri.kata_turunan:
            entri_terkait.append(t("kbbi.embed.derived_words", value="; ".join(entri.kata_turunan)))
        if entri.gabungan_kata:
            entri_terkait.append(t("kbbi.embed.compound_words", value="; ".join(entri.gabungan_kata)))
        if entri.peribahasa:
            peri_ha = "; ".join(entri.peribahasa)
            peri_ha = self._highlight_specific(peri_ha, kueri)
            entri_terkait.append(t("kbbi.embed.proverb", value=peri_ha))
        if entri.idiom:
            idiom_ha = "; ".join(entri.idiom)
            idiom_ha = self._highlight_specific(idiom_ha, kueri)
            entri_terkait.append(t("kbbi.embed.idiom", value=idiom_ha))

        makna_table = []
        contoh_table = []
        for n, makna in enumerate(entri.makna, 1):
            makna_table.append(f"**{n}**. {makna}")
            contoh_text = f"**{n}**. "
            if makna.contoh:
                contoh_text += "; ".join(makna.contoh)
            else:
                contoh_text += t("kbbi.embed.no_example")
            contoh_table.append(contoh_text)

        embed.add_field(name=t("kbbi.embed.meanings"), value=cutoff_text("\n".join(makna_table), 1024), inline=False)
        embed.add_field(name=t("kbbi.embed.examples"), value=cutoff_text("\n".join(contoh_table), 1024), inline=False)
        if entri_terkait:
            embed.add_field(
                name=t("kbbi.embed.related_entries"),
                value=cutoff_text("\n".join(entri_terkait), 1024),
                inline=False,
            )
        if btb_varian:
            embed.add_field(
                name=t("kbbi.embed.nonstandard_variant"),
                value=cutoff_text("\n".join(btb_varian), 1024),
                inline=False,
            )
        embed.set_footer(text=t("kbbi.embed.footer"))
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
        kbbi_data = self.kbbi.get_cookies
        self.logger.info("auth_check: checking kbbi cookie expiry...")
        if current_time >= kbbi_data["expires"]:
            self.logger.warning("auth_check: Cookie expired!")
            do_reauth = True
        if not do_reauth:
            self.logger.info("auth_check: checking directly to KBBI...")
            do_reauth = await self.kbbi.cek_auth()
            self.logger.info(f"auth_check: test results if it needs reauth: {do_reauth}")
        if not do_reauth:
            self.logger.warning("auth_check: cookie is not expired yet, skipping run...")
            return

        self.logger.info("auth_check: re-authenticating...")
        await self.kbbi.reautentikasi()
        self.logger.info("auth_check: authenticated, saving cache...")
        if self.bot.redisdb is None:
            self.logger.error("auth_check: Redis is unavailable; cannot save KBBI authentication")
            return
        await self.bot.redisdb.set("ntconfig_kbbiauth", self.kbbi.get_cookies)
        self.logger.info("auth_check: done")

    @app_commands.command(
        name="kbbi",
        description=app_commands.locale_str(
            "Cari definisi sebuah kata di KBBI Daring",
            key="kutubuku.kbbi.description",
        ),
    )
    @app_commands.describe(
        kata=app_commands.locale_str("Kata yang ingin dicari", key="kutubuku.kbbi.option_kata"),
    )
    async def _kutubuku_kbbi_slash(self, inter: discord.Interaction, kata: str):
        """Cari definisi sebuah kata di KBBI Daring"""
        ctx = await self.bot.get_context(inter)
        kata_pencarian: str = kata.lower()
        self.logger.info(f"Querying for: {kata_pencarian}")
        await ctx.defer()

        hasil_data, error_msg, saran_entri = await self._query_kbbi(kata_pencarian, t=ctx.t)
        if hasil_data is None:
            self.logger.error(f"{kata_pencarian}: error\n{error_msg}")
            if len(saran_entri) > 0:
                saran = ", ".join(saran_entri)
                return await ctx.send(ctx.t("kbbi.not_found_suggestions", suggestions=saran))
            return await ctx.send(error_msg)

        if not hasil_data.entri:
            self.logger.warning(f"{kata_pencarian}: no results...")
            if len(saran_entri) > 0:
                saran = ", ".join(saran_entri)
                return await ctx.send(ctx.t("kbbi.not_found_suggestions", suggestions=saran))
            return await ctx.send(ctx.t("kbbi.not_found_plain"))

        self.logger.info("Sending result...")
        embed_gen = partial(
            self._design_embed,
            pranala=hasil_data.pranala,
            kueri=kata_pencarian,
            t=ctx.t,
        )
        ui_paginate = DiscordPaginatorUI(ctx, hasil_data.entri, 20.0)
        ui_paginate.attach(embed_gen)
        await ui_paginate.interact()


async def setup(bot: naoTimesBot):
    if bot.kbbi is None:
        bot.logger.warning("KBBI client is unavailable; skipping KBBI cog")
        return
    await bot.add_cog(KutubukuKBBIv2(bot))
