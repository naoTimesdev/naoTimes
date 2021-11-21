import asyncio
import logging
import random
import traceback
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import arrow
import discord
import wavelink
from discord.backoff import ExponentialBackoff
from discord.ext import commands

try:
    from sentry_sdk import push_scope
except ImportError:
    pass

from naotimes.bot import naoTimesBot
from naotimes.music import TrackEntry, TrackRepeat
from naotimes.utils import quote

if TYPE_CHECKING:
    from cogs.botbrain.error import BotBrainErrorHandler

VocalChannel = Union[discord.VoiceChannel, discord.StageChannel]


class MusikPlayerListener(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("MusicP.Listener")

        self.error_backoff: Dict[str, ExponentialBackoff] = {}

    def delay_next(self, guild_id: str):
        guild_id = str(guild_id)
        if guild_id not in self.error_backoff:
            # Dont delay first try
            self.error_backoff[guild_id] = ExponentialBackoff()
            return None
        delay = self.error_backoff[guild_id].delay()
        return delay

    def clean_delay(self, guild_id: int):
        guild_id = str(guild_id)
        if guild_id in self.error_backoff:
            try:
                del self.error_backoff[guild_id]
            except KeyError:
                pass

    @commands.Cog.listener("on_wavelink_node_ready")
    async def on_node_ready(self, node: wavelink.Node):
        self.logger.info(f"Node: <{node.identifier}> [{node.region.name}] is ready!")

    @commands.Cog.listener("on_wavelink_track_end")
    async def on_track_end(self, player: wavelink.Player, track: wavelink.Track, reason: str):
        ctime = self.bot.now().int_timestamp
        current = self.bot.ntplayer.get(player)
        current_track = player.source or track
        if current.current:
            current_track = current.current.track
        node = player.node
        track_title = None
        if current_track:
            track_title = current_track.title
        self.logger.info(
            f"Player: <{player.guild}> [{node.identifier}] track [{track_title}] has ended with: {reason}"
        )
        # Dispatch task
        self.bot.loop.create_task(
            self.bot.ntplayer.play_next(player),
            name=f"naotimes-track-end-{player.guild.id}_{ctime}_{reason}",
        )

    @commands.Cog.listener("on_wavelink_track_exception")
    async def on_track_exception(self, player: wavelink.Player, track: wavelink.Track, error: Exception):
        node = player.node
        real_track = player.source or track
        self.logger.warning(
            f"Player: <{player.guild}> [{node.identifier}] track [{real_track.title}] has exception: {error}"
        )
        vc_player = self.bot.ntplayer.get(player)
        channel = None
        determine_announce = True
        # Determine if we should announce error
        # If the current position is around 5 seconds before the track end, dont announce it.
        if vc_player.current:
            channel = vc_player.current.channel
            cpos = player.position
            duration = vc_player.current.track.duration
            grace_period = duration - 5
            if cpos >= grace_period:
                determine_announce = False
            await self._push_error_to_sentry(player, vc_player.current, error, "track-exc")

        if channel and determine_announce:
            try:
                await channel.send(
                    f"Terjadi kesalahan ketika menyetel lagu `{track.title}`, mohon kontak Owner Bot!"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener("on_wavelink_track_start")
    async def on_track_start(self, player: wavelink.Player, track: wavelink.Track):
        instance = self.bot.ntplayer.get(player)
        self.clean_delay(player.guild.id)

        # Temporary update the position.
        last_update = arrow.utcnow().datetime
        player.last_position = 1
        player.last_update = last_update

        current = instance.current
        track = current.track
        track_title = track.title
        self.logger.info(
            f"Player: <{player.guild}> [{player.node.identifier}]: <{track_title}> has started playing!"
        )
        embed = self.bot.ntplayer.generate_track_embed(current)
        try:
            await current.channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _dispatch_playback_next_later(
        self, player: wavelink.Player, delay: Optional[float], ctime: int
    ):
        self.logger.info(f"Player: Delaying playback of next track by {delay} seconds")
        if delay:
            await asyncio.sleep(delay)
        self.bot.loop.create_task(
            self.bot.ntplayer.play_next(player),
            name=f"naotimes-playback-retries-{player.guild.id}_{ctime}_{delay}",
        )

    @commands.Cog.listener("on_naotimes_playback_failed")
    async def on_playback_failed(self, player: wavelink.Player, entry: TrackEntry, exception: Exception):
        ctime = self.bot.now().int_timestamp
        instance = self.bot.ntplayer.get(player)
        self.logger.warning(
            f"Player: <{player.guild}> failed to play track: {entry.track}", exc_info=exception
        )
        delay_next = self.delay_next(player.guild.id)
        if instance.repeat != TrackRepeat.single:
            delay_next = None
        # Dispatch play_next agane
        self.bot.loop.create_task(
            self._dispatch_playback_next_later(player, delay_next, ctime),
            name=f"naotimes-playback-retries-delayed-{player.guild.id}_{ctime}_{str(exception)}",
        )
        channel = entry.channel
        if channel:
            error_msg_delay = f"Lagu `{entry.track.title}` gagal diputar, bot akan melewati lagu tersebut!"
            if delay_next:
                error_msg_delay += (
                    f"\nBot akan mencoba menyetel lagu selanjutnya dalam {round(delay_next, 2)} detik"
                )
            try:
                await channel.send(error_msg_delay)
            except (discord.Forbidden, discord.HTTPException, Exception):
                pass

        _do_not_log = (wavelink.errors.LoadTrackError, wavelink.errors.BuildTrackError)

        if isinstance(exception, _do_not_log):
            return

        # Push to log channel
        embed = discord.Embed(
            title="🎵 Music Error Log",
            colour=0xFF253E,
            description="Terjadi kesalahan ketika ingin memutar musik!",
            timestamp=self.bot.now().datetime,
        )
        track = entry.track
        _source = getattr(track, "source", "Unknown")
        track_info = f"**Judul**: `{track.title}`\n**Artis**: `{track.author}`"
        track_info += f"\n**Link**: [Link]({track.uri})\n**Source**: `{_source}`"
        embed.add_field(name="Lagu", value=track_info, inline=False)
        peladen_info = f"{player.guild.name} ({player.guild.id})"
        author_info = f"{str(entry.requester)} ({entry.requester.id})"
        embed.add_field(
            name="Pemutar", value=f"**Peladen**: {peladen_info}\n**Pemutar**: {author_info}", inline=False
        )

        error_info = [
            f"Lagu: {track.author} - {track.title}",
            f"URL: {track.uri} ({_source})",
            f"Peladen: {peladen_info}",
            f"Pemutar: {author_info}",
        ]
        tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
        tb_fmt = "".join(tb).replace("`", "")
        tb_fmt_quote = quote(tb_fmt, True, "py")

        full_pesan = "**Terjadi kesalahan pada pemutar musik**\n\n"
        full_pesan += quote("\n".join(error_info), True, "py") + "\n\n"
        full_pesan += tb_fmt_quote
        embed.add_field(name="Traceback", value=tb_fmt_quote, inline=False)

        error_cog: BotBrainErrorHandler = self.bot.get_cog("BotBrainErrorHandler")
        await error_cog._push_bot_log_or_cdn(embed, full_pesan)
        await self._push_error_to_sentry(player, entry, exception)

    async def _push_error_to_sentry(
        self, player: wavelink.Player, track: TrackEntry, e: Exception, handler: str = "playback"
    ):
        if self.bot._use_sentry:
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
                scope.set_tag("guild_id", str(player.guild.id))
                scope.set_tag("channel_id", str(player.channel.id))
                self.logger.error(
                    f"Player: <{player.guild}> failed to play track: <{track.track}>", exc_info=e
                )

    def _select_members(
        self, members: List[discord.Member], id_check: int = None
    ) -> Optional[discord.Member]:
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

    async def _delegate_on_bot_new_channel(self, guild: discord.Guild, after_channel: Optional[VocalChannel]):
        if after_channel is None:
            self.logger.info(f"Player: Bot got kicked from <{guild.id}> VC, deleting queue...")
            self.bot.ntplayer.delete(guild)
            return

        vc_members = after_channel.members
        delegated = self._select_members(vc_members)
        if delegated is None:
            self.logger.info(f"Player<{guild.id}>: No delegate found, no one to delegate to.")
            self.bot.ntplayer.change_dj(guild, None)
            return
        self.bot.ntplayer.change_dj(guild, delegated)

    @commands.Cog.listener("on_voice_state_update")
    async def _auto_voice_delegation(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Automatically delegate the DJ of the current music player"""
        guild = member.guild
        has_instance = self.bot.ntplayer.has(guild)
        if not has_instance:
            return

        if member.id == self.bot.user.id:
            return await self._delegate_on_bot_new_channel(guild, after.channel)

        if member.bot:
            return
        vc_check = guild.voice_client
        if not vc_check:
            self.bot.ntplayer.delete(guild)
            return
        instance = self.bot.ntplayer.get(guild)
        if instance.host is None:
            self.logger.info(f"Player: <{guild.id}> no host set, using <{member}> as host")
            self.bot.ntplayer.change_dj(guild, member)
            return

        if instance.host.id != member.id:
            return

        if before.channel is not None and before.channel.id == instance.channel.id:
            if after.channel is None or after.channel.id != instance.channel.id:
                channel = instance.channel
                self.logger.info(f"Player: <{guild.id}> host left VC, trying to delegate...")

                new_host = self._select_members(channel.members, member.id)
                if new_host is None:
                    # No one to delegate to, mark as none while we wait for a new one.
                    self.logger.info(f"Player: <{guild.id}> no delegate found, marking as None")
                    self.bot.ntplayer.change_dj(guild, None)
                    return

                self.logger.info(f"Player: <{guild.id}> delegate found, <{new_host}> is the new host.")
                self.bot.ntplayer.change_dj(guild, new_host)


def setup(bot: naoTimesBot):
    bot.add_cog(MusikPlayerListener(bot))
