import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import wavelink
from aiohttp.web import Request, Response, json_response
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.http.server import delete, get, post
from naotimes.music.tracks import SingleTrackResult


class PlaylistOwner(Enum):
    user = 1
    guild = 2


class PlaylistVisibility(Enum):
    # Only available to user or guild
    private = 1
    # Available to other guild members
    public = 2
    # Available to everyone that have access to naoTimes
    globally = 3


@dataclass
class PlaylistMusic:
    title: str
    artist: str
    source: str
    url: str
    thumbnail: Optional[str] = None

    @classmethod
    def from_db(self, data: dict):
        thumbnail = data.get("thumbnail")
        return PlaylistMusic(data["title"], data["artist"], data["source"], data["url"], thumbnail)

    @classmethod
    def from_lavalink(self, track: SingleTrackResult):
        track_url = track.uri
        track_source = getattr(track, "source", "unknown")
        if hasattr(track, "internal_id"):
            if track_source == "tidal":
                track_url = f"https://tidal.com/track/{track.internal_id}"
            elif track_source == "deezer":
                track_url = f"https://www.deezer.com/track/{track.internal_id}"
            elif track_source == "spotify":
                track_url = f"https://open.spotify.com/track/{track.internal_id}"

        internal_thumbanil = getattr(track, "_int_thumbnail", None)
        if isinstance(track, wavelink.YouTubeTrack) and internal_thumbanil is None:
            internal_thumbanil = f"https://i.ytimg.com/vi/{track.identifier}/maxresdefault.jpg"
        return PlaylistMusic(
            track.title or "Unknown Title",
            track.author or "Unknown Artist",
            track_source,
            track_url,
            internal_thumbanil,
        )

    def to_dict(self):
        return {
            "title": self.title,
            "artist": self.artist,
            "source": self.source,
            "url": self.url,
            "thumbnail": self.thumbnail,
        }


@dataclass
class Playlist:
    id: str
    name: str
    tracks: List[PlaylistMusic]
    owner: PlaylistOwner
    owner_id: str
    visibility: PlaylistVisibility

    @classmethod
    def from_db(self, data: dict):
        tracks: List[PlaylistMusic] = []
        for track in data.get("tracks", []):
            tracks.append(PlaylistMusic.from_db(track))
        return Playlist(
            id=data["id"],
            name=data["name"],
            tracks=tracks,
            owner=PlaylistOwner(data["owner"]),
            owner_id=data["owner_id"],
            visibility=PlaylistVisibility(data["visibility"]),
        )

    def to_json(self):
        return {
            "id": self.id,
            "name": self.name,
            "tracks": self.tracks,
            "owner": self.owner.value,
            "owner_id": self.owner_id,
            "visibility": self.visibility.value,
        }


@dataclass
class PlaylistEditRequest:
    id: str
    playlist_id: str
    editable_by: List[str]
    is_new_playlist: bool = False

    @classmethod
    def from_json(cls, data: dict):
        return PlaylistEditRequest(data["id"], data["playlist_id"], data["editable_by"], data["shiny"])

    def to_json(self):
        return {
            "id": self.id,
            "playlist_id": self.playlist_id,
            "editable_by": self.editable_by,
            "shiny": self.is_new_playlist,
        }


class MusikPlayerPlaylistAPI(commands.Cog):
    http_route_prefix = "/api/v1/musik/playlist"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("MusicP.PlaylistAPI")

        self.db = bot.redisdb

    @get("/{code}")
    async def musik_api_playlist_get(self, request: Request):
        code_match: str = request.match_info["code"]
        if code_match == "":
            return json_response({"error": "No code provided"}, status=400)

        self.logger.info(f"PlaylistFetch: Requested playlist with temporary code {code_match}")
        playlist_temp = await self.db.get(f"ntplayer_playlist_temp_{code_match}")
        if playlist_temp is None:
            return json_response({"error": "No playlist found"}, status=404)

        parsed_temp = PlaylistEditRequest.from_json(playlist_temp)
        playlist_data = await self.db.get(f"ntplayer_playlist_{parsed_temp.playlist_id}")
        if playlist_data is None:
            await self.db.rm(f"ntplayer_playlist_temp_{code_match}")
            return json_response({"error": "Associated playlist is gone"}, status=404)

        playlist = Playlist.from_db(playlist_data)
        return json_response({"playlist": playlist.to_json(), "code": code_match})

    @delete("/{code}/", with_auth=True)
    async def musik_api_playlist_delete(self, request: Request):
        code_match: str = request.match_info["code"]
        if code_match == "":
            return json_response({"error": "No code provided"}, status=400)

        self.logger.info(f"PlaylistFetch: Requested playlist with temporary code {code_match}")
        playlist_temp = await self.db.get(f"ntplayer_playlist_temp_{code_match}")
        if playlist_temp is None:
            return json_response({"error": "No playlist found"}, status=404)

        parsed_temp = PlaylistEditRequest.from_json(playlist_temp)
        playlist_data = await self.db.get(f"ntplayer_playlist_{parsed_temp.playlist_id}")
        if playlist_data is None:
            await self.db.rm(f"ntplayer_playlist_temp_{code_match}")
            return json_response({"error": "Associated playlist is gone"}, status=404)

        if not parsed_temp.is_new_playlist:
            await self.db.rm(f"ntplayer_playlist_{parsed_temp.playlist_id}")
            await self.db.rm(f"ntplayer_playlist_temp_{code_match}")
            return json_response({"success": True})

        return json_response({"error": "Cannot delete existing playlist from the API"}, status=409)

    @post("/{code}/update")
    async def musik_api_playlist_update(self, request: Request):
        code_match: str = request.match_info["code"]
        if code_match == "":
            return json_response({"error": "No code provided"}, status=400)
        if request.headers.get("content-type", "") != "application/json":
            return json_response({"error": "Content-Type must be application/json"}, status=400)

        self.logger.info(f"PlaylistUpdate: Requested playlist update with temporary code {code_match}")
        content_update = await request.json()
        if "tracks" not in content_update and "name" not in content_update:
            return json_response({"error": "No tracks or name update provided"}, status=400)

        tracks_update = content_update.get("tracks", [])
        parsed_tracks: List[PlaylistMusic] = []
        for track in tracks_update:
            parsed_tracks.append(PlaylistMusic.from_db(track))

        name_update = content_update.get("name")

        self.logger.info(f"PlaylistFetch: Requested playlist with temporary code {code_match}")
        playlist_temp = await self.db.get(f"ntplayer_playlist_temp_{code_match}")
        if playlist_temp is None:
            return json_response({"error": "No playlist found"}, status=404)

        parsed_temp = PlaylistEditRequest.from_json(playlist_temp)
        playlist_data = await self.db.get(f"ntplayer_playlist_{parsed_temp.playlist_id}")
        if playlist_data is None:
            await self.db.rm(f"ntplayer_playlist_temp_{code_match}")
            return json_response({"error": "Associated playlist is gone"}, status=404)

        playlist = Playlist.from_db(playlist_data)
        if name_update is not None:
            playlist.name = name_update
        if parsed_tracks:
            playlist.tracks = parsed_tracks

        await self.db.set(f"ntplayer_playlist_{playlist.id}", playlist.to_json())
        await self.db.rm(f"ntplayer_playlist_temp_{code_match}")
        return Response(status=201)

    @post("/findtracks", with_auth=True)
    async def musik_api_playlist_find_tracks(self, request: Request):
        if request.headers.get("content-type", "") != "application/json":
            return json_response({"error": "Content-Type must be application/json"}, status=400)

        self.logger.info("PlaylistFetchTrack: Requested track update information")
        content_request = await request.json()
        if "q" not in content_request:
            return json_response({"error": "No query provided"}, status=400)

        query = content_request["q"]
        self.logger.info(f"PlaylistFetchTrack: Searching for tracks with query {query} to lavalink")
        random_node = wavelink.NodePool.get_node()
        fetch_results = await self.bot.ntplayer.search_track(query, random_node)
        if not isinstance(fetch_results, list):
            fetch_results = [fetch_results]

        self.logger.info(f"PlaylistFetchTrack: Found {len(fetch_results)} tracks")
        parsed_tracks: List[dict] = []
        for track in fetch_results:
            parsed_tracks.append(PlaylistMusic.from_lavalink(track).to_dict())

        if not parsed_tracks:
            return json_response({"tracks": []}, status=404)

        return json_response({"tracks": parsed_tracks})


def setup(bot: naoTimesBot):
    bot.add_cog(MusikPlayerPlaylistAPI(bot))
