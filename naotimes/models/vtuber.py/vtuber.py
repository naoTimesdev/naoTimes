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

from typing import List, Literal, Optional

from naotimes.utils import AttributeDict

__all__ = ("VTuberLives", "VTuberSchedules", "VTuberChannels")

_VTuberStatus = Literal["live", "upcoming", "past", "video"]
_VTuberPlatform = Literal["youtube", "twitch", "bilibili", "mildom", "twitcasting"]


class _VTuberPageInfo(AttributeDict):
    hasNextPage: bool
    nextCursor: Optional[str]


class _VTuberCommon(AttributeDict):
    _total: int
    pageInfo: _VTuberPageInfo


class _VTuberChannelLiveCommon(AttributeDict):
    id: str
    en_name: str
    room_id: Optional[int]
    name: str
    image: str


class _VTuberLiveTime(AttributeDict):
    startTime: int


class _VTuberItemCommon(AttributeDict):
    id: str
    title: str
    status: _VTuberStatus
    channel: _VTuberChannelLiveCommon
    thumbnail: str
    platform: _VTuberPlatform
    is_premiere: bool
    is_member: bool
    group: str


class _VTuberLiveItems(_VTuberItemCommon):
    viewers: int
    timeData: _VTuberLiveTime


class VTuberLives(_VTuberCommon):
    items: List[_VTuberLiveItems]


VTuberLiveItems = List[_VTuberLiveItems]


class _VTuberScheduleTime(_VTuberLiveTime):
    scheduledStartTime: int


class _VTuberScheduleItems(_VTuberItemCommon):
    timeData: _VTuberScheduleTime
    viewers: Optional[int]


class VTuberSchedules(_VTuberCommon):
    items: List[_VTuberScheduleItems]


VTuberScheduleItems = List[_VTuberScheduleItems]


class _VTuberChannelStatsItems(AttributeDict):
    subscriberCount: int
    viewCount: Optional[int]


class _VTuberChannelItems(_VTuberChannelLiveCommon):
    group: str
    platform: _VTuberPlatform
    publishedAt: Optional[str]
    statistics: _VTuberChannelStatsItems


class VTuberChannels(_VTuberCommon):
    items: List[_VTuberChannelItems]


VTuberChannelItems = List[_VTuberChannelItems]
