from __future__ import annotations

import io
import logging
import traceback
from dataclasses import dataclass, field

import aiohttp
import arrow
import discord
import wavelink
from discord.app_commands import errors as app_errors
from discord.ext import commands
from discord.ext.commands import errors

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.music import errors as music_errors
from naotimes.utils import quote

try:
    from sentry_sdk import push_scope
except ImportError:
    push_scope = None


def _t(ctx: naoTimesContext, key: str, **kwargs: object) -> str:
    """Resolve a shared ``common`` string for the context's guild."""
    return ctx.t(f"common.{key}", **kwargs)


@dataclass
class CommandErrorHandle:
    exception: Exception
    ctx: naoTimesContext
    timestamp: arrow.Arrow = field(default_factory=arrow.utcnow)

    @property
    def traceback(self):
        tb = traceback.format_exception(type(self.exception), self.exception, self.exception.__traceback__)
        return "".join(tb).replace("`", "")

    @property
    def cog_name(self) -> str | None:
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
            interaction = self.ctx.interaction
            if interaction is None:
                return "Unknown"
            inter_cmd = interaction.command
            if inter_cmd is None:
                return "Unknown"
            return inter_cmd.qualified_name
        if self.ctx.command is None:
            return "Unknown"
        return self.ctx.command.qualified_name

    @property
    def app_type(self) -> str | None:
        if self.ctx.is_interaction():
            interaction = self.ctx.interaction
            if interaction is None:
                return None
            command = interaction.command
            if isinstance(command, discord.app_commands.ContextMenu):
                if command.type is discord.AppCommandType.user:
                    return "User Command"
                elif command.type is discord.AppCommandType.message:
                    return "Message Command"
            return "Slash Command"
        return "Prefixed Message"

    @property
    def app_options(self) -> str | None:
        if not self.ctx.is_interaction():
            return None
        interaction = self.ctx.interaction
        if interaction is None:
            return None
        command = interaction.command
        if command is None:
            return None
        if isinstance(command, discord.app_commands.ContextMenu):
            return command._param_name
        options = command._params
        if not options:
            return None
        all_values: list[str] = list(options.keys())
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
        ctx = self.ctx
        embed = discord.Embed(
            title=_t(ctx, "incident.embed_title"),
            colour=0xFF253E,
            description=_t(ctx, "incident.embed_description"),
            timestamp=self.timestamp.datetime,
        )
        embed.add_field(name=_t(ctx, "incident.cog"), value=f"[nT!] {self.cog_name}", inline=False)
        embed.add_field(name=_t(ctx, "incident.command"), value=self.cmd_full, inline=False)
        guild = ctx.guild
        channel = ctx.channel
        lokasi_insiden = _t(ctx, "incident.dm")
        if guild is not None:
            lokasi_insiden = f"{guild.name} (`{guild.id}`)"
            if isinstance(channel, discord.abc.GuildChannel):
                channel_name = channel.name
            else:
                channel_name = _t(ctx, "incident.channel", id=channel.id)
            lokasi_insiden += f"\n#{channel_name} (`{channel.id}`)"
        author = ctx.author

        embed.add_field(name=_t(ctx, "incident.location"), value=lokasi_insiden, inline=False)
        embed.add_field(name=_t(ctx, "incident.user"), value=f"{author.name} (`{author.id}`)", inline=False)
        embed.add_field(name=_t(ctx, "incident.traceback"), value=quote(self.traceback, True, "py"))
        embed.set_thumbnail(url="https://p.ihateani.me/mccvpqgd.png")
        return embed

    def create_text(self):
        ctx = self.ctx
        perintah_name = self.name
        cog_name = self.cog_name
        if cog_name:
            perintah_name += f" (cog:{cog_name})"
        server_info = _t(ctx, "incident.server_dm")
        if ctx.guild is not None:
            server_info = _t(ctx, "incident.server", name=ctx.guild.name, id=ctx.guild.id)
        channel = ctx.channel
        if isinstance(channel, discord.abc.GuildChannel):
            channel_name = channel.name
        else:
            channel_name = _t(ctx, "incident.channel", id=channel.id)
        channel_info = _t(ctx, "incident.channel_info", name=channel_name, id=channel.id)
        error_info = [
            _t(ctx, "incident.command_info", command=perintah_name),
            _t(ctx, "incident.message_info", message=self.cmd_full),
            server_info,
            channel_info,
            _t(ctx, "incident.culprit", name=ctx.author.name, id=ctx.author.id),
        ]

        full_pesan = _t(ctx, "incident.text_title") + "\n\n"
        full_pesan += quote("\n".join(error_info), True, "py") + "\n\n"
        full_pesan += quote(self.traceback, True, "py")
        return full_pesan


class BotBrainErrorHandler(commands.Cog):
    module = "common"

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

        ignore_completely = (
            errors.CommandNotFound,
            errors.UserInputError,
            errors.NotOwner,
            errors.ArgumentParsingError,
        )
        MISSING_PERMS = (
            errors.MissingPermissions,
            errors.BotMissingPermissions,
        )
        MISSING_ROLE = (
            errors.MissingAnyRole,
            errors.MissingRole,
            errors.BotMissingAnyRole,
            errors.BotMissingRole,
        )
        # Get the original if exist
        exception = getattr(exception, "original", exception)

        if isinstance(exception, ignore_completely):
            self.bot.echo_error(exception)
            return
        if isinstance(exception, errors.DisabledCommand):
            return await ctx.send(_t(ctx, "errors.disabled_command", command=ctx.command))
        if isinstance(exception, errors.NoPrivateMessage):
            return await self._push_message_safely(ctx, _t(ctx, "errors.no_private_message", command=command))
        if isinstance(exception, errors.PrivateMessageOnly):
            return await self._push_message_safely(ctx, _t(ctx, "errors.private_message_only", command=command))
        if isinstance(exception, errors.NSFWChannelRequired):
            return await self._push_message_safely(ctx, _t(ctx, "errors.nsfw_channel_required", command=command))
        if isinstance(exception, MISSING_PERMS):
            return await self.handle_permission_error(ctx, exception)
        if isinstance(exception, MISSING_ROLE):
            return await self.handle_role_error(ctx, exception)
        if isinstance(exception, errors.CommandOnCooldown):
            return await self._push_message_safely(
                ctx, _t(ctx, "errors.cooldown", retry_after=f"{exception.retry_after:.2f}")
            )
        if isinstance(exception, errors.MaxConcurrencyReached):
            return await self.handle_concurrency_error(ctx, exception)

        if isinstance(exception, music_errors.EnsureVoiceChannel):
            is_main = exception.main_check
            message = _t(ctx, "errors.music.voice_required")
            client = exception.ctx.voice_client
            mention_data = None
            if isinstance(client, wavelink.Player) and client.channel:
                mention_data = client.channel.mention
            if not is_main:
                if mention_data:
                    message = _t(ctx, "errors.music.join_voice_channel", channel=mention_data)
                else:
                    message = _t(ctx, "errors.music.join_voice")
            return await self._push_message_safely(exception.ctx, message, True)
        if isinstance(exception, music_errors.EnsureBotVoiceChannel):
            return await self._push_message_safely(exception.ctx, _t(ctx, "errors.music.bot_not_connected"), True)
        if isinstance(exception, music_errors.EnsureHaveRequirement):
            reason = exception.reason
            return await self._push_message_safely(
                exception.ctx, _t(ctx, "errors.music.no_permission", reason=reason), True
            )
        if isinstance(exception, music_errors.EnsureBotHasQueue):
            return await self._push_message_safely(exception.ctx, _t(ctx, "errors.music.no_queue"), True)
        if isinstance(exception, music_errors.WavelinkNoNodes):
            return await self._push_message_safely(ctx, _t(ctx, "errors.music.no_nodes"), True)

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

        MISSING_PERMS = (app_errors.MissingPermissions, app_errors.BotMissingPermissions)
        MISSING_ROLE = (
            app_errors.MissingAnyRole,
            app_errors.MissingRole,
        )
        ignore_completely = (
            app_errors.CommandNotFound,
            app_errors.TransformerError,
            app_errors.CommandLimitReached,
            app_errors.CommandSignatureMismatch,
        )
        exception = getattr(exception, "original", exception)
        interaction = ctx.interaction
        if interaction is None:
            return
        command = interaction.command

        if type(exception) is app_errors.CheckFailure:
            # Gate checks (owner-only, maintenance, disabled) already replied to the user.
            return
        if isinstance(exception, ignore_completely):
            self.bot.echo_error(exception)
            return
        if isinstance(exception, app_errors.NoPrivateMessage):
            if command is None:
                return await self._push_message_safely(ctx, _t(ctx, "errors.no_private_message_generic"))
            return await self._push_message_safely(
                ctx, _t(ctx, "errors.no_private_message", command=command.qualified_name)
            )
        if isinstance(exception, MISSING_PERMS):
            return await self.handle_permission_error(ctx, exception)
        if isinstance(exception, MISSING_ROLE):
            return await self.handle_role_error(ctx, exception)
        if isinstance(exception, app_errors.CommandOnCooldown):
            return await self._push_message_safely(
                ctx, _t(ctx, "errors.cooldown", retry_after=f"{exception.retry_after:.2f}")
            )
        if isinstance(exception, music_errors.EnsureVoiceChannel):
            is_main = exception.main_check
            message = _t(ctx, "errors.music.voice_required")
            client = exception.ctx.voice_client
            mention_data = None
            if isinstance(client, wavelink.Player) and client.channel:
                mention_data = client.channel.mention
            if not is_main:
                if mention_data:
                    message = _t(ctx, "errors.music.join_voice_channel", channel=mention_data)
                else:
                    message = _t(ctx, "errors.music.join_voice")
            return await self._push_message_safely(exception.ctx, message, True)
        if isinstance(exception, music_errors.EnsureBotVoiceChannel):
            return await self._push_message_safely(exception.ctx, _t(ctx, "errors.music.bot_not_connected"), True)
        if isinstance(exception, music_errors.EnsureHaveRequirement):
            reason = exception.reason
            return await self._push_message_safely(
                exception.ctx, _t(ctx, "errors.music.no_permission", reason=reason), True
            )
        if isinstance(exception, music_errors.EnsureBotHasQueue):
            return await self._push_message_safely(exception.ctx, _t(ctx, "errors.music.no_queue"), True)
        if isinstance(exception, music_errors.WavelinkNoNodes):
            return await self._push_message_safely(ctx, _t(ctx, "errors.music.no_nodes"), True)

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
                _t(
                    ctx,
                    "errors.aiohttp_response",
                    status=exception.status,
                    message=exception.message,
                ),
            )
        return await self._push_message_safely(ctx, _t(ctx, "errors.aiohttp"))

    async def handle_discord_http_error(self, ctx: naoTimesContext, exception: discord.HTTPException):
        await self._push_to_sentry(ctx, exception)
        return await self._push_message_safely(ctx, _t(ctx, "errors.discord_http"))

    async def handle_permission_error(
        self,
        ctx: naoTimesContext,
        exception: errors.MissingPermissions
        | errors.BotMissingPermissions
        | app_errors.MissingPermissions
        | app_errors.BotMissingPermissions,
    ):
        missing_perms = exception.missing_permissions
        missing = [perm.replace("_", " ").replace("guild", "server").title() for perm in missing_perms]
        opening_key = "errors.missing_permissions_bot"
        if not str(exception).lower().startswith("bot"):
            opening_key = "errors.missing_permissions_user"
        await self._push_message_safely(ctx, _t(ctx, opening_key, permissions=", ".join(missing)))

    async def handle_role_error(
        self,
        ctx: naoTimesContext,
        exception: errors.MissingRole
        | errors.MissingAnyRole
        | errors.BotMissingRole
        | errors.BotMissingAnyRole
        | app_errors.MissingRole
        | app_errors.MissingAnyRole,
    ):
        opening_key = "errors.missing_roles_bot"
        if not str(exception).lower().startswith("bot"):
            opening_key = "errors.missing_roles_user"
        roles_needed: list[int | str] = []
        if isinstance(exception, (errors.MissingAnyRole, errors.BotMissingAnyRole, app_errors.MissingAnyRole)):
            roles_needed.extend(exception.missing_roles)
        else:
            roles_needed.append(exception.missing_role)
        roles_parsed = [f"{role!r}" for role in roles_needed]
        await self._push_message_safely(ctx, _t(ctx, opening_key, roles=", ".join(roles_parsed)))

    async def handle_concurrency_error(self, ctx: naoTimesContext, exception: errors.MaxConcurrencyReached):
        translated = {
            "default": _t(ctx, "errors.concurrency_per.default"),
            "user": _t(ctx, "errors.concurrency_per.user"),
            "guild": _t(ctx, "errors.concurrency_per.guild"),
            "channel": _t(ctx, "errors.concurrency_per.channel"),
            "member": _t(ctx, "errors.concurrency_per.member"),
            "category": _t(ctx, "errors.concurrency_per.category"),
        }
        per_name = translated.get(exception.per.name, exception.per.name)
        return await self._push_message_safely(
            ctx, _t(ctx, "errors.concurrency", number=exception.number, per=per_name)
        )

    async def _push_to_user(self, ctx: naoTimesContext):
        await self._push_message_safely(ctx, _t(ctx, "errors.user_info"))

    async def _push_message_safely(self, ctx: naoTimesContext, content: str, do_ref: bool = False):
        try:
            reference = ctx.message if do_ref else None
            if ctx.is_interaction() or reference is None:
                await ctx.send(content)
            else:
                await ctx.send(content, reference=reference)
        except (discord.HTTPException, discord.Forbidden, discord.InteractionResponded) as e:
            await self._push_to_sentry(ctx, e)

    async def _push_bot_log_or_cdn(
        self,
        embed: discord.Embed,
        fallback_message: str,
        ctx: naoTimesContext | None = None,
    ):
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
                long_log_message = (
                    _t(ctx, "incident.file_too_long")
                    if ctx is not None
                    else "Dikarenakan log terlalu panjang, ini adalah log errornya"
                )
                await self.bot.send_error_log(long_log_message, file=the_file)
            else:
                await self.bot.send_error_log(fallback_message)

    async def _actual_push_to_bot_log(self, ctx: naoTimesContext, e: Exception) -> None:
        error_handle = CommandErrorHandle(e, ctx)
        full_pesan = error_handle.create_text()

        await self._push_bot_log_or_cdn(error_handle.create_embed(), full_pesan, ctx)

    async def _push_to_bot_log(self, ctx: naoTimesContext, e: Exception) -> None:
        ts = self.bot.now().int_timestamp
        # Create task to push to bot log
        self.bot.loop.create_task(self._actual_push_to_bot_log(ctx, e), name=f"naoTimes-BotLog-{ts}")

    async def _push_to_sentry(self, ctx: naoTimesContext, e: Exception) -> None:
        cmd_err = CommandErrorHandle(e, ctx)
        if self.bot._use_sentry and push_scope is not None:
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

                app_type = (cmd_err.app_type or "unknown").replace(" ", "_").lower()
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
