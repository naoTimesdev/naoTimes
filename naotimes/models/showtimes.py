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

from enum import Enum
from typing import TypedDict, Union

from bson import ObjectId
from odmantic import EmbeddedModel, Field, Model
from pydantic import field_validator

AnyNum = Union[int, float]


def _ints_to_str(value):
    """Existing documents and the app mix ``int`` and ``str`` Discord IDs.

    pydantic 1 silently converted ``int`` to ``str`` for ``str`` fields, pydantic 2 refuses.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [str(v) if isinstance(v, int) and not isinstance(v, bool) else v for v in value]
    return value


class _Embedded(EmbeddedModel):
    """Base for embedded models.

    Existing documents were written before some keys existed (e.g. ``custom``), so missing keys
    must be filled from the default factories while parsing a raw document (odmantic 1.x
    doesn't do that by default). The app also keeps IDs as ints while the schema stores strings,
    pydantic 1 converted those silently so we ask pydantic 2 to do the same.
    """

    model_config = {"parse_doc_with_default_factories": True}


__all__ = (
    "EpisodeStatusProgressSchema",
    "EpisodeStatusSchema",
    "ShowAdminSchema",
    "ShowAnimeAssigneeSchema",
    "ShowAnimeAssignmentsSchema",
    "ShowAnimeFSDBSchema",
    "ShowAnimePosterSchema",
    "ShowAnimeSchema",
    "ShowUIPrivilege",
    "ShowtimesCollabConfirmSchema",
    "ShowtimesDict",
    "ShowtimesSchema",
    "ShowtimesUISchema",
)


class EpisodeStatusCustomProgressSchema(_Embedded):
    key: str
    name: str
    done: bool = Field(default=False)


class EpisodeStatusProgressSchema(_Embedded):
    TL: bool = Field(default=False)
    TLC: bool = Field(default=False)
    ENC: bool = Field(default=False)
    ED: bool = Field(default=False)
    TM: bool = Field(default=False)
    TS: bool = Field(default=False)
    QC: bool = Field(default=False)
    custom: list[EpisodeStatusCustomProgressSchema] = Field(default_factory=list)


class EpisodeStatusSchema(_Embedded):
    episode: int
    is_done: bool
    progress: EpisodeStatusProgressSchema = Field(default_factory=EpisodeStatusProgressSchema)
    airtime: AnyNum | None = None
    delay_reason: str | None = None


class ShowAnimeAssigneeSchema(_Embedded):
    @field_validator("id", mode="before")
    @classmethod
    def _coerce_ids(cls, value):
        return _ints_to_str(value)

    id: str | None = None
    name: str | None = None


class ShowAnimeAssigneeCustomSchema(_Embedded):
    key: str
    name: str
    person: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)


class ShowAnimeAssignmentsSchema(_Embedded):
    TL: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    TLC: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    ENC: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    ED: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    TM: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    TS: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    QC: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    custom: list[ShowAnimeAssigneeCustomSchema] = Field(default_factory=list)


class ShowAnimePosterSchema(_Embedded):
    url: str
    color: AnyNum | None = None


class ShowAnimeFSDBSchema(_Embedded):
    id: int | None = None
    ani_id: int | None = None


class ShowAnimeSchema(_Embedded):
    @field_validator("id", "role_id", "kolaborasi", mode="before")
    @classmethod
    def _coerce_ids(cls, value):
        return _ints_to_str(value)

    id: str
    mal_id: int | None = None
    title: str
    role_id: str | None = None
    start_time: AnyNum | None = None
    assignments: ShowAnimeAssignmentsSchema = Field(default_factory=ShowAnimeAssignmentsSchema)
    status: list[EpisodeStatusSchema] = Field(default_factory=list)
    poster_data: ShowAnimePosterSchema
    # Stored as a plain dict (``{"id": int, "ani_id": int}``) or ``null``: odmantic 1.x rejects an
    # explicit ``null`` for an optional *embedded model*, which is how existing documents store it.
    fsdb_data: dict | None = None
    aliases: list[str] = Field(default_factory=list)
    kolaborasi: list[str] = Field(default_factory=list)
    last_update: AnyNum


class ShowtimesCollabConfirmSchema(_Embedded):
    @field_validator("id", "server_id", "anime_id", mode="before")
    @classmethod
    def _coerce_ids(cls, value):
        return _ints_to_str(value)

    id: str
    server_id: str
    anime_id: str


class ShowtimesSchema(Model):
    @field_validator("id", "serverowner", "announce_channel", mode="before")
    @classmethod
    def _coerce_ids(cls, value):
        return _ints_to_str(value)

    id: str
    # Bind the _id to mongo_id
    mongo_id: ObjectId = Field(primary_field=True)
    name: str | None = None
    fsdb_id: int | None = None
    serverowner: list[str] = Field(default_factory=list)
    announce_channel: str | None = None
    anime: list[ShowAnimeSchema] = Field(default_factory=list)
    konfirmasi: list[ShowtimesCollabConfirmSchema] = Field(default_factory=list)

    model_config = {"collection": "showtimesdatas", "parse_doc_with_default_factories": True}


class ShowAdminSchema(Model):
    @field_validator("id", "servers", mode="before")
    @classmethod
    def _coerce_ids(cls, value):
        return _ints_to_str(value)

    id: str
    # Bind the _id to mongo_id
    mongo_id: ObjectId = Field(primary_field=True)
    servers: list[str] = Field(default_factory=list)

    model_config = {"collection": "showtimesadmin", "parse_doc_with_default_factories": True}


class ShowUIPrivilege(str, Enum):
    ADMIN = "owner"
    SERVER = "server"


class ShowtimesUISchema(Model):
    @field_validator("id", mode="before")
    @classmethod
    def _coerce_ids(cls, value):
        return _ints_to_str(value)

    id: str
    # Bind the _id to mongo_id
    mongo_id: ObjectId | None = Field(primary_field=True)
    name: str | None
    secret: str
    privilege: ShowUIPrivilege

    model_config = {"collection": "showtimesuilogin", "parse_doc_with_default_factories": True}


class _ShowtimesProjectEpisodeStatusCustomProgressDict(TypedDict):
    key: str
    name: str
    done: bool


class _ShowtimesProjectEpisodeStatusProgressBaseDict(TypedDict):
    TL: bool
    TLC: bool
    ENC: bool
    ED: bool
    TM: bool
    TS: bool
    QC: bool


class _ShowtimesProjectEpisodeStatusProgressDict(_ShowtimesProjectEpisodeStatusProgressBaseDict):
    custom: list[_ShowtimesProjectEpisodeStatusCustomProgressDict]


class ShowtimesProjectEpisodeStatusDict(TypedDict):
    episode: int
    is_done: bool
    progress: _ShowtimesProjectEpisodeStatusProgressDict
    airtime: AnyNum | None
    delay_reason: str | None


class _ShowtimesProjectAssigneeOptionalDict(TypedDict, total=False):
    name: str


class _ShowtimesProjectAssigneeDict(_ShowtimesProjectAssigneeOptionalDict):
    id: str | None


class _ShowtimesProjectAssigneeCustomDict(TypedDict):
    key: str
    name: str
    person: _ShowtimesProjectAssigneeDict


class _ShowtimesProjectAssignmentsDict(TypedDict):
    TL: _ShowtimesProjectAssigneeDict
    TLC: _ShowtimesProjectAssigneeDict
    ENC: _ShowtimesProjectAssigneeDict
    ED: _ShowtimesProjectAssigneeDict
    TM: _ShowtimesProjectAssigneeDict
    TS: _ShowtimesProjectAssigneeDict
    QC: _ShowtimesProjectAssigneeDict
    custom: list[_ShowtimesProjectAssigneeCustomDict]


class ShowtimesCollabConfirmDict(TypedDict):
    id: str
    server_id: str
    anime_id: str


class _ShowtimesProjectPosterDict(TypedDict):
    url: str
    color: AnyNum | None


class _ShowtimesProjectFSDBDict(TypedDict):
    id: int | None
    ani_id: int | None


class _ShowtimesProjectOptionalDict(TypedDict, total=False):
    fsdb_data: _ShowtimesProjectFSDBDict


class ShowtimesProjectDict(_ShowtimesProjectOptionalDict):
    id: str
    mal_id: int | None
    title: str
    role_id: str | None
    start_time: AnyNum | None
    assignments: _ShowtimesProjectAssignmentsDict
    status: list[ShowtimesProjectEpisodeStatusDict]
    poster_data: _ShowtimesProjectPosterDict
    aliases: list[str]
    kolaborasi: list[str]
    last_update: AnyNum


class _ShowtimesDictOptional(TypedDict, total=False):
    _id: str
    mongo_id: str
    name: str
    fsdb_id: int
    announce_channel: str


class ShowtimesDict(_ShowtimesDictOptional):
    id: str
    serverowner: list[str]
    anime: list[ShowtimesProjectDict]
    konfirmasi: list[ShowtimesCollabConfirmDict]
