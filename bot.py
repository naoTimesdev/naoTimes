# -*- coding: utf-8 -*-

import asyncio
import logging
import os
import pathlib
import sys
import time
import traceback
from datetime import datetime, timezone
from functools import partial
from itertools import cycle

import aiohttp
import discord
from discord.ext import commands

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
from nthelper.bot import naoTimesBot

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


def announce_error(error):
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    logger.error("Exception occured\n" + "".join(tb))


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
    logger.info("Opening KBBI auth files...")
    kbbi_auth = await read_files("kbbi_auth.json")
    kbbi_cookie = kbbi_auth["cookie"]
    kbbi_expires = kbbi_auth["expires"]
    kbbi_conf = config["kbbi"]

    if not kbbi_conf["skip_check"]:
        logger.info("Testing KBBI cookies...")
        current_dt = datetime.now(tz=timezone.utc).timestamp()
        kbbi_cls = KBBI("periksa", kbbi_cookie)
        is_kbbi_auth = await kbbi_cls.cek_auth()
        await kbbi_cls.tutup()
        if not is_kbbi_auth or current_dt >= kbbi_expires:
            logger.warning("kbbi cookie expired, generating new one...")
            kbbi_auth = AutentikasiKBBI(kbbi_conf["email"], kbbi_conf["password"])
            logger.warning("kbbi_auth: authenticating...")
            await kbbi_auth.autentikasi()
            cookie_baru = await kbbi_auth.ambil_cookies()
            logger.warning("saving new KBBI cookie...")
            new_data = {"cookie": cookie_baru, "expires": round(current_dt + (15 * 24 * 60 * 60))}
            await write_files(new_data, "kbbi_auth.json")
            kbbi_cookie = cookie_baru
            kbbi_expires = round(current_dt + (15 * 24 * 60 * 60))

    logger.info("Opening FSDB Token data...")
    fsdb_token = await read_files("fsdb_login.json")
    logger.info("Preparing FSDB Connection...")
    fsdb_bridge = FansubDBBridge(config["fansubdb"]["username"], config["fansubdb"]["password"])
    if not fsdb_token:
        logger.info("Authenticating (No saved token)...")
        await fsdb_bridge.authorize()
        fsdb_token = fsdb_bridge.token_data
        await write_files(fsdb_token, "fsdb_login.json")
    elif fsdb_token["expires"] is not None:
        if current_dt - 300 >= fsdb_token["expires"]:
            logger.info("Reauthenticating (Token expired)...")
            await fsdb_bridge.authorize()
            fsdb_token = fsdb_bridge.token_data
            await write_files(fsdb_token, "fsdb_login.json")
        else:
            logger.info("Setting FSDB token...")
            fsdb_bridge.set_token(fsdb_token["token"], fsdb_token["expires"])
    else:
        logger.info("Setting FSDB token...")
        fsdb_bridge.set_token(fsdb_token["token"], fsdb_token["expires"])

    cwd = str(pathlib.Path(__file__).parent.absolute())
    temp_folder = os.path.join(cwd, "automod")
    if not os.path.isdir(temp_folder):
        os.makedirs(temp_folder)

    default_prefix = config["default_prefix"]

    try:
        logger.info("Initiating discord.py")
        description = "Penyuruh Fansub biar kerja cepat\n"
        description += f"versi {__version__} || Dibuat oleh: N4O#8868"
        prefixes = partial(prefixes_with_data, prefixes_data=srv_prefixes, default=default_prefix,)
        bot = naoTimesBot(command_prefix=prefixes, description=description, loop=loop)
        bot.remove_command("help")
        # if not hasattr(bot, "logger"):
        #     bot.logger = logger
        if not hasattr(bot, "automod_folder"):
            bot.automod_folder = temp_folder
        if not hasattr(bot, "err_echo"):
            bot.err_echo = announce_error
        if not hasattr(bot, "semver"):
            bot.semver = __version__
        if not hasattr(bot, "jsdb_streams"):
            logger.info("Binding JSON dataset...")
            bot.jsdb_streams = streams_list
            bot.jsdb_currency = currency_data
            bot.jsdb_crypto = crypto_data
        if not hasattr(bot, "fcwd"):
            bot.fcwd = cwd
        if not hasattr(bot, "kbbi_cookie"):
            logger.info("Binding KBBI Cookies...")
            bot.kbbi_cookie = kbbi_cookie
            bot.kbbi_expires = kbbi_expires
            bot.kbbi_auth = {"email": kbbi_conf["email"], "password": kbbi_conf["password"]}
        if not hasattr(bot, "fsdb"):
            logger.info("Binding FansubDB...")
            bot.fsdb = fsdb_bridge
        if not hasattr(bot, "showqueue"):
            logger.info("Binding ShowtimesQueue...")
            bot.showqueue = ShowtimesQueue(cwd)
        logger.info("Success Loading Discord.py")
    except Exception as exc:
        logger.error("Failed to load Discord.py")
        announce_error(exc)
    return bot, config


# Initiate everything
logger.info(f"Initiating bot v{__version__}...")
logger.info("Setting up loop")
# if sys.platform == "win32":
#     logger.info("Detected win32, using ProactorEventLoop")
#     event_loop = asyncio.ProactorEventLoop()
#     asyncio.set_event_loop(event_loop)
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
    logger.info("[$] Connected to discord.")
    activity = discord.Game(name=presence_status[0], type=3)
    await bot.change_presence(activity=activity)
    logger.info("---------------------------------------------------------------")
    if not hasattr(bot, "showtimes_resync"):
        bot.showtimes_resync = []
    if not hasattr(bot, "botconf"):
        bot.botconf = bot_config
    if not hasattr(bot, "prefix"):
        prefix = bot.command_prefix
        if callable(prefix):
            prefix = prefix(bot, "[]")
        if isinstance(prefix, (list, tuple)):
            bot.prefix = prefix[0]
        else:
            bot.prefix = prefix
    if not hasattr(bot, "ntdb"):
        mongos = bot_config["mongodb"]
        bot.ntdb = naoTimesDB(mongos["ip_hostname"], mongos["port"], mongos["dbname"])
        logger.info("Connected to naoTimes Database:")
        logger.info("IP:Port: {}:{}".format(mongos["ip_hostname"], mongos["port"]))
        logger.info("Database: {}".format(mongos["dbname"]))
        logger.info("---------------------------------------------------------------")
        if not mongos["skip_fetch"]:
            logger.info("Fetching nao_showtimes from server db to local json")
            js_data = await bot.ntdb.fetch_all_as_json()
            showtimes_folder = os.path.join(bot.fcwd, "showtimes_folder")
            if not os.path.isdir(showtimes_folder):
                os.makedirs(showtimes_folder)
            for fn, fdata in js_data.items():
                svfn = os.path.join(showtimes_folder, f"{fn}.showtimes")
                logger.info(f"showtimes: saving to file {fn}")
                if fn == "supermod":
                    svfn = os.path.join(showtimes_folder, "super_admin.json")
                await write_files(fdata, svfn)
            logger.info("File fetched and saved to local json")
            logger.info("---------------------------------------------------------------")  # noqa: E501
    if not hasattr(bot, "uptime"):
        bot.owner = (await bot.application_info()).owner
        bot.uptime = time.time()
    logger.info("[#][@][!] Start loading cogs...")
    for load in cogs_list:
        try:
            logger.info("[#] Loading " + load + " module.")
            bot.load_extension(load)
            logger.info("[#] Loaded " + load + " module.")
        except Exception as e:
            logger.info("[!!] Failed Loading " + load + " module.")
            announce_error(e)
    logger.info("[#][@][!] All cogs/extensions loaded.")
    logger.info("---------------------------------------------------------------")
    logger.info("Bot Ready!")
    logger.info("Using Python {}".format(sys.version))
    logger.info("And Using Discord.py v{}".format(discord.__version__))
    logger.info("---------------------------------------------------------------")
    logger.info("Logged in as:")
    logger.info("Bot name: {}".format(bot.user.name))
    logger.info("With Client ID: {}".format(bot.user.id))
    logger.info("With naoTimes version: {}".format(__version__))
    logger.info("---------------------------------------------------------------")


async def change_bot_presence():
    await bot.wait_until_ready()
    logger.info("[@] Loaded auto-presence.")
    presences = cycle(presence_status)

    while not bot.is_closed:
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
        announce_error(error)
        return
    elif isinstance(error, commands.DisabledCommand):
        return await ctx.send(f"`{ctx.command}`` dinon-aktifkan.")
    elif isinstance(error, commands.NoPrivateMessage):
        try:
            return await ctx.author.send(f"`{ctx.command}`` tidak bisa dipakai di Private Messages.")
        except Exception:
            return

    current_time = time.time()

    logger.error("Ignoring exception in command {}:".format(ctx.command))
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    error_fmt = (
        "```An Error has occured...\nIn Command: {0.command}\nCogs: {0.command.cog_name}\nAuthor: {0.message.author} ({0.message.author.id})\n"  # noqa: E501
        "Server: {0.message.guild.id}\nMessage: {0.message.clean_content}".format(ctx)  # noqa: E501
    )
    msg = "```py\n{}```\n{}\n```py\n{}\n```".format(
        datetime.utcnow().strftime("%b/%d/%Y %H:%M:%S UTC") + "\n" + "ERROR!",
        error_fmt,
        "".join(tb).replace("`", ""),
    )

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
        name="Server Insiden", value="{0.guild.name} ({0.guild.id})".format(ctx.message), inline=False,
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
    announce_error(error)


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
    logger.info("checking websocket...")
    ws_ping = bot.latency
    logger.info("checking database...")
    db_res, db_ping = await bot.ntdb.ping_server()
    irnd = lambda t: int(round(t))  # noqa: E731

    logger.info("checking api.ihateani.me...")
    ihapi_res, ihaapi_ping = await ping_website("https://api.ihateani.me/")

    logger.info("checking anilist.co")
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
    logger.info("checking discord itself.")
    t1_dis = time.perf_counter()
    async with channel.typing():
        t2_dis = time.perf_counter()
        dis_ping = irnd((t2_dis - t1_dis) * 1000)
        logger.info("generating results....")
        logger.debug("generating discord res")
        text_res += f"\n{ping_emote(dis_ping)} Discord: `{dis_ping}ms`"

        logger.debug("generating websocket res")
        if ws_ping != float("nan"):
            ws_time = irnd(ws_ping * 1000)
            ws_res = f"{ping_emote(ws_time)} Websocket `{ws_time}ms`"
        else:
            ws_res = ":x: Websocket: `nan`"

        text_res += f"\n{ws_res}"
        logger.debug("generating db res")
        text_res += f"\n{_gen_text(db_res, db_ping, 'Database')}"
        logger.debug("generating ihaapi res")
        text_res += f"\n{_gen_text(ihapi_res, ihaapi_ping, 'naoTimes API')}"
        logger.debug("generating anilist res")
        text_res += f"\n{_gen_text(ani_res, ani_ping, 'Anilist.co')}"
        logger.info("sending results")
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

    # Showtimes
    if not os.path.isfile("nao_showtimes.json"):
        logger.warning("naoTimes are not initiated, skipping...")
        json_data = {}

    json_data = await read_files("nao_showtimes.json")

    text_fmt = "Jumlah server: {}\nJumlah channels: {}\nJumlah pengguna: {}".format(  # noqa: E501
        total_server, total_channels, total_valid_users
    )

    if not json_data:
        text_fmt += "\n\nJumlah server Showtimes: {}\nJumlah anime Showtimes: {}".format(0, 0)  # noqa: E501
    else:
        ntimes_srv = []
        total_animemes = 0
        for k in json_data:
            if k == "supermod":
                continue
            ntimes_srv.append(k)

        total_ntimes_srv = len(ntimes_srv)
        for srv in ntimes_srv:
            anime_keys = list(json_data[srv]["anime"].keys())
            total_animemes += len(anime_keys)
        text_fmt += "\n\nJumlah server Showtimes: {}\nJumlah anime Showtimes: {}".format(  # noqa: E501
            total_ntimes_srv, total_animemes
        )

    return "```" + text_fmt + "```"


def create_uptime():
    current_time = time.time()
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

    return_text = "`"
    if up_months != 0:
        return_text += "{} bulan ".format(up_months)

    return return_text + "{} minggu {} hari {} jam {} menit {} detik`".format(
        up_weeks, up_days, up_hours, up_minutes, up_secs
    )


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
    infog.add_field(name="Pembuat", value="{}".format(bot.owner.mention), inline=False)
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
    logger.info("rereading config files...")
    new_config = await read_files("config.json")
    logger.info("Loading crypto data...")
    crypto_data = await read_files("cryptodata.json")
    logger.info("Loading currency data...")
    currency_data = await read_files("currencydata.json")
    logger.info("Loading streaming lists data...")
    streams_list = await read_files("streaming_lists.json")
    logger.info("Loading prefixes data...")
    srv_prefixes = await read_files("server_prefixes.json")

    default_prefix = new_config["default_prefix"]

    await msg.edit(content="Reassigning attributes")
    bot.botconf = new_config
    mongo_conf = new_config["mongodb"]
    logger.info("starting new database connection")
    nt_db = naoTimesDB(mongo_conf["ip_hostname"], mongo_conf["port"], mongo_conf["dbname"])
    logger.info("connected to database...")
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
    logger.info("reloading cogs...")
    failed_cogs = []
    for cogs in cogs_list:
        try:
            logger.info(f"Re-loading {cogs}")
            bot.reload_extension(cogs)
            logger.info(f"reloaded {cogs}")
        except commands.ExtensionNotLoaded:
            logger.warning(f"{cogs} haven't been loaded yet...")
            try:
                logger.info(f"loading {cogs}")
                bot.load_extension(cogs)
                logger.info(f"{cogs} loaded")
            except commands.ExtensionFailed as cer:
                logger.error(f"failed to load {cogs}")
                announce_error(cer)
                failed_cogs.append(cogs)
        except commands.ExtensionFailed as cer:
            logger.error(f"failed to load {cogs}")
            announce_error(cer)
            failed_cogs.append(cogs)

    logger.info("finished reloading config.")
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
    logger.info(f"trying to reload {cogs}")
    msg = await ctx.send("Please wait, reloading module...")
    try:
        logger.info(f"Re-loading {cogs}")
        bot.reload_extension(cogs)
        logger.info(f"reloaded {cogs}")
    except commands.ExtensionNotFound:
        logger.warning(f"{cogs} doesn't exist.")
        return await msg.edit(content="Cannot find that module.")
    except commands.ExtensionFailed as cef:
        logger.error(f"failed to reload {cogs}")
        announce_error(cef)
        return await msg.edit(content="Failed to (re)load module, please check bot logs.")
    except commands.ExtensionNotLoaded:
        await msg.edit(content="Failed to reload module, trying to load it...")
        logger.warning(f"{cogs} haven't been loaded yet...")
        try:
            logger.info(f"trying to load {cogs}")
            bot.load_extension(cogs)
            logger.info(f"{cogs} loaded")
        except commands.ExtensionFailed as cer:
            logger.error(f"failed to load {cogs}")
            announce_error(cer)
            return await msg.edit(content="Failed to (re)load module, please check bot logs.")
        except commands.ExtensionNotFound:
            logger.warning(f"{cogs} doesn't exist.")
            return await msg.edit(content="Cannot find that module.")

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
    logger.info(f"trying to load {cogs}")
    msg = await ctx.send("Please wait, loading module...")
    try:
        logger.info(f"loading {cogs}")
        bot.load_extension(cogs)
        logger.info(f"loaded {cogs}")
    except commands.ExtensionNotFound:
        logger.warning(f"{cogs} doesn't exist.")
        return await msg.edit(content="Cannot find that module.")
    except commands.ExtensionFailed as cef:
        logger.error(f"failed to load {cogs}")
        announce_error(cef)
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
    logger.info(f"trying to load {cogs}")
    msg = await ctx.send("Please wait, unloading module...")
    try:
        logger.info(f"loading {cogs}")
        bot.unload_extension(cogs)
        logger.info(f"loaded {cogs}")
    except commands.ExtensionNotFound:
        logger.warning(f"{cogs} doesn't exist.")
        return await msg.edit(content="Cannot find that module.")
    except commands.ExtensionNotLoaded:
        logger.warning(f"{cogs} aren't loaded yet.")
        return await msg.edit(content="Module not loaded yet.")
    except commands.ExtensionFailed as cef:
        logger.error(f"failed to unload {cogs}")
        announce_error(cef)
        return await msg.edit(content="Failed to unload module, please check bot logs.")

    await msg.edit(content=f"Successfully unloaded `{cogs}` module.")


@bot.command()  # noqa: F811
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def prefix(ctx, *, msg=None):
    server_message = str(ctx.message.guild.id)
    logger.info(f"requested at {server_message}")
    if not os.path.isfile("server_prefixes.json"):
        prefix_data = {}
        logger.warning(".json file doesn't exist, making one...")
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
            logger.warning(f"{server_message}: deleting custom prefix...")
            del prefix_data[server_message]

            await write_files(prefix_data, "server_prefixes.json")

        return await ctx.send("Berhasil menghapus custom prefix dari server ini")

    if server_message in prefix_data:
        logger.info(f"{server_message}: changing custom prefix...")
        send_txt = "Berhasil mengubah custom prefix ke `{pre_}` untuk server ini"
    else:
        logger.info(f"{server_message}: adding custom prefix...")
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

    logger.info("reloading all cogs.")
    loaded_extensions = list(dict(bot.extensions).keys())
    failed_cogs = []
    for cogs in loaded_extensions:
        try:
            logger.info(f"Re-loading {cogs}")
            bot.reload_extension(cogs)
            logger.info(f"reloaded {cogs}")
        except commands.ExtensionNotLoaded:
            logger.warning(f"{cogs} haven't been loaded yet...")
            try:
                logger.info(f"loading {cogs}")
                bot.load_extension(cogs)
                logger.info(f"{cogs} loaded")
            except commands.ExtensionFailed as cer:
                logger.error(f"failed to load {cogs}")
                announce_error(cer)
                failed_cogs.append(cogs)
        except commands.ExtensionFailed as cer:
            logger.error(f"failed to load {cogs}")
            announce_error(cer)
            failed_cogs.append(cogs)

    if failed_cogs:
        logger.warning("there's cogs that failed\n{}".format("\n".join(failed_cogs)))

    await ctx.send(send_txt.format(pre_=msg))


@prefix.error
async def prefix_error(self, error, ctx):
    if isinstance(error, commands.errors.CheckFailure):
        server_message = str(ctx.message.guild.id)
        if not os.path.isfile("prefixes.json"):
            prefix_data = {}
            logger.warning(".json file doesn't exist, making one...")
            await write_files({}, "server_prefixes.json")
        else:
            prefix_data = await read_files("server_prefixes.json")
        helpcmd = HelpGenerator(bot, "Load", desc="Load module bot.", color=0x00AAAA)
        helpcmd.embed.add_field(
            name="Prefix Server", value=prefix_data.get(server_message, "Tidak ada"), inline=False,
        )
        await helpcmd.generate_aliases()
        await ctx.send(embed=helpcmd.get())


try:
    bot.loop.create_task(change_bot_presence())
    bot.run(bot_config["bot_token"], bot=True, reconnect=True)
except (KeyboardInterrupt, SystemExit, SystemError):
    logger.warning("Logging out...")
    async_loop.run_until_complete(bot.logout())
    logger.warning("Disconnecting from discord...")
    async_loop.run_until_complete(bot.close())
finally:
    logger.warning("Closing queue loop.")
    async_loop.run_until_complete(bot.showqueue.shutdown())
    logger.warning("Shutting down fsdb connection...")
    async_loop.run_until_complete(bot.fsdb.close())
    logger.warning("Closing async loop.")
    async_loop.stop()
    async_loop.close()
