from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Generic, List, Literal, NamedTuple, Optional, TypeVar, Union

import arrow
import discord
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.modlog import ModLog, ModLogAction
from naotimes.timeparse import TimeString, TimeStringParseError

ShadowBanList = Dict[str, List[str]]
RoleMute = Dict[str, discord.Role]
T = TypeVar("T")
ManagerT = TypeVar("ManagerT", bound="Union[MuteManagerChild, ShadowbanManagerChild]")


class GuildMuted(NamedTuple):
    id: int
    guild: int
    reason: Optional[str] = None
    timeout: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict):
        user_id = data.get("id")
        guild_id = data.get("guild_id")
        reason = data.get("reason", None)
        timeout = data.get("timeout", None)
        return cls(user_id, guild_id, reason, timeout)

    def __eq__(self, o: object) -> bool:
        if isinstance(o, GuildMuted):
            return self.id == o.id and self.guild == o.guild
        elif isinstance(o, int):
            return self.id == o
        return False

    def serialize(self):
        return {"id": self.id, "guild_id": self.guild, "reason": self.reason, "timeout": self.timeout}


class MuteManagerChild:
    def __init__(self, guild_id: int):
        self._id = guild_id
        self._muted: List[GuildMuted] = []

    def __eq__(self, other: Union[MuteManagerChild, int]):
        if isinstance(other, MuteManagerChild):
            return self._id == other._id
        elif isinstance(other, int):
            return self._id == other
        return False

    def __iter__(self):
        for mute in self._muted:
            yield mute

    def __repr__(self) -> str:
        all_users = []
        for user in self._muted:
            all_users.append(f"{user.id}")
        all_users = ", ".join(all_users)
        the_ids = self._id
        if isinstance(the_ids, str):
            the_ids = f'"{the_ids}"'
        else:
            the_ids = str(the_ids)
        return f"<MuteManagerChild id={the_ids} users=[{all_users}]>"

    def __add__(self, other: GuildMuted):
        if other not in self:
            self._muted.append(other)
        return self

    def __sub__(self, other: Union[int, GuildMuted]):
        if other in self:
            self.remove(other)
            return self
        return self

    def __contains__(self, other: Union[int, GuildMuted]):
        for user in self._muted:
            if user == other:
                return True
        return False

    def add(self, data: Union[dict, GuildMuted]):
        if isinstance(data, dict):
            self._muted.append(GuildMuted.from_dict(data))
        else:
            self._muted.append(data)

    def remove(self, user_id: int):
        index = -1
        for n, user in enumerate(self._muted):
            if user == user_id:
                index = n
                break
        if index >= 0:
            return self._muted.pop(index)
        return None

    def get(self, user_id: Union[GuildMuted, int]):
        for user in self._muted:
            if user == user_id:
                return user
        return None

    def serialize(self):
        return [user.serialize() for user in self._muted]


class ShadowbanManagerChild:
    def __init__(self, guild_id: int) -> None:
        self._id = guild_id
        self._banned: List[int] = []

    def __eq__(self, other: Union[ShadowbanManagerChild, int]):
        if isinstance(other, ShadowbanManagerChild):
            return self._id == other._id
        elif isinstance(other, int):
            return self._id == other
        return False

    def __iter__(self):
        for ban in self._banned:
            yield ban

    def __repr__(self) -> str:
        all_users = []
        for user in self._banned:
            all_users.append(f"{user}")
        all_users = ", ".join(all_users)
        the_ids = self._id
        if isinstance(the_ids, str):
            the_ids = f'"{the_ids}"'
        else:
            the_ids = str(the_ids)
        return f"<MuteManagerChild id={the_ids} users=[{all_users}]>"

    def __add__(self, other: int):
        if isinstance(other, int):
            self.add(other)
        return self

    def __sub__(self, other: int):
        if isinstance(other, int):
            return self.remove(other)
        return None

    def __contains__(self, other: int):
        if isinstance(other, int):
            return other in self._banned
        return False

    def add(self, user_id: int):
        if user_id not in self:
            self._banned.append(user_id)

    def remove(self, user_id: int):
        if user_id in self:
            self._banned.remove(user_id)
            return user_id
        return None

    def get(self, user_id: int):
        for user in self._banned:
            if user == user_id:
                return user
        return None

    def serialize(self):
        return self._banned


MemberManagerContext = Union[MuteManagerChild, ShadowbanManagerChild]


class MemberManager(Generic[ManagerT]):
    def __init__(self, Context: ManagerT):
        self._childs: List[ManagerT] = []
        self._ctx = Context

    def __repr__(self) -> str:
        ctx_name = str(self._ctx)
        return f'<MemberManager ctx="{ctx_name}" child={len(self._childs)}>'

    def __iter__(self):
        for child in self._childs:
            for d in child:
                yield d

    def childs(self):
        for child in self._childs:
            yield child

    def add_child(self, guild_id: Any) -> ManagerT:
        child = self._ctx(guild_id)
        self._childs.append(child)
        return child

    def get_child(self, guild_id: Any) -> ManagerT:
        for child in self._childs:
            if child == guild_id:
                return child
        return self.add_child(guild_id)

    def add_to_child(self, guild_id: int, data: Any) -> None:
        child = self.get_child(guild_id)
        child.add(data)

    def remove_from_child(self, guild_id, data: Any) -> None:
        child = self.get_child(guild_id)
        if data in child:
            return child.remove(data)
        return None

    def get_from_child(self, guild_id, data: Any):
        child = self.get_child(guild_id)
        if data in child:
            return child.get(data)
        return None


class ModToolsMemberControl(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("ModTools.MemberControl")

        self._shadowbanned = MemberManager[ShadowbanManagerChild](ShadowbanManagerChild)
        self._mute_manager = MemberManager[MuteManagerChild](MuteManagerChild)
        # Reuse
        self._timed_ban_manager = MemberManager[MuteManagerChild](MuteManagerChild)
        self._mute_roles: RoleMute = {}

        self._mute_lock = False
        self._timed_ban_lock = False
        self.bot.loop.create_task(self.initialize(), name="modtools-initialize-member")
        self.watch_mute_timeout.start()
        self.watch_ban_timeout.start()

    def cog_unload(self) -> None:
        self.watch_mute_timeout.cancel()
        self.watch_ban_timeout.cancel()

    async def _inject_mute_overwrite(self, role: discord.Role, return_error: bool = False):
        guild: discord.Guild = role.guild
        all_channel: List[discord.abc.GuildChannel] = guild.channels
        for channel in all_channel:
            all_overwrites: List[int] = list(map(lambda x: x.id, channel.overwrites.keys()))
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                force_propagate = False
                if role.id not in all_overwrites:
                    force_propagate = True
                current_overwrite = channel.overwrites_for(role)
                should_overwrite = False
                if current_overwrite.send_messages:
                    should_overwrite = True
                    current_overwrite.send_messages = False
                if current_overwrite.speak:
                    should_overwrite = True
                    current_overwrite.speak = False
                if current_overwrite.send_messages_in_threads:
                    should_overwrite = True
                    current_overwrite.send_messages_in_threads = False
                if force_propagate:
                    current_overwrite.send_messages_in_threads = False
                    current_overwrite.send_messages = False
                    current_overwrite.speak = False
                if should_overwrite or force_propagate:
                    try:
                        self.logger.info(f"Setting overwrite for {str(channel)} on role {str(role)}")
                        await channel.set_permissions(
                            role, overwrite=current_overwrite, reason="Auto set by naoTimes ModTools"
                        )
                    except discord.Forbidden:
                        self.logger.error("Cannot overwrite the role because missing permission sadge")
                        if return_error:
                            return (
                                "Gagal membuat permission override, mohon pastikan Bot dapat "
                                "mengatur permission channel",
                            )
                    except discord.NotFound:
                        self.logger.error("Failed to create overwrite, role is missing for some reason...")
                        if return_error:
                            return "Gagal membuat permission override, role tidak dapat ditemukan"
                    except discord.HTTPException:
                        self.logger.error("An HTTP exception occured while trying to overwrite perms...")
                        if return_error:
                            return "Gagal membuat permission override dikarenakan kesalahan koneksi"
        if return_error:
            return None

    async def initialize(self):
        await self.bot.wait_until_ready()
        self.logger.info("Collecting shadowbanned users...")
        all_shadowbanned = await self.bot.redisdb.getalldict("ntmodtools_shban_*")
        for server_id, server_shadowbanned in all_shadowbanned.items():
            server_id = server_id[17:]
            for uuid in server_shadowbanned:
                self._shadowbanned.add_to_child(int(server_id), uuid)
            self.logger.info(
                f"{server_id}: Collected {len(server_shadowbanned)} currently shadowbanned users"
            )
        self.logger.info("Collecting currently timed banned users...")
        all_timed_banned = await self.bot.redisdb.getalldict("ntmodtools_timedban_*")
        for server_id, server_timed_banned in all_timed_banned.items():
            server_id = server_id[20:]
            for uuid in server_timed_banned:
                self._timed_ban_manager.add_to_child(int(server_id), uuid)
            self.logger.info(
                f"{server_id}: Collected {len(server_timed_banned)} currently timed banned users"
            )
        self.logger.info("Collecting currently muted users...")
        muted_users = await self.bot.redisdb.getalldict("ntmodtools_muted_*")
        for server_id, server_muted_users in muted_users.items():
            server_id = server_id[17:]
            for muted_user in server_muted_users:
                self._mute_manager.add_to_child(int(server_id), muted_user)
            self.logger.info(f"{server_id}: Collected {len(server_muted_users)} currently muted users")
        self.logger.info("Collecting mute roles...")
        mute_roles = await self.bot.redisdb.getalldict("ntmodtools_muterole_*")
        for server_id, server_mute_role in mute_roles.items():
            server_id = server_id[20:]
            try:
                the_guild: discord.Guild = self.bot.get_guild(int(server_id))
                if the_guild is None:
                    self.logger.warning(f"Could not find guild with id {server_id}")
                    continue
            except ValueError:
                self.logger.warning(f"{server_id} is not a guild, skipping")
                continue

            try:
                the_role: discord.Role = the_guild.get_role(int(server_mute_role))
                if the_role is None:
                    self.logger.warning(f"Could not find role with id {server_mute_role}")
                    await self.bot.redisdb.rm(f"ntmodtools_muterole_{server_id}")
                    continue
                else:
                    await self._inject_mute_overwrite(the_role)
                    self.logger.info(f"{the_guild.id}: Adding {the_role.id}")
                    self._mute_roles[server_id] = the_role
            except ValueError:
                self.logger.warning(f"{server_mute_role} is not a role, skipping")
                continue

    def _generate_modlog(self, action: ModLogAction, data: dict):
        current = self.bot.now()
        mod_log = ModLog(action, timestamp=current.timestamp())

        if action == ModLogAction.EVASION_TIMEOUT:
            embed = discord.Embed(
                title="🏃‍♀️ Mute evasion",
                colour=discord.Color.from_rgb(113, 57, 66),
                timestamp=current.datetime,
            )
            user_data: discord.Member = data["member"]
            desc_data = []
            desc_data.append(f"**• Pengguna**: {user_data.name}#{user_data.discriminator}")
            desc_data.append(f"**• ID Pengguna**: {user_data.id}")
            desc_data.append(f"**• Akun Bot?**: {'Ya' if user_data.bot else 'Tidak'}")
            if "delta" in data:
                delta: TimeString = data["delta"]
                desc_data.append(f"**• Sisa Waktu?**: {str(delta)}")
            embed.description = "\n".join(desc_data)
            author_data = {
                "name": f"{user_data.name}#{user_data.discriminator}",
                "icon_url": str(user_data.avatar),
            }
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            embed.set_footer(text="🏃‍♀️ Mute Evasion")
            mod_log.embed = embed
        elif action == ModLogAction.MEMBER_TIMEOUT:
            embed = discord.Embed(title="🔇 User dimute", colour=discord.Color.from_rgb(163, 82, 94))
            user_data: discord.Member = data["member"]
            executor: discord.Member = data["executor"]
            desc_data = []
            desc_data.append(f"**• Pengguna**: {user_data.name}#{user_data.discriminator}")
            desc_data.append(f"**• ID Pengguna**: {user_data.id}")
            desc_data.append(f"**• Akun Bot?**: {'Ya' if user_data.bot else 'Tidak'}")
            if "durasi" in data:
                desc_data.append(f"**• Durasi**: {data['durasi']}")
            embed.add_field(name="🧑 Moderator", value=f"{str(executor)} [{executor.id}]")
            embed.description = "\n".join(desc_data)
            author_data = {
                "name": f"{user_data.name}#{user_data.discriminator}",
                "icon_url": str(user_data.avatar),
            }
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            embed.set_footer(text="🔇 Muted")
            mod_log.embed = embed
        elif action == ModLogAction.MEMBER_UNTIMEOUT:
            embed = discord.Embed(title="🔊 User diunmute", colour=discord.Color.from_rgb(56, 112, 173))
            user_data: discord.Member = data["member"]
            executor: discord.Member = data["executor"]
            desc_data = []
            desc_data.append(f"**• Pengguna**: {user_data.name}#{user_data.discriminator}")
            desc_data.append(f"**• ID Pengguna**: {user_data.id}")
            desc_data.append(f"**• Akun Bot?**: {'Ya' if user_data.bot else 'Tidak'}")
            embed.description = "\n".join(desc_data)
            if isinstance(executor, str):
                embed.add_field(name="🧑 Moderator", value=executor)
            else:
                embed.add_field(name="🧑 Moderator", value=f"{str(executor)} [{executor.id}]")
            author_data = {
                "name": f"{user_data.name}#{user_data.discriminator}",
                "icon_url": str(user_data.avatar),
            }
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            embed.set_footer(text="🔊 Unmuted")
            mod_log.embed = embed
        elif action == ModLogAction.MEMBER_TIMED_BAN:
            embed = discord.Embed(title="🔨⏱️ Timed ban", colour=0x8B0E0E, timestamp=current.datetime)
            user_data: discord.Member = data["member"]
            executor: discord.Member = data["executor"]
            reason: str = data["reason"]
            durasi: str = data["durasi"]
            desc_data = []
            join_arrow = arrow.get(user_data.created_at)
            join_strf = join_arrow.format("MMMM DD YYYY, HH:mm:ss UTC", "id")
            desc_data.append(f"**• Pengguna**: {user_data.name}#{user_data.discriminator}")
            desc_data.append(f"**• ID Pengguna**: {user_data.id}")
            desc_data.append(f"**• Akun Bot?**: {'Ya' if user_data.bot else 'Tidak'}")
            desc_data.append(f"**• Akun Dibuat**: {join_strf}")
            desc_data.append(f"**• Terjadi pada**: <t:{current.int_timestamp}>")
            desc_data.append(f"**• Durasi**: {durasi}")
            embed.description = "\n".join(desc_data)
            embed.add_field(name="🧑 Moderator", value=f"<@{executor.id}> [{executor.id}]")
            embed.add_field(name="📝 Alasan", value=f"```\n{reason}\n```")
            author_data = {
                "name": f"{user_data.name}#{user_data.discriminator}",
                "icon_url": str(user_data.avatar),
            }
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            embed.set_footer(text="🔨⏱️ Banned")
            mod_log.embed = embed
        elif action == ModLogAction.MEMBER_UNBAN_TIMED:
            embed = discord.Embed(title="👼⏱️ Timed ban (Unban)", colour=0x2BCEC2, timestamp=current.datetime)
            uuid = data["id"]
            desc_data = []
            desc_data.append(f"**• ID Pengguna**: {uuid}")
            desc_data.append(f"**• Terjadi pada**: <t:{current.int_timestamp}>")
            embed.description = "\n".join(desc_data)
            embed.set_author(name=str(self.bot.user), icon_url=self.bot.user.avatar)
            embed.set_footer(text="👼⏱️ Unbanned")
            mod_log.embed = embed

        return mod_log

    async def _dispatch_shadowban_check(self, member: discord.Member):
        if self._shadowbanned.get_from_child(member.guild.id, member.id):
            self.logger.info(f"{member} is shadowbanned, banning for real")
            try:
                await member.ban(delete_message_days=0, reason="Shadowbanned by naoTimes ModTools")
            except discord.Forbidden:
                pass
            self.logger.info(f"{member}: removing from shadowbanned list")
            self._shadowbanned.remove_from_child(member.guild.id, member.id)
            await self.bot.redisdb.set(
                f"ntmodtools_shban_{member.guild.id}",
                self._shadowbanned.get_child(member.guild.id).serialize(),
            )

    async def _dispatch_mute_evasion_check(self, member: discord.Member):
        muted_member: Optional[GuildMuted] = self._mute_manager.get_from_child(member.guild.id, member.id)
        mute_roles = self._mute_roles.get(str(member.guild.id))
        if muted_member is not None and mute_roles is not None:
            self.logger.info(f"{member} is in muted list!")
            timeout = muted_member.timeout
            if timeout is None:
                self.logger.info(f"{member} is muted indefinitely, this person is evasion, remuting...")
                try:
                    await member.add_roles(mute_roles, reason="Mute evasion by leaving server")
                except discord.Forbidden:
                    pass
                modlog_setting = self.bot.get_modlog(member.guild.id)
                if modlog_setting is not None:
                    mod_log = self._generate_modlog(ModLogAction.EVASION_TIMEOUT, {"member": member})
                    await self.bot.add_modlog(mod_log, modlog_setting)
            else:
                self.logger.info(f"{member} is in mute list, checking timeout...")
                current_ts = self.bot.now().timestamp()
                if timeout > current_ts:
                    self.logger.info(f"{member} is still muted, remuting...")
                    mute_left = TimeString.from_seconds(timeout - current_ts)
                    try:
                        await member.add_roles(
                            mute_roles, reason=f"Mute evasion by leaving server, have {str(mute_left)} left"
                        )
                    except discord.Forbidden:
                        pass
                    modlog_setting = self.bot.get_modlog(member.guild.id)
                    if modlog_setting is not None:
                        mod_log = self._generate_modlog(
                            ModLogAction.EVASION_TIMEOUT, {"member": member, "delta": mute_left}
                        )
                        await self.bot.add_modlog(mod_log, modlog_setting)
                else:
                    self.logger.info(f"{member}: is already been unmuted, removing from list...")
                    self._mute_manager.remove_from_child(member.guild.id, member.id)
                    await self.bot.redisdb.set(
                        f"ntmodtools_muted_{member.guild.id}",
                        self._mute_manager.get_child(member.guild.id).serialize(),
                    )

    @commands.Cog.listener("on_member_join")
    async def _modtools_member_evasion_check(self, member: discord.Member):
        # Check for shadowban
        ctime = self.bot.now().int_timestamp
        self.bot.loop.create_task(
            self._dispatch_shadowban_check(member), name=f"mem-join-shadowban-{member.id}_{ctime}"
        )
        self.bot.loop.create_task(
            self._dispatch_mute_evasion_check(member), name=f"mem-join-mute-evasion-{member.id}_{ctime}"
        )

    @commands.Cog.listener("on_member_unban")
    async def _modtools_member_unban_timed_check(self, guild: discord.Guild, user: discord.User):
        manager = self._timed_ban_manager.get_from_child(guild.id, user.id)
        if manager is not None:
            self.logger.info(f"{user} got unbanned and is in timed ban list, removing it...")
            self._timed_ban_manager.remove_from_child(guild.id, user.id)
            await self.bot.redisdb.set(
                f"ntmodtools_timedban_{guild.id}",
                self._timed_ban_manager.get_child(guild.id).serialize(),
            )

    async def _dispatch_mute_timeout(self, member: discord.Member):
        try:
            guild = member.guild
            mute_role = self._mute_roles.get(str(guild.id), self._mute_roles.get(guild.id, None))
            if mute_role is None:
                self.logger.warning("Mute role is gone???")
                return
            try:
                await member.remove_roles(mute_role, reason="Mute timeout")
                self.logger.info(f"User {member} at guild {guild!r} is now unmuted.")
                modlog_set = self.bot.get_modlog(guild.id)
                if modlog_set is not None:
                    modlog_data = {"member": member, "executor": "Unmute otomatis oleh Bot"}
                    mod_log = self._generate_modlog(ModLogAction.MEMBER_UNTIMEOUT, modlog_data)
                    await self.bot.add_modlog(mod_log, modlog_set)
            except discord.Forbidden:
                self.logger.warning(
                    f"Failed to remove role for {member} at {guild!r} because of missing permissions."
                )
            except discord.HTTPException:
                self.logger.error(f"An HTTP exception occured while trying to unmute {member} at {guild!r}!")
        except asyncio.CancelledError:
            self.logger.error(f"Task got cancelled, failed to unmute {member} at guild {member.guild}")

    @tasks.loop(seconds=1)
    async def watch_mute_timeout(self):
        await self.bot.wait_until_ready()
        if self._mute_lock:
            return
        self._mute_lock = True
        try:
            current_ts = self.bot.now().timestamp()
            to_be_removed: List[GuildMuted] = []
            for muted in self._mute_manager:
                if muted.timeout is None:
                    # Forever muted, sadge
                    continue
                if current_ts > muted.timeout:
                    self.logger.info(f"Trying to dispatch unmute event for {muted}")
                    guild = self.bot.get_guild(muted.guild)
                    if guild is None:
                        # Guild is gone, remove from DB
                        self.logger.warning(f"Guild {muted.guild} is gone, removing from list")
                        to_be_removed.append(muted)
                        continue
                    member = guild.get_member(muted.id)
                    if member is None:
                        # Member is gone, wait later.
                        self.logger.warning(f"Member {muted.id} is gone, removing from list")
                        continue
                    self.bot.loop.create_task(
                        self._dispatch_mute_timeout(member), name=f"ntmute-timeoutv2-{muted.id}-{current_ts}"
                    )
                    to_be_removed.append(muted)
            guild_update = []
            for remove in to_be_removed:
                self._mute_manager.remove_from_child(remove.guild, remove.id)
                if remove.guild not in guild_update:
                    guild_update.append(remove.guild)
            for update in guild_update:
                await self.bot.redisdb.set(
                    f"ntmodtools_muted_{update}", self._mute_manager.get_child(update).serialize()
                )
        except Exception:
            pass
        self._mute_lock = False

    async def _dispatch_timedban_unban(self, guild: discord.Guild, user: int):
        try:
            self.logger.info(f"Trying to unban {user} from {guild}")
            await guild.unban(discord.Object(user), reason="Timed ban expired")
            self.logger.info(f"Unbanned {user} from {guild}")
            modlog_setting = self.bot.get_modlog(guild.id)
            if modlog_setting is not None:
                mod_log = self._generate_modlog(ModLogAction.MEMBER_UNBAN_TIMED, {"id": user})
                await self.bot.add_modlog(mod_log, modlog_setting)
        except discord.Forbidden:
            self.logger.warning(f"Failed to unban {user} from {guild}")
        except discord.HTTPException:
            self.logger.error(f"An HTTP exception occured while trying to unban {user} from {guild}!")

    @tasks.loop(seconds=1)
    async def watch_ban_timeout(self):
        await self.bot.wait_until_ready()
        if self._timed_ban_lock:
            return
        self._timed_ban_lock = True
        try:
            current_ts = self.bot.now().timestamp()
            to_be_removed: List[GuildMuted] = []
            for ban in self._timed_ban_manager:
                if current_ts > ban.timeout:
                    self.logger.info(f"Trying to dispatch timed unban event for {ban}")
                    guild = self.bot.get_guild(ban.guild)
                    if guild is None:
                        # Guild is gone, remove from DB
                        self.logger.warning(f"Guild {ban.guild} is gone, removing from list")
                        to_be_removed.append(ban)
                        continue
                    self.bot.loop.create_task(
                        self._dispatch_timedban_unban(guild, ban.id),
                    )
                    to_be_removed.append(ban)
            guild_update = []
            for remove in to_be_removed:
                self._timed_ban_manager.remove_from_child(remove.guild, remove.id)
                if remove.guild not in guild_update:
                    guild_update.append(remove.guild)
            for update in guild_update:
                await self.bot.redisdb.set(
                    f"ntmodtools_timedban_{update}", self._timed_ban_manager.get_child(update).serialize()
                )
        except Exception:
            pass
        self._timed_ban_lock = False

    async def _internal_shadowban(self, guild_id: int, user_id: int, action: Literal["BAN", "UNBAN"] = "BAN"):
        action = action.upper()
        if action == "BAN":
            if not self._shadowbanned.get_from_child(guild_id, int(user_id)):
                self._shadowbanned.add_to_child(guild_id, int(user_id))
                await self.bot.redisdb.set(
                    f"ntmodtools_shban_{guild_id}", self._shadowbanned.get_child(guild_id).serialize()
                )
                return True
        elif action == "UNBAN":
            if self._shadowbanned.get_from_child(guild_id, int(user_id)):
                self._shadowbanned.remove_from_child(guild_id, int(user_id))
                await self.bot.redisdb.set(
                    f"ntmodtools_shban_{guild_id}", self._shadowbanned.get_child(guild_id).serialize()
                )
                return True
        return False

    @commands.command(name="shadowban")
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def _modtools_shadowban(self, ctx: naoTimesContext, user_id: int):
        success_log = await self._internal_shadowban(ctx.guild.id, user_id)
        msg = f"🔨 Palu dilayangkan untuk user ID: `{user_id}`\n"
        msg += "Jika user tersebut masuk ke peladen ini, user tersebut akan otomatis di ban!"
        await ctx.send(msg)
        if success_log and self.bot.has_modlog(ctx.guild.id):
            current_time = self.bot.now()
            modlog = ModLog(ModLogAction.MEMBER_SHADOWBAN, timestamp=current_time.timestamp())
            embed = discord.Embed(title="🔨 Shadowbanned", timestamp=current_time.datetime)
            embed.set_author(name=str(self.bot.user), icon_url=self.bot.user.avatar)
            description = f"**• User ID**: {user_id}\n"
            description += f"**• Pada**: <t:{int(round((current_time.timestamp())))}:F>\n"
            description += f"**• Tukang palu**: {ctx.author.mention} ({ctx.author.id})"
            embed.description = description
            embed.set_footer(text="🔨🕶 Shadowbanned")
            modlog.embed = embed
            await self.bot.add_modlog(modlog, self.bot.get_modlog(ctx.guild.id))

    @commands.command(name="unshadowban")
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def _modtools_unshadowban(self, ctx: naoTimesContext, user_id: int):
        success_log = await self._internal_shadowban(ctx.guild.id, user_id, action="UNBAN")
        msg = f"🛡 Palu ban diambil kembali untuk user ID: `{user_id}`\n"
        msg += "Jika user tersebut masuk ke peladen ini, user tersebut tidak akan di ban otomatis."
        await ctx.send(msg)
        if success_log and self.bot.has_modlog(ctx.guild.id):
            current_time = self.bot.now()
            modlog = ModLog(ModLogAction.MEMBER_UNSHADOWBAN, timestamp=current_time.timestamp())
            embed = discord.Embed(title="🛡🔨 Unshadowban", timestamp=current_time.datetime)
            embed.set_author(name=str(self.bot.user), icon_url=self.bot.user.avatar)
            description = f"**• User ID**: {user_id}\n"
            description += f"**• Pada**: <t:{int(round((current_time.timestamp())))}:F>\n"
            description += f"**• Pemaaf**: {ctx.author.mention} ({ctx.author.id})"
            embed.description = description
            embed.set_footer(text="🛡🔨🕶 Unshadowban")
            modlog.embed = embed
            await self.bot.add_modlog(modlog, self.bot.get_modlog(ctx.guild.id))

    def _check_if_muted(self, guild_id: int, user_id: int):
        if self._mute_manager.get_from_child(guild_id, user_id) is None:
            return False
        return True

    async def _get_mute_role(self, guild_id: int):
        if str(guild_id) in self._mute_roles:
            return self._mute_roles[str(guild_id)], None

        # Create role for muted person
        self.logger.info("Role is missing for this guild, creating a new one...")
        perms = discord.Permissions.none()
        # perms.view_channel = True
        perms.read_message_history = True
        perms.add_reactions = True
        perms.use_external_emojis = True
        # perms.connect = True
        perms.send_messages = False
        perms.send_messages_in_threads = False
        perms.speak = False
        guild_info: discord.Guild = self.bot.get_guild(guild_id)
        try:
            mute_roles = await guild_info.create_role(
                name="Muted by naoTimes",
                permissions=perms,
                hoist=False,
                mentionable=False,
                reason="Auto generated by naoTimes ModTools",
            )
        except discord.Forbidden:
            return None, "Gagal membuat role, mohon pastikan Bot dapat membuat Role baru!"

        self._mute_roles[str(guild_id)] = mute_roles
        await self.bot.redisdb.set(f"ntmodtools_muterole_{guild_id}", mute_roles.id)

        overwrite_err = await self._inject_mute_overwrite(mute_roles, True)
        if overwrite_err is not None:
            return None, overwrite_err

        return mute_roles, None

    @commands.command(name="mute")
    @commands.has_guild_permissions(manage_channels=True, manage_messages=True)
    @commands.guild_only()
    async def _modtools_mute(
        self, ctx: naoTimesContext, member: commands.MemberConverter, *, full_reasoning: str = None
    ):
        guild_id = ctx.guild.id
        if not isinstance(member, discord.Member):
            return await ctx.send("⁉ User yang anda pilih bukanlah member server ini!")

        if member.guild.id != ctx.guild.id:
            return await ctx.send("⁉ User yang anda pilih bukanlah member server ini!")

        if member.bot:
            return await ctx.send("🤖 Member tersebut adalah bot! Jadi tidak bisa di mute!")

        bot_member: discord.Member = ctx.guild.get_member(self.bot.user.id)
        if not bot_member:
            return await ctx.send(
                "⁉ Entah mengapa Bot tidak dapat mengambil User bot di peladen yang dimaksud...?"
            )
        if not bot_member.guild_permissions.manage_roles:
            return await ctx.send(
                "⚠ Bot tidak memiliki akses `Manage roles`, mohon berikan bot "
                "permission ini agar dapat menggunakan fitur ini"
            )

        already_muted = self._check_if_muted(guild_id, member.id)
        if already_muted:
            return await ctx.send("❓ User sudah dimute!")

        if not isinstance(full_reasoning, str):
            full_reasoning = "Muted by bot"

        split_reason = full_reasoning.split(" ", 1)
        timeout = None
        reason = full_reasoning
        if len(split_reason) > 1:
            try:
                timeout = TimeString.parse(split_reason[0])
                reason = split_reason[1]
            except TimeStringParseError:
                self.logger.error("Failed to parse time, ignoring...")
        elif len(split_reason) == 1:
            try:
                timeout = TimeString.parse(split_reason[0])
                reason = f"Muted by bot for {str(timeout)}"
            except TimeStringParseError:
                self.logger.error("Failed to parse time, ignoring...")

        target_top_role: discord.Role = member.top_role
        my_top_role: discord.Role = ctx.author.top_role

        if target_top_role > my_top_role:
            return await ctx.send("🤵 User tersebut memiliki tahkta yang lebih tinggi daripada anda!")

        timed_mute = {
            "id": member.id,
            "guild_id": guild_id,
            "reason": reason,
        }
        if timeout is not None:
            max_time = self.bot.now().timestamp() + timeout.timestamp() + 5
            timed_mute["timeout"] = max_time

        mute_role, mute_err = await self._get_mute_role(guild_id)
        if mute_role is None:
            return await ctx.send(mute_err)

        muted_data = GuildMuted.from_dict(timed_mute)
        try:
            self.logger.info(f"Muting {str(member)} for {str(timeout)}")
            await member.add_roles(mute_role, reason=reason)
            self.logger.info(f"Successfully muted {str(member)}")
        except discord.Forbidden:
            self.logger.error("Bot doesn't have the access to mute that member")
            return await ctx.send("❌ Bot tidak dapat ngemute member tersebut!")
        except discord.HTTPException:
            return await ctx.send("❌ User gagal dimute, mohon cek bot-log!")
        self._mute_manager.add_to_child(guild_id, muted_data)
        await self.bot.redisdb.set(
            f"ntmodtools_muted_{guild_id}", self._mute_manager.get_child(guild_id).serialize()
        )
        await ctx.send("🔇 User berhasil dimute!")
        modlog_set = self.bot.get_modlog(ctx.guild.id)
        if modlog_set is not None:
            modlog_data = {"member": member, "executor": ctx.author}
            if timeout is not None:
                modlog_data["durasi"] = timeout.to_string()
            mod_log = self._generate_modlog(ModLogAction.MEMBER_TIMEOUT, modlog_data)
            await self.bot.add_modlog(mod_log, modlog_set)

    @commands.command(name="unmute")
    @commands.has_guild_permissions(manage_channels=True, manage_messages=True)
    @commands.guild_only()
    async def _modtools_unmute(self, ctx: naoTimesContext, member: commands.MemberConverter):
        guild_id = ctx.guild.id
        if not isinstance(member, discord.Member):
            return await ctx.send("⁉ User yang anda pilih bukanlah member server ini!")

        if member.guild.id != ctx.guild.id:
            return await ctx.send("⁉ User yang anda pilih bukanlah member server ini!")

        muted_member: Optional[GuildMuted] = self._mute_manager.get_from_child(guild_id, member.id)
        if muted_member is None:
            return await ctx.send("❓ User belum dimute")

        mute_role = self._mute_roles.get(str(guild_id))
        if mute_role is None:
            return await ctx.send("⁉ Role yang dipakai untuk mute tidak dapat ditemukan?")

        has_role = member.get_role(mute_role.id)
        if has_role is None:
            return await ctx.send("User tersebut tidak memiliki role mute")

        try:
            await member.remove_roles(mute_role, reason=f"Manual unmute by {str(ctx.author)}")
        except discord.Forbidden:
            self.logger.error(f"Failed to unmute {str(member)}, missing permission")
            return await ctx.send("❌ Gagal unmute user tersebut, bot tidak memliki role `Manage Role`")
        except discord.HTTPException:
            self.logger.error(f"Failed to unmute {str(member)}, HTTP error")
            return await ctx.send("❌ Gagal unmute user tersebut, mohon coba sesaat lagi!")
        self._mute_manager.remove_from_child(guild_id, member.id)
        await self.bot.redisdb.set(
            f"ntmodtools_muted_{guild_id}", self._mute_manager.get_child(guild_id).serialize()
        )
        await ctx.send("🔊 User berhasil di-unmute!")
        modlog_set = self.bot.get_modlog(ctx.guild.id)
        if modlog_set is not None:
            modlog_data = {"member": member, "executor": ctx.author}
            mod_log = self._generate_modlog(ModLogAction.MEMBER_UNTIMEOUT, modlog_data)
            await self.bot.add_modlog(mod_log, modlog_set)

    @commands.command(name="timedban", aliases=["softban", "timeban"])
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def _modtools_timedban(
        self, ctx: naoTimesContext, member: commands.MemberConverter, *, full_reasoning: str
    ):
        guild_id = ctx.guild.id
        if not isinstance(member, discord.Member):
            return await ctx.send("⁉ User yang anda pilih bukanlah member server ini!")

        if member.guild.id != ctx.guild.id:
            return await ctx.send("⁉ User yang anda pilih bukanlah member server ini!")

        if member.bot:
            return await ctx.send("🤖 Member tersebut adalah bot! Jadi tidak bisa di mute!")

        if not isinstance(full_reasoning, str):
            return await ctx.send("⏱️ Mohon berikan durasi ban!")

        split_reason = full_reasoning.split(" ", 1)
        timeout = None
        reason = full_reasoning
        if len(split_reason) > 1:
            try:
                timeout = TimeString.parse(split_reason[0])
                reason = split_reason[1]
            except TimeStringParseError:
                self.logger.error("Failed to parse time, ignoring...")
        elif len(split_reason) == 1:
            try:
                timeout = TimeString.parse(split_reason[0])
                reason = f"Timed ban by bot for {str(timeout)}"
            except TimeStringParseError:
                self.logger.error("Failed to parse time, ignoring...")

        if timeout is None:
            return await ctx.send("⏱️ Mohon berikan durasi ban!")

        target_top_role: discord.Role = member.top_role
        my_top_role: discord.Role = ctx.author.top_role

        if target_top_role > my_top_role:
            return await ctx.send("🤵 User tersebut memiliki tahkta yang lebih tinggi daripada anda!")
        if member.guild_permissions.administrator:
            return await ctx.send("🤵 User tersebut adalah Admin!")

        member_timedban = {
            "id": member.id,
            "guild_id": guild_id,
            "reason": reason,
        }
        if timeout is not None:
            max_time = self.bot.now().timestamp() + timeout.timestamp() + 5
            member_timedban["timeout"] = max_time

        ban_data = GuildMuted.from_dict(member_timedban)
        try:
            self.logger.info(f"Timing ban {str(member)} for {str(timeout)}")
            await member.ban(reason=reason)
            self.logger.info(f"Successfully timed ban {str(member)}")
        except discord.Forbidden:
            self.logger.error(f"Failed to timed ban {str(member)}, missing permission")
            return await ctx.send("❌ Gagal timed ban user tersebut, bot tidak memliki role `Ban Members`")
        except discord.HTTPException:
            self.logger.error(f"Failed to timed ban {str(member)}, HTTP error")
            return await ctx.send("❌ Gagal timed ban user tersebut, mohon coba sesaat lagi!")
        self._timed_ban_manager.add_to_child(guild_id, ban_data)
        await self.bot.redisdb.set(
            f"ntmodtools_timedban_{guild_id}", self._timed_ban_manager.get_child(guild_id).serialize()
        )
        await ctx.send(f"🔨 User berhasil di ban untuk {str(timeout)}")
        modlog_setting = self.bot.get_modlog(ctx.guild.id)
        if modlog_setting is not None:
            modlog_data = {
                "member": member,
                "executor": ctx.author,
                "reason": reason,
                "durasi": timeout.to_string(),
            }
            mod_log = self._generate_modlog(ModLogAction.MEMBER_TIMED_BAN, modlog_data)
            await self.bot.add_modlog(mod_log, modlog_setting)


async def setup(bot: naoTimesBot):
    await bot.add_cog(ModToolsMemberControl(bot))
