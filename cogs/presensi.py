import asyncio
import logging
from itertools import cycle
from random import choice, shuffle
from typing import NamedTuple, Optional

import discord
from discord.ext import commands

from nthelper.bot import naoTimesBot
from nthelper.timeparse import TimeConverter


class PresensiData(NamedTuple):
    teks: str
    # 0: Playing
    # 1: Listening
    # 2: Watching
    tipe: int = 0
    emoji: Optional[str] = None

    def pretty(self):
        name_map = {0: "Playing", 1: "Listening", 2: "Watching", 3: "Streaming"}
        teks = name_map.get(self.tipe, "Playing")
        if self.emoji:
            teks = f"[{self.emoji}] {teks}"
        teks += ": " + self.teks
        return teks

    def presensi(self, prefix: str = "!"):
        kwargs = {"name": self.teks + f" | {prefix}help"}
        if self.emoji is not None:
            kwargs["emoji"] = discord.PartialEmoji(name=self.emoji).to_dict()
        remap_type = {
            0: discord.ActivityType.playing,
            1: discord.ActivityType.listening,
            2: discord.ActivityType.watching,
        }
        tipe = remap_type.get(self.tipe, discord.ActivityType.playing)
        kwargs["type"] = tipe
        return discord.Activity(**kwargs)


PRESENSI_DATA = [
    PresensiData("Mengamati rilisan Fansub"),
    PresensiData("Membantu Fansub"),
    PresensiData("Menambah utang"),
    PresensiData("Membersihkan sampah masyarakat"),
    PresensiData("Mengikuti event wibu"),
    PresensiData("Ngememe"),
    PresensiData("Menjadi babu"),
    PresensiData("Apa Kabar Fansub Indonesia?", 1),
    PresensiData("Drama Fansub", 2),
    PresensiData("Bot ini masih belum legal!"),
    PresensiData("Memburu buronan 1001 Fansub"),
    PresensiData("Menagih utang"),
    PresensiData("Menunggu Fanshare bubar"),
    PresensiData("Mencatat utang Fansub"),
    PresensiData("Menuju Isekai"),
    PresensiData("Membuka donasi"),
    PresensiData("Membuat Fansub"),
    PresensiData("Membuli Fansub"),
    PresensiData("Kapan nikah? Ngesub mulu"),
    PresensiData("Gagal pensi"),
    PresensiData("Mengembalikan kode etik Fansub"),
    PresensiData("Pesan masyarakat ini disponsori oleh [REDACTED]"),
    PresensiData("Menunggu rilisan"),
    PresensiData("Berternak dolar"),
    PresensiData("Judul Anime - Episode (v42069)", 2),
    PresensiData("Keributan antar Fansub", 1),
    PresensiData("VTuber", 2),
    PresensiData("Bot ini dibuat mengikuti SNI"),
    PresensiData("Dunia berakhir", 2),
    PresensiData("Muse ID", 2),
    PresensiData("with pain"),
    PresensiData("Towa-sama", 2),
]


class PresensiDiscord(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        if hasattr(self.bot, "presensi_rate"):
            self.rotation_rate = self.bot.presensi_rate  # In seconds
        else:
            self.rotation_rate = 60
            setattr(self.bot, "presensi_rate", self.rotation_rate)
        self.logger = logging.getLogger("cogs.presensi.PresensiDiscord")

        self._handler_presensi: asyncio.Task = asyncio.Task(self._ubah_presensi())

    def cog_unload(self):
        self._handler_presensi.cancel()

    @commands.command(name="presensiwaktu")
    @commands.is_owner()
    async def _ubah_waktu_presensi(self, ctx: commands.Context, waktu_fmt: TimeConverter):
        self.rotation_rate = waktu_fmt.timestamp()
        await ctx.send(f"Berhasil mengubah rotasi ke `{self.rotation_rate} detik`")
        self.bot.presensi_rate = self.rotation_rate

    @commands.command(name="tespresensi")
    @commands.is_owner()
    async def _manual_presensi_ubah(self, ctx: commands.Context, posisi: int):
        posisi -= 1
        if posisi < 0:
            posisi = 0
        try:
            presensi = PRESENSI_DATA[posisi]
        except IndexError:
            return await ctx.send(f"Posisi diluar range yang ada (1-{len(PRESENSI_DATA)})")
        await self.bot.change_presence(activity=presensi.presensi(self.bot.prefix))
        await ctx.send(f"Mengubah presensi ke `{presensi.pretty()}`")

    async def _ubah_presensi(self):
        self.logger.info("starting presence rotation handler, shuffling!")
        shuffle(PRESENSI_DATA)
        presences = cycle(PRESENSI_DATA)
        while True:
            try:
                await asyncio.sleep(self.rotation_rate)
                try:
                    presensi = next(presences)
                except StopIteration:
                    presensi = choice(PRESENSI_DATA)
                self.logger.info(
                    f"changing to `{presensi.pretty()}`, next rotation in {self.rotation_rate} secs"
                )
                await self.bot.change_presence(activity=presensi.presensi(self.bot.prefix))
            except asyncio.CancelledError:
                self.logger.warning("stopping presences rotator")
                break


def setup(bot: naoTimesBot):
    bot.add_cog(PresensiDiscord(bot))
