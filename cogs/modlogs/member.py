import logging
from datetime import datetime
from typing import Union

import arrow
import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.modlog import ModLog, ModLogAction, ModLogFeature


def rounding(num: int) -> int:
    return int(round(num))


class ModLogMember(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("modlog.MemberLog")

    @staticmethod
    def strftime(dt_time: datetime) -> str:
        to_arrow = arrow.get(dt_time)
        return to_arrow.format("MMMM DD YYYY, HH:mm:ss UTC", "id")

    def _generate_log(self, action: ModLogAction, data: dict) -> ModLog:
        user_data: discord.Member = data["user_data"]
        desc_data = []
        current_time = self.bot.now()
        desc_data.append(f"**• Pengguna**: {user_data.name}#{user_data.discriminator}")
        desc_data.append(f"**• ID Pengguna**: {user_data.id}")
        desc_data.append(f"**• Akun Bot?**: {'Ya' if user_data.bot else 'Tidak'}")
        desc_data.append(f"**• Akun Dibuat**: {self.strftime(user_data.created_at)}")
        desc_data.append(f"**• Terjadi pada**: <t:{rounding(current_time.timestamp())}>")
        author_data = {
            "name": f"{user_data.name}#{user_data.discriminator}",
            "icon_url": str(user_data.avatar),
        }
        modlog = ModLog(action=action, timestamp=current_time.timestamp())
        if action == ModLogAction.MEMBER_JOIN:
            embed = discord.Embed(
                title="📥 Anggota Bergabung", color=0x83D66B, timestamp=current_time.datetime
            )
            embed.description = "\n".join(desc_data)
            embed.set_footer(text="🚪 Bergabung")
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            modlog.embed = embed
        elif action == ModLogAction.MEMBER_LEAVE:
            embed = discord.Embed(title="📥 Anggota Keluar", color=0xD66B6B, timestamp=current_time.datetime)
            embed.description = "\n".join(desc_data)
            embed.set_footer(text="🚪 Keluar")
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            modlog.embed = embed
        elif action == ModLogAction.MEMBER_KICK:
            embed = discord.Embed(
                title="🦶 Anggota ditendang", color=0xD66B6B, timestamp=current_time.datetime
            )
            embed.description = "\n".join(desc_data)
            if data["executor"] is not None:
                embed.add_field(name="Eksekutor", value=data["executor"], inline=False)
            if data["reason"] is not None:
                embed.add_field(name="Alasan", value=f"```\n{data['reason']}\n```", inline=False)
            embed.set_footer(text="🚪🦶 Ditendang")
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            modlog.embed = embed
        elif action == ModLogAction.MEMBER_BAN:
            embed = discord.Embed(
                title="🔨 Anggota terbanned", color=0x8B0E0E, timestamp=current_time.datetime
            )
            ban_data = data["details"]
            embed.description = "\n".join(desc_data)
            if "executor" in ban_data:
                embed.add_field(name="Eksekutor", value=ban_data["executor"])
            embed.add_field(name="Alasan", value=f"```\n{ban_data['reason']}\n```", inline=False)
            embed.set_footer(text="🚪🔨 Banned")
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            modlog.embed = embed
        elif action == ModLogAction.MEMBER_UNBAN:
            embed = discord.Embed(
                title="🔨👼 Anggota diunbanned", color=0x2BCEC2, timestamp=current_time.datetime
            )
            embed.description = "\n".join(desc_data)
            ban_data = data["details"]
            if "forgiver" in ban_data:
                embed.add_field(name="Pemaaf", value=ban_data["forgiver"])
            if "reason" in ban_data and ban_data["reason"]:
                embed.add_field(name="Alasan", value=f"```\n{ban_data['reason']}\n```", inline=False)
            embed.set_footer(text="🚪👼 Unbanned")
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            modlog.embed = embed
        elif action == ModLogAction.MEMBER_UPDATE:
            details = data["details"]
            role_change = "added" in details
            embed = discord.Embed(timestamp=current_time.datetime)
            if role_change:
                embed.title = "🤵 Perubahan Role"
                embed.colour = 0x832D64
                added_role_desc = list(map(lambda role: f"- **{role.name}** `[{role.id}]`", details["added"]))
                removed_role_desc = list(
                    map(lambda role: f"- **{role.name}** `[{role.id}]`", details["removed"])
                )
                if len(added_role_desc) > 0:
                    embed.add_field(name="🆕 Penambahan", value="\n".join(added_role_desc), inline=False)
                if len(removed_role_desc) > 0:
                    embed.add_field(name="❌ Dicabut", value="\n".join(removed_role_desc), inline=False)
                embed.set_footer(text="⚖ Perubahan Roles")
            else:
                old_nick, new_nick = details["old"], details["new"]
                nick_desc = []
                nick_desc.append(f"• Sebelumnya: **{old_nick if old_nick is not None else '*Tidak ada.*'}**")
                nick_desc.append(f"• Sekarang: **{new_nick if new_nick is not None else '*Dihapus.*'}**")
                embed.description = "\n".join(nick_desc)
                embed.set_footer(text="📎 Perubahan Nickname.")
            embed.set_author(**author_data)
            embed.set_thumbnail(url=str(user_data.avatar))
            modlog.embed = embed
        return modlog

    @commands.Cog.listener("on_member_join")
    async def _modlog_member_join(self, member: discord.Member):
        should_log, server_setting = self.bot.should_modlog(member.guild, member, [ModLogFeature.MEMBER_JOIN])
        if not should_log:
            return
        member_name = f"{member.name}#{member.discriminator} ({member.id})"
        self.logger.info(f"{member_name} joined the server, sending to modlogs...")
        modlog_data = self._generate_log(ModLogAction.MEMBER_JOIN, {"user_data": member})
        await self.bot.add_modlog(modlog_data, server_setting)

    @commands.Cog.listener("on_member_remove")
    async def _modlog_member_leave(self, member: discord.Member):
        should_log, server_setting = self.bot.should_modlog(
            member.guild, member, [ModLogFeature.MEMBER_LEAVE]
        )
        if not should_log:
            return
        member_name = f"{member.name}#{member.discriminator} ({member.id})"
        executor = None
        reason = "Tidak ada alasan."
        if self.have_audit_perm(member.guild):
            async for guild_log in member.guild.audit_logs(
                action=discord.AuditLogAction.kick,
            ):
                backward_time = self.bot.now().shift(seconds=-5)
                if backward_time.timestamp() > guild_log.created_at.timestamp():
                    continue
                if guild_log.target.id == member.id:
                    reason = guild_log.reason or "Tidak ada alasan."
                    executor = f"{guild_log.user.mention} ({guild_log.user.id})"
                    break
        if executor is not None:
            self.logger.info(f"{member_name} has been kicked, sending to modlogs...")
            modlog_data = self._generate_log(
                ModLogAction.MEMBER_KICK, {"user_data": member, "executor": executor, "reason": reason}
            )
        else:
            self.logger.info(f"{member_name} leave the server, sending to modlogs...")
            modlog_data = self._generate_log(ModLogAction.MEMBER_LEAVE, {"user_data": member})
        await self.bot.add_modlog(modlog_data, server_setting)

    @commands.Cog.listener("on_member_ban")
    async def _modlog_member_banned(self, guild: discord.Guild, user: Union[discord.User, discord.Member]):
        should_log, server_setting = self.bot.should_modlog(guild, user, [ModLogFeature.MEMBER_BAN])
        if not should_log:
            return
        details_data = {}
        reason = "Tidak ada alasan."
        banned_by = None
        if self.have_audit_perm(guild):
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban):
                backward_time = self.bot.now().shift(seconds=-5)
                if backward_time.timestamp() > entry.created_at.timestamp():
                    continue
                if entry.target.id == user.id:
                    reason = entry.reason or "Tidak ada alasan."
                    banned_by = f"{entry.user.mention} ({entry.user.id})"
                    break
        details_data["reason"] = reason
        if banned_by is not None:
            details_data["executor"] = banned_by

        modlog_data = self._generate_log(
            ModLogAction.MEMBER_BAN, {"user_data": user, "details": details_data}
        )
        self.logger.info(
            f"A user has been banned: {user.name}#{user.discriminator} ({user.id}), sending to modlogs..."
        )
        await self.bot.add_modlog(modlog_data, server_setting)

    def have_audit_perm(self, guild: discord.Guild):
        bot_member: discord.Member = guild.get_member(self.bot.user.id)
        if bot_member.guild_permissions.view_audit_log:
            return True
        return False

    @commands.Cog.listener("on_member_unban")
    async def _member_unban_logging(self, guild: discord.Guild, user: discord.User):
        should_log, server_setting = self.bot.should_modlog(guild, user, [ModLogFeature.MEMBER_UNBAN])
        if not should_log:
            return
        details_data = {}
        if self.have_audit_perm(guild):
            async for entry in guild.audit_logs(action=discord.AuditLogAction.unban):
                backward_time = arrow.utcnow().shift(seconds=-10)
                if backward_time.timestamp() > entry.created_at.timestamp():
                    continue
                if entry.target.id == user.id:
                    details_data = {
                        "forgiver": f"{entry.user.mention} ({entry.user.id})",
                        "reason": entry.reason,
                    }
                    break

        modlog_data = self._generate_log(
            ModLogAction.MEMBER_UNBAN, {"user_data": user, "details": details_data}
        )
        self.logger.info(
            f"A user has been unbanned: {user.name}#{user.discriminator} ({user.id}), sending to modlogs..."
        )
        await self.bot.add_modlog(modlog_data, server_setting)

    @commands.Cog.listener("on_member_update")
    async def _member_update_logging(self, before: discord.Member, after: discord.Member):
        should_log, server_setting = self.bot.should_modlog(
            before.guild, before, [ModLogFeature.MEMBER_UPDATE]
        )
        if not should_log:
            return
        nick_updated = role_updated = False
        nick_detail = {}
        if before.nick != after.nick:
            nick_updated = True
            nick_detail["new"] = after.nick
            nick_detail["old"] = before.nick

        role_before, role_after = before.roles, after.roles
        role_detail = {}
        if len(role_before) != len(role_after):
            role_updated = True
            newly_added = []
            for aft in role_after:
                if aft not in role_before:
                    newly_added.append(aft)
            removed_role = []
            for bef in role_before:
                if bef not in role_after:
                    removed_role.append(bef)
            role_detail["added"] = newly_added
            role_detail["removed"] = removed_role

        if not role_updated and not nick_updated:
            return

        if nick_updated and server_setting.has_features(ModLogFeature.NICK_MEMUPDATE):
            self.logger.info("Nickname is updated, reporting to modlog...")
            generate_log = self._generate_log(
                ModLogAction.MEMBER_UPDATE, {"user_data": after, "details": nick_detail}
            )
            await self.bot.add_modlog(generate_log, server_setting)

        if role_updated and server_setting.has_features(ModLogFeature.ROLE_MEMUPDATE):
            self.logger.info("Role updated, reporting to modlog...")
            generate_log = self._generate_log(
                ModLogAction.MEMBER_UPDATE, {"user_data": after, "details": role_detail}
            )
            await self.bot.add_modlog(generate_log, server_setting)


def setup(bot: naoTimesBot):
    bot.add_cog(ModLogMember(bot))
