import logging

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext


class ModToolsThreads(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("ModTools.Threads")

    @commands.command(name="jointhread", aliases=["gabungthread"])
    @commands.guild_only()
    async def _modtools_jointhread(self, ctx: naoTimesContext, thread: commands.ThreadConverter = None):
        self.logger.info("Trying to join threads...")
        thread: discord.Thread = thread
        if thread is None:
            return await ctx.send("Mohon berikan thread yang valid!")
        if not isinstance(thread, discord.Thread):
            return await ctx.send("Kanal yang diberikan bukanlah thread yang valid!")

        if thread.me is not None:
            return await ctx.send("Sudah bergabung ke kanal tersebut!")

        has_perms = False
        user_perms = ctx.channel.permissions_for(ctx.author)
        if user_perms.manage_threads or user_perms.administrator:
            has_perms = True
        if thread.owner == ctx.author:
            has_perms = True
        if not has_perms:
            return await ctx.send(
                "Hanya thread starter dan moderator dengan permission "
                "`Manage Messages` yang bisa menginvite bot ke thread!"
            )

        try:
            await thread.join()
        except discord.Forbidden:
            return await ctx.send("Bot tidak dapat bergabung ke thread tersebut!", reference=ctx.message)
        await ctx.send(f"Sukses bergabung ke thread: {thread.mention}")

    @commands.command(name="leavethread", aliases=["keluarthread"])
    @commands.guild_only()
    async def _modtools_leavethread(self, ctx: naoTimesContext):
        channel = ctx.channel
        if channel.type != (discord.ChannelType.public_thread or discord.ChannelType.private_thread):
            return await ctx.send("Kanal ini bukanlah thread!")

        has_perms = False
        user_perms = ctx.channel.permissions_for(ctx.author)
        if user_perms.manage_threads or user_perms.administrator:
            has_perms = True
        if channel.owner == ctx.author:
            has_perms = True
        if not has_perms:
            return await ctx.send(
                "Hanya thread starter dan moderator dengan permission "
                "`Manage Messages` yang bisa mengeluarkan bot dari thread!"
            )

        try:
            await channel.leave()
        except discord.Forbidden:
            return await ctx.send("Bot tidak dapat keluar dari thread ini!", reference=ctx.message)
        parent = channel.parent
        if parent is not None:
            await parent.send(f"Sukses keluar dari thread: {channel.mention}")


def setup(bot: naoTimesBot):
    bot.add_cog(ModToolsThreads(bot))
