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

import asyncio
import logging
import os
import platform
import sys
import traceback
import typing as T
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import aiohttp
import arrow
import disnake
from disnake.ext import commands
from tesaurus import TesaurusAsync

from naotimes.log import RollingFileHandler

try:
    from sentry_sdk import push_scope
except ImportError:
    pass

from wavelink.ext.spotify import SpotifyClient as WVSpotifyClient

from .card import AvailableCardGen, CardGenerator
from .config import (
    naoTimesBotConfig,
    naoTimesKBBIConfig,
    naoTimesMerriamWebsterConfig,
    naoTimesUserPassConfig,
)
from .context import naoTimesContext
from .helpgenerator import HelpGenerator
from .http import (
    KBBI,
    AnilistBucket,
    AutentikasiKBBI,
    CrowbarClient,
    GraphQLClient,
    JishoAPI,
    MerriamWebsterClient,
    VNDBSockIOManager,
    WolframAPI,
)
from .http.server import Route as RouteDef
from .http.server import naoTimesHTTPServer
from .modlog import ModLog, ModLogFeature, ModLogSetting
from .music import GeniusAPI, naoTimesPlayer
from .placeholder import PlaceHolderCommand
from .redis import RedisBridge
from .sentry import SentryConfig, setup_sentry
from .showtimes import FansubDBBridge, ShowtimesCogsBases, ShowtimesQueue, naoTimesDB
from .socket import EventManager, SocketEvent, SocketServer
from .t import MemberContext
from .timeparse import TimeString
from .utils import explode_filepath_into_pieces, prefixes_with_data, read_files
from .version import version_info

ContextModlog = T.Union[disnake.Message, disnake.Member, disnake.Guild]
ALL_MODLOG_FEATURES = ModLogFeature.all()

__all__ = ("StartupError", "naoTimesBot")


class StartupError(Exception):
    def __init__(self, base: Exception) -> None:
        super().__init__()
        self.exception = base


class ModLogQueue(T.NamedTuple):
    log: ModLog
    setting: ModLogSetting


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

    presensi_rate: T.Optional[int]

    def __init__(self, base_path: Path, bot_config: naoTimesBotConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger: logging.Logger = logging.getLogger("naoTimesBot")
        self.semver: str = version_info.text
        self.config: naoTimesBotConfig = bot_config
        self.prefix: str = bot_config.default_prefix
        self.fcwd: Path = base_path

        self.jsdb_streams: dict = {}
        self.jsdb_currency: dict = {}
        self.jsdb_crypto: dict = {}
        self.dev_mode: bool = False

        self.ntdb: naoTimesDB = None
        self.fsdb: FansubDBBridge = None
        self.showqueue: ShowtimesQueue = None
        self.showcogs: ShowtimesCogsBases = None
        self.anibucket: AnilistBucket = None
        self.vndb_socket: VNDBSockIOManager = None
        self.kbbi: KBBI = None
        self.redisdb: RedisBridge = None
        self.jisho: JishoAPI = None
        self.tesaurus: TesaurusAsync = None
        self.merriam: MerriamWebsterClient = None
        self.cardgen: CardGenerator = None
        self.ihaapi: GraphQLClient = None
        self.crowbar: CrowbarClient = None
        self.wolfram: WolframAPI = None
        self.aiosession: aiohttp.ClientSession = None
        self.ntevent: EventManager = None
        self.ntplayer: naoTimesPlayer = None
        self.genius: GeniusAPI = None

        self._resolver: aiohttp.AsyncResolver = None
        self._connector: aiohttp.TCPConnector = None

        self.showtimes_resync: T.List[str] = []
        self._copy_of_commands: T.Dict[str, commands.Command] = {}
        self._modlog_server: T.Dict[str, ModLogSetting] = {}
        self._use_sentry: bool = False

        self._start_time: arrow.Arrow = None
        # When the class got created, it will be the boot time of the bot.
        self._boot_time: arrow.Arrow = arrow.utcnow()
        self._log_channel: disnake.TextChannel = None
        self._owner: T.Union[disnake.User, disnake.TeamMember] = None
        self._is_team_bot: bool = False
        self._team_name: str = None
        self._team_members: T.List[disnake.TeamMember] = []
        self.maintenance: BotMaintenance = None

        self._ip_hostname = ""
        self._host_country = ""
        self._host_name = ""
        self._host_os = ""
        self._host_dpyver = disnake.__version__
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
        http_fh = RollingFileHandler(http_log_path, maxBytes=5_242_880, backupCount=5, encoding="utf-8")
        socket_fh = RollingFileHandler(
            self.fcwd / "logs" / "socket.log", maxBytes=5_242_880, backupCount=5, encoding="utf-8"
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
            loop=self.loop,
        )
        self.ntsocket: SocketServer = SocketServer(
            self.config.socket.port,
            self.config.socket.password,
            logger=socket_logger,
            loop=self.loop,
        )
        self.__first_time_ready = False
        self.__last_disconnection: T.Optional[arrow.Arrow] = None

        self._commit_data = {
            "hash": None,
            "full_hash": None,
            "date": None,
        }

    async def get_context(self, message, *, cls=naoTimesContext):
        """Override the method with custom context"""
        return await super().get_context(message, cls=cls)

    @classmethod
    def create(cls: T.Type[naoTimesBot], base_path: Path, bot_config: naoTimesBotConfig) -> naoTimesBot:
        """
        Create a new instance of the bot and returns it.

        You can set the bot on dev mode by setting the ``NAOTIMES_ENV`` environment
        into ``development``.

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
        bot_description += f"Versi {version_info.text} | Master @N4O#8868"
        IS_DEV = os.getenv("NAOTIMES_ENV", "production") == "development"
        should_sync_command = not bot_config.init_config.slash_check

        intents = disnake.Intents.all()
        # Disable some intents, presences might need to be enabled later.
        intents.presences = False
        if bot_config.init_config.parsed_ns.presence:
            intents.presences = True
        # if bot_config.init_config.parsed_ns.message:
        intents.invites = False
        intents.dm_typing = False
        intents.typing = False
        intents.dm_reactions = True

        bot = cls(
            base_path,
            bot_config,
            command_prefix=bot_config.default_prefix,
            description=bot_description,
            case_insensitive=True,
            max_messages=10_000,
            loop=loop,
            intents=intents,
            sync_commands=should_sync_command,
            reload=IS_DEV,
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

    def now(self) -> arrow.Arrow:
        """:class:`arrow.Arrow`: Get current UTC time"""
        return arrow.utcnow()

    def create_help(self, ctx: naoTimesContext, *args, **kwargs):
        """Create a help embed generator"""
        return HelpGenerator(self, ctx, *args, **kwargs)

    def get_uptime(self, detailed: bool = False):
        """Get bot uptime in relative format.

        Parameters
        ----------
        detailed: :class:`bool`
            If ``True``, return a detailed uptime.
            Example: ``2 menit 30 detik``.
        """
        if self._start_time is None:
            return "baru saja"
        time_ago = self._start_time.humanize(self.now(), "id")
        if detailed:
            ts = TimeString.from_seconds((self.now() - self._start_time).total_seconds())
            return ts.to_string()
        return time_ago

    async def save_config(self):
        """Save the bot configuration to disk"""
        await self.config.save(self.fcwd / "config.json")

    def set_maintenance(self, start: arrow.Arrow, end: arrow.Arrow):
        self.maintenance = BotMaintenance(start, end)

    async def force_update_prefixes(self):
        """Force update the prefix for every guild."""
        srv_prefixes = await self.redisdb.getalldict("ntprefix_*")
        fmt_prefixes = {}
        for srv, prefix in srv_prefixes.items():
            fmt_prefixes[srv[9:]] = prefix

        self.command_prefix = partial(prefixes_with_data, prefixes_data=fmt_prefixes, default=self.prefix)

    async def change_global_prefix(self, new_prefix: str):
        """
        Change the global prefix of the bot.

        Parameters
        ----------
        new_prefix: :class:`str`
            The new prefix.
        """
        self.prefix = new_prefix
        self.config = self.config.update_prefix(new_prefix)
        await self.force_update_prefixes()
        await self.config.save(self.fcwd / "config.json")

    async def _init_kbbi(self, config: naoTimesKBBIConfig):
        self.logger.info("Initializing KBBI...")
        if config is None:
            return KBBI()
        if not config.email or not config.password:
            return KBBI()

        current_dt = self.now().timestamp()
        self.logger.info("Checking authentication information to redis...")
        kbbi_auth_f = await self.redisdb.get("ntconfig_kbbiauth")

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
                    kbbi_cls.set_autentikasi(
                        cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60))
                    )
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
                        kbbi_cls.set_autentikasi(
                            cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60))
                        )
            self.logger.info("KBBI auth restored, resetting connection...")
        except Exception:  # skipcq: PYL-W0703
            self.logger.error(
                "Failed to authenticate, probably server down or something, ignoring for now..."
            )

        await kbbi_cls.reset_connection()
        await self.redisdb.set("ntconfig_kbbiauth", kbbi_cls.get_cookies)
        return kbbi_cls

    async def _init_fsdb(self, config: naoTimesUserPassConfig):
        if config is None:
            return False, None
        if not config.username or not config.password:
            return False, None

        current_dt = self.now().timestamp()
        self.logger.info("Checking authentication information to redis...")
        fsdb_token = await self.redisdb.get("ntconfig_fsdbtoken")
        self.logger.info("Preparing FSDB connection...")
        fsdb_bridge = FansubDBBridge(config.username, config.password, self.aiosession, self.loop)
        if not fsdb_token:
            self.logger.info("FSDB token not found, generating new token...")
            try:
                await asyncio.wait_for(fsdb_bridge.authorize(), timeout=10.0)
            except asyncio.TimeoutError:
                self.logger.warning("Failed to generate new token, disabling...")
                return False, None
            fsdb_token = fsdb_bridge.token_data
        elif fsdb_token["expires"] is not None and current_dt - 300 >= fsdb_token["expires"]:
            self.logger.info("FSDB token expired, generating new token...")
            try:
                await asyncio.wait_for(fsdb_bridge.authorize(), timeout=10.0)
            except asyncio.TimeoutError:
                self.logger.warning("Failed to generate new token, disabling...")
                return False, None
            fsdb_token = fsdb_bridge.token_data
        else:
            self.logger.info("Using saved token...")
            fsdb_bridge.set_token(fsdb_token["token"], fsdb_token["expires"])
        await self.redisdb.set("ntconfig_fsdbtoken", fsdb_token)
        return True, fsdb_bridge

    async def _init_vndb(self, config: naoTimesUserPassConfig):
        if config is None:
            return False, None
        if not config.username or not config.password:
            return False, None

        self.logger.info("Initializing VNDB Socket Connection...")
        vndb_conn = VNDBSockIOManager(config.username, config.password, self.loop)
        await vndb_conn.initialize()
        self.logger.info("Logging in...")
        try:
            await asyncio.wait_for(vndb_conn.async_login(), timeout=10.0)
        except asyncio.TimeoutError:
            self.logger.error("Failed to login, connection timeout after 10 seconds.")
            return True, vndb_conn
        if not vndb_conn.loggedin:
            self.logger.error("Failed to login, provided username and password is wrong.")
            return False, None
        return True, vndb_conn

    async def _init_history_data(self):
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
        self._host_dpyver = disnake.__version__

        self.logger.info("getting bot connection info...")
        async with self.aiosession.get("https://ipinfo.io/json") as resp:
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
        self._commit_data["hash"] = commit[0:7]
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

    async def get_commit_info(self):
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
        self.prefix = self.config.default_prefix

        self.logger.info("Reading all jsdb data...")
        self.jsdb_crypto = await read_files(self.fcwd / "cryptodata.json")
        self.jsdb_currency = await read_files(self.fcwd / "currencydata.json")
        self.jsdb_streams = await read_files(self.fcwd / "streaming_lists.json")

        self.logger.info("Connecting to RedisDB...")
        redis_conf = self.config.redisdb
        redis_conn = RedisBridge(redis_conf.ip_hostname, redis_conf.port, redis_conf.password, self.loop)
        try:
            await redis_conn.connect()
            await redis_conn.client.get("pingpong")
        except ConnectionRefusedError as ce:
            self.logger.error("Failed to connect to RedisDB, aborting...")
            raise StartupError(ce)
        self.redisdb = redis_conn

        self.logger.info("Fetching all server prefixes data...")
        srv_prefixes = await self.redisdb.getalldict("ntprefix_*")
        fmt_prefixes = {}
        for srv, prefix in srv_prefixes.items():
            fmt_prefixes[srv[9:]] = prefix

        self.command_prefix = partial(prefixes_with_data, prefixes_data=fmt_prefixes, default=self.prefix)

        self.logger.info("Fetching all modlog enabled server...")
        servers_modlogs = await self.redisdb.getall("ntmodlog_*")
        for modlog in servers_modlogs:
            parsed_modlog = ModLogSetting.from_dict(modlog)
            if str(parsed_modlog.guild) not in self._modlog_server:
                self._modlog_server[str(parsed_modlog.guild)] = parsed_modlog

        self.logger.info("Initializing FansubDB Bridge...")
        use_fsdb, fsdb_bridge = await self._init_fsdb(self.config.fansubdb)
        if use_fsdb:
            self.fsdb = fsdb_bridge
        self.logger.info("Initializing VNDB Bridge...")
        use_vndb, vndb_bridge = await self._init_vndb(self.config.vndb)
        if use_vndb:
            self.vndb_socket = vndb_bridge

        self.logger.info("Initializing Card generator...")
        card_generator = CardGenerator(self.loop)
        await card_generator.init()
        self.cardgen = card_generator
        self.logger.info("Binding all card generator...")
        for card in AvailableCardGen:
            try:
                await asyncio.wait_for(self.cardgen.bind(card), timeout=10.0)
            except asyncio.TimeoutError:
                self.logger.warning(f"Failed to bind <{card.name}>, timeout after 10 secs")
            except Exception as e:
                self.logger.error(f"Failed to bind <{card.name}> card generator", exc_info=e)

        self.logger.info("Initializing KBBI...")
        if self.config.init_config.kbbi_check:
            self.kbbi = await self._init_kbbi(self.config.kbbi)
        else:
            self.kbbi = KBBI()
        self.logger.info("Binding TesaurusAysnc...")
        self.tesaurus = TesaurusAsync(self.aiosession, self.loop)
        wolfram_conf = self.config.wolfram
        if wolfram_conf is not None:
            wolfram_app_id = wolfram_conf.appid
            if isinstance(wolfram_app_id, str):
                self.logger.info("Binding WolframAlpha...")
                self.wolfram = WolframAPI(wolfram_app_id)

        self.logger.info("Binding Event manager...")
        self.ntevent = EventManager(self.loop)

        if self.config.mongodb:
            mongos = self.config.mongodb
            self.logger.info("Initializing MongoDB/ShowtimesDB connection...")
            self.ntdb: naoTimesDB = naoTimesDB(
                mongos.ip_hostname, mongos.port, mongos.dbname, mongos.auth, mongos.tls, self.dev_mode
            )
            try:
                self.logger.info(f"Trying to connect to: {self.ntdb.url}")
                await self.ntdb.validate_connection()
                self.logger.info("Connected to Database:")
                self.logger.info(f"Connection URL: {self.ntdb.url}")
                self.logger.info(f"Database Name: {self.ntdb.dbname}")
                if self.config.init_config.showtimes_fetch:
                    self.logger.info("Fetching server showtimes data to local database/memory...")
                    showtimes_data = await self.ntdb.fetch_all_as_json()
                    await self.redisdb.bulkrm("showtimes_*")
                    await self.redisdb.bulkrm("showadmin_*")
                    admin_saved = 0
                    for admins in showtimes_data["supermod"]:
                        await self.redisdb.set(f"showadmin_{admins['id']}", admins)
                        admin_saved += 1
                    server_saved = 0
                    stprefix = "showtimes_"
                    for server in showtimes_data["servers"]:
                        svfn = f"{stprefix}{server['id']}"
                        await self.redisdb.set(svfn, server)
                        server_saved += 1
                    self.logger.info(
                        f"Stored {admin_saved}/{len(showtimes_data['supermod'])} admin to redis memcache"
                    )
                    self.logger.info(
                        f"Stored {server_saved}/{len(showtimes_data['servers'])} server to redis memcache"
                    )
            except Exception as exc:  # skipcq: PYL-W0703
                self.logger.error("Failed to validate if database is up and running.")
                self.echo_error(exc)
                self.logger.error(f"IP:Port: {mongos.ip_hostname}:{mongos.port}")

        if isinstance(self.config.merriam_webster, naoTimesMerriamWebsterConfig):
            mwapi_conf = self.config.merriam_webster
            if mwapi_conf.dictionary or mwapi_conf.thesaurus:
                self.logger.info("Binding MerriamWebster client...")
                self.merriam = MerriamWebsterClient(
                    {"words": mwapi_conf.dictionary, "thesaurus": mwapi_conf.thesaurus}
                )

        await self._init_history_data()

        self.logger.info("Preparing music player...")
        music_conf = self.config.music
        try:
            spotify_client = None
            if music_conf and music_conf.spotify:
                spoti_conf = music_conf.spotify
                spotify_client = WVSpotifyClient(client_id=spoti_conf.id, client_secret=spoti_conf.secret)
                if spoti_conf.url:
                    setattr(spotify_client, "_url_host", spoti_conf.url)
            self.ntplayer = naoTimesPlayer(self, self.loop, spotify_client)
        except Exception:
            self.logger.exception("Failed to initialize music player.")

        if music_conf and music_conf.genius:
            gen_conf = music_conf.genius
            self.genius = GeniusAPI(gen_conf.client_id, gen_conf.client_secret, self.aiosession)
            genius_token = await self.redisdb.get("ntplayer_genius")
            if genius_token:
                self.logger.info("Using cached token for Genius API!")
                token: str = genius_token["token"]
                self.genius._token = token
            else:
                self.logger.info("Authorizing with Genius API...")
                await self.genius.authorize()
                self.logger.info("Authorized, saving token!")
                await self.redisdb.set("ntplayer_genius", {"expiry": None, "token": self.genius._token})

        self.logger.info("Binding Jisho connection...")
        self.jisho = JishoAPI(self.aiosession)
        self.logger.info("Binding ShowtimesQueue...")
        self.showqueue = ShowtimesQueue(self.redisdb)
        self.logger.info("Binding AnilistBucket...")
        self.anibucket = AnilistBucket(self.aiosession)
        self.logger.info("Binding Showtimes Base Cogs stuff")
        self.showcogs = ShowtimesCogsBases(self.anibucket)
        self.logger.info("Binding ihateani.me API")
        self.ihaapi = GraphQLClient("https://api.ihateani.me/v2/graphql", self.aiosession)
        if self.config.crowbar_api:
            self.logger.info("Binding (🛠) Crowbar status checker")
            self.crowbar = CrowbarClient(self.config.crowbar_api, self.aiosession)

        self.logger.info("Preparing hot-module reloader")
        # self._hot_reloader = CogWatcher(self, self.loop)

    async def login(self, *args, **kwargs):
        """Logs in the bot to Discord."""
        # self._resolver = aiohttp.AsyncResolver()
        # self._connector = aiohttp.TCPConnector(resolver=self._resolver, family=AF_INET)
        # self.http.connector = self._connector
        self.aiosession = aiohttp.ClientSession(
            headers={
                "User-Agent": f"naoTimes/v{version_info.shorthand} (https://github.com/naoTimesdev/naoTimes)"
            },
            loop=self.loop,
            # connector=self._connector,
        )

        await self.initialize()
        await super().login(*args, **kwargs)
        self.load_extensions()

    async def close(self):
        """Close discord connection and all other stuff that I opened!"""
        # if hasattr(self, "_hot_reloader"):
        #     self._hot_reloader.close()

        for ext in list(self.extensions):
            with suppress(Exception):
                self.unload_extension(ext)

        for cog in list(self.cogs):
            with suppress(Exception):
                self.remove_cog(cog)

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
        if self.vndb_socket:
            self.logger.info("Closing VNDB socket...")
            await self.vndb_socket.close()
        if self.jisho:
            self.logger.info("Closing Jisho connection...")
            await self.jisho.close()
        if self.tesaurus:
            self.logger.info("Closing Tesaurus connection...")
            await self.tesaurus.tutup()
        if self.cardgen:
            self.logger.info("Closing chromium card generator instance...")
            await self.cardgen.close()
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
        if self.genius:
            self.logger.info("Closing genius client...")
            current_token = self.genius._token
            if current_token:
                # Save to cache.
                await self.redisdb.set("ntplayer_genius", {"expiry": None, "token": current_token})
            await self.genius.close()
        if self.ntplayer:
            self.logger.info("Closing music player...")
            await self.ntplayer.close()

        self.logger.info("Closing HTTP server...")
        await self.__http_server.close()

        if self.aiosession:
            self.logger.info("Closing aiohttp Session...")
            await self.aiosession.close()
        if self._connector:
            await self._connector.close()
        if self._resolver:
            await self._resolver.close()

        if self.redisdb:
            self.logger.info("Shutting down redis connection...")
            await self.redisdb.close()

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
        await self.change_presence(
            activity=disnake.Game(name=f"Halo Dunia! | {self.config.default_prefix}help", type=3)
        )
        self.logger.info("Dispatching start event for HTTP server...")
        self.__http_server.start()
        self.logger.info("Checking bot team status...")
        await self.detect_teams_bot()
        self._start_time = self.now()
        if isinstance(self.config.log_channel, int):
            channel_data = self.get_channel(self.config.log_channel)
            if isinstance(channel_data, disnake.TextChannel):
                self._log_channel = channel_data

        music_conf = self.config.music
        if music_conf:
            self.logger.info(f"Connecting with Lavalink nodes ({len(music_conf.nodes)} nodes)")
            for node in music_conf.nodes:
                await self.ntplayer.add_node(node)
        self.logger.info("---------------------------------------------------------------")
        self.logger.info("Bot Ready!")
        self.logger.info(f"Using Python {sys.version}")
        self.logger.info(f"Using Disnake v{disnake.__version__}")
        self.logger.info("---------------------------------------------------------------")
        self.logger.info("Bot Info:")
        self.logger.info(f"Username: {self.user.name}")
        if self._is_team_bot:
            self.logger.info(f"Owner: {self._team_name}")
        else:
            self.logger.info("Owner: {0.name}#{0.discriminator}".format(self._owner))
        if self._is_team_bot and len(self._team_members) > 0:
            member_set = ["{0.name}#{0.discriminator}".format(self._owner)]
            member_set.extend(["{0.name}#{0.discriminator}".format(user) for user in self._team_members])
            parsed_member = ", ".join(member_set)
            self.logger.info(f"With team members: {parsed_member}")
        self.logger.info(f"Client ID: {self.user.id}")
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
        owner_user = self.teams_to_user(self._owner)
        if isinstance(owner_user, disnake.User):
            dm_channel = owner_user.dm_channel
            if dm_channel is None:
                dm_channel = await self._owner.create_dm()
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

    def load_extension(self, name: str, *, package: T.Optional[str] = None):
        self.logger.info(f"Loading module: {name}")
        super().load_extension(name, package=package)
        self.logger.info(f"{name} module is now loaded!")

    def unload_extension(self, name: str):
        self.logger.info(f"Unloading module: {name}")
        super().unload_extension(name)
        self.logger.info(f"{name} module is now unloaded!")

    def _fetch_cog_function(self, cog: commands.Cog) -> T.List[T.Callable[..., T.Any]]:
        _DEFAULT_FUNC = list(commands.Cog.__dir__(commands.Cog))
        all_functions = filter(lambda x: x not in _DEFAULT_FUNC, dir(cog))
        all_functions = filter(lambda x: not x.startswith("cog_"), all_functions)
        all_functions = filter(lambda x: not x.startswith("__cog_"), all_functions)
        all_functions = filter(lambda x: callable(getattr(cog, x)), all_functions)
        all_functions = map(lambda x: getattr(cog, x), all_functions)
        return list(all_functions)

    def _inject_ntsocketevent(self, cog: commands.Cog):
        all_functions = self._fetch_cog_function(cog)
        for func in all_functions:
            socket_cmd = getattr(func, "__nt_socket__", None)
            event_cmd = getattr(func, "__nt_event__", None)
            web_server_route: RouteDef = getattr(func, "__nt_webserver_route__", None)
            if socket_cmd is not None:
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
                if isinstance(event_cmd, list):
                    for cmd in event_cmd:
                        if not cmd["installed"]:
                            self.logger.debug(f"Registering {cmd['name']} into EventManager")
                            self.ntevent.on(cmd["name"], func)
                elif isinstance(event_cmd, dict) and not event_cmd["installed"]:
                    self.logger.debug(f"Registering {event_cmd['name']} into EventManager")
                    self.ntevent.on(event_cmd["name"], func)
            if web_server_route is not None:
                web_server_route.bind_cog(cog)
                self.__http_server.add_route(web_server_route)

    def _uninject_ntsocketevent(self, cog: commands.Cog):
        all_functions = self._fetch_cog_function(cog)
        for func in all_functions:
            socket_cmd = getattr(func, "__nt_socket__", None)
            event_cmd = getattr(func, "__nt_event__", None)
            if socket_cmd is not None:
                if isinstance(socket_cmd, list):
                    for cmd in socket_cmd:
                        if cmd["installed"]:
                            self.logger.debug(f"Removing {cmd['name']} from SocketServer")
                            self.ntsocket.off(cmd["name"])
                elif isinstance(socket_cmd, dict) and socket_cmd["installed"]:
                    self.logger.debug(f"Removing {socket_cmd['name']} from SocketServer")
                    self.ntsocket.off(socket_cmd["name"])
            if event_cmd is not None:
                if isinstance(event_cmd, list):
                    for cmd in event_cmd:
                        if cmd["installed"]:
                            self.logger.debug(f"Removing {cmd['name']} from EventManager")
                            self.ntevent.off(cmd["name"])
                elif isinstance(event_cmd, dict) and event_cmd["installed"]:
                    self.logger.debug(f"Removing {event_cmd['name']} from EventManager")
                    self.ntevent.off(event_cmd["name"])

    def add_cog(self, cog: commands.Cog):
        super().add_cog(cog)
        injected_cog = self.get_cog(cog.__cog_name__)
        if injected_cog is not None:
            self._inject_ntsocketevent(injected_cog)

    def remove_cog(self, name: str):
        cog = self.get_cog(name)
        if cog is not None:
            self._uninject_ntsocketevent(cog)
        super().remove_cog(name)

    def available_extensions(self):
        """Returns all available extensions"""
        ALL_EXTENSION_LIST = []
        IGNORED = ["__init__", "__main__"]
        current_path = str(self.fcwd).replace("\\", "/")
        for (dirpath, _, filenames) in os.walk(self.fcwd / "cogs"):
            for filename in filenames:
                if filename.endswith(".py"):
                    dirpath = dirpath.replace("\\", "/")
                    dirpath = dirpath.replace(current_path, "")
                    if dirpath.startswith("./"):
                        dirpath = dirpath[2:]
                    dirpath = dirpath.lstrip("/")
                    expanded_path = ".".join(explode_filepath_into_pieces(dirpath))
                    just_the_name = filename.replace(".py", "")
                    if just_the_name in IGNORED:
                        continue
                    ALL_EXTENSION_LIST.append(f"{expanded_path}.{just_the_name}")
        ALL_EXTENSION_LIST.sort()
        return ALL_EXTENSION_LIST

    def load_extensions(self):
        """Load all extensions"""
        ALL_EXTENSIONS = self.available_extensions()

        for extension in ALL_EXTENSIONS:
            if extension in self.config.init_config.cogs_skip:
                self.logger.info(f"Skipping {extension}...")
                continue
            try:
                self.load_extension(extension)
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
            with push_scope() as scope:
                scope.set_tag("event", event)
                scope.set_extra("event_args", args)
                scope.set_extra("event_kwargs", kwargs)

                self.logger.exception(f"Unhandled event exception in {event}.")
        else:
            self.logger.exception(f"Unhandled event exception in {event}.")

    def prefixes(self, ctx: T.Union[commands.Context, disnake.TextChannel, disnake.Guild]) -> str:
        """Get server-based bot prefixes
        If none, returns the default prefix

        :param ctx: The context
        :type ctx: T.Union[commands.Context, discord.TextChannel, discord.Guild]
        :return: Server prefix or the default prefix
        :rtype: str
        """
        prefix = self.command_prefix
        if callable(prefix):
            prefix = prefix(self, ctx)
        if isinstance(prefix, (list, tuple)):
            return prefix[0]
        return prefix

    @staticmethod
    def is_mentionable(ctx: commands.Context, user: MemberContext) -> str:
        """Check if the user is mentionable

        :param ctx: The context
        :type ctx: commands.Context
        :param user: The user
        :type user: UserContext
        :return: Formatted mention or just user#discriminator
        :rtype: str
        """
        member = ctx.message.guild.get_member(user.id)
        if member is None:
            return str(user)
        return user.mention

    def teams_to_user(self, user_data: disnake.TeamMember) -> MemberContext:
        member_data = self.get_user(user_data.id)
        if member_data is None:
            return user_data
        return member_data

    async def send_error_log(
        self, message: str = None, embed: disnake.Embed = None, file: disnake.File = None
    ):
        """|coro|

        Send an error log to bot owner or the set channel.

        Parameters
        ----------
        message : str, optional
            The error message to send, by default None
        embed : discord.Embed, optional
            A formatted Discord Embed to send, by default None
        """
        content_to_send = {}
        if isinstance(message, str) and len(message.strip()) > 0:
            content_to_send["content"] = message
        if isinstance(embed, disnake.Embed):
            content_to_send["embed"] = embed
        if isinstance(file, disnake.File):
            content_to_send["file"] = file
        if self._log_channel is None:
            return await self._owner.send(**content_to_send)
        await self._log_channel.send(**content_to_send)

    async def detect_teams_bot(self):
        """|coro|

        Detect if the bot is a team bot and get the team name and members
        """
        app_info: disnake.AppInfo = await self.application_info()
        team_data: disnake.Team = app_info.team
        if team_data is None:
            self._owner = app_info.owner
        else:
            main_owner = disnake.TeamMember = team_data.owner
            members_list: T.List[disnake.TeamMember] = team_data.members

            self._owner = self.teams_to_user(main_owner)
            self._team_name = team_data.name
            self._is_team_bot = True
            for member in members_list:
                if member.id == main_owner.id:
                    continue
                self._team_members.append(self.teams_to_user(member))

    # Some HTTP helper
    async def ping_website(self, web_url: str) -> T.Tuple[bool, float]:
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
            res = await asyncio.wait_for(_internal_pinger(self.aiosession, web_url), timeout=10.0)
            t2 = self.now().timestamp()
            return res, (t2 - t1) * 1000
        except asyncio.TimeoutError:
            return False, 99999.0

    async def send_ihateanime(
        self, text_data: str, filename_prefix: str = None, retention_date: T.Optional[str] = None
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
        async with self.aiosession.post(
            "https://p.ihateani.me/upload", data=form_data, params=params
        ) as resp:
            res = await resp.text()
            if resp.status == 200:
                return res, None
            else:
                return None, res

    async def _dispatch_modlog_internal(self, modlog: ModLogQueue, channel_id: int):
        """|coro|

        Internal dispatcher for modlog
        """
        try:
            the_channel = self.get_channel(channel_id)
            if the_channel is not None:
                try:
                    await self.send_modlog(modlog.log, the_channel)
                except Exception as e:
                    error_msg = "An error occured while trying to send modlog for "
                    error_msg += f"guild {modlog.setting.guild}\n"
                    error_msg += f"Modlog event: {modlog.log.action.name}"
                    self.logger.error(error_msg)
                    self.echo_error(e, True)
        except asyncio.CancelledError:
            self.logger.warning(f"Task {modlog} got cancelled")

    # Modlog stuff
    async def send_modlog(self, modlog: ModLog, channel: disnake.TextChannel = None):
        if channel is None:
            return
        if modlog.embed is not None:
            embed = modlog.embed
            if modlog.timestamp is None:
                modlog.timestamp = None
            if embed.colour == disnake.Embed.Empty:
                embed.colour = disnake.Color.random()
            if embed.timestamp == disnake.Embed.Empty:
                datedata: arrow.Arrow = arrow.get(modlog.timestamp)
                embed.timestamp = datedata.datetime
            modlog.embed = embed

        real_message = modlog.message
        if not real_message:
            real_message = None
        if real_message is None and modlog.embed is None:
            self.logger.warning(f"Got empty modlog data? {modlog} ({channel})")
            return
        await channel.send(content=real_message, embed=modlog.embed)

    def should_modlog(
        self,
        context: ContextModlog,
        user_data: MemberContext = None,
        features: T.List[ModLogFeature] = ALL_MODLOG_FEATURES,
        include_bot: bool = False,
    ):
        """Check if we can and should modlog the event received.
        This will check if it's a bot, server exist in the modlog list,
        the server have the feature enabled for that event and more.

        :param context: The context, either guild, channel or user
        :type context: ContextModlog
        :param user_data: The user data
        :type user_data: MemberContext
        :param features: The feature set needed to be enabled
        :type features: T.List[ModLogFeature]
        :param include_bot: Can bot data be included in this, defaults to False
        :type include_bot: bool, optional
        :return: Tuple of boolean and ModLogSetting of the guild
        :rtype: T.Tuple[bool, ModLogSetting]
        """
        # Check if context exist
        if context is None:
            return False, None
        server_data = context
        if not isinstance(context, disnake.Guild):
            server_data = context.guild
        # Check if bot can be included
        if user_data is not None and user_data.bot and not include_bot:
            return False, None
        srv_id = str(server_data.id)
        # Check if server in the modlog list
        if srv_id not in self._modlog_server:
            return False, None
        modlog_setting = self._modlog_server[srv_id]
        # Check if the guild enable this feature set.
        if not modlog_setting.has_features(features):
            return False, None
        return True, modlog_setting

    async def add_modlog(self, modlog: ModLog, setting: ModLogSetting):
        """Add modlog info to be sent later

        :param modlog: Modlog to be sent
        :type modlog: ModLog
        :param setting: The guild settings for that modlog
        :type setting: ModLogSetting
        """
        ctime = self.now().timestamp()

        if modlog.timestamp is None:
            modlog.timestamp = ctime

        queue = ModLogQueue(modlog, setting)
        self.loop.create_task(
            self._dispatch_modlog_internal(queue, setting.channel),
            name=f"modlog-dispatcher-internal-event-{modlog.action.name}_{ctime}",
        )
        if setting.is_public_features(modlog.action):
            self.loop.create_task(
                self._dispatch_modlog_internal(queue, setting.public_channel),
                name=f"modlog-dispatcher-public-event-{modlog.action.name}_{ctime}",
            )

    def has_modlog(self, guild_id: int) -> bool:
        """Check if guild have modlog enabled or not

        :param guild_id: Guild ID to be checked
        :type guild_id: int
        :return: True if guild have modlog enabled
        :rtype: bool
        """
        return str(guild_id) in self._modlog_server

    def get_modlog(self, guild_id: int) -> T.Optional[ModLogSetting]:
        """Get the guild settings a guild id

        :param guild_id: Guild ID to be checked
        :type guild_id: int
        :return: The guild settings
        :rtype: T.Optional[ModLogSetting]
        """
        return self._modlog_server.get(str(guild_id), None)

    async def remove_modlog(self, guild_id: int):
        """Remove the modlog feature form a guild"""
        if not self.has_modlog(guild_id):
            return

        self._modlog_server.pop(str(guild_id))
        self.logger.info(f"Removed modlog for guild {guild_id}")
        await self.redisdb.rm(f"ntmodlog_{guild_id}")

    async def update_modlog(self, guild_id: int, setting: ModLogSetting):
        """Update the modlog settings for a guild

        :param guild_id: Guild ID to be updated
        :type guild_id: int
        :param setting: The new settings
        :type setting: ModLogSetting
        """
        self._modlog_server[str(guild_id)] = setting
        await self.redisdb.set(f"ntmodlog_{guild_id}", setting.serialize())

    # Placeholder command helper
    def toggle_command(self, command_name: str, reason: str = None):
        """Toggle a command to be enabled or disabled"""
        DISALLOWED_CMD = ["disablecmd", "enablecmd", "load", "reload", "unload"]
        command_name = command_name.rstrip().lower()
        if command_name in DISALLOWED_CMD:
            self.logger.warning("Command is on not allowed list")
            return False, "Tidak bisa menonaktifkan perintah tersebut karena dibutuhkan!"

        command_real: commands.Command = self.remove_command(command_name)
        if command_real is None:
            self.logger.warning(f"{command_name}: Command not found")
            return False, "Tidak dapat menemukan command tersebut."

        command_aliases = command_real.aliases
        command_real_name = command_real.name
        for alias in command_aliases:
            # Try to remove it just in case owner remove the alias only.
            self.logger.info(f"{command_name}: removing `{alias}` alias...")
            self.remove_command(alias)
        if command_name in command_aliases:
            self.logger.info(
                f"{command_name}: removing `{command_real_name}` real command name (user provide alias)..."
            )
            self.remove_command(command_real_name)

        if command_real_name in self._copy_of_commands:
            self.logger.info(f"{command_name}: registering original command back")
            original_cmd = self._copy_of_commands.pop(command_real_name)
            try:
                self.logger.info(f"{command_name}: registering the original command back...")
                self.add_command(original_cmd)
            except commands.CommandRegistrationError as cre:
                self.logger.error(f"{command_name}: Failed to registered the original command")
                self.echo_error(cre)
                return False, "Gagal meregistrasi ulang perintah asli ke bot!"
            self.logger.info(f"{command_name}: successfully reenabled original command")
            return True, f"Perintah `{command_name}` berhasil diaktifkan kembali!"
        else:
            self.logger.info(f"{command_name}: disabling command and adding placeholder cmd")
            plch_cmd = PlaceHolderCommand(command_real_name, reason)
            plch_discordcmd = commands.Command(
                plch_cmd.send_placeholder, name=command_real_name, aliases=command_aliases
            )
            self.add_command(plch_discordcmd)
            self._copy_of_commands[command_real_name] = command_real
            self.logger.info(f"{command_name}: original command are now disabled!")
            return True, f"Perintah `{command_name}` berhasil dinonaktifkan!"
