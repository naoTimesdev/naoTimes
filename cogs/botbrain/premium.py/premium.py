"""
A helper module for premium stuff.
"""

import logging

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption
from naotimes.showtimes.models import FansubRSS
from naotimes.timeparse import TimeString, TimeStringParseError


class BotBrainPremium(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logging = logging.getLogger("BotBrain.Premium")

    @commands.group(name="ntpremium")
    @commands.is_owner()
    async def _bb_premium(self, ctx: naoTimesContext):
        if not ctx.invoked_subcommand:
            if not ctx.empty_subcommand(2):
                return await ctx.send("Perintah tidak diketahui!")
            helpcmd = ctx.create_help(
                "naoTimes Premium[*]", desc="Semua perintah untuk aktivasi fitur premium naoTimes"
            )
            helpcmd.add_field(
                HelpField(
                    "ntpremium fansubrss",
                    "Aktivasi fitur premium untuk sebuah peladen!",
                    [
                        HelpOption(
                            "guild id",
                            required=True,
                        ),
                        HelpOption(
                            "durasi",
                            required=True,
                        ),
                    ],
                )
            )
            helpcmd.add_aliases()
            await ctx.send(embed=helpcmd.get())

    @_bb_premium.command(name="fansubrss", aliases=["fsrss"])
    async def _bb_premium_fansubrss(self, ctx: naoTimesContext, guild: commands.GuildConverter, durasi: str):
        if not isinstance(guild, discord.Guild):
            return await ctx.send("Guild yang diberikan bukanlah guild yang valid!")
        guild: discord.Guild = guild
        rss_metadata = await self.bot.redisdb.get(f"ntfsrss_{guild.id}")
        if rss_metadata is None:
            return await ctx.send("Guild belum mengaktifkan fitur FansubRSS!")
        parsed_metadata = FansubRSS.from_dict(guild.id, rss_metadata)
        durasi_text = "tak terbatas"
        if durasi == "-1":
            parsed_metadata.set_indefinite()
        else:
            try:
                parse_time = TimeString.parse(durasi)
                durasi_text = str(parse_time.to_string())
                parsed_metadata.add_time(parse_time.timestamp())
            except TimeStringParseError:
                return await ctx.send("Durasi waktu yang diberikan tidak dapat dimengerti!")

        durasi_ask = f"Akan mengaktifkan fitur premium di `{str(guild)}` untuk "
        durasi_ask += f"durasi `{durasi_text}`, apakah anda yakin?"
        confirmed = await ctx.confirm(durasi_ask)
        if not confirmed:
            return await ctx.send("Dibatalkan!")

        await self.bot.redisdb.set(f"ntfsrss_{guild.id}", parsed_metadata.serialize())
        await ctx.send(
            f"FansubRSS premium berhasil diaktifkan di `{str(guild)}` untuk durasi `{durasi_text}`!"
        )


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainPremium(bot))
