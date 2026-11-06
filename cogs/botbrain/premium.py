"""
A helper module for premium stuff.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import OwnerGroup
from naotimes.showtimes.models import FansubRSS
from naotimes.timeparse import TimeString, TimeStringParseError


class BotBrainPremium(commands.Cog):
    premium = OwnerGroup(
        name="ntpremium",
        description=app_commands.locale_str(
            "Aktivasi fitur premium naoTimes (owner)", key="botbrain.premium.group_description"
        ),
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logging = logging.getLogger("BotBrain.Premium")

    @premium.command(
        name="fansubrss",
        description=app_commands.locale_str(
            "Aktivasi fitur premium FansubRSS untuk sebuah peladen", key="botbrain.premium.fansubrss_description"
        ),
    )
    @app_commands.describe(
        guild_id=app_commands.locale_str("ID peladen", key="botbrain.premium.option_guild"),
        durasi=app_commands.locale_str(
            "Durasi, contoh: 30d atau -1 untuk tak terbatas", key="botbrain.premium.option_duration"
        ),
    )
    async def _bb_premium_fansubrss(self, inter: discord.Interaction, guild_id: str, durasi: str):
        ctx = await self.bot.get_context(inter)
        if not guild_id.isdigit():
            return await inter.response.send_message(ctx.t("premium.invalid_guild_id"), ephemeral=True)
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            return await inter.response.send_message(ctx.t("premium.guild_not_found"), ephemeral=True)
        if self.bot.redisdb is None:
            return await inter.response.send_message(ctx.t("premium.redis_unavailable"), ephemeral=True)
        rss_metadata = await self.bot.redisdb.get(f"ntfsrss_{guild.id}")
        if rss_metadata is None:
            return await inter.response.send_message(ctx.t("premium.rss_not_enabled"), ephemeral=True)
        parsed_metadata = FansubRSS.from_dict(guild.id, rss_metadata)
        durasi_text = ctx.t("premium.indefinite")
        if durasi == "-1":
            parsed_metadata.set_indefinite()
        else:
            try:
                parse_time = TimeString.parse(durasi)
                durasi_text = str(parse_time.to_string())
                parsed_metadata.add_time(parse_time.timestamp())
            except TimeStringParseError:
                return await inter.response.send_message(ctx.t("premium.invalid_duration"), ephemeral=True)

        durasi_ask = ctx.t("premium.confirm", guild=guild, duration=durasi_text)
        if not await ctx.confirm(durasi_ask):
            return await ctx.send(ctx.t("premium.cancelled"))

        await self.bot.redisdb.set(f"ntfsrss_{guild.id}", parsed_metadata.serialize())
        await ctx.send(ctx.t("premium.success", guild=guild, duration=durasi_text))


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainPremium(bot))
