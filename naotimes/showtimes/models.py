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
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, Union, overload

import arrow
import discord
from bson import ObjectId

from ..models import showtimes as showmodel
from ..t import MemberContext, T
from ..utils import get_indexed, time_struct_dt

__all__ = (
    "FansubRSS",
    "FansubRSSEmbed",
    "FansubRSSFeed",
    "FansubRSSPremium",
    "ShowAliases",
    "ShowKolaborasi",
    "ShowRoles",
    "ShowRolesEx",
    "ShowRolesUx",
    "Showtimes",
    "ShowtimesAdmin",
    "ShowtimesAssignee",
    "ShowtimesAssigneeCustom",
    "ShowtimesAssignment",
    "ShowtimesEpisodeStatus",
    "ShowtimesEpisodeStatusChild",
    "ShowtimesEpisodeStatusCustomChild",
    "ShowtimesFSDB",
    "ShowtimesKonfirmasi",
    "ShowtimesLock",
    "ShowtimesOwner",
    "ShowtimesPoster",
    "ShowtimesProject",
    "ShowtimesServer",
)

ShowtimesOwner = list[int]
ShowtimesServer = list[int]
ShowAliases = list[str]
ShowKolaborasi = list[int]
ShowRolesUx = Literal["TL", "TLC", "ENC", "ED", "TM", "TS", "QC"]
ShowRolesEx = Literal["tl", "tlc", "enc", "ed", "tm", "ts", "qc"]
ShowRoles = Union[ShowRolesUx, ShowRolesEx]
Looped = Generator[T]
DiscordUser = (discord.User, discord.Member)


def to_bool(data: Any) -> bool:
    quick_map = {
        "y": True,
        "yes": True,
        "1": True,
        1: True,
        "true": True,
        "n": False,
        "no": False,
        "0": False,
        0: False,
        "false": False,
    }
    if data is not None:
        if isinstance(data, str):
            data = data.lower()
            return quick_map.get(data, False)
        elif isinstance(data, int):
            if data > 0:
                return True
            return False
        elif isinstance(data, bool):
            return data
    return False


def _optional_string(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"Expected a string or None, got {type(value).__name__}")


class ShowtimesKonfirmasi:
    def __init__(self, id: str, server_id: int, anime_id: str):
        self._id = id
        self._server_id = server_id
        self._anime_id = anime_id

    def __repr__(self):
        return f'<ShowtimesKonfirmasi id="{self._id}" server={self._server_id} anime={self._anime_id}>'

    def __eq__(self, other: object):
        if isinstance(other, ShowtimesKonfirmasi):
            return self.id == other.id
        elif isinstance(other, str):
            return self.id == other
        return False

    @property
    def id(self) -> str:
        return self._id

    @id.setter
    def id(self, data: str) -> None:
        self._id = data

    @property
    def server(self) -> int:
        return self._server_id

    @server.setter
    def server(self, data: int) -> None:
        self._server_id = data

    @property
    def anime(self) -> str:
        return self._anime_id

    @anime.setter
    def anime(self, data: str) -> None:
        self._anime_id = data

    def copy(self) -> ShowtimesKonfirmasi:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(cls: type[ShowtimesKonfirmasi], data: showmodel.ShowtimesCollabConfirmDict) -> ShowtimesKonfirmasi:
        kode = data.get("id")
        if kode is None:
            raise ValueError("ShowtimesKonfirmasi: `id` is a required data")
        server_id = data.get("server_id")
        try:
            server = int(server_id)
        except ValueError:
            raise ValueError("ShowtimesKonfirmasi: `server_id` is not a number")
        anime_id = data.get("anime_id")
        if anime_id is None:
            raise ValueError("ShowtimesKonfirmasi: `anime_id` is a required data")
        return cls(kode, server, anime_id)

    def serialize(self) -> showmodel.ShowtimesCollabConfirmDict:
        return {"id": self.id, "server_id": str(self.server), "anime_id": self.anime}


class ShowtimesAssignee:
    def __init__(self, id: int | None = None, name: str | None = None):
        self._id = id
        self._name = name

    def __repr__(self):
        return f'<ShowtimesAssignee id={self._id} name="{self._name}">'

    def __eq__(self, other: object):
        if isinstance(other, ShowtimesAssignee):
            return self.id == other.id
        elif isinstance(other, (str, int)):
            return str(self.id) == str(other)
        return False

    @property
    def id(self) -> int | None:
        return self._id

    @id.setter
    def id(self, data: int | None) -> None:
        self._id = data

    @property
    def name(self) -> str | None:
        return self._name

    @name.setter
    def name(self, data: str | None) -> None:
        self._name = data

    def copy(self) -> ShowtimesAssignee:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(cls: type[ShowtimesAssignee], data: showmodel._ShowtimesProjectAssigneeDict) -> ShowtimesAssignee:
        id = data.get("id")
        try:
            user_id = int(id) if id is not None else None
        except ValueError:
            user_id = None
        name = data.get("name")
        return cls(user_id, name)

    def serialize(self) -> showmodel._ShowtimesProjectAssigneeDict:
        id_ = self.id
        if id_ is not None:
            id_ = str(id_)
        result: showmodel._ShowtimesProjectAssigneeDict = {"id": id_}
        if self.name is not None:
            result["name"] = self.name
        return result


class ShowtimesAssigneeCustom:
    def __init__(self, key: str, name: str, person: ShowtimesAssignee = ShowtimesAssignee()):
        self._key = key
        self._name = name
        self._person = person

    def __repr__(self):
        return f"<ShowtimesAssigneeCustom key={self._key!r} person={self._person!r}>"

    def __eq__(self, other: object):
        if isinstance(other, ShowtimesAssigneeCustom):
            return self.key == other.key
        elif isinstance(other, str):
            return self.key == other.upper() or self.name == other
        return False

    @property
    def key(self) -> str:
        return self._key.upper()

    @property
    def name(self) -> str:
        return self._name

    @property
    def person(self) -> ShowtimesAssignee:
        return self._person

    @person.setter
    def person(self, data: ShowtimesAssignee | MemberContext | str | int):
        if isinstance(data, ShowtimesAssignee):
            self._person = data
        elif isinstance(data, str):
            self._person.name = data
        elif isinstance(data, int):
            self._person.id = data
        elif isinstance(data, DiscordUser):
            self._person.id = data.id
            self._person.name = data.name

    def copy(self) -> ShowtimesAssigneeCustom:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(
        cls: type[ShowtimesAssigneeCustom],
        data: showmodel._ShowtimesProjectAssigneeCustomDict,
    ) -> ShowtimesAssigneeCustom:
        key = data.get("key")
        if key is None:
            raise ValueError("ShowtimesAssigneeCustom: `key` is a required data")
        name = data.get("name")
        if name is None:
            raise ValueError("ShowtimesAssigneeCustom: `name` is a required data")
        person = data.get("person")
        if person is None:
            raise ValueError("ShowtimesAssigneeCustom: `person` is a required data")
        person = ShowtimesAssignee.from_dict(person)
        return cls(key, name, person)

    def serialize(self) -> showmodel._ShowtimesProjectAssigneeCustomDict:
        return {
            "key": self.key,
            "name": self.name,
            "person": self.person.serialize(),
        }


class ShowtimesAssignment:
    def __init__(
        self,
        tlor: ShowtimesAssignee,
        tlcer: ShowtimesAssignee,
        encoder: ShowtimesAssignee,
        editor: ShowtimesAssignee,
        timer: ShowtimesAssignee,
        tser: ShowtimesAssignee,
        qcer: ShowtimesAssignee,
        custom: list[ShowtimesAssigneeCustom] = [],
    ) -> None:
        self._tlor = tlor
        self._tlcer = tlcer
        self._encoder = encoder
        self._editor = editor
        self._timer = timer
        self._tser = tser
        self._qcer = qcer
        self._custom = custom

    def __iter__(self) -> Looped[tuple[str, ShowtimesAssignee]]:
        serialized = self.serialize()
        for role in ("TL", "TLC", "ENC", "ED", "TM", "TS", "QC"):
            yield role, ShowtimesAssignee.from_dict(serialized[role])
        for custom in serialized["custom"]:
            yield custom["key"], ShowtimesAssignee.from_dict(custom["person"])

    def __repr__(self) -> str:
        serialized = self.serialize()
        roles = ("TL", "TLC", "ENC", "ED", "TM", "TS", "QC")
        assignments = [f"{role}={serialized[role]['id']}" for role in roles]
        assignments.extend(f"{custom['key']}={custom['person']['id']}" for custom in serialized["custom"])
        return f"<ShowtimesAssignment {' '.join(assignments)}>"

    def _set_assignee(self, attr: str, data: ShowtimesAssignee | MemberContext | str | int):
        expand_map = {
            "tl": "_tlor",
            "tlc": "_tlcer",
            "enc": "_encoder",
            "ed": "_editor",
            "tm": "_timer",
            "ts": "_tser",
            "qc": "_qcer",
        }
        mapping = expand_map.get(attr)
        if mapping is None:
            # Assume custom
            self.set_custom(attr, data)
            return
        if isinstance(data, ShowtimesAssignee):
            setattr(self, mapping, data)
        elif isinstance(data, str):
            mapped: ShowtimesAssignee | None = getattr(self, mapping, None)
            if mapped is None:
                mapped = ShowtimesAssignee(name=data)
            mapped.name = data
            setattr(self, mapping, mapped)
        elif isinstance(data, int):
            mapped: ShowtimesAssignee | None = getattr(self, mapping, None)
            if mapped is None:
                mapped = ShowtimesAssignee(id=data)
            mapped.id = data
            setattr(self, mapping, mapped)
        elif isinstance(data, DiscordUser):
            setattr(self, mapping, ShowtimesAssignee(id=data.id, name=data.name))

    @property
    def tlor(self) -> ShowtimesAssignee:
        return self._tlor

    @tlor.setter
    def tlor(self, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        self._set_assignee("tl", data)

    @property
    def tlcer(self) -> ShowtimesAssignee:
        return self._tlcer

    @tlcer.setter
    def tlcer(self, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        self._set_assignee("tlc", data)

    @property
    def encoder(self) -> ShowtimesAssignee:
        return self._encoder

    @encoder.setter
    def encoder(self, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        self._set_assignee("enc", data)

    @property
    def editor(self) -> ShowtimesAssignee:
        return self._editor

    @editor.setter
    def editor(self, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        self._set_assignee("ed", data)

    @property
    def timer(self) -> ShowtimesAssignee:
        return self._timer

    @timer.setter
    def timer(self, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        self._set_assignee("tm", data)

    @property
    def tser(self) -> ShowtimesAssignee:
        return self._tser

    @tser.setter
    def tser(self, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        self._set_assignee("ts", data)

    @property
    def qcer(self) -> ShowtimesAssignee:
        return self._qcer

    @qcer.setter
    def qcer(self, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        self._set_assignee("qc", data)

    @property
    def custom(self) -> list[ShowtimesAssigneeCustom]:
        return self._custom

    def is_custom(self, key: str) -> bool:
        return key.lower() not in ["tl", "tlc", "enc", "ed", "tm", "ts", "qc"]

    def set_custom(self, key: str, data: ShowtimesAssignee | MemberContext | str | int) -> None:
        if self.is_custom(key):
            for custom in self._custom:
                if custom == key:
                    if isinstance(data, ShowtimesAssignee):
                        custom.person = data
                    elif isinstance(data, str):
                        custom.person.name = data
                    elif isinstance(data, int):
                        custom.person.id = data
                    elif isinstance(data, DiscordUser):
                        custom.person.id = data.id
                        custom.person.name = data.name
                    return

    def get_custom(self, key: str) -> ShowtimesAssignee | None:
        if self.is_custom(key):
            for custom in self._custom:
                if custom == key:
                    return custom.person
        return None

    def get_custom_name(self, key: str) -> str | None:
        if self.is_custom(key):
            for custom in self._custom:
                if custom == key:
                    return custom.name
        return None

    def remove_custom(self, key: str) -> None:
        if self.is_custom(key):
            idx = -1
            for i, custom in enumerate(self._custom):
                if custom == key:
                    idx = i
                    break
            if idx >= 0:
                self._custom.pop(idx)

    def create_custom(self, key: str, name: str, value: ShowtimesAssignee | None = None) -> None:
        if self.is_custom(key):
            is_exist = self.get_custom(key)
            if is_exist is None:
                self._custom.append(ShowtimesAssigneeCustom(key, name, value or ShowtimesAssignee()))

    def copy(self) -> ShowtimesAssignment:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(
        cls: type[ShowtimesAssignment], data: showmodel._ShowtimesProjectAssignmentsDict
    ) -> ShowtimesAssignment:
        tlor = ShowtimesAssignee.from_dict(data.get("TL"))
        tlcer = ShowtimesAssignee.from_dict(data.get("TLC"))
        encoder = ShowtimesAssignee.from_dict(data.get("ENC"))
        editor = ShowtimesAssignee.from_dict(data.get("ED"))
        timer = ShowtimesAssignee.from_dict(data.get("TM"))
        tser = ShowtimesAssignee.from_dict(data.get("TS"))
        qcer = ShowtimesAssignee.from_dict(data.get("QC"))
        custom = [ShowtimesAssigneeCustom.from_dict(c) for c in data.get("custom", [])]
        return cls(tlor, tlcer, encoder, editor, timer, tser, qcer, custom)

    @classmethod
    def factory(cls: type[ShowtimesAssignment]) -> ShowtimesAssignment:
        return cls(
            ShowtimesAssignee(),
            ShowtimesAssignee(),
            ShowtimesAssignee(),
            ShowtimesAssignee(),
            ShowtimesAssignee(),
            ShowtimesAssignee(),
            ShowtimesAssignee(),
            [],
        )

    def serialize(self) -> showmodel._ShowtimesProjectAssignmentsDict:
        return {
            "TL": self._tlor.serialize(),
            "TLC": self._tlcer.serialize(),
            "ENC": self._encoder.serialize(),
            "ED": self._editor.serialize(),
            "TM": self._timer.serialize(),
            "TS": self._tser.serialize(),
            "QC": self._qcer.serialize(),
            "custom": [c.serialize() for c in self._custom],
        }

    def can_release(self, user: int | MemberContext) -> bool:
        """Check if said user can release or retract a release

        :param user: User to check
        :type user: Union[int, MemberContext]
        :return: u
        :rtype: [type]
        """
        if isinstance(user, DiscordUser):
            uuid = user.id
            return self._qcer.id == uuid
        elif isinstance(user, int):
            return user == self._qcer.id
        return False

    def can_toggle(self, role: str, user: int | MemberContext) -> bool:
        get_role = role.upper()
        serialized = self.serialize()
        if isinstance(user, DiscordUser):
            uuid = user.id
            if self.is_custom(get_role):
                return self.get_custom(get_role) == uuid
            return serialized[get_role]["id"] == str(uuid)
        elif isinstance(user, int):
            uuid = str(user)
            if self.is_custom(get_role):
                return self.get_custom(get_role) == uuid
            return serialized[get_role]["id"] == uuid
        return False

    def set(self, role: str, user: int | str | MemberContext | ShowtimesAssignee) -> None:
        self._set_assignee(role, user)


class ShowtimesEpisodeStatusCustomChild:
    def __init__(self, key: str, name: str, is_done: bool) -> None:
        self._key = key
        self._name = name
        self._is_done = is_done

    def __bool__(self):
        return self._is_done

    def __repr__(self) -> str:
        return f"<ShowtimesEpisodeStatusCustomChild {self._key}={self._is_done!r}>"

    def __eq__(self, target: object):
        if isinstance(target, ShowtimesEpisodeStatusCustomChild):
            return self.key == target.key
        elif isinstance(target, str):
            return self.key == target.upper() or self._name == target
        return False

    @property
    def key(self) -> str:
        return self._key.upper()

    @property
    def name(self) -> str:
        return self._name

    @property
    def done(self) -> bool:
        return self._is_done

    @done.setter
    def done(self, value: bool) -> None:
        self._is_done = value

    @classmethod
    def from_dict(
        cls, data: showmodel._ShowtimesProjectEpisodeStatusCustomProgressDict
    ) -> ShowtimesEpisodeStatusCustomChild:
        key = data["key"]
        name = data["name"]
        is_done = data.get("done", False)
        return cls(key, name, is_done)

    def serialize(self) -> showmodel._ShowtimesProjectEpisodeStatusCustomProgressDict:
        return {"key": self.key, "name": self._name, "done": self._is_done}

    def copy(self) -> ShowtimesEpisodeStatusCustomChild:
        return self.from_dict(self.serialize())


class ShowtimesEpisodeStatusChild:
    def __init__(
        self,
        tl: bool = False,
        tlc: bool = False,
        enc: bool = False,
        ed: bool = False,
        tm: bool = False,
        ts: bool = False,
        qc: bool = False,
        custom: list[ShowtimesEpisodeStatusCustomChild] = [],
    ):
        self._tl = tl
        self._tlc = tlc
        self._enc = enc
        self._ed = ed
        self._tm = tm
        self._ts = ts
        self._qc = qc
        self._custom = custom

    def __len__(self) -> int:
        return sum(1 for value in self.serialize().values() if value)

    def __bool__(self):
        return any(self.serialize().values())

    def __iter__(self) -> Looped[tuple[str, bool]]:
        serialized = self.serialize()
        for status in ("TL", "TLC", "ENC", "ED", "TM", "TS", "QC"):
            yield status, serialized[status]
        for child in serialized["custom"]:
            yield child["key"], child["done"]

    def __repr__(self) -> str:
        infotaiment = []
        for key, value in self.serialize().items():
            if key == "custom":
                continue
            infotaiment.append(f"{key}={'true' if value else 'false'}")
        custom_count = len(self._custom)
        if custom_count > 0:
            infotaiment.append(f"CustomRole={custom_count}")
        return f"<ShowtimesEpisodeStatusChild {' '.join(infotaiment)}>"

    @property
    def TL(self) -> bool:
        return self._tl

    @TL.setter
    def TL(self, data: bool) -> None:
        self._tl = to_bool(data)

    @property
    def TLC(self) -> bool:
        return self._tlc

    @TLC.setter
    def TLC(self, data: bool) -> None:
        self._tlc = to_bool(data)

    @property
    def Encode(self) -> bool:
        return self._enc

    @Encode.setter
    def Encode(self, data: bool) -> None:
        self._enc = to_bool(data)

    @property
    def Edit(self) -> bool:
        return self._ed

    @Edit.setter
    def Edit(self, data: bool):
        self._ed = to_bool(data)

    @property
    def Timing(self):
        return self._tm

    @Timing.setter
    def Timing(self, data: bool) -> None:
        self._tm = to_bool(data)

    @property
    def TS(self) -> bool:
        return self._ts

    @TS.setter
    def TS(self, data: bool) -> None:
        self._ts = to_bool(data)

    @property
    def QC(self) -> bool:
        return self._qc

    @QC.setter
    def QC(self, data: bool) -> None:
        self._qc = to_bool(data)

    @property
    def Custom(self) -> list[ShowtimesEpisodeStatusCustomChild]:
        return self._custom

    @Custom.setter
    def Custom(self, data: ShowtimesEpisodeStatusCustomChild | list[ShowtimesEpisodeStatusCustomChild]) -> None:
        if isinstance(data, ShowtimesEpisodeStatusCustomChild):
            try:
                idx = self._custom.index(data)
                self._custom[idx] = data
                return
            except ValueError:
                return
        elif isinstance(data, list):
            for child in data:
                if not isinstance(child, ShowtimesEpisodeStatusCustomChild):
                    raise TypeError("Custom status must be ShowtimesEpisodeStatusCustomChild")
                self.Custom = child
            return

    def copy(self) -> ShowtimesEpisodeStatusChild:
        return self.from_dict(self.serialize())

    def is_custom(self, key: str):
        return key not in ["TL", "TLC", "ENC", "ED", "TM", "TS", "QC"]

    def set_custom(self, key: str, value: bool) -> None:
        if self.is_custom(key.upper()):
            for child in self._custom:
                if child == key.upper():
                    child.done = value
                    break

    @overload
    def get_custom(self, key: str, strict_null: Literal[False] = False) -> bool: ...

    @overload
    def get_custom(self, key: str, strict_null: Literal[True]) -> bool | None: ...

    def get_custom(self, key: str, strict_null: bool = False) -> bool | None:
        if self.is_custom(key.upper()):
            for child in self._custom:
                if child.key == key.upper():
                    return child.done
        return False if not strict_null else None

    def get_custom_name(self, key: str) -> str | None:
        if self.is_custom(key.upper()):
            for child in self._custom:
                if child.key == key.upper():
                    return child.name
        return None

    def create_custom(self, key: str, name: str, value: bool) -> None:
        if self.is_custom(key.upper()):
            is_exist = self.get_custom(key, True)
            if is_exist is None:
                self._custom.append(ShowtimesEpisodeStatusCustomChild(key, name, value))

    def remove_custom(self, key: str) -> None:
        if self.is_custom(key.upper()):
            idx = -1
            for i, child in enumerate(self._custom):
                if child.key == key.upper():
                    idx = i
                    break
            if idx != -1:
                self._custom.pop(idx)

    @classmethod
    def factory(cls: type[ShowtimesEpisodeStatusChild]) -> ShowtimesEpisodeStatusChild:
        return cls()

    @classmethod
    def factory_from_other(
        cls: type[ShowtimesEpisodeStatusChild], data: ShowtimesEpisodeStatusChild
    ) -> ShowtimesEpisodeStatusChild:
        copy_data = data.copy()
        cls_init = cls()
        for custom in copy_data.Custom:
            cls_init.create_custom(custom.key, custom.name, custom.done)
        return cls_init

    @classmethod
    def from_dict(cls: type[ShowtimesEpisodeStatusChild], data: Mapping[str, object]) -> ShowtimesEpisodeStatusChild:
        custom_data = data.get("custom", [])
        if not isinstance(custom_data, list):
            raise ValueError("Episode progress `custom` must be a list")
        custom_parsed = []
        for item in custom_data:
            if not isinstance(item, Mapping):
                raise ValueError("Custom episode progress must be a mapping")
            key = item.get("key")
            name = item.get("name")
            done = item.get("done", False)
            if not isinstance(key, str) or not isinstance(name, str):
                raise ValueError("Custom episode progress requires string `key` and `name`")
            custom_parsed.append(ShowtimesEpisodeStatusCustomChild(key, name, to_bool(done)))
        return cls(
            to_bool(data.get("TL", False)),
            to_bool(data.get("TLC", False)),
            to_bool(data.get("ENC", False)),
            to_bool(data.get("ED", False)),
            to_bool(data.get("TM", False)),
            to_bool(data.get("TS", False)),
            to_bool(data.get("QC", False)),
            custom_parsed,
        )

    def serialize(self) -> showmodel._ShowtimesProjectEpisodeStatusProgressDict:
        return {
            "TL": self._tl,
            "TLC": self._tlc,
            "ENC": self._enc,
            "ED": self._ed,
            "TM": self._tm,
            "TS": self._ts,
            "QC": self._qc,
            "custom": [x.serialize() for x in self._custom],
        }

    def toggle(self, role: str, target: bool):
        normalized_role = role.upper()
        if normalized_role == "TL":
            self.TL = target
        elif normalized_role == "TLC":
            self.TLC = target
        elif normalized_role == "ENC":
            self.Encode = target
        elif normalized_role == "ED":
            self.Edit = target
        elif normalized_role == "TM":
            self.Timing = target
        elif normalized_role == "TS":
            self.TS = target
        elif normalized_role == "QC":
            self.QC = target
        else:
            self.set_custom(normalized_role, target)

    def get(self, role: str) -> bool:
        normalized_role = role.upper()
        if normalized_role == "TL":
            return self.TL
        elif normalized_role == "TLC":
            return self.TLC
        elif normalized_role == "ENC":
            return self.Encode
        elif normalized_role == "ED":
            return self.Edit
        elif normalized_role == "TM":
            return self.Timing
        elif normalized_role == "TS":
            return self.TS
        elif normalized_role == "QC":
            return self.QC
        else:
            return self.get_custom(normalized_role)


class ShowtimesEpisodeStatus:
    def __init__(
        self,
        episode: int,
        progress: ShowtimesEpisodeStatusChild,
        airtime: showmodel.AnyNum | None = None,
        is_finished: bool = False,
        delay_reason: str | None = None,
    ):
        self._ep = episode
        self._progress = progress
        self._is_finished = is_finished
        self._airtime = airtime
        self._delay_reason = delay_reason

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ShowtimesEpisodeStatus):
            return self._ep == other.episode and self._is_finished == other.finished
        elif isinstance(other, int):
            return self._ep == other
        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return f"<ShowtimesEpisodeStatus episode={self.episode} finished={self._is_finished}>"

    def __bool__(self) -> bool:
        return self._is_finished

    def __lt__(self, other: ShowtimesEpisodeStatus | int) -> bool:
        if isinstance(other, ShowtimesEpisodeStatus):
            return self._ep < other.episode
        elif isinstance(other, int):
            return self._ep < other
        return False

    def __le__(self, other: ShowtimesEpisodeStatus | int) -> bool:
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other: ShowtimesEpisodeStatus | int) -> bool:
        return not self.__le__(other)

    def __ge__(self, other: ShowtimesEpisodeStatus | int) -> bool:
        return not self.__lt__(other)

    @property
    def episode(self) -> int:
        return self._ep

    @episode.setter
    def episode(self, data: int) -> None:
        self._ep = data

    @property
    def progress(self) -> ShowtimesEpisodeStatusChild:
        return self._progress

    @progress.setter
    def progress(self, data: Mapping[str, object] | ShowtimesEpisodeStatusChild) -> None:
        if isinstance(data, Mapping):
            self._progress = ShowtimesEpisodeStatusChild.from_dict(data)
        elif isinstance(data, ShowtimesEpisodeStatusChild):
            self._progress = data

    @property
    def finished(self) -> bool:
        return self._is_finished

    @finished.setter
    def finished(self, data: bool) -> None:
        self._is_finished = data

    @property
    def airtime(self) -> showmodel.AnyNum | None:
        return self._airtime

    @airtime.setter
    def airtime(self, data: showmodel.AnyNum | None) -> None:
        self._airtime = data

    @property
    def delay_reason(self) -> str | None:
        return self._delay_reason

    @delay_reason.setter
    def delay_reason(self, data: str | None) -> None:
        self._delay_reason = data

    def copy(self) -> ShowtimesEpisodeStatus:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(
        cls: type[ShowtimesEpisodeStatus], data: showmodel.ShowtimesProjectEpisodeStatusDict
    ) -> ShowtimesEpisodeStatus:
        episode = data.get("episode")
        is_done = data.get("is_done", False)
        progress_data = data.get("progress")
        progress = (
            ShowtimesEpisodeStatusChild.from_dict(progress_data)
            if progress_data is not None
            else ShowtimesEpisodeStatusChild.factory()
        )
        airtime = data.get("airtime", None)
        delay_reason = data.get("delay_reason")
        return cls(episode, progress, airtime, is_done, delay_reason)

    def serialize(self) -> showmodel.ShowtimesProjectEpisodeStatusDict:
        return {
            "episode": self._ep,
            "is_done": self._is_finished,
            "progress": self._progress.serialize(),
            "airtime": self._airtime,
            "delay_reason": self._delay_reason,
        }


class ShowtimesPoster:
    def __init__(self, url: str, color: int = 0x1EB5A6):
        self._url = url
        self._color = color

    def __repr__(self) -> str:
        return f'<ShowtimesPoster url="{self._url}" >'

    @property
    def url(self) -> str:
        return self._url

    @url.setter
    def url(self, data: str) -> None:
        self._url = data

    @property
    def color(self) -> int:
        return self._color

    @color.setter
    def color(self, data: int) -> None:
        self._color = data

    def copy(self) -> ShowtimesPoster:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(cls: type[ShowtimesPoster], data: showmodel._ShowtimesProjectPosterDict) -> ShowtimesPoster:
        url = data.get("url")
        color = data.get("color", 0x1EB5A6)
        if url is None:
            raise ValueError("ShowtimesPoster: `url` is a required data")
        if color is None:
            color = 0x1EB5A6
        return cls(url, int(color))

    def serialize(self) -> showmodel._ShowtimesProjectPosterDict:
        return {"url": self._url, "color": self._color}


class ShowtimesFSDB:
    def __init__(self, uuid: int | None, anime_id: int | None):
        self._uuid = uuid
        self._anime_id = anime_id

    def __repr__(self) -> str:
        return f"<ShowtimesFSDB id={self._uuid} animeId={self._anime_id}>"

    @property
    def id(self) -> int | None:
        return self._uuid

    @id.setter
    def id(self, data: int | None) -> None:
        self._uuid = data

    @property
    def anime(self) -> int | None:
        return self._anime_id

    @anime.setter
    def anime(self, data: int | None) -> None:
        self._anime_id = data

    def copy(self) -> ShowtimesFSDB:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(cls: type[ShowtimesFSDB], data: showmodel._ShowtimesProjectFSDBDict) -> ShowtimesFSDB:
        uuid = data.get("id")
        anime_id = data.get("ani_id")
        return cls(uuid, anime_id)

    def serialize(self) -> showmodel._ShowtimesProjectFSDBDict:
        return {"id": self._uuid, "ani_id": self._anime_id}

    @classmethod
    def factory(cls: type[ShowtimesFSDB]) -> ShowtimesFSDB:
        return cls(None, None)


class ShowtimesProject:
    def __init__(
        self,
        id: str,
        title: str,
        mal_id: int | None = None,
        role_id: int | None = None,
        start_time: showmodel.AnyNum | None = None,
        assignment: ShowtimesAssignment | None = None,
        status: list[ShowtimesEpisodeStatus] = [],
        poster_data: ShowtimesPoster | None = None,
        aliases: ShowAliases = [],
        kolaborasi: ShowKolaborasi = [],
        fsdb_data: ShowtimesFSDB | None = None,
        last_update: showmodel.AnyNum | None = None,
    ):
        self._id = id
        self._title = title
        self._mal_id = mal_id
        self._role_id = role_id
        self._start_time = start_time
        self._assignment = assignment if assignment is not None else ShowtimesAssignment.factory()
        self._status = status
        self._poster_data = poster_data if poster_data is not None else ShowtimesPoster("")
        self._aliases = aliases
        self._kolaborasi = kolaborasi
        self._fsdb_data = fsdb_data
        if last_update is None:
            self._last_update = arrow.utcnow().int_timestamp
        else:
            self._last_update = last_update

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ShowtimesProject):
            return self._id == other.id
        elif isinstance(other, str):
            return self._id == other or self._title.casefold() == other.casefold()
        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __iter__(self) -> Looped[ShowtimesEpisodeStatus]:
        for status in self._status:
            yield status

    def __repr__(self) -> str:
        return f'<ShowtimesProject id={self._id} episodes={len(self._status)} title="{self._title}">'

    def __add__(self, other: ShowtimesEpisodeStatus | list[ShowtimesEpisodeStatus]) -> ShowtimesProject:
        if not isinstance(other, (ShowtimesEpisodeStatus, list)):
            raise TypeError(f"Can only add ShowtimesEpisodeStatus to ShowtimesProject, but got {type(other)} instead.")
        merged = []
        if not isinstance(other, list):
            if other not in self._status:
                merged.append(other)
        else:
            for m in merged:
                if isinstance(m, ShowtimesEpisodeStatus) and m not in self._status:
                    merged.append(m)
        for o in merged:
            self._status.append(o)
        return self

    def __sub__(self, other: ShowtimesEpisodeStatus | int | list[ShowtimesEpisodeStatus | int]) -> ShowtimesProject:
        if not isinstance(other, (ShowtimesEpisodeStatus, int, list)):
            raise TypeError(
                f"Can only subtract ShowtimesEpisodeStatus or int from ShowtimesProject, but got {type(other)} instead."
            )
        if not isinstance(other, list):
            other = [other]
        for o in other:
            if not isinstance(o, (ShowtimesEpisodeStatus, int)):
                continue
            self.remove_episode(o)
        return self

    def __iadd__(self, other: ShowtimesEpisodeStatus | list[ShowtimesEpisodeStatus]) -> ShowtimesProject:
        return self.__add__(other)

    def __isub__(self, other: ShowtimesEpisodeStatus | int | list[ShowtimesEpisodeStatus | int]) -> ShowtimesProject:
        return self.__sub__(other)

    def __len__(self) -> int:
        return len(self._status)

    def _updated(self):
        self._last_update = arrow.utcnow().int_timestamp

    update_time = _updated

    @property
    def id(self) -> str:
        return self._id

    @id.setter
    def id(self, data: str):
        self._id = data

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, data: str):
        self._title = data

    @property
    def mal_id(self) -> int | None:
        return self._mal_id

    @mal_id.setter
    def mal_id(self, data: int | None) -> None:
        self._mal_id = int(data) if data is not None else None

    @property
    def role(self) -> int | None:
        return self._role_id

    @role.setter
    def role(self, data: discord.Role | int) -> None:
        if isinstance(data, int):
            self._role_id = data
        elif isinstance(data, discord.Role):
            self._role_id = data.id

    @property
    def start_time(self) -> showmodel.AnyNum | None:
        return self._start_time

    @start_time.setter
    def start_time(self, data: showmodel.AnyNum | None) -> None:
        self._start_time = data

    @property
    def assignment(self) -> ShowtimesAssignment:
        return self._assignment

    @assignment.setter
    def assignment(self, data: ShowtimesAssignment) -> None:
        if isinstance(data, ShowtimesAssignment):
            self._assignment = data

    def update_assignment(self, role: str, data: ShowtimesAssignee | MemberContext | str | int):
        self._assignment._set_assignee(role, data)

    @property
    def status(self) -> list[ShowtimesEpisodeStatus]:
        return self._status

    @status.setter
    def status(self, data: ShowtimesEpisodeStatus | list[ShowtimesEpisodeStatus]) -> None:
        if isinstance(data, list):
            self._status = data
            self._updated()
        elif isinstance(data, ShowtimesEpisodeStatus):
            ep_index = -1
            for n, ep in enumerate(self._status):
                if ep.episode == data.episode:
                    ep_index = n
                    break
            if ep_index >= 0:
                self._status[ep_index] = data
                self._updated()

    @property
    def total_episodes(self):
        return len(self._status)

    def get_episode(self, episode: int) -> ShowtimesEpisodeStatus | None:
        the_episode = list(filter(lambda x: x.episode == episode, self._status))
        if len(the_episode) > 0:
            return the_episode[0]
        return None

    def add_episode(self, episode: ShowtimesEpisodeStatus):
        is_episode = self.get_episode(episode.episode)
        if not is_episode:
            self._status.append(episode)
            self._updated()

    def remove_episode(self, episode: ShowtimesEpisodeStatus | int):
        episode_no = episode
        if isinstance(episode, ShowtimesEpisodeStatus):
            episode_no = episode.episode
        ep_index = -1
        for n, ep in enumerate(self._status):
            if ep.episode == episode_no:
                ep_index = n
                break
        if ep_index >= 0:
            del self._status[ep_index]
            self._updated()

    def get_current(self) -> ShowtimesEpisodeStatus | None:
        for episode in self._status:
            if not episode.finished:
                return episode
        return None

    def get_previous_episode(self) -> ShowtimesEpisodeStatus | None:
        # Find the latest episode that marked as finished
        # And then get the previous one
        for episode in reversed(self._status):
            if episode.finished:
                return episode
        return None

    def get_all_unfinished(self) -> list[ShowtimesEpisodeStatus]:
        return list(filter(lambda x: not x.finished, self._status))

    @staticmethod
    def is_progressing(episode: ShowtimesEpisodeStatus) -> bool:
        return bool(episode.progress)

    @property
    def poster(self) -> ShowtimesPoster:
        return self._poster_data

    @poster.setter
    def poster(self, data: ShowtimesPoster | str | int) -> None:
        if isinstance(data, ShowtimesPoster):
            self._poster_data = data
        elif isinstance(data, str):
            if self._poster_data is None:
                self._poster_data = ShowtimesPoster(data)
            else:
                self._poster_data.url = data
        elif isinstance(data, int):
            if self._poster_data is None:
                raise ValueError("Missing poster data, cannot set color")
            self._poster_data.color = data

    @property
    def aliases(self) -> ShowAliases:
        return self._aliases

    def add_alias(self, alias: str):
        if alias not in self._aliases:
            self._aliases.append(alias)

    def remove_alias(self, alias: str):
        if alias in self._aliases:
            self._aliases.remove(alias)

    @property
    def kolaborasi(self) -> ShowKolaborasi:
        return self._kolaborasi

    @kolaborasi.setter
    def kolaborasi(self, data: int | list[int]):
        if isinstance(data, int):
            self.add_kolaborator(data)
        elif isinstance(data, list):
            self._kolaborasi = data

    def add_kolaborator(self, kolaborator: int):
        if kolaborator not in self._kolaborasi:
            self._kolaborasi.append(kolaborator)

    def remove_kolaborator(self, kolaborator: int) -> int | None:
        if kolaborator in self._kolaborasi:
            self._kolaborasi.remove(kolaborator)
            return kolaborator
        return None

    @property
    def fsdb(self) -> ShowtimesFSDB | None:
        return self._fsdb_data

    @fsdb.setter
    def fsdb(self, data: ShowtimesFSDB | None) -> None:
        self._fsdb_data = data

    @property
    def last_update(self) -> showmodel.AnyNum:
        return self._last_update

    def format_last_update(self, language: str = "id") -> str:
        passed_time: arrow.Arrow = arrow.get(self._last_update)

        return passed_time.humanize(locale=language)

    @property
    def formatted_last_update(self) -> str:
        return self.format_last_update()

    @classmethod
    def from_dict(cls: type[ShowtimesProject], data: showmodel.ShowtimesProjectDict) -> ShowtimesProject:
        anime_id = data.get("id")
        mal_id = data.get("mal_id")
        anime_title = data.get("title")
        role_id = data.get("role_id")
        try:
            role_id = int(role_id) if role_id is not None else None
        except (ValueError, TypeError):
            role_id = None
        start_time = data.get("start_time")
        assignment_data = data.get("assignments")
        assignements = (
            ShowtimesAssignment.from_dict(assignment_data)
            if assignment_data is not None
            else ShowtimesAssignment.factory()
        )
        all_status = []
        for status_data in data.get("status", []):
            all_status.append(ShowtimesEpisodeStatus.from_dict(status_data))
        aliases = data.get("aliases", [])
        poster_payload = data.get("poster_data")
        poster_data = ShowtimesPoster.from_dict(poster_payload) if poster_payload is not None else ShowtimesPoster("")
        fsdb_data = None
        fsdb = data.get("fsdb_data")
        if fsdb:
            fsdb_data = ShowtimesFSDB.from_dict(fsdb)
        kolaborasi = list(map(int, data.get("kolaborasi", [])))
        last_update = data.get("last_update", arrow.utcnow().int_timestamp)
        # if last_update is None:
        # last_update = arrow.utcnow().int_timestamp
        return cls(
            anime_id,
            anime_title,
            mal_id,
            role_id,
            start_time,
            assignements,
            all_status,
            poster_data,
            aliases,
            kolaborasi,
            fsdb_data,
            last_update,
        )

    @classmethod
    def factory(cls: type[ShowtimesProject]) -> ShowtimesProject:
        return cls(
            "",
            "",
            None,
            None,
            None,
            ShowtimesAssignment.factory(),
            [],
            ShowtimesPoster(""),
            [],
            [],
            None,
        )

    def serialize(self) -> showmodel.ShowtimesProjectDict:
        all_status: list[showmodel.ShowtimesProjectEpisodeStatusDict] = []
        for status in self._status:
            all_status.append(status.serialize())
        safely_role = str(self._role_id) if self._role_id is not None else None
        final_dict: showmodel.ShowtimesProjectDict = {
            "id": self._id,
            "mal_id": self.mal_id,
            "title": self._title,
            "role_id": safely_role,
            "start_time": self._start_time,
            "assignments": self._assignment.serialize(),
            "status": all_status,
            "poster_data": self._poster_data.serialize(),
            "aliases": self._aliases,
            "kolaborasi": list(map(str, self._kolaborasi)),
            "last_update": self._last_update,
        }
        if self._fsdb_data is not None:
            final_dict["fsdb_data"] = self._fsdb_data.serialize()
        return final_dict

    def copy(self):
        return self.from_dict(self.serialize())

    def update(self, data: ShowtimesProject, only_data: bool = True):
        self._id = data.id
        self._mal_id = data.mal_id
        self._title = data.title
        self._start_time = data.start_time
        self._assignment = data.assignment
        self._status = data.status
        self._poster_data = data.poster
        self._aliases = data.aliases
        self._kolaborasi = data.kolaborasi
        self._updated()

        if not only_data:
            self._role_id = data.role
            self._fsdb_data = data.fsdb


@dataclass
class ShowtimesSearch:
    id: str
    index: int
    title: str
    real_title: str | None = None
    type: Literal["real", "alias"] = "real"

    def match(self, target: str) -> bool:
        target_clean = re.escape(target)
        target_compiler = re.compile(f"({target_clean})", re.IGNORECASE)
        matched = target_compiler.search(self.title)
        if matched is None:
            return False
        return True


class Showtimes:
    def __init__(
        self,
        id: int,
        projects: list[ShowtimesProject],
        owner: ShowtimesOwner,
        konfirmasi: list[ShowtimesKonfirmasi] = [],
        announce_channel: int | None = None,
        name: str | None = None,
        fsdb_id: int | None = None,
    ):
        self._mongo_id = None
        self._id = id
        self._projects = projects
        self._admins = owner
        self._confirmations = konfirmasi
        self._announce_channel = announce_channel
        self._name = name
        self._fsdb_id = fsdb_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Showtimes):
            return self.id == other.id
        elif isinstance(other, int):
            return self.id == other
        return False

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __iter__(self) -> Looped[ShowtimesProject]:
        for project in self._projects:
            yield project

    def __repr__(self) -> str:
        return f"<Showtimes id={self.id} name={self._name} projects={len(self._projects)}>"

    def __add__(self, other: ShowtimesProject | list[ShowtimesProject]) -> Showtimes:
        if isinstance(other, ShowtimesProject):
            self.add_project(other)
        elif isinstance(other, list):
            for project in other:
                if isinstance(project, ShowtimesProject):
                    self.add_project(project)
        else:
            raise TypeError(f"Cannot add type {type(other)} to Showtimes")
        return self

    def __sub__(self, other: ShowtimesProject | list[ShowtimesProject]) -> Showtimes:
        if isinstance(other, ShowtimesProject):
            self.remove_project(other)
        elif isinstance(other, list):
            for project in other:
                if isinstance(project, ShowtimesProject):
                    self.remove_project(project)
        else:
            raise TypeError(f"Cannot remove type {type(other)} from Showtimes")
        return self

    def __iadd__(self, other: ShowtimesProject | list[ShowtimesProject]) -> Showtimes:
        return self + other

    def __isub__(self, other: ShowtimesProject | list[ShowtimesProject]) -> Showtimes:
        return self - other

    def __len__(self) -> int:
        return len(self._projects)

    def __propagate_all_titles(self, ignore_alias: bool = False) -> list[ShowtimesSearch]:
        propagated = []
        for index, anime_data in enumerate(self._projects):
            propagated.append(ShowtimesSearch(anime_data.id, index, anime_data.title, "real"))
            if not ignore_alias:
                for alias in anime_data.aliases:
                    propagated.append(ShowtimesSearch(anime_data.id, index, alias, anime_data.title, "alias"))
        return propagated

    @property
    def id(self) -> int:
        return self._id

    @property
    def mongo_id(self) -> ObjectId | None:
        return self._mongo_id

    @mongo_id.setter
    def mongo_id(self, value: ObjectId | None):
        if value is None:
            self._mongo_id = None
        else:
            if not isinstance(value, ObjectId):
                value = ObjectId(value)
            self._mongo_id = value

    @property
    def projects(self) -> list[ShowtimesProject]:
        return self._projects

    def get_project(self, other: str | ShowtimesProject) -> ShowtimesProject | None:
        for project in self._projects:
            if project == other:
                return project
        return None

    def find_projects(self, title: str, ignore_alias: bool = False) -> list[ShowtimesProject]:
        propagated = self.__propagate_all_titles(ignore_alias)
        matched = list(filter(lambda x: x.match(title), propagated))
        deduplicated: list[ShowtimesProject] = []
        dedup_idx: list[int] = []
        for match in matched:
            if match.index not in dedup_idx:
                deduplicated.append(self._projects[match.index])
                dedup_idx.append(match.index)
        return deduplicated

    def exact_match(self, title: str) -> ShowtimesProject | None:
        for project in self._projects:
            if project.title == title:
                return project
        return None

    def update_project(self, project: ShowtimesProject, only_data: bool = True):
        index = -1
        for i, p in enumerate(self._projects):
            if p.id == project.id:
                index = i
                break
        if index >= 0:
            old_project = self._projects[index].copy()
            old_project.update(project, only_data)
            self._projects[index] = old_project
        else:
            self._projects.append(project)

    def add_project(self, project: ShowtimesProject):
        if project.id in [p.id for p in self._projects]:
            return
        self._projects.append(project)

    def remove_project(self, project: str | ShowtimesProject):
        if isinstance(project, ShowtimesProject):
            proj_id = project.id
        else:
            proj_id = project
        index = -1
        for i, p in enumerate(self._projects):
            if p.id == proj_id:
                index = i
                break
        if index >= 0:
            del self._projects[index]

    @property
    def admins(self) -> ShowtimesOwner:
        return self._admins

    def is_admin(self, user: int | MemberContext) -> bool:
        if isinstance(user, int):
            return user in self._admins
        elif isinstance(user, DiscordUser):
            return user.id in self._admins
        return False

    def add_admin(self, user: int | MemberContext):
        if isinstance(user, int):
            if user not in self._admins:
                self._admins.append(user)
        elif isinstance(user, DiscordUser):
            if user.id not in self._admins:
                self._admins.append(user.id)

    def remove_admin(self, user: int | MemberContext):
        if isinstance(user, int):
            if user in self._admins:
                self._admins.remove(user)
        elif isinstance(user, DiscordUser):
            if user.id in self._admins:
                self._admins.remove(user.id)

    @property
    def konfirmasi(self) -> list[ShowtimesKonfirmasi]:
        return self._confirmations

    def get_konfirm(self, kode: str) -> ShowtimesKonfirmasi | None:
        for konfirm in self._confirmations:
            if konfirm == kode:
                return konfirm
        return None

    def add_konfirm(self, konfirm: ShowtimesKonfirmasi):
        matched = len(list(filter(lambda x: x == konfirm, self._confirmations)))
        if matched < 1:
            self._confirmations.append(konfirm)

    def remove_konfirm(self, konfirm: ShowtimesKonfirmasi | str):
        idx = -1
        for i, konfirm_data in enumerate(self._confirmations):
            if konfirm_data == konfirm:
                idx = i
                break
        if idx >= 0:
            del self._confirmations[idx]

    @property
    def announcer(self) -> int | None:
        return self._announce_channel

    @announcer.setter
    def announcer(self, data: int | discord.TextChannel):
        if isinstance(data, discord.TextChannel):
            self._announce_channel = data.id
        elif isinstance(data, int):
            self._announce_channel = data

    @property
    def name(self) -> str | None:
        return self._name

    @name.setter
    def name(self, data: str):
        self._name = data

    @property
    def fsdb_id(self) -> int | None:
        return self._fsdb_id

    @fsdb_id.setter
    def fsdb_id(self, data: int):
        self._fsdb_id = data

    def copy(self) -> Showtimes:
        return self.from_dict(self.serialize())

    @classmethod
    def from_dict(cls: type[Showtimes], data: showmodel.ShowtimesDict) -> Showtimes:
        server_id = int(data.get("id"))
        server_name = data.get("name")
        announcer = data.get("announce_channel")
        if announcer is not None:
            try:
                announcer = int(announcer)
            except ValueError:
                announcer = None
        server_owner = data.get("serverowner", [])
        server_owner = list(map(int, server_owner))
        projects = data.get("anime", [])
        parsed_project = []
        for project in projects:
            parsed_project.append(ShowtimesProject.from_dict(project))
        konfirmasi = data.get("konfirmasi", [])
        parsed_konfirm = []
        for konfirm in konfirmasi:
            parsed_konfirm.append(ShowtimesKonfirmasi.from_dict(konfirm))
        fsdb_id = data.get("fsdb_id")
        db_id = data.get("_id", data.get("mongo_id"))
        if db_id is None:
            raise KeyError("Missing `_id` or `mongo_id` on the data, it's needed to update the database!")
        if not isinstance(db_id, ObjectId):
            db_id = ObjectId(db_id)
        new_cls = cls(
            server_id,
            parsed_project,
            server_owner,
            parsed_konfirm,
            announcer,
            server_name,
            fsdb_id,
        )
        new_cls.mongo_id = db_id
        return new_cls

    def serialize(self) -> showmodel.ShowtimesDict:
        all_projects = list(map(lambda x: x.serialize(), self._projects))
        all_confirms = list(map(lambda x: x.serialize(), self._confirmations))
        all_admins = list(map(str, self._admins))
        final_dict: showmodel.ShowtimesDict = {
            "id": str(self.id),
            "serverowner": all_admins,
            "anime": all_projects,
            "konfirmasi": all_confirms,
        }
        if self.mongo_id is not None:
            final_dict["_id"] = str(self.mongo_id)
        if self._name is not None:
            final_dict["name"] = self._name
        if self._announce_channel is not None:
            final_dict["announce_channel"] = str(self._announce_channel)
        if self._fsdb_id is not None:
            final_dict["fsdb_id"] = self._fsdb_id
        return final_dict


class ShowtimesAdmin:
    def __init__(self, id: int, servers: ShowtimesServer):
        self._id = id
        self._mongo_id = None
        self._servers = servers

    @property
    def id(self):
        return self._id

    @property
    def servers(self):
        return self._servers

    @property
    def mongo_id(self) -> ObjectId | None:
        return self._mongo_id

    @mongo_id.setter
    def mongo_id(self, value: ObjectId | None):
        if value is None:
            self._mongo_id = None
        else:
            if not isinstance(value, ObjectId):
                value = ObjectId(value)
            self._mongo_id = value

    def add_server(self, id: int):
        if id not in self._servers:
            self._servers.append(id)

    def remove_server(self, id: int):
        if id in self._servers:
            self._servers.remove(id)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]):
        identifier = data.get("id")
        if not isinstance(identifier, (str, int)) or isinstance(identifier, bool):
            raise ValueError("ShowtimesAdmin: `id` must be a string or integer")
        servers = data.get("servers", [])
        if not isinstance(servers, list):
            raise ValueError("ShowtimesAdmin: `servers` must be a list")
        parsed_servers = []
        for server in servers:
            if not isinstance(server, (str, int)) or isinstance(server, bool):
                raise ValueError("ShowtimesAdmin: server IDs must be strings or integers")
            parsed_servers.append(int(server))
        mongo_id = data.get("_id", data.get("mongo_id"))
        if mongo_id is None:
            raise KeyError("Missing `_id` or `mongo_id` on the data, it's needed to update the database!")
        if not isinstance(mongo_id, ObjectId):
            if not isinstance(mongo_id, str):
                raise ValueError("ShowtimesAdmin: Mongo ID must be an ObjectId or string")
            mongo_id = ObjectId(mongo_id)
        new_cls = cls(int(identifier), parsed_servers)
        new_cls.mongo_id = mongo_id
        return new_cls

    def serialize(self):
        return {
            "_id": self._mongo_id,
            "id": self._id,
            "servers": list(map(str, self._servers)),
        }


class ShowtimesLock:
    def __init__(self, server_id: str | int):
        self._id = str(server_id)
        self._unlocked = asyncio.Event()
        self._unlocked.set()
        self._log = logging.getLogger(f"ShowtimesLock[{server_id}]")

    async def __aenter__(self, *args, **kwargs):
        await self.hold()
        return self._id

    async def __aexit__(self, *args, **kwargs):
        await self.release()

    async def hold(self):
        timeout_max = 10  # In seconds
        try:
            await asyncio.wait_for(self._unlocked.wait(), timeout=timeout_max)
        except TimeoutError:
            self._log.warning("Waiting timeout occured, relocking!")
        self._log.info("Holding access to lock!")
        self._unlocked.clear()

    async def release(self):
        self._log.info("Releasing lock...")
        self._unlocked.set()


#####################
#     FansubRSS     #
#####################


class FansubRSSEmbed:
    def __init__(
        self,
        title: str | None,
        description: str | None,
        url: str | None,
        thumbnail: str | None,
        image: str | None,
        footer: str | None,
        footer_img: str | None,
        color: int | None = None,
        timestamp: bool = False,
    ):
        self._title = title
        self._description = description
        self._url = url
        self._thumbnail = thumbnail
        self._image = image
        self._footer = footer
        self._footer_img = footer_img
        self._color = color
        self._timestamp = timestamp

    def __getitem__(self, name: str):
        if not name.startswith("_"):
            name = "_" + name
        return getattr(self, name, None)

    def __setitem__(self, name: str, value: str | bool | int):
        if not name.startswith("_"):
            name = "_" + name
        if not hasattr(self, name):
            return
        setattr(self, name, value)

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, data: str | None):
        self._title = data

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, data: str | None):
        self._description = data

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, data: str | None):
        self._url = data

    @property
    def thumbnail(self):
        return self._thumbnail

    @thumbnail.setter
    def thumbnail(self, data: str | None):
        self._thumbnail = data

    @property
    def image(self):
        return self._image

    @image.setter
    def image(self, data: str | None):
        self._image = data

    @property
    def footer(self):
        return self._footer

    @footer.setter
    def footer(self, data: str | None):
        self._footer = data

    @property
    def footer_img(self):
        return self._footer_img

    @footer_img.setter
    def footer_img(self, data: str | None):
        self._footer_img = data

    @property
    def color(self) -> int | None:
        return self._color

    @color.setter
    def color(self, data: discord.Color | int):
        if isinstance(data, int):
            self._color = data
        elif isinstance(data, discord.Color):
            self._color = data.value

    @property
    def timestamp(self) -> bool:
        return self._timestamp

    @timestamp.setter
    def timestamp(self, data: bool):
        self._timestamp = data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> FansubRSSEmbed:
        color_value = data.get("color", 0x525252)
        color = int(color_value) if isinstance(color_value, (int, float)) else 0x525252
        timestamp_value = data.get("timestamp", False)
        timestamp = timestamp_value if isinstance(timestamp_value, bool) else False
        return cls(
            _optional_string(data.get("title")),
            _optional_string(data.get("description")),
            _optional_string(data.get("url")),
            _optional_string(data.get("thumbnail")),
            _optional_string(data.get("image")),
            _optional_string(data.get("footer")),
            _optional_string(data.get("footer_img")),
            color,
            timestamp,
        )

    def serialize(self):
        return {
            "title": self._title,
            "description": self._description,
            "url": self._url,
            "thumbnail": self._thumbnail,
            "image": self._image,
            "footer": self._footer,
            "footer_img": self._footer_img,
            "color": self._color,
            "timestamp": self._timestamp,
        }

    @property
    def is_valid(self):
        # A minimum of title and description must be available
        if not self._title or not self._description:
            return False
        return True

    def generate(self, entry_data: dict, template_mode=False) -> discord.Embed | None:
        if not self.is_valid and not template_mode:
            return None

        regex_embed = re.compile(r"(?P<data>{[^{}]+})", re.MULTILINE | re.IGNORECASE)
        filtered = {}
        for key, value in self.serialize().items():
            if not value:
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                filtered[key] = value
                continue
            matched = re.findall(regex_embed, value)
            formatted = list(map(lambda x: x.replace("{", "").replace("}", ""), matched))
            for fmt in formatted:
                try:
                    if isinstance(entry_data[fmt], (tuple, list)):
                        joined = ", ".join(map(str, entry_data[fmt]))
                        entry_data[fmt] = joined
                    value = value.replace("{" + fmt + "}", entry_data[fmt])
                except KeyError:
                    pass
            filtered[key] = value

        embedded = discord.Embed()
        title = filtered.get("title")
        description = filtered.get("description")
        url_value = filtered.get("url")
        url = url_value if isinstance(url_value, str) else None
        if title is not None:
            embedded.title = title
        elif template_mode:
            embedded.title = "Tidak ada judul"
        if description is not None:
            embedded.description = description
        elif template_mode:
            embedded.description = "*Tidak ada deskripsi*"
        if url is not None and url.startswith("http"):
            embedded.url = url

        embedded.colour = discord.Colour(self.color if self.color is not None else 0x525252)

        thumbnail_value = filtered.get("thumbnail")
        thumbnail = thumbnail_value if isinstance(thumbnail_value, str) else None
        image_value = filtered.get("image")
        image = image_value if isinstance(image_value, str) else None
        if thumbnail is not None and thumbnail.startswith("http"):
            embedded.set_thumbnail(url=thumbnail)
        if image is not None and image.startswith("http"):
            embedded.set_image(url=image)

        if self.timestamp:
            try:
                _, dt_data = time_struct_dt(entry_data["published_parsed"])
            except (AttributeError, KeyError, ValueError):
                dt_data = arrow.utcnow().datetime
            if isinstance(dt_data, arrow.Arrow):
                dt_data = dt_data.datetime
            embedded.timestamp = dt_data

        footer = filtered.get("footer")
        if footer is not None:
            kwargs_footer = {"text": footer}
            footer_img = filtered.get("footer_img")
            if footer_img is not None:
                kwargs_footer["icon_url"] = footer_img
            embedded.set_footer(**kwargs_footer)
        elif template_mode:
            embedded.set_footer(text="*Tidak ada footer*")

        return embedded


class FansubRSSPremium:
    def __init__(
        self,
        start: showmodel.AnyNum,
        duration: showmodel.AnyNum,
    ):
        self._start = start
        self._duration = duration

    @property
    def start(self) -> showmodel.AnyNum:
        return self._start

    @start.setter
    def start(self, data: showmodel.AnyNum):
        self._start = data

    def set_now(self):
        self._start = arrow.utcnow().int_timestamp

    @property
    def duration(self) -> showmodel.AnyNum:
        return self._duration

    @duration.setter
    def duration(self, data: showmodel.AnyNum):
        self._duration = data

    def add_duration(self, data: showmodel.AnyNum):
        self._duration += data

    @property
    def is_infinite(self):
        if self._start < 0 or self._duration < 0:
            return True
        return False

    @property
    def is_valid(self):
        if self.is_infinite:
            return True
        now = arrow.utcnow().int_timestamp
        max_time = self._start + self._duration
        return now < max_time

    @property
    def time_left(self) -> int | None:
        now = arrow.utcnow().int_timestamp
        max_time = self._start + self._duration
        time_left = round(max_time - now)
        if time_left < 0:
            return None
        return time_left

    def is_intersecting(self, target: showmodel.AnyNum | arrow.Arrow) -> bool:
        if isinstance(target, arrow.Arrow):
            target = target.int_timestamp
        max_time = self._start + self._duration
        return self._start <= target < max_time

    def exhaust(self):
        self._duration = 0

    @classmethod
    def from_dict(cls, data: bool | int | Mapping[str, object]) -> FansubRSSPremium | None:
        if isinstance(data, (bool, int)):
            data = bool(data)
            if data:
                return cls(-1, -1)
            else:
                return None
        start = data.get("start")
        duration = data.get("duration")
        if not isinstance(start, (int, float)) or isinstance(start, bool):
            raise ValueError("FansubRSSPremium: `start` must be numeric")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            raise ValueError("FansubRSSPremium: `duration` must be numeric")
        return cls(
            start,
            duration,
        )

    def serialize(self):
        return {
            "start": round(self._start),
            "duration": round(self._duration),
        }


class FansubRSSFeed:
    def __init__(
        self,
        id: str | int,
        channel: str | int,
        feed_url: str,
        message: str | None = None,
        embed: FansubRSSEmbed | None = None,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ):
        self._id = str(id)
        self._channel = str(channel)
        self._feed_url = feed_url
        self._message = message
        self._embed = embed
        self._last_etag = last_etag
        self._last_modified = last_modified

    def __eq__(self, other: object):
        if isinstance(other, (int, str)):
            return self._id == str(other)
        elif isinstance(other, FansubRSSFeed):
            return self.id == other.id
        return False

    def __repr__(self):
        attr = [
            f"id={self._id!r}",
            f"channel={self._channel!r}",
            f"url={self._feed_url!r}",
        ]
        return f"<FansubRSSFeed {' '.join(attr)}>"

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, data: str | int):
        self._id = str(data)

    @property
    def channel(self):
        return int(self._channel)

    @channel.setter
    def channel(self, data: str | int | discord.TextChannel):
        if isinstance(data, (int, str)):
            self._channel = str(data)
        elif isinstance(data, discord.TextChannel):
            self._channel = str(data.id)

    @property
    def feed_url(self):
        return self._feed_url

    @feed_url.setter
    def feed_url(self, data: str):
        self._feed_url = str(data)

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, data: str):
        self._message = data

    @property
    def embed(self):
        return self._embed

    @embed.setter
    def embed(self, data: dict | FansubRSSEmbed):
        if isinstance(data, dict):
            self._embed = FansubRSSEmbed.from_dict(data)
        elif isinstance(data, FansubRSSEmbed):
            self._embed = data
        elif data is None:
            self._embed = FansubRSSEmbed.from_dict({})

    @property
    def last_etag(self):
        return self._last_etag or ""

    @last_etag.setter
    def last_etag(self, data: str):
        self._last_etag = data

    @property
    def last_modified(self):
        return self._last_modified or ""

    @last_modified.setter
    def last_modified(self, data: str):
        self._last_modified = data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> FansubRSSFeed:
        feed_id = data.get("id")
        channel = data.get("channel")
        feed_url = data.get("feedUrl")
        if not isinstance(feed_id, (str, int)) or isinstance(feed_id, bool):
            raise ValueError("FansubRSSFeed: `id` must be a string or integer")
        if not isinstance(channel, (str, int)) or isinstance(channel, bool):
            raise ValueError("FansubRSSFeed: `channel` must be a string or integer")
        if not isinstance(feed_url, str):
            raise ValueError("FansubRSSFeed: `feedUrl` must be a string")
        message = _optional_string(data.get("message"))
        raw_embed = data.get("embed")
        if raw_embed is None:
            embed = None
        elif isinstance(raw_embed, FansubRSSEmbed):
            embed = raw_embed
        elif isinstance(raw_embed, Mapping):
            embed = FansubRSSEmbed.from_dict(raw_embed)
        else:
            raise ValueError("FansubRSSFeed: `embed` must be a mapping")
        last_etag = _optional_string(data.get("lastEtag", ""))
        last_modified = _optional_string(data.get("lastModified", ""))
        return cls(
            id=feed_id,
            channel=channel,
            feed_url=feed_url,
            message=message,
            embed=embed,
            last_etag=last_etag,
            last_modified=last_modified,
        )

    def serialize(self):
        embed = self.embed if self.embed is not None else FansubRSSEmbed.from_dict({})
        return {
            "id": self.id,
            "channel": self.channel,
            "feedUrl": self.feed_url,
            "message": self.message,
            "embed": embed.serialize(),
            "lastEtag": self.last_etag,
            "lastModified": self.last_modified,
        }

    def __parse_message(self, entry_data: dict):
        message = self.message
        if not message:
            return ""
        matches = re.findall(r"(?P<data>{[^{}]+})", message, re.MULTILINE | re.IGNORECASE)
        msg_fmt_data = [m.strip(r"{}") for m in matches]

        for fmt in msg_fmt_data:
            try:
                message = message.replace("{" + fmt + "}", entry_data[fmt])
            except KeyError:
                pass

        return message.replace("\\n", "\n")

    def generate(self, entry_data: dict) -> tuple[str | None, discord.Embed | None]:
        parsed_message = None
        if self.message:
            parsed_message = self.__parse_message(entry_data)

        parsed_embed = None
        if self.embed and self.embed.is_valid:
            parsed_embed = self.embed.generate(entry_data)

        return parsed_message, parsed_embed


class FansubRSS:
    def __init__(self, id: int, feeds: list[FansubRSSFeed] = [], premiums: list[FansubRSSPremium] = []):
        self._id = id
        self._feeds = feeds
        self._premiums = premiums

    def __eq__(self, other: object):
        if isinstance(other, int):
            return self._id == other
        elif isinstance(other, FansubRSS):
            return self.id == other.id
        return False

    def __repr__(self):
        return f"<FansubRSS id={self._id!r} feeds={len(self._feeds)!r} premium={self.has_premium!r}>"

    @property
    def id(self):
        return self._id

    @property
    def feeds(self):
        return self._feeds

    @feeds.setter
    def feeds(self, data: FansubRSSFeed | list[FansubRSSFeed]):
        if isinstance(data, list):
            self._feeds = data
        elif isinstance(data, FansubRSSFeed):
            self.update_feed(data)

    def get_feed(self, id: str | int) -> FansubRSSFeed | None:
        for feed in self.feeds:
            if feed == id:
                return feed
        return None

    def add_feed(self, feed: FansubRSSFeed):
        self.update_feed(feed)

    def remove_feed(self, data: FansubRSSFeed | str | int):
        feed_idx = -1
        for idx, feed in enumerate(self._feeds):
            if feed == data:
                feed_idx = idx
                break
        if feed_idx >= 0:
            self._feeds.pop(feed_idx)

    def update_feed(self, data: FansubRSSFeed):
        feed_idx = -1
        for idx, feed in enumerate(self._feeds):
            if feed == data:
                feed_idx = idx
                break
        if feed_idx >= 0:
            self._feeds[feed_idx] = data
        else:
            self._feeds.append(data)

    @property
    def has_premium(self):
        for premium in self._premiums:
            if premium.is_valid:
                return True
        return False

    @property
    def premium_left(self):
        last_premium = get_indexed(self._premiums, -1)
        if last_premium is None:
            return None
        return self._premium

    @premium_left.setter
    def premium_left(self, data: int):
        self._premium = data

    def add_time(self, time: float):
        if not isinstance(time, (int, float)):
            raise ValueError("Muse be a int or a float!")
        premium_count = time
        if isinstance(time, float):
            premium_count = round(time)

        start_time = arrow.utcnow().timestamp()

        premium_intersect = -1
        for n, premium in enumerate(self._premiums):
            if premium.is_intersecting(start_time):
                premium_intersect = n

        if premium_intersect > -1:
            self._premiums[premium_intersect].add_duration(premium_count)
        else:
            self._premiums.append(FansubRSSPremium(start_time, premium_count))

        self._premiums.sort(key=lambda x: x.start)

    def exhaust_time(self):
        for premium in self._premiums:
            if premium.is_valid:
                premium.exhaust()
                break

    def set_indefinite(self):
        self._premiums = [FansubRSSPremium(-1, -1)]

    def time_left(self) -> timedelta | Literal[-1] | None:
        for premium in self._premiums:
            if premium.is_valid:
                if premium.is_infinite:
                    return -1
                time_left = premium.time_left
                if time_left is not None:
                    return timedelta(seconds=time_left)
        return None

    @classmethod
    def from_dict(cls, server_id: int | str, data: dict):
        parsed = []
        for feed in data.get("feeds", []):
            parsed.append(FansubRSSFeed.from_dict(feed))

        premium = data.get("premium", [])
        if isinstance(premium, (bool, int)):
            premium = [premium]
        parsed_prem = []
        for premi in premium:
            ppremi = FansubRSSPremium.from_dict(premi)
            if ppremi is not None:
                parsed_prem.append(ppremi)
        return cls(
            id=int(server_id),
            feeds=parsed,
            premiums=parsed_prem,
        )

    def serialize(self):
        serialized = []
        for feed in self.feeds:
            serialized.append(feed.serialize())
        premiums = []
        for premium in self._premiums:
            premiums.append(premium.serialize())
        return {
            "id": str(self.id),
            "feeds": serialized,
            "premium": premiums,
        }
