import logging
from datetime import datetime

import arrow
import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.modlog import ModLog, ModLogAction, ModLogFeature


class ModLogThreads(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("modlog.ThreadsLog")

    @staticmethod
    def strftime(dt_time: datetime) -> str:
        to_arrow = arrow.get(dt_time)
        return to_arrow.format("MMMM DD YYYY, HH:mm:ss UTC", "id")

    def have_audit_perm(self, guild: disnake.Guild):
        bot_member: disnake.Member = guild.get_member(self.bot.user.id)
        if bot_member.guild_permissions.view_audit_log:
            return True
        return False

    def _generate_log(self, action: ModLogAction, data: dict) -> ModLog:
        current_time = self.bot.now().timestamp()
        mod_log = ModLog(action=action, timestamp=current_time)
        guild_info = data.get("guild", None)

        if action == ModLogAction.THREAD_CREATE:
            embed = disnake.Embed(title="🗞 Thread dibuat", color=disnake.Color.from_rgb(67, 154, 96))
            description = []
            description.append(f"**• Nama**: #{data['name']}")
            description.append(f"**• ID thread**: {data['id']} (<#{data['id']}>)")
            if data["channel"] is not None:
                description.append(f"**• Di kanal**: #{data['channel']}")
            embed.description = "\n".join(description)
            embed.set_footer(text="#️⃣ Thread baru")
            if guild_info is not None:
                if guild_info["icon"] is not None:
                    embed.set_thumbnail(url=guild_info["icon"])
                embed.set_author(name=guild_info["name"], icon_url=guild_info["icon"])
            mod_log.embed = embed
        elif action == ModLogAction.THREAD_REMOVE:
            embed = disnake.Embed(title="🚮 Thread dihapus", color=disnake.Color.from_rgb(176, 45, 45))
            description = []
            description.append(f"**• Nama**: #{data['name']}")
            description.append(f"**• ID thread**: {data['id']} (<#{data['id']}>)")
            if data["channel"] is not None:
                description.append(f"**• Dari kanal**: #{data['channel']}")
            embed.description = "\n".join(description)
            embed.set_footer(text="🚮 Thread dihapus")
            if guild_info is not None:
                if guild_info["icon"] is not None:
                    embed.set_thumbnail(url=guild_info["icon"])
                embed.set_author(name=guild_info["name"], icon_url=guild_info["icon"])
            mod_log.embed = embed
        elif action == ModLogAction.THREAD_UPDATE:
            embed = disnake.Embed(title="💎 Perubahan thread", color=disnake.Color.random())
            if "name" in data:
                name_detail = data["name"]
                name_desc = []
                name_desc.append(f"**• Sebelumnya**: #{name_detail['before']}")
                name_desc.append(f"**• Sekarang**: #{name_detail['after']}")
                embed.add_field(name="🔡 Perubahan Nama", value="\n".join(name_desc), inline=False)
            if "archive" in data:
                arch = data["archive"]
                arch_desc = []
                lock_k = "🔒"
                lock_ka = "*Thread diarchive*"
                if not arch["status"]:
                    lock_ka = "*Thread dibuka kembali*"
                    lock_k = "🔓"
                if "author" in arch:
                    arch_desc.append(f"**• Pelaku**: {arch['author']}")
                arch_desc.append(f"**• Pada**: {self.strftime(arch['timestamp'])}")
                embed.add_field(name=f"{lock_k} {lock_ka}", value="\n".join(arch_desc), inline=False)
            if guild_info is not None:
                if guild_info["icon"] is not None:
                    embed.set_thumbnail(url=guild_info["icon"])
                embed.set_author(name=guild_info["name"], icon_url=guild_info["icon"])
            if data["channel"] is not None:
                embed.description = f"**• Di kanal**: #{data['channel']}"
            mod_log.embed = embed

        return mod_log

    @commands.Cog.listener("on_thread_create")
    async def _modlog_thread_join(self, thread: disnake.Thread):
        should_log, server_setting = self.bot.should_modlog(
            thread.guild, features=[ModLogFeature.THREAD_CREATE]
        )
        if not should_log:
            return

        guild = thread.guild
        parent = thread.parent
        parent_name = None
        if parent is not None:
            parent_name = parent.name
        # if thread.me is not None and thread.me.id == self.bot.user.id:
        #     return

        ikon_guild = guild.icon
        if ikon_guild is not None:
            ikon_guild = str(ikon_guild)

        details = {
            "name": thread.name,
            "id": thread.id,
            "channel": parent_name,
            "guild": {"name": guild.name, "icon": ikon_guild},
        }

        self.logger.info(f"Thread joined/created, {details!r}")
        modlog = self._generate_log(ModLogAction.THREAD_CREATE, details)
        await self.bot.add_modlog(modlog, server_setting)

    @commands.Cog.listener("on_thread_delete")
    async def _modlog_thread_delete(self, thread: disnake.Thread):
        should_log, server_setting = self.bot.should_modlog(
            thread.guild, features=[ModLogFeature.THREAD_DELETE]
        )
        if not should_log:
            return

        guild = thread.guild
        parent = thread.parent
        parent_name = None
        if parent is not None:
            parent_name = parent.name

        ikon_guild = guild.icon
        if ikon_guild is not None:
            ikon_guild = str(ikon_guild)

        details = {
            "name": thread.name,
            "id": thread.id,
            "channel": parent_name,
            "guild": {"name": guild.name, "icon": ikon_guild},
        }

        self.logger.info(f"Thread deleted, {details!r}")
        modlog = self._generate_log(ModLogAction.THREAD_REMOVE, details)
        await self.bot.add_modlog(modlog, server_setting)

    @commands.Cog.listener("on_thread_update")
    async def _modlog_thread_update(self, before: disnake.Thread, after: disnake.Thread):
        should_log, server_setting = self.bot.should_modlog(
            before.guild, features=[ModLogFeature.THREAD_UPDATE]
        )
        if not should_log:
            return

        guild: disnake.Guild = before.guild
        parent = before.parent
        parent_name = None
        if parent is not None:
            parent_name = parent.name
        if parent_name is None and after.parent is not None:
            parent_name = after.parent.name

        details = {}
        name_details = {}
        if before.name != after.name:
            name_details["before"] = before.name
            name_details["after"] = after.name
            details["name"] = name_details
        archive_details = {}
        if before.archived != after.archived:
            archive_details["status"] = after.archived
            if after.archived:
                archiver_id = after.archiver_id
                if archiver_id is None:
                    archive_details["author"] = "*Archive otomatis oleh Discord*"
                else:
                    member_info = guild.get_member(archiver_id)
                    if member_info is None:
                        archive_details["author"] = "*Archive otomatis oleh Discord*"
                    else:
                        archive_details["author"] = f"{str(member_info)} (`{member_info.id}`)"
                archive_details["timestamp"] = after.archive_timestamp
            else:
                archive_details["timestamp"] = self.bot.now()
            details["archive"] = archive_details

        if "name" not in details and "archive" not in details:
            return

        if self.have_audit_perm(guild):
            current_time = self.bot.now().shift(seconds=-30)
            async for guild_log in guild.audit_logs(
                action=disnake.AuditLogAction.thread_update, after=current_time.datetime
            ):
                if guild_log.target.id == after.id:
                    archive_details["author"] = str(guild_log.user)
                    break

        ikon_guild = guild.icon
        if ikon_guild is not None:
            ikon_guild = str(ikon_guild)

        details["guild"] = {"name": guild.name, "icon": ikon_guild}
        details["channel"] = parent_name

        self.logger.info(f"Thread updated, {details!r}")
        modlog = self._generate_log(ModLogAction.THREAD_UPDATE, details)
        await self.bot.add_modlog(modlog, server_setting)


def setup(bot: naoTimesBot):
    bot.add_cog(ModLogThreads(bot))
