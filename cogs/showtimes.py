# -*- coding: utf-8 -*-

import asyncio
import glob
import logging
import os
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import partial
from random import choice
from string import ascii_lowercase, digits
from typing import Optional, Tuple, Union

import aiohttp
import discord
from discord.ext import commands, tasks

import ujson
from nthelper import HelpGenerator, read_files, send_timed_msg, write_files
from nthelper.utils import get_current_time

showlog = logging.getLogger("cogs.showtimes")


anifetch_query = """
query ($id: Int!) {
    Media(id: $id, type: ANIME) {
        id
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

tambahepisode_instruct = """Jumlah yang dimaksud adalah jumlah yang ingin ditambahkan dari jumlah episode sekarang
Misal ketik `4` dan total jumlah episode sekarang adalah `12`
Maka total akan berubah menjadi `16` `(13, 14, 15, 16)`"""  # noqa: E501

hapusepisode_instruct = """Ranged number, bisa satu digit untuk 1 episode saja atau range dari episode x sampai y
Contoh: `4` untuk episode 4 saja || `4-6` untuk episode 4 sampai 6"""  # noqa: E501


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


def parse_anilist_start_date(startDate: str) -> int:
    """parse start data of anilist data to Unix Epoch"""
    airing_start = datetime.strptime(startDate, "%Y%m%d")
    epoch_start = datetime(1970, 1, 1, 0, 0, 0)
    return int((airing_start - epoch_start).total_seconds())


def get_episode_airing(nodes: dict, episode: str) -> tuple:
    """Get total episode of airing anime (using anilist data)"""
    if not nodes:
        return None, "1"  # No data
    for i in nodes:
        if i["episode"] == int(episode):
            return i["airingAt"], i["episode"]  # return episodic data
    if len(nodes) == 1:
        return (
            nodes[0]["airingAt"],
            nodes[-1]["episode"],
        )  # get the only airing data
    return (
        nodes[-1]["airingAt"],
        nodes[-1]["episode"],
    )  # get latest airing data


def get_original_time(x: int, total: int) -> int:
    """what the fuck does this thing even do"""
    for _ in range(total):
        x -= 24 * 3600 * 7
    return x


def parse_ani_time(x: int) -> str:
    """parse anilist time to time-left format"""
    sec = timedelta(seconds=abs(x))
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
    current_ep,
    total_episode=None,
    return_time_data=False,
    jadwal_only=False,
    return_only_time=False,
) -> Union[str, tuple]:
    """
    Fetch Anilist.co API data for helping all showtimes
    command to work properly
    Used on almost command, tweaked to make it compatible to every command
    """
    variables = {
        "id": int(ani_id),
    }
    api_link = "https://graphql.anilist.co"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                api_link, json={"query": anifetch_query, "variables": variables},
            ) as r:
                try:
                    data = await r.json()
                except IndexError:
                    return "ERROR: Terjadi kesalahan internal"
                if r.status != 200:
                    if r.status == 404:
                        return "ERROR: Tidak dapat menemukan anime tersebut"
                    elif r.status == 500:
                        return "ERROR: Internal Error :/"
                try:
                    entry = data["data"]["Media"]
                except IndexError:
                    return "ERROR: Tidak ada hasil."
        except aiohttp.ClientError:
            return "ERROR: Koneksi terputus"

    if jadwal_only:
        taimu: Optional[str]
        next_episode: Optional[int]
        try:
            time_until = entry["nextAiringEpisode"]["timeUntilAiring"]
            next_episode = entry["nextAiringEpisode"]["episode"]

            taimu = parse_ani_time(time_until)
        except Exception:
            taimu = None
            time_until = None
            next_episode = None

        return taimu, time_until, next_episode, entry["title"]["romaji"]

    poster = [
        entry["coverImage"]["large"],
        rgbhex_to_rgbint(entry["coverImage"]["color"]),
    ]
    start_date = entry["startDate"]
    title_rom = entry["title"]["romaji"]
    airing_time_nodes = entry["airingSchedule"]["nodes"]
    show_format = entry["format"].lower()
    current_time = int(round(time.time()))
    airing_time, episode_number = get_episode_airing(airing_time_nodes, current_ep)
    if not airing_time:
        airing_time = parse_anilist_start_date(
            "{}{}{}".format(start_date["year"], start_date["month"], start_date["day"])
        )
    if show_format in ["tv", "tv_short"]:
        if str(episode_number) == str(current_ep):
            pass
        else:
            airing_time = get_original_time(airing_time, int(episode_number) - int(current_ep))
    airing_time = airing_time - current_time
    try:
        episodes = entry["episodes"]
        if not episodes:
            episodes = 0
    except KeyError:
        episodes = 0
    except IndexError:
        episodes = 0

    if not airing_time_nodes:
        airing_time_nodes = []
        temporary_nodes = {}
        temporary_nodes["airingAt"] = parse_anilist_start_date(
            "{}{}{}".format(start_date["year"], start_date["month"], start_date["day"])
        )
        airing_time_nodes.append(temporary_nodes)

    if return_only_time:
        ext_dt = []
        date_dt = []
        try:
            yyyy = start_date["year"]
            ext_dt.append("%Y")
            date_dt.append(yyyy)
        except KeyError:
            pass
        try:
            mm = start_date["month"]
            ext_dt.append("%m")
            date_dt.append(mm)
        except KeyError:
            pass
        try:
            dd = start_date["day"]
            ext_dt.append("%d")
            date_dt.append(dd)
        except KeyError:
            pass
        if not ext_dt or len(date_dt) < 2:
            raise ValueError("Not enough data.")
        airing_start = (
            datetime.strptime("-".join(date_dt), "-".join(ext_dt))
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        return airing_start, title_rom, ani_id

    taimu = parse_ani_time(airing_time)
    if return_time_data:
        if total_episode is not None and int(total_episode) < episodes:
            total_episode = episodes
        else:
            total_episode = int(total_episode)
        time_data = []
        if show_format in ["tv", "tv_short"]:
            for x in range(total_episode):
                try:
                    time_data.append(airing_time_nodes[x]["airingAt"])
                except IndexError:  # Out of range stuff ;_;
                    calc = 24 * 3600 * 7 * x
                    time_data.append(int(airing_time_nodes[0]["airingAt"]) + calc)
        else:
            for x in range(total_episode):
                time_data.append(
                    get_original_time(
                        parse_anilist_start_date(
                            "{}{}{}".format(
                                start_date["year"], start_date["month"], start_date["day"],
                            )
                        ),
                        x + 1,
                    )
                )
        return taimu, poster, title_rom, time_data, total_episode
    return taimu, poster, title_rom


def get_last_updated(oldtime):
    """
    Get last updated time from naoTimes database
    and convert it to "passed time"
    """
    current_time = datetime.now()
    oldtime = datetime.utcfromtimestamp(oldtime)
    delta_time = current_time - oldtime

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


class SaveQueueData:
    """A queue data of save state
    used mainly for queue-ing when there's shit ton of stuff
    to save to the local database.
    """

    def __init__(self, dataset: Union[list, dict], server_id: str, cwd: str):
        self.dataset = dataset
        self.server_id = server_id
        self.cwd = cwd


global_queue: asyncio.Queue = asyncio.Queue()
global_lock = False


async def acquire_lock():
    global global_lock
    while True:
        if not global_lock:
            break
        await asyncio.sleep(0.2)
    global_lock = True


async def release_lock():
    global global_lock
    global_lock = False


async def dumps_showtimes(dataset, server_id, cwd):
    showlog.info(f"dumping db {server_id}")
    svfn = os.path.join(cwd, "showtimes_folder", f"{server_id}.showtimes")
    await acquire_lock()
    try:
        await write_files(dataset, svfn)
    except Exception:
        pass
    await release_lock()


async def background_save():
    showlog.info("starting task...")
    while True:
        try:
            svq_data: SaveQueueData = await global_queue.get()
            showlog.info(f"job get, running: {svq_data.server_id}")
            await dumps_showtimes(svq_data.dataset, svq_data.server_id, svq_data.cwd)
            global_queue.task_done()
        except asyncio.CancelledError:
            return


async def store_queue(save_data: SaveQueueData):
    """Save to a queue

    :param save_data: [description]
    :type save_data: SaveQueueData
    :return: [description]
    :rtype: [type]
    """
    return await global_queue.put(save_data)


class ShowtimesBase:
    """Base class for Showtimes

    This include some repeated functon on all Showtimes class.
    """

    def __init__(self):
        self._async_lock = False
        self.logger = logging.getLogger("cogs.showtimes.ShowtimesBase")

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
            pass
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
            pass
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
        return res_matches

    def parse_status(self, status: dict) -> str:
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

    def get_current_ep(self, status_list: dict) -> Union[str, None]:
        """
        Find episode `not_released` status in showtimes database
        If not exist return None
        """
        for ep in status_list:
            if status_list[ep]["status"] == "not_released":
                return ep
        return None

    def get_not_released_ep(self, status_list: dict) -> list:
        """
        Find all episode `not_released` status in showtimes database
        If not exist return None/False
        """
        ep_list = []
        for ep in status_list:
            if status_list[ep]["status"] == "not_released":
                ep_list.append(ep)
        return ep_list

    def get_close_matches(self, target: str, lists: list) -> list:
        """
        Find close matches from input target
        Sort everything if there's more than 2 results
        """
        target_compiler = re.compile("({})".format(target), re.IGNORECASE)
        return sorted(list(filter(target_compiler.search, lists)))

    def check_role(self, needed_role, user_roles: list) -> bool:
        """
        Check if there's needed role for the anime
        """
        for role in user_roles:
            if int(needed_role) == int(role.id):
                return True
        return False

    def find_alias_anime(self, key: str, alias_list: dict) -> Union[str, None]:
        """
        Return a target_anime value for alias provided
        """
        for k, v in alias_list.items():
            if key == k:
                return v
        return None

    def make_numbered_alias(self, alias_list: list) -> str:
        """
        Create a numbered text for alias_list
        """
        t = []
        for n, i in enumerate(alias_list):
            t.append("**{}**. {}".format(n + 1, i))
        return "\n".join(t)

    def any_progress(self, status: dict) -> bool:
        """
        Check if there's any progress to the project
        """
        for _, v in status.items():
            if v == "y":
                return False
        return True

    def get_role_name(self, role_id, roles) -> str:
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

    def split_until_less_than(self, dataset: list) -> list:
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
            self.logger.warn(f"{srv_}: no registered data on database.")
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


class Showtimes(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(Showtimes, self).__init__()
        self.bot = bot
        # pylint: disable=E1101
        self.resync_failed_server.start()
        self.logger = logging.getLogger("cogs.showtimes.Showtimes")
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        # pylint: enable=E1101
        # self.task = asyncio.Task(self.resync_failure())

    def __str__(self):
        return "Showtimes Main"

    async def resync_failure(self):
        self.logger.info("starting task...")
        while True:
            try:
                srv = await self.bot.showtimes_resync.get()
                showlog.info(f"job get, resynchronizing: {srv}")
                srv_data = await self.srv_fetch(srv)
                res, msg = await self.bot.ntdb.update_data_server(srv, srv_data)
                if not res:
                    self.logger.error(f"\tFailed to update, reason: {msg}")
                    self.bot.showtimes_resync.task_done()
                    await self.bot.showtimes_resync.put(srv)
                else:
                    self.logger.info(f"{srv}: resynchronized!")
                    self.bot.showtimes_resync.task_done()
            except asyncio.CancelledError:
                return

    @tasks.loop(minutes=1.0)
    async def resync_failed_server(self):
        if not self.bot.showtimes_resync:
            return
        self.logger.info("trying to resynchronizing...")
        for srv in self.bot.showtimes_resync:
            self.logger.info(f"updating: {srv}")
            srv_data = await self.srv_fetch(srv)
            res, msg = await self.bot.ntdb.update_data_server(srv, srv_data)
            if not res:
                self.logger.error(f"\tFailed to update, reason: {msg}")
                continue
            self.logger.info(f"{srv}: updated!")
            self.bot.showtimes_resync.remove(srv)
        lefts = len(self.bot.showtimes_resync)
        self.logger.info(f"done! leftover to resync are {lefts} server")

    @commands.command(aliases=["blame", "mana"])
    @commands.guild_only()
    async def tagih(self, ctx, *, judul=None):
        """
        Menagih utang fansub tukang diley maupun tidak untuk memberikan
        mereka tekanan
        ---
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        last_update = int(program_info["last_update"])
        status_list = program_info["status"]

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.info(f"{matches[0]}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        poster_data = program_info["poster_data"]
        poster_image, poster_color = poster_data["url"], poster_data["color"]

        if self.any_progress(status_list[current]["staff_status"]):
            time_data, _, _ = await fetch_anilist(program_info["anilist_id"], current)
            last_status = time_data
            last_text = "Tayang"
        else:
            last_status = get_last_updated(last_update)
            last_text = "Update Terakhir"

        current_ep_status = self.parse_status(status_list[current]["staff_status"])

        self.logger.info(f"{matches[0]} sending current episode progress...")
        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=poster_color)
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name="Status", value=current_ep_status, inline=False)
        embed.add_field(name=last_text, value=last_status, inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["release"])
    @commands.guild_only()
    async def rilis(self, ctx, *, data):
        data = data.split()

        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if len(srv_anilist) < 1:
            self.logger.warn(f"{server_message}: no registered data on database.")
            return await ctx.send("**Tidak ada anime yang terdaftar di database**")

        if not data or data == []:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        koleb_list = []
        osrv_dumped = {}

        if data[0] not in ["batch", "semua"]:
            """
            Merilis rilisan, hanya bisa dipakai sama role tertentu
            ---
            judul: Judul anime yang terdaftar
            """
            self.logger.info(f"{server_message}: using normal mode.")

            judul = " ".join(data)

            if judul == " " or judul == "" or judul == "   " or not judul:
                return await self.send_all_projects(ctx, srv_anilist, server_message)

            self.logger.info(f"{server_message}: getting close matches...")
            matches = await self.find_any_matches(
                judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
            )
            if not matches:
                self.logger.warn(f"{server_message}: no matches.")
                return await ctx.send("Tidak dapat menemukan judul tersebut di database")
            elif len(matches) > 1:
                self.logger.info(f"{server_message}: multiple matches!")
                matches = await self.choose_anime(ctx, matches)
                if not matches:
                    return await ctx.send("**Dibatalkan!**")

            self.logger.info(f"{server_message}: matched {matches[0]}")
            program_info = srv_data["anime"][matches[0]]
            status_list = program_info["status"]

            if "kolaborasi" in program_info:
                koleb_data = program_info["kolaborasi"]
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            current = self.get_current_ep(status_list)
            if not current:
                self.logger.warn(f"{matches[0]}: no episode left to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
                if str(ctx.message.author.id) not in srv_owner:
                    self.logger.warn(f"{matches[0]}: user not allowed.")
                    return await ctx.send(
                        "**Tidak secepat itu ferguso, " "yang bisa rilis cuma admin atau QCer**"
                    )

            if koleb_list:
                self.logger.info(f"{matches[0]}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.srv_fetch(other_srv)
                    if srv_o_data is None:
                        continue
                    self.logger.debug(f"{server_message}: {other_srv} processing...")
                    srv_o_data["anime"][matches[0]]["status"][current]["status"] = "released"
                    srv_o_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await store_queue(SaveQueueData(srv_o_data, other_srv, self.bot.fcwd))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{matches[0]}: setting status...")
            srv_data["anime"][matches[0]]["status"][current]["status"] = "released"
            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            text_data = "**{} - #{}** telah dirilis".format(matches[0], current)
            embed_text_data = "{} #{} telah dirilis!".format(matches[0], current)
        elif data[0] == "batch":
            self.logger.info(f"{server_message}: using batch mode.")
            if not data[1].isdigit():
                await self.send_all_projects(ctx, srv_anilist, server_message)
                return await ctx.send("Lalu tulis jumlah terlebih dahulu baru judul")
            if len(data) < 3:
                return await self.send_all_projects(ctx, srv_anilist, server_message)

            jumlah = data[1]
            judul = " ".join(data[2:])

            self.logger.info(f"{server_message}: getting close matches...")
            matches = await self.find_any_matches(
                judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
            )
            if not matches:
                self.logger.warn(f"{server_message}: no matches.")
                return await ctx.send("Tidak dapat menemukan judul tersebut di database")
            elif len(matches) > 1:
                self.logger.info(f"{server_message}: multiple matches!")
                matches = await self.choose_anime(ctx, matches)
                if not matches:
                    return await ctx.send("**Dibatalkan!**")
            self.logger.info(f"{server_message}: matched {matches[0]}")

            program_info = srv_data["anime"][matches[0]]
            status_list = program_info["status"]

            if "kolaborasi" in program_info:
                koleb_data = program_info["kolaborasi"]
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            current = self.get_current_ep(status_list)
            if not current:
                self.logger.warn(f"{matches[0]}: no episode left " "to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
                if str(ctx.message.author.id) not in srv_owner:
                    self.logger.warn(f"{matches[0]}: user not allowed.")
                    return await ctx.send(
                        "**Tidak secepat itu ferguso, " "yang bisa rilis cuma admin atau QCer**"
                    )

            if koleb_list:
                self.logger.info(f"{matches[0]}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.srv_fetch(other_srv)
                    if srv_o_data is None:
                        continue
                    self.logger.debug(f"{server_message}: {other_srv} processing...")
                    for x in range(
                        int(current), int(current) + int(jumlah)
                    ):  # range(int(c), int(c)+int(x))
                        srv_o_data["anime"][matches[0]]["status"][str(x)]["status"] = "released"
                    srv_o_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await store_queue(SaveQueueData(srv_o_data, other_srv, self.bot.fcwd))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{matches[0]}: setting status...")
            for x in range(
                int(current), int(current) + int(jumlah)
            ):  # range(int(c), int(c)+int(x))
                srv_data["anime"][matches[0]]["status"][str(x)]["status"] = "released"

            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(
                matches[0], current, int(current) + int(jumlah) - 1
            )
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(
                matches[0], current, int(current) + int(jumlah) - 1
            )
        elif data[0] == "semua":
            self.logger.info(f"{server_message}: using all mode.")
            judul = " ".join(data[1:])

            if judul == " " or judul == "" or judul == "   " or not judul:
                return await self.send_all_projects(ctx, srv_anilist, server_message)

            self.logger.info(f"{server_message}: getting close matches...")
            matches = await self.find_any_matches(
                judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
            )
            if not matches:
                self.logger.warn(f"{server_message}: no matches.")
                return await ctx.send("Tidak dapat menemukan judul tersebut di database")
            elif len(matches) > 1:
                self.logger.info(f"{server_message}: multiple matches!")
                matches = await self.choose_anime(ctx, matches)
                if not matches:
                    return await ctx.send("**Dibatalkan!**")

            program_info = srv_data["anime"][matches[0]]
            status_list = program_info["status"]

            if "kolaborasi" in program_info:
                koleb_data = program_info["kolaborasi"]
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            all_status = self.get_not_released_ep(status_list)
            if not all_status:
                self.logger.warn(f"{matches[0]}: no episode left " "to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
                if str(ctx.message.author.id) not in srv_owner:
                    self.logger.warn(f"{matches[0]}: user not allowed.")
                    return await ctx.send(
                        "**Tidak secepat itu ferguso, " "yang bisa rilis cuma admin atau QCer**"
                    )

            if koleb_list:
                self.logger.info(f"{matches[0]}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.srv_fetch(other_srv)
                    if srv_o_data is None:
                        continue
                    for x in all_status:
                        srv_o_data["anime"][matches[0]]["status"][x]["status"] = "released"
                    srv_o_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await store_queue(SaveQueueData(srv_o_data, other_srv, self.bot.fcwd))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{matches[0]}: setting status...")
            for x in all_status:
                srv_data["anime"][matches[0]]["status"][x]["status"] = "released"

            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(
                matches[0], all_status[0], all_status[-1]
            )
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(
                matches[0], all_status[0], all_status[-1]
            )

        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        self.logger.info(f"{server_message}: sending message")
        await ctx.send(text_data)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            self.logger.info(f"{osrv}: updating collab server...")
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            if "announce_channel" in osrv_data:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                if not target_chan:
                    self.logger.warn(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title="{}".format(matches[0]), color=0x1EB5A6)
                embed.add_field(name="Rilis!", value=embed_text_data, inline=False)
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        if "announce_channel" in srv_data:
            self.logger.info(f"{server_message}: sending progress to everyone...")
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed = discord.Embed(title="{}".format(matches[0]), color=0x1EB5A6)
            embed.add_field(name="Rilis!", value=embed_text_data, inline=False)
            embed.set_footer(text=f"Pada: {get_current_time()}")
            if target_chan:
                await target_chan.send(embed=embed)

    @commands.command(aliases=["done"])
    async def beres(self, ctx, posisi: str, *, judul: str):
        """
        Menyilang salah satu tugas pendelay
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        posisi, posisi_asli = await self.get_roles(posisi)
        if posisi is None:
            self.logger.warn(f"unknown position.")
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )
        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(self.bot, ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        if not self.check_role(program_info["role_id"], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warn(f"{matches[0]}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        current_stat = status_list[current]["staff_status"][posisi]
        if current_stat == "y":
            self.logger.warn(f"{matches[0]}: position already set to done.")
            return await ctx.send(f"**{posisi_asli}** sudah ditandakan " "sebagai beres.")

        poster_data = program_info["poster_data"]
        poster_image = poster_data["url"]

        if str(ctx.message.author.id) != program_info["staff_assignment"][posisi]:
            if str(ctx.message.author.id) not in srv_owner:
                self.logger.warn(f"{matches[0]}: no access to set to done.")
                return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        self.logger.info(f"{matches[0]}: setting episode {current} to done.")
        srv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "y"
        srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.srv_fetch(other_srv)
                if osrv_data is None:
                    continue
                osrv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "y"
                osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                await store_queue(SaveQueueData(osrv_data, other_srv, self.bot.fcwd))
                osrv_dumped[other_srv] = osrv_data

        current_ep_status = status_list[current]["staff_status"]

        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        self.logger.info(f"{matches[0]}: sending progress info to staff...")
        await ctx.send("Berhasil mengubah status garapan {} - #{}".format(matches[0], current))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        if osrv_dumped:
            for osrv, osrv_data in osrv_dumped.items():
                if osrv == server_message:
                    continue
                if "announce_channel" in osrv_data:
                    self.logger.info(f"{osrv}: sending progress to everyone...")
                    announce_chan = osrv_data["announce_channel"]
                    target_chan = self.bot.get_channel(int(announce_chan))
                    if not target_chan:
                        self.logger.warn(f"{announce_chan}: unknown channel.")
                        continue
                    embed = discord.Embed(
                        title="{} - #{}".format(matches[0], current), color=0x1EB5A6,
                    )
                    embed.add_field(
                        name="Status", value=self.parse_status(current_ep_status), inline=False,
                    )
                    embed.set_footer(text=f"Pada: {get_current_time()}")
                    await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0x1EB5A6)
        embed.add_field(
            name="Status", value=self.parse_status(current_ep_status), inline=False,
        )
        if "announce_channel" in srv_data:
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed.set_footer(text=f"Pada: {get_current_time()}")
            self.logger.info(f"{server_message}: sending progress to everyone...")
            if target_chan:
                await target_chan.send(embed=embed)
        embed.add_field(name="Update Terakhir", value="Baru saja", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        embed.set_thumbnail(url=poster_image)
        return await ctx.send(embed=embed)

    @commands.command(aliases=["gakjadirilis", "revert"])
    @commands.guild_only()
    async def batalrilis(self, ctx, *, judul=None):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]
        srv_owner = srv_data["serverowner"]

        if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
            if str(ctx.message.author.id) not in srv_owner:
                return await ctx.send(
                    "**Tidak secepat itu ferguso, yang bisa "
                    "membatalkan rilisan cuma admin atau QCer**"
                )

        current = self.get_current_ep(status_list)
        if not current:
            current = int(list(status_list.keys())[-1])
        else:
            current = int(current) - 1

        if current < 1:
            self.logger.info(f"{matches[0]}: no episode have been released.")
            return await ctx.send("Tidak ada episode yang dirilis untuk judul ini.")

        current = str(current)

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        self.logger.info(f"{matches[0]}: unreleasing episode {current}")
        srv_data["anime"][matches[0]]["status"][current]["status"] = "not_released"
        srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.srv_fetch(other_srv)
                if osrv_data is None:
                    continue
                osrv_data["anime"][matches[0]]["status"][current]["status"] = "not_released"
                osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                await store_queue(SaveQueueData(osrv_data, other_srv, self.bot.fcwd))
                osrv_dumped[other_srv] = osrv_data

        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        self.logger.info(f"{matches[0]}: sending progress info to staff...")
        await ctx.send("Berhasil membatalkan rilisan **{}** episode {}".format(matches[0], current))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update" f", reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            if "announce_channel" in osrv_data:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                if not target_chan:
                    self.logger.warn(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title="{}".format(matches[0]), color=0xB51E1E)
                embed.add_field(
                    name="Batal rilis...",
                    value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(  # noqa: E501
                        current
                    ),
                    inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        if "announce_channel" in srv_data:
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed = discord.Embed(title="{}".format(matches[0]), color=0xB51E1E)
            embed.add_field(
                name="Batal rilis...",
                value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(  # noqa: E501
                    current
                ),
                inline=False,
            )
            self.logger.info(f"{server_message}: sending " "progress to everyone...")
            embed.set_footer(text=f"Pada: {get_current_time()}")
            if target_chan:
                await target_chan.send(embed=embed)

    @commands.command(aliases=["undone", "cancel"])
    @commands.guild_only()
    async def gakjadi(self, ctx, posisi, *, judul):
        """
        Menghilangkan tanda karena ada kesalahan
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        posisi, posisi_asli = await self.get_roles(posisi)
        if posisi is None:
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        if not self.check_role(program_info["role_id"], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warn(f"{matches[0]}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        current_stat = status_list[current]["staff_status"][posisi]
        if current_stat == "x":
            self.logger.warn(f"{matches[0]}: position already set to undone.")
            return await ctx.send(f"**{posisi_asli}** sudah ditandakan " "sebagai tidak beres.")

        poster_data = program_info["poster_data"]
        poster_image = poster_data["url"]

        if str(ctx.message.author.id) != program_info["staff_assignment"][posisi]:
            if str(ctx.message.author.id) not in srv_owner:
                self.logger.warn(f"{matches[0]}: no access to set to undone.")
                return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        self.logger.info(f"{matches[0]}: setting episode {current} to undone.")
        srv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "x"
        srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.srv_fetch(other_srv)
                if osrv_data is None:
                    continue
                osrv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "x"
                osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                await store_queue(SaveQueueData(osrv_data, other_srv, self.bot.fcwd))
                osrv_dumped[other_srv] = osrv_data

        current_ep_status = status_list[current]["staff_status"]

        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        self.logger.info(f"{matches[0]}: sending progress info to staff...")
        await ctx.send("Berhasil mengubah status garapan {} - #{}".format(matches[0], current))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            if "announce_channel" in osrv_data:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                if not target_chan:
                    self.logger.warn(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0xB51E1E,)
                embed.add_field(
                    name="Status", value=self.parse_status(current_ep_status), inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0xB51E1E)
        embed.add_field(
            name="Status", value=self.parse_status(current_ep_status), inline=False,
        )
        if "announce_channel" in srv_data:
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed.set_footer(text=f"Pada: {get_current_time()}")
            self.logger.info(f"{server_message}: sending progress to everyone...")
            if target_chan:
                await target_chan.send(embed=embed)
        embed.add_field(name="Update Terakhir", value="Baru saja", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        embed.set_thumbnail(url=poster_image)
        await ctx.send(embed=embed)

    @commands.command(aliases=["airing"])
    @commands.guild_only()
    async def jadwal(self, ctx):
        """
        Melihat jadwal anime musiman yang di ambil.
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        time_data_list = {}
        total_anime = len(list(srv_data["anime"].keys()))
        self.logger.info(f"{server_message}: collecting {total_anime} jadwal...")

        async def add_to_list(data_map):
            time_until, data = data_map["t"], data_map["d"]
            if time_until in time_data_list:  # For anime that air at the same time
                time_until += 1
                while True:
                    if time_until not in time_data_list:
                        break
                    time_until += 1
            time_data_list[time_until] = data

        def calculate_needed(status_list):
            all_ep = list(status_list.keys())[-1]
            return 7 * int(all_ep) * 24 * 60 * 60

        simple_queue = asyncio.Queue()
        fetch_anime_jobs = []
        current_date = datetime.now(tz=timezone.utc).timestamp()
        for ani, ani_data in srv_data["anime"].items():
            if ani == "alias":
                continue
            current = self.get_current_ep(ani_data["status"])
            if current is None:
                self.logger.warn(f"{ani}: anime already done worked on.")
                continue
            try:
                start_time = ani_data["start_time"]
            except KeyError:
                self.logger.error(f"{ani}: failed fetching start_time from database.")
                continue
            calc_need = calculate_needed(ani_data["status"])
            needed_time = start_time + calc_need + (24 * 60 * 60)
            if current_date >= needed_time:
                self.logger.warn(f"{ani}: anime already ended, skipping...")
                continue
            self.logger.info(f"{server_message}: requesting {ani}")
            fetch_anime_jobs.append(
                fetch_anilist(srv_data["anime"][ani]["anilist_id"], 1, jadwal_only=True)
            )

        self.logger.info(f"{server_message}: running jobs...")
        for anime_job in asyncio.as_completed(fetch_anime_jobs):
            time_data, time_until, episode, title = await anime_job
            if not isinstance(time_data, str):
                continue
            await simple_queue.put({"t": time_until, "d": [title, time_data, episode]})

        self.logger.info(f"{server_message}: starting queue...")
        while not simple_queue.empty():
            data_map = await simple_queue.get()
            time_until, data = data_map["t"], data_map["d"]
            if time_until in time_data_list:  # For anime that air at the same time
                time_until += 1
                while True:
                    if time_until not in time_data_list:
                        break
                    time_until += 1
            time_data_list[time_until] = data
            simple_queue.task_done()

        sorted_time = sorted(deepcopy(time_data_list))
        appendtext = ""
        self.logger.info(f"{server_message}: generating result...")
        for s in sorted_time:
            animay, time_data, episode = time_data_list[s]
            appendtext += "**{}** - #{}\n".format(animay, episode)
            appendtext += time_data + "\n\n"

        self.logger.info(f"{server_message}: sending message...")
        if appendtext != "":
            await ctx.send(appendtext.strip())
        else:
            await ctx.send("**Tidak ada utang pada musim ini yang terdaftar**")

    @commands.command(aliases=["tukangdelay", "pendelay"])
    @commands.guild_only()
    async def staff(self, ctx, *, judul):
        """
        Menagih utang fansub tukang diley maupun
        tidak untuk memberikan mereka tekanan
        ---
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        staff_assignment = srv_data["anime"][matches[0]]["staff_assignment"]
        self.logger.info(f"{server_message}: parsing staff data...")

        rtext = "Staff yang mengerjakaan **{}**\n**Admin**: ".format(matches[0])
        rtext += ""

        async def get_user_name(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return "{}#{}".format(user_data.name, user_data.discriminator)
            except Exception:
                return "[Rahasia]"

        new_srv_owner = []
        for adm in srv_owner:
            user = await get_user_name(adm)
            new_srv_owner.append(user)

        rtext += ", ".join(new_srv_owner)

        rtext += "\n**Role**: {}".format(
            self.get_role_name(srv_data["anime"][matches[0]]["role_id"], ctx.message.guild.roles,)
        )

        if "kolaborasi" in srv_data["anime"][matches[0]]:
            k_list = []
            for other_srv in srv_data["anime"][matches[0]]["kolaborasi"]:
                if server_message == other_srv:
                    continue
                server_data = self.bot.get_guild(int(other_srv))
                if not server_data:
                    self.logger.warn(f"{other_srv}: can't find server on Discord.")
                    self.logger.warn(f"{other_srv}: is the bot on that server.")
                    continue
                k_list.append(server_data.name)
            if k_list:
                rtext += "\n**Kolaborasi dengan**: {}".format(", ".join(k_list))

        rtext += "\n\n"

        for k, v in staff_assignment.items():
            try:
                user = await get_user_name(v)
                rtext += "**{}**: {}\n".format(k, user)
            except discord.errors.NotFound:
                rtext += "**{}**: Unknown\n".format(k)

        rtext += "\n**Jika ada yang Unknown, admin dapat menggantikannya**"

        self.logger.info(f"{server_message}: sending message!")
        await ctx.send(rtext)

    @commands.command(aliases=["mark"])
    @commands.guild_only()
    async def tandakan(self, ctx, posisi: str, episode_n: str, *, judul):
        """
        Mark something as done or undone for
        other episode without announcing it
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        posisi, posisi_asli = await self.get_roles(posisi)
        if posisi is None:
            self.logger.warn(f"unknown position.")
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(self.bot, ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]

        if episode_n not in status_list:
            self.logger.warn(f"{matches[0]}: episode out of range.")
            return await ctx.send("Episode tersebut tidak ada di database.")

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warn(f"{matches[0]}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        # Toggle status section
        if str(ctx.message.author.id) != program_info["staff_assignment"][posisi]:
            if str(ctx.message.author.id) not in srv_owner:
                self.logger.warn(f"{matches[0]}: no access to set to mark it.")
                return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        pos_status = status_list[str(episode_n)]["staff_status"]

        osrv_dumped = {}
        self.logger.info(f"{matches[0]}: marking episode {current}...")
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.srv_fetch(other_srv)
                if osrv_data is None:
                    continue
                if pos_status[posisi] == "x":
                    osrv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][
                        posisi
                    ] = "y"
                elif pos_status[posisi] == "y":
                    osrv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][
                        posisi
                    ] = "x"
                await store_queue(SaveQueueData(osrv_data, other_srv, self.bot.fcwd))
                osrv_dumped[other_srv] = osrv_data

        if pos_status[posisi] == "x":
            srv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][posisi] = "y"
            txt_msg = "Berhasil mengubah status **{st}** **{an}** episode **#{ep}** ke **beres**"  # noqa: E501
        elif pos_status[posisi] == "y":
            srv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][posisi] = "x"
            txt_msg = "Berhasil mengubah status **{st}** **{an}** episode **#{ep}** ke **belum beres**"  # noqa: E501

        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        await ctx.send(txt_msg.format(st=posisi, an=matches[0], ep=episode_n))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)


class ShowtimesAlias(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesAlias, self).__init__()
        self.bot = bot
        self.cog_name = "Showtimes Alias"
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes.ShowtimesAlias")

    def __str__(self):
        return "Showtimes Alias"

    @commands.group()
    @commands.guild_only()
    async def alias(self, ctx):
        """
        Initiate alias creation for certain anime
        """
        if not ctx.invoked_subcommand:
            server_message = str(ctx.message.guild.id)
            self.logger.info(f"requested at {server_message}")
            srv_data = await self.srv_fetch(server_message)

            if srv_data is not None:
                return
            self.logger.info(f"{server_message}: data found.")

            if str(ctx.message.author.id) not in srv_data["serverowner"]:
                self.logger.warn(f"{server_message}: not the server admin")
                return await ctx.send("Hanya admin yang bisa menambah alias")

            srv_anilist, _ = await self.collect_anime_with_alias(
                srv_data["anime"], srv_data["alias"]
            )

            if len(srv_anilist) < 1:
                self.logger.warn(f"{server_message}: no registered data on database.")
                return await ctx.send("Tidak ada anime yang terdaftar di database")

            self.logger.info(f"{server_message}: generating initial data...")
            embed = discord.Embed(title="Alias", color=0x56ACF3)
            embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            emb_msg = await ctx.send(embed=embed)
            msg_author = ctx.message.author
            json_tables = {"alias_anime": "", "target_anime": ""}

            def check_if_author(m):
                return m.author == msg_author

            async def process_anime(table, emb_msg, anime_list):
                self.logger.info(f"{server_message}: processing anime...")
                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Judul/Garapan Anime",
                    value="Ketik judul animenya (yang asli), bisa disingkat",
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                await_msg = await self.bot.wait_for("message", check=check_if_author)
                matches = self.get_close_matches(await_msg.content, anime_list)
                await await_msg.delete()
                if not matches:
                    await ctx.send("Tidak dapat menemukan judul tersebut di database")
                    return False, False
                elif len(matches) > 1:
                    matches = await self.choose_anime(ctx, matches)
                    if not matches:
                        return await ctx.send("**Dibatalkan!**")

                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Apakah benar?", value="Judul: **{}**".format(matches[0]), inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)

                to_react = ["✅", "❌"]
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != msg_author:
                    pass
                elif "✅" in str(res.emoji):
                    table["target_anime"] = matches[0]
                    await emb_msg.clear_reactions()
                elif "❌" in str(res.emoji):
                    await ctx.send("**Dibatalkan!**")
                    await emb_msg.clear_reactions()
                    return False, False

                return table, emb_msg

            async def process_alias(table, emb_msg):
                self.logger.info(f"{server_message}: processing alias...")
                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Alias", value="Ketik alias yang diinginkan", inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                await_msg = await self.bot.wait_for("message", check=check_if_author)
                table["alias_anime"] = await_msg.content
                await await_msg.delete()

                return table, emb_msg

            json_tables, emb_msg = await process_anime(json_tables, emb_msg, srv_anilist)

            if not json_tables:
                self.logger.warn(f"{server_message}: cancelling process...")
                return

            json_tables, emb_msg = await process_alias(json_tables, emb_msg)
            self.logger.info(f"{server_message}: final checking...")
            first_time = True
            cancel_toggled = False
            while True:
                embed = discord.Embed(
                    title="Alias",
                    description="Periksa data!\nReact jika ingin diubah.",
                    color=0xE7E363,
                )
                embed.add_field(
                    name="1⃣ Anime/Garapan",
                    value="{}".format(json_tables["target_anime"]),
                    inline=False,
                )
                embed.add_field(
                    name="2⃣ Alias", value="{}".format(json_tables["alias_anime"]), inline=False,
                )
                embed.add_field(
                    name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                if first_time:
                    await emb_msg.delete()
                    emb_msg = await ctx.send(embed=embed)
                    first_time = False
                else:
                    await emb_msg.edit(embed=embed)

                to_react = ["1⃣", "2⃣", "✅", "❌"]
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                if to_react[0] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    json_tables, emb_msg = await process_anime(json_tables, emb_msg, srv_anilist)
                elif to_react[1] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    json_tables, emb_msg = await process_alias(json_tables, emb_msg)
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                elif "❌" in str(res.emoji):
                    self.logger.warn(f"{server_message}: cancelled!")
                    cancel_toggled = True
                    await emb_msg.clear_reactions()
                    break

            if cancel_toggled:
                self.logger.warn(f"{server_message}: cancelling process...")
                return await ctx.send("**Dibatalkan!**")

            # Everything are done and now processing data
            self.logger.info(f"{server_message}: saving data...")
            embed = discord.Embed(title="Alias", color=0x56ACF3)
            embed.add_field(name="Memproses!", value="Membuat data...", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            if json_tables["alias_anime"] in srv_data["alias"]:
                embed = discord.Embed(title="Alias", color=0xE24545)
                embed.add_field(
                    name="Dibatalkan!",
                    value="Alias **{}** sudah terdaftar untuk **{}**".format(
                        json_tables["alias_anime"], srv_data["alias"][json_tables["alias_anime"]],
                    ),
                    inline=True,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.delete()
                return await ctx.send(embed=embed)

            srv_data["alias"][json_tables["alias_anime"]] = json_tables["target_anime"]

            embed = discord.Embed(title="Alias", color=0x56ACF3)
            embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            self.logger.info(f"{server_message}: storing data...")
            await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
            embed = discord.Embed(title="Alias", color=0x96DF6A)
            embed.add_field(
                name="Sukses!",
                value="Alias **{} ({})** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                    json_tables["alias_anime"], json_tables["target_anime"]
                ),
                inline=True,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await ctx.send(embed=embed)
            await emb_msg.delete()

            self.logger.info(f"{server_message}: updating database...")
            success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)

            if not success:
                self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                if server_message not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(server_message)

            await ctx.send(
                "Berhasil menambahkan alias **{} ({})** ke dalam database utama naoTimes".format(  # noqa: E501
                    json_tables["alias_anime"], json_tables["target_anime"]
                )
            )

    @alias.command(name="list")
    async def alias_list(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if not srv_data["alias"]:
            return await ctx.send("Tidak ada alias yang terdaftar.")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = self.get_close_matches(judul, srv_anilist)
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        srv_anilist_alias = []
        for k, v in srv_data["alias"].items():
            if v in matches:
                srv_anilist_alias.append(k)

        text_value = ""
        if not srv_anilist_alias:
            text_value += "Tidak ada"

        if not text_value:
            text_value += self.make_numbered_alias(srv_anilist_alias)

        self.logger.info(f"{server_message}: sending alias!")
        embed = discord.Embed(title="Alias list", color=0x47E0A7)
        embed.add_field(name=matches[0], value=text_value, inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

    @alias.command(name="hapus", aliases=["remove"])
    async def alias_hapus(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warn(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa menghapus alias")

        if not srv_data["alias"]:
            return await ctx.send("Tidak ada alias yang terdaftar.")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        matches = self.get_close_matches(judul, srv_anilist)
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        srv_anilist_alias = []
        for k, v in srv_data["alias"].items():
            if v in matches:
                srv_anilist_alias.append(k)

        if not srv_anilist_alias:
            self.logger.info(f"{matches[0]}: no registered alias.")
            return await ctx.send(
                "Tidak ada alias yang terdaftar untuk judul **{}**".format(matches[0])
            )

        alias_chunked = [srv_anilist_alias[i : i + 5] for i in range(0, len(srv_anilist_alias), 5)]

        first_run = True
        n = 1
        max_n = len(alias_chunked)
        while True:
            if first_run:
                self.logger.info(f"{server_message}: sending results...")
                n = 1
                first_run = False
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name="{}".format(matches[0]),
                    value=self.make_numbered_alias(alias_chunked[n - 1]),
                    inline=False,
                )
                embed.add_field(
                    name="*Informasi*",
                    value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya" "\n⏩ Selanjutnya\n❌ Batalkan",
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                emb_msg = await ctx.send(embed=embed)

            react_ext = []
            to_react = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣"]  # 5 per page
            if max_n == 1 and n == 1:
                pass
            elif n == 1:
                react_ext.append("⏩")
            elif n == max_n:
                react_ext.append("⏪")
            elif n > 1 and n < max_n:
                react_ext.extend(["⏪", "⏩"])

            react_ext.append("❌")
            to_react = to_react[0 : len(alias_chunked[n - 1])]
            to_react.extend(react_ext)

            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", check=check_react, timeout=30.0)
            except asyncio.TimeoutError:
                return await emb_msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                n = n - 1
                await emb_msg.clear_reactions()
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name="{}".format(matches[0]),
                    value=self.make_numbered_alias(alias_chunked[n - 1]),
                    inline=False,
                )
                embed.add_field(
                    name="*Informasi*",
                    value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya" "\n⏩ Selanjutnya\n❌ Batalkan",
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                n = n + 1
                await emb_msg.clear_reactions()
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name="{}".format(matches[0]),
                    value=self.make_numbered_alias(alias_chunked[n - 1]),
                    inline=False,
                )
                embed.add_field(
                    name="*Informasi*",
                    value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya" "\n⏩ Selanjutnya\n❌ Batalkan",
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)
            elif "❌" in str(res.emoji):
                self.logger.warn(f"{server_message}: cancelling...")
                await emb_msg.clear_reactions()
                return await ctx.send("**Dibatalkan!**")
            else:
                self.logger.info(f"{server_message}: updating alias list!")
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                index_del = to_react.index(str(res.emoji))
                n_del = alias_chunked[n - 1][index_del]
                del srv_data["alias"][n_del]

                await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
                await ctx.send(
                    "Alias **{} ({})** telah dihapus dari database".format(n_del, matches[0])
                )

                self.logger.info(f"{server_message}: updating database...")
                success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)

                if not success:
                    self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                    if server_message not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(server_message)

                await emb_msg.delete()


class ShowtimesKolaborasi(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesKolaborasi, self).__init__()
        self.bot = bot
        self.cog_name = "Showtimes Kolaborasi"
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.srv_lists = partial(self.fetch_servers, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes.ShowtimesKolaborasi")

    def __str__(self):
        return "Showtimes Kolaborasi"

    @commands.group(aliases=["joint", "join", "koleb"])
    @commands.guild_only()
    async def kolaborasi(self, ctx):
        if not ctx.invoked_subcommand:
            helpcmd = HelpGenerator(self.bot, "kolaborasi", f"Versi {self.bot.semver}")
            await helpcmd.generate_field(
                "kolaborasi", desc="Memunculkan bantuan perintah", use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi dengan",
                desc="Memulai proses kolaborasi garapan dengan fansub lain.",
                opts=[
                    {"name": "server id kolaborasi", "type": "r"},
                    {"name": "judul", "type": "r"},
                ],
                use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi konfirmasi",
                desc="Konfirmasi proses kolaborasi garapan.",
                opts=[{"name": "kode unik", "type": "r"}],
                use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi putus",
                desc="Memutuskan hubungan kolaborasi suatu garapan.",
                opts=[{"name": "judul", "type": "r"}],
                use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi batalkan",
                desc="Membatalkan proses kolaborasi.",
                opts=[
                    {"name": "server id kolaborasi", "type": "r"},
                    {"name": "kode unik", "type": "r"},
                ],
                use_fullquote=True,
            )
            await helpcmd.generate_aliases(["joint", "join", "koleb"])
            await ctx.send(embed=helpcmd.get())

    @kolaborasi.command(name="dengan", aliases=["with"])
    async def kolaborasi_dengan(self, ctx, server_id, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warn(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa memulai kolaborasi")

        target_server = await self.srv_fetch(server_id)
        if target_server is None:
            self.logger.warn(f"{server_id}: can't find the server.")
            return await ctx.send("Tidak dapat menemukan server tersebut di database")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")

        if "kolaborasi" in srv_data["anime"][matches[0]]:
            if server_id in srv_data["anime"][matches[0]]["kolaborasi"]:
                self.logger.info(f"{matches[0]}: already on collab.")
                return await ctx.send("Server tersebut sudah diajak kolaborasi.")

        randomize_confirm = "".join(choice(ascii_lowercase + digits) for i in range(16))

        cancel_toggled = False
        first_time = True
        while True:
            try:
                server_identd = self.bot.get_guild(int(server_id))
                server_ident = server_identd.name
            except Exception:
                server_ident = server_id
            embed = discord.Embed(
                title="Kolaborasi",
                description="Periksa data!\nReact jika ingin diubah.",
                color=0xE7E363,
            )
            embed.add_field(name="Anime/Garapan", value=matches[0], inline=False)
            embed.add_field(name="Server", value=server_ident, inline=False)
            embed.add_field(
                name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = ["✅", "❌"]
            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                self.logger.warn(f"{matches[0]}: cancelling...")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        table_data = {}
        table_data["anime"] = matches[0]
        table_data["server"] = server_message

        if "konfirmasi" not in target_server:
            target_server["konfirmasi"] = {}
        target_server["konfirmasi"][randomize_confirm] = table_data

        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}-{server_id}: storing data...")
        await store_queue(SaveQueueData(target_server, server_id, self.bot.fcwd))
        # await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))  # noqa: E501
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berikan kode berikut `{}` kepada fansub/server lain.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                randomize_confirm
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.delete()
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating database...")
        success, msg = await self.bot.ntdb.kolaborasi_dengan(
            server_id, randomize_confirm, table_data
        )

        if not success:
            self.logger.error(f"{server_id}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berikan kode berikut `{rand}` kepada fansub/server lain.\nKonfirmasi di server lain dengan `!kolaborasi konfirmasi {rand}`".format(  # noqa: E501
                rand=randomize_confirm
            )
        )

    @kolaborasi.command(name="konfirmasi", aliases=["confirm"])
    async def kolaborasi_konfirmasi(self, ctx, konfirm_id):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warn(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa konfirmasi kolaborasi.")

        if "konfirmasi" not in srv_data:
            self.logger.warn(f"{server_message}: nothing to confirm.")
            return await ctx.send("Tidak ada kolaborasi yang harus dikonfirmasi.")
        if konfirm_id not in srv_data["konfirmasi"]:
            self.logger.warn(f"{konfirm_id}: can't find that confirm id.")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")

        klb_data = srv_data["konfirmasi"][konfirm_id]

        try:
            server_identd = self.bot.get_guild(int(klb_data["server"]))
            server_ident = server_identd.name
        except Exception:
            server_ident = klb_data["server"]

        embed = discord.Embed(title="Konfirmasi Kolaborasi", color=0xE7E363)
        embed.add_field(name="Anime/Garapan", value=klb_data["anime"], inline=False)
        embed.add_field(name="Server", value=server_ident, inline=False)
        embed.add_field(name="Lain-Lain", value="✅ Konfirmasi!\n❌ Batalkan!", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)

        to_react = ["✅", "❌"]
        for react in to_react:
            await emb_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != emb_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        res, user = await self.bot.wait_for("reaction_add", check=check_react)
        if user != ctx.message.author:
            pass
        if "✅" in str(res.emoji):
            await emb_msg.clear_reactions()
        elif "❌" in str(res.emoji):
            self.logger.warn(f"{server_message}: cancelling...")
            await emb_msg.clear_reactions()
            return await ctx.send("**Dibatalkan!**")

        ani_srv_role = ""
        if klb_data["anime"] in srv_data["anime"]:
            self.logger.warn(f"{server_message}: existing data, changing with source server")
            ani_srv_role += srv_data["anime"][klb_data["anime"]]["role_id"]
            del srv_data["anime"][klb_data["anime"]]

        if not ani_srv_role:
            self.logger.info(f"{server_message}: creating roles...")
            c_role = await ctx.message.guild.create_role(
                name=klb_data["anime"], colour=discord.Colour(0xDF2705), mentionable=True,
            )
            ani_srv_role = str(c_role.id)

        srv_source = klb_data["server"]
        source_srv_data = await self.srv_fetch(srv_source)

        other_anime_data = source_srv_data["anime"][klb_data["anime"]]
        copied_data = deepcopy(other_anime_data)
        srv_data["anime"][klb_data["anime"]] = copied_data
        srv_data["anime"][klb_data["anime"]]["role_id"] = ani_srv_role

        join_srv = [klb_data["server"], server_message]
        if "kolaborasi" in srv_data["anime"][klb_data["anime"]]:
            join_srv.extend(srv_data["anime"][klb_data["anime"]]["kolaborasi"])
        join_srv = list(dict.fromkeys(join_srv))
        if "kolaborasi" in other_anime_data:
            join_srv.extend(other_anime_data["kolaborasi"])
        join_srv = list(dict.fromkeys(join_srv))
        other_anime_data["kolaborasi"] = join_srv

        srv_data["anime"][klb_data["anime"]]["kolaborasi"] = join_srv
        del srv_data["konfirmasi"][konfirm_id]

        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}-{srv_source}: storing data...")
        await store_queue(SaveQueueData(source_srv_data, srv_source, self.bot.fcwd))
        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berhasil konfirmasi dengan server **{}**.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                klb_data["server"]
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.delete()
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.kolaborasi_konfirmasi(
            klb_data["server"], server_message, source_srv_data, srv_data,
        )

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berhasil menambahkan kolaborasi dengan **{}** ke dalam database utama naoTimes\nBerikan role berikut agar bisa menggunakan perintah staff <@&{}>".format(  # noqa: E501
                klb_data["server"], ani_srv_role
            )
        )

    @kolaborasi.command(name="batalkan")
    async def kolaborasi_batalkan(self, ctx, server_id, konfirm_id):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warn(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa membatalkan kolaborasi")

        other_srv_data = await self.srv_fetch(server_id)
        if other_srv_data is None:
            self.logger.warn(f"{server_message}: can't find target server.")
            return await ctx.send("Tidak dapat menemukan server tersebut di database")

        if "konfirmasi" not in other_srv_data:
            self.logger.warn(f"{server_message}: nothing to confirm.")
            return await ctx.send("Tidak ada kolaborasi yang harus dikonfirmasi.")
        if konfirm_id not in other_srv_data["konfirmasi"]:
            self.logger.warn(f"{server_message}: can't find that confirm id.")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")

        del other_srv_data["konfirmasi"][konfirm_id]

        self.logger.info(f"{server_message}-{server_id}: storing data...")
        await store_queue(SaveQueueData(other_srv_data, server_id, self.bot.fcwd))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berhasil membatalkan kode konfirmasi **{}**.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                konfirm_id
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating database...")
        success, msg = await self.bot.ntdb.kolaborasi_batalkan(server_id, konfirm_id)

        if not success:
            self.logger.error(f"{server_id}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berhasil membatalkan kode konfirmasi **{}** dari database utama naoTimes".format(  # noqa: E501
                konfirm_id
            )
        )

    @kolaborasi.command()
    async def putus(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            return await ctx.send("Hanya admin yang bisa memputuskan kolaborasi")

        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]

        if "kolaborasi" not in program_info:
            self.logger.warn(f"{server_message}: no registered collaboration on this title.")
            return await ctx.send("Tidak ada kolaborasi sama sekali pada judul ini.")

        self.logger.warn(f"{matches[0]}: start removing server from other server...")
        for osrv in program_info["kolaborasi"]:
            if osrv == server_message:
                continue
            osrv_data = await self.srv_fetch(osrv)
            klosrv = deepcopy(osrv_data["anime"][matches[0]]["kolaborasi"])
            klosrv.remove(server_message)

            remove_all = False
            if len(klosrv) == 1:
                if klosrv[0] == osrv:
                    remove_all = True

            if remove_all:
                del osrv_data["anime"][matches[0]]["kolaborasi"]
            else:
                osrv_data["anime"][matches[0]]["kolaborasi"] = klosrv
            await store_queue(SaveQueueData(osrv_data, osrv, self.bot.fcwd))
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        self.logger.info(f"{server_message}: storing data...")
        del srv_data["anime"][matches[0]]["kolaborasi"]
        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berhasil memputuskan kolaborasi **{}**.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                matches[0]
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.kolaborasi_putuskan(server_message, matches[0])

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berhasil memputuskan kolaborasi **{}** dari database utama naoTimes".format(  # noqa: E501
                matches[0]
            )
        )


class ShowtimesAdmin(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesAdmin, self).__init__()
        self.bot = bot
        self.bot_config = bot.botconf
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.srv_lists = partial(self.fetch_servers, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes.ShowtimesAdmin")

    def __str__(self):
        return "Showtimes Admin"

    @commands.group(aliases=["naotimesadmin", "naoadmin"])
    @commands.is_owner()
    @commands.guild_only()
    async def ntadmin(self, ctx):
        if ctx.invoked_subcommand is None:
            helpcmd = HelpGenerator(self.bot, "ntadmin", desc=f"Versi {self.bot.semver}",)
            await helpcmd.generate_field(
                "ntadmin", desc="Memunculkan bantuan perintah ini.",
            )
            await helpcmd.generate_field(
                "ntadmin initiate", desc="Menginisiasi showtimes.",
            )
            await helpcmd.generate_field(
                "ntadmin tambah",
                desc="Menambah server baru ke database naoTimes.",
                opts=[
                    {"name": "server id", "type": "r"},
                    {"name": "admin id", "type": "r"},
                    {"name": "#progress channel", "type": "o"},
                ],
            )
            await helpcmd.generate_field(
                "ntadmin hapus",
                desc="Menghapus server dari database naoTimes.",
                opts=[{"name": "server id", "type": "r"}],
            )
            await helpcmd.generate_field(
                "ntadmin tambahadmin",
                desc="Menambah admin ke server baru " "yang terdaftar di database.",
                opts=[{"name": "server id", "type": "r"}, {"name": "admin id", "type": "r"},],
            )
            await helpcmd.generate_field(
                "ntadmin hapusadmin",
                desc="Menghapus admin dari server baru yang" " terdaftar di database.",
                opts=[{"name": "server id", "type": "r"}, {"name": "admin id", "type": "r"},],
            )
            await helpcmd.generate_field(
                "ntadmin fetchdb", desc="Mengambil database lokal dan kirim ke Discord.",
            )
            await helpcmd.generate_field(
                "ntadmin patchdb", desc="Update database dengan file yang dikirim user.",
            )
            await helpcmd.generate_field(
                "ntadmin forcepull", desc="Update paksa database lokal dengan database utama.",
            )
            await helpcmd.generate_field(
                "ntadmin forceupdate", desc="Update paksa database utama dengan database lokal.",
            )
            await helpcmd.generate_aliases(["naotimesadmin", "naoadmin"])
            await ctx.send(embed=helpcmd.get())

    @ntadmin.command()
    async def listserver(self, ctx):
        print("[#] Requested !ntadmin listserver by admin")
        srv_dumps = await self.srv_lists()
        if not srv_dumps:
            return

        srv_list = []
        for srv in srv_dumps:
            if srv == "supermod":
                continue
            srv_ = self.bot.get_guild(int(srv))
            if not srv_:
                print(f"[$] Unknown server: {srv}")
                continue
            srv_list.append(f"{srv_.name} ({srv})")

        text = "**List server ({} servers):**\n".format(len(srv_list))
        for x in srv_list:
            text += x + "\n"

        text = text.rstrip("\n")

        await ctx.send(text)

    @ntadmin.command()
    async def listresync(self, ctx):
        resynclist = self.bot.showtimes_resync
        if not resynclist:
            return await ctx.send("**Server that still need to be resynced**: None")
        resynclist = ["- {}\n".format(x) for x in resynclist]
        main_text = "**Server that still need to be resynced**:\n"
        main_text += "".join(resynclist)
        main_text = main_text.rstrip("\n")
        await ctx.send(main_text)

    @ntadmin.command()
    async def migratedb(self, ctx):
        await ctx.send("Mulai migrasi database!")
        url = "https://gist.githubusercontent.com/{u}/{g}/raw/nao_showtimes.json"
        async with aiohttp.ClientSession() as session:
            while True:
                headers = {"User-Agent": "naoTimes v2.0"}
                print("\t[#] Fetching nao_showtimes.json")
                async with session.get(
                    url.format(
                        u=self.bot_config["github_info"]["username"], g=self.bot_config["gist_id"],
                    ),
                    headers=headers,
                ) as r:
                    try:
                        r_data = await r.text()
                        js_data = ujson.loads(r_data)
                        print("\t[@] Fetched and saved.")
                        break
                    except IndexError:
                        pass
        await ctx.send("Berhasil mendapatkan database dari github, " "mulai migrasi ke MongoDB")
        await self.bot.ntdb.patch_all_from_json(js_data)
        await ctx.send("Selesai migrasi database, silakan di coba cuk.")

    @ntadmin.command()
    async def initiate(self, ctx):
        """
        Initiate naoTimes on this server so it can be used on other server
        Make sure everything is filled first before starting this command
        """
        print("[@] Initiated naoTimes first-time setup")
        if self.bot_config["gist_id"] != "":
            print("[@] Already setup, skipping")
            return await ctx.send("naoTimes sudah dipersiapkan dan sudah bisa digunakan")

        print("Membuat data")
        embed = discord.Embed(title="naoTimes", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "id": "",
            "owner_id": str(msg_author.id),
            "progress_channel": "",
        }

        def check_if_author(m):
            return m.author == ctx.message.author

        async def process_gist(table, emb_msg, author):
            print("[@] Memproses database")
            embed = discord.Embed(title="naoTimes", color=0x96DF6A)
            embed.add_field(name="Gist ID", value="Ketik ID Gist GitHub", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            await_msg = await self.bot.wait_for("message", check=check_if_author)
            table["id"] = str(await_msg.content)

            return table, emb_msg

        async def process_progchan(table, emb_msg, author):
            print("[@] Memproses #progress channel")
            embed = discord.Embed(title="naoTimes", color=0x96DF6A)
            embed.add_field(
                name="#progress channel ID", value="Ketik ID channel", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                if await_msg.content.isdigit():
                    table["progress_channel"] = str(await_msg.content)
                    await await_msg.delete()
                    break
                await await_msg.delete()

            return table, emb_msg

        async def process_owner(table, emb_msg, author):
            print("[@] Memproses ID Owner")
            embed = discord.Embed(title="naoTimes", color=0x96DF6A)
            embed.add_field(
                name="Owner ID", value="Ketik ID Owner server atau mention orangnya", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table["owner_id"] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table["owner_id"] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                await await_msg.delete()

            return table, emb_msg

        json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)

        print("[@] Making sure.")
        first_time = True
        cancel_toggled = False
        while True:
            embed = discord.Embed(
                title="naoTimes",
                description="Periksa data!\nReact jika ingin diubah.",
                color=0xE7E363,
            )
            embed.add_field(
                name="1⃣ Gists ID", value="{}".format(json_tables["id"]), inline=False,
            )
            embed.add_field(
                name="2⃣ Owner ID", value="{}".format(json_tables["owner_id"]), inline=False,
            )
            embed.add_field(
                name="3⃣ #progress channel ID",
                value="{}".format(json_tables["progress_channel"]),
                inline=False,
            )
            embed.add_field(
                name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = ["1⃣", "2⃣", "3⃣", "✅", "❌"]
            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_owner(json_tables, emb_msg, msg_author)
            elif to_react[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                print("[@] Cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        embed = discord.Embed(title="naoTimes", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        main_data = {}
        server_data = {}
        main_data["supermod"] = [json_tables["owner_id"]]

        server_data["serverowner"] = [json_tables["owner_id"]]
        server_data["announce_channel"] = json_tables["progress_channel"]
        server_data["anime"] = {}
        server_data["alias"] = {}

        main_data[str(ctx.message.guild.id)] = server_data
        print("[@] Sending data")
        for srv_patch, srv_data_patch in main_data.items():
            if srv_patch == "supermod":
                await self.dumps_super_admins(srv_data_patch, self.bot.fcwd)
            else:
                await store_queue(SaveQueueData(srv_data_patch, srv_patch, self.bot.fcwd))
        _ = await self.bot.ntdb.patch_all_from_json(main_data)

        print("[@] Reconfiguring config files")
        self.bot_config["gist_id"] = json_tables["gist_id"]
        await write_files(self.bot_config, "config.json")
        print("[@] Reconfigured. Every configuration are done, please restart.")
        embed = discord.Embed(title="naoTimes", color=0x56ACF3)
        embed.add_field(
            name="Sukses!",
            value="Sukses membuat database di github\n"
            "Silakan restart bot agar naoTimes dapat diaktifkan.\n\n"
            "Laporkan isu di: "
            "[GitHub Issue](https://github.com/noaione/naoTimes/issues)",
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)
        await emb_msg.delete()

    @ntadmin.command()
    async def fetchdb(self, ctx):
        print("[#] Requested !ntadmin fetchdb by admin")
        srv_lists = await self.srv_lists()
        if not srv_lists:
            return

        async def _internal_fetch(srv_id):
            data_res = await self.srv_fetch(srv_id)
            return data_res, srv_id

        channel = ctx.message.channel
        fetch_jobs = [_internal_fetch(srv) for srv in srv_lists]

        final_dataset = {}
        for fjob in asyncio.as_completed(fetch_jobs):
            data_res, srv_id = await fjob
            if data_res is not None:
                final_dataset[srv_id] = data_res

        super_admin = await self.fetch_super_admins(self.bot.fcwd)
        final_dataset["supermod"] = super_admin

        print("Saving .json")
        save_file_name = str(int(round(time.time()))) + "_naoTimes_database.json"
        await write_files(final_dataset, save_file_name)

        print("Sending .json")
        await channel.send(content="Here you go!", file=discord.File(save_file_name))
        os.remove(save_file_name)  # Cleanup

    @ntadmin.command()
    async def forcepull(self, ctx):
        print("[#] Requested !ntadmin forcepull by owner")
        channel = ctx.message.channel

        json_d = await self.bot.ntdb.fetch_all_as_json()
        for srv, srv_data in json_d.items():
            if srv == "supermod":
                await self.dumps_super_admins(srv_data, self.bot.fcwd)
            else:
                await store_queue(SaveQueueData(srv_data, srv, self.bot.fcwd))
        await channel.send("Newest database has been pulled and saved to local save")

    @ntadmin.command()
    @commands.guild_only()
    async def patchdb(self, ctx):
        """
        !! Warning !!
        This will patch entire database
        """
        print("[#] Requested !ntadmin patchdb by admin")

        if ctx.message.attachments == []:
            await ctx.message.delete()
            return await ctx.send(
                "Please provide a valid .json file by uploading "
                "and add `!!ntadmin patchdb` command"
            )

        print("[@] Fetching attachments")

        attachment = ctx.message.attachments[0]
        uri = attachment.url
        filename = attachment.filename

        if filename[filename.rfind(".") :] != ".json":
            await ctx.message.delete()
            return await ctx.send(
                "Please provide a valid .json file by uploading "
                "and add `!!ntadmin patchdb` command"
            )

        # Start downloading .json file
        print("[@] Downloading file")
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(uri) as resp:
                data = await resp.text()
                await ctx.message.delete()
                json_to_patch = ujson.loads(data)

        print("[@] Make sure.")
        preview_msg = await ctx.send(
            "**Are you sure you want to patch " "the database with provided .json file?**"
        )
        to_react = ["✅", "❌"]
        for react in to_react:
            await preview_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != preview_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        try:
            res, user = await self.bot.wait_for("reaction_add", timeout=15, check=check_react)
        except asyncio.TimeoutError:
            await ctx.send("***Timeout!***")
            return await preview_msg.clear_reactions()
        if user != ctx.message.author:
            pass
        elif "✅" in str(res.emoji):
            for srv, srv_data in json_to_patch.items():
                if srv == "supermod":
                    await self.dumps_super_admins(srv_data, self.bot.fcwd)
                else:
                    await store_queue(SaveQueueData(srv_data, srv, self.bot.fcwd))
            success = await self.bot.ntdb.patch_all_from_json(json_to_patch)
            await preview_msg.clear_reactions()
            if success:
                return await preview_msg.edit(content="**Patching success!, try it with !tagih**")
            await preview_msg.edit(content="**Patching failed!, try it again later**")
        elif "❌" in str(res.emoji):
            print("[@] Patch Cancelled")
            await preview_msg.clear_reactions()
            await preview_msg.edit(content="**Ok, cancelled process**")

    @ntadmin.command()
    async def tambah(self, ctx, srv_id, adm_id, prog_chan=None):
        """
        Menambah server baru ke database naoTimes

        :srv_id: server id
        :adm_id: admin id
        :prog_chan: #progress channel id
        """

        print("[#] Requested !ntadmin tambah by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")

        if adm_id is None:
            return await ctx.send("Tidak ada input admin dari user")

        new_server = await self.srv_fetch(str(srv_id))
        if new_server is not None:
            return await ctx.send("Server `{}` tersebut telah terdaftar di database".format(srv_id))

        new_srv_data = {}

        new_srv_data["serverowner"] = [str(adm_id)]
        if prog_chan:
            new_srv_data["announce_channel"] = str(prog_chan)
        new_srv_data["anime"] = {}
        new_srv_data["alias"] = {}

        supermod_lists = await self.fetch_super_admins(self.bot.fcwd)
        if str(adm_id) not in supermod_lists:
            supermod_lists.append(str(adm_id))  # Add to supermod list
        print("[#] Created new table for server: {}".format(srv_id))

        await store_queue(SaveQueueData(new_srv_data, str(srv_id), self.bot.fcwd))
        await self.dumps_super_admins(supermod_lists, self.bot.fcwd)
        if not prog_chan:
            prog_chan = None

        success, msg = await self.bot.ntdb.new_server(str(srv_id), str(adm_id), prog_chan)
        if not success:
            print("[%] Failed to update, reason: {}".format(msg))
            if str(srv_id) not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(srv_id))
        await ctx.send(
            "Sukses menambah server dengan info berikut:\n```Server ID: {s}\nAdmin: {a}\nMemakai #progress Channel: {p}```".format(  # noqa: E501
                s=srv_id, a=adm_id, p=bool(prog_chan)
            )
        )

    @ntadmin.command()
    async def hapus(self, ctx, srv_id):
        """
        Menghapus server dari database naoTimes

        :srv_id: server id
        """
        print("[#] Requested !ntadmin hapus by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")
        srv_data = await self.srv_fetch(str(srv_id))

        if srv_data is None:
            return await ctx.send("Server tidak dapat ditemukan dalam database.")
        adm_id = srv_data["serverowner"][0]

        super_admins = await self.fetch_super_admins(self.bot.fcwd)

        try:
            super_admins.remove(adm_id)
        except Exception:
            return await ctx.send("Gagal menghapus admin dari data super admin")

        await self.dumps_super_admins(super_admins, self.bot.fcwd)
        fpath = os.path.join(self.bot.fcwd, "showtimes_folder", f"{srv_id}.showtimes")
        try:
            os.remove(fpath)
        except Exception:
            # FIXME: Add logging here
            pass
        success, msg = await self.bot.ntdb.remove_server(srv_id, adm_id)
        if not success:
            await ctx.send(
                "Terdapat kegagalan ketika ingin menghapus server\nalasan: {}".format(  # noqa: E501
                    msg
                )
            )
        await ctx.send("Sukses menghapus server `{s}` dari naoTimes".format(s=srv_id))

    @ntadmin.command()
    async def tambahadmin(self, ctx, srv_id: str, adm_id: str):
        """
        Menambah admin ke server ke database naoTimes

        :srv_id: server id
        :adm_id: admin id
        """

        print("[#] Requested !ntadmin tambahadmin by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")

        if adm_id is None:
            return await ctx.send("Tidak ada input admin dari user")

        srv_data = await self.srv_fetch(srv_id)

        if srv_data is None:
            return await ctx.send("Server tidak dapat ditemukan dalam database.")

        if adm_id in srv_data["serverowner"]:
            return await ctx.send("Admin sudah terdaftar di server tersebut.")

        srv_data["serverowner"].append(adm_id)

        await store_queue(SaveQueueData(srv_data, srv_id, self.bot.fcwd))
        success, msg = await self.bot.ntdb.update_data_server(srv_id, srv_data)
        if not success:
            print("[%] Failed to update main database data")
            print("\tReason: {}".format(msg))
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        await ctx.send("Sukses menambah admin `{a}` di server `{s}`".format(s=srv_id, a=adm_id))

    @ntadmin.command()
    async def hapusadmin(self, ctx, srv_id: str, adm_id: str):
        """
        Menghapus admin dari server dari database naoTimes

        :srv_id: server id
        :adm_id: admin id
        """
        print("[#] Requested !ntadmin hapusadmin by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")

        if adm_id is None:
            return await ctx.send("Tidak ada input admin dari user")

        srv_data = await self.srv_fetch(srv_id)

        if srv_data is None:
            return await ctx.send("Server tidak dapat ditemukan dalam database.")

        if adm_id not in srv_data["serverowner"]:
            return await ctx.send("Tidak dapat menemukan admin tersebut.")

        srv_data["serverowner"].remove(adm_id)

        await store_queue(SaveQueueData(srv_data, srv_id, self.bot.fcwd))
        print("[%] Removing admin from main database")
        success, msg = await self.bot.ntdb.update_data_server(srv_id, srv_data)
        if not success:
            print("[%] Failed to update main database data")
            print("\tReason: {}".format(msg))
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        await ctx.send("Sukses menghapus admin `{a}` dari server `{s}`".format(s=srv_id, a=adm_id))
        if adm_id in srv_data["serverowner"]:
            success, msg = await self.bot.ntdb.remove_top_admin(adm_id)
            if not success:
                await ctx.send("Tetapi gagal menghapus admin dari top_admin.")


class ShowtimesData(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesData, self).__init__()
        self.bot = bot
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes.ShowtimesData")

    def __str__(self):
        return "Showtimes Data"

    @commands.command()
    @commands.guild_only()
    async def ubahdata(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warn(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa mengubah data garapan.")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )
        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(
            judul, srv_anilist, srv_anilist_alias, srv_data["alias"]
        )
        if not matches:
            self.logger.warn(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        def check_if_author(m):
            return m.author == ctx.message.author

        async def get_user_name(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return "{}#{}".format(user_data.name, user_data.discriminator)
            except Exception:
                return "[Rahasia]"

        async def internal_change_staff(role, staff_list, emb_msg):
            better_names = {
                "TL": "Translator",
                "TLC": "TLCer",
                "ENC": "Encoder",
                "ED": "Editor",
                "TM": "Timer",
                "TS": "Typesetter",
                "QC": "Quality Checker",
            }
            self.logger.info(f"{matches[0]}: changing {role}")
            embed = discord.Embed(title="Mengubah Staff", color=0xEB79B9)
            embed.add_field(
                name="{} ID".format(better_names[role]),
                value="Ketik ID {} atau mention orangnya".format(better_names[role]),
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        staff_list[role] = await_msg.content
                        await await_msg.delete()
                        break
                else:
                    staff_list[role] = str(mentions[0].id)
                    await await_msg.delete()
                    break
            return staff_list, emb_msg

        async def ubah_staff(emb_msg):
            first_run = True
            self.logger.info(f"{matches[0]}: processing staff.")
            while True:
                if first_run:
                    staff_list = deepcopy(srv_data["anime"][matches[0]]["staff_assignment"])
                    staff_list_key = list(staff_list.keys())
                    first_run = False

                staff_list_name = {}
                for k, v in staff_list.items():
                    usr_ = await get_user_name(v)
                    staff_list_name[k] = usr_

                embed = discord.Embed(
                    title="Mengubah Staff",
                    description="Anime: {}".format(matches[0]),
                    color=0xEBA279,
                )
                embed.add_field(name="1⃣ TLor", value=staff_list_name["TL"], inline=False)
                embed.add_field(name="2⃣ TLCer", value=staff_list_name["TLC"], inline=False)
                embed.add_field(
                    name="3⃣ Encoder", value=staff_list_name["ENC"], inline=False,
                )
                embed.add_field(name="4⃣ Editor", value=staff_list_name["ED"], inline=True)
                embed.add_field(name="5⃣ Timer", value=staff_list_name["TM"], inline=True)
                embed.add_field(
                    name="6⃣ Typeseter", value=staff_list_name["TS"], inline=True,
                )
                embed.add_field(name="7⃣ QCer", value=staff_list_name["QC"], inline=True)
                embed.add_field(name="Lain-Lain", value="✅ Selesai!", inline=False)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "✅"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                else:
                    await emb_msg.clear_reactions()
                    reaction_pos = reactmoji.index(str(res.emoji))
                    staff_list, emb_msg = await internal_change_staff(
                        staff_list_key[reaction_pos], staff_list, emb_msg
                    )

            self.logger.info(f"{matches[0]}: setting new staff.")
            srv_data["anime"][matches[0]]["staff_assignment"] = staff_list
            if koleb_list:
                for other_srv in koleb_list:
                    osrv_data = await self.srv_fetch(other_srv)
                    if osrv_data is None:
                        continue
                    osrv_data["anime"][matches[0]]["staff_assignment"] = staff_list
                    await store_queue(SaveQueueData(osrv_data, other_srv, self.bot.fcwd))

            return emb_msg

        async def ubah_role(emb_msg):
            self.logger.info(f"{matches[0]}: processing role.")
            embed = discord.Embed(title="Mengubah Role", color=0xEBA279)
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\n"
                "Atau ketik `auto` untuk membuatnya otomatis",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        srv_data["anime"][matches[0]]["role_id"] = await_msg.content
                        await await_msg.delete()
                        break
                    elif await_msg.content.startswith("auto"):
                        c_role = await ctx.message.guild.create_role(
                            name=matches[0], colour=discord.Colour(0xDF2705), mentionable=True,
                        )
                        srv_data["anime"][matches[0]]["role_id"] = str(c_role.id)
                        await await_msg.delete()
                        break
                else:
                    srv_data["anime"][matches[0]]["role_id"] = str(mentions[0].id)
                    await await_msg.delete()
                    break

            self.logger.info(f"{matches[0]}: setting role...")
            role_ids = srv_data["anime"][matches[0]]["role_id"]
            await send_timed_msg(ctx, f"Berhasil menambah role ID ke {role_ids}", 2)

            return emb_msg

        async def tambah_episode(emb_msg):
            self.logger.info(f"{matches[0]}: adding new episode...")
            status_list = program_info["status"]
            max_episode = list(status_list.keys())[-1]
            _, _, _, time_data, _ = await fetch_anilist(
                program_info["anilist_id"], 1, max_episode, True
            )

            embed = discord.Embed(
                title="Menambah Episode",
                description="Jumlah Episode Sekarang: {}".format(max_episode),
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan jumlah episode yang diinginkan.",
                value=tambahepisode_instruct,
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if await_msg.content.isdigit():
                    jumlah_tambahan = int(await_msg.content)
                    await await_msg.delete()
                    break

            osrv_dumped = {}
            if koleb_list:
                for osrv in koleb_list:
                    osrv_data = await self.srv_fetch(osrv)
                    if osrv_data is None:
                        continue
                    osrv_dumped[osrv] = osrv_data

            self.logger.info(f"{matches[0]}: adding a total of {jumlah_tambahan}...")
            for x in range(
                int(max_episode) + 1, int(max_episode) + jumlah_tambahan + 1
            ):  # range(int(c), int(c)+int(x))
                st_data = {}
                staff_status = {}

                staff_status["TL"] = "x"
                staff_status["TLC"] = "x"
                staff_status["ENC"] = "x"
                staff_status["ED"] = "x"
                staff_status["TM"] = "x"
                staff_status["TS"] = "x"
                staff_status["QC"] = "x"

                st_data["status"] = "not_released"
                try:
                    st_data["airing_time"] = time_data[x - 1]
                except IndexError:
                    pass
                st_data["staff_status"] = staff_status
                if osrv_dumped:
                    for osrv, osrv_data in osrv_dumped.items():
                        osrv_data["anime"][matches[0]]["status"][str(x)] = st_data
                        osrv_dumped[osrv] = osrv_data
                srv_data["anime"][matches[0]]["status"][str(x)] = st_data

            if osrv_dumped:
                for osrv, osrv_data in osrv_dumped.items():
                    osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await store_queue(SaveQueueData(osrv_data, osrv, self.bot.fcwd))
            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            await send_timed_msg(ctx, f"Berhasil menambah {jumlah_tambahan} episode baru", 2)

            return emb_msg

        async def hapus_episode(emb_msg):
            self.logger.info(f"{matches[0]}: removing an episodes...")
            status_list = program_info["status"]
            max_episode = list(status_list.keys())[-1]

            embed = discord.Embed(
                title="Menghapus Episode",
                description="Jumlah Episode Sekarang: {}".format(max_episode),
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan range episode yang ingin dihapus.",
                value=hapusepisode_instruct,
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                jumlah_tambahan = await_msg.content
                embed = discord.Embed(title="Menghapus Episode", color=0xEBA279)
                embed.add_field(
                    name="Apakah Yakin?",
                    value="Range episode: **{}**".format(jumlah_tambahan),
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["✅", "❌"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await await_msg.delete()
                    await emb_msg.clear_reactions()
                    break
                elif "❌" in str(res.emoji):
                    await await_msg.delete()
                    embed = discord.Embed(
                        title="Menghapus Episode",
                        description="Jumlah Episode Sekarang: {}".format(max_episode),
                        color=0xEBA279,
                    )
                    embed.add_field(
                        name="Masukan range episode yang ingin dihapus.",
                        value=hapusepisode_instruct,
                        inline=False,
                    )
                    embed.set_footer(
                        text="Dibawakan oleh naoTimes™®",
                        icon_url="https://p.n4o.xyz/i/nao250px.png",
                    )
                    await emb_msg.edit(embed=embed)
                await emb_msg.clear_reactions()

            total_episode = jumlah_tambahan.split("-")
            if len(total_episode) < 2:
                current = int(total_episode[0])
                total = int(total_episode[0])
            else:
                current = int(total_episode[0])
                total = int(total_episode[1])

            if koleb_list:
                for osrv in koleb_list:
                    osrv_data = await self.srv_fetch(osrv)
                    if osrv_data is None:
                        continue
                    for x in range(current, total + 1):  # range(int(c), int(c)+int(x))
                        del osrv_data["anime"][matches[0]]["status"][str(x)]
                    osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await store_queue(SaveQueueData(osrv_data, osrv, self.bot.fcwd))

            self.logger.info(f"{matches[0]}: removing a total of {total} episodes...")
            for x in range(current, total + 1):  # range(int(c), int(c)+int(x))
                del srv_data["anime"][matches[0]]["status"][str(x)]
            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            await send_timed_msg(ctx, f"Berhasil menghapus episode {current} ke {total}", 2)

            return emb_msg

        async def hapus_utang_tanya(emb_msg):
            delete_ = False
            self.logger.info(f"{matches[0]}: preparing to nuke project...")
            while True:
                embed = discord.Embed(
                    title="Menghapus Utang",
                    description="Anime: {}".format(matches[0]),
                    color=0xCC1C20,
                )
                embed.add_field(
                    name="Peringatan!",
                    value="Utang akan dihapus selama-lamanya dan tidak bisa "
                    "dikembalikan!\nLanjutkan proses?",
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["✅", "❌"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    delete_ = True
                    break
                elif "❌" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                await emb_msg.clear_reactions()
            return emb_msg, delete_

        first_run = True
        exit_command = False
        hapus_utang = False
        while True:
            guild_roles = ctx.message.guild.roles
            total_episodes = len(srv_data["anime"][matches[0]]["status"])
            role_id = srv_data["anime"][matches[0]]["role_id"]
            embed = discord.Embed(
                title="Mengubah Data", description="Anime: {}".format(matches[0]), color=0xE7E363,
            )
            embed.add_field(
                name="1⃣ Ubah Staff", value="Ubah staff yang mengerjakan anime ini.", inline=False,
            )
            embed.add_field(
                name="2⃣ Ubah Role",
                value="Ubah role discord yang digunakan:\n"
                "Role sekarang: {}".format(self.get_role_name(role_id, guild_roles)),
                inline=False,
            )
            embed.add_field(
                name="3⃣ Tambah Episode",
                value="Tambah jumlah episode\n" "Total Episode sekarang: {}".format(total_episodes),
                inline=False,
            )
            embed.add_field(
                name="4⃣ Hapus Episode", value="Hapus episode tertentu.", inline=False,
            )
            embed.add_field(
                name="5⃣ Drop Garapan",
                value="Menghapus garapan ini dari daftar utang " "untuk selama-lamanya...",
                inline=False,
            )
            embed.add_field(name="Lain-Lain", value="✅ Selesai!\n❌ Batalkan!", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                emb_msg = await ctx.send(embed=embed)
                first_run = False
            else:
                await emb_msg.edit(embed=embed)

            reactmoji = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "✅", "❌"]

            for react in reactmoji:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif reactmoji[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_staff(emb_msg)
            elif reactmoji[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_role(emb_msg)
            elif reactmoji[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await tambah_episode(emb_msg)
            elif reactmoji[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await hapus_episode(emb_msg)
            elif reactmoji[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg, hapus_utang = await hapus_utang_tanya(emb_msg)
                if hapus_utang:
                    await emb_msg.delete()
                    break
            elif reactmoji[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break
            elif reactmoji[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                exit_command = True
                break

        if exit_command:
            self.logger.warn(f"{matches[0]}: cancelling...")
            return await ctx.send("**Dibatalkan!**")
        if hapus_utang:
            self.logger.warn(f"{matches[0]}: nuking project...")
            current = self.get_current_ep(program_info["status"])
            try:
                if program_info["status"]["1"]["status"] == "not_released":
                    announce_it = False
                elif not current:
                    announce_it = False
                else:
                    announce_it = True
            except KeyError:
                announce_it = True

            del srv_data["anime"][matches[0]]
            for osrv in koleb_list:
                osrv_data = await self.srv_fetch(osrv)
                if osrv_data is None:
                    continue
                if "kolaborasi" in osrv_data["anime"][matches[0]]:
                    if server_message in osrv_data["anime"][matches[0]]["kolaborasi"]:
                        klosrv = deepcopy(osrv_data["anime"][matches[0]]["kolaborasi"])
                        klosrv.remove(server_message)

                        remove_all = False
                        if len(klosrv) == 1:
                            if klosrv[0] == osrv:
                                remove_all = True

                        if remove_all:
                            del osrv_data["anime"][matches[0]]["kolaborasi"]
                        else:
                            osrv_data["anime"][matches[0]]["kolaborasi"] = klosrv
                        await store_queue(SaveQueueData(osrv_data, osrv, self.bot.fcwd))

            await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
            self.logger.info(f"{matches[0]}: storing final data...")
            await ctx.send("Berhasil menghapus **{}** dari daftar utang".format(matches[0]))

            self.logger.info(f"{server_message}: updating database...")
            success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
            for osrv in koleb_list:
                if osrv == server_message:
                    continue
                osrv_data = await self.srv_fetch(osrv)
                if osrv_data is None:  # Skip if the server doesn't exist :pepega:
                    continue
                self.logger.info(f"{osrv}: updating database...")
                res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
                if not res2:
                    if osrv not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(osrv)
                    self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

            if not success:
                self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                if server_message not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(server_message)

            if "announce_channel" in srv_data:
                announce_chan = srv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                embed = discord.Embed(title="{}".format(matches[0]), color=0xB51E1E)
                embed.add_field(
                    name="Dropped...",
                    value="{} telah di drop dari fansub ini :(".format(matches[0]),
                    inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                if announce_it:
                    self.logger.info(f"{server_message}: announcing removal of a project...")
                    if target_chan:
                        await target_chan.send(embed=embed)
            return

        self.logger.info(f"{matches[0]}: saving new data...")
        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            osrv_data = await self.srv_fetch(osrv)
            if osrv_data is None:  # Skip if the server doesn't exist :pepega:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send("Berhasil menyimpan data baru untuk garapan **{}**".format(matches[0]))

    @commands.command(aliases=["addnew"])
    @commands.guild_only()
    async def tambahutang(self, ctx):
        """
        Membuat utang baru, ambil semua user id dan role id yang diperlukan.
        ----
        Menggunakan embed agar terlihat lebih enak dibanding sebelumnya
        Merupakan versi 2
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.srv_fetch(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warn(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa menambah utang")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        self.logger.info(f"{server_message}: creating initial data...")
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)
        current_time = int(round(time.time()))
        msg_author = ctx.message.author
        json_tables = {
            "ani_title": "",
            "anilist_id": "",
            "episodes": "",
            "time_data": "",
            "poster_img": "",
            "role_id": "",
            "tlor_id": "",
            "tlcer_id": "",
            "encoder_id": "",
            "editor_id": "",
            "timer_id": "",
            "tser_id": "",
            "qcer_id": "",
            "settings": {"time_data_are_the_same": False},
            "old_time_data": [],
        }
        cancel_toggled = False  # Some easy check if it's gonna fucked up
        first_time = True

        def check_if_author(m):
            return m.author == msg_author

        async def process_episode(table, emb_msg):
            self.logger.info(f"{server_message}: processing total episodes...")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name="Jumlah Episode", value="Ketik Jumlah Episode perkiraan", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if await_msg.content.isdigit():
                    await await_msg.delete()
                    break

                await await_msg.delete()

            _, _, _, time_data, correct_episode_num = await fetch_anilist(
                table["anilist_id"], 1, int(await_msg.content), True
            )
            table["episodes"] = correct_episode_num
            table["time_data"] = time_data

            return table, emb_msg

        async def process_anilist(table, emb_msg):
            self.logger.info(f"{server_message}: processing anime data...")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.add_field(
                name="Anilist ID",
                value="Ketik ID Anilist untuk anime yang diinginkan\n\n"
                "Bisa gunakan `!anime <judul>` dan melihat bagian bawah "
                "untuk IDnya\n\nKetik *cancel* untuk membatalkan proses",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(content="", embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if not await_msg.content.startswith("!anime"):
                    if await_msg.content == ("cancel"):
                        return False, "Dibatalkan oleh user."

                    if await_msg.content.isdigit():
                        await await_msg.delete()
                        break

                    await await_msg.delete()

            (_, poster_data, title, time_data, correct_episode_num,) = await fetch_anilist(
                await_msg.content, 1, 1, True
            )
            poster_image, poster_color = poster_data

            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=poster_image)
            embed.add_field(
                name="Apakah benar?", value="Judul: **{}**".format(title), inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            to_react = ["✅", "❌"]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                try:
                    air_start, _, _ = await fetch_anilist(
                        await_msg.content, 1, 1, return_only_time=True
                    )
                except Exception:
                    self.logger.warn(
                        f"{server_message}: failed to fetch air start, please try again later."
                    )
                    return False, "Gagal mendapatkan start_date, silakan coba lagi ketika sudah ada kepastian kapan animenya mulai."
                table["ani_title"] = title
                table["poster_data"] = {
                    "url": poster_image,
                    "color": poster_color,
                }
                table["anilist_id"] = str(await_msg.content)
                await emb_msg.clear_reactions()
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                return False, "Dibatalkan oleh user."

            if correct_episode_num == 1:
                self.logger.info(f"{server_message}: asking episode total to user...")
                table, emb_msg = await process_episode(table, emb_msg)
            else:
                self.logger.info(f"{server_message}: using anilist episode total...")
                table["episodes"] = correct_episode_num
                table["time_data"] = time_data

            return table, emb_msg

        async def process_role(table, emb_msg):
            self.logger.info(f"{server_message}: processing roles")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\n"
                "Atau ketik `auto` untuk membuatnya otomatis",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        table["role_id"] = await_msg.content
                        await await_msg.delete()
                        break
                    elif await_msg.content.startswith("auto"):
                        self.logger.info(f"{server_message}: auto-generating role...")
                        c_role = await ctx.message.guild.create_role(
                            name=table["ani_title"],
                            colour=discord.Colour(0xDF2705),
                            mentionable=True,
                        )
                        table["role_id"] = str(c_role.id)
                        await await_msg.delete()
                        break
                else:
                    table["role_id"] = mentions[0].id
                    await await_msg.delete()
                    break

            return table, emb_msg

        async def process_staff(table, emb_msg, staffer):
            staffer_mapping = {
                "tl": {"b": "tlor_id", "n": "Translator"},
                "tlc": {"b": "tlcer_id", "n": "TLCer"},
                "enc": {"b": "encoder_id", "n": "Encoder"},
                "ed": {"b": "editor_id", "n": "Editor"},
                "ts": {"b": "tser_id", "n": "Penata Rias"},
                "tm": {"b": "timer_id", "n": "Penata Waktu"},
                "qc": {"b": "qcer_id", "n": "Pemeriksa Akhir"},
            }
            staff_need = staffer_mapping.get(staffer)
            staff_name, table_map = staff_need["n"], staff_need["b"]
            self.logger.info(f"{server_message}: processing {staff_name}")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name=f"{staff_name} ID",
                value=f"Ketik ID Discord {staff_name} atau mention orangnya",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table[table_map] = await_msg.content
                        await await_msg.delete()
                        break
                else:
                    table[table_map] = mentions[0].id
                    await await_msg.delete()
                    break
                # await await_msg.delete()

            return table, emb_msg

        def check_setting(gear):
            if not gear:
                return "❌"
            return "✅"

        async def process_pengaturan(table, emb_msg):
            # Inner settings
            async def gear_1(table, emb_msg, gear_data):
                self.logger.info("pengaturan: setting all time data to be the same.")
                if not gear_data:
                    table["old_time_data"] = table[
                        "time_data"
                    ]  # Make sure old time data are not deleted
                    time_table = table["time_data"]
                    new_time_table = []
                    for _ in time_table:
                        new_time_table.append(time_table[0])

                    table["time_data"] = new_time_table
                    table["settings"]["time_data_are_the_same"] = True
                    return table, emb_msg

                new_time_table = []
                for i, _ in enumerate(table["time_data"]):
                    new_time_table.append(table["old_time_data"][i])

                table["old_time_data"] = []  # Remove old time data because it resetted
                table["settings"]["time_data_are_the_same"] = False
                return table, emb_msg

            self.logger.info("showing settings...")
            while True:
                embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
                embed.set_thumbnail(url=table["poster_img"])
                embed.add_field(
                    name="1⃣ Samakan waktu tayang",
                    value="Status: **{}**\n\nBerguna untuk anime Netflix yang sekali rilis banyak".format(  # noqa: E501
                        check_setting(table["settings"]["time_data_are_the_same"])
                    ),
                    inline=False,
                )
                embed.add_field(name="Lain-Lain", value="⏪ Kembali", inline=False)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                to_react = [
                    "1⃣",
                    "⏪",
                ]
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif to_react[0] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    table, emb_msg = await gear_1(
                        table, emb_msg, table["settings"]["time_data_are_the_same"],
                    )
                elif to_react[-1] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    return table, emb_msg

        json_tables, emb_msg = await process_anilist(json_tables, emb_msg)

        if not json_tables:
            self.logger.warn(f"{server_message}: process cancelled")
            return await ctx.send(emb_msg)

        if json_tables["ani_title"] in srv_anilist:
            self.logger.warn(f"{server_message}: anime already registered on database.")
            return await ctx.send("Anime sudah didaftarkan di database.")

        json_tables, emb_msg = await process_role(json_tables, emb_msg)
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tl")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tlc")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "enc")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ed")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tm")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ts")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "qc")

        async def fetch_username_from_id(_id):
            try:
                user_data = self.bot.get_user(int(_id))
                return "{}#{}".format(user_data.name, user_data.discriminator)
            except Exception:
                return "[Rahasia]"

        self.logger.info(f"{server_message}: checkpoint before commiting")
        while True:
            tl_ = await fetch_username_from_id(json_tables["tlor_id"])
            tlc_ = await fetch_username_from_id(json_tables["tlcer_id"])
            enc_ = await fetch_username_from_id(json_tables["encoder_id"])
            ed_ = await fetch_username_from_id(json_tables["editor_id"])
            tm_ = await fetch_username_from_id(json_tables["timer_id"])
            ts_ = await fetch_username_from_id(json_tables["tser_id"])
            qc_ = await fetch_username_from_id(json_tables["qcer_id"])

            embed = discord.Embed(
                title="Menambah Utang",
                description="Periksa data!\nReact jika ingin diubah.",
                color=0xE7E363,
            )
            embed.set_thumbnail(url=json_tables["poster_img"])
            embed.add_field(
                name="1⃣ Judul",
                value="{} ({})".format(json_tables["ani_title"], json_tables["anilist_id"]),
                inline=False,
            )
            embed.add_field(
                name="2⃣ Episode", value="{}".format(json_tables["episodes"]), inline=False,
            )
            embed.add_field(
                name="3⃣ Role",
                value="{}".format(
                    self.get_role_name(json_tables["role_id"], ctx.message.guild.roles)
                ),
                inline=False,
            )
            embed.add_field(name="4⃣ Translator", value=tl_, inline=True)
            embed.add_field(name="5⃣ TLCer", value=tlc_, inline=True)
            embed.add_field(name="6⃣ Encoder", value=enc_, inline=True)
            embed.add_field(name="7⃣ Editor", value=ed_, inline=True)
            embed.add_field(name="8⃣ Timer", value=tm_, inline=True)
            embed.add_field(name="9⃣ Typesetter", value=ts_, inline=True)
            embed.add_field(name="0⃣ Quality Checker", value=qc_, inline=True)
            embed.add_field(
                name="Lain-Lain", value="🔐 Pengaturan\n✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = [
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
                "🔐",
                "✅",
                "❌",
            ]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_anilist(json_tables, emb_msg)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_episode(json_tables, emb_msg)
            elif to_react[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_role(json_tables, emb_msg)
            elif to_react[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tl")
            elif to_react[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tlc")
            elif to_react[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "enc")
            elif to_react[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ed")
            elif to_react[7] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tm")
            if to_react[8] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ts")
            elif to_react[9] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "qc")
            elif "🔐" in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_pengaturan(json_tables, emb_msg)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                self.logger.warn(f"{server_message}: process cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        # Everything are done and now processing data
        self.logger.info(f"{server_message}: commiting data to database...")
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        new_anime_data = {}
        staff_data = {}
        status = {}

        new_anime_data["anilist_id"] = json_tables["anilist_id"]
        new_anime_data["last_update"] = str(current_time)
        new_anime_data["role_id"] = json_tables["role_id"]
        new_anime_data["poster_data"] = json_tables["poster_data"]
        new_anime_data["start_time"] = json_tables["start_time"]

        staff_data["TL"] = json_tables["tlor_id"]
        staff_data["TLC"] = json_tables["tlcer_id"]
        staff_data["ENC"] = json_tables["encoder_id"]
        staff_data["ED"] = json_tables["editor_id"]
        staff_data["TM"] = json_tables["timer_id"]
        staff_data["TS"] = json_tables["tser_id"]
        staff_data["QC"] = json_tables["qcer_id"]
        new_anime_data["staff_assignment"] = staff_data

        self.logger.info(f"{server_message}: generating episode...")
        for x in range(int(json_tables["episodes"])):
            st_data = {}
            staff_status = {}

            staff_status["TL"] = "x"
            staff_status["TLC"] = "x"
            staff_status["ENC"] = "x"
            staff_status["ED"] = "x"
            staff_status["TM"] = "x"
            staff_status["TS"] = "x"
            staff_status["QC"] = "x"

            st_data["status"] = "not_released"
            st_data["airing_time"] = json_tables["time_data"][x]
            st_data["staff_status"] = staff_status
            status[str(x + 1)] = st_data

        new_anime_data["status"] = status

        srv_data["anime"][json_tables["ani_title"]] = new_anime_data

        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}: saving to local database...")
        await store_queue(SaveQueueData(srv_data, server_message, self.bot.fcwd))
        embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="**{}** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                json_tables["ani_title"]
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, srv_data)
        await emb_msg.delete()

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        self.logger.info(f"{server_message}: done processing!")
        await ctx.send(
            "Berhasil menambahkan **{}** ke dalam database utama naoTimes".format(  # noqa: E501
                json_tables["ani_title"]
            )
        )

ShowTimesCommands = [
    Showtimes,
    ShowtimesAdmin,
    ShowtimesAlias,
    ShowtimesKolaborasi,
    ShowtimesData,
]


def setup(bot: commands.Bot):
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            showlog.info(f"\tLoading {str(ShowTCLoad)} subcogs...")
            bot.add_cog(ShowTCLoad)
            showlog.info(f"\tLoaded {str(ShowTCLoad)} subcogs.")
        except Exception as ex:
            showlog.info(f"\tFailed to load {str(ShowTCLoad)} subcogs.")
            showlog.error(f"\tTraceback -> {ex}")

    asyncio.Task(background_save(), loop=bot.loop)
