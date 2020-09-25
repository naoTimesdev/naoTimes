import asyncio
import functools
import glob
import logging
import os
import random
import re
import string
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Union

import aiohttp
import discord
import feedparser
from discord.ext import commands, tasks
from markdownify import markdownify as mdparse

from nthelper.bot import naoTimesBot
from nthelper.utils import HelpGenerator, read_files, send_timed_msg, sync_wrap, write_files

asyncfeed = sync_wrap(feedparser.parse)


async def confirmation_dialog(bot: naoTimesBot, ctx, message: str) -> bool:
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


def clean_text(text_data: str) -> str:
    replace_data = {
        "â€™": "’",
    }
    for src, dest in replace_data.items():
        text_data = text_data.replace(src, dest)
    return text_data


def month_in_text(t: int) -> str:
    tdata = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]
    return tdata[t - 1]


def rgbhex_to_rgbint(hex_num: str) -> int:
    hex_num = hex_num.replace("#", "").upper()
    rr, gg, bb = int(hex_num[0:2], 16), int(hex_num[2:4], 16), int(hex_num[4:6], 16)
    return (256 * 256 * rr) + (256 * gg) + bb


def rgbint_to_rgbhex(int_num: int) -> str:
    r = int_num // 256 // 256
    int_num -= 256 * 256 * r
    g = int_num // 256
    b = int_num - (256 * g)
    return ("#" + hex(r)[2:] + hex(g)[2:] + hex(b)[2:]).upper()


def time_struct_dt(time_struct: time.struct_time) -> Tuple[str, datetime]:
    if not isinstance(time_struct, time.struct_time):
        return time_struct
    yymmdd_fmt = []
    mm_norm = None
    hh_norm = None
    hhmmss_fmt = []
    try:
        dd = time_struct.tm_mday
        yymmdd_fmt.append(str(dd).zfill(2))
    except AttributeError:
        pass
    try:
        mm = time_struct.tm_mon
        mm_norm = str(mm).zfill(2)
        yymmdd_fmt.append(month_in_text(mm))
    except AttributeError:
        pass
    try:
        yyyy = time_struct.tm_year
        yymmdd_fmt.append(str(yyyy))
    except AttributeError:
        pass

    try:
        hh = time_struct.tm_hour
        hh_norm = hh
        hhmmss_fmt.append(str(hh + 7).zfill(2))
    except AttributeError:
        pass
    try:
        mm = time_struct.tm_min
        hhmmss_fmt.append(str(mm).zfill(2))
    except AttributeError:
        pass
    try:
        ss = time_struct.tm_sec
        hhmmss_fmt.append(str(ss).zfill(2))
    except AttributeError:
        pass

    strftime_str = " ".join(yymmdd_fmt)
    strftime_str += " " + ":".join(hhmmss_fmt)

    dt_data = datetime.strptime(
        f"{yymmdd_fmt[2]}-{mm_norm}-{yymmdd_fmt[0]} {hh_norm}:{hhmmss_fmt[1]}:{hhmmss_fmt[2]} +0000",
        "%Y-%m-%d %H:%M:%S %z",
    )
    return strftime_str, dt_data


def filter_data(entries) -> dict:
    """Remove unnecessary tags that just gonna trashed the data"""
    remove_data = [
        "title_detail",
        "links",
        "authors",
        "author_detail",
        "content",
        "updated",
        "guidislink",
        "summary_detail",
        "comments",
        "href",
        "wfw_commentrss",
        "slash_comments",
    ]

    for r in remove_data:
        try:
            del entries[r]
        except KeyError:
            pass

    if "tags" in entries:
        try:
            tags = []
            for t in entries["tags"]:
                tags.append(t["term"])
            entries["tags"] = tags
        except KeyError:
            entries["tags"] = []

    if "media_thumbnail" in entries:
        try:
            entries["media_thumbnail"] = entries["media_thumbnail"][0]["url"]
        except IndexError:
            entries["media_thumbnail"] = ""
        except KeyError:
            entries["media_thumbnail"] = ""

    if "summary" in entries:
        entries["summary"] = clean_text(mdparse(entries["summary"]))

    if "description" in entries:
        entries["description"] = clean_text(mdparse(entries["description"]))
    if "media_content" in entries:
        media_url = entries["media_content"]
        if media_url:
            entries["media_content"] = media_url[0]["url"]
        else:
            del entries["media_content"]

    return entries


async def async_feedparse(url: str, **kwargs) -> Optional[feedparser.FeedParserDict]:
    aio_timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=aio_timeout) as session:
        try:
            async with session.get(url) as r:
                r_data = await r.text()
        except aiohttp.ClientTimeout:  # type: ignore
            return None
        except aiohttp.ClientError:
            return None
    return await asyncfeed(r_data, **kwargs)


async def check_if_valid(url: str) -> bool:
    feed = await async_feedparse(url)

    if feed is None:
        return False

    if not feed.entries:
        return False
    return True


async def parse_message(message, entry_data):
    matches = re.findall(r"(?P<data>{[^{}]+})", message, re.MULTILINE | re.IGNORECASE)
    msg_fmt_data = [m.strip(r"{}") for m in matches]

    for i in msg_fmt_data:
        try:
            message = message.replace("{" + i + "}", entry_data[i])
        except KeyError:
            pass

    return message.replace("\\n", "\n")


def replace_tz(string):
    for i in range(-12, 13):
        string = string.replace("+0{}:00".format(i), "")
    return string


async def parse_embed(embed_data, entry_data) -> discord.Embed:
    regex_embed = re.compile(r"(?P<data>{[^{}]+})", re.MULTILINE | re.IGNORECASE)

    filtered = {}
    for k, v in embed_data.items():
        if not v:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            filtered[k] = v
            continue
        matches = re.findall(regex_embed, v)
        msg_fmt = [m.strip(r"{}") for m in matches]
        for i in msg_fmt:
            try:
                if isinstance(entry_data[i], (tuple, list)):
                    stringed_list = [str(val) for val in entry_data[i]]
                    entry_data[i] = ", ".join(stringed_list)
                v = v.replace("{" + i + "}", entry_data[i])
            except KeyError:
                pass
        filtered[k] = v

    embed_beauty = discord.Embed()
    if "title" in filtered and filtered["title"] is not None:
        embed_beauty.title = filtered["title"]
    if "description" in filtered and filtered["description"] is not None:
        embed_beauty.description = filtered["description"]
    if "url" in filtered and filtered["url"] is not None:
        embed_beauty.url = filtered["url"]

    if "color" in filtered and filtered["color"] is not None:
        embed_beauty.colour = discord.Colour(value=filtered["color"])

    if "thumbnail" in filtered and filtered["thumbnail"] is not None:
        embed_beauty.set_thumbnail(url=filtered["thumbnail"])
    if "image" in filtered and filtered["image"] is not None:
        embed_beauty.set_image(url=filtered["image"])

    if embed_data["timestamp"]:
        try:
            _, dt_data = time_struct_dt(entry_data["published_parsed"])
        except Exception:
            dt_data = datetime.now(tz=timezone.utc)
        embed_beauty.timestamp = dt_data

    if "footer" in filtered and filtered["footer"] is not None:
        kwargs_footer = {"text": filtered["footer"]}
        if "footer_img" in filtered and filtered["footer_img"] is not None:
            kwargs_footer["icon_url"] = filtered["footer_img"]
        embed_beauty.set_footer(**kwargs_footer)

    return embed_beauty


async def recursive_check_feed(url, rss_data, fetched_data):
    last_etag = rss_data["lastEtag"]
    last_modified = rss_data["lastModified"]
    feed = await async_feedparse(url, etag=last_etag, modified=last_modified)
    if not feed:
        return None, "", ""

    entries = feed.entries

    filtered_entry = []
    for n, entry in enumerate(entries):
        if entry["link"] in fetched_data:
            continue
        filtered_entry.append(filter_data(entries[n]))

    etag = ""
    modified_tag = ""
    try:
        etag = feed.etag
    except AttributeError:
        pass
    try:
        modified_tag = feed.modified
    except AttributeError:
        pass

    return filtered_entry, etag, modified_tag


class FansubRSSDataHolder:
    def __init__(
        self, server_id: Union[str, int], rss_data: Union[list, dict], hash_id: Optional[str] = None
    ):
        self.srv_id = server_id
        self.rss_data = rss_data
        self.hash_id = hash_id


class FansubRSS(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.fansubrss.FansubRSS")

        self.splitbase = lambda path: os.path.splitext(os.path.basename(path))  # noqa: E731
        self.default_msg = r":newspaper: | Rilisan Baru: **{title}**\n{link}"

        self._locked_server: List[str] = []
        self._first_run = True

        self._server_normal: List[Union[str, int]] = []
        self._server_premium: List[Union[str, int]] = []

        self._precheck_server_type.start()
        self.servers_rss_checks.start()
        self.premium_rss_checks.start()

        self._bgqueue: asyncio.Queue = asyncio.Queue()
        self._bgtasks: asyncio.Task = asyncio.Task(self.background_rss_saver(), loop=bot.loop)

    def cog_unload(self):
        self.logger.info("Cancelling all tasks...")
        self.servers_rss_checks.cancel()
        self.premium_rss_checks.cancel()
        self._bgtasks.cancel()

    def is_msg_empty(self, msg: str, thr: int = 3) -> bool:
        split_msg: List[str] = msg.split(" ")
        split_msg = [m for m in split_msg if m != ""]
        if len(split_msg) < thr:
            return True
        return False

    def generate_random(self, srv_id: Union[str, int]):
        srv_hash = str(srv_id)[5:]
        strings_best = string.ascii_lowercase + string.digits
        gen_id = "".join([random.choice(strings_best) for _ in range(10)]) + srv_hash
        return gen_id

    async def read_rss(self, server_id: Union[str, int]) -> dict:
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", f"{server_id}.fsrss")
        if not os.path.isfile(full_path):
            return {}
        rss_metadata = await read_files(full_path)
        return rss_metadata

    async def read_rss_feeds(self, server_id: Union[str, int], hash_ids: str) -> dict:
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", f"{server_id}_data")
        if not os.path.isdir(full_path):
            os.makedirs(full_path)
        full_path = os.path.join(full_path, f"{hash_ids}.fsdata")
        if not os.path.isfile(full_path):
            return {"fetchedURL": []}
        rss_metadata = await read_files(full_path)
        return rss_metadata

    async def write_rss(self, server_id: Union[str, int], data: dict):
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", f"{server_id}.fsrss")
        await write_files(data, full_path)

    async def write_rss_feeds(self, server_id: Union[str, int], hash_ids: str, feeds_data: list):
        save_data = {"fetchedURL": feeds_data}
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", f"{server_id}_data")
        if not os.path.isdir(full_path):
            os.makedirs(full_path)
        full_path = os.path.join(full_path, f"{hash_ids}.fsdata")
        await write_files(save_data, full_path)

    async def server_rss(self) -> list:
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", "*.fsrss")
        all_rss = [self.splitbase(path)[0] for path in glob.glob(full_path)]
        return all_rss

    @tasks.loop(seconds=1, count=1)
    async def _precheck_server_type(self):
        fetch_all_servers = await self.server_rss()
        self.logger.info("Prechecking server type...")
        for srv in fetch_all_servers:
            rss_meta = await self.read_rss(srv)
            if "premium" in rss_meta and rss_meta["premium"]:
                self.logger.info(f"Appending `{srv}` server to premium treatmeant.")
                self._server_premium.append(srv)
            else:
                self.logger.info(f"Appending `{srv}` server to normal treatmeant.")
                self._server_normal.append(srv)
        self._first_run = False

    def check_if_author(self, message, original_author, channel_id):
        self.logger.info(f"Checking if {original_author} is the same as {message.author.id}")
        return message.author.id == original_author and message.channel.id == channel_id

    def base_check_react(self, reaction, user, ctx, message, emotes_set):
        if reaction.message.id != message.id:
            return False
        if user != ctx.message.author:
            return False
        if str(reaction.emoji) not in emotes_set:
            return False
        return True

    async def choose_rss(self, ctx, full_rss_metadata: dict) -> int:
        total_data = len(full_rss_metadata["feeds"])
        if total_data > 1:
            check_if_author = functools.partial(
                self.check_if_author, original_author=ctx.message.author.id, channel_id=ctx.message.channel.id
            )
            embed = discord.Embed(title="Format RSS", description="Pilih RSS sebelum melanjutkan.")
            for i in range(total_data):
                channel_id = full_rss_metadata["feeds"][i]["channel"]
                feeds_url = full_rss_metadata["feeds"][i]["feedUrl"]
                embed.add_field(
                    name=f"Feeds no. {i + 1}",
                    value=f"Channel: <#{channel_id}>\nFeeds: {feeds_url}",
                    inline=False,
                )
            emb_ask = await ctx.send(embed=embed)
            ask_msg_norm = await ctx.send(
                "Ketik angka untuk memilih RSS yang ingin diformat.\nKetik `cancel` untuk membatalkan."
            )
            cancel_asking_first = False
            selected_rss = -1
            while True:
                pick_answer = await self.bot.wait_for("message", check=check_if_author)
                answer_num = pick_answer.content
                await pick_answer.delete()
                if answer_num == ("cancel"):
                    cancel_asking_first = True
                    break
                else:
                    if answer_num.isdigit():
                        selected_rss = int(answer_num)
                        if selected_rss in list(range(1, total_data + 1)):
                            break
                        else:
                            await send_timed_msg(ctx, f"Angka diluar range 1 sampai {total_data}", 2)
                    else:
                        await send_timed_msg(ctx, "Jawaban bukanlah angka.", 2)
            selected_rss -= 1
            await ask_msg_norm.delete()
            await emb_ask.delete()
            if cancel_asking_first:
                selected_rss = -1
        else:
            selected_rss = 0
        return selected_rss

    async def background_rss_saver(self):
        self.logger.info("Starting FansubRSS_SaveQueue Task...")
        while True:
            try:
                fsh_data: FansubRSSDataHolder = await self._bgqueue.get()
                if fsh_data.hash_id is not None:
                    self.logger.info(f"Job feeds get, saving: {fsh_data.srv_id}")
                    await self.write_rss_feeds(fsh_data.srv_id, fsh_data.hash_id, fsh_data.rss_data)
                else:
                    self.logger.info(f"Job metadata get, saving: {fsh_data.srv_id}")
                    await self.write_rss(fsh_data.srv_id, fsh_data.rss_data)
                self._bgqueue.task_done()
            except asyncio.CancelledError:
                return

    async def put_rss_job(self, srv_id, metadata):
        await self._bgqueue.put(FansubRSSDataHolder(srv_id, metadata))

    async def put_rss_feeds_job(self, srv_id, hash_id, feeds_data):
        await self._bgqueue.put(FansubRSSDataHolder(srv_id, feeds_data, hash_id))

    async def internal_rss_check(self, server_list):
        # Skip locked channel because it's useless.
        async def _internal_request(srv_id):
            rss_metadata = await self.read_rss(srv_id)
            return rss_metadata, srv_id

        jobs_list = [_internal_request(srv) for srv in server_list if srv not in self._locked_server]
        for job in asyncio.as_completed(jobs_list):
            full_metadata, server_id = await job
            metadatas_to_fetch = []
            if not full_metadata["premium"]:
                metadatas_to_fetch.append(full_metadata["feeds"][0])
            else:
                metadatas_to_fetch.extend(full_metadata["feeds"])
            for metadata in metadatas_to_fetch:
                fetched_feeds = await self.read_rss_feeds(server_id, metadata["id"])
                feed_res, etag, modified = await recursive_check_feed(
                    metadata["feedUrl"], metadata, fetched_feeds["fetchedURL"]
                )
                if feed_res:
                    self.logger.info(f"Updating Feed: {metadata['feedUrl']}")
                    channel = self.bot.get_channel(metadata["channel"])
                    if not channel:
                        self.logger.warning(
                            f"RSS Feed `{metadata['feedUrl']}` have an invalid channel: {metadata['channel']}"
                        )
                        continue
                    self.logger.info(f"Sending result to: #{channel.name}")
                    for entry in feed_res[::-1]:
                        fetched_feeds["fetchedURL"].append(entry["link"])
                    await self.put_rss_feeds_job(server_id, metadata["id"], fetched_feeds["fetchedURL"])
                    for entry in feed_res[::-1]:
                        if metadata["embed"]:
                            embed_data = await parse_embed(metadata["embed"], entry)
                            kwargs_to_send = {"embed": embed_data}
                            if metadata["message"] is not None and metadata["message"] != "":
                                message_data = await parse_message(metadata["message"], entry)
                                kwargs_to_send["content"] = message_data
                            await channel.send(**kwargs_to_send)
                        else:
                            if metadata["message"] is None:
                                self.logger.warning(
                                    f"For some reason, RSS feed `{metadata['feedUrl']}` doesn't have message "
                                    "or embed formatting."
                                )
                                continue
                            message_data = await parse_message(metadata["message"], entry)
                            await channel.send(message_data)
                elif feed_res is None:
                    self.logger.error(
                        "Failed to fetch RSS Feed, possiblity include timeout and parsing error."
                    )
                else:
                    self.logger.info("No RSS entries to parse.")

    @tasks.loop(minutes=5.0)
    async def servers_rss_checks(self):
        """
        The actual process that will check all RSS feeds.
        """
        if self._first_run:
            return
        self.logger.info("[Normal] Running background RSS Checks")
        await self.internal_rss_check(self._server_normal)
        self.logger.info("[Normal] Sleeping...")

    @tasks.loop(minutes=2.0)
    async def premium_rss_checks(self):
        """
        The actual process that will check all RSS feeds.

        Premium version, :D
        """
        if self._first_run:
            return
        self.logger.info("[Premium] Running background RSS Checks")
        await self.internal_rss_check(self._server_premium)
        self.logger.info("[Premium] Sleeping...")

    @commands.group(aliases=["rss"])
    @commands.has_guild_permissions(manage_guild=True)
    async def fansubrss(self, ctx):
        msg = ctx.message.content
        if ctx.invoked_subcommand is None:
            if not self.is_msg_empty(msg, 2):
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            helpcmd = HelpGenerator(self.bot, "fansubrss", desc="Pemantau RSS Fansub.")
            await helpcmd.generate_field(
                "fansubrss", desc="Memunculkan bantuan perintah ini.",
            )
            await helpcmd.generate_field(
                "fansubrss aktifkan", desc="Mengaktifkan RSS announcer di channel tertentu.",
            )
            await helpcmd.generate_field(
                "fansubrss ubah", desc="Mengatur settingan RSS di server ini.",
            )
            await helpcmd.generate_field("fansubrss format", desc="Format bagaimana RSS akan dikirim.")
            await helpcmd.generate_field(
                "fansubrss terakhir",
                desc="Mengambil RSS terakhir dan mengirimnya ke channel di mana perintah itu dipakai.",
            )
            await helpcmd.generate_field("fansubrss format", desc="Format bagaimana RSS akan dikirim.")
            await helpcmd.generate_aliases(["rss"])
            await ctx.send(embed=helpcmd.get())

    @fansubrss.command(name="aktifkan", aliases=["activate"])
    async def fansubrss_aktifkan(self, ctx, *, channel_id: int = 0):
        if channel_id == 0:
            channel_id = ctx.message.channel.id
        server_id = str(ctx.message.guild.id)
        self.logger.info(f"{server_id}: mengaktivasi fansubrss")

        saved_rss = await self.server_rss()
        if server_id in saved_rss:
            self.logger.warning(f"{server_id}: fansubrss sudah diaktifkan di server ini.")
            return await ctx.send(
                "FansubRSS sudah diaktifkan di server ini, silakan gunakan !fansubrss ubah untuk mengaturnya."
            )

        check_if_author = functools.partial(
            self.check_if_author, original_author=ctx.message.author.id, channel_id=ctx.message.channel.id
        )

        self.logger.info(f"{server_id}: waiting for URL input.")
        msg = await ctx.send("Mohon ketik/paste URL rss.\nKetik `cancel` untuk membatalkan.")
        await_msg = await self.bot.wait_for("message", check=check_if_author)
        if await_msg.content == ("cancel"):
            self.logger.warning(f"{server_id}: process cancelled.")
            return await ctx.send("Dibatalkan.")
        rss_url = await_msg.content
        if not (await check_if_valid(rss_url)):
            return await ctx.send("URL yang diberikan bukanlah link RSS yang valid.")

        feeds_parsed = await async_feedparse(rss_url)

        self.logger.info(f"{server_id}: waiting for confirmation.")
        res = await confirmation_dialog(self.bot, ctx, f"Apakah yakin ingin menggunakan link: <{rss_url}>?")
        if not res:
            self.logger.warning(f"{server_id}: process cancelled.")
            return await ctx.send("Dibatalkan.")

        await msg.delete()
        await await_msg.delete()
        await ctx.send("Mengaktifkan RSS...")

        skip_fetch_url = []
        for entry in feeds_parsed.entries:  # type: ignore
            try:
                skip_fetch_url.append(entry["link"])
            except KeyError:
                try:
                    skip_fetch_url.append(entry["url"])
                except KeyError:
                    pass

        gen_hash = self.generate_random(server_id)

        self.logger.info(f"{server_id}: activating FansubRSS...")
        json_tables = {
            "feeds": [
                {
                    "id": gen_hash,
                    "channel": channel_id,
                    "feedUrl": rss_url,
                    "message": self.default_msg,
                    "lastEtag": "",
                    "lastModified": "",
                    "embed": {},
                }
            ],
            "premium": False,
        }

        await self.write_rss(server_id, json_tables)
        await self.write_rss_feeds(server_id, gen_hash, skip_fetch_url)
        self.logger.info(f"{server_id}: FansubRSS activated.")
        await ctx.send("FansubRSS berhasil diaktifkan, silakan atur formatting dengan !fansubrss format")

    @fansubrss.command(name="tambah", aliases=["add"])
    async def fansubrss_tambah(self, ctx, *, channel_id: int = 0):
        server_id = str(ctx.message.guild.id)
        if channel_id == 0:
            channel_id = ctx.message.channel.id
        self._locked_server.append(server_id)
        check_if_author = functools.partial(
            self.check_if_author, original_author=ctx.message.author.id, channel_id=ctx.message.channel.id
        )
        full_rss_metadata = await self.read_rss(server_id)
        self.logger.info(f"fetching {server_id} metadata...")
        if not full_rss_metadata:
            self.logger.error(f"{server_id}: cannot find metadata...")
            return await ctx.send("FansubRSS belum diaktifkan.")

        if not full_rss_metadata["premium"]:
            self.logger.error(f"{server_id}: not premium user...")
            return await ctx.send(
                "Server ini tidak mendapatkan fitur premium, silakan refer ke: `!fansubrss premium`."
            )

        total_data = len(full_rss_metadata["feeds"])
        if total_data >= 3:
            self.logger.error(f"{server_id}: maximum limit reached...")
            return await ctx.send("Telah mencapai limit maksimal RSS untuk user premium.")

        self.logger.info(f"{server_id}: waiting for URL input.")
        msg = await ctx.send("Mohon ketik/paste URL rss.\nKetik `cancel` untuk membatalkan.")
        await_msg = await self.bot.wait_for("message", check=check_if_author)
        if await_msg.content == ("cancel"):
            self.logger.warning(f"{server_id}: process cancelled.")
            return await ctx.send("Dibatalkan.")
        rss_url = await_msg.content
        if not (await check_if_valid(rss_url)):
            return await ctx.send("URL yang diberikan bukanlah link RSS yang valid.")

        feeds_parsed = await async_feedparse(rss_url)

        self.logger.info(f"{server_id}: waiting for confirmation.")
        res = await confirmation_dialog(self.bot, ctx, f"Apakah yakin ingin menggunakan link: <{rss_url}>?")
        if not res:
            self.logger.warning(f"{server_id}: process cancelled.")
            return await ctx.send("Dibatalkan.")

        await msg.delete()
        await await_msg.delete()
        await ctx.send("Menambahkan RSS...")

        skip_fetch_url = []
        for entry in feeds_parsed.entries:  # type: ignore
            try:
                skip_fetch_url.append(entry["link"])
            except KeyError:
                try:
                    skip_fetch_url.append(entry["url"])
                except KeyError:
                    pass

        self.logger.info(f"{server_id}: adding feed {rss_url}...")
        gen_hash = self.generate_random(server_id)
        json_addition = {
            "id": gen_hash,
            "channel": channel_id,
            "feedUrl": rss_url,
            "message": self.default_msg,
            "lastEtag": "",
            "lastModified": "",
            "embed": {},
        }
        full_rss_metadata["feeds"].append(json_addition)

        await self.write_rss(server_id, full_rss_metadata)
        await self.write_rss_feeds(server_id, gen_hash, skip_fetch_url)
        self.logger.info(f"{server_id}: added feed {rss_url}.")
        await ctx.send("FansubRSS berhasil diaktifkan, silakan atur formatting dengan !fansubrss format")

    @fansubrss.command(name="format")
    async def fansubrss_format(self, ctx):
        server_id = str(ctx.message.guild.id)
        self._locked_server.append(server_id)
        check_if_author = functools.partial(
            self.check_if_author, original_author=ctx.message.author.id, channel_id=ctx.message.channel.id
        )
        full_rss_metadata = await self.read_rss(server_id)
        self.logger.info(f"fetching {server_id} metadata...")
        if not full_rss_metadata:
            self.logger.error(f"{server_id}: cannot find metadata...")
            return await ctx.send("FansubRSS belum diaktifkan.")

        selected_rss = await self.choose_rss(ctx, full_rss_metadata)
        if selected_rss == -1:
            return await ctx.send("Dibatalkan.")
        rss_metadata = full_rss_metadata["feeds"][selected_rss]

        self.logger.info(f"{server_id}: fetching latest rss data for sample...")
        feed_data = await async_feedparse(rss_metadata["feedUrl"])
        if not feed_data:
            self.logger.error(f"{server_id}: failed to fetch data sample, cancelling...")
            return await ctx.send("Tidak dapat membuat koneksi dengan RSS feed, membatalkan...")
        entries_data = feed_data.entries
        sample_entry = filter_data(entries_data[0])

        async def generate_sample_data(entry_data: dict):
            embed = discord.Embed(
                title="Contoh data",
                description=r"Ketik `{nama_data}` untuk memakai data dari RSS, misalkan "
                "ingin memakai judul dari RSS.\n"
                r"Maka pakai `{title}`",
            )
            for nama_data, isi_data in entry_data.items():
                if isinstance(isi_data, time.struct_time):
                    isi_data, _ = time_struct_dt(isi_data)
                elif isinstance(isi_data, (list, tuple)):
                    isi_data = [str(val) for val in isi_data]
                    isi_data = ", ".join(isi_data)
                if not isinstance(isi_data, str):
                    isi_data = str(isi_data)
                embed.add_field(name="`{" + str(nama_data) + "}`", value=isi_data)
            return embed

        async def generate_internal_embed(internal_data: dict):
            embed = discord.Embed(
                title="Format Data Embed", description=r"Ketik `nama_data` untuk mengubah isinya."
            )
            if internal_data["color"] is not None:
                embed.colour = discord.Colour(internal_data["color"])
            for key, value in internal_data.items():
                if key == "timestamp":
                    embed.add_field(
                        name="`timestamp`", value="Aktif" if value else "Tidak aktif", inline=False
                    )
                elif key == "color":
                    embed.add_field(
                        name="`color`",
                        value=f"`{rgbint_to_rgbhex(internal_data['color'])}`"
                        if internal_data["color"] is not None
                        else "Kosong.",
                        inline=False,
                    )
                else:
                    if isinstance(value, (list, tuple)):
                        value = [str(val) for val in value]
                        value = ", ".join(value)
                    embed.add_field(
                        name=f"`{key}`", value=f"`{value}`" if value is not None else "Kosong.", inline=False
                    )
            return embed

        number_reactions = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
            "8️⃣",
            "9️⃣",
            "0️⃣",
        ]
        valid_embed = [
            "title",
            "description",
            "url",
            "color",
            "thumbnail",
            "image",
            "footer",
            "footer_img",
        ]

        first_run = True
        cancelled = False
        emb_msg: discord.Message
        self.logger.info(f"{server_id}: starting data modifying...")
        while True:
            embed = discord.Embed(title="FansubRSS")
            embed.description = f"<#{rss_metadata['channel']}>: {rss_metadata['feedUrl']}"
            embed.add_field(name="1️⃣ Atur Pesan", value=f"`{rss_metadata['message']}`", inline=False)
            embed.add_field(
                name="2️⃣ Atur Embed",
                value="Embed aktif?: {}".format("Ya" if rss_metadata["embed"] else "Tidak"),
                inline=False,
            )
            embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=True)
            embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                first_run = False
                emb_msg = await ctx.send(embed=embed)
            else:
                await emb_msg.edit(embed=embed)

            react_first_part = number_reactions[0:2]
            react_first_part.extend(["✅", "❌"])

            first_check = functools.partial(
                self.base_check_react, ctx=ctx, message=emb_msg, emotes_set=react_first_part
            )

            for react in react_first_part:
                await emb_msg.add_reaction(react)

            res, user = await self.bot.wait_for("reaction_add", check=first_check)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                cancelled = True
                break
            elif react_first_part[0] in str(res.emoji):
                self.logger.info(f"{server_id}: changing message data...")
                await emb_msg.clear_reactions()
                smpl_embed = await generate_sample_data(sample_entry)
                await emb_msg.edit(embed=smpl_embed)
                extra_msg = await ctx.send(
                    "Ketik pesan yang diinginkan!\n"
                    "Ketik `cancel` untuk membatalkannya proses ini\n"
                    "Ketik `clear` untuk menghapus pesan yang ada\n"
                    "Ketik `reset` untuk menormalkannya kembali"
                )
                format_msg_wait = await self.bot.wait_for("message", check=check_if_author)
                format_msg_cntn = format_msg_wait.content
                if format_msg_cntn == ("cancel"):
                    pass
                elif format_msg_cntn == ("clear"):
                    rss_metadata["message"] = None
                elif format_msg_cntn == ("reset"):
                    rss_metadata["message"] = self.default_msg
                else:
                    rss_metadata["message"] = format_msg_cntn
                    await send_timed_msg(ctx, f"Pesan berhasil diubah ke: `{rss_metadata['message']}`", 2)
                await extra_msg.delete()
                await format_msg_wait.delete()
            elif react_first_part[1] in str(res.emoji):
                self.logger.info(f"{server_id}: changing embed data...")
                await emb_msg.clear_reactions()
                new_embed_data = {
                    "title": None,
                    "description": None,
                    "url": None,
                    "thumbnail": None,
                    "image": None,
                    "footer": None,
                    "footer_img": None,
                    "color": None,
                    "timestamp": False,
                }
                if rss_metadata["embed"]:
                    for ek, ev in rss_metadata["embed"].items():
                        new_embed_data[ek] = ev
                cur_emb_data = await generate_internal_embed(new_embed_data)
                smpl_embed = await generate_sample_data(sample_entry)
                await emb_msg.edit(embed=smpl_embed)
                cur_emb_msg = await ctx.send(embed=cur_emb_data)
                extra_msg_embed = await ctx.send(
                    "Ketik `nama_data` untuk mengubahnya (misal `title`)!\n"
                    "ketik `cancel` untuk membatalkannya proses ini\n"
                    "Ketik `clear` untuk menghapus embed yang ada\n"
                    "Ketik `done` jika sudah selesai."
                )
                cancelled_embed = False
                first_embed_change_run = True
                while True:
                    if first_embed_change_run:
                        first_embed_change_run = False
                    else:
                        cur_emb_data = await generate_internal_embed(new_embed_data)
                        await cur_emb_msg.edit(embed=cur_emb_data)
                    embed_input = await self.bot.wait_for("message", check=check_if_author)
                    embed_input_txt = embed_input.content
                    if embed_input_txt == ("cancel"):
                        cancelled_embed = True
                        await embed_input.delete()
                        break
                    elif embed_input_txt == ("reset"):
                        new_embed_data = {}
                        await embed_input.delete()
                        break
                    elif embed_input_txt == ("done"):
                        await embed_input.delete()
                        break
                    else:
                        if embed_input_txt in valid_embed:
                            self.logger.info(f"embed: changing {embed_input_txt}")
                            extra_clr_txt = (
                                "\n Masukan warna hex (format: #aabbcc), contohnya: `#87D3F8`"  # noqa: E501
                                if "color" in embed_input_txt
                                else ""
                            )
                            msg_changed = await ctx.send(
                                f"Mengubah: `{embed_input_txt}`{extra_clr_txt}\n"
                                "Ketik `cancel` untuk membatalkannya\n"
                                "Ketik `clear` untuk menghapus isi bagian ini."
                            )
                            embed_change_input = await self.bot.wait_for("message", check=check_if_author)
                            embed_change_input_txt = embed_change_input.content
                            if embed_change_input_txt == ("cancel"):
                                pass
                            elif embed_change_input_txt == ("clear"):
                                new_embed_data[embed_input_txt.strip()] = None
                                await msg_changed.delete()
                                await embed_change_input.delete()
                                await send_timed_msg(ctx, f"Berhasil menghapus data `{embed_input_txt}`", 2)
                            elif embed_input_txt == ("color"):
                                await msg_changed.delete()
                                await embed_change_input.delete()
                                try:
                                    color_parsed = rgbhex_to_rgbint(embed_change_input_txt)
                                    new_embed_data[embed_input_txt.strip()] = color_parsed
                                    await send_timed_msg(
                                        ctx, f"Berhasil mengubah warna ke: `{color_parsed}`.", 2
                                    )
                                except Exception:
                                    await send_timed_msg(ctx, "Bukan warna HEX yang valid.", 2)
                            else:
                                new_embed_data[embed_input_txt.strip()] = embed_change_input_txt
                                await msg_changed.delete()
                                await embed_change_input.delete()
                                await send_timed_msg(ctx, f"Berhasil mengubah data `{embed_input_txt}`", 2)
                        elif "timestamp" in embed_input_txt:
                            if not new_embed_data["timestamp"]:
                                new_embed_data["timestamp"] = True
                                await send_timed_msg(ctx, "Mengaktifkan timestamp...", 2)
                            else:
                                new_embed_data["timestamp"] = False
                                await send_timed_msg(ctx, "Menonaktifkan timestamp...", 2)
                        else:
                            await send_timed_msg(ctx, "Tipe data tidak diketahui.", 2)
                    await embed_input.delete()

                if not cancelled_embed:
                    rss_metadata["embed"] = new_embed_data

                await cur_emb_msg.delete()
                await extra_msg_embed.delete()
                if not cancelled_embed:
                    await send_timed_msg(ctx, "Berhasil mengubah data embed.", 2)

        if cancelled:
            self._locked_server.remove(server_id)
            self.logger.warning(f"{server_id}: commiting data is cancelled...")
            return await ctx.send("Dibatalkan.")

        self.logger.info(f"{server_id}: commiting data...")
        await emb_msg.delete()
        full_rss_metadata["feeds"][selected_rss] = rss_metadata
        msg_final = await ctx.send("Menyimpan data terbaru...")
        await self.write_rss(server_id, full_rss_metadata)
        self._locked_server.remove(server_id)
        await msg_final.edit(content="Formatting baru telah disimpan.")

    @fansubrss.command(name="terakhir", aliases=["latest", "terbaru"])
    async def fansubrss_terakhir(self, ctx):
        server_id = str(ctx.message.guild.id)
        full_rss_metadata = await self.read_rss(server_id)
        self.logger.info(f"fetching {server_id} metadata...")
        if not full_rss_metadata:
            self.logger.error(f"{server_id}: cannot find metadata...")
            return await ctx.send("FansubRSS belum diaktifkan.")

        selected_rss = await self.choose_rss(ctx, full_rss_metadata)
        if selected_rss == -1:
            return await ctx.send("Dibatalkan.")
        rss_metadata = full_rss_metadata["feeds"][selected_rss]

        msg_to_change = await ctx.send("Mengirimkan RSS terbaru...")
        self.logger.info(f"{server_id}: fetching latest rss data for sample...")
        feed_data = await async_feedparse(rss_metadata["feedUrl"])
        if not feed_data:
            self.logger.error(f"{server_id}: failed to fetch data sample, cancelling...")
            return await ctx.send("Tidak dapat membuat koneksi dengan RSS feed, membatalkan...")
        entries_data = feed_data.entries
        sample_entry = filter_data(entries_data[0])

        msg_rss = rss_metadata["message"]
        if msg_rss is None:
            msg_rss = ""

        if rss_metadata["embed"]:
            embed_data: discord.Embed = await parse_embed(rss_metadata["embed"], sample_entry)
            if msg_rss != "":
                msg_rss = await parse_message(msg_rss, sample_entry)
            await msg_to_change.edit(content=msg_rss, embed=embed_data)
        else:
            if msg_rss == "":
                msg_rss = "TIDAK ADA FORMAT PESAN YANG DIPILIH."
            else:
                msg_rss = await parse_message(msg_rss, sample_entry)
            await msg_to_change.edit(content=msg_rss)

    @fansubrss.command(name="hapus", aliases=["remove"])
    async def fansubrss_hapus(self, ctx):
        server_id = str(ctx.message.guild.id)
        full_rss_metadata = await self.read_rss(server_id)
        self.logger.info(f"fetching {server_id} metadata...")
        if not full_rss_metadata:
            self.logger.error(f"{server_id}: cannot find metadata...")
            return await ctx.send("FansubRSS belum diaktifkan.")

        total_data = len(full_rss_metadata["feeds"])
        if total_data < 2:
            return await ctx.send(
                "Tidak dapat menghapus salah satu RSS, dikarenakan hanya ada 1\n"
                f"Silakan gunakan, `{self.bot.prefix}fansubrss deaktivasi`"
            )

        selected_rss = await self.choose_rss(ctx, full_rss_metadata)
        if selected_rss == -1:
            return await ctx.send("Dibatalkan.")

        # Remove RSS.
        rss_data = full_rss_metadata["feeds"].pop(selected_rss)
        self.logger.info(f"Removing RSS: {rss_data['feedUrl']}")

        feeds_data_path = os.path.join(
            self.bot.fcwd, "fansubrss_data", f"{server_id}_data", f"{rss_data['id']}.fsdata"
        )
        os.remove(feeds_data_path)
        await self.put_rss_job(server_id, full_rss_metadata)
        await ctx.send(f"Berhasil menghapus RSS: <{rss_data['feedUrl']}>")

    @fansubrss.command(name="atur", aliases=["configure", "edit", "ubah"])
    async def fansubrss_atur(self, ctx):
        server_id = str(ctx.message.guild.id)
        self._locked_server.append(server_id)
        check_if_author = functools.partial(
            self.check_if_author, original_author=ctx.message.author.id, channel_id=ctx.message.channel.id
        )
        full_rss_metadata = await self.read_rss(server_id)
        self.logger.info(f"fetching {server_id} metadata...")
        if not full_rss_metadata:
            self.logger.error(f"{server_id}: cannot find metadata...")
            return await ctx.send("FansubRSS belum diaktifkan.")

        self.logger.info(f"{server_id}: waiting for user pick.")
        selected_rss = await self.choose_rss(ctx, full_rss_metadata)
        if selected_rss == -1:
            self.logger.info(f"{server_id}: cancelled process.")
            return await ctx.send("Dibatalkan.")
        self.logger.info(f"{server_id}: user pick no. {selected_rss + 1}")
        rss_metadata = full_rss_metadata["feeds"][selected_rss]

        number_reactions = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
            "8️⃣",
            "9️⃣",
            "0️⃣",
        ]

        first_run = True
        cancelled = False
        emb_msg: discord.Message
        self.logger.info(f"{server_id}: starting data modifying...")
        while True:
            embed = discord.Embed(title="FansubRSS")
            embed.add_field(name="1️⃣ Atur URL", value=f"`{rss_metadata['feedUrl']}`", inline=False)
            embed.add_field(
                name="2️⃣ Atur Channel", value=f"Sekarang: <#{rss_metadata['channel']}>", inline=False,
            )
            embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=True)
            embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                first_run = False
                emb_msg = await ctx.send(embed=embed)
            else:
                await emb_msg.edit(embed=embed)

            react_first_part = number_reactions[0:2]
            react_first_part.extend(["✅", "❌"])

            first_check = functools.partial(
                self.base_check_react, ctx=ctx, message=emb_msg, emotes_set=react_first_part
            )

            for react in react_first_part:
                await emb_msg.add_reaction(react)

            res, user = await self.bot.wait_for("reaction_add", check=first_check)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                cancelled = True
                break
            elif react_first_part[0] in str(res.emoji):
                self.logger.info(f"{server_id}: changing rss url...")
                await emb_msg.clear_reactions()
                extra_msg = await ctx.send(
                    "Ketik url RSS baru yang diinginkan!\nKetik `cancel` untuk membatalkannya proses ini"
                )
                rss_feed_wait = await self.bot.wait_for("message", check=check_if_author)
                rss_feed_new_url = rss_feed_wait.content
                if rss_feed_new_url == ("cancel"):
                    pass
                else:
                    if not (await check_if_valid(rss_feed_new_url)):
                        await send_timed_msg(ctx, "URL yang diberikan tidak valid.", 2)
                    else:
                        rss_metadata["feedUrl"] = rss_feed_new_url
                        await send_timed_msg(ctx, f"RSS Feed berhasil diubah ke: <{rss_feed_new_url}>", 2)
                await extra_msg.delete()
                await rss_feed_wait.delete()
            elif react_first_part[1] in str(res.emoji):
                self.logger.info(f"{server_id}: changing channel target...")
                await emb_msg.clear_reactions()
                extra_msg = await ctx.send(
                    "Ketik ID Channel baru yang diinginkan, atau mention channelnya.\n"
                    "Ketik `cancel` untuk membatalkannya proses ini"
                )
                channel_feed_wait = await self.bot.wait_for("message", check=check_if_author)
                # channel_mentions
                channel_text_data = channel_feed_wait.content
                channel_mentions_data = channel_feed_wait.channel_mentions
                if channel_text_data == ("cancel"):
                    pass
                else:
                    if channel_mentions_data:
                        new_channel_id = channel_mentions_data[0].id
                        rss_metadata["channel"] = new_channel_id
                        await send_timed_msg(ctx, f"Channel berhasil diubah ke: <#{new_channel_id}>", 2)
                    elif channel_text_data.isdigit():
                        new_channel_id = int(channel_text_data)
                        if self.bot.get_channel(new_channel_id) is not None:
                            rss_metadata["channel"] = new_channel_id
                            await send_timed_msg(ctx, f"Channel berhasil diubah ke: <#{new_channel_id}>", 2)
                        else:
                            await send_timed_msg(ctx, "Tidak dapat menemukan channel tersebut.", 2)
                    else:
                        await send_timed_msg(ctx, "Channel yang diberikan tidak valid.", 2)
                await extra_msg.delete()
                await channel_feed_wait.delete()

        if cancelled:
            self._locked_server.remove(server_id)
            self.logger.warning(f"{server_id}: commiting data is cancelled...")
            return await ctx.send("Dibatalkan.")

        self.logger.info(f"{server_id}: commiting data...")
        await emb_msg.delete()
        full_rss_metadata["feeds"][selected_rss] = rss_metadata
        msg_final = await ctx.send("Menyimpan data terbaru...")
        await self.write_rss(server_id, full_rss_metadata)
        self._locked_server.remove(server_id)
        await msg_final.edit(content="Formatting baru telah disimpan.")

    @fansubrss.command(name="premium")
    async def fansubrss_premium(self, ctx, *, server_id=""):
        if not (await self.bot.is_owner(ctx.author)):
            return await ctx.send(
                "Fitur premium hanya tersedia bagi yang donasi bulanan via Trakteer\n"
                "<https://trakteer.id/noaione> [2x Cendol]"
            )

        self.logger.info(f"fetching {server_id} metadata...")
        rss_metadata = await self.read_rss(server_id)
        if not rss_metadata:
            self.logger.error(f"{server_id}: cannot find metadata...")
            return await ctx.send("FansubRSS belum diaktifkan.")

        if not rss_metadata["premium"]:
            self.logger.info(f"{server_id}: enabling premium feature for this server...")
            rss_metadata["premium"] = True
            try:
                self._server_normal.remove(server_id)
            except ValueError:
                pass
            self._server_premium.append(server_id)
            msg_to_send = f"💳 | Fitur premium server `{server_id}` telah diaktifkan!"
        else:
            self.logger.info(f"{server_id}: disabling premium feature for this server...")
            rss_metadata["premium"] = False
            try:
                self._server_premium.remove(server_id)
            except ValueError:
                pass
            self._server_normal.append(server_id)
            msg_to_send = f"🕸️ | Fitur premium server `{server_id}` telah dinonaktifkan!"
        await self.write_rss(server_id, rss_metadata)
        await ctx.send(msg_to_send)


def setup(bot):
    bot.add_cog(FansubRSS(bot))
