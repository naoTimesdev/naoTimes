"""
A simple RSS fetcher and poster, mostly copying how DiscordRSS work.
The thing is I don't even know how that bot work so I'm basically recreating it.

---

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

import asyncio
import logging
import re
import time
from datetime import timedelta
from typing import List, Optional, Union
from urllib.parse import urlparse

import aiohttp
import discord
import feedparser
import schema as sc
from discord.ext import commands, tasks
from markdownify import markdownify as mdparse

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.helpgenerator import HelpField
from naotimes.showtimes import FansubRSS, FansubRSSEmbed, FansubRSSFeed
from naotimes.timeparse import TimeString
from naotimes.utils import generate_custom_code, hex_to_color, quote, sync_wrap, time_struct_dt

asyncfeed = sync_wrap(feedparser.parse)
ImageExtract = re.compile(r"!\[[^\]]*\]\((?P<filename>.*?)(?=\"|\))(?P<optionalpart>\".*\")?\)", re.I)
NoneStr = sc.Or(str, None)

# Schemas
fansubRSSSchemas = sc.Schema(
    {
        sc.Optional("id"): sc.Or(str, int),
        "feeds": [
            {
                "id": sc.Or(str, int),
                "channel": sc.Or(str, int),
                "feedUrl": str,
                sc.Optional("message"): NoneStr,
                sc.Optional("lastEtag"): str,
                sc.Optional("lastModified"): str,
                sc.Optional("embed"): sc.Or(
                    {
                        "title": NoneStr,
                        "description": NoneStr,
                        "url": NoneStr,
                        "thumbnail": NoneStr,
                        "image": NoneStr,
                        "footer": NoneStr,
                        "footer_img": NoneStr,
                        "color": sc.Or(str, int, None),
                        "timestamp": bool,
                    },
                    {},
                ),
            }
        ],
        sc.Optional("premium"): [
            {
                "start": int,
                "duration": int,
            }
        ],
    }
)

fetchedUrlSchemas = sc.Schema({"fetchedURL": [str]})


def cleanup_encoding_error(text: str) -> str:
    """
    Fix encoding errors in text.
    """
    replace_data = {
        "â€™": "’",
    }
    for key, value in replace_data.items():
        text = text.replace(key, value)
    return text.strip()


def rgbint_to_rgbhex(int_num: int) -> str:
    r = int_num // 256 // 256
    int_num -= 256 * 256 * r
    g = int_num // 256
    b = int_num - (256 * g)
    return ("#" + hex(r)[2:] + hex(g)[2:] + hex(b)[2:]).upper()


def first_match_in_list(targets: list, key: str):
    for data in targets:
        try:
            valid = data[key]
            return valid
        except Exception:
            pass
    return None


def normalize_rss_data(entries: dict, base_url: str = "") -> dict:
    """Remove unnecessary tags that basically useless for the bot."""
    KEYS_TO_REMOVE = [
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

    if base_url.endswith("/"):
        base_url = base_url[:-1]

    for KEY in KEYS_TO_REMOVE:
        try:
            del entries[KEY]
        except KeyError:
            pass

    tagar = entries.get("tags", [])
    proper_tag = []
    for tag in tagar:
        proper_tag.append(tag["term"])
    entries["tags"] = proper_tag

    if "media_thumbnail" in entries:
        try:
            matching_image = first_match_in_list(entries["media_thumbnail"], "url")
            if matching_image is None:
                entries["media_thumbnail"] = ""
            else:
                entries["media_thumbnail"] = matching_image
        except IndexError:
            entries["media_thumbnail"] = ""
        except KeyError:
            entries["media_thumbnail"] = ""
    else:
        entries["media_thumbnail"] = ""

    if "summary" in entries:
        parsed_summary = cleanup_encoding_error(mdparse(entries["summary"]))
        extracted_images = list(ImageExtract.finditer(parsed_summary))
        first_image_link = None
        for extracted in extracted_images:
            if extracted:
                filename_match = extracted.group("filename")
                all_match = extracted.group()
                parsed_summary = parsed_summary.replace(all_match, "")
                parse_url = urlparse(filename_match)
                if parse_url.netloc == "":
                    real_url = parse_url.path
                    if real_url.startswith("/"):
                        real_url = real_url[1:]
                    query_params = parse_url.query
                    first_image_link = f"{base_url}/{real_url}"
                    if query_params != "":
                        first_image_link += f"?{query_params}"
                else:
                    skema_url = parse_url.scheme
                    if skema_url == "":
                        skema_url = "http"
                    first_image_link = f"{skema_url}://{parse_url.netloc}{parse_url.path}"
                    if parse_url.query != "":
                        first_image_link += f"?{parse_url.query}"
        entries["summary"] = cleanup_encoding_error(parsed_summary)
        if first_image_link is not None and not entries["media_thumbnail"]:
            entries["media_thumbnail"] = first_image_link

    if "description" in entries:
        parsed_description = cleanup_encoding_error(mdparse(entries["description"]))
        entries["description"] = parsed_description

    if "media_content" in entries:
        media_url = entries["media_content"]
        if media_url:
            matching_image = first_match_in_list(media_url, "url")
            if matching_image is not None:
                entries["media_content"] = matching_image
        else:
            del entries["media_content"]

    return entries


async def async_feedparse(url: str, **kwargs) -> Optional[feedparser.FeedParserDict]:
    aio_timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": "naoTimes-RSSBot/1.0 (+https://github.com/naoTimesdev/naoTimes)"}
    async with aiohttp.ClientSession(timeout=aio_timeout, headers=headers) as session:
        try:
            async with session.get(url) as r:
                r_data = await r.text()
        except asyncio.TimeoutError:
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


class ShowtimesFansubRSS(commands.Cog):
    DEFAULT_MSG = r":newspaper: | Rilisan Baru: **{title}**\n{link}"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.FansubRSS")

        self._MAXIMUM_FEEDS = 5
        self._locke: List[str] = []
        self._running_tasks: List[asyncio.Task] = []
        self.bot.loop.create_task(self._loop_check_internal_cogs(), name="fansubrss-init-propagate")

        self._loop_check_basic_rss.start()
        self._loop_check_premium_rss.start()

    def cog_unload(self):
        self._loop_check_basic_rss.cancel()
        self._loop_check_premium_rss.cancel()
        for task in self._running_tasks:
            task.cancel()

    async def _loop_check_internal_cogs(self):
        all_feeds = await self.get_all_servers()
        self.logger.info("Resaving all internal feeds...")
        for feed in all_feeds:
            await self.bot.redisdb.set(f"ntfsrss_{feed.id}", feed.serialize())
        self.logger.info("All feeds has been resaved to use new format!")

    async def get_server(self, server_id: int):
        rss_feeds = await self.bot.redisdb.get(f"ntfsrss_{server_id}")
        if rss_feeds is None:
            return None
        return FansubRSS.from_dict(server_id, rss_feeds)

    def get_lock(self, server_id: int):
        server_id = str(server_id)
        if server_id not in self._locke:
            self._locke.append(server_id)

    def release_lock(self, server_id: int):
        server_id = str(server_id)
        if server_id in self._locke:
            self._locke.remove(server_id)

    def is_locked(self, server_id: int):
        server_id = str(server_id)
        return server_id in self._locke

    async def get_all_servers(self):
        fsrss_data = await self.bot.redisdb.getalldict("ntfsrss_*")
        all_parsed_feeds: List[FansubRSS] = []
        for srv_id, data in fsrss_data.items():
            srv_id = srv_id.replace("ntfsrss_", "")
            parsed_fsrss = FansubRSS.from_dict(srv_id, data)
            all_parsed_feeds.append(parsed_fsrss)
        return all_parsed_feeds

    async def read_rss_feeds(self, server_id: Union[str, int], hash_ids: Union[str, int]) -> List[str]:
        rss_metadata = await self.bot.redisdb.get(f"ntfsrssd_{server_id}_{hash_ids}")
        if rss_metadata is None:
            return []
        return rss_metadata["fetchedURL"]

    async def _recursive_check_feeds(self, metadata: FansubRSSFeed, fetched_url: List[str]):
        try:
            feed = await asyncio.wait_for(
                async_feedparse(metadata.feed_url, etag=metadata.last_etag, modified=metadata.last_modified),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            self.logger.error(f"connection timeout trying to fetch {metadata.feed_url} rss.")
            return None, metadata
        if not feed:
            return None, metadata

        base_url = feed["feed"]["link"]
        parsed_base_url = urlparse(base_url)

        skema_uri = parsed_base_url.scheme
        if skema_uri == "":
            skema_uri = "http"
        base_url_for_real = f"{skema_uri}://{parsed_base_url.netloc}"

        entries = feed.entries

        filtered_entry = []
        for n, entry in enumerate(entries):
            if entry["link"] in fetched_url:
                continue
            filtered_entry.append(normalize_rss_data(entries[n], base_url_for_real))

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
        metadata.last_etag = etag
        metadata.last_modified = modified_tag
        return filtered_entry, metadata

    async def _actual_internal_feed_rss_checker(
        self, guild_info: discord.Guild, server: FansubRSS, feed: FansubRSSFeed
    ):
        try:
            self.logger.info(f"Fetching feed: {feed.feed_url}")
            fetched_news = await self.read_rss_feeds(server.id, feed.id)
            try:
                new_news, _ = await self._recursive_check_feeds(feed, fetched_news)
            except Exception as e:
                self.logger.error(f"Error fetching feed of {feed!r}", exc_info=e)
                return
            if new_news is None:
                self.logger.error(
                    f"Failed to fetch RSS Feed ({feed}), possiblity include timeout and parsing error."
                )
                return

            if len(new_news) < 1:
                self.logger.info(f"{server!r}: No new news for {feed!r}")
                return

            self.logger.info(f"{server!r}: Updating Feed: {feed!r}")
            channel = guild_info.get_channel(feed.channel)
            if channel is None:
                self.logger.warning(f"{server!r}: Channel {feed!r} not found")
                return
            self.logger.info(f"{server!r}-{feed!r}: Sending result to: #{channel.name}")
            for entry in new_news[::-1]:
                fetched_news.append(entry["link"])
            await self.bot.redisdb.set(f"ntfsrssd_{server.id}_{feed.id}", {"fetchedURL": fetched_news})
            is_forbidden = False
            for entry in new_news[::-1]:
                if is_forbidden:
                    self.logger.warning(
                        f"{server!r}-{feed!r}: Cannot send anything to channel since bot has no perms!"
                    )
                    break
                txt_msg, emb_msg = feed.generate(entry)
                kwargs_to_send = {}
                if txt_msg is not None:
                    kwargs_to_send["content"] = txt_msg
                if emb_msg is not None:
                    kwargs_to_send["embed"] = emb_msg

                if len(list(kwargs_to_send.keys())) < 1:
                    self.logger.warning(
                        f"{server!r}: For some reason, RSS feed `{feed!r}` doesn't have message "
                        "or embed formatting."
                    )
                    continue

                try:
                    await channel.send(**kwargs_to_send)
                except discord.Forbidden:
                    self.logger.warning(f"{server!r}: Forbidden to send message to #{channel.name}")
                    is_forbidden = True
                    continue
                except discord.HTTPException:
                    self.logger.warning(f"{server!r}: Failed to send message to #{channel.name}")
                    continue
        except asyncio.CancelledError:
            self.logger.warning(f"Got hangup for task cancellation for feed {feed!r} for server {server!r}")

    def _deregister_rss_schedule(self, task: asyncio.Task):
        try:
            self.logger.info(f"RSS task {task.get_name()} has finished running")
            self._running_tasks.remove(task)
        except (ValueError, KeyError, IndexError, AttributeError):
            self.logger.error(f"Failed to deregister task {task.get_name()}, probably missing!")

    async def _main_internal_rss_checker(self, server: FansubRSS, ctime: int, has_premium: bool):
        try:
            fetch_feeds: List[FansubRSSFeed] = []
            if len(server.feeds) < 1:
                self.logger.warning(f"{server!r}: no registered feeds")
                return
            if has_premium:
                fetch_feeds.extend(server.feeds)
            else:
                fetch_feeds.append(server.feeds[0])

            guild_info = self.bot.get_guild(server.id)
            if guild_info is None:
                self.logger.warning(f"{server!r}: server not found on bot cache?")
                return

            premium_ = "premium" if has_premium else "basic"

            for feed in fetch_feeds:
                try:
                    _task_name = f"fansubrss-{server.id}-{premium_}-feed_{feed.id}-{ctime}"
                    task: asyncio.Task = self.bot.loop.create_task(
                        self._actual_internal_feed_rss_checker(guild_info, server, feed), name=_task_name
                    )
                    self._running_tasks.append(task)
                    self.logger.info(f"Scheduled RSSFeed checker for {feed!r} ({server!r})")
                    task.add_done_callback(self._deregister_rss_schedule)
                except Exception as e:
                    self.logger.error(
                        f"Failed to schedule RSS checker for feed {feed!r} at {server!r}", exc_info=e
                    )
        except asyncio.CancelledError:
            self.logger.warning(f"Got hangup for task cancellation for server {server!r}")

    def _schedule_dispatch_rss(self, server: FansubRSS, current_time: int, is_premium: bool = False):
        premium_ = "premium" if is_premium else "basic"
        _task_name = f"fansubrss-{server.id}-{premium_}-{current_time}"
        try:
            task: asyncio.Task = self.bot.loop.create_task(
                self._main_internal_rss_checker(server, current_time, is_premium), name=_task_name
            )
            self._running_tasks.append(task)
            task.add_done_callback(self._deregister_rss_schedule)
            self.logger.info(f"Scheduled RSS checker for {server!r}")
        except Exception as e:
            self.logger.error(f"Failed to schedule RSS checker for {server!r}", exc_info=e)

    @tasks.loop(minutes=2.0)
    async def _loop_check_premium_rss(self):
        """A tasks process that will check premium server"""
        all_servers = await self.get_all_servers()
        premium_server = list(filter(lambda x: x.has_premium and not self.is_locked(x.id), all_servers))
        current_time = self.bot.now().int_timestamp
        if len(premium_server) > 0:
            try:
                self.logger.info("[Premium] Scheduling background RSS checks...")
                for server in premium_server:
                    self._schedule_dispatch_rss(server, current_time, True)
                self.logger.info("[Premium] Sleeping...")
            except asyncio.CancelledError:
                self.logger.warning("[Premium] Got cancel signal, stopping...")

    @tasks.loop(minutes=5.0)
    async def _loop_check_basic_rss(self):
        """A tasks that will check non-premium server"""
        all_servers = await self.get_all_servers()
        non_premium_server = list(
            filter(lambda x: not x.has_premium and not self.is_locked(x.id), all_servers)
        )
        current_time = self.bot.now().int_timestamp
        if len(non_premium_server) > 0:
            try:
                self.logger.info("[Basic] Running background RSS checks...")
                for server in non_premium_server:
                    self._schedule_dispatch_rss(server, current_time, False)
                self.logger.info("[Basic] Sleeping...")
            except asyncio.CancelledError:
                self.logger.warning("[Basic] Got cancel signal, stopping...")

    @_loop_check_basic_rss.before_loop
    @_loop_check_premium_rss.before_loop
    async def _loop_check_rss_before(self):
        self.logger.info("[FansubRSS] Waiting till bot is ready...")
        await self.bot.wait_until_ready()
        self.logger.info("[FansubRSS] Bot is now ready!")

    @commands.group(name="fansubrss", aliases=["rss", "fsrss"])
    @commands.has_guild_permissions(manage_guild=True)
    async def _showfsrss(self, ctx: naoTimesContext):
        if ctx.invoked_subcommand is None:
            if not ctx.empty_subcommand(2):
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            helpcmd = ctx.create_help("FansubRSS", desc="Pemantau RSS Fansub")
            helpcmd.add_field(HelpField("fansubrss", "Memunculkan bantuan perintah ini"))
            helpcmd.add_field(HelpField("fansubrss aktifkan", "Mengaktifkan RSS announcer di sebuah kanal"))
            helpcmd.add_field(HelpField("fansubrss ubah", "Mengatur settingan RSS di peladen ini"))
            helpcmd.add_field(HelpField("fansubrss format", "Format bagaimana RSS akan dikirim"))
            helpcmd.add_field(HelpField("fansubrss terakhir", "Mengambil RSS terakhir"))
            helpcmd.add_field(HelpField("fansubrss premium", "Melihat status FansubRSS premium"))
            helpcmd.add_aliases(["rss", "fsrss"])
            await ctx.send(embed=helpcmd.get())

    async def _create_rss_singleton(self, ctx: naoTimesContext, channel: discord.TextChannel):
        guild_id = ctx.guild.id
        prefix = self.bot.prefixes(ctx)
        self.logger.info(f"{guild_id}: waiting for RSS URL input...")
        rss_url = await ctx.wait_content("Mohon ketik/paste URL RSS")
        if rss_url is None:
            return await ctx.send("Timeout, mohon ulangi lagi!")
        if not rss_url:
            return await ctx.send("*Dibatalkan!*")

        is_valid = await check_if_valid(rss_url)
        if not is_valid:
            return await ctx.send("URL yang diberikan bukanlah link RSS yang valid.")

        feeds_parsed = await async_feedparse(rss_url)
        self.logger.info(f"{guild_id}: waiting for confirmation...")

        res = await ctx.confirm(f"Apakah yakin ingin menggunakan link: <{rss_url}>?")
        if not res:
            self.logger.warning(f"{guild_id}: process cancelled.")
            return await ctx.send("Dibatalkan.")

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

        registered_hash = str(guild_id)[5:]
        registered_hash += generate_custom_code(10, True)

        GENERATED_FEED = {
            "id": registered_hash,
            "channel": channel.id,
            "feedUrl": rss_url,
            "message": self.DEFAULT_MSG,
            "lastEtag": "",
            "lastModified": "",
            "embed": {},
        }

        self.logger.info(f"{guild_id}: activating FansubRSS...")
        original_feeds = await self.get_server(guild_id)
        if original_feeds is None:
            json_tables = {
                "feeds": [],
                "premium": [],
            }
            parsed_json = FansubRSS.from_dict(guild_id, json_tables)
        else:
            parsed_json = original_feeds

        parsed_json.add_feed(FansubRSSFeed.from_dict(GENERATED_FEED))

        await self.bot.redisdb.set(f"ntfsrss_{guild_id}", parsed_json.serialize())
        await self.bot.redisdb.set(f"ntfsrssd_{guild_id}_{registered_hash}", {"fetchedURL": skip_fetch_url})
        self.logger.info(f"{guild_id}: FansubRSS is now activated!")
        await ctx.send(
            f"FansubRSS berhasil diaktifkan, silakan atur formatting dengan `{prefix}fansubrss format`"
        )

    @_showfsrss.command(name="aktifkan", aliases=["activate"])
    async def _showfsrss_aktifkan(
        self, ctx: naoTimesContext, *, channel: commands.TextChannelConverter = None
    ):
        guild_id = ctx.guild.id
        if not channel:
            channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            return await ctx.send("Kanal yang dipilih bukanlah kanal teks!")
        if channel.guild.id != guild_id:
            return await ctx.send("Kanal yang dipilih tidak ada di peladen ini!")

        server_rss = await self.bot.redisdb.get(f"ntfsrss_{guild_id}")
        prefix = self.bot.prefixes(ctx)
        if server_rss is not None:
            self.logger.warning(f"{guild_id}: fansubrss sudah diaktifkan di server ini.")
            cmd_name = f"`{prefix}fansubrss ubah`"
            return await ctx.send(
                f"FansubRSS sudah diaktifkan di server ini, silakan gunakan {cmd_name} untuk mengaturnya."
            )

        await self._create_rss_singleton(ctx, channel)

    @_showfsrss.command(name="deaktivasi", aliases=["deactivate"])
    async def _showfsrss_deaktivasi(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        rss_metadata = await self.get_server(guild_id)
        if not rss_metadata:
            self.logger.error(f"{guild_id}: cannot find metadata...")
            return await ctx.send("FansubRSS tidak diaktifkan di peladen ini.")

        self.logger.info(f"{guild_id}: asking for confirmation...")
        res = await ctx.confirm(
            "Apakah anda yakin ingin menonaktifkan FansubRSS (Akan dihapus dari database)"
        )
        if not res:
            self.logger.info(f"{guild_id}: cancelled.")
            return await ctx.send("Dibatalkan.")

        self.logger.info(f"{guild_id}: deactivating FansubRSS...")
        await self.bot.redisdb.rm(f"ntfsrss_{guild_id}")
        self.logger.info(f"{guild_id}: detaching feeds fetched data...")
        for feed in rss_metadata.feeds:
            await self.bot.redisdb.rm(f"ntfsrssd_{guild_id}_{feed.id}")
        self.logger.info(f"{guild_id}: FansubRSS is now deactivated!")
        await ctx.send(
            "Berhasil menonaktifkan, silakan aktifkan kembali via "
            f"`{self.bot.prefixes(ctx)}fansubrss aktifkan`"
        )

    @_showfsrss.command(name="tambah", aliases=["add"])
    async def _showfsrss_tambah(self, ctx: naoTimesContext, *, channel: commands.TextChannelConverter):
        guild_id = ctx.guild.id
        if not channel:
            channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            return await ctx.send("Kanal yang dipilih bukanlah teks kanal!")
        if channel.guild.id != guild_id:
            return await ctx.send("Kanal yang dipilih tidak ada di peladen ini!")

        self.logger.info(f"{guild_id}: fetching RSS metadata...")
        full_rss_metadata = await self.get_server(guild_id)
        if not full_rss_metadata:
            self.logger.error(f"{guild_id}: cannot find metadata...")
            return await ctx.send("FansubRSS tidak diaktifkan di peladen ini.")

        prefix = self.bot.prefixes(ctx)
        total_feeds = len(full_rss_metadata.feeds)
        if not full_rss_metadata.has_premium and total_feeds > 0:
            self.logger.error(f"{guild_id}: not premium user...")
            return await ctx.send(
                f"Server ini tidak mendapatkan fitur premium, silakan refer ke: `{prefix}fansubrss premium`."
            )

        if total_feeds >= self._MAXIMUM_FEEDS:
            self.logger.error(f"{guild_id}: maximum limit reached...")
            return await ctx.send("Telah mencapai limit maksimal RSS untuk user premium.")

        await self._create_rss_singleton(ctx, channel)

    async def _showfsrss_format_internal(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id

        self.get_lock(guild_id)
        rss_metadata = await self.get_server(guild_id)
        if not rss_metadata:
            self.logger.error(f"{guild_id}: cannot find metadata...")
            self.release_lock(guild_id)
            return await ctx.send("FansubRSS tidak diaktifkan di peladen ini.")

        if len(rss_metadata.feeds) < 1:
            self.logger.error(f"{guild_id}: no feeds...")
            self.release_lock(guild_id)
            return await ctx.send("Tidak ada RSS yang terdaftar")

        selected_rss = await ctx.select_simple(rss_metadata.feeds, lambda x: x.feed_url)
        if selected_rss is None:
            self.logger.warning(f"{guild_id}: cancelled")
            self.release_lock(guild_id)
            return await ctx.send("*Dibatalkan*")

        self.logger.info(f"{guild_id}: fetching latest RSS data for sample...")
        feed_data = await async_feedparse(selected_rss.feed_url)
        if not feed_data:
            self.logger.error(f"{guild_id}: cannot fetch data...")
            self.release_lock(guild_id)
            return await ctx.send("Tidak dapat mengambil data RSS, membatalkan...")

        entries_data = feed_data.entries
        sample_entry = normalize_rss_data(entries_data[0])

        def _create_sample_display(entry: dict):
            embed = discord.Embed(
                title="Contoh data",
                description=r"Ketik `{nama_data}` untuk memakai data dari RSS, misalkan "
                "ingin memakai judul dari RSS.\n"
                r"Maka pakai `{title}`",
            )
            for nama_data, isi_data in entry.items():
                if isinstance(isi_data, time.struct_time):
                    isi_data, _ = time_struct_dt(isi_data)
                elif isinstance(isi_data, (list, tuple)):
                    isi_data = [str(val) for val in isi_data]
                    isi_data = ", ".join(isi_data)
                if not isinstance(isi_data, str):
                    isi_data = str(isi_data)
                embed.add_field(name="`{" + str(nama_data) + "}`", value=isi_data)
            return embed

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
        self.logger.info(f"{guild_id}: start modifying...")
        while True:
            embed = discord.Embed(title="FansubRSS")
            embed.description = f"<#{selected_rss.channel}>: {selected_rss.feed_url}"
            rss_msg = selected_rss.message
            if rss_msg is None:
                rss_msg = "*Kosong*"
            else:
                rss_msg = quote(rss_msg)
            embed.add_field(name="1️⃣ Atur pesan", value=rss_msg, inline=False)
            rss_emb_active = "Embed aktif?: Tidak"
            if selected_rss.embed is not None and selected_rss.embed.is_valid:
                rss_emb_active = "Embed aktif?: Ya"
            embed.add_field(name="2️⃣ Atur embed", value=rss_emb_active, inline=False)
            embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=True)
            embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                first_run = False
                emb_msg = await ctx.send(embed=embed)
            else:
                await emb_msg.edit(embed=embed)

            reaction_set = ["1️⃣", "2️⃣", "✅", "❌"]

            def check_reaction(reaction: discord.Reaction, user: discord.User):
                return (
                    reaction.message.id == emb_msg.id
                    and user.id == ctx.author.id
                    and str(reaction.emoji) in reaction_set
                )

            for react in reaction_set:
                await emb_msg.add_reaction(react)

            res: discord.Reaction
            user: discord.Member

            res, user = await self.bot.wait_for("reaction_add", check=check_reaction)
            if user != ctx.author:
                pass
            elif res.emoji == "✅":
                await emb_msg.clear_reactions()
                break
            elif res.emoji == "❌":
                cancelled = True
                await emb_msg.clear_reactions()
                break
            elif res.emoji == "1️⃣":
                self.logger.info(f"{guild_id}: changing message data...")
                await emb_msg.clear_reactions()
                smpl_embed = _create_sample_display(sample_entry)
                await emb_msg.edit(embed=smpl_embed)
                wait_msg = await ctx.wait_content(
                    "Ketik pesan yang diinginkan!\n"
                    "Ketik `clear` untuk menghapus pesan yang ada\n"
                    "Ketik `reset` untuk menormalkannya kembali",
                    True,
                    True,
                    None,
                )

                if not wait_msg:
                    pass
                elif wait_msg == "clear":
                    selected_rss.message = None
                elif wait_msg == "reset":
                    selected_rss.message = self.DEFAULT_MSG
                else:
                    selected_rss.message = wait_msg
                    await ctx.send_timed(f"Pesan berhasil diubah ke: `{wait_msg}`", 2)
            elif res.emoji == "2️⃣":
                self.logger.info(f"{guild_id}: changing embed data...")
                await emb_msg.clear_reactions()
                embed_data = FansubRSSEmbed.from_dict({})
                if selected_rss.embed is not None:
                    embed_data = selected_rss.embed

                cur_emb_data = embed_data.generate(sample_entry, True)
                smpl_embed = _create_sample_display(sample_entry)
                await emb_msg.edit(embed=smpl_embed)
                cur_emb_msg: discord.Message = await ctx.send(embed=cur_emb_data)

                first_embed_run = True
                cancelled_embed = False
                embed_input: str
                prompt_msg: discord.Message = None
                while True:
                    if first_embed_run:
                        first_embed_run = False
                    else:
                        cur_emb_data = embed_data.generate(sample_entry, True)
                        await cur_emb_msg.edit(embed=cur_emb_data)

                    simple_msg = "Ketik `nama_data` untuk mengubah isi embed! (misal `title`)\n"
                    simple_msg += "Lihat referensinya di sini: <https://naoti.me/img/fsrss_embed.png>\n"
                    simple_msg += "Anda juga dapat mengubah strip warna dengan ketik `color`\n\n"
                    simple_msg += "Ketik `reset` untuk menghapus embed yang ada\n"
                    simple_msg += "Ketik `done` jika anda sudah selesai!"

                    [embed_input, prompt_msg, _] = await ctx.wait_content(
                        simple_msg,
                        False,
                        True,
                        None,
                        True,
                        prompt_msg,
                    )
                    if not embed_input:
                        cancelled_embed = True
                        break
                    elif embed_input == "reset":
                        embed_data = None
                        break
                    elif embed_input == "done":
                        break
                    else:
                        if embed_input in valid_embed:
                            self.logger.info(f"embed: changing {embed_input}")
                            extra_clr_txt = (
                                "\n Masukan warna hex (format: #aabbcc), contohnya: `#87D3F8`"  # noqa: E501
                                if "color" in embed_input
                                else ""
                            )

                            msg_changed = await ctx.wait_content(
                                f"Mengubah: `{embed_input}`{extra_clr_txt}\n"
                                "Ketik `clear` untuk menghapus isi bagian ini.",
                                True,
                                True,
                                None,
                            )
                            if not msg_changed:
                                pass
                            elif msg_changed == "clear":
                                embed_data[embed_input] = None
                                await ctx.send_timed(f"Berhasil menghapus data `{embed_input}`", 2)
                            elif embed_input == "color":
                                try:
                                    color_parsed = hex_to_color(msg_changed)
                                    embed_data.color = color_parsed
                                    await ctx.send_timed(f"Berhasil mengubah warna ke: `{color_parsed}`.", 2)
                                except Exception:
                                    await ctx.send_timed("Bukan warna HEX yang valid.", 2)
                            else:
                                embed_data[embed_input] = msg_changed
                                await ctx.send_timed(f"Berhasil mengubah data `{embed_input}`", 2)
                        elif "timestamp" in embed_input:
                            embed_data.timestamp = not embed_data.timestamp
                            acc_ts = "Mengaktifkan"
                            if not embed_data.timestamp:
                                acc_ts = "Menonaktifkan"
                            await ctx.send_timed(f"{acc_ts} timestamp...", 2)
                        else:
                            await ctx.send_timed("Tipe data tidak diketahui...", 2)

                if not cancelled_embed:
                    selected_rss.embed = embed_data

                await cur_emb_msg.delete()
                if prompt_msg:
                    await prompt_msg.delete()
                if not cancelled_embed:
                    await ctx.send_timed("Berhasil mengubah data embed.", 2)

        if cancelled:
            self.release_lock(guild_id)
            self.logger.warning(f"{guild_id}: commiting data is cancelled...")
            return await ctx.send("*Dibatalkan*")

        self.logger.info(f"{guild_id}: commiting data...")
        await emb_msg.delete()
        rss_metadata.update_feed(selected_rss)
        msg_final = await ctx.send("Menyimpan data baru...")
        await self.bot.redisdb.set(f"ntfsrss_{guild_id}", rss_metadata.serialize())
        self.release_lock(guild_id)
        self.logger.info(f"{guild_id}: data commited, process completed!")
        await msg_final.edit(content="Formatting baru telah disimpan!")

    @_showfsrss.command(name="format")
    async def _showfsrss_format(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        try:
            await self._showfsrss_format_internal(ctx)
            self.release_lock(guild_id)
        except Exception as e:
            self.bot.echo_error(e)
            self.release_lock(guild_id)
            await ctx.send("Terjadi kesalahan internal, mohon hubungi Owner Bot!")

    async def _showfsrss_atur_internal(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        self.get_lock(guild_id)
        rss_metadata = await self.get_server(guild_id)
        if not rss_metadata:
            self.logger.error(f"{guild_id}: cannot find metadata...")
            self.release_lock(guild_id)
            return await ctx.send("FansubRSS tidak diaktifkan di peladen ini.")

        if len(rss_metadata.feeds) < 1:
            self.logger.error(f"{guild_id}: no feeds...")
            self.release_lock(guild_id)
            return await ctx.send("Tidak ada RSS yang terdaftar")

        selected_rss = await ctx.select_simple(rss_metadata.feeds, lambda x: x.feed_url)
        if selected_rss is None:
            self.logger.warning(f"{guild_id}: cancelled")
            self.release_lock(guild_id)
            return await ctx.send("*Dibatalkan*")

        first_run = True
        is_cancelled = False
        emb_msg: discord.Message
        self.logger.info(f"{guild_id}: start data modifying...")
        while True:
            embed = discord.Embed(title="FansubRSS")
            embed.add_field(name="1️⃣ Atur URL", value=f"`{selected_rss.feed_url}`", inline=False)
            embed.add_field(
                name="2️⃣ Atur Channel",
                value=f"Sekarang: <#{selected_rss.channel}>",
                inline=False,
            )
            embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=True)
            embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                first_run = False
                emb_msg = await ctx.send(embed=embed)
            else:
                await emb_msg.edit(embed=embed)

            reaction_set = ["1️⃣", "2️⃣", "✅", "❌"]

            def check_reaction(reaction: discord.Reaction, user: discord.User):
                return (
                    reaction.message.id == emb_msg.id
                    and user.id == ctx.author.id
                    and str(reaction.emoji) in reaction_set
                )

            for react in reaction_set:
                await emb_msg.add_reaction(react)

            res: discord.Reaction
            user: discord.Member

            res, user = await self.bot.wait_for("reaction_add", check=check_reaction)
            if user.id != ctx.author.id:
                pass
            elif res.emoji == "✅":
                await emb_msg.clear_reactions()
                break
            elif res.emoji == "❌":
                is_cancelled = True
                await emb_msg.clear_reactions()
                break
            elif res.emoji == "1️⃣":
                self.logger.info(f"{guild_id}: changing rss url...")
                await emb_msg.clear_reactions()
                feed_new_url = await ctx.wait_content("Ketik url RSS baru yang diinginkan!", True, True, None)
                if not feed_new_url:
                    pass
                else:
                    self.logger.info(f"{guild_id}: parsing and checking feed: {feed_new_url}")
                    feed_data = await async_feedparse(feed_new_url)
                    if feed_data:
                        entries_data = feed_data.entries
                        collect_url = [url["link"] for url in entries_data]
                        self.logger.info(f"{guild_id}: dumping all current entries...")
                        saved_rss_data = await self.read_rss_feeds(ctx.message.guild.id, rss_metadata["id"])
                        saved_rss_data.extend(collect_url)
                        await self.bot.redisdb.set(
                            f"ntfsrssd_{guild_id}_{selected_rss.id}", {"fetchedURL": saved_rss_data}
                        )
                        selected_rss.feed_url = feed_new_url
                        await ctx.send_timed(f"RSS Feed berhasil diubah ke: <{feed_new_url}>", 2)
                    else:
                        await ctx.send_timed("URL yang diberikan tidak valid.", 2)
            elif res.emoji == "2️⃣":
                self.logger.info(f"{guild_id}: changing channel target...")
                await emb_msg.clear_reactions()
                channel_feed = await ctx.wait_content(
                    "Ketik ID kanal baru yang diinginkan, atau mention kanalnya!", True, True, None
                )
                if not channel_feed:
                    pass
                else:
                    converter = commands.TextChannelConverter()
                    try:
                        parsed_channel = await converter.convert(ctx, channel_feed)
                        if isinstance(parsed_channel, discord.TextChannel):
                            if parsed_channel.guild.id != guild_id:
                                self.logger.warning(f"{guild_id}: selected channel is not a valid one!")
                                await ctx.send_timed(
                                    "Kanal yang diberikan tidak dapat di temukan di dalam peladen ini!", 2
                                )
                            else:
                                self.logger.info(f"{guild_id}: changing channel to: {parsed_channel.id}")
                                selected_rss.channel = parsed_channel.id
                                await ctx.send_timed(
                                    f"Kanal telah berhasil diubah ke: <#{parsed_channel.id}>", 2
                                )
                        else:
                            await ctx.send_timed("Tidak dapat menemukan kanal tersebut.", 2)
                    except commands.ChannelNotFound:
                        await ctx.send_timed("Kanal yang diberikan tidak valid.", 2)

        if is_cancelled:
            self.release_lock(guild_id)
            self.logger.warning(f"{guild_id}: commiting data is cancelled...")
            return await ctx.send("*Dibatalkan*")

        self.logger.info(f"{guild_id}: commiting data...")
        await emb_msg.delete()
        rss_metadata.update_feed(selected_rss)
        msg_final = await ctx.send("Menyimpan data terbaru...")
        await self.bot.redisdb.set(f"ntfsrss_{guild_id}", rss_metadata.serialize())
        self.release_lock(guild_id)
        await msg_final.edit(content="Data baru telah disimpan!")
        self.logger.info(f"{guild_id}: commiting data done!")

    @_showfsrss.command(name="atur", aliases=["configure", "edit", "ubah"])
    async def _showfsrss_atur(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        try:
            await self._showfsrss_atur_internal(ctx)
            self.release_lock(guild_id)
        except Exception:
            self.release_lock(guild_id)

    @_showfsrss.command(name="terakhir", aliases=["last", "test"])
    async def _showfsrss_terakhir(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        rss_metadata = await self.get_server(guild_id)
        if not rss_metadata:
            return await ctx.send("FansubRSS tidak diaktifkan di peladen ini.")

        selected_rss = await ctx.select_simple(rss_metadata.feeds, lambda x: x.feed_url)
        if selected_rss is None:
            self.logger.warning(f"{guild_id}: cancelled")
            self.release_lock(guild_id)
            return await ctx.send("*Dibatalkan*")

        self.logger.info(f"{guild_id}: fetching RSS data...")
        entries, _ = await self._recursive_check_feeds(selected_rss, [])
        if entries is None:
            return await ctx.send("Gagal mengambil data dari RSS, mohon coba lagi nanti!")

        first_entry = entries[0]

        gen_msg, gen_emb = selected_rss.generate(first_entry)
        if gen_msg is None and gen_emb is None:
            return await ctx.send("Tidak bisa membuat contoh karena formatter kosong!")
        contents = {}
        if gen_emb is not None:
            contents["embed"] = gen_emb
        if gen_msg is not None:
            contents["content"] = gen_msg
        await ctx.send(**contents)

    @_showfsrss.command(name="premium")
    async def _showfsrss_premium(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id

        self.logger.info(f"{guild_id}: fetching server metadata...")
        rss_metadata = await self.get_server(guild_id)
        if not rss_metadata:
            self.logger.error(f"{guild_id}: cannot find metadata...")
            return await ctx.send("FansubRSS tidak diaktifkan di peladen ini.")

        self.logger.info(f"{guild_id}: checking premium status...")
        premium_left = rss_metadata.time_left()
        if premium_left is not None:
            pp_left_t = "Aktif selamanya"
            if isinstance(premium_left, timedelta):
                x_left = TimeString.from_seconds(premium_left.total_seconds())
                pp_left_t = f"sisa {x_left} lagi"
            return await ctx.send(f"💳 | Fitur premium aktif ({pp_left_t})")
        else:
            return await ctx.send(
                "💳 | Fitur premium tidak aktif\n\n"
                "Silakan donasi di link berikut: <https://naoti.me/donasi>"
            )


def setup(bot: naoTimesBot):
    bot.add_cog(ShowtimesFansubRSS(bot))
