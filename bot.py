# -*- coding: utf-8 -*-

import argparse
import asyncio
import gc
import logging
import os
import pathlib
import random
import sys
import time
import traceback
from datetime import datetime, timezone
from functools import partial
from itertools import cycle
from typing import Optional

import aiohttp
import discord
import pymongo.errors
from discord.ext import commands, tasks
from discord_slash import SlashCommand

from nthelper.anibucket import AnilistBucket
from nthelper.bot import naoTimesBot
from nthelper.fsdb import FansubDBBridge
from nthelper.jisho import JishoAPI
from nthelper.kbbiasync import KBBI, AutentikasiKBBI
from nthelper.redis import RedisBridge
from nthelper.showtimes_helper import ShowtimesQueue, naoTimesDB
from nthelper.utils import (
    HelpGenerator,
    __version__,
    get_server,
    get_version,
    ping_website,
    prefixes_with_data,
    read_files,
    write_files,
)
from nthelper.vndbsocket import VNDBSockIOManager

# Silent some imported module
logging.getLogger("websockets").setLevel(logging.WARNING)

cogs_list = ["cogs." + x.replace(".py", "") for x in os.listdir("cogs") if x.endswith(".py")]

logger = logging.getLogger()
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[logging.FileHandler("naotimes.log", "w", "utf-8")],
    format="[%(asctime)s] - (%(name)s)[%(levelname)s](%(funcName)s): %(message)s",  # noqa: E501
    datefmt="%Y-%m-%d %H:%M:%S",
)

console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console_formatter = logging.Formatter("[%(levelname)s] (%(name)s): %(funcName)s: %(message)s")
console.setFormatter(console_formatter)
logger.addHandler(console)

# Handle the new Intents.
discord_ver_tuple = tuple([int(ver) for ver in discord.__version__.split(".")])
DISCORD_INTENTS = None
if discord_ver_tuple >= (1, 5, 0):
    logger.info("Detected discord.py version 1.5.0, using the new Intents system...")
    # Enable all except Presences.
    DISCORD_INTENTS = discord.Intents.all()

parser = argparse.ArgumentParser("naotimesbot")
parser.add_argument("-dcog", "--disable-cogs", default=[], action="append", dest="cogs_skip")
parser.add_argument("-skbbi", "--skip-kbbi-check", action="store_true", dest="kbbi_check")
parser.add_argument("-sshow", "--skip-showtimes-fetch", action="store_true", dest="showtimes_fetch")
args_parsed = parser.parse_args()


def announce_error(error):
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    logger.error("Exception occured\n%s", tb)


async def initialize_kbbi(config_data: dict) -> KBBI:
    if "kbbi" not in config_data:
        return KBBI()
    kbbi_conf = config_data["kbbi"]
    if "email" not in kbbi_conf or "password" not in kbbi_conf:
        return KBBI()
    if not kbbi_conf["email"] or not kbbi_conf["password"]:
        return KBBI()
    current_dt = datetime.now(tz=timezone.utc).timestamp()
    logger.info("trying to read KBBI auth files...")
    kbbi_auth_f = await read_files("kbbi_auth.json")

    kbbi_cls = KBBI()
    kbbi_cls.set_autentikasi(username=kbbi_conf["email"], password=kbbi_conf["password"])

    try:
        if not kbbi_auth_f:
            logger.info("authenticating to KBBI...")
            kbbi_auth = AutentikasiKBBI(kbbi_conf["email"], kbbi_conf["password"])
            await kbbi_auth.autentikasi()
            cookie_baru = await kbbi_auth.ambil_cookies()
            kbbi_cls.set_autentikasi(cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60)))
        else:
            if current_dt >= kbbi_auth_f["expires"]:
                logger.warning("kbbi cookie expired, generating new one...")
                kbbi_auth = AutentikasiKBBI(kbbi_conf["email"], kbbi_conf["password"])
                await kbbi_auth.autentikasi()
                cookie_baru = await kbbi_auth.ambil_cookies()
                kbbi_cls.set_autentikasi(cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60)))
            else:
                kbbi_cls.set_autentikasi(cookie=kbbi_auth_f["cookie"], expiry=kbbi_auth_f["expires"])
                await kbbi_cls.reset_connection()
                is_kbbi_auth = await kbbi_cls.cek_auth()
                if not is_kbbi_auth:
                    logger.warning("kbbi cookie expired, generating new one...")
                    kbbi_auth = AutentikasiKBBI(kbbi_conf["email"], kbbi_conf["password"])
                    await kbbi_auth.autentikasi()
                    cookie_baru = await kbbi_auth.ambil_cookies()
                    kbbi_cls.set_autentikasi(
                        cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60))
                    )
        logger.info("kbbi auth restored, resetting connection.")
    except Exception:  # skipcq: PYL-W0703
        logger.error("Failed to authenticate, probably server down or something, ignoring for now...")
    await kbbi_cls.reset_connection()
    await write_files(kbbi_cls.get_cookies, "kbbi_auth.json")
    return kbbi_cls


async def initialize_fsdb(config_data: dict):
    if "fansubdb" not in config_data:
        return False, None
    fsdb_conf = config_data["fansubdb"]
    if "username" not in fsdb_conf or "password" not in fsdb_conf:
        return False, None
    if not fsdb_conf["username"] or not fsdb_conf["password"]:
        return False, None

    current_dt = datetime.now(tz=timezone.utc).timestamp()
    logger.info("Opening FSDB Token data...")
    fsdb_token = await read_files("fsdb_login.json")
    logger.info("Preparing FSDB Connection...")
    fsdb_bridge = FansubDBBridge(fsdb_conf["username"], fsdb_conf["password"])
    if not fsdb_token:
        logger.info("Authenticating (No saved token)...")
        await fsdb_bridge.authorize()
        fsdb_token = fsdb_bridge.token_data
        await write_files(fsdb_token, "fsdb_login.json")
    elif fsdb_token["expires"] is not None and current_dt - 300 >= fsdb_token["expires"]:
        logger.info("Reauthenticating (Token expired)...")
        await fsdb_bridge.authorize()
        fsdb_token = fsdb_bridge.token_data
        await write_files(fsdb_token, "fsdb_login.json")
    else:
        logger.info("Setting FSDB token...")
        fsdb_bridge.set_token(fsdb_token["token"], fsdb_token["expires"])
    return True, fsdb_bridge


async def initialize_vndb(config_data: dict, loop):
    if "vndb" not in config_data:
        return False, None
    vndb_conf = config_data["vndb"]
    if "username" not in vndb_conf or "password" not in vndb_conf:
        return False, None
    if not vndb_conf["username"] or not vndb_conf["password"]:
        return False, None

    logger.info("Initializing VNDB Socket Connection...")
    vndb_conn = VNDBSockIOManager(vndb_conf["username"], vndb_conf["password"], loop)
    await vndb_conn.initialize()
    logger.info("Logging in...")
    try:
        await asyncio.wait_for(vndb_conn.async_login(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("Failed to login, connection timeout after 10 seconds.")
        return True, vndb_conn
    if not vndb_conn.loggedin:
        logger.error("Failed to login, provided username and password is wrong.")
        return False, None
    return True, vndb_conn


async def init_bot(loop) -> naoTimesBot:
    """
    Start loading all the bot process
    Will start:
        - discord.py and the modules
        - Setting some global variable
        - load local json and add it to Bot class.
    """
    logger.info("Looking up config")
    config = await read_files("config.json")
    logger.info("Loading crypto data...")
    crypto_data = await read_files("cryptodata.json")
    logger.info("Loading currency data...")
    currency_data = await read_files("currencydata.json")
    logger.info("Loading streaming lists data...")
    streams_list = await read_files("streaming_lists.json")

    if not args_parsed.kbbi_check:
        kbbi_conn = await initialize_kbbi(config)
    else:
        kbbi_conn = KBBI()

    if "redisdb" not in config:
        logger.error("Redis DB is not setup, please setup Redis before continuing!")
        return sys.exit(1)
    if not config["redisdb"]:
        logger.error("Redis DB is not setup, please setup Redis before continuing!")
        return sys.exit(1)
    redis_conf = config["redisdb"]
    if "ip_hostname" not in redis_conf or "port" not in redis_conf:
        logger.error("Redis DB is not setup, please setup Redis before continuing!")
        return sys.exit(1)
    if not redis_conf["ip_hostname"] or not redis_conf["port"]:
        logger.error("Redis DB is not setup, please setup Redis before continuing!")
        return sys.exit(1)

    redis_conn = RedisBridge(
        redis_conf["ip_hostname"], redis_conf["port"], redis_conf.get("password", None), loop
    )
    logger.info("Connecting to RedisDB...")
    await redis_conn.connect()
    logger.info("Connected to RedisDB!")

    logger.info("Fetching prefixes data...")
    srv_prefixes = await redis_conn.getalldict("ntprefix_*")
    fmt_prefixes = {}
    for srv, pre in srv_prefixes.items():
        fmt_prefixes[srv[9:]] = pre

    use_fsdb, fsdb_bridge = await initialize_fsdb(config)
    use_vndb, vndb_conn = await initialize_vndb(config, loop)

    cwd = str(pathlib.Path(__file__).parent.absolute())

    default_prefix = config["default_prefix"]

    try:
        logger.info("Initiating discord.py")
        description = "Penyuruh Fansub biar kerja cepat\n"
        description += f"versi {__version__} || Dibuat oleh: N4O#8868"
        prefixes = partial(prefixes_with_data, prefixes_data=fmt_prefixes, default=default_prefix)
        if discord_ver_tuple >= (1, 5, 0):
            # Insert intents
            bot = naoTimesBot(
                command_prefix=prefixes, description=description, intents=DISCORD_INTENTS, loop=loop
            )
        else:
            bot = naoTimesBot(command_prefix=prefixes, description=description, loop=loop)
        bot.remove_command("help")
        bot.logger.info("Bot loaded, now using bot logger for logging.")
        # if not hasattr(bot, "logger"):
        #     bot.logger = logger
        bot.botconf = config
        bot.semver = __version__
        bot.logger.info("Binding JSON dataset...")
        bot.jsdb_streams = streams_list
        bot.jsdb_currency = currency_data
        bot.jsdb_crypto = crypto_data
        bot.fcwd = cwd
        bot.logger.info("Binding KBBI Connection...")
        bot.kbbi = kbbi_conn
        bot.logger.info("Binding Jisho Connection...")
        bot.jisho = JishoAPI()
        if use_fsdb:
            bot.logger.info("Binding FansubDB...")
            bot.fsdb = fsdb_bridge
        if use_vndb:
            bot.logger.info("Binding VNDB Socket Connection...")
            bot.vndb_socket = vndb_conn
        bot.logger.info("Binding ShowtimesQueue...")
        bot.showqueue = ShowtimesQueue(redis_conn, loop)
        bot.logger.info("Binding AnilistBucket")
        bot.anibucket = AnilistBucket()
        bot.logger.info("Binding Redis...")
        bot.redisdb = redis_conn
        bot.logger.info("Success Loading Discord.py")
        bot.logger.info("Binding interactions...")
        SlashCommand(bot, sync_commands=True, override_type=True)
    except Exception as exc:  # skipcq: PYL-W0703
        bot.logger.error("Failed to load Discord.py")
        announce_error(exc)
        return None  # type: ignore
    return bot


# Initiate everything
logger.info(f"Initiating bot v{__version__}...")
logger.info("Setting up loop")
async_loop = asyncio.get_event_loop()
bot: naoTimesBot = async_loop.run_until_complete(init_bot(async_loop))
if bot is None:
    sys.exit(1)
presence_status = [
    "Mengamati rilisan fansub | !help",
    "Membantu Fansub | !help",
    "Menambah utang | !help",
    "Membersihkan nama baik | !help",
    "Ngememe | !help",
    "Membersihkan sampah masyarakat | !help",
    "Mengikuti event wibu | !help",
    "Menjadi babu | !help",
    "Memantau hal yang berbau Yuri | !help",
    "!help | !help",
    "Apa Kabar Fansub Indonesia? | !help",
    "Memantau drama | !help",
    "Bot ini masih belum legal | !help",
    "Mengoleksi berhala | !help",
    "Memburu buronan 1001 Fansub | !help",
    "Menagih utang | !help",
    "Menunggu Fanshare bubar | !help",
    "Mencatat Delayan Fansub | !help",
    "Mengintai waifu orang | !help",
    "Waifu kalian sampah | !help",
    "Membeli waifu di toko terdekat | !help",
    "Reinkarnasi Fansub mati | !help",
    "Menuju Isekai | !help",
    "Leecher harap menagih dalam 120x24 jam | !help",
    "Membuka donasi | !help",
    "Menunggu rilisan | !help",
    "Mengelus kepala owner bot | !help",
    "Membuat Fansub | !help",
    "Membuli Fansub | !help",
    "Membuat Meme berstandar SNI",
    "Mengembalikan kode etik Fansub | !help",
    "Meniduri waifu anda | !help",
    "Mengamati paha | !help",
    "Berternak dolar | !help",
    "Kapan nikah? Ngesub mulu. | !help",
    "Kapan pensi? | !help",
    "Gagal pensi | !help",
    "Judul Anime - Episode (v9999) | !help",
]


@bot.event
async def on_ready():
    """Bot loaded here"""
    bot.logger.info("Connected to discord.")
    activity = discord.Game(name=presence_status[0], type=3)
    await bot.change_presence(activity=activity)
    bot.logger.info("Checking bot team status...")
    await bot.detect_teams_bot()
    await bot.populate_data()
    bot.logger.info("---------------------------------------------------------------")
    precall = bot.command_prefix
    if callable(precall):
        precall = precall(bot, "[]")
    if isinstance(precall, (list, tuple)):
        bot.prefix = precall[0]
    else:
        bot.prefix = precall
    if "mongodb" in bot.botconf:
        mongos = bot.botconf["mongodb"]
        bot.ntdb = naoTimesDB(
            mongos["ip_hostname"], mongos["port"], mongos["dbname"], mongos["auth"], mongos["tls"]
        )
        try:
            bot.logger.info(f"Connecting to: {bot.ntdb.url}...")
            await bot.ntdb.validate_connection()
            bot.logger.info("Connected to Database:")
            bot.logger.info("Connection URL: {}".format(bot.ntdb.url))
            bot.logger.info("Database Name: {}".format(bot.ntdb.dbname))
            bot.logger.info("---------------------------------------------------------------")
            if not args_parsed.showtimes_fetch:
                bot.logger.info("Fetching nao_showtimes from server db to local json")
                js_data = await bot.ntdb.fetch_all_as_json()
                showtimes_folder = os.path.join(bot.fcwd, "showtimes_folder")
                if not os.path.isdir(showtimes_folder):
                    os.makedirs(showtimes_folder)
                for fn, fdata in js_data.items():
                    svfn = f"showtimes_{fn}"
                    bot.logger.info(f"showtimes: saving to file {fn}")
                    if fn == "supermod":
                        svfn = "showtimesadmin"
                    await bot.redisdb.set(svfn, fdata)
                bot.logger.info("File fetched and saved to local json")
                bot.logger.info(
                    "---------------------------------------------------------------"
                )  # noqa: E501
        except Exception:  # skipcq: PYL-W0703
            bot.logger.error("Failed to validate if database is up and running.")
            bot.logger.error("IP:Port: {}:{}".format(mongos["ip_hostname"], mongos["port"]))
            bot.ntdb = None
            bot.logger.info("---------------------------------------------------------------")  # noqa: E501
    bot.uptime = datetime.now(tz=timezone.utc).timestamp()
    if "error_logger" in bot.botconf and bot.botconf["error_logger"] is not None:
        channel_data = bot.get_channel(bot.botconf["error_logger"])
        if channel_data is not None:
            bot.error_logger = bot.botconf["error_logger"]
    skipped_cogs = []
    for cogs in args_parsed.cogs_skip:
        if not cogs.startswith("cogs."):
            cogs = "cogs." + cogs
        skipped_cogs.append(cogs)
    bot.logger.info("[#][@][!] Start loading cogs...")
    for load in cogs_list:
        if load in skipped_cogs:
            bot.logger.warning(f"Skipping: {load}")
            continue
        try:
            bot.logger.info(f"Loading: {load}")
            bot.load_extension(load)
            bot.logger.info(f"Loaded: {load}")
        except commands.ExtensionError as enoff:
            bot.logger.error(f"Failed to load {load} module")
            bot.echo_error(enoff)
    bot_hostdata = bot.get_hostdata
    bot.logger.info("[#][@][!] All cogs/extensions loaded.")
    bot.logger.info("Preparing command registration")
    await bot.slash.sync_all_commands()
    # await bot.slash.register_all_commands()
    bot.logger.info("---------------------------------------------------------------")
    bot.logger.info("Bot Ready!")
    bot.logger.info("Using Python {}".format(sys.version))
    bot.logger.info("And Using Discord.py v{}".format(discord.__version__))
    bot.logger.info("Hosted in: {0.location} [{0.masked_ip}]".format(bot_hostdata))
    bot.logger.info("---------------------------------------------------------------")
    bot.logger.info("Bot Info:")
    bot.logger.info("Username: {}".format(bot.user.name))
    if bot.is_team_bot:
        bot.logger.info(f"Owner: {bot.team_name}")
    else:
        bot.logger.info("Owner: {0.name}#{0.discriminator}".format(bot.owner))
    if bot.is_team_bot and len(bot.team_members) > 0:
        member_set = ["{0.name}#{0.discriminator}".format(bot.owner)]
        member_set.extend(["{0.name}#{0.discriminator}".format(user) for user in bot.team_members])
        parsed_member = ", ".join(member_set)
        bot.logger.info("With team members: {}".format(parsed_member))
    bot.logger.info("Client ID: {}".format(bot.user.id))
    bot.logger.info("Running naoTimes version: {}".format(__version__))
    commit_info = bot.get_commit
    if commit_info["hash"] is not None:
        bot.logger.info(f"With Commit Hash: {commit_info['full_hash']} ({commit_info['date']})")
    bot.logger.info("---------------------------------------------------------------")


async def change_bot_presence():
    await bot.wait_until_ready()
    bot.logger.info("Loaded auto-presence.")
    presences = cycle(presence_status)

    while not bot.is_closed():
        await asyncio.sleep(30)
        try:
            current_status = next(presences)
        except StopIteration:
            current_status = random.choice(presences)
        activity = discord.Game(name=current_status, type=3)
        await bot.change_presence(activity=activity)


@tasks.loop(hours=12)
async def garbage_collector():
    bot.logger.info("running garbage collection...")
    collected = gc.collect()
    bot.logger.info(f"collected {collected} objects.")


async def send_hastebin(info):
    async with aiohttp.ClientSession() as session:
        current = str(datetime.now(tz=timezone.utc).timestamp())
        form_data = aiohttp.FormData()
        form_data.add_field(
            name="file",
            value=info.encode("utf-8"),
            content_type="text/x-python",
            filename=f"naoTimes_error_log_{current}.py",
        )
        async with session.post("https://p.ihateani.me/upload", data=form_data) as resp:
            if resp.status == 200:
                res = await resp.text()
                finalized = "**Error Occured!**\n"
                finalized += "But since the log it's way past Discord 2000 characters limit, "
                finalized += f"the log file can be accessed here: <{res}>"

                finalized += "\n\nThe log file are valid for around 2.5 months"
                return finalized


@bot.event
async def on_command_error(ctx: commands.Context, error):
    """The event triggered when an error is raised while invoking a command.
    ctx   : Context
    error : Exception"""

    if hasattr(ctx.command, "on_error"):
        return

    ignored = (
        commands.CommandNotFound,
        commands.UserInputError,
        commands.NotOwner,
        commands.ArgumentParsingError,
        aiohttp.ClientError,
        discord.errors.HTTPException,
    )
    error = getattr(error, "original", error)

    if isinstance(error, ignored):
        bot.echo_error(error)
        return
    if isinstance(error, commands.DisabledCommand):
        return await ctx.send(f"`{ctx.command}`` dinon-aktifkan.")
    if isinstance(error, commands.NoPrivateMessage):
        try:
            return await ctx.author.send(f"`{ctx.command}`` tidak bisa dipakai di Private Messages.")
        except discord.HTTPException:
            bot.logger.error("Failed to sent private message about it, ignoring...")
            return

    current_time = datetime.now(tz=timezone.utc).timestamp()

    bot.logger.error("Ignoring exception in command {}:".format(ctx.command))
    tb = traceback.format_exception(type(error), error, error.__traceback__)

    error_info = "\n".join(
        [
            "Perintah: {0.command}".format(ctx),
            "Pesan: {0.message.clean_content}".format(ctx),
            "Server: {0.guild.name} ({0.guild.id})".format(ctx.message),
            "Kanal: #{0.channel.name} ({0.channel.id})".format(ctx.message),
            "Author: {0.author.name}#{0.author.discriminator} ({0.author.id})".format(ctx.message),
        ]
    )
    traceback_parsed = "".join(tb).replace("`", "")
    msg = f"**Terjadi Kesalahan**\n```py\n{error_info}\n```\n```py\n{traceback_parsed}\n```"

    embed = discord.Embed(
        title="Error Logger",
        colour=0xFF253E,
        description="Terjadi kesalahan atau Insiden baru-baru ini...",
        timestamp=datetime.utcfromtimestamp(current_time),
    )
    embed.add_field(
        name="Cogs", value="[nT!] {0.cog_name}".format(ctx.command), inline=False,
    )
    embed.add_field(
        name="Perintah yang dipakai",
        value="{0.command}\n`{0.message.clean_content}`".format(ctx),
        inline=False,
    )
    embed.add_field(
        name="Server Insiden",
        value="{0.guild.name} ({0.guild.id})\n#{0.channel.name} ({0.channel.id})".format(ctx.message),
        inline=False,
    )
    embed.add_field(
        name="Orang yang memakainya",
        value="{0.author.name}#{0.author.discriminator} ({0.author.id})".format(ctx.message),  # noqa: E501
        inline=False,
    )
    embed.add_field(
        name="Traceback", value="```py\n{}\n```".format("".join(tb)), inline=True,
    )
    embed.set_thumbnail(url="https://p.ihateani.me/mccvpqgd.png")
    try:
        await bot.send_error_log(embed=embed)
    except discord.HTTPException:
        bot.logger.error("Failed to send bot error log to provided channel!")
        if len(msg) > 1900:
            msg = await send_hastebin(msg)
        else:
            await bot.send_error_log(msg)
    await ctx.send(
        "**Error**: Insiden internal ini telah dilaporkan "
        f"ke **{bot.owner.name}#{bot.owner.discriminator}**, mohon tunggu jawabannya kembali."
    )
    bot.echo_error(error)


def ping_emote(t_t):
    if t_t < 50:
        emote = ":race_car:"
    elif t_t >= 50 and t_t < 200:
        emote = ":blue_car:"
    elif t_t >= 200 and t_t < 500:
        emote = ":racehorse:"
    elif t_t >= 200 and t_t < 500:
        emote = ":runner:"
    elif t_t >= 500 and t_t < 3500:
        emote = ":walking:"
    elif t_t >= 3500:
        emote = ":snail:"
    return emote


@bot.command()
async def ping(ctx):
    """
    pong!
    """
    channel = ctx.message.channel
    bot.logger.info("checking websocket...")
    ws_ping = bot.latency
    bot.logger.info("checking database...")
    db_res, db_ping = await bot.ntdb.ping_server()
    irnd = lambda t: int(round(t))  # noqa: E731

    bot.logger.info("checking api.ihateani.me...")
    ihapi_res, ihaapi_ping = await ping_website("https://api.ihateani.me/")

    bot.logger.info("checking anilist.co")
    ani_res, ani_ping = await ping_website("https://graphql.anilist.co")

    def _gen_text(ping_res, ping, name):
        text_res = ":x: "
        if ping_res:
            text_res = f"{ping_emote(ping)} "
        text_res += "{}: `{}`".format(name, "{}ms".format(ping) if ping_res else "nan")
        return text_res

    ihaapi_ping = irnd(ihaapi_ping)
    ani_ping = irnd(ani_ping)
    db_ping = irnd(db_ping)

    text_res = ":satellite: Ping Results :satellite:"
    bot.logger.info("checking discord itself.")
    t1_dis = time.perf_counter()
    async with channel.typing():
        t2_dis = time.perf_counter()
        dis_ping = irnd((t2_dis - t1_dis) * 1000)
        bot.logger.info("generating results....")
        bot.logger.debug("generating discord res")
        text_res += f"\n{ping_emote(dis_ping)} Discord: `{dis_ping}ms`"

        bot.logger.debug("generating websocket res")
        if ws_ping != float("nan"):
            ws_time = irnd(ws_ping * 1000)
            ws_res = f"{ping_emote(ws_time)} Websocket `{ws_time}ms`"
        else:
            ws_res = ":x: Websocket: `nan`"

        text_res += f"\n{ws_res}"
        bot.logger.debug("generating db res")
        text_res += f"\n{_gen_text(db_res, db_ping, 'Database')}"
        bot.logger.debug("generating ihaapi res")
        text_res += f"\n{_gen_text(ihapi_res, ihaapi_ping, 'naoTimes API')}"
        bot.logger.debug("generating anilist res")
        text_res += f"\n{_gen_text(ani_res, ani_ping, 'Anilist.co')}"
        bot.logger.info("sending results")
        await channel.send(content=text_res)


async def fetch_bot_count_data():
    server_list = bot.guilds
    total_server = len(server_list)

    users_list = []
    total_channels = 0

    for srv in server_list:
        total_channels += len(srv.channels)

        for user in srv.members:
            if not user.bot and user.id not in users_list:
                users_list.append(user.id)

    total_valid_users = len(users_list)

    text_fmt = "Jumlah server: {}\nJumlah channels: {}\nJumlah pengguna: {}".format(  # noqa: E501
        total_server, total_channels, total_valid_users
    )

    showtimes_servers = await bot.redisdb.keys("showtimes_*")
    if showtimes_servers:
        text_fmt += f"\n\nJumlah Server Showtimes: {len(showtimes_servers)}"

    return "```" + text_fmt + "```"


def create_uptime():
    current_time = datetime.now(tz=timezone.utc).timestamp()
    up_secs = int(round(current_time - bot.uptime))  # Seconds

    up_months = int(up_secs // 2592000)  # 30 days format
    up_secs -= up_months * 2592000
    up_weeks = int(up_secs // 604800)
    up_secs -= up_weeks * 604800
    up_days = int(up_secs // 86400)
    up_secs -= up_days * 86400
    up_hours = int(up_secs // 3600)
    up_secs -= up_hours * 3600
    up_minutes = int(up_secs // 60)
    up_secs -= up_minutes * 60

    return_data = []
    if up_months > 0:
        return_data.append(f"{up_months} bulan")
    if up_weeks > 0:
        return_data.append(f"{up_weeks} minggu")
    if up_days > 0:
        return_data.append(f"{up_days} hari")
    if up_hours > 0:
        return_data.append(f"{up_hours} jam")
    if up_minutes > 0:
        return_data.append(f"{up_minutes} menit")
    return_data.append(f"{up_secs} detik")

    return "`" + " ".join(return_data) + "`"


async def creator_info(ctx):
    if not bot.is_team_bot:
        return bot.is_mentionable(ctx, bot.owner)
    res = f"{bot.team_name} | "
    member_data = []
    member_data.append(bot.is_mentionable(ctx, bot.owner))
    if bot.team_members:
        for member in bot.team_members:
            if member.id == bot.owner.id:
                continue
            member_data.append(bot.is_mentionable(ctx, member))
    res += " ".join(member_data)
    return res


@bot.command()
async def info(ctx):
    """
    Melihat Informasi bot
    """
    infog = discord.Embed(
        title="naoTimes", description="Sang penagih utang fansub agar fansubnya mau gerak", color=0xDE8730,
    )
    infog.set_author(
        name="naoTimes", icon_url=bot.user.avatar_url,  # noqa: E501
    )
    semver = bot.semver
    commit = bot.get_commit
    if commit["hash"] is not None:
        semver += f" ({commit['hash']})"
    infog.set_thumbnail(url=bot.user.avatar_url)
    infog.add_field(name="Server Info", value=get_server(), inline=False)
    infog.add_field(name="Statistik", value=(await fetch_bot_count_data()), inline=False)
    infog.add_field(name="Dibuat", value="Gak tau, tiba-tiba jadi.", inline=False)
    infog.add_field(name="Pembuat", value=(await creator_info(ctx)), inline=False)
    infog.add_field(name="Bahasa", value=get_version(), inline=False)
    infog.add_field(name="Fungsi", value="Menagih utang fansub (!help)", inline=False)
    infog.add_field(name="Uptime", value=create_uptime())
    infog.set_footer(
        text=f"naoTimes versi {semver} || Dibuat oleh N4O#8868", icon_url="https://p.n4o.xyz/i/nao250px.png",
    )
    await ctx.send(embed=infog)


@bot.command()
async def uptime(ctx):
    up = create_uptime()
    await ctx.send(f":alarm_clock: {up}")


@bot.command()
@commands.is_owner()
async def reloadconf(ctx):
    msg = await ctx.send("Please wait...")
    bot.logger.info("rereading config files...")
    new_config = await read_files("config.json")
    bot.logger.info("Loading crypto data...")
    crypto_data = await read_files("cryptodata.json")
    bot.logger.info("Loading currency data...")
    currency_data = await read_files("currencydata.json")
    bot.logger.info("Loading streaming lists data...")
    streams_list = await read_files("streaming_lists.json")

    default_prefix = new_config["default_prefix"]

    await msg.edit(content="Reassigning attributes")

    if "redisdb" not in new_config:
        bot.logger.error("Redis DB is not setup, please setup Redis before continuing!")
        await ctx.send("Cannot reload config since the provided Redis Config is wrong! Stopping bot!")
        raise SystemExit
    if not new_config["redisdb"]:
        bot.logger.error("Redis DB is not setup, please setup Redis before continuing!")
        await ctx.send("Cannot reload config since the provided Redis Config is wrong! Stopping bot!")
        raise SystemExit
    redis_conf = new_config["redisdb"]
    if "ip_hostname" not in redis_conf or "port" not in redis_conf:
        bot.logger.error("Redis DB is not setup, please setup Redis before continuing!")
        await ctx.send("Cannot reload config since the provided Redis Config is wrong! Stopping bot!")
        raise SystemExit
    if not redis_conf["ip_hostname"] or not redis_conf["port"]:
        bot.logger.error("Redis DB is not setup, please setup Redis before continuing!")
        await ctx.send("Cannot reload config since the provided Redis Config is wrong! Stopping bot!")
        raise SystemExit

    logger.info("Disconnecting old redis connection!")
    await bot.redisdb.close()

    redis_conn = RedisBridge(
        redis_conf["ip_hostname"], redis_conf["port"], redis_conf.get("password", None), bot.loop
    )
    logger.info("Connecting to RedisDB...")
    await redis_conn.connect()
    logger.info("Connected to RedisDB!")
    bot.redisdb = redis_conn

    bot.botconf = new_config
    try:
        mongo_conf = new_config["mongodb"]
        bot.logger.info("starting new database connection")
        nt_db = naoTimesDB(mongo_conf["ip_hostname"], mongo_conf["port"], mongo_conf["dbname"])
        await nt_db.validate_connection()
        bot.logger.info("connected to database...")
        bot.ntdb = nt_db
    except pymongo.errors.PyMongoError:
        bot.logger.error("failed to connect to database...")
        bot.ntdb = None
    if bot.fsdb is not None:
        bot.logger.info("restarting fansubdb connection")
        _, fsdb_conn = await initialize_fsdb(new_config)
        if fsdb_conn is not None:
            await bot.fsdb.close()
            bot.fsdb = fsdb_conn
    if bot.vndb_socket is not None:
        bot.logger.info("restarting vndb connection")
        _, vndb_io = await initialize_vndb(new_config, bot.loop)
        if vndb_io is not None:
            await bot.vndb_socket.close()
            bot.vndb_socket = vndb_io
    if bot.kbbi.terautentikasi:
        bot.logger.info("restarting kbbi connection")
        _, kbbi_conn = await initialize_kbbi(new_config)
        if kbbi_conn is not None:
            await bot.kbbi.tutup()
            bot.kbbi = kbbi_conn
    logger.info("Refetching prefixes data...")
    srv_prefixes = await redis_conn.getalldict("ntprefix_*")
    fmt_prefixes = {}
    for srv, pre in srv_prefixes.items():
        fmt_prefixes[srv[9:]] = pre
    bot.command_prefix = partial(prefixes_with_data, prefixes_data=fmt_prefixes, default=default_prefix)
    bot.jsdb_streams = streams_list
    bot.jsdb_currency = currency_data
    bot.jsdb_crypto = crypto_data

    prefix = bot.command_prefix
    if callable(prefix):
        prefix = prefix(bot, "[]")
    if isinstance(prefix, (list, tuple)):
        bot.prefix = prefix[0]
    else:
        bot.prefix = prefix

    if "error_logger" in new_config and new_config["error_logger"] is not None:
        channel_data = bot.get_channel(new_config["error_logger"])
        if channel_data is not None:
            bot.error_logger = new_config["error_logger"]

    await msg.edit(content="Reloading all cogs...")
    bot.logger.info("reloading cogs...")
    failed_cogs = []
    for cogs in cogs_list:
        try:
            bot.logger.info(f"Re-loading {cogs}")
            bot.reload_extension(cogs)
            bot.logger.info(f"reloaded {cogs}")
        except commands.ExtensionNotLoaded:
            bot.logger.warning(f"{cogs} haven't been loaded yet...")
            try:
                bot.logger.info(f"loading {cogs}")
                bot.load_extension(cogs)
                bot.logger.info(f"{cogs} loaded")
            except commands.ExtensionFailed as cer:
                bot.logger.error(f"failed to load {cogs}")
                bot.echo_error(cer)
                failed_cogs.append(cogs)
        except commands.ExtensionFailed as cer:
            bot.logger.error(f"failed to load {cogs}")
            bot.echo_error(cer)
            failed_cogs.append(cogs)

    bot.logger.info("finished reloading config.")
    msg_final = "Finished reloading cogs"
    if failed_cogs:
        ext_msg = "But it seems like some cogs failed to load/reload"
        ext_msg += "\n```\n{}\n```".format("\n".join(failed_cogs))
        msg_final += "\n{}".format(ext_msg)

    await msg.edit(content=msg_final)


@bot.command()
@commands.is_owner()
async def status(ctx):
    """Check bot status.
    This would check loaded cogs, unloaded cogs.
    status of kbbi/vndb/fsdb connection.

    Parameters
    ----------
    ctx : Context
        Bot context that are passed

    Returns
    -------
    None
    """
    bot.logger.info("checking loaded extensions...")
    loaded_extensions = list(dict(bot.extensions).keys())
    bot.logger.info("checking unloaded extensions...")
    unloaded_extensions = []
    for cl in cogs_list:
        if cl not in loaded_extensions:
            unloaded_extensions.append(cl)

    def yn_conn_stat(stat: bool) -> str:
        if stat:
            return "Connected"
        return "Not connected"

    loaded_extensions = [f"- {cogs}" for cogs in loaded_extensions]
    if unloaded_extensions:
        unloaded_extensions = [f"- {cogs}" for cogs in unloaded_extensions]

    bot.logger.info("checking kbbi/fsdb/vndb/ntdb connection...")
    if bot.kbbi is not None:
        is_kbbi_auth = bot.kbbi.terautentikasi
    else:
        is_kbbi_auth = False
    is_fsdb_loaded = bot.fsdb is not None
    is_vndb_loaded = bot.vndb_socket is not None
    is_db_loaded = bot.ntdb is not None

    bot_location = bot.get_hostdata.location

    bot.logger.info("generating status...")
    embed = discord.Embed(
        title="Bot Statuses", description=f"Bot Location: {bot_location}\nPrefix: {bot.prefix}"
    )
    embed.add_field(name="Loaded Cogs", value="```\n" + "\n".join(loaded_extensions) + "\n```", inline=False)
    if unloaded_extensions:
        embed.add_field(
            name="Unloaded Cogs", value="```\n" + "\n".join(unloaded_extensions) + "\n```", inline=False
        )
    con_stat_test = []
    if is_kbbi_auth:
        con_stat_test.append("**KBBI**: Authenticated.")
    else:
        con_stat_test.append("**KBBI**: Not authenticated.")
    con_stat_test.append(f"**VNDB**: {yn_conn_stat(is_vndb_loaded)}")
    if is_db_loaded:
        ntdb_text = "**naoTimesDB**: Connected [`"
        ip_ntdb = bot.botconf["mongodb"]["ip_hostname"].split(".")
        port_ntdb = bot.botconf["mongodb"]["port"]
        ip_masked = ["*" * len(ip) for ip in ip_ntdb[:3]]  # noqa: W605
        ip_masked.append(ip_ntdb[-1])
        ntdb_text += ".".join(ip_masked)
        ntdb_text += f":{port_ntdb}`]"
        con_stat_test.append(ntdb_text)
    else:
        con_stat_test.append("**naoTimesDB**: Not connected.")
    con_stat_test.append(f"**FansubDB**: {yn_conn_stat(is_fsdb_loaded)}")
    embed.add_field(name="Connection Status", value="\n".join(con_stat_test), inline=False)
    embed.set_footer(text=f"Versi {bot.semver}")
    await ctx.send(embed=embed)


@bot.command()
@commands.is_owner()
async def reload(ctx, *, cogs=None):
    """
    Restart salah satu module bot, owner only
    """
    if not cogs:
        helpcmd = HelpGenerator(bot, ctx, "Reload", desc="Reload module bot.",)
        helpcmd.embed.add_field(
            name="Module/Cogs List", value="\n".join(["- " + cl for cl in cogs_list]), inline=False,
        )
        return await ctx.send(embed=helpcmd.get())
    if not cogs.startswith("cogs."):
        cogs = "cogs." + cogs
    bot.logger.info(f"trying to reload {cogs}")
    msg = await ctx.send("Please wait, reloading module...")
    try:
        bot.logger.info(f"Re-loading {cogs}")
        bot.reload_extension(cogs)
        bot.logger.info(f"reloaded {cogs}")
    except commands.ExtensionNotLoaded:
        await msg.edit(content="Failed to reload module, trying to load it...")
        bot.logger.warning(f"{cogs} haven't been loaded yet...")
        try:
            bot.logger.info(f"trying to load {cogs}")
            bot.load_extension(cogs)
            bot.logger.info(f"{cogs} loaded")
        except commands.ExtensionFailed as cer:
            bot.logger.error(f"failed to load {cogs}")
            bot.echo_error(cer)
            return await msg.edit(content="Failed to (re)load module, please check bot logs.")
        except commands.ExtensionNotFound:
            bot.logger.warning(f"{cogs} doesn't exist.")
            return await msg.edit(content="Cannot find that module.")
    except commands.ExtensionNotFound:
        bot.logger.warning(f"{cogs} doesn't exist.")
        return await msg.edit(content="Cannot find that module.")
    except commands.ExtensionFailed as cef:
        bot.logger.error(f"failed to reload {cogs}")
        bot.echo_error(cef)
        return await msg.edit(content="Failed to (re)load module, please check bot logs.")

    await msg.edit(content=f"Successfully (re)loaded `{cogs}` module.")


@bot.command()
@commands.is_owner()
async def load(ctx, *, cogs=None):
    """
    Load salah satu module bot, owner only
    """
    if not cogs:
        helpcmd = HelpGenerator(bot, ctx, "Load", desc="Load module bot.",)
        helpcmd.embed.add_field(
            name="Module/Cogs List", value="\n".join(["- " + cl for cl in cogs_list]), inline=False,
        )
        return await ctx.send(embed=helpcmd.get())
    if not cogs.startswith("cogs."):
        cogs = "cogs." + cogs
    bot.logger.info(f"trying to load {cogs}")
    msg = await ctx.send("Please wait, loading module...")
    try:
        bot.logger.info(f"loading {cogs}")
        bot.load_extension(cogs)
        bot.logger.info(f"loaded {cogs}")
    except commands.ExtensionAlreadyLoaded:
        bot.logger.warning(f"{cogs} already loaded.")
        return await msg.edit(content="Module already loaded.")
    except commands.ExtensionNotFound:
        bot.logger.warning(f"{cogs} doesn't exist.")
        return await msg.edit(content="Cannot find that module.")
    except commands.ExtensionFailed as cef:
        bot.logger.error(f"failed to load {cogs}")
        bot.echo_error(cef)
        return await msg.edit(content="Failed to load module, please check bot logs.")

    await msg.edit(content=f"Successfully loaded `{cogs}` module.")


@bot.command()
@commands.is_owner()
async def unload(ctx, *, cogs=None):
    """
    Unload salah satu module bot, owner only
    """
    if not cogs:
        helpcmd = HelpGenerator(bot, ctx, "Unload", desc="Unload module bot.",)
        helpcmd.embed.add_field(
            name="Module/Cogs List", value="\n".join(["- " + cl for cl in cogs_list]), inline=False,
        )
        return await ctx.send(embed=helpcmd.get())
    if not cogs.startswith("cogs."):
        cogs = "cogs." + cogs
    bot.logger.info(f"trying to unload {cogs}")
    msg = await ctx.send("Please wait, unloading module...")
    try:
        bot.logger.info(f"unloading {cogs}")
        bot.unload_extension(cogs)
        bot.logger.info(f"unloaded {cogs}")
    except commands.ExtensionNotFound:
        bot.logger.warning(f"{cogs} doesn't exist.")
        return await msg.edit(content="Cannot find that module.")
    except commands.ExtensionNotLoaded:
        bot.logger.warning(f"{cogs} aren't loaded yet.")
        return await msg.edit(content="Module not loaded yet.")
    except commands.ExtensionFailed as cef:
        bot.logger.error(f"failed to unload {cogs}")
        bot.echo_error(cef)
        return await msg.edit(content="Failed to unload module, please check bot logs.")

    await msg.edit(content=f"Successfully unloaded `{cogs}` module.")


class PlaceHolderCommand:
    """
    A placeholder command for disabled, it replaced with a simple text

    Usage:
    ```py
    # Initialize first the class, then pass the send_placeholder command

    plch_cmd = PlaceHolderCommand(name="kbbi", reason="Website sangat tidak stabil untuk digunakan.")
    bot.add_command(commands.Command(plch_cmd.send_placeholder, name="kbbi"))
    ```
    """

    def __init__(self, name: str, reason: Optional[str] = None):
        """Initialize the PlaceHolderCommand class

        :param name: command name
        :type name: str
        :param reason: reason why that command is being disabled, or replaced by placeholder, defaults to None
        :type reason: Optional[str], optional
        """
        self.reason = reason
        self.name = name

    async def send_placeholder(self, ctx):
        send_msg = f"Perintah **`{self.name}`** dinon-aktifkan oleh owner bot ini."
        if self.reason is not None and self.reason != "":
            send_msg += f"\n**Alasan**: {self.reason}"
        await ctx.send(send_msg)


@bot.command()
@commands.is_owner()
async def disablecmd(ctx, *, cmd_name):
    """Disable a command"""
    try:
        splitted_data = cmd_name.split("-")
        cmd_name = splitted_data[0]
        reason_for = "-".join(splitted_data[1:])
    except ValueError:
        reason_for = None
    cmd_name = cmd_name.rstrip().lower()
    bot.logger.info(f"disabling: {cmd_name}")
    if cmd_name in ("disablecmd", "enablecmd"):
        bot.logger.warning("command on not allowed list")
        return await ctx.send("Tidak bisa menon-aktifkan command `disablecmd` atau `enablecmd`")
    if bot.copy_of_commands.get(cmd_name) is not None:
        bot.logger.error("command is already disabled.")
        return await ctx.send("Command tersebut sudah dinon-aktifkan.")

    command_data: commands.Command = bot.remove_command(cmd_name)
    if command_data is None:
        bot.logger.error(f"{cmd_name}: command not found.")
        return await ctx.send("Tidak dapat menemukan command tersebut.")
    old_cmd_aliases = command_data.aliases
    for alias in old_cmd_aliases:
        # Try to remove it just in case owner remove the alias only.
        bot.logger.info(f"{cmd_name}: removing `{alias}` alias...")
        bot.remove_command(alias)
    old_cmd_name = command_data.name
    if cmd_name in old_cmd_aliases:
        bot.logger.info(f"{cmd_name}: removing the cmd from bot since the user provided aliases.")
        bot.remove_command(old_cmd_name)
    bot.logger.info(f"{cmd_name}: adding a placeholder command.")
    plch_cmd = PlaceHolderCommand(name=old_cmd_name, reason=reason_for)
    bot.add_command(commands.Command(plch_cmd.send_placeholder, name=old_cmd_name, aliases=old_cmd_aliases))
    bot.copy_of_commands[cmd_name] = command_data
    bot.logger.info(f"{cmd_name}: command successfully disabled.")
    await ctx.send(f"Command `{old_cmd_name}` berhasil dinon-aktifkan.")


@bot.command()
@commands.is_owner()
async def enablecmd(ctx, *, cmd_name):
    cmd_name = cmd_name.rstrip().lower()
    bot.logger.info(f"enabling: {cmd_name}")
    try:
        command_data = bot.copy_of_commands.pop(cmd_name)
    except KeyError:
        bot.logger.error(f"{cmd_name}: command not found.")
        return await ctx.send("Tidak dapat menemukan command tersebut.")
    if command_data is None:
        bot.logger.error(f"{cmd_name}: command not found.")
        return await ctx.send("Tidak dapat menemukan command tersebut.")
    # Remove the placeholder command.
    bot.logger.error(f"{cmd_name}: command not found.")
    old_cmd_data = bot.remove_command(cmd_name)
    if old_cmd_data is None:
        bot.logger.error(f"{cmd_name}: for some unknown reason, it cannot found the command.")
        return await ctx.send("Entah kenapa, bot tidak bisa menemukan command tersebut.")
    for alias in old_cmd_data.aliases:
        bot.logger.info(f"{cmd_name}: removing `{alias}` alias...")
        bot.remove_command(alias)
    if cmd_name in old_cmd_data.aliases:
        bot.logger.info(f"{cmd_name}: removing the cmd from bot since the user provided aliases.")
        bot.remove_command(old_cmd_data.name)
    try:
        bot.logger.info(f"{cmd_name}: readding command...")
        bot.add_command(command_data)
    except commands.CommandRegistrationError as cre:
        bot.logger.error(f"{cmd_name}: command failed to registered.")
        bot.echo_error(cre)
        return await ctx.send("Tidak dapat meregistrasi ulang command.")
    bot.logger.info(f"{cmd_name}: command successfully enabled.")
    await ctx.send(f"Command `{cmd_name}` berhasil diaktifkan kembali.")


@bot.command()  # noqa: F811
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def prefix(ctx, *, msg=None):
    server_message = str(ctx.message.guild.id)
    bot.logger.info(f"requested at {server_message}")
    srv_pre = await bot.redisdb.get(f"ntprefix_{server_message}")
    if not msg:
        helpcmd = HelpGenerator(bot, ctx, "Prefix", color=0x00AAAA)
        helpcmd.embed.add_field(
            name="Prefix Server", value="Tidak ada" if srv_pre is None else srv_pre, inline=False,
        )
        await helpcmd.generate_aliases()
        return await ctx.send(embed=helpcmd.get())

    deletion = False
    if msg in ["clear", "bersihkan", "hapus"]:
        res = await bot.redisdb.rm(f"ntprefix_{server_message}")
        deletion = True
        if res:
            bot.logger.info(f"{server_message}: removing custom prefix...")
            send_txt = "Berhasil menghapus custom prefix dari server ini"
        else:
            return await ctx.send("Tidak ada prefix yang terdaftar untuk server ini, mengabaikan...")

    if srv_pre is not None and not deletion:
        bot.logger.info(f"{server_message}: changing custom prefix...")
        send_txt = "Berhasil mengubah custom prefix ke `{pre_}` untuk server ini"
    elif srv_pre is None and not deletion:
        bot.logger.info(f"{server_message}: adding custom prefix...")
        send_txt = "Berhasil menambah custom prefix `{pre_}` untuk server ini"

    if not deletion:
        await bot.redisdb.set(f"ntprefix_{server_message}", msg)
    prefix_data = await bot.redisdb.getalldict("ntprefix_*")
    new_prefix_fmt = {}
    for srv, pre in prefix_data.items():
        new_prefix_fmt[srv[9:]] = pre
    bot.command_prefix = partial(
        prefixes_with_data, prefixes_data=new_prefix_fmt, default=bot.botconf["default_prefix"],
    )
    bot.prefix = bot.prefixes("[]")

    bot.logger.info("reloading all cogs.")
    loaded_extensions = list(dict(bot.extensions).keys())
    failed_cogs = []
    for cogs in loaded_extensions:
        try:
            bot.logger.info(f"Re-loading {cogs}")
            bot.reload_extension(cogs)
            bot.logger.info(f"reloaded {cogs}")
        except commands.ExtensionNotLoaded:
            bot.logger.warning(f"{cogs} haven't been loaded yet...")
            try:
                bot.logger.info(f"loading {cogs}")
                bot.load_extension(cogs)
                bot.logger.info(f"{cogs} loaded")
            except commands.ExtensionFailed as cer:
                bot.logger.error(f"failed to load {cogs}")
                bot.echo_error(cer)
                failed_cogs.append(cogs)
        except commands.ExtensionFailed as cer:
            bot.logger.error(f"failed to load {cogs}")
            bot.echo_error(cer)
            failed_cogs.append(cogs)

    if failed_cogs:
        bot.logger.warning("there's cogs that failed\n{}".format("\n".join(failed_cogs)))

    await ctx.send(send_txt.format(pre_=msg))


@prefix.error
async def prefix_error(error, ctx: commands.Context):
    if isinstance(error, commands.errors.CheckFailure):
        try:
            server_message = str(ctx.message.guild.id)
        except (AttributeError, KeyError, ValueError):
            return await ctx.send("Hanya bisa dijalankan di sebuah server!")
        srv_pre = await bot.redisdb.get(f"ntprefix_{server_message}")
        helpcmd = HelpGenerator(bot, ctx, "Prefix", color=0x00AAAA)
        helpcmd.embed.add_field(
            name="Prefix Server", value="Tidak ada" if srv_pre is None else srv_pre, inline=False,
        )
        await helpcmd.generate_aliases()
        await ctx.send(embed=helpcmd.get())


# All of the code from here are mainly a copy of discord.Client.run()
# function, which have been readjusted to fit my needs.
async def run_bot(*args, **kwargs):
    try:
        await bot.start(*args, **kwargs)
    finally:
        await bot.close()


def stop_stuff_on_completion(_):
    bot.logger.info("Closing queue loop.")
    if hasattr(bot, "showqueue") and bot.showqueue is not None:
        async_loop.run_until_complete(bot.showqueue.shutdown())
    bot.logger.info("Shutting down fsdb connection...")
    if hasattr(bot, "fsdb") and bot.fsdb is not None:
        async_loop.run_until_complete(bot.fsdb.close())
    bot.logger.info("Shutting down KBBI and VNDB connection...")
    if hasattr(bot, "kbbi") and bot.kbbi is not None:
        async_loop.run_until_complete(bot.kbbi.tutup())
    if hasattr(bot, "vndb_socket") and bot.vndb_socket is not None:
        async_loop.run_until_complete(bot.vndb_socket.close())
    if hasattr(bot, "jisho") and bot.jisho is not None:
        async_loop.run_until_complete(bot.jisho.close())
    bot.logger.info("Closing Redis Connection...")
    async_loop.run_until_complete(bot.redisdb.close())
    garbage_collector.stop()
    async_loop.stop()


def cancel_all_tasks(loop):
    """A copy of discord.Client _cancel_tasks function

    :param loop: [description]
    :type loop: [type]
    """
    try:
        try:
            task_retriever = asyncio.Task.all_tasks
        except AttributeError:
            # future proofing for 3.9 I guess
            task_retriever = asyncio.all_tasks

        tasks = {t for t in task_retriever(loop=loop) if not t.done()}

        if not tasks:
            return

        bot.logger.info("Cleaning up after %d tasks.", len(tasks))
        for task in tasks:
            task.cancel()

        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        bot.logger.info("All tasks finished cancelling.")

        for task in tasks:
            if task.cancelled():
                continue
            if task.exception() is not None:
                loop.call_exception_handler(
                    {
                        "message": "Unhandled exception during Client.run shutdown.",
                        "exception": task.exception(),
                        "task": task,
                    }
                )
        if sys.version_info >= (3, 6):
            loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        bot.logger.info("Closing the event loop.")


future = asyncio.ensure_future(run_bot(bot.botconf["bot_token"], bot=True, reconnect=True))
future.add_done_callback(stop_stuff_on_completion)
try:
    garbage_collector.start()
    bot.loop.create_task(change_bot_presence())
    async_loop.run_forever()
    # bot.run()
except (KeyboardInterrupt, SystemExit, SystemError):
    bot.logger.info("Received signal to terminate bot.")
finally:
    future.remove_done_callback(stop_stuff_on_completion)
    bot.logger.info("Cleaning up tasks.")
    cancel_all_tasks(async_loop)

if not future.cancelled():
    try:
        future.result()
    except KeyboardInterrupt:
        pass
