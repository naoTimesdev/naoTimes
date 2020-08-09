import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Tuple, Union

import discord
from discord.ext import commands, tasks

from nthelper import write_files
from nthelper.kbbiasync import (
    KBBI,
    AutentikasiKBBI,
    BatasSehari,
    GagalAutentikasi,
    GagalKoneksi,
    TerjadiKesalahan,
    TidakDitemukan,
)


async def secure_results(hasil_entri: list) -> list:
    for x, hasil in enumerate(hasil_entri):
        if "kata_turunan" not in hasil:
            hasil_entri[x]["kata_turunan"] = []
        if "etimologi" not in hasil:
            hasil_entri[x]["etimologi"] = {}
        if "gabungan_kata" not in hasil:
            hasil_entri[x]["gabungan_kata"] = []
        if "peribahasa" not in hasil:
            hasil_entri[x]["peribahasa"] = []
        if "idiom" not in hasil:
            hasil_entri[x]["idiom"] = []
    return hasil_entri


async def query_requests_kbbi(kata_pencarian: str, cookies: str) -> Tuple[str, Union[str, list]]:
    try:
        cari_kata = KBBI(kata_pencarian, cookies)
        await cari_kata.cari()
    except TidakDitemukan:
        await cari_kata.tutup()
        return kata_pencarian, "Tidak dapat menemukan kata tersebut di KBBI."
    except TerjadiKesalahan:
        await cari_kata.tutup()
        return (
            kata_pencarian,
            "Terjadi kesalahan komunikasi dengan server KBBI.",
        )
    except BatasSehari:
        await cari_kata.tutup()
        return (
            kata_pencarian,
            "Bot telah mencapai batas pencarian harian, " "mohon coba esok hari lagi.",
        )
    except GagalKoneksi:
        await cari_kata.tutup()
        return (
            kata_pencarian,
            "Tidak dapat terhubung dengan KBBI, " "kemungkinan KBBI daring sedang down.",
        )

    hasil_kbbi = cari_kata.serialisasi()
    pranala = hasil_kbbi["pranala"]
    hasil_entri = await secure_results(hasil_kbbi["entri"])

    await cari_kata.tutup()
    return pranala, hasil_entri


def strunct(text: str, max_chatacters: int) -> str:
    """A simple text truncate
    If `text` exceed the `max_chatacters` it will truncate
    the last 5 characters.

    :param text:            str:  Text to truncate
    :param max_chatacters:  int:  Maximum n character.
    :return: Truncated text (if applicable)
    :rtype: str
    """
    if len(text) >= max_chatacters - 7:
        text = text[: max_chatacters - 7] + " [...]"
    return text


class KBBICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cookie: str = bot.kbbi_cookie
        self.k_expire: int = bot.kbbi_expires
        self.k_auth: dict = bot.kbbi_auth

        self._cwd = bot.fcwd
        self._first_run = False

        self.logger = logging.getLogger("cogs.kbbi.KBBICog")
        self.daily_check_auth.start()

    @tasks.loop(hours=24)
    async def daily_check_auth(self):
        if not self._first_run:  # Don't run first time
            self._first_run = True
            return
        ct = datetime.now(tz=timezone.utc).timestamp()
        do_reauth = False
        if ct >= self.k_expire:
            self.logger.warn("cookie expired!")
            do_reauth = True
        if not do_reauth:
            self.logger.info("checking directly to KBBI...")
            kbbi_mod = KBBI("periksa", self.cookie)
            do_reauth = await kbbi_mod.cek_auth()
            self.logger.info(f"test results if it needs reauth: {do_reauth}")
        if not do_reauth:
            self.logger.warn("cookie is not expired yet, skipping...")
            return

        self.logger.info("reauthenticating...")
        kbbi_auth = AutentikasiKBBI(self.k_auth["email"], self.k_auth["password"])
        self.logger.info("auth_check: authenticating...")
        try:
            await kbbi_auth.autentikasi()
        except GagalKoneksi:
            self.logger.error("connection error occured.")
            return
        except TerjadiKesalahan:
            self.logger.error("cannot do reauth, please check.")
            return
        except GagalAutentikasi:
            self.logger.error("wrong user/password combination...")
            return

        self.logger.info("auth_check: authenticated, reassigning...")
        cookie = await kbbi_auth.ambil_cookies()
        self.cookie = cookie
        self.k_expire = round(ct + (15 * 24 * 60 * 60))
        self.logger.info("auth_check: saving data...")
        await kbbi_auth.sesi.close()
        save_data = {"cookie": cookie, "expires": self.k_expire}
        save_path = os.path.join(self._cwd, "kbbi_auth.json")
        await write_files(save_data, save_path)

    @commands.command(name="kbbi")
    async def _kbbi_cmd_main(self, ctx, *, kata_pencarian: str):
        kata_pencarian = kata_pencarian.lower()

        self.logger.info(f"searching {kata_pencarian}")
        pranala, hasil_entri = await query_requests_kbbi(kata_pencarian, self.cookie)

        if isinstance(hasil_entri, str):
            self.logger.error(f"{kata_pencarian}: error\n{hasil_entri}")
            return await ctx.send(hasil_entri)

        if not hasil_entri:
            self.logger.warn(f"{kata_pencarian}: no results...")
            return await ctx.send("Tidak dapat menemukan kata tersebut di KBBI")

        add_numbering = False
        if len(hasil_entri) > 1:
            add_numbering = True

        self.logger.info(f"{kata_pencarian}: parsing results...")
        final_dataset = []
        for hasil in hasil_entri:
            entri = {
                "nama": "",
                "kata_dasar": "",
                "pelafalan": "",
                "takbaku": "",
                "varian": "",
                "makna": "",
                "contoh": "",
                "etimologi": "",
                "turunan": "",
                "gabungan": "",
                "peribahasa": "",
                "idiom": "",
            }
            entri["nama"] = hasil["nama"]
            if add_numbering:
                entri["nama"] = "{a} ({b})".format(a=hasil["nama"], b=hasil["nomor"])
            if hasil["kata_dasar"]:
                entri["kata_dasar"] = "; ".join(hasil["kata_dasar"])
            if hasil["pelafalan"]:
                entri["pelafalan"] = hasil["pelafalan"]
            if hasil["bentuk_tidak_baku"]:
                entri["takbaku"] = "; ".join(hasil["bentuk_tidak_baku"])
            if hasil["varian"]:
                entri["varian"] = "; ".join(hasil["varian"])
            if hasil["kata_turunan"]:
                entri["turunan"] = "; ".join(hasil["kata_turunan"])
            if hasil["gabungan_kata"]:
                entri["gabungan"] = "; ".join(hasil["gabungan_kata"])
            if hasil["peribahasa"]:
                entri["peribahasa"] = "; ".join(hasil["peribahasa"])
            if hasil["idiom"]:
                entri["idiom"] = "; ".join(hasil["idiom"])
            contoh_tbl = []
            makna_tbl = []
            for nmr_mkn, makna in enumerate(hasil["makna"], 1):
                makna_txt = "**{i}.** ".format(i=nmr_mkn)
                for kls in makna["kelas"]:
                    makna_txt += "*({a})* ".format(a=kls["kode"])
                makna_txt += "; ".join(makna["submakna"])
                if makna["info"]:
                    makna_txt += " " + makna["info"]
                makna_tbl.append(makna_txt)
                contoh_txt = "**{i}.** ".format(i=nmr_mkn)
                if makna["contoh"]:
                    contoh_txt += "; ".join(makna["contoh"])
                    contoh_tbl.append(contoh_txt)
                else:
                    contoh_txt += "Tidak ada"
                    contoh_tbl.append(contoh_txt)
            if hasil["etimologi"]:
                etimologi_txt = ""
                etimol = hasil["etimologi"]
                etimologi_txt += "[{}]".format(etimol["bahasa"])
                etimologi_txt += " ".join("({})".format(k) for k in etimol["kelas"])
                etimologi_txt += " " + " ".join((etimol["asal_kata"], etimol["pelafalan"])) + ": "
                etimologi_txt += "; ".join(etimol["arti"])
                entri["etimologi"] = etimologi_txt
            entri["makna"] = "\n".join(makna_tbl)
            entri["contoh"] = "\n".join(contoh_tbl)
            final_dataset.append(entri)

        async def _highlight_specifics(text: str, hi: str) -> str:
            tokenize = text.split(" ")
            for n, token in enumerate(tokenize):
                if hi in token:
                    if token.endswith("; "):
                        tokenize[n] = "***{}***; ".format(token[:-2])
                    elif token.endswith(";"):
                        tokenize[n] = "***{}***;".format(token[:-1])
                    elif token.startswith("; "):
                        tokenize[n] = "; ***{}***".format(token[2:])
                    elif token.startswith(";"):
                        tokenize[n] = ";***{}***".format(token[1:])
                    else:
                        tokenize[n] = "***{}***".format(token)
            return " ".join(tokenize)

        async def _design_embed(entri):
            embed = discord.Embed(color=0x110063)
            embed.set_author(
                name=entri["nama"], url=pranala, icon_url="https://p.n4o.xyz/i/kbbi192.png",
            )
            deskripsi = ""
            btb_varian = ""
            if entri["pelafalan"]:
                deskripsi += "**Pelafalan**: {}\n".format(entri["pelafalan"])
            if entri["etimologi"]:
                deskripsi += "**Etimologi**: {}\n".format(entri["etimologi"])
            if entri["kata_dasar"]:
                deskripsi += "**Kata Dasar**: {}\n".format(entri["kata_dasar"])
            if entri["takbaku"]:
                btb_varian += "**Bentuk tak baku**: {}\n".format(entri["takbaku"])
            if entri["varian"]:
                btb_varian += "**Varian**: {}\n".format(entri["varian"])
            if deskripsi:
                embed.description = strunct(deskripsi, 2048)

            entri_terkait = ""
            if entri["turunan"]:
                entri_terkait += "**Kata Turunan**: {}\n".format(entri["turunan"])
            if entri["gabungan"]:
                entri_terkait += "**Kata Gabungan**: {}\n".format(entri["gabungan"])
            if entri["peribahasa"]:
                peri_hi = await _highlight_specifics(entri["peribahasa"], kata_pencarian)
                entri_terkait += "**Peribahasa**: {}\n".format(peri_hi)
            if entri["idiom"]:
                idiom_hi = await _highlight_specifics(entri["idiom"], kata_pencarian)
                entri_terkait += "**Idiom**: {}\n".format(idiom_hi)
            embed.add_field(name="Makna", value=strunct(entri["makna"], 1024), inline=False)
            embed.add_field(
                name="Contoh", value=strunct(entri["contoh"], 1024), inline=False,
            )
            if entri_terkait:
                embed.add_field(
                    name="Entri Terkait", value=strunct(entri_terkait, 1024), inline=False,
                )
            if btb_varian:
                embed.add_field(
                    name="Bentuk tak baku/Varian", value=strunct(btb_varian, 1024), inline=False,
                )
            embed.set_footer(text="Menggunakan KBBI Daring versi 3.0.0")
            return embed

        first_run = True
        dataset_total = len(final_dataset)
        pos = 1
        if not final_dataset:
            return await ctx.send("Terjadi kesalahan komunikasi dengan server KBBI.")
        self.logger.info(f"{kata_pencarian}: total {dataset_total} results.")
        while True:
            if first_run:
                self.logger.info(f"{kata_pencarian}: sending results...")
                entri = final_dataset[pos - 1]
                embed = await _design_embed(entri)
                msg = await ctx.send(embed=embed)
                first_run = False

            if dataset_total < 2:
                self.logger.warn(f"{kata_pencarian}: no other results.")
                break
            elif pos == 1:
                to_react = ["⏩", "✅"]
            elif dataset_total == pos:
                to_react = ["⏪", "✅"]
            elif pos > 1 and pos < dataset_total:
                to_react = ["⏪", "⏩", "✅"]

            for react in to_react:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                self.logger.warn(f"{kata_pencarian}: timeout, nuking!")
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                self.logger.warn(f"{kata_pencarian}: done, nuking!")
                return await msg.clear_reactions()
            elif "⏪" in str(res.emoji):
                self.logger.debug(f"{kata_pencarian}: previous result.")
                await msg.clear_reactions()
                pos -= 1
                entri = final_dataset[pos - 1]
                embed = await _design_embed(entri)
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                self.logger.debug(f"{kata_pencarian}: next result.")
                await msg.clear_reactions()
                pos += 1
                entri = final_dataset[pos - 1]
                embed = await _design_embed(entri)
                await msg.edit(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(KBBICog(bot))
