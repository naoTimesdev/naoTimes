"""
MIT License

Copyright (c) 2019-2021 naoTimesdev

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

from .util import MISSING

if TYPE_CHECKING:
    from wavelink import Node


__all__ = ("TwitchDirectLink",)


class TwitchDirectLink(Track):
    """A track that implements a direct link fetch of Twitch.tv stream"""

    _int_thumbnail: str
    source: Literal["twitch"] = "twitch"

    def __init__(self, id: str, info: dict):
        super().__init__(id, info)
        self.source = "twitch"

    @classmethod
    async def search(
        cls: Type[TwitchDirectLink], query: str, *, node: Node = MISSING, return_first: bool = False
    ) -> Union[TwitchDirectLink, List[TwitchDirectLink]]:
        """Search for a track on YouTube"""

        if node is MISSING:
            node = NodePool.get_node()

        tracks = await node.get_tracks(cls, query)
        for track in tracks:
            author = track.author
            setattr(track, "_int_thumbnail", f"https://ttvthumb.glitch.me/{author}")
        if return_first:
            return tracks[0]
        return tracks
