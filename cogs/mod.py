# -*- coding: utf-8 -*-

import asyncio
import glob
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

import aiofiles
import discord
import ujson
from discord.ext import commands, tasks
from discord.ext.commands.errors import BotMissingPermissions, MissingPermissions
from nthelper.bot import naoTimesBot
from nthelper.utils import send_timed_msg


def setup(bot):
    bot.add_cog(AutoMod(bot))


class AutoMod(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.automod_srv: List[Union[str, int]] = []
        self.no_no_word: List[str] = []
        self.logger = logging.getLogger("cogs.mod.AutoMod")
        self.mute_roles_map: Dict[int, int] = {}
        self.shadowban_map: Dict[str, List[str]] = {}
        self.serverlog_map: Dict[int, Dict[str, Union[int, bool]]] = {}

        self.modpath = bot.automod_folder
        self._locked = False
        self._is_modifying = False

        self.prechecked = False
        self.__precheck_existing.start()

        self._srvlog_msg_queue: asyncio.Queue = asyncio.Queue()
        self._srvlog_member_queue: asyncio.Queue = asyncio.Queue()
        self._srvlog_msg_task: asyncio.Task = asyncio.Task(self._handle_srvlog_message())
        self._srvlog_member_task: asyncio.Task = asyncio.Task(self._handle_srvlog_member())

    def cog_unload(self):
        self.logger.info("shutting down task...")
        self._srvlog_msg_task.cancel()
        self._srvlog_member_task.cancel()

    @tasks.loop(seconds=1.0, count=1)
    async def __precheck_existing(self):
        metadata = await self.read_local()
        if metadata:
            self.logger.info("automod_word: there's existing data, replacing self data.")
            self.automod_srv = metadata["servers"]
            self.no_no_word = metadata["words"]
        metadata2 = await self.read_local_mute()
        if metadata2:
            self.logger.info("mute: there's mute list, adding...")
            self.mute_roles_map = metadata2
        metadata3 = await self.read_local_shadowban()
        if metadata3:
            self.logger.info("shadow_ban: there's shadowbanned list, adding...")
            self.shadowban_map = metadata3
        srvs_log = glob.glob(os.path.join(self.modpath, "*.srvlog"))
        for srv in srvs_log:
            path, _ = os.path.basename(srv).split(".")
            meta_srv_log = await self.read_local_server_log(path)
            if meta_srv_log:
                self.logger.info(f"server_log: adding server {path}...")
                self.serverlog_map[int(path)] = meta_srv_log
        self.prechecked = True

    async def acquire_lock(self):
        while True:
            if not self._locked:
                break
            await asyncio.sleep(0.25)
        self._locked = True

    async def release_lock(self):
        self._locked = False

    async def read_file(self, path: str):
        await self.acquire_lock()
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            data = await f.read()
        await self.release_lock()
        try:
            data = ujson.loads(data)
        except ValueError:
            pass
        return data, path

    async def save_file(self, fpath: str, content):
        await self.acquire_lock()
        async with aiofiles.open(fpath, "w", encoding="utf-8") as fp:
            await fp.write(content)
        await self.release_lock()

    async def read_local(self) -> dict:
        metafile = os.path.join(self.modpath, "automod.json")
        if not os.path.isfile(metafile):
            return {}

        metafile, _ = await self.read_file(metafile)
        return metafile  # type: ignore

    async def read_local_mute(self) -> dict:
        metafile = os.path.join(self.modpath, "automod_mute.json")
        if not os.path.isfile(metafile):
            return {}

        metafile, _ = await self.read_file(metafile)
        return metafile  # type: ignore

    async def read_local_shadowban(self) -> dict:
        metafile = os.path.join(self.modpath, "automod_shadowban.json")
        if not os.path.isfile(metafile):
            return {}

        metafile, _ = await self.read_file(metafile)
        return metafile  # type: ignore

    async def read_local_server_log(self, server_id: Union[str, int]) -> dict:
        metafile = os.path.join(self.modpath, f"{server_id}.srvlog")
        if not os.path.isfile(metafile):
            return {}
        metafile, _ = await self.read_file(metafile)
        return metafile  # type: ignore

    async def save_local(self):
        metafile_path = os.path.join(self.modpath, "automod.json")
        metafile = await self.read_local()
        metafile["words"] = self.no_no_word
        metafile["servers"] = self.automod_srv
        await self.save_file(metafile_path, ujson.dumps(metafile))

    async def save_local_mute(self):
        metafile_path = os.path.join(self.modpath, "automod_mute.json")
        await self.save_file(metafile_path, ujson.dumps(self.mute_roles_map))

    async def save_local_shadowban(self):
        metafile_path = os.path.join(self.modpath, "automod_shadowban.json")
        await self.save_file(metafile_path, ujson.dumps(self.shadowban_map))

    async def save_local_server_log(self, server_id: int):
        metafile_path = os.path.join(self.modpath, f"{server_id}.srvlog")
        await self.save_file(metafile_path, ujson.dumps(self.serverlog_map[server_id]))

    async def verify_word(self, msg_data: str) -> bool:
        msg_data = msg_data.lower()
        triggered = False
        for no_no in self.no_no_word:
            if no_no in msg_data:
                triggered = True
                break
        return triggered

    @commands.Cog.listener("on_message")
    async def automod_watcher(self, message):
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
    async def automod_watcher_editing(self, before, after):
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

    @commands.Cog.listener("on_member_join")
    async def shadowban_watcher(self, member: discord.Member):
        self.logger.info("new member joined, checking shadowban list...")
        guilds = member.guild
        srv_id = str(guilds.id)
        member_id = str(member.id)

        if srv_id in self.shadowban_map:
            if member_id in self.shadowban_map[srv_id]:
                self.logger.info(f"Banning: {member_id}")
                await guilds.ban(user=member, reason="Banned from shadowban list, goodbye o7")

    async def _quick_search_ids(self, member_id: int):
        found_data = None
        for member in self.bot.get_all_members():
            if member.id == member_id:
                found_data = member
                break
        return found_data if found_data is not None else member_id

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def shadowban(self, ctx, user_id: int):
        srv_id = str(ctx.message.guild.id)
        if srv_id not in self.shadowban_map:
            self.shadowban_map[srv_id] = []
        self.shadowban_map[srv_id].append(str(user_id))
        self.logger.info(f"{srv_id}: User {user_id} has been shadowbanned.")
        await self.save_local_shadowban()
        if int(srv_id) in self.serverlog_map:
            srvlog_settings = self.serverlog_map[int(srv_id)]
            member_data = await self._quick_search_ids(user_id)
            dict_data = {"settings": srvlog_settings, "type": "shadowban", "user_data": member_data}
            await self.srvlog_add_to_queue(dict_data, "member")
        await ctx.send(f"User `{user_id}` telah di shadowbanned dari server ini.")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unshadowban(self, ctx, user_id: int):
        srv_id = str(ctx.message.guild.id)
        if srv_id not in self.shadowban_map:
            return await ctx.send("Tidak ada user yang di shadowbanned di server ini.")
        if not self.shadowban_map[srv_id]:
            return await ctx.send("Tidak ada user yang di shadowbanned di server ini.")
        user_id = str(user_id)  # type: ignore
        if user_id not in self.shadowban_map[srv_id]:
            return await ctx.send("User tersebut tidak ada di list shadowbanned server.")
        self.shadowban_map[srv_id].remove(user_id)  # type: ignore
        self.logger.info(f"{srv_id}: User {user_id} has been unshadowbanned.")
        await self.save_local_shadowban()
        if int(srv_id) in self.serverlog_map:
            srvlog_settings = self.serverlog_map[int(srv_id)]
            member_data = await self._quick_search_ids(int(user_id))
            dict_data = {"settings": srvlog_settings, "type": "unshadowban", "user_data": member_data}
            await self.srvlog_add_to_queue(dict_data, "member")
        await ctx.send(f"User `{user_id}` telah di unshadowbanned dari server ini.")

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
    @commands.is_owner()
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
    @commands.is_owner()
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
    @commands.is_owner()
    async def automod_save(self, ctx):
        if ctx.message.author.id != 466469077444067372:
            return
        await self.save_local()
        await ctx.send("⚙️ Local file have been overwritten.")

    @commands.command()
    @commands.is_owner()
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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

    # Server logging part
    def ctime(self) -> datetime:
        return datetime.now(timezone.utc)

    def truncate(self, msg: str, limit: int) -> str:
        if len(msg) <= limit:
            return msg
        msg = msg[: limit - 8] + " [...]"
        return msg

    def strftime(self, dt_time: datetime) -> str:
        month_en = dt_time.strftime("%B")
        tl_map = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": "April",
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": "September",
            "October": "Oktober",
            "November": "November",
            "December": "Desember",
        }
        month_id = tl_map.get(month_en, month_en)
        final_data = dt_time.strftime("%d ") + month_id
        final_data += dt_time.strftime(" %Y, %H:%M:%S UTC")
        return final_data

    async def _handle_srvlog_message(self):
        self.logger.info("starting serverlog message handler...")
        while True:
            try:
                msg_data: dict = await self._srvlog_msg_queue.get()
                log_channel: discord.TextChannel = self.bot.get_channel(msg_data["settings"]["id"])
                if log_channel is not None:
                    kanal_name = msg_data["kanal"]
                    user_data = msg_data["author"]
                    if msg_data["type"] == "edit":
                        before, after = msg_data["before"], msg_data["after"]
                        embed = discord.Embed(title="📝 Pesan diubah", color=0xE7DC8C, timestamp=self.ctime())
                        embed.add_field(name="Sebelum", value=self.truncate(before, 1024), inline=False)
                        embed.add_field(name="Sesudah", value=self.truncate(after, 1024), inline=False)
                        embed.set_footer(text=f"📝 Kanal #{kanal_name}")
                        embed.set_author(name=user_data["name"], icon_url=user_data["avatar"])
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "delete":
                        deleted = msg_data["msg"]
                        embed = discord.Embed(title="🚮 Pesan dihapus", color=0xD66B6B, timestamp=self.ctime())
                        embed.description = self.truncate(deleted, 2048)
                        embed.set_footer(text=f"❌ Kanal #{kanal_name}")
                        embed.set_author(name=user_data["name"], icon_url=user_data["avatar"])
                        await log_channel.send(embed=embed)
                self._srvlog_msg_queue.task_done()
            except asyncio.CancelledError:
                return

    async def _handle_srvlog_member(self):
        self.logger.info("starting serverlog member handler...")
        while True:
            try:
                msg_data: dict = await self._srvlog_member_queue.get()
                log_channel: discord.TextChannel = self.bot.get_channel(msg_data["settings"]["id"])
                if log_channel is not None:
                    user_data: Union[discord.Member, int] = msg_data["user_data"]
                    desc_data = []
                    if "shadowban" not in msg_data["type"]:
                        desc_data.append(f"**• Pengguna**: {user_data.name}#{user_data.discriminator}")
                        desc_data.append(f"**• ID Pengguna**: {user_data.id}")
                        desc_data.append(f"**• Akun Bot?**: {'Ya' if user_data.bot else 'Tidak'}")
                        desc_data.append(f"**• Akun Dibuat**: {self.strftime(user_data.created_at)}")
                    else:
                        if isinstance(user_data, int):
                            desc_data.append(f"**• ID Pengguna**: {user_data}")
                        else:
                            desc_data.append(f"**• Pengguna**: {user_data.name}#{user_data.discriminator}")
                            desc_data.append(f"**• ID Pengguna**: {user_data.id}")
                            desc_data.append(f"**• Akun Bot?**: {'Ya' if user_data.bot else 'Tidak'}")
                            desc_data.append(f"**• Akun Dibuat**: {self.strftime(user_data.created_at)}")
                    if msg_data["type"] == "join":
                        embed = discord.Embed(
                            title="📥 Anggota Bergabung", color=0x83D66B, timestamp=self.ctime()
                        )
                        embed.description = "\n".join(desc_data)
                        embed.set_footer(text="🚪 Bergabung")
                        embed.set_author(
                            name=f"{user_data.name}#{user_data.discriminator}",
                            icon_url=str(user_data.avatar_url),
                        )
                        embed.set_thumbnail(url=str(user_data.avatar_url))
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "leave":
                        embed = discord.Embed(
                            title="📤 Anggota Keluar", color=0xD66B6B, timestamp=self.ctime()
                        )
                        embed.description = "\n".join(desc_data)
                        embed.set_footer(text="🚪 Keluar")
                        embed.set_author(
                            name=f"{user_data.name}#{user_data.discriminator}",
                            icon_url=str(user_data.avatar_url),
                        )
                        embed.set_thumbnail(url=str(user_data.avatar_url))
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "ban":
                        embed = discord.Embed(
                            title="🔨 Anggota terbanned", color=0x8B0E0E, timestamp=self.ctime()
                        )
                        ban_data = msg_data["ban_data"]
                        embed.description = "\n".join(desc_data)
                        if ban_data["executor"] is not None:
                            embed.add_field(name="Eksekutor", value=ban_data["executor"])
                        embed.add_field(name="Alasan", value=f"```\n{ban_data['reason']}\n```", inline=False)
                        embed.set_footer(text="🚪🔨 Banned.")
                        embed.set_author(
                            name=f"{user_data.name}#{user_data.discriminator}",
                            icon_url=str(user_data.avatar_url),
                        )
                        embed.set_thumbnail(url=str(user_data.avatar_url))
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "unban":
                        embed = discord.Embed(
                            title="🔨👼 Anggota diunbanned", color=0x2BCEC2, timestamp=self.ctime()
                        )
                        embed.description = "\n".join(desc_data)
                        embed.set_footer(text="🚪👼 Unbanned.")
                        embed.set_author(
                            name=f"{user_data.name}#{user_data.discriminator}",
                            icon_url=str(user_data.avatar_url),
                        )
                        embed.set_thumbnail(url=str(user_data.avatar_url))
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "shadowban":
                        embed = discord.Embed(
                            title="⚒ Anggota tershadowbanned", color=0xE0E0E, timestamp=self.ctime()
                        )
                        embed.description = "\n".join(desc_data)
                        embed.set_footer(text="🚪🖤 Shadowbanned.")
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "unshadowban":
                        embed = discord.Embed(
                            title="⚒👼 Anggota diunshadowbanned", color=0x2BCEC2, timestamp=self.ctime()
                        )
                        embed.description = "\n".join(desc_data)
                        embed.set_footer(text="🖤👼 Unshadowbanned.")
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "nick":
                        embed = discord.Embed(
                            title="💳 Perubahan Nickname", color=0x322D83, timestamp=self.ctime()
                        )
                        old_nick, new_nick = msg_data["nick_0"], msg_data["nick_1"]
                        nick_desc = []
                        nick_desc.append(
                            f"• Sebelumnya: **{old_nick if old_nick is not None else '*Tidak ada.*'}**"
                        )
                        nick_desc.append(
                            f"• Sekarang: **{new_nick if new_nick is not None else '*Dihapus.*'}**"
                        )
                        embed.set_author(
                            name=f"{user_data.name}#{user_data.discriminator}",
                            icon_url=str(user_data.avatar_url),
                        )
                        embed.description = "\n".join(nick_desc)
                        embed.set_footer(text="📎 Perubahan Nickname.")
                        await log_channel.send(embed=embed)
                    elif msg_data["type"] == "roles":
                        embed = discord.Embed(
                            title="🤵 Perubahan Role", color=0x832D64, timestamp=self.ctime()
                        )
                        added_role_desc = []
                        removed_role_desc = []
                        for role in msg_data["added_roles"]:
                            added_role_desc.append(f"- **{role.name}** `[{role.id}]`")
                        for role in msg_data["removed_roles"]:
                            removed_role_desc.append(f"- **{role.name}** `[{role.id}]`")
                        embed.set_author(
                            name=f"{user_data.name}#{user_data.discriminator}",
                            icon_url=str(user_data.avatar_url),
                        )
                        if added_role_desc:
                            embed.add_field(
                                name="🆕 Penambahan", value="\n".join(added_role_desc), inline=False
                            )
                        if removed_role_desc:
                            embed.add_field(
                                name="❎ Dicabut", value="\n".join(removed_role_desc), inline=False
                            )
                        embed.set_footer(text="⚖ Perubahan Roles.")
                        await log_channel.send(embed=embed)
                self._srvlog_member_queue.task_done()
            except asyncio.CancelledError:
                return

    async def srvlog_add_to_queue(self, dataset: dict, log_type: str):
        if log_type == "msg":
            await self._srvlog_msg_queue.put(dataset)
        elif log_type == "member":
            await self._srvlog_member_queue.put(dataset)
        elif log_type == "guild":
            pass

    def check_if_gucci(
        self,
        context: Union[discord.Message, discord.Member, discord.Guild],
        setting_check: str,
        include_bot: bool = False,
    ) -> Tuple[bool, Optional[discord.Guild], Optional[dict]]:
        """Check if the listener can continue

        :param context: context to check.
        :type context: Union[discord.Message, discord.Member]
        :return: should continue or not
        :rtype: bool
        """
        server_data = context
        if not isinstance(context, discord.Guild):
            server_data = context.guild
        user_data = context
        if isinstance(context, discord.Message):
            user_data = context.author
        if isinstance(user_data, (discord.Member, discord.User)) and not include_bot:
            if user_data.bot:
                return False, None, None
        if server_data is None:
            return False, None, None
        if server_data.id not in self.serverlog_map:
            return False, server_data, None
        srvlog_settings = self.serverlog_map[server_data.id]
        log_channel: discord.TextChannel = self.bot.get_channel(srvlog_settings["id"])
        if log_channel is None:
            return False, server_data, srvlog_settings
        if not srvlog_settings[setting_check]:
            return False, server_data, srvlog_settings
        return True, server_data, srvlog_settings

    @commands.Cog.listener("on_message_edit")
    async def log_server_message_edit(self, before: discord.Message, after: discord.Message):
        is_gucci, server_data, srvlog_settings = self.check_if_gucci(before, "edit_msg")
        if not is_gucci:
            return
        user_data: discord.Member = before.author
        channel_data: discord.TextChannel = before.channel
        dict_data = {
            "kanal": channel_data.name,
            "author": {
                "name": f"{user_data.name}#{user_data.discriminator}",
                "avatar": str(user_data.avatar_url),
            },
            "settings": srvlog_settings,
            "before": before.content,
            "after": after.content,
            "type": "edit",
        }
        await self.srvlog_add_to_queue(dict_data, "msg")

    @commands.Cog.listener("on_message_delete")
    async def log_server_message_delete(self, message: discord.Message):
        is_gucci, server_data, srvlog_settings = self.check_if_gucci(message, "delete_msg")
        if not is_gucci:
            return
        user_data: discord.Member = message.author
        channel_data: discord.TextChannel = message.channel
        dict_data = {
            "kanal": channel_data.name,
            "author": {
                "name": f"{user_data.name}#{user_data.discriminator}",
                "avatar": str(user_data.avatar_url),
            },
            "settings": srvlog_settings,
            "msg": message.content,
            "type": "delete",
        }
        await self.srvlog_add_to_queue(dict_data, "msg")

    @commands.Cog.listener("on_member_update")
    async def log_server_member_nick_update(self, before: discord.Member, after: discord.Member):
        is_gucci, _, srvlog_settings = self.check_if_gucci(before, "nick_update")
        if not is_gucci:
            return
        nick_before, nick_after = before.nick, after.nick
        if nick_before == nick_after:
            return
        dict_data = {
            "user_data": before,
            "settings": srvlog_settings,
            "nick_0": nick_before,
            "nick_1": nick_after,
            "type": "nick",
        }
        await self.srvlog_add_to_queue(dict_data, "member")

    @commands.Cog.listener("on_member_update")
    async def log_server_member_role_update(self, before: discord.Member, after: discord.Member):
        is_gucci, _, srvlog_settings = self.check_if_gucci(before, "role_update")
        if not is_gucci:
            return
        role_before, role_after = before.roles, after.roles
        if len(role_before) == len(role_after):
            return
        newly_added = []
        for aft in role_after:
            if aft not in role_before:
                newly_added.append(aft)
        removed_role = []
        for bef in role_before:
            if bef not in role_after:
                removed_role.append(bef)
        dict_data = {
            "user_data": before,
            "settings": srvlog_settings,
            "added_roles": newly_added,
            "removed_roles": removed_role,
            "type": "roles",
        }
        await self.srvlog_add_to_queue(dict_data, "member")

    @commands.Cog.listener("on_member_join")
    async def log_server_member_join(self, member: discord.Member):
        is_gucci, _, srvlog_settings = self.check_if_gucci(member, "member_join", True)
        if not is_gucci:
            return
        dict_data = {
            "user_data": member,
            "settings": srvlog_settings,
            "type": "join",
        }
        await self.srvlog_add_to_queue(dict_data, "member")

    @commands.Cog.listener("on_member_remove")
    async def log_server_member_leave(self, member: discord.Member):
        is_gucci, _, srvlog_settings = self.check_if_gucci(member, "member_leave", True)
        if not is_gucci:
            return
        dict_data = {
            "user_data": member,
            "settings": srvlog_settings,
            "type": "leave",
        }
        await self.srvlog_add_to_queue(dict_data, "member")

    @commands.Cog.listener("on_member_ban")
    async def log_server_member_ban(self, guild: discord.Guild, member: Union[discord.Member, discord.User]):
        is_gucci, _, srvlog_settings = self.check_if_gucci(guild, "member_ban", True)
        if not is_gucci:
            return
        banned_by = None
        reason = "Tidak ada alasan."
        try:
            ban_data = await guild.fetch_ban(member)
            reason = ban_data.reason
            user_banner = ban_data.user
            banned_by = f"<@{user_banner.id}> [{user_banner.name}#{user_banner.discriminator}]"
        except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
            pass
        dict_data = {
            "user_data": member,
            "ban_data": {"executor": banned_by, "reason": reason},
            "settings": srvlog_settings,
            "type": "ban",
        }
        await self.srvlog_add_to_queue(dict_data, "member")

    @commands.Cog.listener("on_member_unban")
    async def log_server_member_unban(
        self, guild: discord.Guild, member: Union[discord.Member, discord.User]
    ):
        is_gucci, _, srvlog_settings = self.check_if_gucci(guild, "member_unban", True)
        if not is_gucci:
            return
        dict_data = {
            "user_data": member,
            "settings": srvlog_settings,
            "type": "unban",
        }
        await self.srvlog_add_to_queue(dict_data, "member")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def serverlog(self, ctx):
        server_data: discord.Guild = ctx.message.guild
        server_id = server_data.id
        channel_id = ctx.message.channel.id
        original_author = ctx.message.author.id
        srv_log_path = os.path.join(self.modpath, f"{server_id}.srvlog")

        self.logger.info(f"{server_id}: initiated server logging...")

        def check_if_author(message):
            self.logger.info(f"Checking if {original_author} is the same as {message.author.id}")
            return message.author.id == original_author and message.channel.id == channel_id

        def bool_to_stat(tf: bool) -> str:
            return "Aktif" if tf else "Nonaktif"

        metadata_srvlog = {
            "id": 0,
            "edit_msg": False,
            "delete_msg": False,
            "member_join": False,
            "member_leave": False,
            "member_ban": False,
            "member_unban": False,
            "nick_update": False,
            "role_update": False,
        }
        if not os.path.isfile(srv_log_path):
            channel_msg = await ctx.send(
                "Ketik ID Kanal atau mention Kanal yang ingin dijadikan tempat *logging* peladen.\n"
                "Ketik `cancel` untuk membatalkan."
            )
            self.logger.info(f"{server_id}: no channel set, asking user...")
            while True:
                channel_input = await self.bot.wait_for("message", check=check_if_author)
                channel_text_data = channel_input.content
                channel_mentions_data = channel_input.channel_mentions
                if channel_text_data == ("cancel"):
                    return await ctx.send("Dibatalkan.")
                else:
                    if channel_mentions_data:
                        new_channel_id = channel_mentions_data[0].id
                        metadata_srvlog["id"] = new_channel_id
                        await send_timed_msg(ctx, f"Channel berhasil diubah ke: <#{new_channel_id}>", 2)
                        break
                    elif channel_text_data.isdigit():
                        new_channel_id = int(channel_text_data)
                        if self.bot.get_channel(new_channel_id) is not None:
                            metadata_srvlog["id"] = new_channel_id
                            await send_timed_msg(ctx, f"Channel berhasil diubah ke: <#{new_channel_id}>", 2)
                            break
                        else:
                            await send_timed_msg(ctx, "Tidak dapat menemukan channel tersebut.", 2)
                    else:
                        await send_timed_msg(ctx, "Channel yang diberikan tidak valid.", 2)
            await channel_msg.delete()
        else:
            metadata_srvlog = await self.read_local_server_log(server_id)

        number_reactions = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "✅",
            "❌",
        ]

        self.logger.info(f"{server_id}: preparing data...")

        async def _generate_embed(datasete: dict) -> discord.Embed:
            embed = discord.Embed(title="Pencatatan Peladen", color=0x2D8339)
            embed.description = f"Kanal pencatatan: <#{datasete['id']}>\n`[{datasete['id']}]`"
            embed.add_field(
                name="1️⃣ Pesan (Edited/Deleted)",
                value="Aktif" if datasete["edit_msg"] and datasete["delete_msg"] else "Tidak aktif",
                inline=False,
            )
            embed.add_field(
                name="2️⃣ Pengguna (Join/Leave)",
                value="Aktif" if datasete["member_join"] and datasete["member_leave"] else "Tidak aktif",
                inline=False,
            )
            embed.add_field(
                name="3️⃣ Ban (Ban/Unban/Shadowban/Unshadowban)",
                value="Aktif" if datasete["member_ban"] and datasete["member_unban"] else "Tidak aktif",
                inline=False,
            )
            embed.add_field(
                name="4️⃣ Nickname",
                value="Aktif" if datasete["nick_update"] else "Tidak aktif",
                inline=False,
            )
            embed.add_field(
                name="5️⃣ Roles", value="Aktif" if datasete["role_update"] else "Tidak aktif", inline=False,
            )
            embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=True)
            embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
            embed.set_author(name=server_data.name, icon_url=str(server_data.icon_url))
            embed.set_thumbnail(url=str(server_data.icon_url))
            return embed

        first_run = True
        cancelled = False
        emb_msg: discord.Message
        self.logger.info(f"{server_id}: starting data modifying...")
        while True:
            embed = await _generate_embed(metadata_srvlog)
            if first_run:
                first_run = False
                emb_msg = await ctx.send(embed=embed)
            else:
                await emb_msg.edit(embed=embed)

            def base_check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in number_reactions:
                    return False
                return True

            for react in number_reactions:
                await emb_msg.add_reaction(react)

            res, user = await self.bot.wait_for("reaction_add", check=base_check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                cancelled = True
                break
            else:
                index_n = number_reactions.index(str(res.emoji))
                if index_n == 0:
                    metadata_srvlog["edit_msg"] = not metadata_srvlog["edit_msg"]
                    metadata_srvlog["delete_msg"] = not metadata_srvlog["delete_msg"]
                elif index_n == 1:
                    metadata_srvlog["member_join"] = not metadata_srvlog["member_join"]
                    metadata_srvlog["member_leave"] = not metadata_srvlog["member_leave"]
                elif index_n == 2:
                    metadata_srvlog["member_ban"] = not metadata_srvlog["member_ban"]
                    metadata_srvlog["member_unban"] = not metadata_srvlog["member_unban"]
                elif index_n == 3:
                    metadata_srvlog["nick_update"] = not metadata_srvlog["nick_update"]
                elif index_n == 4:
                    metadata_srvlog["role_update"] = not metadata_srvlog["role_update"]
                await emb_msg.clear_reactions()

        if cancelled:
            return await ctx.send("Dibatalkan.")

        await emb_msg.delete()

        self.logger.info(f"{server_id}: saving data...")
        self.serverlog_map[server_id] = metadata_srvlog
        await self.save_local_server_log(server_id)
        await ctx.send("Pencatatan peladen berhasil diatur.")
