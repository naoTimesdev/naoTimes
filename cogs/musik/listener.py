import asyncio
import logging
import random
import traceback
from typing import TYPE_CHECKING, Union, cast

import discord
import wavelink
from discord.backoff import ExponentialBackoff
from discord.ext import commands

try:
    from sentry_sdk import push_scope
except ImportError:
    push_scope = None

from naotimes.bot import naoTimesBot
from naotimes.music import SpotifyNoTrackFound, TrackEntry, TrackRepeat
from naotimes.utils import quote

if TYPE_CHECKING:
    from cogs.botbrain.error import BotBrainErrorHandler

VocalChannel = Union[discord.VoiceChannel, discord.StageChannel]


class MusikPlayerListener(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("MusicP.Listener")

        self.error_backoff: dict[str, ExponentialBackoff] = {}

    def delay_next(self, guild_id: int | str):
        guild_id = str(guild_id)
        if guild_id not in self.error_backoff:
            # Dont delay first try
            self.error_backoff[guild_id] = ExponentialBackoff()
            return None
        delay = self.error_backoff[guild_id].delay()
        return delay

    def clean_delay(self, guild_id: int | str):
        guild_id = str(guild_id)
        if guild_id in self.error_backoff:
            try:
                del self.error_backoff[guild_id]
            except KeyError:
                pass

    @commands.Cog.listener("on_wavelink_node_ready")
    async def on_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        self.logger.info(f"Node: <{payload.node.identifier}> is ready! (resumed: {payload.resumed})")
        manager = self.bot.ntplayer
        if manager:
            manager.track_node(payload.node.identifier)

    @commands.Cog.listener("on_wavelink_node_disconnected")
    async def on_node_disconnected(self, payload: wavelink.NodeDisconnectedEventPayload):
        self.logger.info(f"Node: <{payload.node.identifier}> is disconnected!")
        manager = self.bot.ntplayer
        if manager:
            manager.untrack_node(payload.node.identifier)

    @commands.Cog.listener("on_wavelink_track_end")
    async def on_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if player is None:
            return
        guild = player.guild
        manager = self.bot.ntplayer
        if guild is None or manager is None:
            return
        reason = payload.reason
        track = payload.track
        ctime = self.bot.now().int_timestamp
        current = manager.get(player)
        current_track = track
        if current.current:
            current_track = current.current.track
        node = player.node
        track_title = current_track.title if current_track else None
        self.logger.info(f"Player: <{player.guild}> [{node.identifier}] track [{track_title}] has ended with: {reason}")
        # Dispatch task
        self.bot.loop.create_task(
            manager.play_next(player),
            name=f"naotimes-track-end-{guild.id}_{ctime}_{reason}",
        )

    @commands.Cog.listener("on_wavelink_track_exception")
    async def on_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        player = payload.player
        if player is None:
            return
        guild = player.guild
        manager = self.bot.ntplayer
        if guild is None or manager is None:
            return
        track = payload.track
        error = RuntimeError(str(payload.exception))
        node = player.node
        real_track = track
        self.logger.warning(
            f"Player: <{player.guild}> [{node.identifier}] track [{real_track.title}] has exception: {error}"
        )
        vc_player = manager.get(player)
        channel = None
        determine_announce = True
        # Determine if we should announce error
        # If the current position is around 5 seconds before the track end, dont announce it.
        if vc_player.current:
            channel = vc_player.current.channel
            cpos = player.position
            duration = vc_player.current.track.length
            grace_period = duration - 5000
            if cpos >= grace_period:
                determine_announce = False
            await self._push_error_to_sentry(player, vc_player.current, error, "track-exc")

        if channel and determine_announce:
            tl = self.bot.i18n_for(guild, "musik")
            try:
                await channel.send(tl.t("error.track_exception", title=track.title))
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener("on_wavelink_track_start")
    async def on_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if player is None:
            return
        guild = player.guild
        manager = self.bot.ntplayer
        if guild is None or manager is None:
            return
        instance = manager.get(player)
        self.clean_delay(guild.id)

        current = instance.current
        if current is None:
            return
        track = current.track
        track_title = track.title
        self.logger.info(f"Player: <{player.guild}> [{player.node.identifier}]: <{track_title}> has started playing!")
        embed = manager.generate_track_embed(current)
        try:
            await current.channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _dispatch_playback_next_later(self, player: wavelink.Player, delay: float | None, ctime: int):
        self.logger.info(f"Player: Delaying playback of next track by {delay} seconds")
        guild = player.guild
        manager = self.bot.ntplayer
        if guild is None or manager is None:
            return
        if delay:
            await asyncio.sleep(delay)
        self.bot.loop.create_task(
            manager.play_next(player),
            name=f"naotimes-playback-retries-{guild.id}_{ctime}_{delay}",
        )

    @commands.Cog.listener("on_naotimes_playback_failed")
    async def on_playback_failed(self, player: wavelink.Player, entry: TrackEntry, exception: Exception):
        guild = player.guild
        manager = self.bot.ntplayer
        if guild is None or manager is None:
            return
        ctime = self.bot.now().int_timestamp
        instance = manager.get(player)
        self.logger.warning(f"Player: <{guild}> failed to play track: {entry.track}", exc_info=exception)
        delay_next = self.delay_next(guild.id)
        if instance.repeat != TrackRepeat.single:
            delay_next = None
        # Dispatch play_next agane
        self.bot.loop.create_task(
            self._dispatch_playback_next_later(player, delay_next, ctime),
            name=f"naotimes-playback-retries-delayed-{guild.id}_{ctime}_{exception!s}",
        )
        channel = entry.channel
        tl = self.bot.i18n_for(guild, "musik")
        if channel:
            error_msg_delay = tl.t("playback.failed", title=entry.track.title)
            if isinstance(exception, SpotifyNoTrackFound):
                error_msg_delay = tl.t("playback.spotify_failed")
            if delay_next:
                error_msg_delay += tl.t("playback.retry_suffix", delay=round(delay_next, 2))
            try:
                await channel.send(error_msg_delay)
            except (discord.Forbidden, discord.HTTPException, Exception):
                pass

        do_not_log = (wavelink.LavalinkLoadException, SpotifyNoTrackFound)

        if isinstance(exception, do_not_log):
            return

        # Push to log channel
        embed = discord.Embed(
            title=tl.t("log.title"),
            colour=0xFF253E,
            description=tl.t("log.description"),
            timestamp=self.bot.now().datetime,
        )
        track = entry.track
        source = str(getattr(track, "source", "Unknown"))
        track_info = tl.t("log.track_info", title=track.title, author=track.author)
        track_info += "\n" + tl.t("log.track_extra", uri=track.uri, source=source)
        embed.add_field(name=tl.t("log.field_track"), value=track_info, inline=False)
        peladen_info = f"{guild.name} ({guild.id})"
        author_info = f"{entry.requester!s} ({entry.requester.id})"
        embed.add_field(
            name=tl.t("log.field_player"),
            value=tl.t("log.player_info", guild=peladen_info, requester=author_info),
            inline=False,
        )

        error_info = [
            tl.t("log.error_line_track", author=track.author, title=track.title),
            tl.t("log.error_line_url", uri=track.uri, source=source),
            tl.t("log.error_line_guild", guild=peladen_info),
            tl.t("log.error_line_requester", requester=author_info),
        ]
        tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
        tb_fmt = "".join(tb).replace("`", "")
        tb_fmt_quote = quote(tb_fmt, True, "py")

        full_pesan = tl.t("log.heading") + "\n\n"
        full_pesan += quote("\n".join(error_info), True, "py") + "\n\n"
        full_pesan += tb_fmt_quote
        embed.add_field(name=tl.t("log.field_traceback"), value=tb_fmt_quote, inline=False)

        error_cog = cast("BotBrainErrorHandler | None", self.bot.get_cog("BotBrainErrorHandler"))
        if error_cog is None:
            return
        await error_cog._push_bot_log_or_cdn(embed, full_pesan)
        await self._push_error_to_sentry(player, entry, exception)

    async def _push_error_to_sentry(
        self, player: wavelink.Player, track: TrackEntry, e: Exception, handler: str = "playback"
    ):
        if self.bot._use_sentry and push_scope is not None:
            with push_scope() as scope:
                scope.user = {
                    "id": track.requester.id,
                    "username": str(track.requester),
                }

                scope.set_tag("cog", "music-backend")
                scope.set_tag("command", f"music-{handler}-handler")
                track_src = getattr(track.track, "source", "Unknown")
                scope.set_context(
                    "track",
                    {
                        "title": track.track.title,
                        "artist": track.track.author,
                        "source": track_src,
                        "link": track.track.uri,
                    },
                )
                scope.set_tag("command_type", "music")
                if player.guild is not None:
                    scope.set_tag("guild_id", str(player.guild.id))
                scope.set_tag("channel_id", str(player.channel.id if player.channel else 0))
                self.logger.error(f"Player: <{player.guild}> failed to play track: <{track.track}>", exc_info=e)

    def _select_members(self, members: list[discord.Member], id_check: int | None = None) -> discord.Member | None:
        # Select one member
        # Use priority, so if the member an admin, pick them
        # then check if they have specific permissions
        # if none of them match, get random person.

        administrator = []
        moderators = []
        normal_members = []
        for member in members:
            if member.bot:
                continue
            if member.id == id_check:
                continue
            if member.guild_permissions.administrator:
                administrator.append(member)
            elif member.guild_permissions.manage_guild:
                moderators.append(member)
            else:
                normal_members.append(member)

        if administrator:
            return random.choice(administrator)
        if moderators:
            return random.choice(moderators)
        if not normal_members:
            # Mark no delegate, if someone joined, mark them as
            # the new delegation later.
            return None
        return random.choice(normal_members)

    async def _delegate_on_bot_new_channel(self, guild: discord.Guild, after_channel: VocalChannel | None):
        manager = self.bot.ntplayer
        player = guild.voice_client
        if manager is None or not isinstance(player, wavelink.Player):
            return
        if after_channel is None:
            self.logger.info(f"Player: Bot got kicked from <{guild.id}> VC, deleting queue...")
            manager.delete(guild)
            return

        vc_members = after_channel.members
        delegated = self._select_members(vc_members)
        if delegated is None:
            self.logger.info(f"Player<{guild.id}>: No delegate found, no one to delegate to.")
            manager.change_dj(player, None)
            return
        manager.change_dj(player, delegated)

    @commands.Cog.listener("on_voice_state_update")
    async def _auto_voice_delegation(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        """Automatically delegate the DJ of the current music player"""
        guild = member.guild
        manager = self.bot.ntplayer
        if manager is None:
            return
        has_instance = manager.has(guild)
        if not has_instance:
            return

        bot_user = self.bot.user
        if bot_user is not None and member.id == bot_user.id:
            return await self._delegate_on_bot_new_channel(guild, after.channel)

        if member.bot:
            return
        vc_check = guild.voice_client
        if not isinstance(vc_check, wavelink.Player):
            manager.delete(guild)
            return
        instance = manager.get(vc_check)
        if instance.host is None:
            self.logger.info(f"Player: <{guild.id}> no host set, using <{member}> as host")
            manager.change_dj(vc_check, member)
            return

        if instance.host.id != member.id:
            return

        channel = instance.channel
        if channel is not None and before.channel is not None and before.channel.id == channel.id:
            if after.channel is None or after.channel.id != channel.id:
                self.logger.info(f"Player: <{guild.id}> host left VC, trying to delegate...")

                new_host = self._select_members(channel.members, member.id)
                if new_host is None:
                    # No one to delegate to, mark as none while we wait for a new one.
                    self.logger.info(f"Player: <{guild.id}> no delegate found, marking as None")
                    manager.change_dj(vc_check, None)
                    return

                self.logger.info(f"Player: <{guild.id}> delegate found, <{new_host}> is the new host.")
                manager.change_dj(vc_check, new_host)


async def setup(bot: naoTimesBot):
    await bot.add_cog(MusikPlayerListener(bot))
