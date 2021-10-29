import logging

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot, naoTimesContext


class BotbrainPrefixes(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Prefixes")

    @commands.command(name="prefix")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def _change_prefix(self, ctx: naoTimesContext, *, message: str = None):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"Requested prefix change at {server_message}")
        server_prefix = await self.bot.redisdb.get(f"ntprefix_{server_message}")
        if not message:
            embed = discord.Embed(color=0x00AAAA)
            embed.add_field(
                name="Prefix Peladen",
                value="Tidak ada" if server_prefix is None else server_prefix,
                inline=False,
            )
            return await ctx.send(embed=embed)

        deletion = False
        if message.lower() in ["clear", "bersihkan", "hapus"]:
            res = await self.bot.redisdb.delete(f"ntprefix_{server_message}")
            deletion = True
            if res:
                self.logger.info(f"{server_message}: removing custom prefix...")
                send_txt = "Berhasil menghapus custom prefix untuk peladen ini!"
            else:
                return await ctx.send("Tidak ada prefix yang terdaftar untuk peladen ini, mengabaikan...")

        if server_prefix is not None and not deletion:
            self.logger.info(f"{server_message}: mengubah custom prefix...")
            send_txt = "Berhasil mengubah custom prefix ke `{pfx}` untuk peladen ini"
        elif server_prefix is None and not deletion:
            self.logger.info(f"{server_message}: adding custom prefix...")
            send_txt = "Berhasil menambah custom prefix `{pfx}` untuk server ini"

        if not deletion:
            await self.bot.redisdb.set(f"ntprefix_{server_message}", message)

        await self.bot.change_prefixes()
        await ctx.send(send_txt.format(pfx=message))

    @_change_prefix.error
    async def _change_prefix_error(self, error: commands.CommandError, ctx: naoTimesContext):
        if isinstance(error, commands.errors.CheckFailure):
            try:
                server_message = str(ctx.message.guild.id)
            except (AttributeError, KeyError, ValueError):
                return await ctx.send("Hanya bisa dijalankan di sebuah server!")

            server_prefix = await self.bot.redisdb.get(f"ntprefix_{server_message}")
            helpcmd = self.bot.create_help(ctx, "Prefix", color=0x00AAAA)
            helpcmd.embed.add_field(
                name="Prefix Server",
                value="Tidak ada" if server_prefix is None else server_prefix,
                inline=False,
            )
            await helpcmd.generate_aliases()
            await ctx.send(embed=helpcmd.get())

    @commands.command(name="gprefix")
    @commands.is_owner()
    async def _change_global_prefix(self, ctx: naoTimesContext, *, new_prefix: str = None):
        if not new_prefix:
            helpcmd = self.bot.create_help(ctx, "Prefix", color=0x00AAAA)
            helpcmd.embed.add_field(
                name="Prefix Global",
                value=self.bot.prefix,
                inline=False,
            )
            await helpcmd.generate_aliases()
            return await ctx.send(embed=helpcmd.get())

        self.logger.info(f"Changing global prefix to: {new_prefix}")
        await self.bot.change_global_prefix(new_prefix)
        await ctx.send(f"Sukses mengubah global prefix ke: `{new_prefix}`")


def setup(bot: naoTimesBot):
    bot.add_cog(BotbrainPrefixes(bot))
