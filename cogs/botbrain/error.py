from __future__ import annotations

try:
    from sentry_sdk import push_scope
except ImportError:
    pass

import io
import logging
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp
import arrow
import discord
from discord.ext import app, commands
from discord.ext.app import errors as app_errors
from discord.ext.commands import errors

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.music import errors as music_errors
from naotimes.utils import quote

if TYPE_CHECKING:
    from wavelink.player import Player


@dataclass
class CommandHandle:
    exception: Exception
    name: str
    message: str
    author_id: int
    author_name: str
    channel_id: int
    channel_name: str
    is_dm: bool = False
    guild_id: int = None
    guild_name: str = None
    cog_name: str = None
    timestamp: arrow.Arrow = arrow.utcnow()

    @property
    def traceback(self):
        tb = traceback.format_exception(type(self.exception), self.exception, self.exception.__traceback__)
        return "".join(tb).replace("`", "")

    def create_embed(self):
        embed = discord.Embed(
            title="Error Logger",
            colour=0xFF253E,
            description="Terjadi kesalahan atau Insiden baru-baru ini...",
            timestamp=self.timestamp.datetime,
        )
        if self.cog_name:
            embed.add_field(name="Cogs", value=f"[nT!] {self.cog_name}", inline=False)
        embed.add_field(name="Perintah yang digunakan", value=f"{self.name}\n`{self.message}`", inline=False)
        lokasi_insiden = "DM dengan Bot"
        if self.guild_id:
            lokasi_insiden = f"{self.guild_name} ({self.guild_id})"
            lokasi_insiden += f"\n#{self.channel_name} ({self.channel_id})"

        embed.add_field(name="Lokasi Insiden", value=lokasi_insiden, inline=False)
        embed.add_field(name="Pengguna", value=f"{self.author_name} ({self.author_id})", inline=False)
        embed.add_field(name="Traceback", value=quote(self.traceback, True, "py"))
        embed.set_thumbnail(url="https://p.ihateani.me/mccvpqgd.png")
        return embed

    def create_text(self):
        perintah_text = self.name
        if self.cog_name:
            perintah_text += f" (cog:{self.cog_name})"
        server_info = "Peladen: DM"
        if self.guild_id:
            server_info = f"Peladen: {self.guild_name} ({self.guild_id})"
        channel_info = f"Kanal: {self.channel_name} ({self.channel_id})"
        error_info = [
            f"Perintah: {perintah_text}",
            f"Pesan: {self.message}",
            server_info,
            channel_info,
            f"Perusak: {self.author_name} ({self.author_id})",
        ]

        full_pesan = "**Terjadi Kesalahan**\n\n"
        full_pesan += quote("\n".join(error_info), True, "py") + "\n\n"
        full_pesan += quote(self.traceback, True, "py")
        return full_pesan


class BotBrainErrorHandler(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.ErrorHandler")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: naoTimesContext, exception: errors.CommandError):
        """Logs any bot command error, send to sentry, etc."""
        command = ctx.command

        if hasattr(command, "on_error"):
            # Command already handled the error.
            return

        _ignore_completely = (
            errors.CommandNotFound,
            errors.UserInputError,
            errors.NotOwner,
            errors.ArgumentParsingError,
        )
        _MISSING_PERMS = (
            errors.MissingPermissions,
            errors.BotMissingPermissions,
        )
        _MISSING_ROLE = (
            errors.MissingAnyRole,
            errors.MissingRole,
            errors.BotMissingAnyRole,
            errors.BotMissingRole,
        )
        # Get the original if exist
        exception = getattr(exception, "original", exception)

        if isinstance(exception, _ignore_completely):
            self.bot.echo_error(exception)
            return
        if isinstance(exception, errors.DisabledCommand):
            return await ctx.send(f"`{ctx.command}` dinonaktifkan.")
        if isinstance(exception, errors.NoPrivateMessage):
            return await self._push_message_safely(
                ctx, f"`{command}`` tidak bisa dipakai di Private Messages."
            )
        if isinstance(exception, errors.PrivateMessageOnly):
            return await self._push_message_safely(
                ctx, f"`{command}`` hanya bisa dipakai di Private Messages."
            )
        if isinstance(exception, errors.NSFWChannelRequired):
            return await self._push_message_safely(ctx, f"`{command}` hanya bisa dipakai di kanal NSFW.")
        if isinstance(exception, _MISSING_PERMS):
            return await self.handle_permission_error(ctx, exception)
        if isinstance(exception, _MISSING_ROLE):
            return await self.handle_role_error(ctx, exception)
        if isinstance(exception, errors.CommandOnCooldown):
            return await self._push_message_safely(
                ctx, f"Kamu sedang dalam masa jeda. Coba lagi dalam waktu {exception.retry_after:.2f} detik."
            )
        if isinstance(exception, errors.MaxConcurrencyReached):
            return await self.handle_concurrency_error(ctx, exception)

        if isinstance(exception, music_errors.EnsureVoiceChannel):
            is_main = exception.main_check
            message = "Anda harus join VC terlebih dahulu!"
            client: Player = exception.ctx.voice_client
            mention_data = None
            if client and client.channel:
                mention_data = client.channel.mention
            if not is_main:
                message = "Mohon join voice chat "
                if mention_data:
                    message += mention_data + " "
                message += "untuk menyetel musik."
            return await self._push_message_safely(exception.ctx, message, True)
        if isinstance(exception, music_errors.EnsureBotVoiceChannel):
            return await self._push_message_safely(
                exception.ctx, "Bot tidak terhubung dengan VC manapun!", True
            )
        if isinstance(exception, music_errors.EnsureHaveRequirement):
            reason = exception.reason
            return await self._push_message_safely(
                exception.ctx, f"Anda tidak memiliki hak untuk melakukan hal tersebut!\n{reason}", True
            )
        if isinstance(exception, music_errors.WavelinkNoNodes):
            return await self._push_message_safely(
                ctx, "Bot tidak memiliki node Lavalink untuk menyetel lagu, mohoon kontak bot Owner!", True
            )

        if isinstance(exception, aiohttp.ClientError):
            return await self.handle_aiohttp_error(ctx, exception)
        if isinstance(exception, discord.HTTPException):
            return await self.handle_discord_http_error(ctx, exception)

        await self._push_to_sentry(ctx, exception)
        await self._push_to_bot_log(ctx, exception)
        await self._push_to_user(ctx)

    @commands.Cog.listener()
    async def on_application_error(self, ctx: app.ApplicationContext, exception: Exception):
        """Logs any bot app command error, send to sentry, etc."""

        _ignore_completely = (
            app_errors.ApplicationUserInputError,
            app_errors.ApplicationNotOwner,
        )
        _MISSING_PERMS = (
            app_errors.ApplicationMissingPermissions,
            app_errors.ApplicationBotMissingPermissions,
        )
        _MISSING_ROLE = (
            app_errors.ApplicationMissingAnyRole,
            app_errors.ApplicationMissingRole,
            app_errors.ApplicationBotMissingAnyRole,
            app_errors.ApplicationBotMissingRole,
        )
        exception = getattr(exception, "original", exception)
        command = ctx.command

        if isinstance(exception, _ignore_completely):
            self.bot.echo_error(exception)
            return
        if isinstance(exception, app_errors.ApplicationNoPrivateMessage):
            return await self._push_message_safely(
                ctx, f"`{command.qualified_name}`` tidak bisa dipakai di Private Messages."
            )
        if isinstance(exception, app_errors.ApplicationPrivateMessageOnly):
            return await self._push_message_safely(
                ctx, f"`{command}`` hanya bisa dipakai di Private Messages."
            )
        if isinstance(exception, app_errors.ApplicationNSFWChannelRequired):
            return await self._push_message_safely(ctx, f"`{command}` hanya bisa dipakai di kanal NSFW.")
        if isinstance(exception, _MISSING_PERMS):
            return await self.handle_permission_error(ctx, exception)
        if isinstance(exception, _MISSING_ROLE):
            return await self.handle_role_error(ctx, exception)
        if isinstance(exception, app_errors.ApplicationCommandOnCooldown):
            return await self._push_message_safely(
                ctx, f"Kamu sedang dalam masa jeda. Coba lagi dalam waktu {exception.retry_after:.2f} detik."
            )
        if isinstance(exception, app_errors.ApplicationMaxConcurrencyReached):
            return await self.handle_concurrency_error(ctx, exception)
        if isinstance(exception, music_errors.EnsureVoiceChannel):
            is_main = exception.main_check
            message = "Anda harus join VC terlebih dahulu!"
            client: Player = exception.ctx.voice_client
            mention_data = None
            if client and client.channel:
                mention_data = client.channel.mention
            if not is_main:
                message = "Mohon join voice chat "
                if mention_data:
                    message += mention_data + " "
                message += "untuk menyetel musik."
            return await self._push_message_safely(exception.ctx, message, True)
        if isinstance(exception, music_errors.EnsureBotVoiceChannel):
            return await self._push_message_safely(
                exception.ctx, "Bot tidak terhubung dengan VC manapun!", True
            )
        if isinstance(exception, music_errors.EnsureHaveRequirement):
            reason = exception.reason
            return await self._push_message_safely(
                exception.ctx, f"Anda tidak memiliki hak untuk melakukan hal tersebut!\n{reason}", True
            )
        if isinstance(exception, music_errors.WavelinkNoNodes):
            return await self._push_message_safely(
                ctx, "Bot tidak memiliki node Lavalink untuk menyetel lagu, mohoon kontak bot Owner!", True
            )

        if isinstance(exception, aiohttp.ClientError):
            return await self.handle_aiohttp_error(ctx, exception)
        if isinstance(exception, discord.HTTPException):
            return await self.handle_discord_http_error(ctx, exception)

        await self._push_to_sentry(ctx, exception)
        await self._push_to_bot_log(ctx, exception)
        await self._push_to_user(ctx)

    # Repeating handlers
    async def handle_aiohttp_error(self, ctx: naoTimesContext, exception: aiohttp.ClientError):
        await self._push_to_sentry(ctx, exception)
        if isinstance(exception, aiohttp.ClientResponseError):
            return await self._push_message_safely(
                ctx,
                f"Mendapatkan kode HTTP {exception.status} dari API\n```py\n",
                exception.message,
                "\n```",
            )
        return await self._push_message_safely(
            ctx, "Terjadi kesalahan ketika berkomunikasi dengan API, mohon coba sesaat lagi!"
        )

    async def handle_discord_http_error(self, ctx: naoTimesContext, exception: discord.HTTPException):
        await self._push_to_sentry(ctx, exception)
        return await self._push_message_safely(
            ctx, "Terjadi kesalahan ketika berkomunikasi dengan Discord, mohon coba sesaat lagi!"
        )

    async def handle_permission_error(self, ctx: naoTimesContext, exception: errors.MissingPermissions):
        missing_perms = exception.missing_permissions
        missing = [perm.replace("_", " ").replace("guild", "server").title() for perm in missing_perms]
        opening_message = "Anda tidak memiliki hak untuk menjalankan perintah ini!"
        if str(exception).lower().startswith("bot"):
            opening_message = "Bot tidak memiliki hak untuk menjalankan perintah ini!"
        await self._push_message_safely(
            ctx,
            f"{opening_message}\nKurang: `{', '.join(missing)}`",
        )
        return

    async def handle_role_error(self, ctx: naoTimesContext, exception: errors.MissingRole):
        opening_message = "Anda tidak memiliki hak untuk menjalankan perintah ini!"
        if str(exception).lower().startswith("bot"):
            opening_message = "Bot tidak memiliki hak untuk menjalankan perintah ini!"
        roles_needed = []
        if hasattr(exception, "missing_roles"):
            roles_needed.extend(exception.missing_roles)
        else:
            roles_needed.append(exception.missing_role)
        roles_parsed = [f"{role!r}" for role in roles_needed]
        await self._push_message_safely(
            ctx, f"{opening_message}\nDibutuhkan role dengan ID: {', '.join(roles_parsed)}"
        )

    async def handle_concurrency_error(self, ctx: naoTimesContext, exception: errors.MaxConcurrencyReached):
        _translated = {
            "default": "orang",
            "user": "orang",
            "guild": "peladen",
            "channel": "kanal",
            "member": "pengguna",
            "category": "kategori",
        }
        cooldown_msg = "Terlalu banyak orang sedang memakai perintah ini, "
        per_name = _translated.get(exception.per.name, exception.per.name)
        per_data = f"tiap {exception.number} {per_name}"
        cooldown_msg += f"perintah ini hanya dapat digunakan {per_data} secara bersamaan"
        return await self._push_message_safely(ctx, cooldown_msg)

    async def _push_to_user(self, ctx: naoTimesContext):
        user_err_info = "**Error**: Insiden ini telah dilaporkan! Jika ingin dipercepat penyelesaiannya"
        user_err_info += (
            ", mohon buka Issue baru di GitHub: <https://github.com/naoTimesdev/naoTimes/issues/new/choose>"
        )
        await self._push_message_safely(ctx, user_err_info)

    async def _push_message_safely(self, ctx: naoTimesContext, content: str, do_ref: bool = False):
        try:
            reference = ctx.message if do_ref else None
            await ctx.send(content, reference=reference)
        except (discord.HTTPException, discord.Forbidden, discord.InteractionResponded) as e:
            app_command = None
            if isinstance(ctx, app.ApplicationContext):
                app_command = "application_command"
            await self._push_to_sentry(ctx, e, app_command)

    async def _push_bot_log_or_cdn(self, embed: discord.Embed, fallback_message: str):
        ctime = self.bot.now().int_timestamp
        try:
            await self.bot.send_error_log(embed=embed)
        except discord.HTTPException:
            self.logger.error("Failed to send bot error log to provided channel!")
            if len(fallback_message) > 1950:
                iha_link, err_msg = await self.bot.send_ihateanime(fallback_message, "naoTimesErrorLog_")
                if iha_link is not None:
                    finalized_text = "**Terjadi kesalahan**\n"
                    finalized_text += "Dikarenakan traceback dan sebagainya mencapai limit discord, log dapat"
                    finalized_text += f" diakses di sini: <{iha_link}>"
                    finalized_text += "\n\nLog valid selama kurang lebih 2.5 bulan"
                    await self.bot.send_error_log(finalized_text)
                else:
                    self.logger.error("Failed to upload log to ihateani.me CDN, using discord upload...")
                    fallback_message += f"\n\nihateani.me Error log: {err_msg}"
                    the_file = discord.File(
                        io.BytesIO(fallback_message.encode("utf-8")),
                        filename=f"naoTimesErrorLog_{ctime}.txt",
                    )
                    await self.bot.send_error_log(
                        "Dikarenakan log terlalu panjang, ini adalah log errornya", file=the_file
                    )
            else:
                await self.bot.send_error_log(fallback_message)

    async def _actual_push_to_bot_log(self, ctx: naoTimesContext, e: Exception) -> None:
        is_dm = ctx.guild is None
        guild_id = ctx.guild.id if ctx.guild is not None else None
        guild_name = ctx.guild.name if ctx.guild is not None else None
        error_handle = CommandHandle(
            e,
            ctx.command.name,
            ctx.message.clean_content,
            ctx.author.id,
            ctx.author.name,
            ctx.channel.id,
            ctx.channel.name,
            is_dm,
            guild_id,
            guild_name,
            ctx.cog.qualified_name if ctx.cog else None,
        )

        full_pesan = error_handle.create_text()

        await self._push_bot_log_or_cdn(error_handle.create_embed(), full_pesan)

    async def _push_to_bot_log(self, ctx: naoTimesContext, e: Exception) -> None:
        ts = self.bot.now().int_timestamp
        # Create task to push to bot log
        self.bot.loop.create_task(self._actual_push_to_bot_log(ctx, e), name=f"naoTimes-BotLog-{ts}")

    async def _push_to_sentry(self, ctx: naoTimesContext, e: Exception, app_type: str = None) -> None:
        if self.bot._use_sentry:
            with push_scope() as scope:
                scope.user = {
                    "id": ctx.author.id,
                    "username": str(ctx.author),
                }

                scope.set_tag("command", ctx.command.qualified_name)
                if ctx.cog is not None:
                    scope.set_tag("cog", ctx.cog.qualified_name)
                scope.set_tag("channel_id", ctx.channel.id)
                scope.set_extra("message", ctx.message.content)

                if app_type is not None:
                    scope.set_tag("command_type", app_type)
                else:
                    scope.set_tag("command_type", "normal")

                if ctx.guild is not None:
                    scope.set_tag("guild_id", ctx.guild.id)
                    scope.set_extra(
                        "jump_to",
                        f"https://discordapp.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ctx.message.id}",
                    )

                self.logger.error(f"Ignoring exception in command {ctx.command}:", exc_info=e)


def setup(bot: naoTimesBot):
    bot.add_cog(BotBrainErrorHandler(bot))
