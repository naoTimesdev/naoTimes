import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import aiohttp
import discord
import timeago

from nthelper.redis import RedisBridge

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

    if compiled_data["airing_start"] is None:
        raise ValueError("airing_start is empty, need more data")

    if isinstance(current_ep, str):
        current_ep = int(current_ep)
    if total_episode is not None and isinstance(total_episode, str):
        total_episode = int(total_episode)

    airing_time_nodes = entry["airingSchedule"]["nodes"]
    show_format = entry["format"].lower()
    airing_time, episode_number = get_episode_airing(airing_time_nodes, current_ep)  # type: ignore
    if not airing_time:
        airing_time = start_timestamp
    if show_format in ["tv", "tv_short"] and episode_number != current_ep:
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
    current_time = datetime.now(tz=timezone.utc)
    parsed_time = datetime.fromtimestamp(oldtime, tz=timezone.utc)

    return timeago.format(parsed_time, current_time, "in_ID")


class ShowtimesBase:
    """Base class for Showtimes

    This include some repeated functon on all Showtimes class.
    """

    def __init__(self):
        self._async_lock = False
        self.logger = logging.getLogger("cogs.showtimes_module.base.ShowtimesBase")

    @staticmethod
    def get_unix():
        return int(round(datetime.now(tz=timezone.utc).timestamp()))

    async def __acquire_lock(self):
        while True:
            if not self._async_lock:
                break
            await asyncio.sleep(0.5)
        self._async_lock = True

    async def __release_lock(self):
        self._async_lock = False

    async def fetch_servers(self, redisdb: RedisBridge) -> list:
        self.logger.info("fetching with keys...")
        all_servers = await redisdb.keys("showtimes_*")
        all_showtimes = [srv[10:] for srv in all_servers if srv]
        return all_showtimes

    async def fetch_super_admins(self, redisdb: RedisBridge):
        self.logger.info("dumping data...")
        json_data = await redisdb.getall("showadmin_*")
        if json_data is None:
            return []
        return json_data

    async def fetch_showtimes(self, server_id: str, redisdb: RedisBridge) -> Union[dict, None]:
        """Open a local database of server ID

        :param server_id: server ID
        :type server_id: str
        :return: showtimes data.
        :rtype: dict
        """
        self.logger.info(f"opening db {server_id}")
        await self.__acquire_lock()
        json_data = await redisdb.get(f"showtimes_{server_id}")
        if json_data is None:
            return {}
        await self.__release_lock()
        return json_data

    async def dumps_super_admins(self, dataset: list, redisdb: RedisBridge):
        self.logger.info("dumping data...")
        await self.__acquire_lock()
        await redisdb.set("showtimesadmin", dataset)
        await self.__release_lock()

    async def dumps_showtimes(self, dataset: dict, server_id: str, redisdb: RedisBridge):
        """Save data to local database of server ID

        :param server_id: server ID
        :type server_id: str
        :return: showtimes data.
        :rtype: dict
        """
        self.logger.info(f"dumping db {server_id}")
        await self.__acquire_lock()
        await redisdb.set(f"showtimes_{server_id}", dataset)
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
                    ani_title = i["name"] if i["type"] == "real" else i["real_name"]
                    format_value.append("{} **{}**".format(reactmoji[n], ani_title))
                format_value.append("❌ **Batalkan**")
                embed.description = "\n".join(format_value)

                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
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
            if res_matches[0]["type"] == "alias":
                res_matches[0]["name"] = res_matches[0]["real_name"]
        return res_matches

    @staticmethod
    def _search_data_index(anilist_datasets: list, need_id: str, match_id: str) -> int:
        idx = None
        for n, data in enumerate(anilist_datasets):
            if str(data[need_id]) == str(match_id):
                idx = n
                break
        return idx

    @staticmethod
    async def split_search_id(dataset: list, needed_id: str, matching_id: int, sort=False):
        def to_int(x):
            if isinstance(x, str):
                x = int(x)
            return x

        if sort:
            dataset.sort(key=lambda x: x[sort])

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
            if c_stat:
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
        for status in status_list:
            if not status["is_done"]:
                return status
        return None

    @staticmethod
    def get_not_released_ep(status_list: dict) -> list:
        """
        Find all episode `not_released` status in showtimes database
        If not exist return None/False
        """
        ep_list = []
        for ep in status_list:
            if not ep["is_done"]:
                ep_list.append(ep)
        return ep_list

    @staticmethod
    def get_close_matches(target: str, lists: list) -> list:
        """
        Find close matches from input target
        Sort everything if there's more than 2 results

        lists must be in this format:
        [{
            "index": 0,
            "name": "Anime title"
        }]
        """
        target_compiler = re.compile("({})".format(target), re.IGNORECASE)

        def _match_re(data):
            return target_compiler.search(data["name"])

        return sorted(list(filter(_match_re, lists)), key=lambda x: x["name"])

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
    def is_progressing(progress: dict) -> bool:
        """Check if episode is progressing or not"""
        for _, status in progress.items():
            if status:
                return True
        return False

    @staticmethod
    def get_role_name(role_id, roles) -> str:
        """
        Get role name by comparing the role id
        """
        for r in roles:
            if str(r.id) == str(role_id):
                return r.name
        return "Unknown"

    @staticmethod
    async def get_roles(posisi):
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
    def normalize_role_to_name(posisi: str) -> str:
        posisi_kw = {
            "tl": "Translasi",
            "tlc": "TL Check",
            "enc": "Encode",
            "ed": "Editing",
            "tm": "Timing",
            "ts": "Typesetting",
            "qc": "Pemeriksaan Akhir",
        }
        posisi = posisi.lower()
        picked_role = posisi_kw.get(posisi, posisi.upper())
        return picked_role

    @staticmethod
    def split_until_less_than(dataset: list) -> list:
        """
        Split the !tagih shit into chunked text because discord
        max 2000 characters limit
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

    @staticmethod
    def propagate_anime_with_aliases(anime_lists):
        propagated_anime = []
        for index, anime_data in enumerate(anime_lists):
            propagated_anime.append(
                {"id": anime_data["id"], "index": index, "name": anime_data["title"], "type": "real"}
            )
            if "aliases" in anime_data and anime_data["aliases"]:
                for alias in anime_data["aliases"]:
                    propagated_anime.append(
                        {
                            "id": anime_data["id"],
                            "index": index,
                            "name": alias,
                            "type": "alias",
                            "real_name": anime_data["title"],
                        }
                    )
        return propagated_anime

    def find_any_matches(self, match_title: str, propagated_lists: list) -> list:
        matches = self.get_close_matches(match_title, propagated_lists)
        # Deduplicates
        deduplicated = []
        dedup_index = []
        for match in matches:
            if str(match["index"]) not in dedup_index:
                if match["type"] == "alias":
                    match["name"] = match["real_name"]
                deduplicated.append(match)
                dedup_index.append(str(match["index"]))
        return deduplicated

    async def send_all_projects(self, ctx, dataset: list, srv_: str):
        if len(dataset) < 1:
            self.logger.warning(f"{srv_}: no registered data on database.")
            return await ctx.send("**Tidak ada anime yang terdaftar di database**")
        anime_title_set = []
        for anime in dataset:
            anime_title_set.append(anime["title"])
        sorted_data = sorted(anime_title_set)
        self.logger.info(f"{srv_}: sending all registered anime.")
        sorted_data = self.split_until_less_than(sorted_data)
        first_time = True
        for data in sorted_data:
            if first_time:
                await ctx.send("**Mungkin**: {}".format(", ".join(data)))
                first_time = False
            else:
                await ctx.send("{}".format(", ".join(data)))

    @staticmethod
    async def confirmation_dialog(bot, ctx, message: str) -> bool:
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
