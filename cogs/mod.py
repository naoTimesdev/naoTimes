# -*- coding: utf-8 -*-

import asyncio
import logging
import os

import aiofiles
import discord
from discord.ext import commands, tasks
from discord.ext.commands.errors import (
    BotMissingPermissions,
    MissingPermissions,
)

import ujson


def setup(bot):
    bot.add_cog(AutoMod(bot))


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.automod_srv = []
        self.no_no_word = []
        self.logger = logging.getLogger("cogs.mod.AutoMod")
        self.mute_roles_map = {}

        self.modpath = "/root/naotimes/automod/"
        self._locked = False
        self._is_modifying = False

        self.prechecked = False
        self.__precheck_existing.start()

    @tasks.loop(seconds=1.0, count=1)
    async def __precheck_existing(self):
        metadata = await self.read_local()
        if metadata:
            self.logger.info("precheck: there's existing data, replacing self data.")
            self.automod_srv = metadata["servers"]
            self.no_no_word = metadata["words"]
        metadata2 = await self.read_local_mute()
        if metadata2:
            self.logger.info("precheck: there's mute list, adding...")
            self.mute_roles_map = metadata2
        self.prechecked = True

    async def acquire_lock(self):
        while True:
            if not self._locked:
                break
            await asyncio.sleep(0.25)
        self._locked = True

    async def release_lock(self):
        self._locked = False

    async def read_file(self, path):
        await self.acquire_lock()
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = await f.read()
        await self.release_lock()
        try:
            data = ujson.loads(data)
        except ValueError:
            pass
        return data, path

    async def save_file(self, fpath, content):
        await self.acquire_lock()
        async with aiofiles.open(fpath, "w", encoding="utf-8") as fp:
            await fp.write(content)
        await self.release_lock()

    async def read_local(self):
        metafile = os.path.join(self.modpath, "automod.json")
        if not os.path.isfile(metafile):
            return {}

        metafile, _ = await self.read_file(metafile)
        return metafile

    async def read_local_mute(self):
        metafile = os.path.join(self.modpath, "automod_mute.json")
        if not os.path.isfile(metafile):
            return {}

        metafile, _ = await self.read_file(metafile)
        return metafile

    async def save_local(self):
        metafile_path = os.path.join(self.modpath, "automod.json")
        metafile = await self.read_local()
        metafile["words"] = self.no_no_word
        metafile["servers"] = self.automod_srv
        await self.save_file(metafile_path, ujson.dumps(metafile))

    async def save_local_mute(self):
        metafile_path = os.path.join(self.modpath, "automod_mute.json")
        await self.save_file(metafile_path, ujson.dumps(self.mute_roles_map))

    async def verify_word(self, msg_data):
        msg_data = msg_data.lower()
        triggered = False
        for no_no in self.no_no_word:
            if no_no in msg_data:
                triggered = True
                break
        return triggered

    @commands.Cog.listener("on_message")
    async def new_msg(self, message):
        if self._is_modifying:
            return
        content = message.clean_content
        channel = message.channel
        if not isinstance(channel, discord.TextChannel):
            return
        if message.author.id == 558256913926848537:
            return
        server = channel.guild.id
        if server in self.automod_srv:
            do_delete = await self.verify_word(content)
            if do_delete:
                await message.delete()
                await channel.send("⚠️ Auto-mod trigger.")

    @commands.Cog.listener("on_message_edit")
    async def msg_edited(self, before, after):
        if self._is_modifying:
            return
        content = after.clean_content
        channel = after.channel
        if not isinstance(channel, discord.TextChannel):
            return
        if after.author.id == 558256913926848537:
            return
        server = channel.guild.id
        if server in self.automod_srv:
            do_delete = await self.verify_word(content)
            if do_delete:
                await after.delete()
                await channel.send("⚠️ Auto-mod trigger (Edited Message).")

    @commands.command()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def automod(self, ctx):
        self._is_modifying = True
        srv = ctx.message.guild.id
        if srv in self.automod_srv:
            self.automod_srv.remove(srv)
            await ctx.send("👮⚙️ Auto-mod has been disabled on this server. ⚙️👮")
        else:
            self.automod_srv.append(srv)
            await ctx.send("👮⚙️ Auto-mod has been enabled on this server. ⚙️👮")
        await self.save_local()
        await asyncio.sleep(1.0)
        self._is_modifying = False

    @commands.command()
    async def automod_word(self, ctx, *, word):
        self._is_modifying = True
        if ctx.message.author.id != 466469077444067372:
            return
        self.no_no_word.append(word)
        await ctx.send("⚙️ Added new word.")
        await self.save_local()
        await asyncio.sleep(1.0)
        self._is_modifying = False

    @commands.command()
    async def automod_rm(self, ctx, *, word):
        self._is_modifying = True
        if ctx.message.author.id != 466469077444067372:
            return
        if word not in self.no_no_word:
            return await ctx.send("⚙️ Can't find that word.")
        self.no_no_word.remove(word)
        await ctx.send(f"⚙️ Removed `{word}`.")
        await self.save_local()
        await asyncio.sleep(1.0)
        self._is_modifying = False

    @commands.command()
    async def automod_save(self, ctx):
        if ctx.message.author.id != 466469077444067372:
            return
        await self.save_local()
        await ctx.send(f"⚙️ Local file have been overwritten.")

    @commands.command()
    async def automod_info(self, ctx):
        if ctx.message.author.id != 466469077444067372:
            return
        text_res = "**Server Watched:**\n"
        automod_srv = [str(srv) for srv in self.automod_srv]
        text_res += "\n".join(automod_srv)
        text_res += "\n"
        text_res += "**Banned Words**:\n"
        text_res += "\n".join(self.no_no_word)
        await ctx.send(text_res)

    @automod.error
    async def automod_error(self, ctx, error):
        if isinstance(error, BotMissingPermissions):
            return await ctx.send("Bot tidak memiliki hak `Manage Message`.")
        elif isinstance(error, MissingPermissions):
            return await ctx.send("Bukan admin.")

    @commands.command()
    async def slowmode(self, ctx, amount: int, channel=None):
        fallback_channel = ctx.message.channel
        if channel is not None:
            try:
                if channel.isdigit():
                    channel = ctx.message.guild.get_channel(int(channel))
                else:
                    channel = ctx.message.channel_mentions[0]
            except IndexError:
                channel = fallback_channel
        else:
            channel = fallback_channel
        if amount < 0 or amount > 21600:
            return await ctx.send("Minimum slowmode is 0 seconds" "\nMaximum slowmode is 21600 seconds")
        try:
            await channel.edit(slowmode_delay=amount)
        except discord.Forbidden:
            return await ctx.send(
                "Please give bot `Manage Message` and `Manage Channels` " "permission for this channel."
            )
        await ctx.send("⚙️ Slowmode Activated!\n" f"User can sent message every: {amount} seconds")

    @commands.command()
    async def mute(self, ctx, user):
        try:
            _ = ctx.message.guild.channels
        except Exception:
            return await ctx.send("Not in a server.")

        bot_user = ctx.message.guild.get_member(self.bot.user.id)
        bot_perms = bot_user.guild_permissions

        self.logger.info("checking bot perms.")
        if not bot_perms.manage_channels or not bot_perms.manage_roles or not bot_perms.manage_permissions:
            if not bot_perms.administrator:
                return await ctx.send(
                    "Bot is missing one of this perms:\n"
                    "- Manage Channels\n"
                    "- Manage Roles\n"
                    "- Manage Permissions"
                )

        try:
            if user.isdigit():
                user = ctx.message.guild.get_member(int(user))
            else:
                user = ctx.message.mentions[0]
        except IndexError:
            user = ctx.guild.get_member_named(user)
        if not user:
            user = ctx.guild.get_member_named(user)

        if not isinstance(user, discord.Member):
            return await ctx.send("Not in a server.")

        server_id = str(ctx.message.guild.id)
        if server_id not in self.mute_roles_map:
            self.logger.info("creating roles.")
            perms = discord.Permissions(
                manage_channels=False,
                manage_guild=False,
                read_messages=True,
                view_channel=True,
                send_messages=False,
                send_tts_messages=False,
                manage_messages=False,
                embed_links=False,
                attach_files=False,
                read_message_history=True,
                mention_everyone=False,
                use_external_emojis=False,
                manage_permissions=False,
                manage_emojis=False,
                manage_webhooks=False,
                manage_roles=False,
                manage_nicknames=False,
                add_reactions=False,
                change_nickname=False,
            )
            mute_roles = await ctx.message.guild.create_role(
                name="Muted by naoTimes",
                permissions=perms,
                hoist=False,
                mentionable=True,
                reason="Auto-add by naoTimes moderation cogs",
            )
            self.mute_roles_map[server_id] = mute_roles.id
            await self.save_local_mute()

            guild_channels = await ctx.message.guild.fetch_channels()
            for channel in guild_channels:
                try:
                    self.logger.info(f"{channel.name}: setting channel perms.")
                    await channel.set_permissions(
                        mute_roles,
                        manage_channels=False,
                        read_messages=True,
                        send_messages=False,
                        send_tts_messages=False,
                        manage_messages=False,
                        embed_links=False,
                        attach_files=False,
                        read_message_history=True,
                        mention_everyone=False,
                        use_external_emojis=False,
                        manage_permissions=False,
                        manage_webhooks=False,
                        add_reactions=False,
                        reason="Auto-set by naoTimes moderation cogs.",
                    )
                except discord.Forbidden:
                    self.logger.warn(f"{channel.name}: failed to set perms.")
        else:
            mute_roles = ctx.message.guild.get_role(self.mute_roles_map[server_id])

        self.logger.info("Muting user!")
        await user.add_roles(mute_roles, reason="Set by mute moderation cogs.")
        await ctx.send("User successfully muted.")
