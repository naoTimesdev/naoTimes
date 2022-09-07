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

from typing import TYPE_CHECKING, List, Literal, Type, Union

from wavelink import NodePool, YouTubeTrack

from .util import MISSING, parse_playlists

if TYPE_CHECKING:
    from wavelink import Node


__all__ = ("YoutubeDirectLinkTrack",)


class YoutubeDirectLinkTrack(YouTubeTrack):
    """A track that implements a direct search track"""

    _int_thumbnail: str
    source: Literal["youtube"] = "youtube"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.source = "youtube"

    @classmethod
    async def search(
        cls: Type[YoutubeDirectLinkTrack], query: str, *, node: Node = MISSING, return_first: bool = False
    ) -> Union[YoutubeDirectLinkTrack, List[YoutubeDirectLinkTrack]]:
        """Search for a track on YouTube"""

        if node is MISSING:
            node = NodePool.get_node()

        is_ytmusic = "music.youtube" in query.lower()

        is_playlist = False
        if "/playlist" in query:
            is_playlist = True

        if is_playlist:
            playlists_data = []
            playlist_append = lambda x: playlists_data.extend(parse_playlists(x))  # noqa: E731

            await node.get_playlist(playlist_append, query)
            parsed_tracks = [cls(track["track"], track["info"]) for track in playlists_data]
            for track in parsed_tracks:
                video_id = track.identifier
                if is_ytmusic:
                    setattr(track, "_int_thumbnail", f"https://naotimes-og.glitch.me/ytm/{video_id}")
                else:
                    setattr(track, "_int_thumbnail", f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
            if return_first:
                parsed_tracks[0]
            return parsed_tracks

        tracks = await node.get_tracks(cls, query)
        for track in tracks:
            video_id = track.identifier
            if is_ytmusic:
                setattr(track, "_int_thumbnail", f"https://naotimes-og.glitch.me/ytm/{video_id}")
            else:
                setattr(track, "_int_thumbnail", f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg")
        if return_first:
            return tracks[0]
        return tracks
