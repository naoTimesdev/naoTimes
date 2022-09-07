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

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Union

import arrow
import discord

__all__ = ("ModLog", "ModLogAction", "ModLogFeature", "ModLogSetting")


class ModLogAction(Enum):
    MEMBER_JOIN = 0
    MEMBER_LEAVE = 1
    MEMBER_UPDATE = 2
    MEMBER_BAN = 3
    MEMBER_UNBAN = 4
    MEMBER_KICK = 5
    MEMBER_SHADOWBAN = 6
    MEMBER_UNSHADOWBAN = 7
    MEMBER_TIMED_BAN = 8
    MEMBER_UNBAN_TIMED = 9
    MEMBER_TIMEOUT = 10
    MEMBER_UNTIMEOUT = 11
    CHANNEL_CREATE = 20
    CHANNEL_UPDATE = 21
    CHANNEL_DELETE = 22
    MESSAGE_EDIT = 30
    MESSAGE_DELETE = 31
    MESSAGE_DELETE_BULK = 32
    EVASION_BAN = 40
    EVASION_TIMEOUT = 41
    THREAD_CREATE = 50
    THREAD_REMOVE = 51
    THREAD_UPDATE = 52


PublicModLogActions = [
    ModLogAction.MEMBER_TIMED_BAN,
    ModLogAction.MEMBER_UNBAN_TIMED,
    ModLogAction.MEMBER_TIMEOUT,
    ModLogAction.MEMBER_UNTIMEOUT,
    ModLogAction.EVASION_TIMEOUT,
]


class ModLog:
    def __init__(
        self,
        action: ModLogAction,
        message: str = "",
        embed: discord.Embed = None,
        timestamp: Union[int, arrow.Arrow] = None,
    ) -> None:
        self._action = action
        self._message = message
        self._embed = embed
        if isinstance(timestamp, int):
            self._timestamp = timestamp
        elif isinstance(timestamp, arrow.Arrow):
            self._timestamp = timestamp.int_timestamp
        else:
            self._timestamp = arrow.utcnow().int_timestamp

    @property
    def public(self):
        """Is the log able to be shown into public or not?"""
        if self.action in PublicModLogActions:
            return True
        return False

    @property
    def action(self) -> ModLogAction:
        return self._action

    @property
    def timestamp(self) -> Optional[int]:
        return getattr(self, "_timestamp", None)

    @property
    def message(self) -> str:
        return getattr(self, "_message", "")

    @property
    def embed(self) -> Optional[discord.Embed]:
        return getattr(self, "_embed", None)

    @action.setter
    def action(self, action: ModLogAction):
        if isinstance(action, ModLogAction):
            self._action = action

    @message.setter
    def message(self, message: str):
        if isinstance(message, str) and len(message.strip()) > 0:
            self._message = message

    @timestamp.setter
    def timestamp(self, timestamp: Union[int, arrow.Arrow, None] = None):
        if isinstance(timestamp, int):
            self._timestamp = timestamp
        elif isinstance(timestamp, arrow.Arrow):
            self._timestamp = timestamp.int_timestamp
        else:
            self._timestamp = arrow.utcnow().int_timestamp

    @embed.setter
    def embed(self, embed: discord.Embed):
        if isinstance(embed, discord.Embed):
            self._embed = embed


class ModLogFeature(Enum):
    DELETE_MSG = 0
    EDIT_MSG = 1
    MEMBER_JOIN = 10
    MEMBER_LEAVE = 11
    MEMBER_BAN = 12
    MEMBER_UNBAN = 13
    MEMBER_UPDATE = 14
    CHANNEL_CREATE = 20
    CHANNEL_DELETE = 21
    NICK_MEMUPDATE = 30
    ROLE_MEMUPDATE = 31
    THREAD_CREATE = 40
    THREAD_UPDATE = 41
    THREAD_DELETE = 42

    @classmethod
    def all(cls) -> List["ModLogFeature"]:
        return [cls(val) for val in cls.__members__.values()]

    @classmethod
    def messages(cls) -> List["ModLogFeature"]:
        return [cls(val) for name, val in cls.__members__.items() if name.endswith("_MSG")]

    @classmethod
    def members(cls) -> List["ModLogFeature"]:
        member_data = [cls(val) for name, val in cls.__members__.items() if name.startswith("MEMBER_")]
        specific_data = [cls(val) for name, val in cls.__members__.items() if name.endswith("_MEMUPDATE")]
        return [*member_data, *specific_data]

    @classmethod
    def joinleave(cls) -> List["ModLogFeature"]:
        return [cls(10), cls(11)]

    @classmethod
    def bans(cls) -> List["ModLogFeature"]:
        return [
            cls(val)
            for name, val in cls.__members__.items()
            if name.endswith("BAN") and name.startswith("MEMBER_")
        ]

    @classmethod
    def channels(cls) -> List["ModLogFeature"]:
        return [cls(val) for name, val in cls.__members__.items() if name.startswith("CHANNEL_")]

    @classmethod
    def threads(cls) -> List["ModLogFeature"]:
        return [cls(val) for name, val in cls.__members__.items() if name.startswith("THREAD_")]


@dataclass
class ModLogSetting:
    guild: int
    channel: int
    public_channel: Optional[int] = None
    features: List[ModLogFeature] = field(default_factory=list)
    public_features: List[ModLogFeature] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict):
        guild_id = data["server_id"]
        channel_id = data["channel_id"]

        pub_channel_id = data.get("public_channel_id")

        feature_flags: List[ModLogFeature] = []
        for flag in data["features"]:
            feature_flags.append(ModLogFeature(flag))
        pub_feature_flags: List[ModLogFeature] = []
        for flag in data.get("public_features", []):
            pub_feature_flags.append(ModLogFeature(flag))

        return cls(guild_id, channel_id, pub_channel_id, feature_flags, pub_feature_flags)

    def serialize(self):
        base_serial = {
            "server_id": self.guild,
            "channel_id": self.channel,
            "public_channel_id": self.public_channel,
        }

        features = []
        for flag in self.features:
            features.append(flag.value)
        pub_features = []
        for flag in self.public_features:
            pub_features.append(flag.value)

        base_serial["features"] = features
        base_serial["public_features"] = pub_features
        return base_serial

    def has_features(self, features: Union[ModLogFeature, List[ModLogFeature]]):
        """Check if a list of features is enabled for this server"""
        if isinstance(features, ModLogFeature):
            features = [features]

        return all(feature in self.features for feature in features)

    def any_public_features(self):
        """Check if a list of features is enabled for this server"""
        return len(self.public_features) > 0

    def is_public_features(self, features: Union[ModLogFeature, List[ModLogFeature]]):
        """Check if a list of features is enabled for this server"""
        if isinstance(features, (ModLogFeature, ModLogAction)):
            features = [features]

        check_one = all(feature in self.public_features for feature in features)
        check_two = all(feature in PublicModLogActions for feature in features)

        return check_one or check_two
