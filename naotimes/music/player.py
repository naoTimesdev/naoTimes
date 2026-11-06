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
import re
from math import ceil
from typing import TYPE_CHECKING, Union

import arrow
import wavelink
import yarl
from discord.channel import StageChannel, VoiceChannel
from discord.colour import Colour
from discord.embeds import Embed
from wavelink import Playable, Player

from naotimes.timeparse import TimeString

from .errors import SpotifyNoTrackFound, SpotifyUnavailable, UnsupportedURLFormat
from .queue import (
    GuildMusicInstance,
    TrackEntry,
    TrackQueueAll,
    TrackQueueImpl,
    TrackQueueSingle,
    TrackRepeat,
)

if TYPE_CHECKING:
    from discord.guild import Guild
    from discord.member import Member

    from naotimes.bot import naoTimesBot
    from naotimes.config import naoTimesLavanodes, naoTimesLavaSpotifyNode


__all__ = (
    "format_duration",
    "naoTimesPlayer",
)


class MissingValue:
    __slots__ = ()


MISSING = MissingValue()
VocalChannel = Union[VoiceChannel, StageChannel]


def format_duration(duration: float):
    hours = duration // 3600
    duration = duration % 3600
    minutes = duration // 60
    seconds = duration % 60

    minutes = str(round(minutes)).zfill(2)
    seconds = str(round(seconds)).zfill(2)
    if hours >= 1:
        hours = str(round(hours)).zfill(2)
        return f"{hours}:{minutes}:{seconds}"
    return f"{minutes}:{seconds}"


_SPOTIFY_ENTITIES = ("track", "album", "playlist", "episode", "show", "artist")
_SPOTIFY_URI = re.compile(r"^spotify:(?P<entity>[a-z]+):(?P<identifier>[A-Za-z0-9]+)$")
# Accept optional locale prefix: /intl-id/track/<id>
_SPOTIFY_PATH = re.compile(r"^/(?:intl-[a-zA-Z-]+/)?(?P<entity>[a-z]+)/(?P<identifier>[A-Za-z0-9]+)/?$")


class naoTimesPlayer:
    def __init__(
        self,
        client: naoTimesBot,
        loop: asyncio.AbstractEventLoop | None = None,
        spotify: naoTimesLavaSpotifyNode | None = None,
    ):
        self.logger = logging.getLogger("naoTimes.MusicPlayer")
        # Spotify links are rewritten to the HTTP bridge, which Lavalink then loads.
        self._spotify = spotify
        self._active_guilds: dict[int, GuildMusicInstance] = {}
        self._client = client
        self._loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()

        # Active tracked nodes
        self._tracked_nodes: set[str] = set()

    def __del__(self):
        self._loop.create_task(self.close(), name="naotimes-player-close-all-players")

    @property
    def actives(self):
        return self._active_guilds

    @property
    def tracked_nodes(self) -> set[str]:
        return self._tracked_nodes

    def track_node(self, identifier: str) -> None:
        self._tracked_nodes.add(identifier)

    def untrack_node(self, identifier: str) -> None:
        try:
            self._tracked_nodes.remove(identifier)
        except KeyError:
            pass  # ignore

    async def close(self):
        self.logger.info("Closing all instances...")
        channel_ids = [instance.channel.id for instance in self._active_guilds.values() if instance.channel]
        for vc_instance in self._client.voice_clients:
            if not isinstance(vc_instance, Player):
                continue
            if vc_instance.channel.id in channel_ids:
                await vc_instance.disconnect()
        self.logger.info("Disconnecting nodes...")
        await wavelink.Pool.close()

    async def add_node(self, node: naoTimesLavanodes):
        if node.identifier in wavelink.Pool.nodes:
            self.logger.warning(f"Node <{node.identifier}> is already registered.")
            return
        self.logger.info(f"Trying to connect with node <{node.identifier}>...")
        wl_node = wavelink.Node(
            identifier=node.identifier,
            uri=f"http://{node.host}:{node.port}",
            password=node.password,
            inactive_player_timeout=None,
        )
        try:
            await wavelink.Pool.connect(nodes=[wl_node], client=self._client)
            self.track_node(node.identifier)
        except Exception as exc:
            self.logger.error(f"Failed to connect with node <{node.identifier}>", exc_info=exc)

    async def remove_node(self, identifier: str):
        node = wavelink.Pool.nodes.get(identifier)
        if node is None:
            self.logger.warning(f"Node <{identifier}> is not registered.")
            return
        await node.close()
        self.untrack_node(identifier)

    def _get_id(self, vc: Player | Guild) -> int:
        if isinstance(vc, Player):
            guild = vc.guild
            if guild is None:
                raise ValueError("Music player is not connected to a guild")
            return guild.id
        return vc.id

    def create(self, vc: Guild | Player):
        guild_id = self._get_id(vc)
        if guild_id not in self._active_guilds:
            track_queue = TrackQueueImpl()
            self._active_guilds[guild_id] = GuildMusicInstance(track_queue)

    def has(self, vc: Player | Guild) -> bool:
        if isinstance(vc, Player):
            guild = vc.guild
            return guild is not None and guild.id in self._active_guilds
        return vc.id in self._active_guilds

    def get(self, vc: Guild | Player) -> GuildMusicInstance:
        self.create(vc)
        return self._active_guilds[self._get_id(vc)]

    def set(self, vc: Guild | Player, instance: GuildMusicInstance):
        self._active_guilds[self._get_id(vc)] = instance

    def get_tracks(self, vc: Player | Guild) -> list[TrackEntry]:
        all_tracks: list[TrackEntry] = []
        for track in self.get(vc).queue._queue:
            all_tracks.append(track)
        return all_tracks

    def delete(self, vc: Player | Guild):
        if self.has(vc):
            del self._active_guilds[self._get_id(vc)]

    def delete_track(self, vc: Player | Guild, index: int):
        try:
            queue = self.get(vc)
            if queue.repeat == TrackRepeat.single:
                return True
            self.logger.info(f"Player: Trying to remove track [{index}] at <{self._get_id(vc)}>")
            del queue.queue._queue[index]
            return True
        except Exception as e:
            self.logger.error(f"Player: Failed to remove track [{index}] at <{self._get_id(vc)}>", exc_info=e)
            return False

    def clear(self, vc: Player | Guild):
        guild_id = self._get_id(vc)
        self._active_guilds[guild_id].queue.clear()

    async def enqueue(self, vc: Player, entries: TrackEntry | list[TrackEntry]):
        if not isinstance(entries, list):
            entries = [entries]
        queue = self.get(vc)
        guild_id = self._get_id(vc)
        for entry in entries:
            track = entry.track
            self.logger.info(f"Player: Enqueueing at guild <{guild_id}>: {track.title} by {track.author}")
            await queue.queue.put(entry)
        self._active_guilds[guild_id] = queue

    def _set_current(self, vc: Player, track: TrackEntry | None = None) -> None:
        self.get(vc).current = track

    def change_dj(self, vc: Player, user: Member | None):
        self.get(vc).host = user

    def set_channel(self, vc: Player, channel: VocalChannel):
        self.get(vc).channel = channel

    def reset_vote(self, vc: Player):
        instance = self.get(vc)
        instance.skip_votes.clear()
        self.set(vc, instance)

    def add_vote(self, vc: Player, user: Member):
        self.get(vc).skip_votes.add(user.id)

    def change_repeat_mode(self, vc: Player, mode: TrackRepeat) -> GuildMusicInstance | None:
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

    def generate_track_embed(self, entry: TrackEntry, position: int | MissingValue = MISSING) -> Embed:
        embed = Embed(colour=Colour.from_rgb(78, 214, 139), timestamp=arrow.utcnow().datetime)
        client_user = self._client.user
        embed.set_author(name="Diputar 🎵", icon_url=client_user.display_avatar.url if client_user else None)
        description = []
        track = entry.track
        track_url = track.uri or ""
        description.append(f"[{track.title}]({track_url})")
        if track.author:
            description.append(f"**Artis**: {track.author}")
        embed.description = "\n".join(description)

        embed.add_field(name="Diputar oleh", value=f"{entry.requester.mention}", inline=True)
        durasi = TimeString.from_seconds(ceil(track.length / 1000))
        if isinstance(position, MissingValue):
            embed.add_field(name="Durasi", value=durasi.to_string(), inline=True)
        else:
            posisi = format_duration(position / 1000)
            durasi = format_duration(track.length / 1000)
            embed.add_field(name="Durasi", value=f"{posisi}/{durasi}", inline=True)
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        return embed

    async def _fetch_track_queue(self, player: Player):
        """Fetch a track from the queue"""
        try:
            queue = self.get(player)
            return await queue.queue.get()
        except asyncio.CancelledError:
            return None

    @property
    def spotify_enabled(self) -> bool:
        return self._spotify is not None

    def _rewrite_spotify(self, query: str) -> str | None:
        """Rewrite a Spotify link/URI to the bridge URL: ``<bridge>/<entity>/<id>``.

        Returns ``None`` when the query is not a Spotify link.
        """
        match = _SPOTIFY_URI.match(query)
        if match is None:
            try:
                parsed = yarl.URL(query)
            except ValueError:
                return None
            host = parsed.host or ""
            if host == "spotify.link":
                raise UnsupportedURLFormat(query, "Link pendek spotify.link tidak didukung, pakai link lengkap!")
            if not (host == "spotify.com" or host.endswith(".spotify.com")):
                return None
            match = _SPOTIFY_PATH.match(parsed.path)
            if match is None:
                raise UnsupportedURLFormat(query, "Link Spotify yang diberikan tidak valid!")
        if self._spotify is None:
            raise SpotifyUnavailable(query)
        entity = match["entity"]
        if entity not in _SPOTIFY_ENTITIES:
            raise UnsupportedURLFormat(query, "Tipe URL Spotify tersebut tidak dapat disupport!")
        return f"{self._spotify.url}/{entity}/{match['identifier']}"

    async def search_track(self, query: str, node: wavelink.Node | None = None) -> list[Playable]:
        """Search tracks.

        - Spotify links are rewritten to the bridge URL (``<bridge>/<entity>/<id>``) and loaded by Lavalink.
        - Other URLs are resolved by Lavalink, plain text searches YouTube.
        """
        bridge_url = self._rewrite_spotify(query)
        try:
            if bridge_url is not None:
                results = await Playable.search(bridge_url, node=node)
            elif query.startswith("http"):
                results = await Playable.search(query, node=node)
            else:
                results = await Playable.search(query, source=wavelink.TrackSource.YouTube, node=node)
        except wavelink.LavalinkLoadException as exc:
            if bridge_url is not None:
                self.logger.warning(f"Spotify bridge failed to load <{bridge_url}>: {exc}")
                raise SpotifyNoTrackFound(query) from exc
            raise
        if isinstance(results, wavelink.Playlist):
            return list(results.tracks)
        return list(results)

    # Listeners
    # Call to this function later :)
    async def play_next(self, player: Player):
        self._set_current(player, None)

        # Wait for queue to be ready
        self.logger.info(f"Player: <{player.guild}> is waiting for queue to be ready")
        await self.get(player).wait_unfreeze()
        # Try to get new track.
        try:
            self.logger.info(f"Player: <{player.guild}> trying to enqueue new track... (5 minutes timeout)")
            new_track = await asyncio.wait_for(self._fetch_track_queue(player), timeout=300)
        except TimeoutError:
            # No more tracks, clear queue and stop player.
            self.logger.info(f"Player: <{player.guild}> no more tracks, clearing queue and stopping player.")
            self.delete(player)
            await player.disconnect()
            return

        if new_track is None:
            self.logger.info(f"Player: <{player.guild}> no more tracks, clearing queue and stopping player.")
            self._client.dispatch("naotimes_music_timeout", player)
            self.delete(player)
            await player.disconnect()
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
