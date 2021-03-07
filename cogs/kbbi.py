import logging
import os
import traceback
from datetime import datetime, timezone
from functools import partial
from typing import List, Tuple, Union

import discord
from discord.ext import commands, tasks
from discord_slash import cog_ext
from discord_slash import SlashContext
from discord_slash.utils import manage_commands

from nthelper.bot import naoTimesBot
from nthelper.utils import DiscordPaginator, write_files
from nthelper.kbbiasync import (
    KBBI,
    BatasSehari,
    GagalKoneksi,
    TerjadiKesalahan,
    TidakDitemukan,
)

kbbilog = logging.getLogger("cogs.kbbi")


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


async def query_requests_kbbi(kata_pencarian: str, kbbi_conn: KBBI) -> Tuple[str, Union[str, list]]:
    try:
        await kbbi_conn.cari(kata_pencarian)
    except TidakDitemukan:
        return kata_pencarian, "Tidak dapat menemukan kata tersebut di KBBI."
    except TerjadiKesalahan:
        return (
            kata_pencarian,
            "Terjadi kesalahan komunikasi dengan server KBBI.",
        )
    except BatasSehari:
        return (
            kata_pencarian,
            "Bot telah mencapai batas pencarian harian, mohon coba esok hari lagi.",
        )
    except GagalKoneksi:
        return (
            kata_pencarian,
            "Tidak dapat terhubung dengan KBBI, kemungkinan KBBI daring sedang down.",
        )
    except Exception as error:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        kbbilog.error("Exception occured\n" + "".join(tb))
        return kata_pencarian, "Terjadi kesalahan ketika memparsing hasil dari KBBI, mohon kontak N4O."

    hasil_kbbi = kbbi_conn.serialisasi()
    pranala = hasil_kbbi["pranala"]
    hasil_entri = await secure_results(hasil_kbbi["entri"])

    return pranala, hasil_entri


def strunct(text: str, max_characters: int) -> str:
    """A simple text truncate
    If `text` exceed the `max_characters` it will truncate
    the last 5 characters.

    :param text:            str:  Text to truncate
    :param max_characters:  int:  Maximum n character.
    :return: Truncated text (if applicable)
    :rtype: str
    """
    if len(text) >= max_characters - 7:
        text = text[: max_characters - 7] + " [...]"
    return text


def strunct_split(text: str, max_characters: int, splitters: str = " ") -> str:
    """A text truncate that use a split method
    If `text` exceed the `max_characters` it will not add more to the list.

    :param text: Text to truncate
    :type text: str
    :param max_characters: maximum character
    :type max_characters: int
    :param splitters: split character, defaults to " "
    :type splitters: str, optional
    :return: A truncated text
    :rtype: str
    """

    def len_token(token):
        return len(splitters.join(token))

    tokenize = text.split(splitters)
    final_token: List[str] = []
    for token in tokenize:
        if len_token(final_token) >= max_characters:
            break
        final_token.append(token)
    return splitters.join(final_token)


class KBBICog(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.kbbi_conn = bot.kbbi

        self._cwd = bot.fcwd
        self._first_run = False
        self._use_auth = self.kbbi_conn.terautentikasi

        self.logger = logging.getLogger("cogs.kbbi.KBBICog")
        self.daily_check_auth.start()
        self.check_maintenance_range.start()

        self._on_maintenance = False
        self._maintenance_range: List[int] = [None, 0]  # type: ignore

    def cog_unload(self):
        self.logger.info("Cancelling all tasks...")
        self.daily_check_auth.cancel()
        self.check_maintenance_range.cancel()

    @cog_ext.cog_slash(
        name="kbbi",
        description="Cari definisi kata di KBBI",
        options=[
            manage_commands.create_option(
                name="kata", description="Kata yang ingin di cari", option_type=3, required=True
            )
        ],
    )
    async def _kbbi_slash_cmd(self, ctx: SlashContext, kata: str):
        if self._on_maintenance:
            start_time = datetime.fromtimestamp(self._maintenance_range[0] + (7 * 60 * 60), tz=timezone.utc)
            end_time = datetime.fromtimestamp(self._maintenance_range[1] + (7 * 60 * 60), tz=timezone.utc)
            txt = "KBBI Daring sedang dalam masa maintenance!\n"
            txt += "**Waktu Mulai**: {}\n".format(start_time.strftime("%A, %d %B %Y, %H.%M WIB"))
            txt += "**Waktu Selesai**: {}".format(end_time.strftime("%A, %d %B %Y, %H.%M WIB"))
            return await ctx.send(content=txt)

        self.logger.info(f"searching {kata}")
        pranala, hasil_entri = await query_requests_kbbi(kata, self.kbbi_conn)

        if isinstance(hasil_entri, str):
            self.logger.error(f"{kata}: error\n{hasil_entri}")
            return await ctx.send(hasil_entri)

        if not hasil_entri:
            self.logger.warn(f"{kata}: no results...")
            return await ctx.send(content="Tidak dapat menemukan kata tersebut di KBBI")

        self.logger.info(f"{kata}: parsing results...")
        final_dataset = await self._parse_results(hasil_entri, False)

        self.logger.info(f"{kata}: sending results...")
        entri = final_dataset[0]
        embed = await self._design_embed(entri, pranala, kata)
        await ctx.send(embeds=[embed])

    @tasks.loop(minutes=1)
    async def check_maintenance_range(self):
        self.logger.debug("Checking maintenance time...")
        if self._maintenance_range[0] is None:
            self.logger.debug("Maintenance is not initiated, skipping...")
            return

        current_time = datetime.now(tz=timezone.utc).timestamp()

        start, end = self._maintenance_range
        if current_time >= start and current_time <= end:
            self.logger.debug("Currently on maintenance!")
            self._on_maintenance = True
        else:
            if self._on_maintenance:
                self.logger.debug("Resetting maintenance range...")
                self._maintenance_range = [None, 0]
            self.logger.debug("Currently not on maintenance!")
            self._on_maintenance = False

    @tasks.loop(hours=24)
    async def daily_check_auth(self):
        if not self._first_run:  # Don't run first time
            self._first_run = True
            return
        if self._on_maintenance or not self._use_auth:  # Don't run on maintenance or if not using auth.
            return
        ct = datetime.now(tz=timezone.utc).timestamp()
        do_reauth = False
        kbbi_data = self.kbbi_conn.get_cookies
        if ct >= kbbi_data["expires"]:
            self.logger.warn("cookie expired!")
            do_reauth = True
        if not do_reauth:
            self.logger.info("checking directly to KBBI...")
            do_reauth = await self.kbbi_conn.cek_auth()
            self.logger.info(f"test results if it needs reauth: {do_reauth}")
        if not do_reauth:
            self.logger.warn("cookie is not expired yet, skipping...")
            return

        self.logger.info("reauthenticating...")
        await self.kbbi_conn.reautentikasi()
        self.logger.info("auth_check: authenticated, reassigning...")
        save_path = os.path.join(self._cwd, "kbbi_auth.json")
        await write_files(self.kbbi_conn.get_cookies, save_path)

    async def _highlight_specifics(self, text: str, hi: str) -> str:
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

    async def _design_embed(self, entri, pranala, kata_pencarian):
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
            peri_hi = await self._highlight_specifics(entri["peribahasa"], kata_pencarian)
            entri_terkait += "**Peribahasa**: {}\n".format(peri_hi)
        if entri["idiom"]:
            idiom_hi = await self._highlight_specifics(entri["idiom"], kata_pencarian)
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

    async def _parse_results(self, hasil_entri, add_numbering):
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
        return final_dataset

    @commands.command()
    async def print_cookies(self, ctx):
        print(await self.kbbi_conn.get_cookies)

    @commands.command()
    @commands.is_owner()
    async def kbbi_auth(self, ctx):
        if self._use_auth:
            self._use_auth = False
            return await ctx.send("Perintah kbbi **tidak akan** menggunakan autentikasi!")
        self._use_auth = True
        return await ctx.send("Perintah kbbi **akan** menggunakan autentikasi!")

    @commands.command()
    @commands.is_owner()
    async def kbbi_reenable(self, ctx):
        self._maintenance_range = [None, 0]
        self._on_maintenance = False
        await ctx.send("Mode maintenance telah dimatikan.")

    @commands.command()
    @commands.is_owner()
    async def kbbi_maintenance(self, ctx, *, tanggal):
        date_fmt = "%d-%m-%Y %H.%M %z"
        tanggal += " +0700"
        self.logger.info(f"Setting KBBI Maintenance with start: {tanggal}")
        try:
            start_date: datetime = datetime.strptime(tanggal, date_fmt)
        except ValueError:
            yang_benar = "DD-MM-YYYY HH.MM"
            return await ctx.send("Penulisan tanggal salah.\nYang benar: {}".format(yang_benar))

        def check_if_author(m):
            return m.author == ctx.message.author

        msg = await ctx.send("Mohon masukan tanggal selesai maintenance.")
        await_msg = await self.bot.wait_for("message", check=check_if_author)

        try:
            tanggal_akhir = str(await_msg.content)
            tanggal_akhir += " +0700"
            end_date: datetime = datetime.strptime(tanggal_akhir, date_fmt)
        except ValueError:
            yang_benar = "DD-MM-YYYY HH.MM"
            return await ctx.send("Penulisan tanggal salah.\nYang benar: {}".format(yang_benar))

        self.logger.info(f"Setting KBBI Maintenance with end: {tanggal_akhir}")
        await msg.delete()
        start_ts = start_date.timestamp()
        end_ts = end_date.timestamp()
        self._maintenance_range = [start_ts, end_ts]

        current_time = datetime.now(tz=timezone.utc).timestamp()
        self.logger.info(f"Timestamp info:\nStart: {start_ts}\nEnd: {end_ts}\nCurrent: {current_time}")

        if current_time >= start_ts and current_time <= end_ts:
            self.logger.info("Setting to maintenance mode immediatly!")
            self._on_maintenance = True

        await ctx.send("Masa maintenance telah diatur.")

    @commands.command(name="kbbi")
    async def _kbbi_cmd_main(self, ctx, *, kata_pencarian: str):
        if self._on_maintenance:
            start_time = datetime.fromtimestamp(self._maintenance_range[0] + (7 * 60 * 60), tz=timezone.utc)
            end_time = datetime.fromtimestamp(self._maintenance_range[1] + (7 * 60 * 60), tz=timezone.utc)
            txt = "KBBI Daring sedang dalam masa maintenance!\n"
            txt += "**Waktu Mulai**: {}\n".format(start_time.strftime("%A, %d %B %Y, %H.%M WIB"))
            txt += "**Waktu Selesai**: {}".format(end_time.strftime("%A, %d %B %Y, %H.%M WIB"))
            return await ctx.send(txt)
        kata_pencarian = kata_pencarian.lower()

        self.logger.info(f"searching {kata_pencarian}")
        pranala, hasil_entri = await query_requests_kbbi(kata_pencarian, self.kbbi_conn)

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
        final_dataset = await self._parse_results(hasil_entri, add_numbering)

        if not final_dataset:
            return await ctx.send("Terjadi kesalahan komunikasi dengan server KBBI.")
        self.logger.info(f"{kata_pencarian}: total {len(final_dataset)} results.")
        generate_embed = partial(self._design_embed, pranala=pranala, kata_pencarian=kata_pencarian)
        paginate = DiscordPaginator(self.bot, ctx)
        paginate.checker()
        paginate.set_generator(generate_embed)
        await paginate.start(final_dataset, 20.0)


def setup(bot: commands.Bot):
    bot.add_cog(KBBICog(bot))
