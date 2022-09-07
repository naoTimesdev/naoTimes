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

from wavelink import NodePool, Track

from .util import MISSING, parse_playlists

if TYPE_CHECKING:
    from wavelink import Node

__all__ = ("SoundcloudDirectLink",)


class SoundcloudDirectLink(Track):
    """A track that implements a direct link fetch of Soundcloud"""

    _int_thumbnail: str
    source: Literal["soundcloud"] = "soundcloud"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)

        replace_url = info["uri"].replace("https://", "").replace("http://", "")
        find_first_slash = replace_url.find("/")
        replace_url = replace_url[find_first_slash:]

        self._int_thumbnail = f"https://naotimes-og.glitch.me/soundcloud{replace_url}"
        self.source = "soundcloud"

    @classmethod
    async def search(
        cls: Type[SoundcloudDirectLink], query: str, *, node: Node = MISSING, return_first: bool = False
    ) -> Union[SoundcloudDirectLink, List[SoundcloudDirectLink]]:
        """Search for a track on Soundcloud"""

        if node is MISSING:
            node = NodePool.get_node()

        is_playlist = False
        if "/sets/" in query:
            is_playlist = True

        if is_playlist:
            playlists_data = []
            playlist_append = lambda x: playlists_data.extend(parse_playlists(x))  # noqa: E731

            await node.get_playlist(playlist_append, query)
            parsed_tracks = [cls(track["track"], track["info"]) for track in playlists_data]
            if return_first:
                parsed_tracks[0]
            return parsed_tracks

        tracks = await node.get_tracks(cls, query)
        if return_first:
            return tracks[0]
        return tracks
