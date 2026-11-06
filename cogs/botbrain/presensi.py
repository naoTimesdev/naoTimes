import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from itertools import cycle
from random import choice, shuffle
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import OwnerGroup
from naotimes.timeparse import TimeString, TimeStringParseError

Translator = Callable[..., str]


@dataclass
class PresensiData:
    # Catalog key (relative to the ``botbrain`` module) that holds the presence text.
    teks: str
    # 0: Playing
    # 1: Listening
    # 2: Watching
    tipe: Literal[0, 1, 2] = 0
    emoji: str | None = None

    def pretty(self, t: Translator):
        name_map = {
            0: "presensi.type.playing",
            1: "presensi.type.listening",
            2: "presensi.type.watching",
            3: "presensi.type.streaming",
        }
        teks = t(name_map.get(self.tipe, "presensi.type.playing"))
        if self.emoji:
            teks = f"[{self.emoji}] {teks}"
        teks += ": " + t(self.teks)
        return teks

    def presensi(self, t: Translator, prefix: str = "/"):
        kwargs: dict[str, object] = {"name": t(self.teks) + " | /help"}
        if self.emoji is not None:
            kwargs["emoji"] = discord.PartialEmoji(name=self.emoji)
        remap_type = {
            0: discord.ActivityType.playing,
            1: discord.ActivityType.listening,
            2: discord.ActivityType.watching,
        }
        tipe = remap_type.get(self.tipe, discord.ActivityType.playing)
        kwargs["type"] = tipe
        return discord.Activity(**kwargs)


PRESENSI_DATA = [
    PresensiData("presensi.activities.observe_release"),
    PresensiData("presensi.activities.helping_fansub"),
    PresensiData("presensi.activities.adding_debt"),
    PresensiData("presensi.activities.cleaning_society_trash"),
    PresensiData("presensi.activities.attending_weeb_event"),
    PresensiData("presensi.activities.memeing"),
    PresensiData("presensi.activities.being_servant"),
    PresensiData("presensi.activities.whats_up_fansub", 1),
    PresensiData("presensi.activities.fansub_drama", 2),
    PresensiData("presensi.activities.bot_not_legal"),
    PresensiData("presensi.activities.hunting_fugitive"),
    PresensiData("presensi.activities.collecting_debt"),
    PresensiData("presensi.activities.waiting_fanshare"),
    PresensiData("presensi.activities.recording_debt"),
    PresensiData("presensi.activities.going_isekai"),
    PresensiData("presensi.activities.opening_donation"),
    PresensiData("presensi.activities.making_fansub"),
    PresensiData("presensi.activities.bullying_fansub"),
    PresensiData("presensi.activities.when_marry"),
    PresensiData("presensi.activities.failed_retire"),
    PresensiData("presensi.activities.restoring_code_of_conduct"),
    PresensiData("presensi.activities.sponsored_message"),
    PresensiData("presensi.activities.waiting_release"),
    PresensiData("presensi.activities.farming_dollars"),
    PresensiData("presensi.activities.anime_episode", 2),
    PresensiData("presensi.activities.fansub_dispute", 1),
    PresensiData("presensi.activities.vtuber", 2),
    PresensiData("presensi.activities.bot_sni"),
    PresensiData("presensi.activities.world_ends", 2),
    PresensiData("presensi.activities.muse_id", 2),
    PresensiData("presensi.activities.with_pain"),
    PresensiData("presensi.activities.towa_sama", 2),
    PresensiData("presensi.activities.ayame_phone"),
    PresensiData("presensi.activities.end_of_world", 2),
    PresensiData("presensi.activities.disturbance", 1),
]


class BotBrainPresensi(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        rata = self.bot.presensi_rate or 60  # In seconds
        self.bot.presensi_rate = rata
        self.rotation_rate = rata

        presensi_simple = PRESENSI_DATA.copy()
        shuffle(presensi_simple)
        self._presensi = cycle(presensi_simple)

        self.logger = logging.getLogger("BotBrain.Presensi")
        self._ROTATE_PRESENCE = asyncio.Task(self._loop_bb_ubah_presensi())

    async def cog_unload(self):
        self._ROTATE_PRESENCE.cancel()

    def _presensi_i18n(self):
        return self.bot.i18n_for(None, "botbrain")

    presensi = OwnerGroup(
        name="presensi",
        description=app_commands.locale_str(
            "Atur presensi (status) bot (owner)", key="botbrain.presensi.group_description"
        ),
        default_permissions=discord.Permissions(administrator=True),
    )

    @presensi.command(
        name="waktu",
        description=app_commands.locale_str("Ubah waktu rotasi presensi", key="botbrain.presensi.waktu_description"),
    )
    @app_commands.describe(
        waktu=app_commands.locale_str("Waktu rotasi, contoh: 5m", key="botbrain.presensi.option_waktu")
    )
    async def _bb_ubah_waktu_presensi(self, inter: discord.Interaction, waktu: str):
        ctx = await self.bot.get_context(inter)
        try:
            parsed = TimeString.parse(waktu)
        except TimeStringParseError:
            return await inter.response.send_message(ctx.t("presensi.invalid_time"), ephemeral=True)
        self.rotation_rate = int(parsed.timestamp())
        self.bot.presensi_rate = self.rotation_rate
        await inter.response.send_message(ctx.t("presensi.waktu_success", rate=self.rotation_rate), ephemeral=True)

    @presensi.command(
        name="tes",
        description=app_commands.locale_str(
            "Pilih presensi dari daftar secara manual", key="botbrain.presensi.tes_description"
        ),
    )
    @app_commands.describe(
        posisi=app_commands.locale_str("Posisi presensi dalam daftar", key="botbrain.presensi.option_posisi")
    )
    async def _bb_manual_presensi_ubah(self, inter: discord.Interaction, posisi: int):
        ctx = await self.bot.get_context(inter)
        posisi = max(posisi - 1, 0)
        try:
            presensi = PRESENSI_DATA[posisi]
        except IndexError:
            return await inter.response.send_message(
                ctx.t("presensi.out_of_range", max=len(PRESENSI_DATA)), ephemeral=True
            )
        await self.bot.change_presence(activity=presensi.presensi(self._presensi_i18n()))
        await inter.response.send_message(
            ctx.t("presensi.tes_success", presence=presensi.pretty(self._presensi_i18n())), ephemeral=True
        )

    @presensi.command(
        name="ubah",
        description=app_commands.locale_str(
            "Ubah presensi dengan teks bebas", key="botbrain.presensi.ubah_description"
        ),
    )
    @app_commands.describe(teks=app_commands.locale_str("Teks presensi", key="botbrain.presensi.option_teks"))
    async def _bb_manual_presensi_ubah_real(self, inter: discord.Interaction, teks: str):
        ctx = await self.bot.get_context(inter)
        await self.bot.change_presence(activity=discord.Game(name=teks + " | /help"))
        await inter.response.send_message(ctx.t("presensi.ubah_success", text=teks), ephemeral=True)

    async def _loop_bb_ubah_presensi(self):
        self.logger.info("starting presence rotation handler, shuffling!")
        while True:
            try:
                await asyncio.sleep(self.rotation_rate)
                try:
                    presensi = next(self._presensi)
                except StopIteration:
                    presensi = choice(PRESENSI_DATA)
                tl = self._presensi_i18n()
                self.logger.info(f"changing to `{presensi.pretty(tl)}`, next rotation in {self.rotation_rate} secs")
                try:
                    await self.bot.change_presence(activity=presensi.presensi(tl))
                except Exception as e:
                    self.logger.warning("failed to change presence, ignoring!", exc_info=e)
            except asyncio.CancelledError:
                self.logger.warning("stopping presences rotator")
                break


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainPresensi(bot))
