"""
A simple RSS fetcher and poster, mostly copying how DiscordRSS work.
The thing is I don't even know how that bot work so I'm basically recreating it.

---

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

import asyncio
import logging
import re
import time
from collections.abc import Mapping
from datetime import timedelta
from typing import Protocol, cast
from urllib.parse import urlparse

import aiohttp
import discord
import feedparser
import schema as sc
from discord import app_commands
from discord.ext import commands, tasks
from markdownify import markdownify as mdparse

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.redis import RedisBridge
from naotimes.showtimes import FansubRSS, FansubRSSEmbed, FansubRSSFeed
from naotimes.timeparse import TimeString
from naotimes.utils import (
    generate_custom_code,
    hex_to_color,
    quote,
    time_struct_dt,
)

ImageExtract = re.compile(r"!\[[^\]]*\]\((?P<filename>.*?)(?=\"|\))(?P<optionalpart>\".*\")?\)", re.IGNORECASE)
NoneStr = sc.Or(str, sc.Const(None))

# Schemas
fansubRSSSchemas = sc.Schema({
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
                sc.Schema({
                    "title": NoneStr,
                    "description": NoneStr,
                    "url": NoneStr,
                    "thumbnail": NoneStr,
                    "image": NoneStr,
                    "footer": NoneStr,
                    "footer_img": NoneStr,
                    "color": sc.Or(str, int, sc.Const(None)),
                    "timestamp": bool,
                }),
                sc.Const({}),
            ),
        }
    ],
    sc.Optional("premium"): [
        {
            "start": int,
            "duration": int,
        }
    ],
})

fetchedUrlSchemas = sc.Schema({"fetchedURL": [str]})


class _NullableMessage(Protocol):
    @property
    def message(self) -> str | None: ...

    @message.setter
    def message(self, data: str | None) -> None: ...


class _NullableFeedEmbed(Protocol):
    @property
    def embed(self) -> FansubRSSEmbed | None: ...

    @embed.setter
    def embed(self, data: FansubRSSEmbed | None) -> None: ...


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


def first_match_in_list(targets: object, key: str) -> object | None:
    if not isinstance(targets, list):
        return None
    for data in targets:
        if isinstance(data, Mapping):
            valid = data.get(key)
            if valid is not None:
                return valid
    return None


def normalize_rss_data(entries: dict[str, object], base_url: str = "") -> dict[str, object]:
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

    base_url = base_url.removesuffix("/")

    for key in KEYS_TO_REMOVE:
        entries.pop(key, None)

    tagar = entries.get("tags", [])
    proper_tag: list[str] = []
    if isinstance(tagar, list):
        for tag in tagar:
            if isinstance(tag, Mapping):
                term = tag.get("term")
                if isinstance(term, str):
                    proper_tag.append(term)
    entries["tags"] = proper_tag

    if "media_thumbnail" in entries:
        matching_image = first_match_in_list(entries["media_thumbnail"], "url")
        entries["media_thumbnail"] = matching_image if isinstance(matching_image, str) else ""
    else:
        entries["media_thumbnail"] = ""

    summary = entries.get("summary")
    if isinstance(summary, str):
        parsed_summary = cleanup_encoding_error(mdparse(summary))
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
                    real_url = real_url.removeprefix("/")
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

    description = entries.get("description")
    if isinstance(description, str):
        parsed_description = cleanup_encoding_error(mdparse(description))
        entries["description"] = parsed_description

    if "media_content" in entries:
        media_url = entries["media_content"]
        if isinstance(media_url, list) and media_url:
            matching_image = first_match_in_list(media_url, "url")
            if isinstance(matching_image, str):
                entries["media_content"] = matching_image
        else:
            del entries["media_content"]

    return entries


async def async_feedparse(
    url: str, *, etag: str | None = None, modified: str | None = None
) -> feedparser.FeedParserDict | None:
    aio_timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": "naoTimes-RSSBot/1.0 (+https://github.com/naoTimesdev/naoTimes)"}
    async with aiohttp.ClientSession(timeout=aio_timeout, headers=headers) as session:
        try:
            async with session.get(url) as r:
                r_data = await r.text()
        except TimeoutError:
            return None
        except aiohttp.ClientError:
            return None
    return await asyncio.to_thread(feedparser.parse, r_data, etag=etag, modified=modified)


def feed_entry_url(entry: Mapping[str, object]) -> str | None:
    """Return the entry's stable URL field when the feed includes one."""
    for field in ("link", "url"):
        value = entry.get(field)
        if isinstance(value, str):
            return value
    return None


async def check_if_valid(url: str) -> bool:
    feed = await async_feedparse(url)

    if feed is None:
        return False

    if not feed.entries:
        return False
    return True


class FansubRSSGroup(app_commands.Group):
    """Slash group that requires the *Manage Server* permission."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        if perms is not None and perms.manage_guild:
            return True
        bot = cast(naoTimesBot, interaction.client)
        await interaction.response.send_message(
            bot.i18n_for(interaction.guild, "showtimes").t("fansubrss.manage_server_required"), ephemeral=True
        )
        return False


EMBED_PARTS = [
    app_commands.Choice(
        name=app_commands.locale_str("Judul (title)", key="showtimes.fansubrss.embed_parts.title"), value="title"
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Deskripsi (description)", key="showtimes.fansubrss.embed_parts.description"),
        value="description",
    ),
    app_commands.Choice(
        name=app_commands.locale_str("URL (url)", key="showtimes.fansubrss.embed_parts.url"), value="url"
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Warna (color, hex)", key="showtimes.fansubrss.embed_parts.color"), value="color"
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Thumbnail", key="showtimes.fansubrss.embed_parts.thumbnail"), value="thumbnail"
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Gambar (image)", key="showtimes.fansubrss.embed_parts.image"), value="image"
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Footer", key="showtimes.fansubrss.embed_parts.footer"), value="footer"
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Gambar footer (footer_img)", key="showtimes.fansubrss.embed_parts.footer_img"),
        value="footer_img",
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Timestamp (ya/tidak)", key="showtimes.fansubrss.embed_parts.timestamp"),
        value="timestamp",
    ),
    app_commands.Choice(
        name=app_commands.locale_str("Reset seluruh embed", key="showtimes.fansubrss.embed_parts.reset"), value="reset"
    ),
]


class FansubRSSMessageModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "ShowtimesFansubRSS",
        feed_id: str,
        current: str | None,
        *,
        title: str,
        label: str,
    ):
        super().__init__(title=title)
        self.cog = cog
        self.feed_id = feed_id
        self.pesan = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1800,
            default=current,
        )
        self.add_item(self.pesan)

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        guild_id = await self.cog._guild_id(interaction)
        if guild_id is None:
            return
        mod = self.cog.bot.i18n_for(interaction.guild, "showtimes")
        meta = await self.cog.get_server(guild_id)
        if meta is None:
            await interaction.response.send_message(mod.t("fansubrss.not_enabled"), ephemeral=True)
            return
        feed = meta.get_feed(self.feed_id)
        if feed is None:
            await interaction.response.send_message(mod.t("fansubrss.feed_not_found"), ephemeral=True)
            return
        text = str(self.pesan.value).strip()
        cast(_NullableMessage, feed).message = text or None
        meta.update_feed(feed)
        await self.cog._redisdb().set(f"ntfsrss_{guild_id}", meta.serialize())
        message = feed.message
        if message:
            await interaction.response.send_message(
                mod.t("fansubrss.message_updated", message=quote(message)), ephemeral=True
            )
        else:
            await interaction.response.send_message(mod.t("fansubrss.message_removed"), ephemeral=True)


class ShowtimesFansubRSS(commands.Cog):
    DEFAULT_MSG = r":newspaper: | Rilisan Baru: **{title}**\n{link}"

    fansubrss = FansubRSSGroup(
        name="fansubrss",
        description=app_commands.locale_str("Pemantau RSS Fansub", key="showtimes.fansubrss.description"),
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.FansubRSS")

        self._MAXIMUM_FEEDS = 5
        self._locke: list[str] = []
        self._running_tasks: list[asyncio.Task] = []
        self.bot.loop.create_task(self._loop_check_internal_cogs(), name="fansubrss-init-propagate")

        self._loop_check_basic_rss.start()
        self._loop_check_premium_rss.start()

    async def cog_unload(self):
        self._loop_check_basic_rss.cancel()
        self._loop_check_premium_rss.cancel()
        for task in self._running_tasks:
            task.cancel()

    def _redisdb(self) -> RedisBridge:
        redisdb = self.bot.redisdb
        if redisdb is None:
            raise RuntimeError("Redis bridge is not initialized")
        return redisdb

    @staticmethod
    async def _guild_id(interaction: discord.Interaction) -> int | None:
        if interaction.guild is None:
            bot = cast(naoTimesBot, interaction.client)
            await interaction.response.send_message(
                bot.i18n_for(interaction.guild, "showtimes").t("errors.guild_only_server"), ephemeral=True
            )
            return None
        return interaction.guild.id

    async def _loop_check_internal_cogs(self):
        all_feeds = await self.get_all_servers()
        self.logger.info("Resaving all internal feeds...")
        for feed in all_feeds:
            await self._redisdb().set(f"ntfsrss_{feed.id}", feed.serialize())
        self.logger.info("All feeds has been resaved to use new format!")

    async def get_server(self, server_id: int) -> FansubRSS | None:
        rss_feeds = await self._redisdb().get(f"ntfsrss_{server_id}")
        if rss_feeds is None:
            return None
        return FansubRSS.from_dict(server_id, rss_feeds)

    def get_lock(self, server_id: int) -> None:
        lock_id = str(server_id)
        if lock_id not in self._locke:
            self._locke.append(lock_id)

    def release_lock(self, server_id: int) -> None:
        lock_id = str(server_id)
        if lock_id in self._locke:
            self._locke.remove(lock_id)

    def is_locked(self, server_id: int) -> bool:
        return str(server_id) in self._locke

    async def get_all_servers(self):
        fsrss_data = await self._redisdb().getalldict("ntfsrss_*")
        all_parsed_feeds: list[FansubRSS] = []
        for srv_id, data in fsrss_data.items():
            srv_id = srv_id.replace("ntfsrss_", "")
            parsed_fsrss = FansubRSS.from_dict(srv_id, data)
            all_parsed_feeds.append(parsed_fsrss)
        return all_parsed_feeds

    async def read_rss_feeds(self, server_id: str | int, hash_ids: str | int) -> list[str]:
        rss_metadata = await self._redisdb().get(f"ntfsrssd_{server_id}_{hash_ids}")
        if not isinstance(rss_metadata, Mapping):
            return []
        fetched_urls = rss_metadata.get("fetchedURL")
        if not isinstance(fetched_urls, list):
            return []
        return [url for url in fetched_urls if isinstance(url, str)]

    async def _recursive_check_feeds(
        self, metadata: FansubRSSFeed, fetched_url: list[str]
    ) -> tuple[list[dict[str, object]] | None, FansubRSSFeed]:
        try:
            feed = await asyncio.wait_for(
                async_feedparse(metadata.feed_url, etag=metadata.last_etag, modified=metadata.last_modified),
                timeout=15.0,
            )
        except TimeoutError:
            self.logger.error(f"connection timeout trying to fetch {metadata.feed_url} rss.")
            return None, metadata
        if not feed:
            return None, metadata

        feed_info = feed.get("feed")
        base_url = feed_info.get("link") if isinstance(feed_info, Mapping) else None
        parsed_base_url = urlparse(base_url) if isinstance(base_url, str) else urlparse(metadata.feed_url)

        skema_uri = parsed_base_url.scheme
        if skema_uri == "":
            skema_uri = "http"
        base_url_for_real = f"{skema_uri}://{parsed_base_url.netloc}"

        entries = feed.entries

        filtered_entry: list[dict[str, object]] = []
        for entry in entries:
            entry_url = feed_entry_url(entry)
            if entry_url is not None and entry_url in fetched_url:
                continue
            filtered_entry.append(normalize_rss_data(dict(entry), base_url_for_real))

        etag = feed.get("etag")
        modified = feed.get("modified")
        metadata.last_etag = etag if isinstance(etag, str) else ""
        if isinstance(modified, str):
            metadata.last_modified = modified
        elif isinstance(modified, time.struct_time):
            metadata.last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT", modified)
        else:
            metadata.last_modified = ""
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
                self.logger.error(f"Failed to fetch RSS Feed ({feed}), possiblity include timeout and parsing error.")
                return

            if len(new_news) < 1:
                self.logger.info(f"{server!r}: No new news for {feed!r}")
                return

            self.logger.info(f"{server!r}: Updating Feed: {feed!r}")
            channel = guild_info.get_channel(feed.channel)
            if not isinstance(channel, discord.TextChannel):
                self.logger.warning(f"{server!r}: Text channel for {feed!r} was not found")
                return
            self.logger.info(f"{server!r}-{feed!r}: Sending result to: #{channel.name}")
            for entry in new_news[::-1]:
                entry_url = feed_entry_url(entry)
                if entry_url is not None:
                    fetched_news.append(entry_url)
            await self._redisdb().set(f"ntfsrssd_{server.id}_{feed.id}", {"fetchedURL": fetched_news})
            is_forbidden = False
            for entry in new_news[::-1]:
                if is_forbidden:
                    self.logger.warning(f"{server!r}-{feed!r}: Cannot send anything to channel since bot has no perms!")
                    break
                txt_msg, emb_msg = feed.generate(entry)
                if txt_msg is None and emb_msg is None:
                    self.logger.warning(
                        f"{server!r}: For some reason, RSS feed `{feed!r}` doesn't have message or embed formatting."
                    )
                    continue

                try:
                    if txt_msg is not None and emb_msg is not None:
                        await channel.send(content=txt_msg, embed=emb_msg)
                    elif txt_msg is not None:
                        await channel.send(content=txt_msg)
                    elif emb_msg is not None:
                        await channel.send(embed=emb_msg)
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
            fetch_feeds: list[FansubRSSFeed] = []
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
                    task_name = f"fansubrss-{server.id}-{premium_}-feed_{feed.id}-{ctime}"
                    task: asyncio.Task = self.bot.loop.create_task(
                        self._actual_internal_feed_rss_checker(guild_info, server, feed), name=task_name
                    )
                    self._running_tasks.append(task)
                    self.logger.info(f"Scheduled RSSFeed checker for {feed!r} ({server!r})")
                    task.add_done_callback(self._deregister_rss_schedule)
                except Exception as e:
                    self.logger.error(f"Failed to schedule RSS checker for feed {feed!r} at {server!r}", exc_info=e)
        except asyncio.CancelledError:
            self.logger.warning(f"Got hangup for task cancellation for server {server!r}")

    def _schedule_dispatch_rss(self, server: FansubRSS, current_time: int, is_premium: bool = False):
        premium_ = "premium" if is_premium else "basic"
        task_name = f"fansubrss-{server.id}-{premium_}-{current_time}"
        try:
            task: asyncio.Task = self.bot.loop.create_task(
                self._main_internal_rss_checker(server, current_time, is_premium), name=task_name
            )
            self._running_tasks.append(task)
            task.add_done_callback(self._deregister_rss_schedule)
            self.logger.info(f"Scheduled RSS checker for {server!r}")
        except Exception as e:
            self.logger.error(f"Failed to schedule RSS checker for {server!r}", exc_info=e)

    @tasks.loop(minutes=2.0, name="showtimes-fansubss-premium")
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

    @tasks.loop(minutes=5.0, name="showtimes-fansubss-normal")
    async def _loop_check_basic_rss(self):
        """A tasks that will check non-premium server"""
        all_servers = await self.get_all_servers()
        non_premium_server = list(filter(lambda x: not x.has_premium and not self.is_locked(x.id), all_servers))
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

    # ------------------------------------------------------------------ slash helpers
    async def _feed_auto(self, inter: discord.Interaction, current: str):
        if inter.guild is None:
            return []
        meta = await self.get_server(inter.guild.id)
        if not meta:
            return []
        current = current.lower()
        choices = []
        for feed in meta.feeds:
            label = f"{feed.feed_url}"[:100]
            if current and current not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label, value=str(feed.id)))
        return choices[:25]

    async def _pick_feed(
        self, inter: discord.Interaction, feed_id: str | None
    ) -> tuple[FansubRSS | None, FansubRSSFeed | None]:
        """Returns ``(metadata, feed)``; replies with the error and returns ``(None, None)`` on failure."""
        ctx = await self.bot.get_context(inter)
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return None, None
        meta = await self.get_server(guild_id)
        if not meta:
            await inter.response.send_message(ctx.t("fansubrss.not_enabled"), ephemeral=True)
            return None, None
        if len(meta.feeds) < 1:
            await inter.response.send_message(ctx.t("fansubrss.no_feeds"), ephemeral=True)
            return None, None
        if feed_id is None:
            if len(meta.feeds) > 1:
                await inter.response.send_message(ctx.t("fansubrss.multiple_feeds"), ephemeral=True)
                return None, None
            return meta, meta.feeds[0]
        feed = meta.get_feed(feed_id)
        if feed is None:
            feed = next((f for f in meta.feeds if f.feed_url == feed_id), None)
        if feed is None:
            await inter.response.send_message(ctx.t("fansubrss.feed_not_found"), ephemeral=True)
            return None, None
        return meta, feed

    @staticmethod
    def _text_channel_ok(inter: discord.Interaction, channel: object) -> tuple[discord.TextChannel | None, str | None]:
        if inter.guild is None:
            return None, "errors.guild_only_server"
        if not isinstance(channel, discord.TextChannel):
            return None, "fansubrss.not_text_channel"
        if channel.guild.id != inter.guild.id:
            return None, "fansubrss.channel_wrong_guild"
        return channel, None

    async def _create_rss_singleton(self, inter: discord.Interaction, channel: discord.TextChannel, rss_url: str):
        """Validate the URL, ask for confirmation, then register the feed. Expects a deferred interaction."""
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return
        ctx = await self.bot.get_context(inter)

        feeds_parsed = await async_feedparse(rss_url) if await check_if_valid(rss_url) else None
        if feeds_parsed is None:
            return await ctx.send(ctx.t("fansubrss.invalid_rss_url"))
        if not await ctx.confirm(ctx.t("fansubrss.confirm_link", url=rss_url, channel=channel.mention)):
            return await ctx.send(ctx.t("errors.cancelled_plain"))

        skip_fetch_url: list[str] = []
        for entry in feeds_parsed.entries:
            entry_url = feed_entry_url(entry)
            if entry_url is not None:
                skip_fetch_url.append(entry_url)

        registered_hash = str(guild_id)[5:]
        registered_hash += generate_custom_code(10, True)
        generated_feed = {
            "id": registered_hash,
            "channel": channel.id,
            "feedUrl": rss_url,
            "message": self.DEFAULT_MSG,
            "lastEtag": "",
            "lastModified": "",
            "embed": {},
        }

        self.logger.info(f"{guild_id}: activating FansubRSS...")
        parsed_json = await self.get_server(guild_id)
        if parsed_json is None:
            parsed_json = FansubRSS.from_dict(guild_id, {"feeds": [], "premium": []})
        parsed_json.add_feed(FansubRSSFeed.from_dict(generated_feed))

        await self._redisdb().set(f"ntfsrss_{guild_id}", parsed_json.serialize())
        await self._redisdb().set(f"ntfsrssd_{guild_id}_{registered_hash}", {"fetchedURL": skip_fetch_url})
        self.logger.info(f"{guild_id}: FansubRSS is now activated!")
        await ctx.send(ctx.t("fansubrss.activated"))

    # ------------------------------------------------------------------ aktifkan / tambah / deaktivasi
    @fansubrss.command(
        name="aktifkan",
        description=app_commands.locale_str(
            "Aktifkan RSS announcer di sebuah kanal", key="showtimes.fansubrss.aktifkan"
        ),
    )
    @app_commands.describe(
        url=app_commands.locale_str("URL RSS fansub", key="showtimes.fansubrss.option_url"),
        kanal=app_commands.locale_str("Kanal tujuan (bawaan: kanal ini)", key="showtimes.fansubrss.option_kanal"),
    )
    async def _showfsrss_aktifkan(self, inter: discord.Interaction, url: str, kanal: discord.TextChannel | None = None):
        ctx = await self.bot.get_context(inter)
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return
        channel, error = self._text_channel_ok(inter, kanal or inter.channel)
        if error is not None or channel is None:
            return await inter.response.send_message(ctx.t(error or "fansubrss.not_text_channel"), ephemeral=True)
        if await self._redisdb().get(f"ntfsrss_{guild_id}") is not None:
            return await inter.response.send_message(ctx.t("fansubrss.already_active"), ephemeral=True)
        await inter.response.defer()
        await self._create_rss_singleton(inter, channel, url.strip())

    @fansubrss.command(
        name="tambah",
        description=app_commands.locale_str(
            "Tambah RSS feed baru (premium untuk lebih dari satu)", key="showtimes.fansubrss.tambah"
        ),
    )
    @app_commands.describe(
        url=app_commands.locale_str("URL RSS fansub", key="showtimes.fansubrss.option_url"),
        kanal=app_commands.locale_str("Kanal tujuan (bawaan: kanal ini)", key="showtimes.fansubrss.option_kanal"),
    )
    async def _showfsrss_tambah(self, inter: discord.Interaction, url: str, kanal: discord.TextChannel | None = None):
        ctx = await self.bot.get_context(inter)
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return
        channel, error = self._text_channel_ok(inter, kanal or inter.channel)
        if error is not None or channel is None:
            return await inter.response.send_message(ctx.t(error or "fansubrss.not_text_channel"), ephemeral=True)
        meta = await self.get_server(guild_id)
        if not meta:
            return await inter.response.send_message(ctx.t("fansubrss.not_enabled"), ephemeral=True)
        total_feeds = len(meta.feeds)
        if not meta.has_premium and total_feeds > 0:
            return await inter.response.send_message(ctx.t("fansubrss.premium_required"), ephemeral=True)
        if total_feeds >= self._MAXIMUM_FEEDS:
            return await inter.response.send_message(ctx.t("fansubrss.max_feeds"), ephemeral=True)
        await inter.response.defer()
        await self._create_rss_singleton(inter, channel, url.strip())

    @fansubrss.command(
        name="deaktivasi",
        description=app_commands.locale_str(
            "Nonaktifkan FansubRSS dan hapus semua feed", key="showtimes.fansubrss.deaktivasi"
        ),
    )
    async def _showfsrss_deaktivasi(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return
        rss_metadata = await self.get_server(guild_id)
        if not rss_metadata:
            return await inter.response.send_message(ctx.t("fansubrss.not_enabled"), ephemeral=True)
        await inter.response.defer()
        ctx = await self.bot.get_context(inter)
        if not await ctx.confirm(ctx.t("fansubrss.deactivate_confirm")):
            return await ctx.send(ctx.t("errors.cancelled_plain"))

        await self._redisdb().rm(f"ntfsrss_{guild_id}")
        for feed in rss_metadata.feeds:
            await self._redisdb().rm(f"ntfsrssd_{guild_id}_{feed.id}")
        self.logger.info(f"{guild_id}: FansubRSS is now deactivated!")
        await ctx.send(ctx.t("fansubrss.deactivated"))

    # ------------------------------------------------------------------ format
    @fansubrss.command(
        name="pesan",
        description=app_commands.locale_str(
            "Atur pesan teks yang dikirim untuk setiap rilisan RSS", key="showtimes.fansubrss.pesan"
        ),
    )
    @app_commands.describe(
        feed=app_commands.locale_str("RSS feed (bisa dikosongkan jika hanya ada satu)", key="showtimes.options.feed")
    )
    async def _showfsrss_pesan(self, inter: discord.Interaction, feed: str | None = None):
        ctx = await self.bot.get_context(inter)
        _, selected = await self._pick_feed(inter, feed)
        if selected is None:
            return
        await inter.response.send_modal(
            FansubRSSMessageModal(
                self,
                str(selected.id),
                selected.message,
                title=ctx.t("fansubrss.modal_title"),
                label=ctx.t("fansubrss.modal_label"),
            )
        )

    @fansubrss.command(
        name="data",
        description=app_commands.locale_str(
            "Lihat contoh data RSS yang bisa dipakai di format (`{title}` dll)", key="showtimes.fansubrss.data"
        ),
    )
    @app_commands.describe(
        feed=app_commands.locale_str("RSS feed (bisa dikosongkan jika hanya ada satu)", key="showtimes.options.feed")
    )
    async def _showfsrss_data(self, inter: discord.Interaction, feed: str | None = None):
        ctx = await self.bot.get_context(inter)
        _, selected = await self._pick_feed(inter, feed)
        if selected is None:
            return
        await inter.response.defer(ephemeral=True)
        feed_data = await async_feedparse(selected.feed_url)
        if not feed_data or not feed_data.entries:
            return await inter.followup.send(ctx.t("fansubrss.fetch_failed"), ephemeral=True)
        await inter.followup.send(
            embed=self._sample_display(ctx, normalize_rss_data(feed_data.entries[0])), ephemeral=True
        )

    @staticmethod
    def _sample_display(ctx: naoTimesContext, entry: dict) -> discord.Embed:
        embed = discord.Embed(
            title=ctx.t("fansubrss.sample_title"),
            description=ctx.t("fansubrss.sample_description"),
        )
        for nama_data, isi_data in list(entry.items())[:25]:
            if isinstance(isi_data, time.struct_time):
                isi_data, _ = time_struct_dt(isi_data)
            elif isinstance(isi_data, (list, tuple)):
                isi_data = ", ".join(str(val) for val in isi_data)
            if not isinstance(isi_data, str):
                isi_data = str(isi_data)
            embed.add_field(name=("`{" + str(nama_data) + "}`")[:256], value=(isi_data or "-")[:1024])
        return embed

    @fansubrss.command(
        name="embed",
        description=app_commands.locale_str(
            "Atur bagian embed yang dikirim untuk setiap rilisan RSS", key="showtimes.fansubrss.embed"
        ),
    )
    @app_commands.describe(
        bagian=app_commands.locale_str("Bagian embed yang diubah", key="showtimes.fansubrss.option_bagian"),
        nilai=app_commands.locale_str(
            "Isi baru (kosongkan untuk menghapus; untuk timestamp: ya/tidak; warna: #aabbcc)",
            key="showtimes.fansubrss.option_nilai",
        ),
        feed=app_commands.locale_str("RSS feed (bisa dikosongkan jika hanya ada satu)", key="showtimes.options.feed"),
    )
    @app_commands.choices(bagian=EMBED_PARTS)
    async def _showfsrss_embed(
        self,
        inter: discord.Interaction,
        bagian: app_commands.Choice[str],
        nilai: str | None = None,
        feed: str | None = None,
    ):
        ctx = await self.bot.get_context(inter)
        meta, selected = await self._pick_feed(inter, feed)
        if meta is None or selected is None:
            return
        part = bagian.value
        embed_data = selected.embed if selected.embed is not None else FansubRSSEmbed.from_dict({})
        note = ""
        if part == "reset":
            embed_data = None
            note = ctx.t("fansubrss.embed_reset")
        elif part == "timestamp":
            if nilai is None:
                embed_data.timestamp = not embed_data.timestamp
            else:
                embed_data.timestamp = nilai.strip().lower() in ("ya", "yes", "true", "1", "on")
            note = (
                ctx.t("fansubrss.timestamp_enabled") if embed_data.timestamp else ctx.t("fansubrss.timestamp_disabled")
            )
        elif part == "color":
            if not nilai:
                embed_data._color = None
                note = ctx.t("fansubrss.color_removed")
            else:
                try:
                    embed_data.color = hex_to_color(nilai.strip())
                    note = ctx.t("fansubrss.color_set", color=nilai.strip())
                except Exception:
                    return await inter.response.send_message(ctx.t("fansubrss.invalid_color"), ephemeral=True)
        elif part in {"title", "description", "url", "thumbnail", "image", "footer", "footer_img"}:
            field_value = nilai or None
            if part == "title":
                embed_data.title = field_value
            elif part == "description":
                embed_data.description = field_value
            elif part == "url":
                embed_data.url = field_value
            elif part == "thumbnail":
                embed_data.thumbnail = field_value
            elif part == "image":
                embed_data.image = field_value
            elif part == "footer":
                embed_data.footer = field_value
            else:
                embed_data.footer_img = field_value
            note = (
                ctx.t("fansubrss.embed_part_updated", part=part)
                if nilai
                else ctx.t("fansubrss.embed_part_removed", part=part)
            )
        else:
            return await inter.response.send_message(ctx.t("fansubrss.unknown_embed_part"), ephemeral=True)

        cast(_NullableFeedEmbed, selected).embed = embed_data
        meta.update_feed(selected)
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return
        await self._redisdb().set(f"ntfsrss_{guild_id}", meta.serialize())

        await inter.response.defer(ephemeral=True)
        preview = None
        if embed_data is not None:
            feed_data = await async_feedparse(selected.feed_url)
            if feed_data and feed_data.entries:
                preview = embed_data.generate(normalize_rss_data(feed_data.entries[0]), True)
        if preview is not None:
            await inter.followup.send(note, embed=preview, ephemeral=True)
        else:
            await inter.followup.send(note, ephemeral=True)

    # ------------------------------------------------------------------ atur
    @fansubrss.command(
        name="atur",
        description=app_commands.locale_str("Ubah URL atau kanal sebuah RSS feed", key="showtimes.fansubrss.atur"),
    )
    @app_commands.describe(
        feed=app_commands.locale_str("RSS feed (bisa dikosongkan jika hanya ada satu)", key="showtimes.options.feed"),
        url=app_commands.locale_str("URL RSS baru", key="showtimes.fansubrss.option_url"),
        kanal=app_commands.locale_str("Kanal tujuan baru", key="showtimes.fansubrss.option_kanal"),
    )
    async def _showfsrss_atur(
        self,
        inter: discord.Interaction,
        feed: str | None = None,
        url: str | None = None,
        kanal: discord.TextChannel | None = None,
    ):
        ctx = await self.bot.get_context(inter)
        if url is None and kanal is None:
            return await inter.response.send_message(ctx.t("fansubrss.url_or_channel_required"), ephemeral=True)
        if kanal is not None:
            _, error = self._text_channel_ok(inter, kanal)
            if error:
                return await inter.response.send_message(ctx.t(error), ephemeral=True)
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return
        meta, selected = await self._pick_feed(inter, feed)
        if selected is None or meta is None:
            return
        await inter.response.defer()
        changes: list[str] = []
        if url is not None:
            url = url.strip()
            feed_data = await async_feedparse(url)
            if not feed_data or not feed_data.entries:
                return await inter.followup.send(ctx.t("fansubrss.invalid_url"))
            collect_url = [entry_url for entry in feed_data.entries if (entry_url := feed_entry_url(entry))]
            saved_rss_data = await self.read_rss_feeds(guild_id, selected.id)
            saved_rss_data.extend(collect_url)
            await self._redisdb().set(f"ntfsrssd_{guild_id}_{selected.id}", {"fetchedURL": saved_rss_data})
            selected.feed_url = url
            changes.append(ctx.t("fansubrss.change_url", url=url))
        if kanal is not None:
            selected.channel = kanal.id
            changes.append(ctx.t("fansubrss.change_channel", channel=kanal.mention))
        meta.update_feed(selected)
        await self._redisdb().set(f"ntfsrss_{guild_id}", meta.serialize())
        await inter.followup.send(ctx.t("fansubrss.saved_changes", changes="\n".join(changes)))

    # ------------------------------------------------------------------ terakhir
    @fansubrss.command(
        name="terakhir",
        description=app_commands.locale_str(
            "Lihat contoh hasil format dari rilisan RSS terakhir", key="showtimes.fansubrss.terakhir"
        ),
    )
    @app_commands.describe(
        feed=app_commands.locale_str("RSS feed (bisa dikosongkan jika hanya ada satu)", key="showtimes.options.feed")
    )
    async def _showfsrss_terakhir(self, inter: discord.Interaction, feed: str | None = None):
        _, selected = await self._pick_feed(inter, feed)
        if selected is None:
            return
        await inter.response.defer()
        ctx = await self.bot.get_context(inter)
        entries, _ = await self._recursive_check_feeds(selected, [])
        if not entries:
            return await ctx.send(ctx.t("fansubrss.fetch_retry"))
        gen_msg, gen_emb = selected.generate(entries[0])
        if gen_msg is None and gen_emb is None:
            return await ctx.send(ctx.t("fansubrss.empty_formatter"))
        if gen_msg is not None and gen_emb is not None:
            await ctx.send(gen_msg, embed=gen_emb)
        elif gen_msg is not None:
            await ctx.send(gen_msg)
        elif gen_emb is not None:
            await ctx.send(embed=gen_emb)

    # ------------------------------------------------------------------ premium
    @fansubrss.command(
        name="premium",
        description=app_commands.locale_str("Lihat status FansubRSS premium", key="showtimes.fansubrss.premium"),
    )
    async def _showfsrss_premium(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        guild_id = await self._guild_id(inter)
        if guild_id is None:
            return
        rss_metadata = await self.get_server(guild_id)
        if not rss_metadata:
            return await inter.response.send_message(ctx.t("fansubrss.not_enabled"), ephemeral=True)
        premium_left = rss_metadata.time_left()
        if premium_left is not None:
            pp_left_t = ctx.t("fansubrss.premium_forever")
            if isinstance(premium_left, timedelta):
                x_left = TimeString.from_seconds(premium_left.total_seconds())
                pp_left_t = ctx.t("fansubrss.premium_left", time=x_left)
            return await inter.response.send_message(ctx.t("fansubrss.premium_active", left=pp_left_t))
        await inter.response.send_message(ctx.t("fansubrss.premium_inactive"))

    _showfsrss_pesan.autocomplete("feed")(_feed_auto)
    _showfsrss_data.autocomplete("feed")(_feed_auto)
    _showfsrss_embed.autocomplete("feed")(_feed_auto)
    _showfsrss_atur.autocomplete("feed")(_feed_auto)
    _showfsrss_terakhir.autocomplete("feed")(_feed_auto)


async def setup(bot: naoTimesBot):
    await bot.add_cog(ShowtimesFansubRSS(bot))
