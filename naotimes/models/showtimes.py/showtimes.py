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
from typing import List, Optional, TypedDict, Union

from bson import ObjectId
from odmantic import EmbeddedModel, Field, Model

AnyNum = Union[int, float]

__all__ = (
    "EpisodeStatusProgressSchema",
    "EpisodeStatusSchema",
    "ShowAnimeAssigneeSchema",
    "ShowAnimeAssignmentsSchema",
    "ShowAnimePosterSchema",
    "ShowAnimeFSDBSchema",
    "ShowAnimeSchema",
    "ShowtimesCollabConfirmSchema",
    "ShowtimesSchema",
    "ShowAdminSchema",
    "ShowtimesUISchema",
    "ShowUIPrivilege",
    "ShowtimesDict",
)


class EpisodeStatusProgressSchema(EmbeddedModel):
    TL: bool = Field(default=False)
    TLC: bool = Field(default=False)
    ENC: bool = Field(default=False)
    ED: bool = Field(default=False)
    TM: bool = Field(default=False)
    TS: bool = Field(default=False)
    QC: bool = Field(default=False)


class EpisodeStatusSchema(EmbeddedModel):
    episode: int
    is_done: bool
    progress: EpisodeStatusProgressSchema = Field(default=EpisodeStatusProgressSchema())
    airtime: Optional[AnyNum]
    delay_reason: Optional[str]


class ShowAnimeAssigneeSchema(EmbeddedModel):
    id: Optional[str]
    name: Optional[str]


class ShowAnimeAssignmentsSchema(EmbeddedModel):
    TL: ShowAnimeAssigneeSchema = Field(default=ShowAnimeAssigneeSchema())
    TLC: ShowAnimeAssigneeSchema = Field(default=ShowAnimeAssigneeSchema())
    ENC: ShowAnimeAssigneeSchema = Field(default=ShowAnimeAssigneeSchema())
    ED: ShowAnimeAssigneeSchema = Field(default=ShowAnimeAssigneeSchema())
    TM: ShowAnimeAssigneeSchema = Field(default=ShowAnimeAssigneeSchema())
    TS: ShowAnimeAssigneeSchema = Field(default=ShowAnimeAssigneeSchema())
    QC: ShowAnimeAssigneeSchema = Field(default=ShowAnimeAssigneeSchema())


class ShowAnimePosterSchema(EmbeddedModel):
    url: str
    color: Optional[AnyNum]


class ShowAnimeFSDBSchema(EmbeddedModel):
    id: Optional[int]
    ani_id: Optional[int]


class ShowAnimeSchema(EmbeddedModel):
    id: str
    mal_id: Optional[int]
    title: str
    role_id: Optional[str]
    start_time: Optional[AnyNum]
    assignments: ShowAnimeAssignmentsSchema = Field(default=ShowAnimeAssignmentsSchema())
    status: List[EpisodeStatusSchema] = Field(default=[])
    poster_data: ShowAnimePosterSchema
    fsdb_data: Optional[ShowAnimeFSDBSchema]
    aliases: List[str] = Field(default=[])
    kolaborasi: List[str] = Field(default=[])
    last_update: AnyNum


class ShowtimesCollabConfirmSchema(EmbeddedModel):
    id: str
    server_id: str
    anime_id: str


class ShowtimesSchema(Model):
    id: str
    # Bind the _id to mongo_id
    mongo_id: ObjectId = Field(primary_field=True)
    name: Optional[str]
    fsdb_id: Optional[int]
    serverowner: List[str] = Field(default=[])
    announce_channel: Optional[str]
    anime: List[ShowAnimeSchema] = Field(default=[])
    konfirmasi: List[ShowtimesCollabConfirmSchema] = Field(default=[])

    class Config:
        collection = "showtimesdatas"


class ShowAdminSchema(Model):
    id: str
    # Bind the _id to mongo_id
    mongo_id: ObjectId = Field(primary_field=True)
    servers: List[str] = Field(default=[])

    class Config:
        collection = "showtimesadmin"


class ShowUIPrivilege(str, Enum):
    ADMIN = "owner"
    SERVER = "server"


class ShowtimesUISchema(Model):
    id: str
    # Bind the _id to mongo_id
    mongo_id: Optional[ObjectId] = Field(primary_field=True)
    name: Optional[str]
    secret: str
    privilege: ShowUIPrivilege

    class Config:
        collection = "showtimesuilogin"


class _ShowtimesProjectEpisodeStatusProgressDict(TypedDict):
    TL: bool
    TLC: bool
    ENC: bool
    ED: bool
    TM: bool
    TS: bool
    QC: bool


class ShowtimesProjectEpisodeStatusDict(TypedDict):
    episode: int
    is_done: bool
    progress: _ShowtimesProjectEpisodeStatusProgressDict
    airtime: Optional[AnyNum]
    delay_reason: Optional[str]


class _ShowtimesProjectAssigneeOptionalDict(TypedDict, total=False):
    name: str


class _ShowtimesProjectAssigneeDict(_ShowtimesProjectAssigneeOptionalDict):
    id: Optional[str]


class _ShowtimesProjectAssignmentsDict(TypedDict):
    TL: _ShowtimesProjectAssigneeDict
    TLC: _ShowtimesProjectAssigneeDict
    ENC: _ShowtimesProjectAssigneeDict
    ED: _ShowtimesProjectAssigneeDict
    TM: _ShowtimesProjectAssigneeDict
    TS: _ShowtimesProjectAssigneeDict
    QC: _ShowtimesProjectAssigneeDict


class ShowtimesCollabConfirmDict(TypedDict):
    id: str
    server_id: str
    anime_id: str


class _ShowtimesProjectPosterDict(TypedDict):
    url: str
    color: Optional[AnyNum]


class _ShowtimesProjectFSDBDict(TypedDict):
    id: Optional[int]
    ani_id: Optional[int]


class _ShowtimesProjectOptionalDict(TypedDict, total=False):
    fsdb_data: _ShowtimesProjectFSDBDict


class ShowtimesProjectDict(_ShowtimesProjectOptionalDict):
    id: str
    mal_id: Optional[int]
    title: str
    role_id: Optional[str]
    start_time: Optional[AnyNum]
    assignments: _ShowtimesProjectAssignmentsDict
    status: List[ShowtimesProjectEpisodeStatusDict]
    poster_data: _ShowtimesProjectPosterDict
    aliases: List[str]
    kolaborasi: List[str]
    last_update: AnyNum


class _ShowtimesDictOptional(TypedDict, total=False):
    _id: str
    mongo_id: str
    name: str
    fsdb_id: int
    announce_channel: str


class ShowtimesDict(_ShowtimesDictOptional):
    id: str
    serverowner: List[str]
    anime: List[ShowtimesProjectDict]
    konfirmasi: List[ShowtimesCollabConfirmDict]
