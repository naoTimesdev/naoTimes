import logging
import random
from typing import List, Optional, Union

import arrow
import discord
import wavelink
from discord.ext import commands

from naotimes.bot import naoTimesBot

VocalChannel = Union[discord.VoiceChannel, discord.StageChannel]


class MusikPlayerListener(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("MusicP.Listener")

    @commands.Cog.listener("on_wavelink_node_ready")
    async def on_node_ready(self, node: wavelink.Node):
        self.logger.info(f"Node: <{node.identifier}> [{node.region.name}] is ready!")

    @commands.Cog.listener("on_wavelink_track_end")
    async def on_track_end(self, player: wavelink.Player, track: wavelink.Track, reason: str):
        ctime = self.bot.now().int_timestamp
        current = self.bot.ntplayer.get(player)
        current_track = current.current.track or track
        node = player.node
        track_title = None
        if current_track:
            track_title = current_track.title
        self.logger.info(
            f"Player: <{player.guild}> [{node.identifier}] track [{track_title}] has ended with: {reason}"
        )
        # Dispatch task
        self.bot.loop.create_task(
            self.bot.ntplayer.play_next(player, current_track),
            name=f"naotimes-track-end-{player.guild.id}_{ctime}_{reason}",
        )

    @commands.Cog.listener("on_wavelink_track_exception")
    async def on_track_exception(self, player: wavelink.Player, track: wavelink.Track, error: Exception):
        node = player.node
        self.logger.warning(
            f"Player: <{player.guild}> [{node.identifier}] track [{track.title}] has exception: {error}"
        )
        vc_player = self.bot.ntplayer.get(player)
        channel = None
        if vc_player.current:
            channel = vc_player.current.channel

        if channel:
            try:
                await channel.send(
                    f"Terjadi kesalahan ketika menyetel lagu `{track.title}`, mohon kontak Owner Bot!"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener("on_wavelink_track_start")
    async def on_track_start(self, player: wavelink.Player, track: wavelink.Track):
        instance = self.bot.ntplayer.get(player)

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
