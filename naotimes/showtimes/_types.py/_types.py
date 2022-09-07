from typing import Generic, List, Literal, Optional, TypeVar, Union

from ..utils import AttributeDict

# Bound a TypeVar to a specific type.
AT = TypeVar("AT")

AnilistAnimeFormat = Literal[
    "TV",
    "TV_SHORT",
    "MOVIE",
    "SPECIAL",
    "OVA",
    "ONA",
    "MUSIC",
]
AnilistBooksFormat = Literal["MANGA", "NOVEL", "ONE_SHOT"]
AnilistFormat = Union[AnilistAnimeFormat, AnilistBooksFormat]


class AnilistFuzzyDate(AttributeDict):
    year: Optional[str]
    month: Optional[str]
    day: Optional[str]


class AnilistAiringScheduleNode(AttributeDict):
    id: int
    episode: int
    airingAt: int


class AnilistAiringSchedules(AttributeDict):
    nodes: List[AnilistAiringScheduleNode]


class AnilistCoverImage(AttributeDict):
    medium: str
    large: str
    extraLarge: Optional[str]
    # Hexadecimal color code.
    color: str


class AnilistTitle(AttributeDict):
    romaji: str
    english: str
    native: str


class AnilistAnimeScheduleResult(AttributeDict):
    id: int
    format: AnilistFormat
    episodes: Optional[int]
    startDate: AnilistFuzzyDate
    airingSchedule: AnilistAiringSchedules


class AnilistAnimeInfoResult(AnilistAnimeScheduleResult):
    idMal: Optional[int]
    title: AnilistTitle
    coverImage: AnilistCoverImage


class AnilistQueryMedia(AttributeDict, Generic[AT]):
    Media: AT
