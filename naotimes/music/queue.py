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

import asyncio
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, List, MutableSet, Optional, Type, TypeVar, Union

from discord.channel import StageChannel, TextChannel, VoiceChannel
from discord.member import Member
from wavelink.tracks import Track

from .track import SpotifyDirectTrack

__all__ = (
    "TrackRepeat",
    "TrackEntry",
    "TrackQueueImpl",
    "TrackQueueSingle",
    "TrackQueueAll",
    "GuildMusicInstance",
)

NT = TypeVar("NT", bound="TrackEntry")
VocalChannel = Union[VoiceChannel, StageChannel]


class TrackRepeat(Enum):
    disable = 0
    single = 1
    all = 2

    @property
    def nice(self):
        mapping_tl = {"disable": "Mati", "single": "Satu lagu", "all": "Semua lagu"}
        return mapping_tl.get(self.name.lower(), self.name)


@dataclass
class TrackEntry:
    track: Union[Track, SpotifyDirectTrack]
    requester: Member
    channel: TextChannel


class TrackQueueImpl(asyncio.Queue[NT]):

    _maxsize: int
    _original_queue: Deque[NT]

    def _init(self, maxsize: int):
        self._maxsize = maxsize
        self._queue = deque[NT]()

    def clear(self):
        self._queue.clear()
        if hasattr(self, "_original_queue"):
            self._original_queue.clear()

    @staticmethod
    def _process_list(items: Union[List[NT], Deque[NT]]) -> List[NT]:
        return list(items)

    @classmethod
    def from_other(cls: Type[TrackQueueImpl], other: TrackQueueImpl) -> TrackQueueImpl:
        new_queue = cls(maxsize=other._maxsize)
        other_queue = getattr(other, "_original_queue", getattr(other, "_queue"))
        if isinstance(other_queue, list):
            # Use normal list
            new_queue._queue = cls._process_list(other_queue)
        else:
            new_queue._queue = deque(other_queue)

        if hasattr(new_queue, "_original_queue"):
            new_queue._original_queue = deque(other_queue)

        return new_queue

    def qsize(self) -> int:
        if hasattr(self, "_original_queue"):
            return len(self._original_queue)
        return super().qsize()


class TrackQueueSingle(TrackQueueImpl[NT]):

    _queue: List[NT]
    _original_queue: Deque[NT]

    def _init(self, maxsize: int):
        self._maxsize = maxsize
        self._queue = []
        self._original_queue = deque[NT]()

    def _put(self, item: NT):
        self._original_queue.append(item)

    def _get(self):
        return self._queue[0]

    @staticmethod
    def _process_list(items: Union[List[NT], Deque[NT]]) -> Optional[NT]:
        as_list = list(items)
        try:
            return as_list[0]
        except IndexError:
            return None


class TrackQueueAll(TrackQueueImpl[NT]):

    _queue: Deque[NT]

    def _init(self, maxsize: int):
        self._maxsize = maxsize
        self._queue = deque[NT]()

    def _put(self, item: NT):
        self._queue.append(item)

    def _get(self):
        pop_first = self._queue.popleft()
        self._put(pop_first)
        return pop_first


@dataclass
class GuildMusicInstance:
    queue: TrackQueueImpl[TrackEntry]
    repeat: TrackRepeat = TrackRepeat.disable
    current: Optional[TrackEntry] = None

    # votes related stuff
    skip_votes: MutableSet[int] = field(default_factory=set)
    host: Optional[Member] = None
    channel: Optional[VocalChannel] = None
