import asyncio
import glob
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import aiohttp
import discord

from nthelper.utils import read_files, write_files

showlog = logging.getLogger("cogs.showtimes_module.base")

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


class AniTimeParseError(Exception):
    pass


def is_minus(x: Union[int, float]) -> bool:
    """Essentials for quick testing"""
    return x < 0


def rgbhex_to_rgbint(hex_str: str) -> int:
    """Used for anilist color to convert to discord.py friendly color"""
    if not hex_str:
        return 0x1EB5A6
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
        raise AniTimeParseError("Not enough data.")
    parsed_date = (
        datetime.strptime("-".join(date_dt), "-".join(ext_dt)).replace(tzinfo=timezone.utc).timestamp()
    )
    return int(round(parsed_date))


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
    delta_time = datetime.now(tz=timezone.utc).timestamp() - x
    sec = timedelta(seconds=abs(delta_time))
    d = datetime(1, 1, 1) + sec

    if d.year - 1 >= 1:
        if is_minus(x):
            return "{} tahun yang lalu".format(d.year - 1)
        return "{} tahun lagi".format(d.year - 1)
    if d.year - 1 <= 0 and d.month - 1 >= 1:
        if is_minus(x):
            return "{} bulan yang lalu".format(d.month - 1)
        return "{} bulan lagi".format(d.month - 1)
    if d.day - 1 <= 0 and d.hour > 0:
        if is_minus(x):
            return "{} jam yang lalu".format(d.hour)
        return "{} jam lagi".format(d.hour)
    if d.hour <= 0 and d.day - 1 <= 0:
        if d.minute <= 3:
            if is_minus(x):
                return "Beberapa menit yang lalu"
            return "Beberapa menit lagi"
        if is_minus(x):
            return "{} menit yang lalu".format(d.minute)
        return "{} menit lagi".format(d.minute)

    if d.hour <= 0:
        if is_minus(x):
            return "{} hari yang lalu".format(d.day - 1)
        return "{} hari lagi".format(d.day - 1)
    if is_minus(x):
        return "{} hari dan {} jam yang lalu".format(d.day - 1, d.hour)
    return "{} hari dan {} jam lagi".format(d.day - 1, d.hour)


async def fetch_anilist(
    ani_id,
    current_ep: Optional[Union[int, str]] = None,
    total_episode: Optional[Union[int, str]] = None,
    return_time_data=False,
    jadwal_only=False,
    return_only_time=False,
) -> Union[str, dict]:
    """A version 2 of Anilist fetching function
    Used on most of the Showtimes command.

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
    if current_ep is None and (not return_only_time and not jadwal_only):
        raise ValueError("fetch_anilist: current_ep is none while the other return_only are False.")
    query_to_send = {"query": anifetch_query, "variables": {"id": ani_id}}
    api_link = "https://graphql.anilist.co"
    showlog.info(f"fetching information for id: {ani_id}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_link, json=query_to_send) as resp:
                try:
                    data = await resp.json()
                except IndexError:
                    return "Tidak dapat memparsing hasil dari request API Anilist."
                if resp.status != 200:
                    if resp.status == 404:
                        return "Anilist tidak dapat menemukan anime tersebut."
                    if resp.status == 500:
                        return "Anilist mengalami kesalahan internal, mohon coba sesaat lagi."
                try:
                    entry = data["data"]["Media"]
                except IndexError:
                    return "Tidak ada hasil."
        except aiohttp.ClientError:
            return "Terjadi kesalahan koneksi."

    showlog.info(f"parsing info for {ani_id}")
    compiled_data = {
        "id": entry["id"],
        "idMal": entry["idMal"],
        "title": entry["title"]["romaji"],
    }
    if jadwal_only:
        air_data = {
            "time_until": None,
            "episode": None,
        }
        compiled_data["episode_status"] = None
        if "nextAiringEpisode" in entry and entry["nextAiringEpisode"] is not None:
            next_airing = entry["nextAiringEpisode"]
            try:
                time_until = next_airing["timeUntilAiring"]
                air_data["time_until"] = time_until
            except KeyError:
                air_data["time_until"] = None
            try:
                next_episode = next_airing["episode"]
                air_data["episode"] = next_episode
            except KeyError:
                air_data["episode"] = None
            if next_airing["airingAt"] is not None:
                compiled_data["episode_status"] = utctime_to_timeleft(next_airing["airingAt"])
        compiled_data["next_airing"] = air_data
        return compiled_data

    compiled_data["poster_data"] = {
        "image": entry["coverImage"]["large"],
        "color": rgbhex_to_rgbint(entry["coverImage"]["color"]),
    }
    start_date = entry["startDate"]
    try:
        start_timestamp = parse_anilist_date(start_date)
        compiled_data["airing_start"] = start_timestamp
    except AniTimeParseError:
        compiled_data["airing_start"] = None

    if return_only_time:
        if compiled_data["airing_start"] is None:
            raise ValueError("airing_start is empty, need more data.")
        return compiled_data

    if isinstance(current_ep, str):
        current_ep = int(current_ep)
    if total_episode is not None:
        if isinstance(total_episode, str):
            total_episode = int(total_episode)

    airing_time_nodes = entry["airingSchedule"]["nodes"]
    show_format = entry["format"].lower()
    airing_time, episode_number = get_episode_airing(airing_time_nodes, current_ep)  # type: ignore
    if not airing_time:
        airing_time = start_timestamp
    if show_format in ["tv", "tv_short"]:
        if episode_number != current_ep:
            if current_ep > episode_number:
                for _ in range(current_ep - episode_number):
                    airing_time += 7 * 24 * 3600
            elif episode_number > current_ep:
                for _ in range(episode_number - current_ep):
                    airing_time -= 7 * 24 * 3600

    try:
        episodes = entry["episodes"]
        if not episodes:
            episodes = 0
    except (KeyError, IndexError):
        episodes = 0

    if not airing_time_nodes:
        airing_time_nodes = []
        temporary_nodes = {}
        temporary_nodes["airingAt"] = start_timestamp
        airing_time_nodes.append(temporary_nodes)

    parsed_ani_time = utctime_to_timeleft(airing_time)
    compiled_data["episode_status"] = parsed_ani_time
    if return_time_data:
        if total_episode is not None and total_episode < episodes:
            total_episode = episodes
        time_data = []
        if show_format in ["tv", "tv_short"]:
            for x in range(total_episode):  # type: ignore
                try:
                    time_data.append(airing_time_nodes[x]["airingAt"])
                except IndexError:  # Out of range stuff ;_;
                    calc = 24 * 3600 * 7 * x
                    time_data.append(airing_time_nodes[0]["airingAt"] + calc)
        else:
            for x in range(total_episode):  # type: ignore
                time_data.append(start_timestamp + (x * 7 * 24 * 3600))
        compiled_data["time_data"] = time_data
        compiled_data["total_episodes"] = total_episode
    return compiled_data


def get_last_updated(oldtime: int) -> str:
    """
    Get last updated time from naoTimes database
    and convert it to "passed time"
    """
    current_time = datetime.now()
    old_dt = datetime.utcfromtimestamp(oldtime)
    delta_time = current_time - old_dt

    days_passed_by = delta_time.days
    seconds_passed = delta_time.total_seconds()
    if seconds_passed < 60:
        text = "Beberapa detik yang lalu"
    elif seconds_passed < 180:
        text = "Beberapa menit yang lalu"
    elif seconds_passed < 3600:
        text = "{} menit yang lalu".format(round(seconds_passed / 60))
    elif seconds_passed < 86400:
        text = "{} jam yang lalu".format(round(seconds_passed / 3600))
    elif days_passed_by < 31:
        text = "{} hari yang lalu".format(days_passed_by)
    elif days_passed_by < 365:
        text = "{} bulan yang lalu".format(round(days_passed_by / 30))
    else:
        calculate_year = round(days_passed_by / 365)
        if calculate_year < 1:
            calculate_year = 1
        text = "{} bulan yang lalu".format(calculate_year)

    return text


class ShowtimesBase:
    """Base class for Showtimes

    This include some repeated functon on all Showtimes class.
    """

    def __init__(self):
        self._async_lock = False
        self.logger = logging.getLogger("cogs.showtimes_module.base.ShowtimesBase")

    async def __acquire_lock(self):
        while True:
            if not self._async_lock:
                break
            await asyncio.sleep(0.5)
        self._async_lock = True

    async def __release_lock(self):
        self._async_lock = False

    async def db_is_exists(self, cwd: str, server_id: str) -> bool:
        svfn = os.path.join(cwd, "showtimes_folder", f"{server_id}.showtimes")
        if not os.path.isfile(svfn):
            return False
        return True

    async def fetch_servers(self, cwd: str) -> list:
        self.logger.info("fetching with glob...")
        glob_re = os.path.join(cwd, "showtimes_folder", "*.showtimes")
        basename = os.path.basename
        all_showtimes = glob.glob(glob_re)
        all_showtimes = [os.path.splitext(basename(srv))[0] for srv in all_showtimes]
        return all_showtimes

    async def fetch_super_admins(self, cwd: str):
        self.logger.info("dumping data...")
        svfn = os.path.join(cwd, "showtimes_folder", "super_admin.json")
        if not os.path.isfile(svfn):
            return []
        await self.__acquire_lock()
        try:
            json_data = await read_files(svfn)
        except Exception:
            json_data = []
        await self.__release_lock()
        return json_data

    async def fetch_showtimes(self, server_id: str, cwd: str) -> Union[dict, None]:
        """Open a local database of server ID

        :param server_id: server ID
        :type server_id: str
        :return: showtimes data.
        :rtype: dict
        """
        self.logger.info(f"opening db {server_id}")
        svfn = os.path.join(cwd, "showtimes_folder", f"{server_id}.showtimes")
        if not os.path.isfile(svfn):
            return None
        await self.__acquire_lock()
        try:
            json_data = await read_files(svfn)
        except Exception:
            json_data = None
        await self.__release_lock()
        return json_data

    async def dumps_super_admins(self, dataset: list, cwd: str):
        self.logger.info("dumping data...")
        svfn = os.path.join(cwd, "showtimes_folder", "super_admin.json")
        await self.__acquire_lock()
        try:
            await write_files(dataset, svfn)
        except Exception:
            self.logger.info("error occured when trying to write files.")
        await self.__release_lock()

    async def dumps_showtimes(self, dataset: dict, server_id: str, cwd: str):
        """Save data to local database of server ID

        :param server_id: server ID
        :type server_id: str
        :return: showtimes data.
        :rtype: dict
        """
        self.logger.info(f"dumping db {server_id}")
        svfn = os.path.join(cwd, "showtimes_folder", f"{server_id}.showtimes")
        await self.__acquire_lock()
        try:
            await write_files(dataset, svfn)
        except Exception:
            self.logger.info("error occured when trying to write files.")
        await self.__release_lock()

    async def choose_anime(self, bot, ctx, matches: list):
        self.logger.info("asking for user input...")
        first_run = True
        matches = matches[:10]
        reactmoji = [
            "1⃣",
            "2⃣",
            "3⃣",
            "4⃣",
            "5⃣",
            "6⃣",
            "7⃣",
            "8⃣",
            "9⃣",
            "0⃣",
        ]
        res_matches = []
        while True:
            if first_run:
                embed = discord.Embed(title="Mungkin:", color=0x8253B8)

                format_value = []
                for n, i in enumerate(matches):
                    format_value.append("{} **{}**".format(reactmoji[n], i))
                format_value.append("❌ **Batalkan**")
                embed.description = "\n".join(format_value)

                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®",
                    icon_url="https://p.n4o.xyz/i/nao250px.png",
                )

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji_extension = ["❌"]
            reactmoji_mote = reactmoji[: len(matches)]
            reactmoji_mote.extend(reactmoji_extension)

            for react in reactmoji_mote:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji_mote:
                    return False
                return True

            try:
                res, user = await bot.wait_for("reaction_add", timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                break
            if user != ctx.message.author:
                pass
            elif "❌" in str(res.emoji):
                await msg.clear_reactions()
                break
            else:
                await msg.clear_reactions()
                reaction_pos = reactmoji.index(str(res.emoji))
                res_matches.append(matches[reaction_pos])
                break
        await msg.delete()
        if res_matches:
            self.logger.info(f"picked: {res_matches[0]}")
        return res_matches

    async def split_search_id(self, dataset: list, needed_id: str, matching_id: int):
        def to_int(x):
            if isinstance(x, str):
                x = int(x)
            return x

        mid_num = len(dataset) // 2
        mid_data = dataset[mid_num]
        match_data = to_int(mid_data[needed_id])
        if match_data == matching_id:
            return mid_data
        if match_data > matching_id:
            for data in dataset[:mid_num]:
                if to_int(data[needed_id]) == matching_id:
                    return data
        elif match_data < matching_id:
            for data in dataset[mid_num:]:
                if to_int(data[needed_id]) == matching_id:
                    return data
        for data in dataset:
            if to_int(data[needed_id]) == matching_id:
                return data
        return None

    @staticmethod
    def parse_status(status: dict) -> str:
        """
        Parse status and return a formatted text
        """
        status_list = []
        for work, c_stat in status.items():
            if c_stat == "y":
                status_list.append("~~{}~~".format(work))
            else:
                status_list.append("**{}**".format(work))

        return " ".join(status_list)

    @staticmethod
    def get_current_ep(status_list: dict) -> Union[str, None]:
        """
        Find episode `not_released` status in showtimes database
        If not exist return None
        """
        for ep in status_list:
            if status_list[ep]["status"] == "not_released":
                return ep
        return None

    @staticmethod
    def get_not_released_ep(status_list: dict) -> list:
        """
        Find all episode `not_released` status in showtimes database
        If not exist return None/False
        """
        ep_list = []
        for ep in status_list:
            if status_list[ep]["status"] == "not_released":
                ep_list.append(ep)
        return ep_list

    @staticmethod
    def get_close_matches(target: str, lists: list) -> list:
        """
        Find close matches from input target
        Sort everything if there's more than 2 results
        """
        target_compiler = re.compile("({})".format(target), re.IGNORECASE)
        return sorted(list(filter(target_compiler.search, lists)))

    @staticmethod
    def check_role(needed_role, user_roles: list) -> bool:
        """
        Check if there's needed role for the anime
        """
        for role in user_roles:
            if int(needed_role) == int(role.id):
                return True
        return False

    @staticmethod
    def find_alias_anime(key: str, alias_list: dict) -> Union[str, None]:
        """
        Return a target_anime value for alias provided
        """
        for k, v in alias_list.items():
            if key == k:
                return v
        return None

    @staticmethod
    def make_numbered_alias(alias_list: list) -> str:
        """
        Create a numbered text for alias_list
        """
        t = []
        for n, i in enumerate(alias_list):
            t.append("**{}**. {}".format(n + 1, i))
        return "\n".join(t)

    @staticmethod
    def any_progress(status: dict) -> bool:
        """
        Check if there's any progress to the project
        """
        for _, v in status.items():
            if v == "y":
                return False
        return True

    @staticmethod
    def get_role_name(role_id, roles) -> str:
        """
        Get role name by comparing the role id
        """
        for r in roles:
            if str(r.id) == str(role_id):
                return r.name
        return "Unknown"

    async def get_roles(self, posisi):
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
        picked_roles = posisi_kw.get(posisi, None)
        if picked_roles is not None:
            picked_roles = picked_roles.upper()
        return picked_roles, posisi

    @staticmethod
    def split_until_less_than(dataset: list) -> list:
        """
        Split the !tagih shit into chunked text because discord
        max 2000 characters limit
        """

        def split_list(alist, wanted_parts=1):
            length = len(alist)
            return [
                alist[i * length // wanted_parts : (i + 1) * length // wanted_parts]
                for i in range(wanted_parts)
            ]

        text_format = "**Mungkin**: {}"
        start_num = 2
        new_set = None
        while True:
            internal_meme = False
            new_set = split_list(dataset, start_num)
            for set_ in new_set:
                if len(text_format.format(", ".join(set_))) > 1995:
                    internal_meme = True

            if not internal_meme:
                break
            start_num += 1

        return new_set

    async def collect_anime_with_alias(self, anime_list, alias_list):
        srv_anilist = []
        srv_anilist_alias = []
        for ani, _ in anime_list.items():
            srv_anilist.append(ani)
        for alias, _ in alias_list.items():
            srv_anilist_alias.append(alias)
        return srv_anilist, srv_anilist_alias

    async def find_any_matches(self, judul, anilist: list, aliases: list, alias_map: dict) -> list:
        matches = self.get_close_matches(judul, anilist)
        if aliases:
            temp_anilias = self.get_close_matches(judul, aliases)
            for match in temp_anilias:
                res = self.find_alias_anime(match, alias_map)
                if res is None:
                    continue
                if res not in matches:  # To not duplicate result
                    matches.append(res)
        return matches

    async def send_all_projects(self, ctx, dataset: list, srv_: str):
        if len(dataset) < 1:
            self.logger.warning(f"{srv_}: no registered data on database.")
            return await ctx.send("**Tidak ada anime yang terdaftar di database**")
        sorted_data = sorted(dataset)
        self.logger.info(f"{srv_}: sending all registered anime.")
        sorted_data = self.split_until_less_than(sorted_data)
        first_time = True
        for data in sorted_data:
            if first_time:
                await ctx.send("**Mungkin**: {}".format(", ".join(data)))
                first_time = False
            else:
                await ctx.send("{}".format(", ".join(data)))

    async def confirmation_dialog(self, bot, ctx, message: str) -> bool:
        dis_msg = await ctx.send(message)
        to_react = ["✅", "❌"]
        for react in to_react:
            await dis_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != dis_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        dialog_tick = True
        while True:
            res, user = await bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await dis_msg.delete()
                break
            elif "❌" in str(res.emoji):
                dialog_tick = False
                await dis_msg.delete()
                break
        return dialog_tick
