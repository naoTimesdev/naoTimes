# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from itertools import cycle

import aiohttp
import discord
import requests
from discord.ext import commands
from .nthelper import naoTimesDB

cogs_list = ['cogs.' + x.replace('.py', '') for x in os.listdir('cogs') if x.endswith('.py')]

async def fetch_newest_db(CONFIG_DATA):
    """
    Fetch the newest naoTimes database from github
    """
    print('[#] Fetching newest naoTimes database...')
    if CONFIG_DATA['gist_id'] == "":
        return print('[#] naoTimes are not setted up, skipping...')
    url = 'https://gist.githubusercontent.com/{u}/{g}/raw/nao_showtimes.json'
    url_rss = 'https://gist.githubusercontent.com/{u}/{g}/raw/fansubrss.json'
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                headers = {'User-Agent': 'naoTimes v2.0'}
                print('\t[#] Fetching nao_showtimes.json')
                async with session.get(url.format(u=CONFIG_DATA['github_info']['username'], g=CONFIG_DATA['gist_id']), headers=headers) as r:
                    try:
                        r_data = await r.text()
                        js_data = json.loads(r_data)
                        with open('nao_showtimes.json', 'w') as f:
                            json.dump(js_data, f, indent=4)
                        print('\t[@] Fetched and saved.')
                    except IndexError:
                        continue
                print('\t[#] Fetching fansubrss.json')
                async with session.get(url_rss.format(u=CONFIG_DATA['github_info']['username'], g=CONFIG_DATA['gist_id']), headers=headers) as r:
                    try:
                        r_data = await r.text()
                        js_data = json.loads(r_data)
                        with open('fansubrss.json', 'w') as f:
                            json.dump(js_data, f, indent=4)
                        print('[@] Fetched and saved.')
                    except IndexError:
                        continue
                break
            except aiohttp.ClientError:
                continue

def prefixes(bot, message):
    """
    A modified version of discord.ext.command.when_mentioned_or
    """
    server = message.guild

    with open('prefixes.json') as f:
        pre = json.load(f)
    default_ = "!"

    pre_data = []
    pre_ = None
    if server:
        id_srv = str(server.id)
        pre_ = pre.get(id_srv)
    if not pre_:
        pre_data.append(default_)
    else:
        pre_data.append(pre_)
    if 'ntd.' not in pre_data:
        pre_data.append('ntd.')
    pre_data = [bot.user.mention + ' ', '<@!%s> ' % bot.user.id] + pre_data

    return pre_data

async def init_bot():
    """
    Start loading all the bot process
    Will start:
        - Logging
        - discord.py and the modules
        - Fetching naoTimes main database
        - Setting some global variable
    """
    print('[@] Initializing logger...')
    logger = logging.getLogger('discord')
    logger.setLevel(logging.ERROR)
    handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)

    print('[@] Looking up config')
    with open('config.json', 'r') as fp:
        config = json.load(fp)

    try:
        print('[@] Initiating discord.py')
        description = '''Penyuruh Fansub biar kerja cepat\nversi 2.0.0 || Dibuat oleh: N4O#8868'''
        bot = commands.Bot(command_prefix=prefixes, description=description)
        bot.remove_command('help')
        await fetch_newest_db(config)
        print('[@!!] Success Loading Discord.py')
    except Exception as exc:
        print('[#!!] Failed to load Discord.py ###')
        print('\t' + str(exc))
    return bot, config, logger

# Initiate everything
print('[@] Initiating bot...')
async_loop = asyncio.get_event_loop()
bot, bot_config, logger = async_loop.run_until_complete(init_bot())
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
    "Membeli waifu di toko terdekat | !help"
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
    "Judul Anime - Episode (v9999) | !help"
]

@bot.event
async def on_ready():
    """Bot loaded here"""
    print('[$] Connected to discord.')
    activity = discord.Game(name=presence_status[0], type=3)
    await bot.change_presence(activity=activity)
    print('---------------------------------------------------------------')
    print('Bot Ready!')
    print('Using Python {}'.format(sys.version))
    print('And Using Discord.py v{}'.format(discord.__version__))
    print('---------------------------------------------------------------')
    print('Logged in as:')
    print('Bot name: {}'.format(bot.user.name))
    print('With Client ID: {}'.format(bot.user.id))
    print('---------------------------------------------------------------')
    if not hasattr(bot, "ntdb"):
        mongos = bot_config['mongodb']
        bot.ntdb = naoTimesDB(mongos['ip_hostname'], mongos['port'], mongos['dbname'])
        print('Connected to naoTimes Database:')
        print('IP:Port: {}:{}'.format(mongos['ip_hostname'], mongos['port']))
        print('Database: {}'.format(mongos['dbname']))
        print('---------------------------------------------------------------')
    if not hasattr(bot, 'uptime'):
        bot.owner = (await bot.application_info()).owner
        bot.uptime = time.time()
        print('[#][@][!] Start loading cogs...')
        for load in cogs_list:
            try:
                print('[#] Loading ' + load + ' module.')
                bot.load_extension(load)
                print('[#] Loaded ' + load + ' module.')
            except Exception as e:
                print('[!!] Failed Loading ' + load + ' module.')
                print('\t' + str(e))
        print('[#][@][!] All cogs/extensions loaded.')
        print('---------------------------------------------------------------')

async def change_bot_presence():
    await bot.wait_until_ready()
    print('[@] Loaded auto-presence.')
    presences = cycle(presence_status)

    while not bot.is_closed:
        await asyncio.sleep(30)
        current_status = next(presences)
        activity = discord.Game(name=current_status, type=3)
        await bot.change_presence(activity=activity)

async def send_hastebin(info):
    print(info)
    async with aiohttp.ClientSession() as session:
        async with session.post("https://hastebin.com/documents", data = str(info)) as resp:
            if resp.status is 200:
                return "Error Occured\nSince the log is way too long here's a hastebin logs.\nhttps://hastebin.com/{}.py".format((await resp.json())["key"])

@bot.event
async def on_command_error(ctx, error):
    """The event triggered when an error is raised while invoking a command.
    ctx   : Context
    error : Exception"""

    if hasattr(ctx.command, 'on_error'):
        return

    ignored = (commands.CommandNotFound, commands.UserInputError, commands.NotOwner)
    error = getattr(error, 'original', error)

    if isinstance(error, ignored):
        return
    elif isinstance(error, commands.DisabledCommand):
        return await ctx.send(f'`{ctx.command}`` dinon-aktifkan.')
    elif isinstance(error, commands.NoPrivateMessage):
        try:
            return await ctx.author.send(f'`{ctx.command}`` tidak bisa dipakai di Private Messages.')
        except:
            pass

    current_time = time.time()

    print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    error_fmt = "```An Error has occured...\nIn Command: {0.command}\nCogs: {0.command.cog_name}\nAuthor: {0.message.author} ({0.message.author.id})\n" \
                    "Server: {0.message.guild.id}\nMessage: {0.message.clean_content}".format(ctx)
    msg ="```py\n{}```\n{}\n```py\n{}\n```".format(datetime.utcnow().strftime("%b/%d/%Y %H:%M:%S UTC") + "\n"+ "ERROR!",error_fmt,"".join(tb).replace("`",""))

    embed = discord.Embed(title="Error Logger", colour=0xff253e, description="Terjadi kesalahan atau Insiden baru-baru ini...", timestamp=datetime.utcfromtimestamp(current_time))
    embed.add_field(name="Cogs", value="[nT!] {0.cog_name}".format(ctx.command), inline=False)
    embed.add_field(name="Perintah yang dipakai", value="{0.command}\n`{0.message.clean_content}`".format(ctx), inline=False)
    embed.add_field(name="Server Insiden", value="{0.guild.name} ({0.guild.id})".format(ctx.message), inline=False)
    embed.add_field(name="Orang yang memakainya", value="{0.author.name}#{0.author.discriminator} ({0.author.id})".format(ctx.message), inline=False)
    embed.add_field(name="Traceback", value="```py\n{}\n```".format("".join(tb)), inline=True)
    embed.set_thumbnail(url="http://p.ihateani.me/1bnBuV9C")
    try:
        await bot.owner.send(embed=embed)
    except:
        if len(msg) > 1900:
            msg = await send_hastebin(msg)
        await bot.owner.send(msg)
    await ctx.send('**Error**: Insiden internal ini telah dilaporkan ke N4O#8868, mohon tunggu jawabannya kembali.')
    logger.error("".join(tb))

async def other_ping_test():
    """Github and anilist ping test"""
    async with aiohttp.ClientSession() as session:
        print('Menjalankan tes ping github')
        t1_git = time.time()
        while True:
            try:
                async with session.get('https://api.github.com') as r:
                    try:
                        await r.json()
                        break
                    except IndexError:
                        continue
            except session.ClientError:
                continue
        t2_git = time.time()
        print('Selesai')
        git_time = round((t2_git-t1_git)*1000)
        print('Menjalankan tes ping anilist')
        t1_ani = time.time()
        while True:
            try:
                async with session.get('https://graphql.anilist.co') as r:
                    try:
                        await r.json()
                        break
                    except IndexError:
                        continue
            except session.ClientError:
                continue
        t2_ani = time.time()
        print('Selesai')
        ani_time = round((t2_ani-t1_ani)*1000)

    return {'github': git_time, 'anilist': ani_time}

def create_uptime():
    current_time = time.time()
    up_secs = int(round(current_time - bot.uptime)) # Seconds

    up_months = int(up_secs // 2592000) # 30 days format
    up_secs -= up_months * 2592000
    up_weeks = int(up_secs // 604800)
    up_secs -= up_weeks * 604800
    up_days = int(up_secs // 86400)
    up_secs -= up_days * 86400
    up_hours = int(up_secs // 3600)
    up_secs -= up_hours * 3600
    up_minutes = int(up_secs // 60)
    up_secs -= up_minutes * 60

    return_text = ''
    if up_months != 0:
        return_text += '{} bulan '.format(up_months)

    return return_text + '{} minggu {} hari {} jam {} menit {} detik'.format(up_weeks, up_days, up_hours, up_minutes, up_secs)

@bot.command()
async def ping(ctx):
    """
    pong!
    """
    channel = ctx.message.channel
    print('Melakukan tes ping keseluruhan')

    other_test = await other_ping_test()

    print('Menjalankan tes ping discord')
    t1 = time.time()
    async with channel.typing():
        t2 = time.time()
        print('Selesai')

        print('Menghitung hasil')
        dis_test = round((t2-t1)*1000)

        pingbed = discord.Embed(title="Ping Test", color=0xffffff)
        pingbed.set_thumbnail(url="https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/240/twitter/180/satellite-antenna_1f4e1.png")
        pingbed.add_field(name='Discord', value='{}ms'.format(dis_test), inline=False)
        pingbed.add_field(name='GitHub', value='{}ms'.format(other_test['github']), inline=False)
        pingbed.add_field(name='Anilist.co', value='{}ms'.format(other_test['anilist']), inline=False)
        pingbed.set_footer(text="Tested using \"sophisticated\" ping method ")
        await channel.send(embed=pingbed)

def get_version():
    discord_ver = discord.__version__
    py_ver = sys.version
    return "```py\nDiscord.py v{d}\nPython {p}\n```".format(d=discord_ver, p=py_ver)

def get_server():
    import platform
    uname = platform.uname()
    fmt_plat = "```py\nOS: {0.system} {0.release} v{0.version}\nCPU: {0.processor} ({1} threads)\nPID: {2}\n```".format(uname, os.cpu_count(), os.getpid())
    return fmt_plat

def fetch_bot_count_data():
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
    if not os.path.isfile('nao_showtimes.json'):
        print('[@] naoTimes are not initiated, skipping.')
        json_data = {}
    with open('nao_showtimes.json', 'r') as fp:
        json_data = json.load(fp)

    text_fmt = "Jumlah server: {}\nJumlah channels: {}\nJumlah pengguna: {}".format(total_server, total_channels, total_valid_users)

    if not json_data:
        text_fmt += "\n\nJumlah server Showtimes: {}\nJumlah anime Showtimes: {}".format(0, 0)
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
        text_fmt += "\n\nJumlah server Showtimes: {}\nJumlah anime Showtimes: {}".format(total_ntimes_srv, total_animemes)

    return "```" + text_fmt + "```"

@bot.command()
async def info(ctx):
    """
    Melihat Informasi bot
    """
    infog = discord.Embed(title="naoTimes", description="Sang penagih utang fansub agar fansubnya mau gerak", color=0xde8730)
    infog.set_author(name="naoTimes", icon_url="https://slwordpress.rutgers.edu/wp-content/uploads/sites/98/2015/12/Info-I-Logo.png")
    infog.set_thumbnail(url="https://puu.sh/D3x1l/7f97e14c74.png")
    infog.add_field(name="Server Info", value=get_server(), inline=False)
    infog.add_field(name="Statistik", value=fetch_bot_count_data(), inline=False)
    infog.add_field(name="Dibuat", value="Gak tau, tiba-tiba jadi.", inline=False)
    infog.add_field(name="Pembuat", value="{}".format(bot.owner.mention), inline=False)
    infog.add_field(name="Bahasa", value=get_version(), inline=False)
    infog.add_field(name="Fungsi", value="Menagih utang fansub (!help)", inline=False)
    infog.add_field(name="Uptime", value=create_uptime())
    infog.set_footer(text="naoTimes versi 2.0.0 || Dibuat oleh N4O#8868", icon_url='https://p.n4o.xyz/i/nao250px.png')
    await ctx.send(embed=infog)

@bot.command()
@commands.is_owner()
async def bundir(ctx):
    """
    Mematikan bot, owner only
    """
    try:
        await ctx.send(":gun: Membunuh bot...")
        print('[!!] Starting process...')
        for unload in cogs_list:
            bot.unload_extension(unload)
            print('[#] Unloaded ' + unload + ' module.')
        print('[@] All modules unloaded.')
        await bot.logout()
        await bot.close()
        print('[!!] Connection closed.')
        async_loop.close()
        exit(0)
    except commands.NotOwner:
        await ctx.send("Kamu tidak bisa menjalankan perintah ini\n**Alasan:** Bukan Owner Bot")

@bot.command()
@commands.is_owner()
async def reinkarnasi(ctx):
    """
    Mematikan lalu menghidupkan bot, owner only
    """
    try:
        await ctx.send(":sparkles: Proses Reinkarnasi Dimulai...")
        print('[!!] Starting process...')
        for unload in cogs_list:
            bot.unload_extension(unload)
            print('[#] Unloaded ' + unload + ' module.')
        print('[@] All modules unloaded.')
        await bot.logout()
        await bot.close()
        print('[!!] Connection closed.')
        async_loop.close()
        os.execv(sys.executable, ['python'] + sys.argv)
    except commands.NotOwner:
        await ctx.send("Kamu tidak bisa menjalankan perintah ini\n**Alasan:** Bukan Owner Bot")

@bot.command()
@commands.is_owner()
async def reload(ctx, *, module=None):
    """
    Restart salah satu module bot, owner only
    """
    if not module:
        helpmain = discord.Embed(title="Reload", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='Module/Cogs List', value="\n".join(['- ' + cl for cl in cogs_list]), inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        return await ctx.send(embed=helpmain)
    timetext = 'Started process at'
    rel1 = discord.Embed(title="Reload Module", color=0x8ceeff)
    rel1.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
    rel1.add_field(name=module, value="Status: PROCESSING", inline=False)
    rel1.set_footer(text=timetext)
    sayd = await ctx.send(embed=rel1)
    if 'cogs.' not in module:
        module = 'cogs.' + module
    try:
        print('[#] Reloading ' + module + ' module.')
        bot.unload_extension(module)
        print('[@] Reloaded.')
        bot.load_extension(module)
        timetext = 'Module reloaded'
        rel2 = discord.Embed(title="Reload Module", color=0x6ce170)
        rel2.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel2.add_field(name=module, value="Status: SUCCESS", inline=False)
        rel2.set_footer(text=timetext)
        await sayd.edit(embed=rel2)
    except Exception as error:
        timetext = 'Failed'
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        print("".join(tb))
        rel3 = discord.Embed(title="Module", description="Status: Error", color=0xe73030)
        rel3.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel3.add_field(name=module, value="```py\n{}\n```".format("".join(tb)), inline=False)
        rel3.set_footer(text=timetext)
        await sayd.edit(embed=rel3)


@bot.command()
@commands.is_owner()
async def load(ctx, *, module=None):
    """
    Load salah satu module bot, owner only
    """
    if not module:
        helpmain = discord.Embed(title="Load", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='Module/Cogs List', value="\n".join(['- ' + cl for cl in cogs_list]), inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        return await ctx.send(embed=helpmain)
    timetext = 'Started process at'
    rel1 = discord.Embed(title="Load Module", color=0x8ceeff)
    rel1.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
    rel1.add_field(name=module, value="Status: PROCESSING", inline=False)
    rel1.set_footer(text=timetext)
    sayd = await ctx.send(embed=rel1)
    if 'cogs.' not in module:
        module = 'cogs.' + module
    try:
        print('[#] Loading ' + module + ' module.')
        bot.load_extension(module)
        print('[@] Loaded.')
        timetext = 'Module Loaded'
        rel2 = discord.Embed(title="Load Module", color=0x6ce170)
        rel2.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel2.add_field(name=module, value="Status: SUCCESS", inline=False)
        rel2.set_footer(text=timetext)
        await sayd.edit(embed=rel2)
    except Exception as error:
        timetext = 'Failed'
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        print("".join(tb))
        rel3 = discord.Embed(title="Module", description="Status: Error", color=0xe73030)
        rel3.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel3.add_field(name=module, value="```py\n{}\n```".format("".join(tb)), inline=False)
        rel3.set_footer(text=timetext)
        await sayd.edit(embed=rel3)


@bot.command()
@commands.is_owner()
async def unload(ctx, *, module=None):
    """
    Unload salah satu module bot, owner only
    """
    if not module:
        helpmain = discord.Embed(title="Unload", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='Module/Cogs List', value="\n".join(['- ' + cl for cl in cogs_list]), inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        return await ctx.send(embed=helpmain)
    timetext = 'Started process at'
    rel1 = discord.Embed(title="Unload Module", color=0x8ceeff)
    rel1.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
    rel1.add_field(name=module, value="Status: PROCESSING", inline=False)
    rel1.set_footer(text=timetext)
    sayd = await ctx.send(embed=rel1)
    if 'cogs.' not in module:
        module = 'cogs.' + module
    try:
        print('[#] Unloading ' + module + ' module.')
        bot.unload_extension(module)
        print('[@] Unloaded.')
        timetext = 'Module unloaded'
        rel2 = discord.Embed(title="Unload Module", color=0x6ce170)
        rel2.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel2.add_field(name=module, value="Status: SUCCESS", inline=False)
        rel2.set_footer(text=timetext)
        await sayd.edit(embed=rel2)
    except Exception as error:
        timetext = 'Failed'
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        print("".join(tb))
        rel3 = discord.Embed(title="Module", description="Status: Error", color=0xe73030)
        rel3.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel3.add_field(name=module, value="```py\n{}\n```".format("".join(tb)), inline=False)
        rel3.set_footer(text=timetext)
        await sayd.edit(embed=rel3)

bot.loop.create_task(change_bot_presence())
bot.run(bot_config['bot_token'], bot=True, reconnect=True)
