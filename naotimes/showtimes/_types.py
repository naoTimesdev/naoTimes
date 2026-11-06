from typing import Generic, Literal, TypeVar, Union

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
    year: int | None
    month: int | None
    day: int | None


class AnilistAiringScheduleNode(AttributeDict):
    id: int
    episode: int
    airingAt: int


class AnilistAiringSchedules(AttributeDict):
    nodes: list[AnilistAiringScheduleNode]


class AnilistCoverImage(AttributeDict):
    medium: str | None
    large: str | None
    extraLarge: str | None
    # Hexadecimal color code.
    color: str | None


class AnilistTitle(AttributeDict):
    romaji: str | None
    english: str | None
    native: str | None


class AnilistNextAiringEpisode(AttributeDict):
    timeUntilAiring: int
    episode: int
    airingAt: int


class AnilistAnimeScheduleResult(AttributeDict):
    id: int
    format: AnilistAnimeFormat
    episodes: int | None
    startDate: AnilistFuzzyDate
    airingSchedule: AnilistAiringSchedules
    nextAiringEpisode: AnilistNextAiringEpisode | None


class AnilistAnimeInfoResult(AnilistAnimeScheduleResult):
    idMal: int | None
    title: AnilistTitle
    coverImage: AnilistCoverImage


class AnilistQueryMedia(AttributeDict, Generic[AT]):
    Media: AT
