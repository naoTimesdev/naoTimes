# -*- coding: utf-8 -*-

import argparse
import asyncio
import glob
import logging
import os
import pathlib
import sys
import time
import traceback
from datetime import datetime, timezone
from functools import partial
from itertools import cycle
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from nthelper.anibucket import AnilistBucket
from nthelper.bot import naoTimesBot
from nthelper.fsdb import FansubDBBridge
from nthelper.kbbiasync import KBBI, AutentikasiKBBI
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
discord_intents: Optional[discord.Intents] = None
if discord_ver_tuple >= (1, 5, 0):
    logger.info("Detected discord.py version 1.5.0, using the new Intents system...")
    # Enable all except Presences.
    discord_intents = discord.Intents.all()
    discord_intents.presences = False

parser = argparse.ArgumentParser("naotimesbot")
parser.add_argument("-dcog", "--disable-cogs", default=[], action="append", dest="cogs_skip")
parser.add_argument("-skbbi", "--skip-kbbi-check", action="store_true", dest="kbbi_check")
parser.add_argument("-sshow", "--skip-showtimes-fetch", action="store_true", dest="showtimes_fetch")
args_parsed = parser.parse_args()


def announce_error(error):
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    logger.error("Exception occured\n" + "".join(tb))


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
                kbbi_cls.set_autentikasi(cookie=cookie_baru, expiry=round(current_dt + (15 * 24 * 60 * 60)))
    logger.info("kbbi auth restored, resetting connection.")
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


async def init_bot(loop):
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
    logger.info("Loading prefixes data...")
    srv_prefixes = await read_files("server_prefixes.json")

    if not args_parsed.kbbi_check:
        kbbi_conn = await initialize_kbbi(config)
    else:
        kbbi_conn = KBBI()

    use_fsdb, fsdb_bridge = await initialize_fsdb(config)
    use_vndb, vndb_conn = await initialize_vndb(config, loop)

    cwd = str(pathlib.Path(__file__).parent.absolute())
    temp_folder = os.path.join(cwd, "automod")
    if not os.path.isdir(temp_folder):
        os.makedirs(temp_folder)
    fsrss_folder = os.path.join(cwd, "fansubrss_data")
    if not os.path.isdir(fsrss_folder):
        os.makedirs(fsrss_folder)
    showtimes_folder = os.path.join(cwd, "showtimes_folder")
    if not os.path.isdir(showtimes_folder):
        os.makedirs(showtimes_folder)

    default_prefix = config["default_prefix"]

    try:
        logger.info("Initiating discord.py")
        description = "Penyuruh Fansub biar kerja cepat\n"
        description += f"versi {__version__} || Dibuat oleh: N4O#8868"
        prefixes = partial(prefixes_with_data, prefixes_data=srv_prefixes, default=default_prefix)
        if discord_ver_tuple >= (1, 5, 0):
            # Insert intents
            bot = naoTimesBot(
                command_prefix=prefixes, description=description, intents=discord_intents, loop=loop
            )
        else:
            bot = naoTimesBot(command_prefix=prefixes, description=description, loop=loop)
        bot.remove_command("help")
        bot.logger.info("Bot loaded, now using bot logger for logging.")
        # if not hasattr(bot, "logger"):
        #     bot.logger = logger
        bot.botconf = config
        bot.automod_folder = temp_folder
        bot.semver = __version__
        bot.logger.info("Binding JSON dataset...")
        bot.jsdb_streams = streams_list
        bot.jsdb_currency = currency_data
        bot.jsdb_crypto = crypto_data
        bot.fcwd = cwd
        bot.logger.info("Binding KBBI Connection...")
        bot.kbbi = kbbi_conn
        if use_fsdb:
            bot.logger.info("Binding FansubDB...")
            bot.fsdb = fsdb_bridge
        if use_vndb:
            bot.logger.info("Binding VNDB Socket Connection...")
            bot.vndb_socket = vndb_conn
        bot.logger.info("Binding ShowtimesQueue...")
        bot.showqueue = ShowtimesQueue(cwd)
        bot.logger.info("Binding AnilistBucket")
        bot.anibucket = AnilistBucket()
        bot.logger.info("Success Loading Discord.py")
    except Exception as exc:
        bot.logger.error("Failed to load Discord.py")
        announce_error(exc)
    return bot, config


# Initiate everything
logger.info(f"Initiating bot v{__version__}...")
logger.info("Setting up loop")
async_loop = asyncio.get_event_loop()
res = async_loop.run_until_complete(init_bot(async_loop))
bot: naoTimesBot = res[0]
bot_config: dict = res[1]
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
    "Membeli waifu di toko terdekat | !help" "Reinkarnasi Fansub mati | !help",
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
    bot.logger.info("---------------------------------------------------------------")
    prefix = bot.command_prefix
    if callable(prefix):
        prefix = prefix(bot, "[]")
    if isinstance(prefix, (list, tuple)):
        bot.prefix = prefix[0]
    else:
        bot.prefix = prefix
    if "mongodb" in bot.botconf:
        mongos = bot.botconf["mongodb"]
        bot.ntdb = naoTimesDB(mongos["ip_hostname"], mongos["port"], mongos["dbname"])
        try:
            await bot.ntdb.validate_connection()
            bot.logger.info("Connected to naoTimes Database:")
            bot.logger.info("IP:Port: {}:{}".format(mongos["ip_hostname"], mongos["port"]))
            bot.logger.info("Database: {}".format(mongos["dbname"]))
            bot.logger.info("---------------------------------------------------------------")
            if not args_parsed.showtimes_fetch:
                bot.logger.info("Fetching nao_showtimes from server db to local json")
                js_data = await bot.ntdb.fetch_all_as_json()
                showtimes_folder = os.path.join(bot.fcwd, "showtimes_folder")
                if not os.path.isdir(showtimes_folder):
                    os.makedirs(showtimes_folder)
                for fn, fdata in js_data.items():
                    svfn = os.path.join(showtimes_folder, f"{fn}.showtimes")
                    bot.logger.info(f"showtimes: saving to file {fn}")
                    if fn == "supermod":
                        svfn = os.path.join(showtimes_folder, "super_admin.json")
                    await write_files(fdata, svfn)
                bot.logger.info("File fetched and saved to local json")
                bot.logger.info(
                    "---------------------------------------------------------------"
                )  # noqa: E501
        except Exception:
            bot.logger.error("Failed to validate if database is up and running.")
            bot.logger.error("IP:Port: {}:{}".format(mongos["ip_hostname"], mongos["port"]))
            bot.ntdb = None
            bot.logger.info("---------------------------------------------------------------")  # noqa: E501
    if not hasattr(bot, "uptime"):
        bot.uptime = datetime.now(tz=timezone.utc).timestamp()
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
        except Exception as e:
            bot.logger.error(f"Failed to load {load} module")
            bot.echo_error(e)
    bot.logger.info("[#][@][!] All cogs/extensions loaded.")
    bot.logger.info("---------------------------------------------------------------")
    bot.logger.info("Bot Ready!")
    bot.logger.info("Using Python {}".format(sys.version))
    bot.logger.info("And Using Discord.py v{}".format(discord.__version__))
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
    bot.logger.info("---------------------------------------------------------------")


async def change_bot_presence():
    await bot.wait_until_ready()
    bot.logger.info("Loaded auto-presence.")
    presences = cycle(presence_status)

    while not bot.is_closed():
        await asyncio.sleep(30)
        current_status = next(presences)
        activity = discord.Game(name=current_status, type=3)
        await bot.change_presence(activity=activity)


async def send_hastebin(info):
    async with aiohttp.ClientSession() as session:
        async with session.post("https://hastebin.com/documents", data=str(info)) as resp:
            if resp.status == 200:
                return "Error Occured\nSince the log is way too long here's a hastebin logs.\nhttps://hastebin.com/{}.py".format(  # noqa: E501
                    (await resp.json())["key"]
                )


@bot.event
async def on_command_error(ctx, error):
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
    elif isinstance(error, commands.DisabledCommand):
        return await ctx.send(f"`{ctx.command}`` dinon-aktifkan.")
    elif isinstance(error, commands.NoPrivateMessage):
        try:
            return await ctx.author.send(f"`{ctx.command}`` tidak bisa dipakai di Private Messages.")
        except Exception:
            return

    current_time = datetime.now(tz=timezone.utc).timestamp()

    bot.logger.error("Ignoring exception in command {}:".format(ctx.command))
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
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
    embed.set_thumbnail(url="http://p.ihateani.me/1bnBuV9C")
    try:
        await bot.owner.send(embed=embed)
    except Exception:
        if len(msg) > 1900:
            msg = await send_hastebin(msg)
        await bot.owner.send(msg)
    await ctx.send(
        "**Error**: Insiden internal ini telah dilaporkan ke" " N4O#8868, mohon tunggu jawabannya kembali."
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
            if not user.bot:
                if user.id not in users_list:
                    users_list.append(user.id)

    total_valid_users = len(users_list)

    text_fmt = "Jumlah server: {}\nJumlah channels: {}\nJumlah pengguna: {}".format(  # noqa: E501
        total_server, total_channels, total_valid_users
    )

    async def fetch_servers(cwd: str) -> list:
        bot.logger.info("fetching with glob...")
        glob_re = os.path.join(cwd, "showtimes_folder", "*.showtimes")
        basename = os.path.basename
        all_showtimes = glob.glob(glob_re)
        all_showtimes = [os.path.splitext(basename(srv))[0] for srv in all_showtimes]
        return all_showtimes

    showtimes_servers = await fetch_servers(bot.fcwd)
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
    else:
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
        name="naoTimes",
        icon_url="https://slwordpress.rutgers.edu/wp-content/uploads/sites/98/2015/12/Info-I-Logo.png",  # noqa: E501
    )
    infog.set_thumbnail(url="https://puu.sh/D3x1l/7f97e14c74.png")
    infog.add_field(name="Server Info", value=get_server(), inline=False)
    infog.add_field(name="Statistik", value=(await fetch_bot_count_data()), inline=False)
    infog.add_field(name="Dibuat", value="Gak tau, tiba-tiba jadi.", inline=False)
    infog.add_field(name="Pembuat", value=(await creator_info(ctx)), inline=False)
    infog.add_field(name="Bahasa", value=get_version(), inline=False)
    infog.add_field(name="Fungsi", value="Menagih utang fansub (!help)", inline=False)
    infog.add_field(name="Uptime", value=create_uptime())
    infog.set_footer(
        text=f"naoTimes versi {bot.semver} || Dibuat oleh N4O#8868",
        icon_url="https://p.n4o.xyz/i/nao250px.png",
    )
    await ctx.send(embed=infog)


@bot.command()
async def uptime(ctx):
    uptime = create_uptime()
    await ctx.send(f":alarm_clock: {uptime}")


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
    bot.logger.info("Loading prefixes data...")
    srv_prefixes = await read_files("server_prefixes.json")

    default_prefix = new_config["default_prefix"]

    await msg.edit(content="Reassigning attributes")
    bot.botconf = new_config
    mongo_conf = new_config["mongodb"]
    bot.logger.info("starting new database connection")
    nt_db = naoTimesDB(mongo_conf["ip_hostname"], mongo_conf["port"], mongo_conf["dbname"])
    bot.logger.info("connected to database...")
    bot.ntdb = nt_db
    bot.command_prefix = partial(prefixes_with_data, prefixes_data=srv_prefixes, default=default_prefix)
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
async def reload(ctx, *, cogs=None):
    """
    Restart salah satu module bot, owner only
    """
    if not cogs:
        helpcmd = HelpGenerator(bot, "Reload", desc="Reload module bot.",)
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
        helpcmd = HelpGenerator(bot, "Load", desc="Load module bot.",)
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
        helpcmd = HelpGenerator(bot, "Unload", desc="Unload module bot.",)
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
    if not os.path.isfile("server_prefixes.json"):
        prefix_data = {}
        bot.logger.warning(".json file doesn't exist, making one...")
        await write_files({}, "server_prefixes.json")
    else:
        prefix_data = await read_files("server_prefixes.json")

    if not msg:
        helpcmd = HelpGenerator(bot, "Prefix", color=0x00AAAA)
        helpcmd.embed.add_field(
            name="Prefix Server", value=prefix_data.get(server_message, "Tidak ada"), inline=False,
        )
        await helpcmd.generate_aliases()
        return await ctx.send(embed=helpcmd.get())

    if msg in ["clear", "bersihkan", "hapus"]:
        if server_message in prefix_data:
            bot.logger.warning(f"{server_message}: deleting custom prefix...")
            del prefix_data[server_message]

            await write_files(prefix_data, "server_prefixes.json")

        return await ctx.send("Berhasil menghapus custom prefix dari server ini")

    if server_message in prefix_data:
        bot.logger.info(f"{server_message}: changing custom prefix...")
        send_txt = "Berhasil mengubah custom prefix ke `{pre_}` untuk server ini"
    else:
        bot.logger.info(f"{server_message}: adding custom prefix...")
        send_txt = "Berhasil menambah custom prefix `{pre_}` untuk server ini"
    prefix_data[server_message] = msg

    await write_files(prefix_data, "server_prefixes.json")
    bot.command_prefix = partial(
        prefixes_with_data, prefixes_data=prefix_data, default=bot.botconf["default_prefix"],
    )
    prefix = bot.command_prefix
    if callable(prefix):
        prefix = prefix(bot, "[]")
    if isinstance(prefix, (list, tuple)):
        bot.prefix = prefix[0]
    else:
        bot.prefix = prefix

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
async def prefix_error(self, error, ctx):
    if isinstance(error, commands.errors.CheckFailure):
        server_message = str(ctx.message.guild.id)
        if not os.path.isfile("prefixes.json"):
            prefix_data = {}
            bot.logger.warning(".json file doesn't exist, making one...")
            await write_files({}, "server_prefixes.json")
        else:
            prefix_data = await read_files("server_prefixes.json")
        helpcmd = HelpGenerator(bot, "Load", desc="Load module bot.", color=0x00AAAA)
        helpcmd.embed.add_field(
            name="Prefix Server", value=prefix_data.get(server_message, "Tidak ada"), inline=False,
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


def stop_stuff_on_completion(f):
    bot.logger.info("Closing queue loop.")
    async_loop.run_until_complete(bot.showqueue.shutdown())
    bot.logger.info("Shutting down fsdb connection...")
    async_loop.run_until_complete(bot.fsdb.close())
    bot.logger.info("Shutting down KBBI and VNDB connection...")
    async_loop.run_until_complete(bot.kbbi.tutup())
    async_loop.run_until_complete(bot.vndb_socket.close())
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
    async_loop.run_forever()
    bot.loop.create_task(change_bot_presence())
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
