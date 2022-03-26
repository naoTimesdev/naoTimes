import logging
from typing import List, Union

import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.modlog import ModLog, ModLogAction, ModLogFeature, ModLogSetting


class ModLogMessage(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("modlog.MessageLog")

    async def _upload_or_not(self, content: str, force_upload: bool = False):
        if not isinstance(content, str):
            return "", False
        if len(content) > 1995 or force_upload:
            url, _ = await self.bot.send_ihateanime(content, "ModLog_", "15")
            return url, True
        return content, False

    @staticmethod
    def truncate(msg: str, limit: int) -> str:
        if len(msg) <= limit:
            return msg
        msg = msg[: limit - 8] + " [...]"
        return msg

    def _generate_log(self, action: ModLogAction, data: dict) -> ModLog:
        current = self.bot.now()
        mod_log = ModLog(action=action, timestamp=current.timestamp())
        if action == ModLogAction.MESSAGE_DELETE:
            channel_info = data["channel"]
            uinfo = data["author"]
            embed = disnake.Embed(title="🚮 Pesan dihapus", color=0xD66B6B, timestamp=current.datetime)
            embed.description = data["content"]
            embed.set_author(name=f"{uinfo['name']}", icon_url=uinfo["avatar"])
            embed.set_footer(text=f"❌ Kanal #{channel_info['name']}")
            if "executor" in data:
                exegs = data["executor"]
                embed.add_field(name="Pembersih", value=f"<@{exegs['id']}> ({exegs['id']})", inline=False)
            if "thumbnail" in data:
                embed.set_image(url=data["thumbnail"])
            if "attachments" in data:
                attachments = data["attachments"]
                embed.add_field(name="Attachments", value=attachments, inline=False)
            mod_log.embed = embed
        elif action == ModLogAction.MESSAGE_DELETE_BULK:
            embed = disnake.Embed(
                title=f"🚮 {data['count']} Pesan dihapus",
                color=disnake.Color.from_rgb(199, 46, 69),
                timestamp=current.datetime,
            )
            channel_info = data["channel"]
            server_info = data["guild"]
            new_desc = "*Semua pesan yang dihapus telah diunggah ke link berikut:*\n"
            new_desc += data["url"] + "\n\n*Link valid selama kurang lebih 2.5 bulan*"
            embed.description = new_desc
            if "executor" in data:
                exegs = data["executor"]
                embed.add_field(name="Pembersih", value=f"<@{exegs['id']}> ({exegs['id']})", inline=False)
            embed.set_author(name=f"#{channel_info['name']}", icon_url=server_info["icon"])
            embed.set_footer(text=f"❌ Kanal #{channel_info['name']}")
            mod_log.embed = embed
        elif action == ModLogAction.MESSAGE_EDIT:
            user_data = data["author"]
            kanal_name = data["channel"]["name"]
            before, after = data["before"], data["after"]
            embed = disnake.Embed(title="📝 Pesan diubah", color=0xE7DC8C, timestamp=current.datetime)
            embed.add_field(name="Sebelum", value=self.truncate(before, 1024), inline=False)
            embed.add_field(name="Sesudah", value=self.truncate(after, 1024), inline=False)
            embed.set_footer(text=f"📝 Kanal #{kanal_name}")
            if "thumbnail" in data:
                embed.set_image(url=data["thumbnail"])
            embed.set_author(name=user_data["name"], icon_url=user_data["avatar"])
            mod_log.embed = embed
        return mod_log

    @commands.Cog.listener("on_message_edit")
    async def _modlog_message_edit(self, before: disnake.Message, after: disnake.Message):
        should_log, server_setting = self.bot.should_modlog(
            before.guild, before.author, [ModLogFeature.EDIT_MSG]
        )
        if not should_log:
            return

        if before.content == after.content:
            return

        details = {
            "author": {
                "id": before.author.id,
                "name": before.author.name,
                "avatar": str(before.author.avatar),
            },
            "channel": {"id": before.channel.id, "name": before.channel.name},
            "before": before.content,
            "after": after.content,
        }
        if len(before.attachments) > 0:
            img_attach = None
            for att in before.attachments:
                if att.content_type.startswith("image/"):
                    img_attach = att
                    break
            if img_attach is not None:
                details["thumbnail"] = img_attach
        if "thumbnail" not in details and len(after.attachments) > 0:
            img_attach = None
            for att in after.attachments:
                if att.content_type.startswith("image/"):
                    img_attach = att
                    break
            if img_attach is not None:
                details["thumbnail"] = img_attach

        self.logger.info(f"{before.guild.id}: Message edited on #{before.channel.name}, sending to modlog...")
        mod_log = self._generate_log(ModLogAction.MESSAGE_EDIT, details)
        await self.bot.add_modlog(mod_log, server_setting)

    def have_audit_perm(self, guild: disnake.Guild):
        bot_member: disnake.Member = guild.get_member(self.bot.user.id)
        if bot_member.guild_permissions.view_audit_log:
            return True
        return False

    @commands.Cog.listener("on_message_delete")
    async def _modlog_message_delete(self, message: disnake.Message):
        should_log, server_setting = self.bot.should_modlog(
            message.guild, message.author, [ModLogFeature.DELETE_MSG]
        )
        if not should_log:
            return

        can_audit = self.have_audit_perm(message.guild)
        if not can_audit:
            # Dont try to log if we don't have the audit permission
            return

        if message.is_system():
            # Dont try to log system messages
            return

        guild: disnake.Guild = message.guild
        initiator: Union[disnake.Member, disnake.User] = None
        async for guild_log in guild.audit_logs(action=disnake.AuditLogAction.message_delete):
            backward_time = self.bot.now().shift(seconds=-10)
            if backward_time.timestamp() > guild_log.created_at.timestamp():
                continue
            if guild_log.target.id == message.author.id:
                initiator = guild_log.user
                break

        if initiator is not None and initiator.bot:
            # Dont log if message got deleted by bot.
            return

        real_content, use_iha = await self._upload_or_not(message.content)
        if use_iha:
            mod_content = "*Dikarenakan teks terlalu panjang, isinya telah diunggah ke link berikut:* "
            mod_content += real_content + "\n"
            mod_content += "Link valid kurang lebih untuk 2.5 bulan!"
            real_content = mod_content

        if not real_content:
            real_content = "*Tidak ada konten*"

        details = {
            "channel": {"id": message.channel.id, "name": message.channel.name},
            "author": {
                "id": message.author.id,
                "name": str(message.author),
                "avatar": str(message.author.avatar),
            },
            "content": real_content,
        }
        if len(message.attachments) > 0:
            img_attach = None
            for att in message.attachments:
                if att.content_type.startswith("image/"):
                    img_attach = att
                    break
            all_attachment = []
            if img_attach is not None:
                details["thumbnail"] = img_attach
            for xxy, attach in enumerate(message.attachments, 1):
                all_attachment.append(f"**#{xxy}.** {attach.filename}")
            details["attachments"] = "\n".join(all_attachment)
        if initiator is not None:
            details["executor"] = {
                "id": initiator.id,
                "name": str(initiator),
            }

        self.logger.info(f"Message deleted from: {message.author}, sending to modlog...")
        log_gen = self._generate_log(ModLogAction.MESSAGE_DELETE, details)
        await self.bot.add_modlog(log_gen, server_setting)

    @commands.Cog.listener("on_bulk_message_delete")
    async def _log_bulk_message_delete(self, messages: List[disnake.Message]):
        server_setting: ModLogSetting = None
        valid_messages: List[disnake.Message] = []
        for message in messages:
            should_log, server_setting = self.bot.should_modlog(
                message.guild, message.author, [ModLogFeature.DELETE_MSG]
            )
            if not should_log:
                return
            if message.is_system():
                # Skip system message
                continue
            valid_messages.append(message)

        if len(valid_messages) < 1:
            # Dont log if message empty
            return

        guild: disnake.Guild = valid_messages[0].guild
        can_audit = self.have_audit_perm(guild)
        if not can_audit:
            # Dont try to log if we don't have the audit permission
            return

        executor = {}
        async for audit in guild.audit_logs(action=disnake.AuditLogAction.message_bulk_delete):
            backward_time = self.bot.now().shift(seconds=-15)
            if backward_time.timestamp() > audit.created_at.timestamp():
                continue
            if audit.extra is not None and audit.extra["count"] == len(valid_messages):
                executor = {
                    "id": audit.user.id,
                    "name": str(audit.user),
                }
                break

        full_upload_text = []
        channel = valid_messages[0].channel
        for n, message in enumerate(valid_messages, 1):
            current = []
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S") + " UTC"
            current.append(f"-- Pesan #{n} :: {str(message.author)} ({message.author.id}) [{timestamp}]")
            konten = message.content
            if not isinstance(konten, str):
                konten = "*Tidak ada konten*"
            if not konten:
                konten = "*Tidak ada konten*"
            current.append(konten)
            if len(message.attachments) > 0:
                current.append("")
                current.append("*Attachments*:")
                for xyz, attachment in enumerate(message.attachments, 1):
                    current.append(
                        f"Attachment #{xyz}: {attachment.filename} "
                        + f"({attachment.proxy_url}) ({attachment.url})"
                    )
            full_upload_text.append("\n".join(current))

        ikon_guild = guild.icon
        if ikon_guild is not None:
            ikon_guild = str(ikon_guild)

        real_content, _ = await self._upload_or_not("\n\n".join(full_upload_text), True)
        full_details = {
            "count": len(messages),
            "url": real_content,
            "channel": {"id": channel.id, "name": channel.name},
            "guild": {"icon": ikon_guild},
        }
        if len(executor.keys()) > 0:
            full_details["executor"] = executor

        self.logger.info("Multiple message got deleted, sending to modlog...")
        log_gen = self._generate_log(ModLogAction.MESSAGE_DELETE_BULK, full_details)
        await self.bot.add_modlog(log_gen, server_setting)


def setup(bot: naoTimesBot):
    bot.add_cog(ModLogMessage(bot))
