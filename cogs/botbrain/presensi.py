import asyncio
import logging
from itertools import cycle
from random import choice, shuffle
from typing import Literal, NamedTuple, Optional

import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.converters import TimeConverter


class PresensiData(NamedTuple):
    teks: str
    # 0: Playing
    # 1: Listening
    # 2: Watching
    tipe: Literal[0, 1, 2] = 0
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
            kwargs["emoji"] = disnake.PartialEmoji(name=self.emoji).to_dict()
        remap_type = {
            0: disnake.ActivityType.playing,
            1: disnake.ActivityType.listening,
            2: disnake.ActivityType.watching,
        }
        tipe = remap_type.get(self.tipe, disnake.ActivityType.playing)
        kwargs["type"] = tipe
        return disnake.Activity(**kwargs)


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
    PresensiData(":AyamePhone:"),
    PresensiData("Akhir Dunia", 2),
    PresensiData("Keributan", 1),
]


class BotBrainPresensi(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        if hasattr(self.bot, "presensi_rate"):
            self.rotation_rate = self.bot.presensi_rate  # In seconds
        else:
            self.rotation_rate = 60
            setattr(self.bot, "presensi_rate", self.rotation_rate)

        presensi_simple = PRESENSI_DATA.copy()
        shuffle(presensi_simple)
        self._presensi = cycle(presensi_simple)

        self.logger = logging.getLogger("BotBrain.Presensi")
        self._ROTATE_PRESENCE = asyncio.Task(self._loop_bb_ubah_presensi())

    def cog_unload(self):
        self._ROTATE_PRESENCE.cancel()

    @commands.command(name="presensiwaktu")
    @commands.is_owner()
    async def _bb_ubah_waktu_presensi(self, ctx: naoTimesContext, waktu_fmt: TimeConverter):
        self.rotation_rate = waktu_fmt.timestamp()
        await ctx.send(f"Berhasil mengubah rotasi ke `{self.rotation_rate} detik`")
        self.bot.presensi_rate = self.rotation_rate

    @commands.command(name="tespresensi")
    @commands.is_owner()
    async def _bb_manual_presensi_ubah(self, ctx: naoTimesContext, posisi: int):
        posisi -= 1
        posisi = max(posisi, 0)
        try:
            presensi = PRESENSI_DATA[posisi]
        except IndexError:
            return await ctx.send(f"Posisi diluar range yang ada (1-{len(PRESENSI_DATA)})")
        await self.bot.change_presence(activity=presensi.presensi(self.bot.prefix))
        await ctx.send(f"Mengubah presensi ke `{presensi.pretty()}`")

    @commands.command(name="ubahpresensi")
    @commands.is_owner()
    async def _bb_manual_presensi_ubah_real(self, ctx, *, text: str):
        await self.bot.change_presence(activity=disnake.Game(name=text + " | !help"))
        await ctx.send(f"Mengubah presensi ke `{text}`")

    async def _loop_bb_ubah_presensi(self):
        self.logger.info("starting presence rotation handler, shuffling!")
        while True:
            try:
                await asyncio.sleep(self.rotation_rate)
                try:
                    presensi = next(self._presensi)
                except StopIteration:
                    presensi = choice(PRESENSI_DATA)
                self.logger.info(
                    f"changing to `{presensi.pretty()}`, next rotation in {self.rotation_rate} secs"
                )
                try:
                    await self.bot.change_presence(activity=presensi.presensi(self.bot.prefix))
                except Exception as e:
                    self.logger.warning("failed to change presence, ignoring!", exc_info=e)
            except asyncio.CancelledError:
                self.logger.warning("stopping presences rotator")
                break


def setup(bot: naoTimesBot):
    bot.add_cog(BotBrainPresensi(bot))
