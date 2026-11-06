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

import asyncio
import inspect
import logging
import os
import platform
import sys
import traceback
import typing as T
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, TypeVar, cast, overload

import aiohttp
import arrow
import discord
from anyio import Path as AsyncPath
from async_lru import alru_cache
from discord.ext import commands

from naotimes.log import RollingFileHandler

from .config import (
    naoTimesArgParse,
    naoTimesBotConfig,
    naoTimesKBBIConfig,
    naoTimesUserPassConfig,
    naoTimesVNDBConfig,
)
from .context import naoTimesAppTree, naoTimesContext
from .grouping import CommandGrouper
from .http import (
    KBBI,
    AnilistBucket,
    AutentikasiKBBI,
    GraphQLClient,
    JishoAPI,
    MerriamWebsterClient,
    TesaurusAsync,
    VNDBClient,
    WolframAPI,
)
from .http.server import Route as RouteDef
from .http.server import naoTimesHTTPServer
from .i18n import I18nDictionary, InternalizationMod, load_i18n_async
from .i18n.models import ModuleTranslator
from .i18n.translator import naoTimesTranslator
from .music import naoTimesPlayer
from .music.lyrics import naoTimesLyricsClient, naoTimesLyricsConfig
from .redis import RedisBridge
from .sentry import SentryConfig, setup_sentry
from .showtimes import FansubDBBridge, ShowtimesCogsBases, ShowtimesQueue, naoTimesDB
from .socket import EventFunc, EventManager, SocketEvent, SocketServer
from .t import MemberContext
from .timeparse import TimeString
from .utils import read_files
from .version import version_info

__all__ = ("StartupError", "naoTimesBot")


ResourceT = TypeVar("ResourceT")
ContextT = TypeVar("ContextT", bound=commands.Context)


class ErrorLogPayload(TypedDict, total=False):
    content: str
    embed: discord.Embed
    file: discord.File


def _require_initialized(value: ResourceT | None, name: str) -> ResourceT:
    if value is None:
        raise RuntimeError(f"{name} is not initialized")
    return value


def _record_list(value: object, key: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise TypeError(f"Showtimes data field {key!r} must be a list")
    records: list[dict[str, object]] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict) or not all(isinstance(name, str) for name in record):
            raise TypeError(f"Showtimes data field {key!r}[{index}] must be an object with text keys")
        records.append({name: item for name, item in record.items() if isinstance(name, str)})
    return records


class StartupError(Exception):
    def __init__(self, base: Exception) -> None:
        super().__init__()
        self.exception = base


@dataclass
class BotMaintenance:
    start: arrow.Arrow
    end: arrow.Arrow
    ready: bool = False

    def __post_init__(self):
        self.ready = False

    @property
    def maintenance(self):
        ctime = arrow.utcnow()
        return self.start <= ctime <= self.end

    def set(self):
        self.ready = True


class naoTimesBot(commands.Bot):
    """
    naoTimes is Indonesian based bot to help track foreign media
    translation group project.

    This class is the main bot class that should be invoked to run.

    Example usage: ::

        from naotimes.bot import naoTimesBot

        bot = naoTimesBot.create(...)
        bot.run()

    """

    presensi_rate: int | None
    __tree: naoTimesAppTree
    ntdb: naoTimesDB | None
    fsdb: FansubDBBridge | None
    showqueue: ShowtimesQueue | None
    showcogs: ShowtimesCogsBases | None
    anibucket: AnilistBucket | None
    vndb_client: VNDBClient | None
    kbbi: KBBI | None
    redisdb: RedisBridge | None
    jisho: JishoAPI | None
    tesaurus: TesaurusAsync | None
    merriam: MerriamWebsterClient | None
    ihaapi: GraphQLClient | None
    wolfram: WolframAPI | None
    aiosession: aiohttp.ClientSession | None
    ntevent: EventManager | None
    ntplayer: naoTimesPlayer | None
    ntlyrics: naoTimesLyricsClient | None
    _start_time: arrow.Arrow | None
    _log_channel: discord.TextChannel | None
    _owner: discord.User | None
    _is_team_bot: bool
    _team_name: str | None
    _team_members: list[discord.User | discord.TeamMember]
    maintenance: BotMaintenance | None
    _commit_data: dict[str, str | None]
    __i18n_data: I18nDictionary
    ntsocket: SocketServer | None

    def __init__(self, base_path: Path, bot_config: naoTimesBotConfig, *args, **kwargs):
        kwargs.setdefault("tree_cls", naoTimesAppTree)
        super().__init__(*args, **kwargs)

        self.logger: logging.Logger = logging.getLogger("naoTimesBot")
        self.semver: str = version_info.text
        self.config: naoTimesBotConfig = bot_config
        self.fcwd: Path = base_path
        self.presensi_rate = None

        self.jsdb_streams: dict = {}
        self.jsdb_currency: dict = {}
        self.jsdb_crypto: dict = {}
        self.dev_mode: bool = False

        self.ntdb = None
        self.fsdb = None
        self.showqueue = None
        self.showcogs = None
        self.anibucket = None
        self.vndb_client = None
        self.kbbi = None
        self.redisdb = None
        self.jisho = None
        self.tesaurus = None
        self.merriam = None
        self.ihaapi = None
        self.wolfram = None
        self.aiosession = None
        self.ntevent = None
        self.ntplayer = None
        self.ntlyrics = None

        self.showtimes_resync: list[str] = []
        # Commands disabled by the owner: qualified name -> reason
        self.disabled_commands: dict[str, str | None] = {}
        self.grouper = CommandGrouper(self)
        self._use_sentry: bool = False

        self._start_time = None
        # When the class got created, it will be the boot time of the bot.
        self._boot_time: arrow.Arrow = arrow.utcnow()
        self._log_channel = None
        self._owner = None
        self._is_team_bot: bool = False
        self._team_name = None
        self._team_members = []
        self.maintenance = None

        self._ip_hostname = ""
        self._host_country = ""
        self._host_name = ""
        self._host_os = ""
        self._host_dpyver = discord.__version__
        self._host_pyver = ""
        self._host_pid = os.getpid()
        self._host_proc_threads = -1
        self._host_proc = ""
        self._host_arch = ""
        self._host_os_ver = ""
        self._host_region = ""
        self._host_tz = ""

        http_log_path = self.fcwd / "logs" / "http.log"
        http_log_path.parent.mkdir(exist_ok=True)
        http_fh = RollingFileHandler(str(http_log_path), maxBytes=5_242_880, backupCount=5, encoding="utf-8")
        socket_fh = RollingFileHandler(
            str(self.fcwd / "logs" / "socket.log"), maxBytes=5_242_880, backupCount=5, encoding="utf-8"
        )

        http_log_fmt = logging.Formatter(
            "[%(asctime)s] - (%(name)s) [%(levelname)s]: %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        http_fh.setFormatter(http_log_fmt)
        socket_fh.setFormatter(http_log_fmt)

        http_logger = logging.getLogger("naoTimes.HTTPAccess")
        http_logger.handlers = []
        http_logger.addHandler(http_fh)
        http_logger.setLevel(logging.DEBUG)

        socket_logger = logging.getLogger("naoTimes.SocketAccess")
        socket_logger.handlers = []
        socket_logger.addHandler(socket_fh)
        socket_logger.setLevel(logging.DEBUG)

        self.__http_server: naoTimesHTTPServer = naoTimesHTTPServer(
            bot_config.http_server.host,
            bot_config.http_server.port,
            bot_config.http_server.password,
            logger=http_logger,
        )
        self.ntsocket: SocketServer | None = None
        socket_conf = self.config.socket
        if socket_conf is not None and socket_conf.enabled:
            self.ntsocket = SocketServer(
                socket_conf.port,
                socket_conf.password,
                logger=socket_logger,
            )
        else:
            self.logger.info("Socket server is disabled, not starting it.")
        self.__first_time_ready = False
        self.__last_disconnection: arrow.Arrow | None = None
        self.__i18n_data = I18nDictionary()
        self.__cog_watcher: asyncio.Task | None = None

        self._commit_data: dict[str, str | None] = {
            "hash": None,
            "full_hash": None,
            "date": None,
        }
        # Server mappings
        self._i18n_server_mappings: dict[str, str] = {}

    @overload
    async def get_context(self, origin: discord.Message | discord.Interaction, /) -> naoTimesContext: ...

    @overload
    async def get_context(
        self, origin: discord.Message | discord.Interaction, /, *, cls: type[ContextT]
    ) -> ContextT: ...

    async def get_context(
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[commands.Context] = naoTimesContext,
    ) -> commands.Context:
        """Override the method with custom context"""
        return await super().get_context(origin, cls=cls)

    @classmethod
    async def async_create(cls: type[naoTimesBot], base_path: Path, bot_config: naoTimesBotConfig) -> naoTimesBot:
        """
        Asynchronously create a new instance of the bot and returns it.

        You can set the bot on dev mode by setting ``dev_mode`` to ``true`` in the config
        (or by passing the ``-dev`` flag).

        Parameters
        ----------
        base_path: :class:`Path`
            The base path of the bot.
        bot_config: :class:`naoTimesBotConfig`
            The bot configuration.

        Returns
        -------
        :class:`naoTimesBot`
            The bot instance.
        """
        bot_description = "Bot multifungsi tukang suruh Fansub\n"
        bot_description += f"Versi {version_info.text} | Master @noaione"
        IS_DEV = bot_config.dev_mode

        # Slash-command only: no privileged intents (members, presences, message_content).
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.dm_messages = True
        intents.guild_reactions = True
        intents.dm_reactions = True
        intents.voice_states = True
        intents.emojis_and_stickers = True
        intents.moderation = True

        bot = cls(
            base_path,
            bot_config,
            command_prefix=commands.when_mentioned,
            description=bot_description,
            case_insensitive=True,
            max_messages=10_000,
            intents=intents,
            # reload=IS_DEV,
        )
        bot.logger.info(f"Instanting naoTimes with Intents: {intents!r}")

        bot.logger.info("Fetching commit info...")
        commit, _ = await bot.get_commit_info()

        sentry_config = SentryConfig(
            dsn=bot_config.statistics.sentry_dsn,
            git_commit=commit,
            is_dev=IS_DEV,
        )
        bot.logger.info(f"Trying to setup sentry with: {sentry_config}")
        sentry_success = setup_sentry(sentry_config)
        bot._use_sentry = sentry_success
        bot.dev_mode = IS_DEV

        return bot

    @classmethod
    def create(cls: type[naoTimesBot], base_path: Path, bot_config: naoTimesBotConfig) -> naoTimesBot:
        """
        Create a new instance of the bot and returns it.

        You can set the bot on dev mode by setting ``dev_mode`` to ``true`` in the config
        (or by passing the ``-dev`` flag).

        Parameters
        ----------
        base_path: :class:`Path`
            The base path of the bot.
        bot_config: :class:`naoTimesBotConfig`
            The bot configuration.

        Returns
        -------
        :class:`naoTimesBot`
            The bot instance.
        """
        loop = asyncio.get_event_loop()

        bot_description = "Bot multifungsi tukang suruh Fansub\n"
        bot_description += f"Versi {version_info.text} | Master @noaione"
        IS_DEV = bot_config.dev_mode

        # Slash-command only: no privileged intents (members, presences, message_content).
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.dm_messages = True
        intents.guild_reactions = True
        intents.dm_reactions = True
        intents.voice_states = True
        intents.emojis_and_stickers = True
        intents.moderation = True

        bot = cls(
            base_path,
            bot_config,
            command_prefix=commands.when_mentioned,
            description=bot_description,
            case_insensitive=True,
            max_messages=10_000,
            loop=loop,
            intents=intents,
            # reload=IS_DEV,
        )
        bot.logger.info(f"Instanting naoTimes with Intents: {intents!r}")

        bot.logger.info("Fetching commit info...")
        commit, _ = loop.run_until_complete(bot.get_commit_info())

        sentry_config = SentryConfig(
            dsn=bot_config.statistics.sentry_dsn,
            git_commit=commit,
            is_dev=IS_DEV,
        )
        bot.logger.info(f"Trying to setup sentry with: {sentry_config}")
        sentry_success = setup_sentry(sentry_config)
        bot._use_sentry = sentry_success
        bot.dev_mode = IS_DEV

        return bot

    @property
    def http_server(self) -> naoTimesHTTPServer:
        return self.__http_server

    @property
    def i18n_bot(self) -> I18nDictionary:
        return self.__i18n_data

    def _get_startup_config(self) -> naoTimesArgParse:
        return _require_initialized(self.config.init_config, "Parsed startup configuration")

    def get_i18n(self, server_id: str):
        srv_map = self._i18n_server_mappings.get(server_id)
        if srv_map is None:
            return self.__i18n_data.getdefault()
        return self.__i18n_data.get(srv_map)

    async def set_i18n(self, server_id: str, language: str | None = None):
        redisdb = _require_initialized(self.redisdb, "Redis bridge")
        if language is None:
            self._i18n_server_mappings.pop(server_id, None)
            try:
                await redisdb.rm("nti18n:%s" % server_id)
            except Exception:
                pass
            return
        self._i18n_server_mappings[server_id] = language
        await redisdb.set("nti18n:%s" % server_id, language)

    @overload
    def i18n_for(self, guild: discord.Guild | int | str | None = None, module: None = None) -> InternalizationMod: ...

    @overload
    def i18n_for(self, guild: discord.Guild | int | str | None, module: str) -> ModuleTranslator: ...

    def i18n_for(
        self, guild: discord.Guild | int | str | None = None, module: str | None = None
    ) -> InternalizationMod | ModuleTranslator:
        """Return the translation set for a guild, optionally bound to one module."""
        server_id: str | None = None
        if guild is not None:
            server_id = str(getattr(guild, "id", guild))
        mod = self.get_i18n(server_id) if server_id is not None else self.__i18n_data.getdefault()
        if module is not None:
            return ModuleTranslator(mod, module)
        return mod

    def now(self) -> arrow.Arrow:
        """:class:`arrow.Arrow`: Get current UTC time"""
        return arrow.utcnow()

    def get_uptime(self, detailed: bool = False, locale: str = "id"):
        """Get bot uptime in relative format.

        Parameters
        ----------
        detailed: :class:`bool`
            If ``True``, return a detailed uptime.
            Example: ``2 menit 30 detik``.
        """
        if self._start_time is None:
            return "baru saja" if locale != "en" else "just now"
        time_ago = self._start_time.humanize(self.now(), locale)
        if detailed:
            ts = TimeString.from_seconds((self.now() - self._start_time).total_seconds())
            return ts.to_string(locale)
        return time_ago

    async def save_config(self):
        """Save the bot configuration to disk"""
        await self.config.save(self.fcwd / "config.json")

    def set_maintenance(self, start: arrow.Arrow, end: arrow.Arrow):
        self.maintenance = BotMaintenance(start, end)

    async def _init_kbbi(self, config: naoTimesKBBIConfig | None):
        self.logger.info("Initializing KBBI...")
        if config is None:
            return KBBI()
        if not config.email or not config.password:
            return KBBI()

        current_dt = self.now().timestamp()
        self.logger.info("Checking authentication information to redis...")
        redisdb = _require_initialized(self.redisdb, "Redis bridge")
        kbbi_auth_f = await redisdb.get("ntconfig_kbbiauth")

        kbbi_cls = KBBI()
        kbbi_cls.set_autentikasi(config.email, config.password)

        try:
            if not kbbi_auth_f:
                self.logger.info("Authenticating with KBBI...")
                kbbi_auth = AutentikasiKBBI(config.email, config.password)
                await kbbi_auth.autentikasi()
                cookie_baru = await kbbi_auth.ambil_cookies()
                kbbi_cls.set_autentikasi(cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60)))
            else:
                if current_dt >= kbbi_auth_f["expires"]:
                    self.logger.warning("KBBI cookie expired, generating new cookie 🍪!")
                    kbbi_auth = AutentikasiKBBI(config.email, config.password)
                    await kbbi_auth.autentikasi()
                    cookie_baru = await kbbi_auth.ambil_cookies()
                    kbbi_cls.set_autentikasi(cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60)))
                else:
                    self.logger.info("Using saved cookie 🍪!")
                    kbbi_cls.set_autentikasi(cookie=kbbi_auth_f["cookie"], expiry=kbbi_auth_f["expires"])
                    await kbbi_cls.reset_connection()
                    self.logger.info("Checking authentication...")
                    is_kbbi_auth = await kbbi_cls.cek_auth()
                    if not is_kbbi_auth:
                        self.logger.warning("KBBI cookie expired, generating new cookie 🍪!")
                        kbbi_auth = AutentikasiKBBI(config.email, config.password)
                        await kbbi_auth.autentikasi()
                        cookie_baru = await kbbi_auth.ambil_cookies()
                        kbbi_cls.set_autentikasi(cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60)))
            self.logger.info("KBBI auth restored, resetting connection...")
        except Exception as exc:  # skipcq: PYL-W0703
            self.logger.error(
                "Failed to authenticate, probably server down or something, ignoring for now...", exc_info=exc
            )

        await kbbi_cls.reset_connection()
        await redisdb.set("ntconfig_kbbiauth", kbbi_cls.get_cookies)
        return kbbi_cls

    async def _init_fsdb(self, config: naoTimesUserPassConfig | None):
        if config is None:
            return False, None
        if not config.username or not config.password:
            return False, None

        current_dt = self.now().timestamp()
        self.logger.info("Checking authentication information to redis...")
        redisdb = _require_initialized(self.redisdb, "Redis bridge")
        session = _require_initialized(self.aiosession, "HTTP session")
        fsdb_token = await redisdb.get("ntconfig_fsdbtoken")
        self.logger.info("Preparing FSDB connection...")
        fsdb_bridge = FansubDBBridge(config.username, config.password, session, self.loop)
        if not fsdb_token:
            self.logger.info("FSDB token not found, generating new token...")
            try:
                await asyncio.wait_for(fsdb_bridge.authorize(), timeout=10.0)
            except TimeoutError:
                self.logger.warning("Failed to generate new token, disabling...")
                return False, None
            fsdb_token = fsdb_bridge.token_data
        elif fsdb_token["expires"] is not None and current_dt - 300 >= fsdb_token["expires"]:
            self.logger.info("FSDB token expired, generating new token...")
            try:
                await asyncio.wait_for(fsdb_bridge.authorize(), timeout=10.0)
            except TimeoutError:
                self.logger.warning("Failed to generate new token, disabling...")
                return False, None
            fsdb_token = fsdb_bridge.token_data
        else:
            self.logger.info("Using saved token...")
            fsdb_bridge.set_token(fsdb_token["token"], fsdb_token["expires"])
        await redisdb.set("ntconfig_fsdbtoken", fsdb_token)
        return True, fsdb_bridge

    async def _init_vndb(self, config: naoTimesVNDBConfig | None) -> VNDBClient:
        session = _require_initialized(self.aiosession, "HTTP session")
        self.logger.info("Initializing VNDB Kana API client...")
        return VNDBClient(session, config.token if config else None)

    async def _init_history_data(self) -> None:
        """|coro|

        Populate the bot data with attributes and data like IP/Country
        """
        self.logger.info("Getting bot hardware info...")
        platform_info = platform.uname()
        self._host_os = platform_info.system
        self._host_os_ver = platform_info.release
        self._host_name = platform_info.node
        self._host_arch = platform_info.machine

        self._host_proc = platform_info.processor
        self._host_proc_threads = os.cpu_count()
        self._host_pid = os.getpid()

        py_ver = platform.python_version()
        py_impl = platform.python_implementation()
        py_compiler = platform.python_compiler()
        self._host_pyver = f"{py_ver} ({py_impl}) [{py_compiler}]"
        self._host_dpyver = discord.__version__

        self.logger.info("getting bot connection info...")
        session = _require_initialized(self.aiosession, "HTTP session")
        async with session.get("https://ipinfo.io/json") as resp:
            conn_data = await resp.json()

        country = conn_data["country"]
        region = conn_data["region"]
        timezone = conn_data["timezone"]
        ip_hostname = conn_data["ip"]

        self._ip_hostname = ip_hostname
        self._host_country = country
        self._host_region = region
        self._host_tz = timezone

        self.logger.info("getting commit info...")
        commit, commit_date = await self.get_commit_info()
        self._commit_data["hash"] = commit[:7] if commit is not None else None
        self._commit_data["full_hash"] = commit
        self._commit_data["date"] = commit_date

    @property
    def commits(self) -> dict:
        """Return the commit data if git is used.
        Returns
        -------
        Commit data: `dict`:
            A collection of dictionary that the 7 hash commit and the time of the commit
        """
        return self._commit_data

    async def get_commit_info(self) -> tuple[str | None, str | None]:
        cmd = r'cd "{{fd}}" && git log --format="%H" -n 1 && git show -s --format=%ci'
        cmd = cmd.replace(r"{{fd}}", str(self.fcwd))
        self.logger.info("Executing: " + cmd)
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stdout = stdout.decode().rstrip()
        stderr = stderr.decode().rstrip()
        if not stdout:
            return None, None
        commit, date = stdout.split("\n")
        return commit, date

    async def initialize(self):
        """|coro|

        Initialize the bot
        """
        self.logger.info("Initializing bot...")
        startup_config = self._get_startup_config()
        session = _require_initialized(self.aiosession, "HTTP session")

        self.logger.info("Fetching i18n data...")
        i18n_data = await load_i18n_async(self.loop, default_language=self.config.i18n.default_language)
        self.__i18n_data = i18n_data
        self.logger.info(f"Loaded {len(i18n_data)} languages for i18n: {', '.join(i18n_data.languages)}")
        await self.tree.set_translator(naoTimesTranslator(i18n_data))

        self.logger.info("Reading all jsdb data...")
        self.jsdb_crypto = await read_files(str(self.fcwd / "cryptodata.json"))
        self.jsdb_currency = await read_files(str(self.fcwd / "currencydata.json"))
        self.jsdb_streams = await read_files(str(self.fcwd / "streaming_lists.json"))

        self.logger.info("Connecting to RedisDB...")
        redis_conf = self.config.redisdb
        redis_conn = RedisBridge(
            redis_conf.ip_hostname, redis_conf.port, redis_conf.password, self.loop, db=redis_conf.db
        )
        await redis_conn.connect()
        await redis_conn.client.get("pingpong")
        self.redisdb = redis_conn

        self.logger.info("Fetching i18n server data...")
        i18n_server_data = await redis_conn.getalldict("nti18n:*")
        for server, language in i18n_server_data.items():
            server = server.replace("nti18n:", "", 1)
            self._i18n_server_mappings[server] = language

        self.logger.info("Initializing FansubDB Bridge...")
        use_fsdb, fsdb_bridge = await self._init_fsdb(self.config.fansubdb)
        if use_fsdb:
            self.fsdb = fsdb_bridge
        self.logger.info("Initializing VNDB API client...")
        self.vndb_client = await self._init_vndb(self.config.vndb)

        self.logger.info("Initializing KBBI...")
        if startup_config.kbbi_check:
            self.kbbi = await self._init_kbbi(self.config.kbbi)
        else:
            self.kbbi = KBBI()
        self.logger.info("Binding TesaurusAysnc...")
        self.tesaurus = TesaurusAsync(session, self.loop)
        wolfram_conf = self.config.wolfram
        if wolfram_conf is not None:
            wolfram_app_id = wolfram_conf.appid
            if isinstance(wolfram_app_id, str):
                self.logger.info("Binding WolframAlpha...")
                self.wolfram = WolframAPI(wolfram_app_id)

        self.logger.info("Binding Event manager...")
        self.ntevent = EventManager(self.loop)

        mongos = self.config.mongodb
        self.logger.info("Initializing MongoDB/ShowtimesDB connection...")
        ntdb = naoTimesDB(
            mongos.ip_hostname,
            mongos.port,
            mongos.dbname,
            mongos.auth,
            mongos.tls if mongos.tls is not None else False,
            self.dev_mode,
        )
        self.ntdb = ntdb
        try:
            self.logger.info(f"Trying to connect to: {ntdb.url}")
            await ntdb.validate_connection()
            self.logger.info("Connected to Database:")
            self.logger.info(f"Connection URL: {ntdb.url}")
            self.logger.info(f"Database Name: {ntdb.dbname}")
            if startup_config.showtimes_fetch:
                self.logger.info("Fetching server showtimes data to local database/memory...")
                raw_showtimes_data: object = await ntdb.fetch_all_as_json()
                if not isinstance(raw_showtimes_data, dict) or not all(
                    isinstance(key, str) for key in raw_showtimes_data
                ):
                    raise TypeError("Showtimes export must be an object with text keys")
                showtimes_data = {key: value for key, value in raw_showtimes_data.items() if isinstance(key, str)}
                supermods = _record_list(showtimes_data.get("supermod"), "supermod")
                servers = _record_list(showtimes_data.get("servers"), "servers")
                await redis_conn.bulkrm("showtimes_*")
                await redis_conn.bulkrm("showadmin_*")
                for admins in supermods:
                    admin_id = admins.get("id")
                    if admin_id is None:
                        raise ValueError("Showtimes administrator record is missing an id")
                    await redis_conn.set(f"showadmin_{admin_id}", admins)
                for server in servers:
                    server_id = server.get("id")
                    if server_id is None:
                        raise ValueError("Showtimes server record is missing an id")
                    await redis_conn.set(f"showtimes_{server_id}", server)
                self.logger.info(f"Stored {len(supermods)} admins to redis memcache")
                self.logger.info(f"Stored {len(servers)} servers to redis memcache")
        except Exception as exc:  # skipcq: PYL-W0703
            self.logger.error("Failed to validate if database is up and running.")
            self.logger.error(f"IP:Port: {mongos.ip_hostname}:{mongos.port}")
            raise StartupError(exc)

        mwapi_conf = self.config.merriam_webster
        if mwapi_conf is not None and (mwapi_conf.dictionary or mwapi_conf.thesaurus):
            self.logger.info("Binding MerriamWebster client...")
            api_keys: dict[str, str | None] = {
                "words": mwapi_conf.dictionary,
                "thesaurus": mwapi_conf.thesaurus,
            }
            # The client uses None to disable either endpoint, though its annotation is narrower.
            self.merriam = MerriamWebsterClient(cast(dict[str, str], api_keys))

        await self._init_history_data()

        self.logger.info("Preparing music player...")
        music_conf = self.config.music
        try:
            self.ntplayer = naoTimesPlayer(self, self.loop, music_conf.spotify if music_conf else None)
        except Exception:
            self.logger.exception("Failed to initialize music player.")

        if music_conf:
            mxm_api_key = None
            if music_conf.musixmatch is not None:
                mxm_api_key = music_conf.musixmatch.api_key
            genius_id = None
            genius_secret = None
            if music_conf.genius:
                genius_id = music_conf.genius.client_id
                genius_secret = music_conf.genius.client_secret
            self.logger.info("Binding naoTimes Lyrics...")
            config = naoTimesLyricsConfig(mxm_api_key, genius_id, genius_secret)
            ntlyrics = naoTimesLyricsClient(config, session)
            genius_token = None
            genius_token_fetch = await redis_conn.get("ntplayer_genius")
            if genius_token_fetch is not None:
                genius_token = genius_token_fetch["token"]
            await ntlyrics.initialize(genius_token)
            await redis_conn.set("ntplayer_genius", {"token": genius_token, "expiry": None})
            self.ntlyrics = ntlyrics

        self.logger.info("Binding Jisho connection...")
        self.jisho = JishoAPI(session)
        self.logger.info("Binding ShowtimesQueue...")
        self.showqueue = ShowtimesQueue(redis_conn)
        self.logger.info("Binding AnilistBucket...")
        self.anibucket = AnilistBucket(session)
        self.logger.info("Binding Showtimes Base Cogs stuff")
        self.showcogs = ShowtimesCogsBases(self.anibucket)
        self.logger.info("Binding ihateani.me API")
        self.ihaapi = GraphQLClient("https://api.ihateani.me/v2/graphql", session)

        self.logger.info("Preparing hot-module reloader")
        # self._hot_reloader = CogWatcher(self, self.loop)

    async def setup_hook(self) -> None:
        """Setup bot essential stuff, will be called after bot is logged in."""
        self.aiosession = aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{version_info.shorthand} (https://github.com/naoTimesdev/naoTimes)"},
            loop=self.loop,
            # connector=self._connector,
        )
        await self.initialize()
        await self.load_extensions()

        if self._get_startup_config().slash_check:
            test_guild_id = self.config.slash_test_guild
            if self.dev_mode and test_guild_id is not None:
                test_guild = discord.Object(id=test_guild_id)
                self.tree.copy_global_to(guild=test_guild)
                self.logger.info("Synchronizing application commands to test guild %s...", test_guild_id)
                await self.tree.sync(guild=test_guild)
            else:
                self.logger.info("Synchronizing application commands globally...")
                await self.tree.sync()
            self.logger.info("Triggered synchronization, this might take a while...")

        if self.dev_mode:
            task = asyncio.create_task(
                self._cog_watchdog(), name="naotimes-cog-watcher-" + str(self.now().int_timestamp)
            )
            self.__cog_watcher = task

    async def close(self) -> None:
        """Close discord connection and all other stuff that I opened!"""
        # if hasattr(self, "_hot_reloader"):
        #     self._hot_reloader.close()

        for ext in list(self.extensions):
            with suppress(Exception):
                await self.unload_extension(ext)

        for cog in list(self.cogs):
            with suppress(Exception):
                await self.remove_cog(cog)

        await super().close()

        if self.showqueue:
            self.logger.info("Closing the ShowtimesQueue...")
            await self.showqueue.shutdown()
        if self.fsdb:
            self.logger.info("Closing FansubDB connection...")
            await self.fsdb.close()
        if self.kbbi:
            self.logger.info("Closing KBBI connection...")
            await self.kbbi.tutup()
        if self.jisho:
            self.logger.info("Closing Jisho connection...")
            await self.jisho.close()
        if self.tesaurus:
            self.logger.info("Closing Tesaurus connection...")
            await self.tesaurus.tutup()
        if self.anibucket:
            self.logger.info("Closing anibucket session...")
            await self.anibucket.close()
        if self.ihaapi:
            self.logger.info("Closing ihaAPI session...")
            await self.ihaapi.close()
        if self.wolfram:
            self.logger.info("Closing WolframAlpha connection...")
            await self.wolfram.close()
        if self.ntsocket:
            self.logger.info("Closing socket server...")
            self.ntsocket.close()
        if self.ntevent:
            self.logger.info("Closing event manager...")
            await self.ntevent.close()
        if self.ntlyrics:
            self.logger.info("Closing lyrics client...")
            await self.ntlyrics.close()
        if self.ntplayer:
            self.logger.info("Closing music player...")
            await self.ntplayer.close()

        self.logger.info("Closing HTTP server...")
        await self.__http_server.close()

        if self.aiosession:
            self.logger.info("Closing aiohttp Session...")
            await self.aiosession.close()

        if self.redisdb:
            self.logger.info("Shutting down redis connection...")
            await self.redisdb.close()
        if self.__cog_watcher:
            self.logger.info("Closing cog watcher...")
            self.__cog_watcher.cancel()
            await self.__cog_watcher

    async def on_resumed(self):
        """|coro|

        Happens when the client is resumed, usually happen if disconnection happened.
        """
        delta_time = None
        if self.__last_disconnection is not None:
            delta_time_real = arrow.utcnow() - self.__last_disconnection
            delta_time = delta_time_real.total_seconds()
        self.__last_disconnection = None
        if delta_time is not None:
            self.logger.info(f"Discord connection resumed after {delta_time} seconds.")
        else:
            self.logger.info("Discord connection was resumed, connection died for unknown reason.")

    async def on_ready(self):
        """|coro|

        Called when the bot is ready.
        """
        if self.__first_time_ready:
            delta_time = None
            if self.__last_disconnection is not None:
                delta_time_real = arrow.utcnow() - self.__last_disconnection
                delta_time = delta_time_real.total_seconds()
            self.logger.info("Bot gateway connection lost for a moment, now we're ready again")
            if delta_time is not None:
                self.logger.info(f"It took {delta_time} seconds to reconnect")
            self.__last_disconnection = None
            return
        self.logger.info("Connected to Discord!")
        await self.change_presence(activity=discord.Game(name="Halo Dunia! | /help", type=3))
        self.logger.info("Dispatching start event for HTTP server...")
        await self.__http_server.start()
        self.logger.info("Checking bot team status...")
        await self.detect_teams_bot()
        owner = _require_initialized(self._owner, "Bot owner")
        self._start_time = self.now()
        if isinstance(self.config.log_channel, int):
            channel_data = self.get_channel(self.config.log_channel)
            if isinstance(channel_data, discord.TextChannel):
                self._log_channel = channel_data

        music_conf = self.config.music
        if music_conf:
            self.logger.info(f"Connecting with Lavalink nodes ({len(music_conf.nodes)} nodes)")
            player = _require_initialized(self.ntplayer, "Music player")
            for node in music_conf.nodes:
                await player.add_node(node)
        self.logger.info("---------------------------------------------------------------")
        self.logger.info("Bot Ready!")
        self.logger.info(f"Using Python {sys.version}")
        self.logger.info(f"Using Discord v{discord.__version__}")
        self.logger.info("---------------------------------------------------------------")
        self.logger.info("Bot Info:")
        current_user = _require_initialized(self.user, "Discord user")
        self.logger.info(f"Username: {current_user.name}")
        if self._is_team_bot:
            self.logger.info(f"Owner: {self._team_name}")
        else:
            self.logger.info(f"Owner: {owner.name}#{owner.discriminator}")
        if self._is_team_bot and len(self._team_members) > 0:
            member_set = [f"{owner.name}#{owner.discriminator}"]
            member_set.extend([f"{user.name}#{user.discriminator}" for user in self._team_members])
            parsed_member = ", ".join(member_set)
            self.logger.info(f"With team members: {parsed_member}")
        self.logger.info(f"Client ID: {current_user.id}")
        self.logger.info(f"Running naoTimes version: {self.semver}")
        commit_info = self._commit_data
        if commit_info["hash"] is not None:
            self.logger.info(f"With commit hash: {commit_info['full_hash']} ({commit_info['date']})")
        self.logger.info("---------------------------------------------------------------")
        # Send ready message to owner DM
        boot_delta = (self.now() - self._boot_time).total_seconds()
        self.logger.info(f"Bot Booted in {boot_delta} seconds")
        self.logger.info("---------------------------------------------------------------")
        self.__first_time_ready = True
        dm_channel = owner.dm_channel
        if dm_channel is None:
            dm_channel = await owner.create_dm()
        boot_message = "🟥🟨🟩🟦 naoTimes 🟦🟩🟨🟥"
        boot_message += f"\nVersi: **{self.semver}**"
        boot_message += f"\nDurasi boot up: {boot_delta} detik"
        boot_message += "\n\nnaoTimes sekarang siap melayani!"
        boot_message += "\n<https://naoti.me>"
        await dm_channel.send(content=boot_message)

    async def on_disconnect(self):
        """|coro|

        Called when the bot disconnects from Discord.
        """
        self.logger.info("Bot got disconnected from Discord gateway, we're trying to reconnect...")
        self.__last_disconnection = self.now()

    async def load_extension(self, name: str, *, package: str | None = None):
        self.logger.info(f"Loading module: {name}")
        await super().load_extension(name, package=package)
        self.logger.info(f"{name} module is now loaded!")

    async def unload_extension(self, name: str, *, package: str | None = None) -> None:
        self.logger.info(f"Unloading module: {name}")
        await super().unload_extension(name, package=package)
        self.logger.info(f"{name} module is now unloaded!")

    def _fetch_cog_function(self, cog: commands.Cog) -> list[T.Callable[..., T.Any]]:
        default_functions = set(dir(commands.Cog))
        functions: list[T.Callable[..., T.Any]] = []
        for name in dir(cog):
            if name in default_functions or name.startswith(("cog_", "__cog_")):
                continue
            if isinstance(inspect.getattr_static(cog, name), property):
                continue
            callback = getattr(cog, name)
            if callable(callback):
                functions.append(callback)
        return functions

    def _inject_ntsocketevent(self, cog: commands.Cog):
        all_functions = self._fetch_cog_function(cog)
        for func in all_functions:
            socket_cmd = getattr(func, "__nt_socket__", None)
            event_cmd = getattr(func, "__nt_event__", None)
            web_server_route = getattr(func, "__nt_webserver_route__", None)
            if socket_cmd is not None and self.ntsocket is not None:
                if isinstance(socket_cmd, list):
                    for cmd in socket_cmd:
                        if not cmd["installed"]:
                            self.logger.debug(f"Registering {cmd['name']} into SocketServer")
                            socket_cb = SocketEvent(func, cmd["locked"])
                            self.ntsocket.on(cmd["name"], socket_cb)
                elif isinstance(socket_cmd, dict) and not socket_cmd["installed"]:
                    self.logger.debug(f"Registering {socket_cmd['name']} into SocketServer")
                    socket_cb = SocketEvent(func, socket_cmd["locked"])
                    self.ntsocket.on(socket_cmd["name"], socket_cb)
            if event_cmd is not None:
                event_manager = _require_initialized(self.ntevent, "Event manager")
                if isinstance(event_cmd, list):
                    for cmd in event_cmd:
                        if not cmd["installed"]:
                            self.logger.debug(f"Registering {cmd['name']} into EventManager")
                            event_manager.on(cmd["name"], cast(EventFunc, func))
                elif isinstance(event_cmd, dict) and not event_cmd["installed"]:
                    self.logger.debug(f"Registering {event_cmd['name']} into EventManager")
                    event_manager.on(event_cmd["name"], cast(EventFunc, func))
            if isinstance(web_server_route, RouteDef):
                web_server_route.bind_cog(cog)
                self.__http_server.add_route(web_server_route)

    def _uninject_ntsocketevent(self, cog: commands.Cog):
        all_functions = self._fetch_cog_function(cog)
        for func in all_functions:
            socket_cmd = getattr(func, "__nt_socket__", None)
            event_cmd = getattr(func, "__nt_event__", None)
            if socket_cmd is not None and self.ntsocket is not None:
                if isinstance(socket_cmd, list):
                    for cmd in socket_cmd:
                        if cmd["installed"]:
                            self.logger.debug(f"Removing {cmd['name']} from SocketServer")
                            self.ntsocket.off(cmd["name"])
                elif isinstance(socket_cmd, dict) and socket_cmd["installed"]:
                    self.logger.debug(f"Removing {socket_cmd['name']} from SocketServer")
                    self.ntsocket.off(socket_cmd["name"])
            if event_cmd is not None:
                event_manager = _require_initialized(self.ntevent, "Event manager")
                if isinstance(event_cmd, list):
                    for cmd in event_cmd:
                        if cmd["installed"]:
                            self.logger.debug(f"Removing {cmd['name']} from EventManager")
                            event_manager.off(cmd["name"])
                elif isinstance(event_cmd, dict) and event_cmd["installed"]:
                    self.logger.debug(f"Removing {event_cmd['name']} from EventManager")
                    event_manager.off(event_cmd["name"])

    async def add_cog(
        self,
        cog: commands.Cog,
        /,
        *,
        override: bool = False,
        guild: discord.abc.Snowflake | None = discord.utils.MISSING,
        guilds: Sequence[discord.abc.Snowflake] = discord.utils.MISSING,
    ) -> None:
        await super().add_cog(cog, override=override, guild=guild, guilds=guilds)
        injected_cog = self.get_cog(cog.__cog_name__)
        if injected_cog is not None:
            self._inject_ntsocketevent(injected_cog)
            self.grouper.apply(injected_cog)

    async def remove_cog(
        self,
        name: str,
        /,
        *,
        guild: discord.abc.Snowflake | None = discord.utils.MISSING,
        guilds: Sequence[discord.abc.Snowflake] = discord.utils.MISSING,
    ) -> commands.Cog | None:
        cog = self.get_cog(name)
        if cog is not None:
            self._uninject_ntsocketevent(cog)
            self.grouper.release(cog)
        return await super().remove_cog(name, guild=guild, guilds=guilds)

    # Cache for 10 minutes
    @alru_cache(typed=False)
    async def available_extensions(self):
        ALL_EXTENSIONS = []
        IGNORED_FILES = ["__init__", "__main__"]

        # See cogs folder
        cogs_folder = self.fcwd / "cogs"
        async for cogs_file in AsyncPath(cogs_folder).rglob("*.py"):
            if cogs_file.stem.lower() in IGNORED_FILES:
                continue

            # Get the cog path
            # ex: cogs/xxxx/a.py
            #     cogs/b.py

            cog_parts = list(cogs_file.relative_to(cogs_folder.parent).parts)
            # Remove .py from the last part
            cog_parts[-1] = Path(cog_parts[-1]).stem
            cog_path = ".".join(cog_parts)
            ALL_EXTENSIONS.append(cog_path)
        ALL_EXTENSIONS.sort()
        return ALL_EXTENSIONS

    async def load_extensions(self):
        """Load all extensions"""
        ALL_EXTENSIONS = await self.available_extensions()
        startup_config = self._get_startup_config()

        for extension in ALL_EXTENSIONS:
            if extension in startup_config.cogs_skip:
                self.logger.info(f"Skipping {extension}...")
                continue
            try:
                await self.load_extension(extension)
            except commands.ExtensionError as enoff:
                self.logger.error(f"Failed to load {extension}")
                self.echo_error(enoff)

    def echo_error(self, error: Exception, debug_mode: bool = False):
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        if not debug_mode:
            self.logger.error("Exception occured\n" + "".join(tb))
        else:
            self.logger.debug("Exception occured\n" + "".join(tb))

    async def on_error(self, event: str, *args, **kwargs):
        """Log errors raised in event listeners rather than printing them to stderr."""

        if self._use_sentry:
            try:
                from sentry_sdk import push_scope
            except ImportError:
                self.logger.exception(f"Unhandled event exception in {event}.")
                return
            with push_scope() as scope:
                scope.set_tag("event", event)
                scope.set_extra("event_args", args)
                scope.set_extra("event_kwargs", kwargs)

                self.logger.exception(f"Unhandled event exception in {event}.")
            return
        self.logger.exception(f"Unhandled event exception in {event}.")

    @staticmethod
    def is_mentionable(guild: discord.Guild | None, user: MemberContext) -> str:
        """Format a user as a mention if they are in the guild, otherwise as plain text."""
        if guild is None or guild.get_member(user.id) is None:
            return str(user)
        return user.mention

    def teams_to_user(self, user_data: discord.TeamMember) -> discord.User | discord.TeamMember:
        member_data = self.get_user(user_data.id)
        if member_data is None:
            return user_data
        return member_data

    async def send_error_log(
        self,
        message: str | None = None,
        embed: discord.Embed | None = None,
        file: discord.File | None = None,
    ) -> None:
        """|coro|

        Send an error log to bot owner or the set channel.

        Parameters
        ----------
        message : str, optional
            The error message to send, by default None
        embed : discord.Embed, optional
            A formatted Discord Embed to send, by default None
        """
        content_to_send: ErrorLogPayload = {}
        if isinstance(message, str) and len(message.strip()) > 0:
            content_to_send["content"] = message
        if isinstance(embed, discord.Embed):
            content_to_send["embed"] = embed
        if isinstance(file, discord.File):
            content_to_send["file"] = file
        if self._log_channel is not None:
            await self._log_channel.send(**content_to_send)
            return
        owner = self._owner
        if owner is None:
            self.logger.warning("Cannot send error log before the bot owner has been resolved.")
            return
        await owner.send(**content_to_send)

    async def detect_teams_bot(self):
        """|coro|

        Detect if the bot is a team bot and get the team name and members
        """
        app_info: discord.AppInfo = await self.application_info()
        team_data = app_info.team
        if team_data is None:
            self._owner = app_info.owner
        else:
            main_owner = team_data.owner
            if main_owner is None:
                raise RuntimeError("Discord team has no owner")

            owner = self.get_user(main_owner.id)
            if owner is None:
                owner = await self.fetch_user(main_owner.id)
            self._owner = owner
            self._team_name = team_data.name
            self._is_team_bot = True
            for member in team_data.members:
                if member.id == main_owner.id:
                    continue
                self._team_members.append(self.teams_to_user(member))

    # Some HTTP helper
    async def ping_website(self, web_url: str) -> tuple[bool, float]:
        """|coro|

        Ping a website
        """

        async def _internal_pinger(sesi: aiohttp.ClientSession, url: str):
            """Internal worker for the ping process."""
            try:
                async with sesi.head(url) as resp:
                    await resp.text()
            except aiohttp.ClientError:
                return False
            return True

        t1 = self.now().timestamp()
        try:
            # Wrap it around asyncio.wait_for to make sure it doesn't wait until 10+ secs
            session = _require_initialized(self.aiosession, "HTTP session")
            res = await asyncio.wait_for(_internal_pinger(session, web_url), timeout=10.0)
            t2 = self.now().timestamp()
            return res, (t2 - t1) * 1000
        except TimeoutError:
            return False, 99999.0

    async def send_ihateanime(
        self, text_data: str, filename_prefix: str | None = None, retention_date: str | None = None
    ):
        """|coro|

        Upload a text data to ihaCDN
        """
        timestamp = str(self.now().timestamp())
        real_filename = "naoTimes_"
        if filename_prefix is not None:
            real_filename = filename_prefix
        real_filename += timestamp + ".py"

        form_data = aiohttp.FormData()
        form_data.add_field(
            name="file", value=text_data.encode("utf-8"), content_type="text/x-python", filename=real_filename
        )
        params = {}
        if retention_date is not None:
            params["retention"] = retention_date
        session = _require_initialized(self.aiosession, "HTTP session")
        async with session.post("https://p.ihateani.me/upload", data=form_data, params=params) as resp:
            res = await resp.text()
            if resp.status == 200:
                return res, None
            else:
                return None, res

    # Command toggling
    def toggle_command(self, command_name: str, reason: str | None = None) -> tuple[bool, str]:
        """Toggle a (slash) command to be enabled or disabled.

        Returns a tuple of (success, message).
        """
        command_name = command_name.strip().lstrip("/").lower()
        if command_name == "owner" or command_name.startswith("owner "):
            return False, "Tidak bisa menonaktifkan perintah tersebut karena dibutuhkan!"

        if command_name in self.disabled_commands:
            del self.disabled_commands[command_name]
            self.logger.info(f"{command_name}: command re-enabled")
            return True, f"Perintah `/{command_name}` berhasil diaktifkan kembali!"

        known = {c.qualified_name for c in self.tree.walk_commands()}
        root_names = {name.split(" ")[0] for name in known}
        if command_name not in known and command_name not in root_names:
            self.logger.warning(f"{command_name}: Command not found")
            return False, "Tidak dapat menemukan command tersebut."

        self.disabled_commands[command_name] = reason or None
        self.logger.info(f"{command_name}: command disabled")
        return True, f"Perintah `/{command_name}` berhasil dinonaktifkan!"

    # Watchdog
    async def _cog_watchdog(self):
        await self.wait_until_ready()

        last = self.now()
        self.logger.info("WATCHDOG: Starting watchdog...")
        while not self.is_closed():
            ct = self.now()

            extensions = set()
            for name, module in self.extensions.items():
                file = module.__file__
                if file and (await AsyncPath(file).stat()).st_mtime > last.float_timestamp:
                    extensions.add(name)

            for name in extensions:
                try:
                    await self.reload_extension(name)
                except commands.errors.ExtensionError as ee:
                    self.logger.error(f"WATCHDOG: Failed to reload {name}", exc_info=ee)
                else:
                    self.logger.info(f"WATCHDOG: Reloaded {name}")

            await asyncio.sleep(1)
            last = ct
