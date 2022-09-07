"""
MIT License

Copyright (c) 2019-2022 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import asyncio
import logging
from math import ceil
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import arrow
import wavelink
from discord.channel import StageChannel, VoiceChannel
from discord.colour import Colour
from discord.embeds import Embed
from wavelink import Player
from wavelink.errors import NodeOccupied, NoMatchingNode
from wavelink.ext import spotify
from wavelink.tracks import YouTubeTrack
from wavelink.utils import MISSING

from naotimes.timeparse import TimeString

from .errors import UnsupportedURLFormat
from .queue import (
    GuildMusicInstance,
    TrackEntry,
    TrackQueueAll,
    TrackQueueImpl,
    TrackQueueSingle,
    TrackRepeat,
)
from .tracks import (
    BandcampDirectLink,
    SoundcloudDirectLink,
    SpotifyDirectTrack,
    SpotifyTrack,
    TidalDirectLink,
    TwitchDirectLink,
    YoutubeDirectLinkTrack,
)

if TYPE_CHECKING:
    from discord.guild import Guild
    from discord.member import Member

    from naotimes.bot import naoTimesBot
    from naotimes.config import naoTimesLavanodes


__all__ = (
    "naoTimesPlayer",
    "format_duration",
)
RealTrack = Union[YouTubeTrack, YoutubeDirectLinkTrack, SpotifyTrack]
VocalChannel = Union[VoiceChannel, StageChannel]


def format_duration(duration: float):
    hours = duration // 3600
    duration = duration % 3600
    minutes = duration // 60
    seconds = duration % 60

    minutes = str(int(round(minutes))).zfill(2)
    seconds = str(int(round(seconds))).zfill(2)
    if hours >= 1:
        hours = str(int(round(hours))).zfill(2)
        return f"{hours}:{minutes}:{seconds}"
    return f"{minutes}:{seconds}"


class naoTimesPlayer:
    def __init__(
        self,
        client: naoTimesBot,
        loop: asyncio.AbstractEventLoop = None,
        spotify_client: spotify.SpotifyClient = None,
    ):
        self.logger = logging.getLogger("naoTimes.MusicPlayer")
        self._active_guilds: Dict[int, GuildMusicInstance] = {}
        self._client = client
        # Use single spotify client for all players
        self._spotify = spotify_client
        self._loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()

    def __del__(self):
        self._loop.create_task(self.close(), name="naotimes-player-close-all-players")

    @property
    def actives(self):
        return self._active_guilds

    async def close(self):
        self.logger.info("Closing all instances...")
        channel_ids = [instance.channel.id for instance in self._active_guilds.values() if instance.channel]
        for vc_instance in self._client.voice_clients:
            vc_instance: Player
            if vc_instance.channel.id in channel_ids:
                await vc_instance.disconnect(force=True)
        self.logger.info("Disconnecting nodes...")
        for node in wavelink.NodePool._nodes.copy().values():
            await node.disconnect(force=True)
        await self._spotify.session.close()

    async def add_node(self, node: naoTimesLavanodes):
        try:
            self.logger.info(f"Trying to connect with node <{node.identifier}>...")
            await wavelink.NodePool.create_node(
                bot=self._client,
                host=node.host,
                port=node.port,
                password=node.password,
                identifier=node.identifier,
                spotify_client=self._spotify,
            )
        except NodeOccupied:
            self.logger.warning(f"Node <{node.identifier}> is already occupied or registered.")

    async def remove_node(self, identifier: str):
        try:
            node = wavelink.NodePool.get_node(identifier=identifier)
            await node.disconnect(force=False)
        except NoMatchingNode:
            self.logger.warning(f"Node <{identifier}> is not registered.")

    def _get_id(self, vc: Union[Player, Guild]) -> int:
        if hasattr(vc, "guild"):
            return vc.guild.id
        else:
            return vc.id

    def create(self, vc: Union[Guild, Player]):
        guild_id = self._get_id(vc)
        if guild_id not in self._active_guilds:
            track_queue = TrackQueueImpl()
            self._active_guilds[guild_id] = GuildMusicInstance(track_queue)

    def has(self, vc: Union[Player, Guild]) -> bool:
        if hasattr(vc, "guild"):
            return vc.guild.id in self._active_guilds
        elif hasattr(vc, "id"):
            return vc.id in self._active_guilds
        return False

    def get(self, vc: Union[Guild, Player]) -> GuildMusicInstance:
        self.create(vc)
        return self._active_guilds[self._get_id(vc)]

    def set(self, vc: Union[Guild, Player], instance: GuildMusicInstance):
        self._active_guilds[self._get_id(vc)] = instance

    def get_tracks(self, vc: Union[Player, Guild]) -> List[TrackEntry]:
        all_tracks: List[TrackEntry] = []
        for track in self.get(vc).queue._queue:
            all_tracks.append(track)
        return all_tracks

    def delete(self, vc: Union[Player, Guild]):
        if self.has(vc):
            del self._active_guilds[self._get_id(vc)]

    def delete_track(self, vc: Union[Player, Guild], index: int):
        try:
            queue = self.get(vc)
            if queue.repeat == TrackRepeat.single:
                return True
            self.logger.info(f"Player: Trying to remove track [{index}] at <{vc.guild}>")
            del queue.queue._queue[index]
            return True
        except Exception as e:
            self.logger.error(f"Player: Failed to remove track [{index}] at <{vc.guild}>", exc_info=e)
            return False

    def clear(self, vc: Union[Player, Guild]):
        guild_id = self._get_id(vc)
        self._active_guilds[guild_id].queue.clear()

    async def enqueue(self, vc: Player, entries: Union[TrackEntry, List[TrackEntry]]):
        if not isinstance(entries, list):
            entries = [entries]
        queue = self.get(vc)
        guild_id = self._get_id(vc)
        for entry in entries:
            track = entry.track
            self.logger.info(f"Player: Enqueueing at guild <{guild_id}>: {track.title} by {track.author}")
            await queue.queue.put(entry)
        self._active_guilds[guild_id] = queue

    def _set_current(self, vc: Player, track: Optional[TrackEntry] = None) -> None:
        self.get(vc).current = track

    def change_dj(self, vc: Player, user: Member):
        self.get(vc).host = user

    def set_channel(self, vc: Player, channel: VocalChannel):
        self.get(vc).channel = channel

    def reset_vote(self, vc: Player):
        instance = self.get(vc)
        instance.skip_votes.clear()
        self.set(vc, instance)

    def add_vote(self, vc: Player, user: Member):
        self.get(vc).skip_votes.add(user)

    def change_repeat_mode(self, vc: Player, mode: TrackRepeat) -> Optional[GuildMusicInstance]:
        queue = self.get(vc)
        if queue.repeat == mode:
            return None
        queue.repeat = mode
        if mode == TrackRepeat.single:
            queue.queue = TrackQueueSingle.from_other(queue.queue)
        elif mode == TrackRepeat.all:
            queue.queue = TrackQueueAll.from_other(queue.queue)
        elif mode == TrackRepeat.disable:
            queue.queue = TrackQueueImpl.from_other(queue.queue)
        self._active_guilds[self._get_id(vc)] = queue
        return queue

    def get_requirements(self, vc: Player) -> int:
        in_voice = vc.channel.members
        # 40% need to vote to skip.
        required = ceil(len(in_voice) * 0.4)
        return required

    def generate_track_embed(self, entry: TrackEntry, position: int = MISSING) -> Embed:
        embed = Embed(colour=Colour.from_rgb(78, 214, 139), timestamp=arrow.utcnow().datetime)
        embed.set_author(name="Diputar 🎵", icon_url=self._client.user.avatar)
        description = []
        track = entry.track
        track_url = track.uri
        if hasattr(track, "internal_id") and getattr(track, "source", None) == "spotify":
            track_url = f"https://open.spotify.com/track/{track.internal_id}"
        elif hasattr(track, "internal_id") and getattr(track, "source", None) == "tidal":
            track_url = f"https://tidal.com/track/{track.internal_id}"
        description.append(f"[{track.title}]({track_url})")
        if track.author:
            description.append(f"**Artis**: {track.author}")
        if hasattr(track, "description") and track.description:
            description.append(f"\n{track.description}")
        embed.description = "\n".join(description)

        embed.add_field(name="Diputar oleh", value=f"{entry.requester.mention}", inline=True)
        durasi = TimeString.from_seconds(int(ceil(track.duration)))
        if position is MISSING:
            embed.add_field(name="Durasi", value=durasi.to_string(), inline=True)
        else:
            posisi = format_duration(position)
            durasi = format_duration(track.duration)
            embed.add_field(name="Durasi", value=f"{posisi}/{durasi}", inline=True)
        internal_thumb = getattr(track, "_int_thumbnail", None)
        if internal_thumb:
            embed.set_thumbnail(url=internal_thumb)
        elif isinstance(track, YouTubeTrack):
            embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{track.identifier}/maxresdefault.jpg")
        return embed

    async def _fetch_track_queue(self, player: Player):
        """Fetch a track from the queue"""
        try:
            queue = self.get(player)
            return await queue.queue.get()
        except asyncio.CancelledError:
            return None

    async def search_track(self, query: str, node: wavelink.Node):
        if query.startswith("http"):
            if "spotify.com" in query:
                track_mode = spotify.SpotifySearchType.track
                if "/album" in query:
                    track_mode = spotify.SpotifySearchType.album
                elif "/playlist" in query:
                    track_mode = spotify.SpotifySearchType.playlist
                spoti_results = await SpotifyDirectTrack.search(
                    query, type=track_mode, node=node, spotify=self._spotify, return_first=False
                )
                return spoti_results
            elif "soundcloud.com" in query:
                soundcloud_tracks = await SoundcloudDirectLink.search(query, node=node)
                return soundcloud_tracks
            elif "bandcamp.com" in query:
                bandcamp_tracks = await BandcampDirectLink.search(query, node=node)
                return bandcamp_tracks
            elif "vimeo.com" in query:
                raise UnsupportedURLFormat(query, "Vimeo tidak didukung untuk sekarang!")
            elif "twitch.tv" in query:
                ttv_results = await TwitchDirectLink.search(query, node=node, return_first=True)
                return ttv_results
            elif "tidal.com" in query:
                tidal_results = await TidalDirectLink.search(query, node=node)
                return tidal_results
            else:
                return_first = "/playlist" not in query
                results = await YoutubeDirectLinkTrack.search(
                    query,
                    node=node,
                    return_first=return_first,
                )
                return results
        results = await YouTubeTrack.search(query, node=node, return_first=False)
        for result in results:
            setattr(result, "source", "youtube")
        return results

    # Listeners
    # Call to this function later :)
    async def play_next(self, player: Player):
        self._set_current(player, None)

        # Try to get new track.
        try:
            self.logger.info(f"Player: <{player.guild}> trying to enqueue new track... (5 minutes timeout)")
            new_track = await asyncio.wait_for(self._fetch_track_queue(player), timeout=300)
        except asyncio.TimeoutError:
            # No more tracks, clear queue and stop player.
            self.logger.info(f"Player: <{player.guild}> no more tracks, clearing queue and stopping player.")
            self.delete(player)
            await player.disconnect(force=True)
            return

        if new_track is None:
            self.logger.info(f"Player: <{player.guild}> no more tracks, clearing queue and stopping player.")
            self._client.dispatch("naotimes_music_timeout", player)
            self.delete(player)
            await player.disconnect(force=True)
            return

        self.reset_vote(player)

        self.logger.info(f"Player: <{player.guild}> got new track: {new_track.track}")
        self._set_current(player, new_track)
        try:
            await player.play(new_track.track)
        except Exception as e:
            # Dispatch failed to play event
            self._client.dispatch("naotimes_playback_failed", player, new_track, e)
            return
        wrapped_entry = TrackEntry(player.source, new_track.requester, new_track.channel)
        self._set_current(player, wrapped_entry)
