"""Globally set maintenance mode for naoTimes.

While maintenance is active, `naoTimesAppTree.interaction_check` blocks every
command for non-owners. There is nothing to patch on the command tree.
"""

import logging

import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import OwnerGroup


class BotBrainMaintenance(commands.Cog):
    maintenance = OwnerGroup(
        name="maintenance",
        description=app_commands.locale_str(
            "Atur mode maintenance bot (owner)", key="botbrain.maintenance.group_description"
        ),
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Maintenance")

    @staticmethod
    def _parse_time(raw: str) -> arrow.Arrow | None:
        try:
            return arrow.get(raw)
        except (arrow.ParserError, ValueError):
            return None

    @maintenance.command(
        name="mulai",
        description=app_commands.locale_str("Jadwalkan mode maintenance", key="botbrain.maintenance.mulai_description"),
    )
    @app_commands.describe(
        mulai=app_commands.locale_str(
            "Waktu mulai, contoh: 2026-11-07T01:00:00+07:00", key="botbrain.maintenance.option_start"
        ),
        selesai=app_commands.locale_str(
            "Waktu selesai, contoh: 2026-11-07T03:00:00+07:00", key="botbrain.maintenance.option_end"
        ),
    )
    async def _bb_maintenance_start(self, inter: discord.Interaction, mulai: str, selesai: str):
        ctx = await self.bot.get_context(inter)
        start = self._parse_time(mulai)
        end = self._parse_time(selesai)
        if start is None or end is None:
            return await inter.response.send_message(
                ctx.t("maintenance.invalid_time"),
                ephemeral=True,
            )
        if start >= end:
            return await inter.response.send_message(ctx.t("maintenance.start_after_end"), ephemeral=True)

        text = ctx.t("maintenance.confirm", start=start.int_timestamp, end=end.int_timestamp)
        if not await ctx.confirm(text):
            return await ctx.send(ctx.t("maintenance.cancelled"))

        self.bot.set_maintenance(start, end)
        await ctx.send(ctx.t("maintenance.scheduled"))

    @maintenance.command(
        name="batal",
        description=app_commands.locale_str("Batalkan mode maintenance", key="botbrain.maintenance.batal_description"),
    )
    async def _bb_maintenance_cancel(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        if self.bot.maintenance is None:
            return await inter.response.send_message(ctx.t("maintenance.none_scheduled"), ephemeral=True)
        self.bot.maintenance = None
        await inter.response.send_message(ctx.t("maintenance.cancelled_mode"), ephemeral=True)


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainMaintenance(bot))
