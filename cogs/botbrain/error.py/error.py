from __future__ import annotations

try:
    from sentry_sdk import push_scope
except ImportError:
    pass

import io
import logging
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

import aiohttp
import arrow
import discord
from discord.app_commands import errors as app_errors
from discord.ext import commands
from discord.ext.commands import errors

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.music import errors as music_errors
from naotimes.utils import quote

if TYPE_CHECKING:
    from wavelink.player import Player


@dataclass
class CommandErrorHandle:
    exception: errors.CommandError
    ctx: naoTimesContext
    timestamp: arrow.Arrow = arrow.utcnow()

    @property
    def traceback(self):
        tb = traceback.format_exception(type(self.exception), self.exception, self.exception.__traceback__)
        return "".join(tb).replace("`", "")

    @property
    def cog_name(self) -> Optional[str]:
        cog_name = None
        ctx = self.ctx
        if not hasattr(ctx, "cog"):
            return cog_name
        if ctx.cog is not None:
            cog_name = ctx.cog.qualified_name
        return cog_name

    @property
    def name(self):
        if self.ctx.is_interaction():
            inter_cmd = self.ctx.interaction.command
            if inter_cmd is None:
                return "Unknown"
            return inter_cmd.qualified_name
        if self.ctx.command is None:
            return "Unknown"
        return self.ctx.command.qualified_name

    @property
    def app_type(self) -> Optional[str]:
        if self.ctx.is_interaction():
            command = self.ctx.interaction.command
            if isinstance(command, discord.app_commands.ContextMenu):
                if command.type is discord.AppCommandType.user:
                    return "User Command"
                elif command.type is discord.AppCommandType.message:
                    return "Message Command"
            return "Slash Command"
        return "Prefixed Message"

    @property
    def app_options(self) -> Optional[str]:
        if not self.ctx.is_interaction():
            return None
        command = self.ctx.interaction.command
        if command is None:
            return None
        if isinstance(command, discord.app_commands.ContextMenu):
            return command._param_name
        options = command._params
        if not options:
            return None
        all_values: List[str] = list(options.keys())
        if not all_values:
            return None
        return " ".join(all_values)

    @property
    def cmd_full(self):
        ctx = self.ctx
        if not self.ctx.is_interaction():
            return f"{self.name}\n`{ctx.message.clean_content}`"
        raw_cmd_name = self.name
        app_options = self.app_options
        command_exec = f"{raw_cmd_name} ({self.app_type})"
        if app_options:
            command_exec += f"\n`{raw_cmd_name} {app_options}`"
        return command_exec

    def create_embed(self):
        embed = discord.Embed(
            title="Error Logger",
            colour=0xFF253E,
            description="Terjadi kesalahan atau Insiden baru-baru ini...",
            timestamp=self.timestamp.datetime,
        )
        ctx = self.ctx
        embed.add_field(name="Cog", value=f"[nT!] {self.cog_name}", inline=False)
        embed.add_field(name="Perintah yang digunakan", value=self.cmd_full, inline=False)
        guild = ctx.guild
        channel = ctx.channel
        lokasi_insiden = "DM dengan Bot"
        if guild is not None:
            lokasi_insiden = f"{guild.name} (`{guild.id}`)"
            lokasi_insiden += f"\n#{channel.name} (`{channel.id}`)"
        author = ctx.author

        embed.add_field(name="Lokasi Insiden", value=lokasi_insiden, inline=False)
        embed.add_field(name="Pengguna", value=f"{author.name} (`{author.id}`)", inline=False)
        embed.add_field(name="Traceback", value=quote(self.traceback, True, "py"))
        embed.set_thumbnail(url="https://p.ihateani.me/mccvpqgd.png")
        return embed

    def create_text(self):
        perintah_name = self.name
        cog_name = self.cog_name
        if cog_name:
            perintah_name += f" (cog:{cog_name})"
        server_info = "Peladen: DM"
        if self.ctx.guild is not None:
            server_info = f"Peladen: {self.ctx.guild.name} ({self.ctx.guild.id})"
        channel_info = f"Kanal: {self.ctx.channel.name} ({self.ctx.channel.id})"
        error_info = [
            f"Perintah: {perintah_name}",
            f"Pesan: {self.cmd_full}",
            server_info,
            channel_info,
            f"Perusak: {self.ctx.author.name} ({self.ctx.author.id})",
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
    async def on_application_command_error(self, ctx: naoTimesContext, exception: Exception):
        """Logs any bot app command error, send to sentry, etc."""

        _MISSING_PERMS = (app_errors.MissingPermissions, app_errors.BotMissingPermissions)
        _MISSING_ROLE = (
            app_errors.MissingAnyRole,
            app_errors.MissingRole,
        )
        _ignore_completely = (
            app_errors.CommandNotFound,
            app_errors.TransformerError,
            app_errors.CommandLimitReached,
            app_errors.CommandSignatureMismatch,
        )
        exception = getattr(exception, "original", exception)
        command = ctx.interaction.command

        if isinstance(exception, _ignore_completely):
            self.bot.echo_error(exception)
            return
        if isinstance(exception, app_errors.NoPrivateMessage):
            return await self._push_message_safely(
                ctx, f"`{command.qualified_name}`` tidak bisa dipakai di Private Messages."
            )
        if isinstance(exception, _MISSING_PERMS):
            return await self.handle_permission_error(ctx, exception)
        if isinstance(exception, _MISSING_ROLE):
            return await self.handle_role_error(ctx, exception)
        if isinstance(exception, app_errors.CommandOnCooldown):
            return await self._push_message_safely(
                ctx, f"Kamu sedang dalam masa jeda. Coba lagi dalam waktu {exception.retry_after:.2f} detik."
            )
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
            if ctx.is_interaction():
                await ctx.send(content)
            else:
                await ctx.send(content, reference=reference)
        except (discord.HTTPException, discord.Forbidden, discord.InteractionResponded) as e:
            app_command = None
            if ctx.is_interaction():
                app_command = "application_command"
            await self._push_to_sentry(ctx, e, app_command)

    async def _push_bot_log_or_cdn(self, embed: discord.Embed, fallback_message: str):
        ctime = self.bot.now().int_timestamp
        try:
            await self.bot.send_error_log(embed=embed)
        except discord.HTTPException:
            self.logger.error("Failed to send bot error log to provided channel!")
            if len(fallback_message) > 1950:
                self.logger.error("Sending as file...")
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
        error_handle = CommandErrorHandle(e, ctx)
        full_pesan = error_handle.create_text()

        await self._push_bot_log_or_cdn(error_handle.create_embed(), full_pesan)

    async def _push_to_bot_log(self, ctx: naoTimesContext, e: Exception) -> None:
        ts = self.bot.now().int_timestamp
        # Create task to push to bot log
        self.bot.loop.create_task(self._actual_push_to_bot_log(ctx, e), name=f"naoTimes-BotLog-{ts}")

    async def _push_to_sentry(self, ctx: naoTimesContext, e: Exception) -> None:
        cmd_err = CommandErrorHandle(e, ctx)
        if self.bot._use_sentry:
            with push_scope() as scope:
                scope.user = {
                    "id": ctx.author.id,
                    "username": str(ctx.author),
                }

                scope.set_tag("command", cmd_err.name)
                if cmd_err.cog_name is not None:
                    scope.set_tag("cog", cmd_err.cog_name)
                scope.set_tag("channel_id", ctx.channel.id)
                if ctx.is_interaction():
                    cmd_exec = f"[{cmd_err.app_type}] {cmd_err.name}"
                    app_opts = cmd_err.app_options
                    if app_opts:
                        cmd_exec += f" {app_opts}"
                    scope.set_extra("message", cmd_exec)
                else:
                    scope.set_extra("message", ctx.message.clean_content)

                app_type = cmd_err.app_type.replace(" ", "_").lower()
                if app_type == "prefixed_message":
                    app_type = "normal"
                scope.set_tag("command_type", app_type)

                if ctx.guild is not None:
                    scope.set_tag("guild_id", ctx.guild.id)
                    if isinstance(ctx, naoTimesContext):
                        scope.set_extra(
                            "jump_to",
                            f"https://discordapp.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ctx.message.id}",
                        )

                self.logger.error(f"Ignoring exception in command {ctx.command}:", exc_info=e)


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainErrorHandler(bot))
