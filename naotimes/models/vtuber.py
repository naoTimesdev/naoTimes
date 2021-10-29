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
