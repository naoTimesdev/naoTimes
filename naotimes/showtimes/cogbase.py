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

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union, cast

import arrow
import discord
from discord.ext import commands

from ..http import AnilistBucket
from ..models import showtimes as showmodel
from ._types import (
    AnilistAiringScheduleNode,
    AnilistAnimeFormat,
    AnilistAnimeInfoResult,
    AnilistAnimeScheduleResult,
)
from .models import Showtimes, ShowtimesEpisodeStatusChild

if TYPE_CHECKING:
    from ..bot import naoTimesBot

__all__ = ("ShowtimesCogsBases",)

StrInt = Union[str, int]

anifetch_query = """
query AnimeSchedule($id:Int!) {
    Media(id:$id,type:ANIME) {
        id
        format
        startDate {
            year
            month
            day
        }
        episodes
        airingSchedule {
            nodes {
                id
                episode
                airingAt
            }
        }
        nextAiringEpisode {
            timeUntilAiring
            episode
            airingAt
        }
    }
}

query AnimeInfo($id:Int) {
    Media(id:$id,type:ANIME) {
        id
        idMal
        title {
            romaji
            english
            native
        }
        coverImage {
            medium
            large
            extraLarge
            color
        }
        format
        episodes
        startDate {
            year
            month
            day
        }
        airingSchedule {
            nodes {
                id
                episode
                airingAt
            }
        }
        nextAiringEpisode {
            timeUntilAiring
            episode
            airingAt
        }
    }
}
"""


def is_minus(x: float) -> bool:
    """Essentials for quick testing"""
    return x < 0


def rgbhex_to_rgbint(hex_str: str | None, fallback: int = 0x1EB5A6) -> int:
    """Used for anilist color to convert to discord.py friendly color"""
    if not hex_str:
        return fallback
    hex_str = hex_str.replace("#", "").upper()
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return (256 * 256 * r) + (256 * g) + b


def parse_anilist_date(start_date: object) -> int:
    """Parse anilist date or normal date into timestamp.

    :param start_date: I'm bad at naming things
    :type start_date: dict
    :raises ValueError: If input only include one thing
    :return: UTC Timestamp
    :rtype: int
    """
    if not isinstance(start_date, dict):
        raise ValueError("Start date is not an object.")
    date_parts: list[tuple[str, int | None]] = [
        ("%Y", start_date.get("year")),
        ("%m", start_date.get("month")),
        ("%d", start_date.get("day")),
    ]
    present_parts = [(fmt, value) for fmt, value in date_parts if isinstance(value, int)]
    if len(present_parts) < 2:
        raise ValueError("Not enough data.")
    parsed_date = arrow.Arrow.strptime(
        "-".join(str(value) for _, value in present_parts), "-".join(fmt for fmt, _ in present_parts)
    )
    return parsed_date.int_timestamp


def get_episode_airing(nodes: list[AnilistAiringScheduleNode], episode: int) -> tuple[int | None, int | None]:
    """Get total episode of airing anime (using anilist data)"""
    if not nodes:
        return None, 1  # No data
    if len(nodes) == 1:
        return nodes[0].airingAt, nodes[0].episode
    for node in nodes:
        if node.episode == episode:
            return node.airingAt, node.episode
    return (
        nodes[-1].airingAt,
        nodes[-1].episode,
    )  # get latest airing data


def utctime_to_timeleft(x: int, language: str = "id") -> str:
    """parse anilist time to time-left format"""
    # Nasty hack to port old style in arrow.Arrow format
    timedata = arrow.get(x)

    # Extract the units numerically so the parsing does not depend on the locale's wording.
    delta_seconds = abs(round((timedata - arrow.utcnow()).total_seconds()))
    year_human = delta_seconds // 31536000
    day_human = delta_seconds // 86400
    hour_human = delta_seconds // 3600
    if year_human > 0:
        return timedata.humanize(locale=language, granularity=["year"])
    elif day_human > 0:
        if hour_human > 0:
            return timedata.humanize(locale=language, granularity=["day", "hour"])
        return timedata.humanize(locale=language, granularity=["day"])
    return timedata.humanize(locale=language)


@dataclass
class AnilistFailure:
    error: str | None = None


@dataclass
class AnilistSchedule:
    airing_at: int
    episode: int


AnilistSchedules = list[AnilistSchedule]


@dataclass
class AnilistInfo:
    id: int
    mal_id: int | None
    title: str
    cover_image: str
    cover_color: int
    format: AnilistAnimeFormat
    schedules: AnilistSchedules
    start_time: int


class ShowtimesCogsBases:
    def __init__(self, anibucket: AnilistBucket):
        self.anibucket = anibucket
        self.logger = logging.getLogger("Showtimes.CogsBase")

    def _parse_schedules_data(
        self,
        entries: AnilistAnimeScheduleResult | AnilistAnimeInfoResult,
        expected_episodes: int | None = None,
    ) -> AnilistSchedules | AnilistFailure:
        """Parse anilist data to anilist schedules"""
        ani_id = entries.id

        start_date = entries.startDate
        try:
            start_timestamp = parse_anilist_date(start_date)
        except ValueError:
            self.logger.error(f"Failed to parse start date for {ani_id}")
            return AnilistFailure(
                error="Waktu mulai tidak diketahui, dibutuhkan minimal tahun dan bulan untuk menambah proyek!"
            )

        airing_nodes = entries.airingSchedule.nodes
        episodes = entries.episodes or 0

        if not airing_nodes:
            self.logger.warning(f"No airing data for {ani_id}")
            airing_nodes = []
            airing_nodes.append(AnilistAiringScheduleNode(id=-1, airingAt=start_timestamp, episode=1))

        show_format = entries.format.lower()
        if expected_episodes is not None and expected_episodes < episodes:
            expected_episodes = episodes

        schedules: AnilistSchedules = []
        if expected_episodes is not None:
            for ep_num in range(1, expected_episodes + 1):
                if show_format in ["tv", "tv_short", "ona"]:
                    node = airing_nodes[ep_num - 1] if ep_num <= len(airing_nodes) else None
                    if node is None:
                        calc = 24 * 3600 * 7 * (ep_num - 1)
                        airing_at = start_timestamp + calc
                    else:
                        airing_at = node.airingAt
                    schedules.append(AnilistSchedule(airing_at=airing_at, episode=ep_num))
            if episodes > 0 and (not schedules or schedules[-1].episode != episodes):
                calc = start_timestamp + (24 * 3600 * 7 * (episodes - 1))
                schedules.append(AnilistSchedule(airing_at=calc, episode=episodes))

        return schedules

    async def anilist_get_schedules(self, ani_id: StrInt, expected_episodes: int | None = None):
        if isinstance(ani_id, str):
            ani_id = int(ani_id)

        self.logger.info(f"Fetching schedules for {ani_id}")
        full_data = await self.anibucket.handle(anifetch_query, {"id": ani_id}, "AnimeSchedule")
        if len(full_data.errors) > 0:
            self.logger.error("Error fetching anilist data")
            self.logger.error(full_data.errors)
            return AnilistFailure(error="Terjadi kesalahan ketika menghubungi Anilist")

        self.logger.info(f"Parsing schedule result for {ani_id}")
        if full_data.data is None:
            return AnilistFailure(error="Anilist tidak mengembalikan data jadwal")
        media_data = full_data.data.get("Media")
        if not isinstance(media_data, dict):
            return AnilistFailure(error="Anilist tidak mengembalikan data jadwal")
        return self._parse_schedules_data(cast(AnilistAnimeScheduleResult, media_data), expected_episodes)

    async def anilist_get_information(self, ani_id: StrInt):
        if isinstance(ani_id, str):
            ani_id = int(ani_id)

        self.logger.info(f"Fetching anime information for {ani_id}")
        full_data = await self.anibucket.handle(anifetch_query, {"id": ani_id}, "AnimeInfo")
        if len(full_data.errors) > 0:
            self.logger.error("Error fetching anilist data")
            self.logger.error(full_data.errors)
            return AnilistFailure(error="Terjadi kesalahan ketika menghubungi Anilist")

        self.logger.info(f"Parsing anime information for {ani_id}")
        if full_data.data is None:
            return AnilistFailure(error="Anilist tidak mengembalikan data anime")
        media_data = full_data.data.get("Media")
        if not isinstance(media_data, dict):
            return AnilistFailure(error="Anilist tidak mengembalikan data anime")
        entries = cast(AnilistAnimeInfoResult, media_data)

        selected_title = entries.title.romaji or entries.title.english or entries.title.native
        if not selected_title:
            return AnilistFailure(error="Judul gagal didapatkan, mohon coba lagi lain waktu!")

        selected_cover = entries.coverImage.extraLarge or entries.coverImage.large or entries.coverImage.medium
        if not selected_cover:
            return AnilistFailure(error="Cover gagal didapatkan, mohon coba lagi lain waktu!")
        cover_color = rgbhex_to_rgbint(entries.coverImage.color)

        start_date = entries.startDate
        try:
            start_timestamp = parse_anilist_date(start_date)
        except ValueError:
            self.logger.error(f"Failed to parse start date for {ani_id}")
            return AnilistFailure(
                error="Waktu mulai tidak diketahui, dibutuhkan minimal tahun dan bulan untuk menambah proyek!"
            )

        self.logger.info(f"Parsing schedule result for {ani_id}")
        schedules = self._parse_schedules_data(entries, 1)
        if isinstance(schedules, AnilistFailure):
            return schedules

        ani_info = AnilistInfo(
            entries.id,
            entries.get("idMal"),
            selected_title,
            selected_cover,
            cover_color,
            entries.format,
            schedules,
            start_timestamp,
        )
        return ani_info

    async def fetch_anilist(
        self,
        ani_id: StrInt,
        current_episode: StrInt | None = None,
        total_episode: StrInt | None = None,
        jadwal_only=False,
        return_only_time=False,
        language: str = "id",
    ):
        """A version 2.5 of the Anilist fetching function
        Used on most Showtimes command

        :param ani_id: Anilist ID
        :type ani_id: int
        :param current_ep: Current episode, defaults to None
        :type current_ep: Optional[Union[int, str]], optional
        :param total_episode: Total episode, defaults to None
        :type total_episode: Optional[Union[int, str]], optional
        :param return_time_data: Return time data only, defaults to False
        :type return_time_data: bool, optional
        :param jadwal_only: Return jadwal only, defaults to True
        :type jadwal_only: bool, optional
        :param return_only_time: Return only time, defaults to True
        :type return_only_time: bool, optional
        :return: Return results
        :rtype: Union[str, dict]
        """

        if isinstance(ani_id, str):
            ani_id = int(ani_id)
        if current_episode is None and (not return_only_time and not jadwal_only):
            raise ValueError("Current episode is None while the `return_only_xxx` attribute is False")

        full_data = await self.anibucket.handle(anifetch_query, {"id": ani_id})
        if len(full_data.errors) > 0:
            self.logger.error("An error occured")
            self.logger.error(full_data.errors)
            return "Terjadi kesalahan ketika menghubungi Anilist"

        raw_payload = full_data.data
        if raw_payload is None:
            return "Tidak ada hasil"

        media_data = raw_payload.get("Media")
        if not isinstance(media_data, dict):
            return "Tidak ada hasil"
        entries = cast(AnilistAnimeInfoResult, media_data)
        self.logger.info(f"Parsing info for {ani_id}")
        real_title = entries.title.romaji or entries.title.english or entries.title.native
        if not real_title:
            return "Judul anime tidak tersedia"
        compiled_data = {
            "id": str(entries.id),
            "idMal": str(entries.idMal) if entries.idMal is not None else None,
            "title": real_title,
        }
        compiled_data["poster_data"] = {
            "image": entries.coverImage.large,
            "color": rgbhex_to_rgbint(entries.coverImage.color),
        }

        if jadwal_only:
            air_data: dict[str, int | None] = {
                "time_until": None,
                "episode": None,
            }
            compiled_data["episode_status"] = None
            next_air_episode = entries.nextAiringEpisode
            if next_air_episode is not None:
                air_data["time_until"] = next_air_episode.timeUntilAiring
                air_data["episode"] = next_air_episode.episode
                compiled_data["episode_status"] = f"<t:{next_air_episode.airingAt}:R>"
            compiled_data["next_airing"] = air_data
            return compiled_data

        start_date = entries.startDate
        try:
            start_timestamp = parse_anilist_date(start_date)
        except ValueError as error:
            raise ValueError("`airing_start` is empty, we need more data so we can return properly") from error
        compiled_data["airing_start"] = start_timestamp

        if return_only_time:
            return compiled_data

        if isinstance(current_episode, str):
            current_episode = int(current_episode)
        if total_episode is not None and isinstance(total_episode, str):
            total_episode = int(total_episode)

        airing_nodes = entries.airingSchedule.nodes
        show_format = entries.format.lower()
        current_episode = int(current_episode) if current_episode is not None else None
        if current_episode is None:
            raise ValueError("Current episode is required for schedule results")
        airing_time, episode_number = get_episode_airing(airing_nodes, current_episode)
        if not airing_time:
            airing_time = start_timestamp
        if show_format in ["tv", "tv_short"] and episode_number is not None and episode_number != current_episode:
            if current_episode > episode_number:
                for _ in range(current_episode - episode_number):
                    airing_time += 7 * 24 * 3600
            elif episode_number > current_episode:
                for _ in range(episode_number - current_episode):
                    airing_time -= 7 * 24 * 3600

        episodes = entries.episodes or 0

        parsed_ani_time = utctime_to_timeleft(airing_time, language)
        compiled_data["episode_status"] = parsed_ani_time
        if total_episode is not None and total_episode < episodes:
            total_episode = episodes
        time_data = []
        if total_episode is not None:
            for x in range(total_episode):
                if show_format in ["tv", "tv_short"]:
                    node = airing_nodes[x] if x < len(airing_nodes) else None
                    if node is None:
                        time_data.append(start_timestamp + 24 * 3600 * 7 * x)
                    else:
                        time_data.append(node.airingAt)
                else:
                    time_data.append(start_timestamp + (24 * 3600 * 7 * x))
        compiled_data["time_data"] = time_data
        compiled_data["total_episodes"] = total_episode
        return compiled_data

    @staticmethod
    def parse_status(status: ShowtimesEpisodeStatusChild) -> str:
        status_lists = []
        status_keying = cast(showmodel._ShowtimesProjectEpisodeStatusProgressBaseDict, status.serialize())
        custom_data = cast(
            list[showmodel._ShowtimesProjectEpisodeStatusCustomProgressDict], status_keying.pop("custom", [])
        )
        qc_data = status_keying.pop("QC", False)
        QC_data = qc_data if isinstance(qc_data, bool) else False

        custom_data.sort(key=lambda x: x["key"])

        for custom in custom_data:
            status_keying[custom["key"]] = custom["done"]
        status_keying["QC"] = QC_data

        for work, c_stat in status_keying.items():
            wrap = "~~" if c_stat else "**"
            status_lists.append(f"{wrap}{work}{wrap}")
        return " ".join(status_lists)

    @staticmethod
    def get_roles(posisi: str) -> tuple[str | None, str]:
        posisi_kw = {
            "tl": "tl",
            "translation": "tl",
            "translate": "tl",
            "tlc": "tlc",
            "enc": "enc",
            "encode": "enc",
            "ed": "ed",
            "edit": "ed",
            "editing": "ed",
            "tm": "tm",
            "timing": "tm",
            "ts": "ts",
            "typeset": "ts",
            "typesett": "ts",
            "typesetting": "ts",
            "qc": "qc",
            "check": "qc",
        }
        posisi = posisi.lower()
        picked_roles = posisi_kw.get(posisi)
        if picked_roles is not None:
            picked_roles = picked_roles.upper()
        return picked_roles, posisi

    @staticmethod
    def normalize_role_name(posisi: str, staff: bool = False) -> str:
        posisi_kw = {
            "tl": "Terjemahan",
            "tlc": "Cek Terjemahan",
            "enc": "Olah Video",
            "ed": "Menggubah Skrip",
            "tm": "Selaras Waktu",
            "ts": "Tata Rias",
            "qc": "Tinjauan Akhir",
        }
        posisi_kw_staff = {
            "tl": "Translator",
            "tlc": "Pemeriksa Terjemahan",
            "enc": "Pengolah Video",
            "ed": "Penggubah Skrip",
            "tm": "Penata Waktu",
            "ts": "Penata Rias",
            "qc": "Pemeriksa Akhir",
        }
        posisi = posisi.lower()
        if staff:
            return posisi_kw_staff.get(posisi, posisi.upper())
        return posisi_kw.get(posisi, posisi.upper())

    @staticmethod
    def split_until_less_than(dataset: list[str]) -> list:
        """
        Split the !tagih stuff into chunked text because discord limitation

        :param dataset: The dataset to parse
        :type dataset: List[str]
        :return: Parsed text
        :rtype: list
        """

        text_format = "**Mungkin**: "
        concat_set = []
        finalized_sets = []
        first_run = True
        for data in dataset:
            if first_run:
                concat_set.append(data)
                check = text_format + ", ".join(concat_set)
                if len(check) >= 1995:
                    last_occured = concat_set.pop()
                    finalized_sets.append(concat_set)
                    concat_set = [last_occured]
                    first_run = False
            else:
                concat_set.append(data)
                if len(", ".join(concat_set)) >= 1995:
                    last_occured = concat_set.pop()
                    finalized_sets.append(concat_set)
                    concat_set = [last_occured]

        new_sets = []
        while True:
            if len(", ".join(concat_set)) >= 1995:
                new_sets.append(concat_set.pop())
            else:
                break
        if concat_set:
            finalized_sets.append(concat_set)
        if new_sets:
            finalized_sets.append(new_sets)

        return finalized_sets

    async def send_all_projects(self, ctx: commands.Context, dataset: Showtimes):
        if len(dataset.projects) < 1:
            self.logger.warning(f"{dataset.id}: no registered data on database.")
            return await ctx.send("**Tidak ada anime yang terdaftar di database**")

        all_title = list(map(lambda x: x.title, dataset.projects))
        complete_title = sorted(self.split_until_less_than(all_title))
        self.logger.info(f"{dataset.id}: Sending all registered anime.")

        first_time = True
        for data in complete_title:
            if first_time:
                await ctx.send(f"**Mungkin**: {', '.join(data)}")
                first_time = False
            else:
                await ctx.send(", ".join(data))

    async def announce_embed(self, bot: naoTimesBot, channel: int | None, embed: discord.Embed):
        if not isinstance(channel, int):
            return
        kanal_target = bot.get_channel(channel)
        if not isinstance(kanal_target, discord.TextChannel):
            self.logger.warning(f"{channel}: unknown channel.")
            return
        try:
            self.logger.info(f"Trying to sent announcement to {kanal_target}")
            await kanal_target.send(embed=embed)
        except discord.Forbidden:
            self.logger.error(
                f"Failed to sent announcement to channel {kanal_target} because missing permission",
            )
        except discord.HTTPException as e:
            self.logger.error(f"Failed to sent announcement to channel {kanal_target}", exc_info=e)
