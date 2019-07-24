# -*- coding: utf-8  -*-
#!/usr/bin/env python3

import json
import logging
import os
import sys
import time

import asyncio
import aiohttp
import discord
import requests
from discord.ext import commands

cogs_list = ['cogs.' + x.replace('.py', '') for x in os.listdir('cogs') if x.endswith('.py')]

async def fetch_newest_db(CONFIG_DATA):
    """
    Fetch the newest naoTimes database from github
    """
    print('@@ Fetching newest database')
    if CONFIG_DATA['gist_id'] == "":
        return print('@@ naoTimes are not setted up, skipping...')
    url = 'https://gist.githubusercontent.com/{u}/{g}/raw/nao_showtimes.json'
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url.format(u=CONFIG_DATA['github_info']['username'], g=CONFIG_DATA['gist_id'])) as r:
                    try:
                        r_data = await r.text()
                        js_data = json.loads(r_data)
                        with open('nao_showtimes.json', 'w') as f:
                            json.dump(js_data, f, indent=4)
                        print('@@ Fetched and saved.')
                        return
                    except IndexError:
                        continue
            except session.ClientError:
                continue

def prefixes(bot, message):
    """
    A modified version of discord.ext.command.when_mentioned_or
    """
    server = message.guild

    with open('prefixes.json') as f:
        pre = json.load(f)
    default_ = "!!"

    id_srv = server.id
    pre_data = []
    pre_ = pre_data.append(pre.get(id_srv, default_))
    if default_ not in pre_data:
        pre_data.append(default_)
    if '.' not in pre_data:
        pre_data.append('.')
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
    print('@@ Loading logger...')
    logger = logging.getLogger('discord')
    logger.setLevel(logging.ERROR)
    handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)

    print('@@ Set global start time')
    global_start_time = time.time()

    print('@@ Looking up config')
    with open('config.json', 'r') as fp:
        config = json.load(fp)

    try:
        print('@@ Initiating discord.py')
        description = '''Penyuruh Fansub biar kerja cepat\nversi 2.0.0 || Dibuat oleh: N4O#8868'''
        bot = commands.Bot(command_prefix=prefixes, description=description)
        bot.remove_command('help')
        await fetch_newest_db(config)
        for load in cogs_list:
            bot.load_extension(load)
            print('Loaded ' + load + ' Modules')
        print('### Success Loading Discord.py ###')
    except Exception as exc:
        print('### Failed to load Discord.py ###')
        print(exc)
    return bot, config, logger, global_start_time

# Initiate everything
print('@@ Initiating bot...')
async_loop = asyncio.get_event_loop()
bot, bot_config, logger, global_start_time = async_loop.run_until_complete(init_bot())

@bot.event
async def on_ready():
    """Bot loaded here"""
    print('Connected to discord.')
    presence = 'Mengamati rilisan fansub | !help'
    activity = discord.Game(name=presence, type=3)
    await bot.change_presence(activity=activity)
    print('---------------------------------------------------------------')
    print('Logged in as:')
    print('Bot name: {}'.format(bot.user.name))
    print('With Client ID: {}'.format(bot.user.id))
    print('---------------------------------------------------------------')

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
    up_secs = int(round(current_time - global_start_time)) # Seconds

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

@bot.command()
async def info():
    """
    Melihat Informasi bot
    """
    infog = discord.Embed(title="naoTimes", description="Sang penagih utang fansub agar fansubnya mau gerak", color=0xde8730)
    infog.set_author(name="naoTimes", icon_url="https://slwordpress.rutgers.edu/wp-content/uploads/sites/98/2015/12/Info-I-Logo.png")
    infog.set_thumbnail(url="https://puu.sh/D3x1l/7f97e14c74.png")
    infog.add_field(name="Info", value="Dijalankan di Heroku server US", inline=False)
    infog.add_field(name="Dibuat", value="Gak tau, tiba-tiba jadi.", inline=False)
    infog.add_field(name="Pembuat", value="N4O#8868", inline=False)
    infog.add_field(name="Bahasa", value="Discord.py dengan Python 3.6", inline=False)
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
        print('!!!! Memulai proses')
        for unload in cogs_list:
            bot.unload_extension(unload)
            print('Unloaded ' + unload + ' Modules')
        print('### Modules unloaded')
        await bot.logout()
        await bot.close()
        async_loop.close()
        #res = requests.patch('https://api.heroku.com/apps/nao-times/formation/f8aa4e6a-7189-4cf5-8829-b031574e2cef', data={"quantity": 0, "size": "Free"}, headers={'Accept': 'application/vnd.heroku+json; version=3', 'Authorization': 'Bearer 9ab0ac6e-cb20-4610-8cc1-cec4a75f53da'})
        #print(res.text)
        print('### Connection closed')
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
        print('!!!! Memulai proses')
        for reload_mod in cogs_list:
            bot.unload_extension(reload_mod)
            print('Unloaded ' + reload_mod + ' Modules')
        print('### Modules unloaded')
        await bot.logout()
        await bot.close()
        print('### Connection closed')
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
        bot.unload_extension(module)
        bot.load_extension(module)
        timetext = 'Module reloaded'
        rel2 = discord.Embed(title="Reload Module", color=0x6ce170)
        rel2.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel2.add_field(name=module, value="Status: SUCCESS", inline=False)
        rel2.set_footer(text=timetext)
        await sayd.edit(embed=rel2)
    except Exception as e:
        timetext = 'Failed'
        rel3 = discord.Embed(title="Module", color=0xe73030)
        rel3.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel3.add_field(name=module, value="Status: ERROR - {}".format(str(e)), inline=False)
        rel3.set_footer(text=timetext)
        await sayd.edit(embed=rel3)
        print(e)


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
        bot.load_extension(module)
        timetext = 'Module Loaded'
        rel2 = discord.Embed(title="Load Module", color=0x6ce170)
        rel2.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel2.add_field(name=module, value="Status: SUCCESS", inline=False)
        rel2.set_footer(text=timetext)
        await sayd.edit(embed=rel2)
    except Exception as e:
        timetext = 'Failed'
        rel3 = discord.Embed(title="Load Module", color=0xe73030)
        rel3.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel3.add_field(name=module, value="Status: ERROR - {}".format(str(e)), inline=False)
        rel3.set_footer(text=timetext)
        await sayd.edit(embed=rel3)
        print(e)


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
        bot.unload_extension(module)
        timetext = 'Module unloaded'
        rel2 = discord.Embed(title="Unload Module", color=0x6ce170)
        rel2.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel2.add_field(name=module, value="Status: SUCCESS", inline=False)
        rel2.set_footer(text=timetext)
        await sayd.edit(embed=rel2)
    except Exception as e:
        timetext = 'Failed'
        rel3 = discord.Embed(title="Unload Module", color=0xe73030)
        rel3.set_thumbnail(url="https://d30y9cdsu7xlg0.cloudfront.net/png/4985-200.png")
        rel3.add_field(name=module, value="Status: ERROR - {}".format(str(e)), inline=False)
        rel3.set_footer(text=timetext)
        await sayd.edit(embed=rel3)
        print(e)

try:
    bot.run(bot_config['bot_token'], bot=True, reconnect=True)
except KeyboardInterrupt:
    bot.logout()
finally:
    bot.close()

