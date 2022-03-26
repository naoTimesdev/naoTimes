import logging

import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.timeparse import TimeString


class ModtoolsMessage(commands.Cog):
    MAX_TIME = TimeString.parse("24h")

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("ModTools.MessageControl")

    @commands.command(name="clean", aliases=["bersihkan"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    async def _modtools_clean(self, ctx: naoTimesContext, count: int = 50):
        """
        Bersihkan pesan di kanal di mana perintah ini digunakan!

        Perintah ini akan menghapus semua pesan yang lebih lama dari 14 hari
        """
        if count >= 100:
            return await ctx.send("Batas maksimal pesan yang bisa dihapus adalah 100 pesan!")
        if count <= 0:
            return await ctx.send("Mohon berikan total pesan yang ingin dihapus!")

        def not_self(m: disnake.Message):
            return m.id != ctx.message.id

        kanal: disnake.TextChannel = ctx.channel
        deleted_messages = await kanal.purge(limit=count, bulk=True, check=not_self)
        await ctx.send_timed(f"Berhasil menghapus {len(deleted_messages)} pesan!")
        try:
            await ctx.message.delete(no_log=True)
        except (disnake.NotFound, disnake.Forbidden, disnake.HTTPException):
            pass

    @commands.command(name="nuke", aliases=["nuklir"])
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def _modtools_nuke_channel(
        self, ctx: naoTimesContext, channel: commands.TextChannelConverter = None
    ):
        if not channel:
            channel = ctx.channel
        if not isinstance(channel, disnake.TextChannel):
            return await ctx.send("Kanal yang dipilih bukanlah kanal teks!")

        confirm = await ctx.confirm(
            f"Apakah anda yakin mau menghapus semua pesan di kanal {channel.mention}?"
        )
        if not confirm:
            return await ctx.send("*Dibatalkan*")
        real_and_true = await ctx.send("Mencoba menghapus semua pesan...")

        def _simple_check(message: disnake.Message):
            return message.id != real_and_true.id

        deleted = await channel.purge(limit=None, check=_simple_check)
        count = len(deleted)
        await ctx.send_timed(f"Berhasil menghapus {count:,} pesan!")
        await real_and_true.delete()

    @commands.command(name="nukeuser", aliases=["nukliruser"])
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def _modtools_nuke_user(
        self, ctx: naoTimesContext, user: commands.ObjectConverter, time_limit: str = "24h"
    ):
        guild: disnake.Guild = ctx.guild
        if not isinstance(user, disnake.Object):
            return await ctx.send("Tidak dapat menemukan pengguna tersebut!")

        maximum_deletion = TimeString.parse(time_limit)
        if maximum_deletion > self.MAX_TIME:
            return await ctx.send(f"{maximum_deletion} tidak dapat melebihi {self.MAX_TIME}!")

        bot_member = guild.get_member(self.bot.user.id)

        max_del_ts = maximum_deletion.to_delta()
        max_backward_time = self.bot.now() - max_del_ts
        confirm = await ctx.confirm(f"Apakah anda yakin akan menghapus semua pesan dari {user}?")
        if not confirm:
            return await ctx.send("*Dibatalkan*")

        init_msg = await ctx.send("Mulai proses menghapus pesan...")

        def _check_validate(m: disnake.Message):
            return m.author.id == user.id and init_msg.id != m.id

        all_channels = guild.text_channels
        all_deleted = 0
        for kanal in all_channels:
            self.logger.info(f"Trying to delete message by user `{user}` in `{kanal}`")
            permission: disnake.Permissions = kanal.permissions_for(bot_member)
            if not permission.manage_messages:
                continue
            deleted = await kanal.purge(limit=None, check=_check_validate, after=max_backward_time.datetime)
            count = len(deleted)
            await init_msg.edit(f"Berhasil menghapus {count:,} pesan dari kanal #{kanal.mention}")
            all_deleted += count

        await init_msg.edit(f"Berhasil menghapus {all_deleted:,} pesan dari semua kanal!")


def setup(bot: naoTimesBot):
    bot.add_cog(ModtoolsMessage(bot))
