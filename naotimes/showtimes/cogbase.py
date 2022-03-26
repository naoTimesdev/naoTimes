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

import logging
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

import arrow
import disnake
from disnake.ext import commands

from ..http import AnilistBucket
from ..utils import complex_walk
from .models import Showtimes, ShowtimesEpisodeStatusChild

if TYPE_CHECKING:
    from ..bot import naoTimesBot

__all__ = ("ShowtimesCogsBases",)

StrInt = Union[str, int]

anifetch_query = """
query ($id: Int!) {
    Media(id: $id, type: ANIME) {
        id
        idMal
        title {
            romaji
            english
        }
        coverImage {
            large
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
            airingAt
            episode
        }
    }
}
"""


def is_minus(x: Union[int, float]) -> bool:
    """Essentials for quick testing"""
    return x < 0


def rgbhex_to_rgbint(hex_str: str, fallback: int = 0x1EB5A6) -> int:
    """Used for anilist color to convert to discord.py friendly color"""
    if not hex_str:
        return fallback
    hex_str = hex_str.replace("#", "").upper()
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return (256 * 256 * r) + (256 * g) + b


def parse_anilist_date(start_date: dict) -> int:
    """Parse anilist date or normal date into timestamp.

    :param start_date: I'm bad at naming things
    :type start_date: dict
    :raises ValueError: If input only include one thing
    :return: UTC Timestamp
    :rtype: int
    """
    ext_dt = []
    date_dt = []
    try:
        yyyy = start_date["year"]
        if yyyy is not None:
            ext_dt.append("%Y")
            date_dt.append(str(yyyy))
    except KeyError:
        pass
    try:
        mm = start_date["month"]
        if mm is not None:
            ext_dt.append("%m")
            date_dt.append(str(mm))
    except KeyError:
        pass
    try:
        dd = start_date["day"]
        if dd is not None:
            ext_dt.append("%d")
            date_dt.append(str(dd))
    except KeyError:
        pass
    if not ext_dt or len(date_dt) < 2:
        raise ValueError("Not enough data.")
    parsed_date = arrow.Arrow.strptime("-".join(date_dt), "-".join(ext_dt))
    return parsed_date.int_timestamp


def get_episode_airing(nodes: dict, episode: str) -> tuple:
    """Get total episode of airing anime (using anilist data)"""
    if not nodes:
        return None, 1  # No data
    if len(nodes) == 1:
        return (
            nodes[0]["airingAt"],
            nodes[-1]["episode"],
        )  # get the only airing data
    for i in nodes:
        if i["episode"] == int(episode):
            return i["airingAt"], i["episode"]  # return episodic data
    return (
        nodes[-1]["airingAt"],
        nodes[-1]["episode"],
    )  # get latest airing data


def utctime_to_timeleft(x: int) -> str:
    """parse anilist time to time-left format"""
    # Nasty hack to port old style in arrow.Arrow format
    timedata = arrow.get(x)
    year_human = int(timedata.humanize(locale="id", only_distance=True, granularity=["year"]).split()[0])
    day_human = int(timedata.humanize(locale="id", only_distance=True, granularity=["day"]).split()[0])
    hour_human = int(timedata.humanize(locale="id", only_distance=True, granularity=["hour"]).split()[0])
    if year_human > 0:
        return timedata.humanize(locale="id", granularity=["year"])
    elif day_human > 0:
        if hour_human > 0:
            return timedata.humanize(locale="id", granularity=["day", "hour"])
        return timedata.humanize(locale="id", granularity=["day"])
    return timedata.humanize(locale="id")


class ShowtimesCogsBases:
    def __init__(self, anibucket: AnilistBucket):
        self.anibucket = anibucket
        self.logger = logging.getLogger("Showtimes.CogsBase")

    async def fetch_anilist(
        self,
        ani_id: StrInt,
        current_episode: Optional[StrInt] = None,
        total_episode: Optional[StrInt] = None,
        jadwal_only=False,
        return_only_time=False,
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

        raw_data = full_data.data
        if raw_data is None:
            return "Tidak ada hasil"

        entries = raw_data["Media"]
        self.logger.info(f"Parsing info for {ani_id}")
        real_title = complex_walk(entries, "title.romaji")
        if real_title is None:
            real_title = complex_walk(entries, "title.english")
        compiled_data = {"id": str(entries["id"]), "idMal": str(entries["idMal"]), "title": real_title}
        compiled_data["poster_data"] = {
            "image": complex_walk(entries, "coverImage.large"),
            "color": rgbhex_to_rgbint(complex_walk(entries, "coverImage.color")),
        }

        if jadwal_only:
            air_data = {
                "time_until": None,
                "episode": None,
            }
            compiled_data["episode_status"] = None
            next_air_episode = complex_walk(entries, "nextAiringEpisode")
            if next_air_episode is not None:
                air_data["time_until"] = complex_walk(next_air_episode, "timeUntilAiring")
                air_data["episode"] = complex_walk(next_air_episode, "episode")
                airing_at = complex_walk(next_air_episode, "airingAt")
                if airing_at is not None:
                    compiled_data["episode_status"] = utctime_to_timeleft(airing_at)
            compiled_data["next_airing"] = air_data
            return compiled_data

        start_date = entries["startDate"]
        try:
            start_timestamp = parse_anilist_date(start_date)
            compiled_data["airing_start"] = start_timestamp
        except ValueError:
            compiled_data["airing_start"] = None

        if compiled_data["airing_start"] is None:
            raise ValueError("`airing_start` is empty, we need more data so we can return properly")

        if return_only_time:
            return compiled_data

        if isinstance(current_episode, str):
            current_episode = int(current_episode)
        if total_episode is not None and isinstance(total_episode, str):
            total_episode = int(total_episode)

        airing_nodes = complex_walk(entries, "airingSchedule.nodes")
        show_format = entries["format"].lower()
        airing_time, episode_number = get_episode_airing(airing_nodes, current_episode)
        if not airing_time:
            airing_time = start_timestamp
        if show_format in ["tv", "tv_short"] and episode_number != current_episode:
            if current_episode > episode_number:
                for _ in range(current_episode - episode_number):
                    airing_time += 7 * 24 * 3600
            elif episode_number > current_episode:
                for _ in range(episode_number - current_episode):
                    airing_time -= 7 * 24 * 3600

        episodes = complex_walk(entries, "episodes")
        if episodes is None:
            episodes = 0

        if not airing_nodes:
            airing_nodes = []
            temp_nodes = {}
            temp_nodes["airingAt"] = start_timestamp
            airing_nodes.append(temp_nodes)

        parsed_ani_time = utctime_to_timeleft(airing_time)
        compiled_data["episode_status"] = parsed_ani_time
        if total_episode is not None and total_episode < episodes:
            total_episode = episodes
        time_data = []
        if total_episode is not None:
            for x in range(total_episode):
                if show_format in ["tv", "tv_short"]:
                    noda = complex_walk(airing_nodes, f"{x}.airingAt")
                    if noda is None:
                        calc = 24 * 3600 * 7 * x
                        noda = airing_nodes[0]["airingAt"] + calc
                    time_data.append(noda)
                else:
                    time_data.append(start_timestamp * (24 * 3600 * 7 * x))
        compiled_data["time_data"] = time_data
        compiled_data["total_episodes"] = total_episode
        return compiled_data

    @staticmethod
    def parse_status(status: ShowtimesEpisodeStatusChild) -> str:
        status_lists = []
        for work, c_stat in status:
            wrap = "~~" if c_stat else "**"
            status_lists.append(f"{wrap}{work}{wrap}")
        return " ".join(status_lists)

    @staticmethod
    def get_roles(posisi: str) -> Tuple[str, str]:
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
    def split_until_less_than(dataset: List[str]) -> list:
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

    async def announce_embed(self, bot: naoTimesBot, channel: Optional[int], embed: disnake.Embed):
        if not isinstance(channel, int):
            return
        kanal_target = bot.get_channel(channel)
        if not isinstance(kanal_target, disnake.TextChannel):
            self.logger.warning(f"{channel}: unknown channel.")
            return
        try:
            self.logger.info(f"Trying to sent announcement to {kanal_target}")
            await kanal_target.send(embed=embed)
        except disnake.Forbidden:
            self.logger.error(
                f"Failed to sent announcement to channel {kanal_target} because missing permission",
            )
        except disnake.HTTPException as e:
            self.logger.error(f"Failed to sent announcement to channel {kanal_target}", exc_info=e)
