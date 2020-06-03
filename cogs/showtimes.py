# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import asyncio
import json
import os
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta
from random import choice
from string import ascii_lowercase, digits

import aiohttp
import discord
from discord.ext import commands, tasks
from typing import Union
import pytz

anifetch_query = '''
query ($id: Int!) {
    Media(id: $id, type: ANIME) {
        id
        title {
            romaji
            english
        }
        coverImage {
            large
            color
        }
        format
        episodes
        startDate {
            year
            month
            day
        }
        airingSchedule {
            nodes {
                id
                episode
                airingAt
            }
        }
        nextAiringEpisode {
            timeUntilAiring
            airingAt
            episode
        }
    }
}
'''

tambahepisode_instruct = """Jumlah yang dimaksud adalah jumlah yang ingin ditambahkan dari jumlah episode sekarang
Misal ketik `4` dan total jumlah episode sekarang adalah `12`
Maka total akan berubah menjadi `16` `(13, 14, 15, 16)`"""

hapusepisode_instruct = """Ranged number, bisa satu digit untuk 1 episode saja atau range dari episode x sampai y
Contoh: `4` untuk episode 4 saja || `4-6` untuk episode 4 sampai 6"""

with open('config.json', 'r') as fp:
    bot_config = json.load(fp)

async def fetch_json() -> dict:
    """
    Open local database
    """
    print('[@] Opening json file')
    if not os.path.isfile('nao_showtimes.json'):
        print('[@] naoTimes are not initiated, skipping.')
        return {}
    with open('nao_showtimes.json', 'r', encoding="utf-8") as fp:
        json_data = json.load(fp)

    return json_data


async def dump_json(dataset: dict):
    """
    Dump database into a json file
    """
    print('[@] Dumping dictionary to json file')
    with open('nao_showtimes.json', 'w', encoding="utf-8") as fp:
        json.dump(dataset, fp, indent=2)


def is_minus(x: Union[int, float]) -> bool:
    """Essentials for quick testing"""
    return x < 0


def rgbhex_to_rgbint(hex_str: str) -> int:
    """Used for anilist color to convert to discord.py friendly color"""
    if not hex_str:
        return 0x1eb5a6
    hex_str = hex_str.replace("#", "").upper()
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return (256 * 256 * r) + (256 * g) + b


def parse_anilist_start_date(startDate: str) -> int:
    """parse start data of anilist data to Unix Epoch"""
    airing_start = datetime.strptime(startDate, '%Y%m%d')
    epoch_start = datetime(1970, 1, 1, 0, 0, 0)
    return int((airing_start - epoch_start).total_seconds())


def get_episode_airing(nodes: dict, episode: str) -> tuple:
    """Get total episode of airing anime (using anilist data)"""
    if not nodes:
        return None, '1' # No data
    for i in nodes:
        if i['episode'] == int(episode):
            return i['airingAt'], i['episode'] # return episodic data
    if len(nodes) == 1:
        return nodes[0]['airingAt'], nodes[-1]['episode'] # get the only airing data
    return nodes[-1]['airingAt'], nodes[-1]['episode'] # get latest airing data


def get_original_time(x: int, total: int) -> int:
    """what the fuck does this thing even do"""
    for _ in range(total):
        x -= 24 * 3600 * 7
    return x


def parse_ani_time(x: int) -> str:
    """parse anilist time to time-left format"""
    sec = timedelta(seconds=abs(x))
    d = datetime(1, 1, 1) + sec
    print('Anilist Time: {} year {} month {} day {} hour {} minutes {} seconds'.format(d.year, d.month, d.day, d.hour, d.minute, d.second))

    if d.year-1 >= 1:
        if is_minus(x):
            return '{} tahun yang lalu'.format(d.year-1)
        return '{} tahun lagi'.format(d.year-1)
    if d.year-1 <= 0 and d.month-1 >= 1:
        if is_minus(x):
            return '{} bulan yang lalu'.format(d.month-1)
        return '{} bulan lagi'.format(d.month-1)
    if d.day-1 <= 0 and d.hour > 0:
        if is_minus(x):
            return '{} jam yang lalu'.format(d.hour)
        return '{} jam lagi'.format(d.hour)
    if d.hour <= 0 and d.day-1 <= 0:
        if d.minute <= 3:
            if is_minus(x):
                return 'Beberapa menit yang lalu'
            return 'Beberapa menit lagi'
        if is_minus(x):
            return '{} menit yang lalu'.format(d.minute)
        return '{} menit lagi'.format(d.minute)

    if d.hour <= 0:
        if is_minus(x):
            return '{} hari yang lalu'.format(d.day-1)
        return '{} hari lagi'.format(d.day-1)
    if is_minus(x):
        return '{} hari dan {} jam yang lalu'.format(d.day-1, d.hour)
    return '{} hari dan {} jam lagi'.format(d.day-1, d.hour)


async def fetch_anilist(ani_id, current_ep, total_episode=None, return_time_data=False, jadwal_only=False) -> tuple:
    """
    Fetch Anilist.co API data for helping all showtimes command to work properly
    Used on almost command, tweaked to make it compatible to every command
    """
    variables = {
        'id': int(ani_id),
    }
    api_link = 'https://graphql.anilist.co'
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_link, json={'query': anifetch_query, 'variables': variables}) as r:
                try:
                    data = await r.json()
                except IndexError:
                    return "ERROR: Terjadi kesalahan internal"
                if r.status != 200:
                    if r.status == 404:
                        return "ERROR: Tidak dapat menemukan anime tersebut"
                    elif r.status == 500:
                        return "ERROR: Internal Error :/"
                try:
                    entry = data['data']['Media']
                except IndexError:
                    return "ERROR: Tidak ada hasil."
        except aiohttp.ClientError:
            return "ERROR: Koneksi terputus"

    if jadwal_only:
        try:
            time_until = entry['nextAiringEpisode']['timeUntilAiring']
            next_episode = entry['nextAiringEpisode']['episode']

            taimu = parse_ani_time(time_until)
        except:
            taimu = None
            time_until = None
            next_episode = None

        return taimu, time_until, next_episode

    poster = [entry['coverImage']['large'], rgbhex_to_rgbint(entry['coverImage']['color'])]
    start_date = entry['startDate']
    title_rom = entry['title']['romaji']
    airing_time_nodes = entry['airingSchedule']['nodes']
    show_format = entry['format'].lower()
    current_time = int(round(time.time()))
    airing_time, episode_number = get_episode_airing(airing_time_nodes, current_ep)
    if not airing_time:
        airing_time = parse_anilist_start_date('{}{}{}'.format(start_date['year'], start_date['month'], start_date['day']))
    if show_format in ['tv', 'tv_short']:
        if str(episode_number) == str(current_ep):
            pass
        else:
            airing_time = get_original_time(airing_time, int(episode_number) - int(current_ep))
    airing_time = airing_time - current_time
    try:
        episodes = entry['episodes']
        if not episodes:
            episodes = 0
    except KeyError:
        episodes = 0
    except IndexError:
        episodes = 0

    if not airing_time_nodes:
        airing_time_nodes = []
        temporary_nodes = {}
        temporary_nodes['airingAt'] = parse_anilist_start_date('{}{}{}'.format(start_date['year'], start_date['month'], start_date['day']))
        airing_time_nodes.append(temporary_nodes)

    taimu = parse_ani_time(airing_time)
    if return_time_data:
        if total_episode is not None and int(total_episode) < episodes:
            total_episode = episodes
        else:
            total_episode = int(total_episode)
        time_data = []
        if show_format in ['tv', 'tv_short']:
            for x in range(total_episode):
                try:
                    time_data.append(airing_time_nodes[x]['airingAt'])
                except IndexError: # Out of range stuff ;_;
                    calc = 24 * 3600 * 7 * x
                    time_data.append(int(airing_time_nodes[0]['airingAt']) + calc)
        else:
            for x in range(total_episode):
                time_data.append(get_original_time(parse_anilist_start_date('{}{}{}'.format(start_date['year'], start_date['month'], start_date['day'])), x+1))
        return taimu, poster, title_rom, time_data, total_episode
    return taimu, poster, title_rom


def get_current_ep(status_list: dict) -> list:
    """
    Find episode `not_released` status in showtimes database
    If not exist return None
    """
    for ep in status_list:
        if status_list[ep]['status'] == 'not_released':
            return ep
    return None


def get_not_released_ep(status_list: dict) -> list:
    """
    Find all episode `not_released` status in showtimes database
    If not exist return None/False
    """
    ep_list = []
    for ep in status_list:
        if status_list[ep]['status'] == 'not_released':
            ep_list.append(ep)
    return ep_list


def get_close_matches(target: str, lists: list) -> list:
    """
    Find close matches from input target
    Sort everything if there's more than 2 results
    """
    target_compiler = re.compile('({})'.format(target), re.IGNORECASE)
    return sorted(list(filter(target_compiler.search, lists)))


def check_role(needed_role, user_roles: list) -> bool:
    """
    Check if there's needed role for the anime
    """
    for role in user_roles:
        if int(needed_role) == int(role.id):
            return True
    return False


def get_last_updated(oldtime):
    """
    Get last updated time from naoTimes database
    and convert it to "passed time"
    """
    current_time = datetime.now()
    oldtime = datetime.utcfromtimestamp(oldtime)
    delta_time = current_time - oldtime

    days_passed_by = delta_time.days
    seconds_passed = delta_time.total_seconds()
    if seconds_passed < 60:
        text = 'Beberapa detik yang lalu'
    elif seconds_passed < 180:
        text = 'Beberapa menit yang lalu'
    elif seconds_passed < 3600:
        text = '{} menit yang lalu'.format(round(seconds_passed / 60))
    elif seconds_passed < 86400:
        text = '{} jam yang lalu'.format(round(seconds_passed / 3600))
    elif days_passed_by < 31:
        text = '{} hari yang lalu'.format(days_passed_by)
    elif days_passed_by < 365:
        text = '{} bulan yang lalu'.format(round(days_passed_by / 30))
    else:
        calculate_year = round(days_passed_by / 365)
        if calculate_year < 1:
            calculate_year = 1
        text = '{} bulan yang lalu'.format(calculate_year)

    return text


def get_current_time() -> str:
    """
    Return current time in `DD Month YYYY HH:MM TZ (+X)` format
    """
    current_time = datetime.now(pytz.timezone('Asia/Jakarta'))

    def month_in_idn(datetime_fmt):
        x = datetime_fmt.strftime("%B")
        eng = ["January", "February", "March", "April",
                "May", "June", "July", "August",
                "September", "October", "November", "December"]
        idn = ["Januari", "Februari", "Maret", "April",
                "Mei", "Juni", "Juli", "Agustus",
                "September", "Oktober", "November", "Desember"]
        return idn[eng.index(x)]

    d = current_time.strftime("%d")
    m = month_in_idn(current_time)
    rest = current_time.strftime("%Y %H:%M %Z (+7)")

    return '{} {} {}'.format(d, m, rest)


def parse_status(status) -> str:
    """
    Parse status and return a formatted text
    """
    status_list = []
    for work, c_stat in status.items():
        if c_stat == 'y':
            status_list.append("~~{}~~".format(work))
        else:
            status_list.append("**{}**".format(work))

    return " ".join(status_list)


def find_alias_anime(key: str, alias_list: dict) -> str:
    """
    Return a target_anime value for alias provided
    """
    for k, v in alias_list.items():
        if key == k:
            return v


def make_numbered_alias(alias_list: list) -> str:
    """
    Create a numbered text for alias_list
    """
    t = []
    for n, i in enumerate(alias_list):
        t.append('**{}**. {}'.format(n + 1, i))
    return "\n".join(t)


def any_progress(status: dict) -> bool:
    """
    Check if there's any progress to the project
    """
    for _, v in status.items():
        if v == 'y':
            return False
    return True


def get_role_name(role_id, roles) -> str:
    """
    Get role name by comparing the role id
    """
    for r in roles:
        if str(r.id) == str(role_id):
            return r.name
    return 'Unknown'


def split_until_less_than(dataset: list) -> list:
    """
    Split the !tagih shit into chunked text because discord max 2000 characters limit
    """
    def split_list(alist, wanted_parts=1):
        length = len(alist)
        return [alist[i*length // wanted_parts: (i+1)*length // wanted_parts]
                for i in range(wanted_parts)]

    text_format = '**Mungkin**: {}'
    start_num = 2
    new_set = None
    while True:
        internal_meme = False
        new_set = split_list(dataset, start_num)
        for set_ in new_set:
            if len(text_format.format(', '.join(set_))) > 1995:
                internal_meme = True

        if not internal_meme:
            break
        start_num += 1

    return new_set


async def patch_error_handling(bot, ctx):
    current_time = time.time()
    embed = discord.Embed(title="Patch Error Logger", colour=0x252aff, description="Terjadi kesalahan patch ke github...", timestamp=datetime.utcfromtimestamp(current_time))
    embed.add_field(name="Cogs", value="[nT!] {0.cog_name}".format(ctx.command), inline=False)
    embed.add_field(name="Perintah yang dipakai", value="{0.command}\n`{0.message.clean_content}`".format(ctx), inline=False)
    embed.add_field(name="Server Insiden", value="{0.guild.name} ({0.guild.id})".format(ctx.message), inline=False)
    embed.add_field(name="Orang yang memakainya", value="{0.author.name}#{0.author.discriminator} ({0.author.id})".format(ctx.message), inline=False)
    embed.set_thumbnail(url="http://p.ihateani.me/1bnBuV9C")

    await bot.owner.send(embed=embed)


class Showtimes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # pylint: disable=E1101
        self.resync_failed_server.start()
        # pylint: enable=E1101

    def __str__(self):
        return 'Showtimes Main'

    @tasks.loop(minutes=1.0)
    async def resync_failed_server(self):
        print('[$] Resynchronizing failed server update to main database.')
        if not self.bot.showtimes_resync:
            return print('[!] No resynchronizing required.')
        json_d = await fetch_json()
        for srv in self.bot.showtimes_resync:
            print('[#] Updating: {}'.format(srv))
            res, msg = await self.bot.ntdb.update_data_server(srv, json_d[srv])
            if not res:
                print('\tFailed to update, reason: {}'.format(msg))
                continue
            print('\tUpdated!')
            self.bot.showtimes_resync.remove(srv)
        print('[@] Finished resync, leftover server amount are {}'.format(len(self.bot.showtimes_resync)))

    async def choose_anime(self, ctx, matches):
        print('[!] Asking user for input.')
        first_run = True
        matches = matches[:10]
        reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
        res_matches = []
        while True:
            if first_run:
                embed = discord.Embed(title='Mungkin:', color=0x8253b8)

                format_value = []
                for n, i in enumerate(matches):
                    format_value.append('{} **{}**'.format(reactmoji[n], i))
                format_value.append('❌ **Batalkan**')
                embed.description = '\n'.join(format_value)

                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
            reactmoji_extension = ['❌']

            reactmoji = reactmoji[:len(matches)]
            reactmoji.extend(reactmoji_extension)

            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                break
            if user != ctx.message.author:
                pass
            elif '❌' in str(res.emoji):
                await msg.clear_reactions()
                break
            else:
                await msg.clear_reactions()
                reaction_pos = reactmoji.index(str(res.emoji))
                res_matches.append(matches[reaction_pos])
                break
        await msg.delete()
        if res_matches:
            print('[#] Picked: {}'.format(res_matches[0]))
        return res_matches

    @commands.command(aliases=['blame', 'mana'])
    @commands.guild_only()
    async def tagih(self, ctx, *, judul=None):
        """
        Menagih utang fansub tukang diley maupun tidak untuk memberikan mereka tekanan
        ---
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        print('[@] Requested !tagih at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            sorted_data = sorted(srv_anilist)
            count_text = len('**Mungkin**: {}'.format(', '.join(sorted_data)))
            if count_text > 1995:
                sorted_data = split_until_less_than(sorted_data)
                first_time = True
                for data in sorted_data:
                    if first_time:
                        await ctx.send('**Mungkin**: {}'.format(', '.join(data)))
                        first_time = False
                    else:
                        await ctx.send('{}'.format(', '.join(data)))
                return
            else:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(sorted_data)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        program_info = server_data['anime'][matches[0]]
        last_update = int(program_info['last_update'])
        status_list = program_info['status']

        current = get_current_ep(status_list)
        if not current:
            return await ctx.send('**Sudah beres digarap!**')

        time_data, poster_data, _ = await fetch_anilist(program_info['anilist_id'], current)
        poster_image, poster_color = poster_data

        if any_progress(status_list[current]['staff_status']):
            last_status = time_data
            last_text = 'Tayang'
        else:
            last_status = get_last_updated(last_update)
            last_text = 'Update Terakhir'

        current_ep_status = parse_status(status_list[current]['staff_status'])
        print('[#] Sending message to user request...')

        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=poster_color)
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name='Status', value=current_ep_status, inline=False)
        embed.add_field(name=last_text, value=last_status, inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)


    @commands.command(aliases=['release'])
    @commands.guild_only()
    async def rilis(self, ctx, *, data):
        data = data.split()

        server_message = str(ctx.message.guild.id)
        print('[@] Requested !rilis at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if len(srv_anilist) < 1:
            return await ctx.send('**Tidak ada anime yang terdaftar di database**')

        if not data or data == []:
            return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        koleb_list = []

        if data[0] not in ['batch', 'semua']:
            """
            Merilis rilisan, hanya bisa dipakai sama role tertentu
            ---
            judul: Judul anime yang terdaftar
            """
            print('[@] Inherited normal rilis command')

            judul = ' '.join(data)

            if judul == ' ' or judul == '' or judul == '   ' or not judul:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('[!] Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await ctx.send('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                matches = await self.choose_anime(ctx, matches)
                if not matches:
                    return await ctx.send('**Dibatalkan!**')

            program_info = server_data['anime'][matches[0]]
            status_list = program_info['status']

            if 'kolaborasi' in program_info:
                koleb_data = program_info['kolaborasi']
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            current = get_current_ep(status_list)
            if not current:
                return await ctx.send('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await ctx.send('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            if koleb_list:
                for other_srv in koleb_list:
                    if other_srv not in json_d:
                        continue
                    json_d[other_srv]['anime'][matches[0]]['status'][current]['status'] = 'released'
                    json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))
            json_d[server_message]['anime'][matches[0]]['status'][current]['status'] = 'released'
            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            text_data = "**{} - #{}** telah dirilis".format(matches[0], current)
            embed_text_data = "{} #{} telah dirilis!".format(matches[0], current)
        elif data[0] == 'batch':
            if not data[1].isdigit():
                await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))
                return await ctx.send("Lalu tulis jumlah terlebih dahulu baru judul")
            if len(data) < 3:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

            jumlah = data[1]
            judul = ' '.join(data[2:])

            print('[@] Inherited batch rilis command')

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('[!] Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await ctx.send('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                matches = await self.choose_anime(ctx, matches)
                if not matches:
                    return await ctx.send('**Dibatalkan!**')

            program_info = server_data['anime'][matches[0]]
            status_list = program_info['status']

            if 'kolaborasi' in program_info:
                koleb_data = program_info['kolaborasi']
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            current = get_current_ep(status_list)
            if not current:
                return await ctx.send('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await ctx.send('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            if koleb_list:
                for other_srv in koleb_list:
                    if other_srv not in json_d:
                        continue
                    for x in range(int(current), int(current)+int(jumlah)): # range(int(c), int(c)+int(x))
                        json_d[other_srv]['anime'][matches[0]]['status'][str(x)]['status'] = 'released'
                    json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))
            for x in range(int(current), int(current)+int(jumlah)): # range(int(c), int(c)+int(x))
                json_d[server_message]['anime'][matches[0]]['status'][str(x)]['status'] = 'released'

            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(matches[0], current, int(current)+int(jumlah)-1)
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(matches[0], current, int(current)+int(jumlah)-1)
        elif data[0] == 'semua':
            judul = ' '.join(data[1:])

            if judul == ' ' or judul == '' or judul == '   ' or not judul:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

            print('[!] Inherited all rilis command')

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('[!] Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await ctx.send('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                matches = await self.choose_anime(ctx, matches)
                if not matches:
                    return await ctx.send('**Dibatalkan!**')

            program_info = server_data['anime'][matches[0]]
            status_list = program_info['status']

            if 'kolaborasi' in program_info:
                koleb_data = program_info['kolaborasi']
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            all_status = get_not_released_ep(status_list)
            if not all_status:
                return await ctx.send('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await ctx.send('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            if koleb_list:
                for other_srv in koleb_list:
                    if other_srv not in json_d:
                        continue
                    for x in all_status:
                        json_d[other_srv]['anime'][matches[0]]['status'][x]['status'] = 'released'
                    json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))
            for x in all_status:
                json_d[server_message]['anime'][matches[0]]['status'][x]['status'] = 'released'

            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(matches[0], all_status[0], all_status[-1])
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(matches[0], all_status[0], all_status[-1])

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sending message...')
        await ctx.send(text_data)

        print("[%] Updating main database data...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            if osrv not in json_d: # Skip if the server doesn't exist :pepega:
                continue
            print("[%] Updating collaboration server: {}".format(osrv))
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, json_d[osrv])
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                print('[%] Failed updating collaboration server: {}\n\tReason: {}'.format(osrv, msg2))

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                if 'announce_channel' in json_d[other_srv]:
                    print('[@] Sending progress info to everyone at {}'.format(other_srv))
                    announce_chan = json_d[other_srv]['announce_channel']
                    target_chan = self.bot.get_channel(int(announce_chan))
                    if not target_chan:
                        print('[$] Unknown server: {}'.format(announce_chan))
                        continue
                    embed = discord.Embed(title="{}".format(matches[0]), color=0x1eb5a6)
                    embed.add_field(name='Rilis!', value=embed_text_data, inline=False)
                    embed.set_footer(text="Pada: {}".format(get_current_time()))
                    await target_chan.send(embed=embed)
        if 'announce_channel' in server_data:
            announce_chan = server_data['announce_channel']
            target_chan = self.bot.get_channel(int(announce_chan))
            embed = discord.Embed(title="{}".format(matches[0]), color=0x1eb5a6)
            embed.add_field(name='Rilis!', value=embed_text_data, inline=False)
            embed.set_footer(text="Pada: {}".format(get_current_time()))
            if target_chan:
                await target_chan.send(embed=embed)


    @commands.command(aliases=['done'])
    async def beres(self, ctx, posisi, *, judul):
        """
        Menyilang salah satu tugas pendelay
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        print('[@] Requested !beres at: ' + server_message)
        posisi = posisi.lower()
        list_posisi = ['tl', 'tlc', 'enc', 'ed', 'tm', 'ts', 'qc']
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']

        koleb_list = []
        if 'kolaborasi' in program_info:
            koleb_data = program_info['kolaborasi']
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        if not check_role(program_info['role_id'], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = get_current_ep(status_list)
        if not current:
            return await ctx.send('**Sudah beres digarap!**')

        _, poster_data, _ = await fetch_anilist(program_info['anilist_id'], current)
        poster_image, _ = poster_data

        if posisi not in list_posisi:
            return await ctx.send('Tidak ada posisi itu\nYang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`')

        if str(ctx.message.author.id) != program_info['staff_assignment'][posisi.upper()]:
            if str(ctx.message.author.id) not in srv_owner:
                return await ctx.send('**Bukan posisi situ untuk mengubahnya!**')

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                json_d[other_srv]['anime'][matches[0]]['status'][current]['staff_status'][posisi.upper()] = 'y'
                json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))
        json_d[server_message]['anime'][matches[0]]['status'][current]['staff_status'][posisi.upper()] = 'y'
        json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

        current_ep_status = status_list[current]['staff_status']

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sending progress info to staff')
        await ctx.send('Berhasil mengubah status garapan {} - #{}'.format(matches[0], current))

        print("[%] Updating main database data...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            if osrv not in json_d: # Skip if the server doesn't exist :pepega:
                continue
            print("[%] Updating collaboration server: {}".format(osrv))
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, json_d[osrv])
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                print('[%] Failed updating collaboration server: {}\n\tReason: {}'.format(osrv, msg2))

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                if 'announce_channel' in json_d[other_srv]:
                    print('[@] Sending progress info to everyone at {}'.format(other_srv))
                    announce_chan = json_d[other_srv]['announce_channel']
                    target_chan = self.bot.get_channel(int(announce_chan))
                    if not target_chan:
                        print('[$] Unknown server: {}'.format(announce_chan))
                        continue
                    embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0x1eb5a6)
                    embed.add_field(name='Status', value=parse_status(current_ep_status), inline=False)
                    embed.set_footer(text="Pada: {}".format(get_current_time()))
                    await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0x1eb5a6)
        embed.add_field(name='Status', value=parse_status(current_ep_status), inline=False)
        if 'announce_channel' in server_data:
            announce_chan = server_data['announce_channel']
            target_chan = self.bot.get_channel(int(announce_chan))
            embed.set_footer(text="Pada: {}".format(get_current_time()))
            print('[@] Sending progress info to everyone')
            if target_chan:
                await target_chan.send(embed=embed)
        embed.add_field(name='Update Terakhir', value='Baru saja', inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        embed.set_thumbnail(url=poster_image)
        return await ctx.send(embed=embed)


    @commands.command(aliases=['gakjadirilis', 'revert'])
    @commands.guild_only()
    async def batalrilis(self, ctx, *, judul=None):
        server_message = str(ctx.message.guild.id)
        print('[@] Requested !batalrilis at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            sorted_data = sorted(srv_anilist)
            count_text = len('**Mungkin**: {}'.format(', '.join(sorted_data)))
            if count_text > 1995:
                sorted_data = split_until_less_than(sorted_data)
                first_time = True
                for data in sorted_data:
                    if first_time:
                        await ctx.send('**Mungkin**: {}'.format(', '.join(data)))
                        first_time = False
                    else:
                        await ctx.send('{}'.format(', '.join(data)))
                return
            else:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(sorted_data)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']
        srv_owner = server_data['serverowner']

        if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
            if str(ctx.message.author.id) not in srv_owner:
                return await ctx.send('**Tidak secepat itu ferguso, yang bisa membatalkan rilisan cuma admin atau QCer**')

        current = get_current_ep(status_list)
        if not current:
            current = int(list(status_list.keys())[-1])
        else:
            current = int(current) - 1

        if current < 1:
            return await ctx.send('Tidak ada episode yang dirilis untuk judul ini.')

        current = str(current)

        koleb_list = []
        if 'kolaborasi' in program_info:
            koleb_data = program_info['kolaborasi']
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                json_d[other_srv]['anime'][matches[0]]['status'][current]['status'] = 'not_released'
                json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))
        json_d[server_message]['anime'][matches[0]]['status'][current]['status'] = 'not_released'
        json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sending progress info to staff')
        await ctx.send('Berhasil membatalkan rilisan **{}** episode {}'.format(matches[0], current))

        print("[%] Updating main database data...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            if osrv not in json_d: # Skip if the server doesn't exist :pepega:
                continue
            print("[%] Updating collaboration server: {}".format(osrv))
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, json_d[osrv])
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                print('[%] Failed updating collaboration server: {}\n\tReason: {}'.format(osrv, msg2))

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                if 'announce_channel' in json_d[other_srv]:
                    print('[@] Sending progress info to everyone at {}'.format(other_srv))
                    announce_chan = json_d[other_srv]['announce_channel']
                    target_chan = self.bot.get_channel(int(announce_chan))
                    if not target_chan:
                        print('[$] Unknown server: {}'.format(announce_chan))
                        continue
                    embed = discord.Embed(title="{}".format(matches[0]), color=0xb51e1e)
                    embed.add_field(name='Batal rilis...', value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(current), inline=False)
                    embed.set_footer(text="Pada: {}".format(get_current_time()))
                    await target_chan.send(embed=embed)
        if 'announce_channel' in server_data:
            announce_chan = server_data['announce_channel']
            target_chan = self.bot.get_channel(int(announce_chan))
            embed = discord.Embed(title="{}".format(matches[0]), color=0xb51e1e)
            embed.add_field(name='Batal rilis...', value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(current), inline=False)
            embed.set_footer(text="Pada: {}".format(get_current_time()))
            if target_chan:
                await target_chan.send(embed=embed)


    @commands.command(aliases=['undone', 'cancel'])
    @commands.guild_only()
    async def gakjadi(self, ctx, posisi, *, judul):
        """
        Menghilangkan tanda karena ada kesalahan
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        print('[@] Requested !gakjadi at: ' + server_message)
        posisi = posisi.lower()
        list_posisi = ['tl', 'tlc', 'enc', 'ed', 'tm', 'ts', 'qc']
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']

        koleb_list = []
        if 'kolaborasi' in program_info:
            koleb_data = program_info['kolaborasi']
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        if not check_role(program_info['role_id'], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = get_current_ep(status_list)
        if not current:
            return await ctx.send('**Sudah beres digarap!**')

        _, poster_data, _ = await fetch_anilist(program_info['anilist_id'], current)
        poster_image, _ = poster_data

        if posisi not in list_posisi:
            return await ctx.send('Tidak ada posisi itu\nYang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`')

        if str(ctx.message.author.id) != program_info['staff_assignment'][posisi.upper()]:
            if str(ctx.message.author.id) not in srv_owner:
                return await ctx.send('**Bukan posisi situ untuk mengubahnya!**')

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                json_d[other_srv]['anime'][matches[0]]['status'][current]['staff_status'][posisi.upper()] = 'x'
                json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))
        json_d[server_message]['anime'][matches[0]]['status'][current]['staff_status'][posisi.upper()] = 'x'
        json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

        current_ep_status = status_list[current]['staff_status']

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sending progress info to staff')
        await ctx.send('Berhasil mengubah status garapan {} - #{}'.format(matches[0], current))

        print("[%] Updating main database data...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            if osrv not in json_d: # Skip if the server doesn't exist :pepega:
                continue
            print("[%] Updating collaboration server: {}".format(osrv))
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, json_d[osrv])
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                print('[%] Failed updating collaboration server: {}\n\tReason: {}'.format(osrv, msg2))

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                if 'announce_channel' in json_d[other_srv]:
                    print('[@] Sending progress info to everyone at {}'.format(other_srv))
                    announce_chan = json_d[other_srv]['announce_channel']
                    target_chan = self.bot.get_channel(int(announce_chan))
                    if not target_chan:
                        print('[$] Unknown server: {}'.format(announce_chan))
                        continue
                    embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0xb51e1e)
                    embed.add_field(name='Status', value=parse_status(current_ep_status), inline=False)
                    embed.set_footer(text="Pada: {}".format(get_current_time()))
                    await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0xb51e1e)
        embed.add_field(name='Status', value=parse_status(current_ep_status), inline=False)
        if 'announce_channel' in server_data:
            announce_chan = server_data['announce_channel']
            target_chan = self.bot.get_channel(int(announce_chan))
            embed.set_footer(text="Pada: {}".format(get_current_time()))
            print('[@] Sending progress info to everyone')
            if target_chan:
                await target_chan.send(embed=embed)
        embed.add_field(name='Update Terakhir', value='Baru saja', inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        embed.set_thumbnail(url=poster_image)
        await ctx.send(embed=embed)


    @commands.command(aliases=['add', 'tambah'])
    @commands.guild_only()
    async def tambahutang(self, ctx):
        """
        Membuat utang baru, ambil semua user id dan role id yang diperlukan.
        ----
        Menggunakan embed agar terlihat lebih enak dibanding sebelumnya
        Merupakan versi 2
        """
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !tambahutang at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa menambah utang')

        print('Membuat data')
        embed = discord.Embed(title="Menambah Utang", color=0x56acf3)
        embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await ctx.send(embed=embed)
        current_time = int(round(time.time()))
        msg_author = ctx.message.author
        json_tables = {
            "ani_title": "",
            "anilist_id": "",
            "episodes": "",
            "time_data": "",
            "poster_img": "",
            "role_id": "",
            "tlor_id": "",
            "tlcer_id": "",
            "encoder_id": "",
            "editor_id": "",
            "timer_id": "",
            "tser_id": "",
            "qcer_id": "",
            "settings": {
                'time_data_are_the_same': False
            },
            "old_time_data": []
        }
        cancel_toggled = False # Some easy check if it's gonna fucked up
        first_time = True

        def check_if_author(m):
            return m.author == msg_author

        async def process_episode(table, emb_msg):
            print('[@] Memproses jumlah episode')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Jumlah Episode', value="Ketik Jumlah Episode perkiraan", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)
            
            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)

                if await_msg.content.isdigit():
                    await await_msg.delete()
                    break

                await await_msg.delete()

            _, _, _, time_data, correct_episode_num = await fetch_anilist(table['anilist_id'], 1, int(await_msg.content), True)
            table['episodes'] = correct_episode_num
            table['time_data'] = time_data

            return table, emb_msg

        async def process_anilist(table, emb_msg):
            print('[@] Memproses Anilist data')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.add_field(name='Anilist ID', value="Ketik ID Anilist untuk anime yang diinginkan\n\nBisa gunakan `!anime <judul>` dan melihat bagian bawah untuk IDnya\n\nKetik *cancel* untuk membatalkan proses", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(content="", embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)

                if not await_msg.content.startswith("!anime"):
                    if await_msg.content == ("cancel"):
                        return False, False

                    if await_msg.content.isdigit():
                        await await_msg.delete()
                        break

                    await await_msg.delete()

            _, poster_data, title, time_data, correct_episode_num = await fetch_anilist(await_msg.content, 1, 1, True)
            poster_image, _ = poster_data

            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=poster_image)
            embed.add_field(name='Apakah benar?', value="Judul: **{}**".format(title), inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            to_react = ['✅', '❌']
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for('reaction_add', check=check_react)
            if user != ctx.message.author:
                pass
            elif '✅' in str(res.emoji):
                table['ani_title'] = title
                table['poster_img'] = poster_image
                table['anilist_id'] = str(await_msg.content)
                await emb_msg.clear_reactions()
            elif '❌' in str(res.emoji):
                await emb_msg.clear_reactions()
                return False, False

            if correct_episode_num == 1:
                print('[@] Correct episode are not grabbed, asking user...')
                table, emb_msg = await process_episode(table, emb_msg)
            else:
                print('[@] Total episodes exist, using that to continue...')
                table['episodes'] = correct_episode_num
                table['time_data'] = time_data

            return table, emb_msg

        async def process_role(table, emb_msg):
            print('[@] Memproses Role')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Role ID', value="Ketik ID Role atau mention rolenya\nAtau ketik `auto` untuk membuatnya otomatis", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)

                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        table['role_id'] = await_msg.content
                        await await_msg.delete()
                        break
                    elif await_msg.content.startswith('auto'):
                        c_role = await ctx.message.guild.create_role(
                            name=table['ani_title'],
                            colour=discord.Colour(0xdf2705),
                            mentionable=True
                        )
                        table['role_id'] = str(c_role.id)
                        await await_msg.delete()
                        break
                else:
                    table['role_id'] = mentions[0].id
                    await await_msg.delete()
                    break

            return table, emb_msg

        async def process_tlcer(table, emb_msg):
            print('[@] Memproses TLCer')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='TLCer ID', value="Ketik ID TLC atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['tlcer_id'] = await_msg.content
                        await await_msg.delete()
                        break
                else:
                    table['tlcer_id'] = mentions[0].id
                    await await_msg.delete()
                    break
                #await await_msg.delete()

            return table, emb_msg

        async def process_tlor(table, emb_msg):
            print('[@] Memproses TLor')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Translator ID', value="Ketik ID Translator atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['tlor_id'] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table['tlor_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break

            return table, emb_msg

        async def process_encoder(table, emb_msg):
            print('[@] Memproses Encoder')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Encoder ID', value="Ketik ID Encoder atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['encoder_id'] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table['encoder_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                #await await_msg.delete()

            return table, emb_msg

        async def process_editor(table, emb_msg):
            print('[@] Memproses Editor')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Editor ID', value="Ketik ID Editor atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['editor_id'] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table['editor_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                #await await_msg.delete()

            return table, emb_msg

        async def process_timer(table, emb_msg):
            print('[@] Memproses Timer')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Timer ID', value="Ketik ID Timer atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['timer_id'] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table['timer_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                #await await_msg.delete()

            return table, emb_msg

        async def process_tser(table, emb_msg):
            print('[@] Memproses Typesetter')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Typesetter ID', value="Ketik ID Typesetter atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['tser_id'] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table['tser_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                #await await_msg.delete()

            return table, emb_msg

        async def process_qcer(table, emb_msg):
            print('[@] Memproses QCer')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Quality Checker ID', value="Ketik ID Quality Checker atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['qcer_id'] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table['qcer_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                #await await_msg.delete()

            return table, emb_msg

        def check_setting(gear):
            if not gear:
                return '❌'
            return '✅'

        async def process_pengaturan(table, emb_msg):
            # Inner settings
            async def gear_1(table, emb_msg, gear_data):
                print('[@] Mengatur time_data agar sama')
                if not gear_data:
                    table['old_time_data'] = table['time_data'] # Make sure old time data are not deleted
                    time_table = table['time_data']
                    new_time_table = []
                    for _ in time_table:
                        new_time_table.append(time_table[0])
                    
                    table['time_data'] = new_time_table
                    table['settings']['time_data_are_the_same'] = True
                    return table, emb_msg
                
                new_time_table = []
                for i, _ in enumerate(table['time_data']):
                    new_time_table.append(table['old_time_data'][i])

                table['old_time_data'] = [] # Remove old time data because it resetted
                table['settings']['time_data_are_the_same'] = False
                return table, emb_msg

            print('[@] Showing toogleable settings.')
            while True:
                embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
                embed.set_thumbnail(url=table['poster_img'])
                embed.add_field(name='1⃣ Samakan waktu tayang', value="Status: **{}**\n\nBerguna untuk anime Netflix yang sekali rilis banyak".format(check_setting(table['settings']['time_data_are_the_same'])), inline=False)
                embed.add_field(name='Lain-Lain', value="⏪ Kembali", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)

                to_react = ['1⃣', '⏪'] # ["2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣', '✅', '❌']
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for('reaction_add', check=check_react)
                if user != ctx.message.author:
                    pass
                elif to_react[0] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    table, emb_msg = await gear_1(table, emb_msg, table['settings']['time_data_are_the_same'])
                elif to_react[-1] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    return table, emb_msg

        json_tables, emb_msg = await process_anilist(json_tables, emb_msg)

        if not json_tables:
            print('[@] Proses `tambahutang` dibatalkan')
            return await ctx.send('**Dibatalkan!**')

        json_tables, emb_msg = await process_role(json_tables, emb_msg)
        json_tables, emb_msg = await process_tlor(json_tables, emb_msg)
        json_tables, emb_msg = await process_tlcer(json_tables, emb_msg)
        json_tables, emb_msg = await process_encoder(json_tables, emb_msg)
        json_tables, emb_msg = await process_editor(json_tables, emb_msg)
        json_tables, emb_msg = await process_timer(json_tables, emb_msg)
        json_tables, emb_msg = await process_tser(json_tables, emb_msg)
        json_tables, emb_msg = await process_qcer(json_tables, emb_msg)

        async def fetch_username_from_id(_id):
            try:
                user_data = self.bot.get_user(int(_id))
                return '{}#{}'.format(user_data.name, user_data.discriminator)
            except:
                return 'ERROR'

        print('[@] Checkpoint before sending')
        while True:
            tl_ = await fetch_username_from_id(json_tables['tlor_id'])
            tlc_ = await fetch_username_from_id(json_tables['tlcer_id'])
            enc_ = await fetch_username_from_id(json_tables['encoder_id'])
            ed_ = await fetch_username_from_id(json_tables['editor_id'])
            tm_ = await fetch_username_from_id(json_tables['timer_id'])
            ts_ = await fetch_username_from_id(json_tables['tser_id'])
            qc_ = await fetch_username_from_id(json_tables['qcer_id'])

            embed=discord.Embed(title="Menambah Utang", description="Periksa data!\nReact jika ingin diubah.", color=0xe7e363)
            embed.set_thumbnail(url=json_tables['poster_img'])
            embed.add_field(name="1⃣ Judul", value="{} ({})".format(json_tables['ani_title'], json_tables['anilist_id']), inline=False)
            embed.add_field(name='2⃣ Episode', value="{}".format(json_tables['episodes']), inline=False)
            embed.add_field(name='3⃣ Role', value="{}".format(get_role_name(json_tables['role_id'], ctx.message.guild.roles)), inline=False)
            embed.add_field(name="4⃣ Translator", value=tl_, inline=True)
            embed.add_field(name="5⃣ TLCer", value=tlc_, inline=True)
            embed.add_field(name="6⃣ Encoder", value=enc_, inline=True)
            embed.add_field(name="7⃣ Editor", value=ed_, inline=True)
            embed.add_field(name="8⃣ Timer", value=tm_, inline=True)
            embed.add_field(name="9⃣ Typesetter", value=ts_, inline=True)
            embed.add_field(name="0⃣ Quality Checker", value=qc_, inline=True)
            embed.add_field(name="Lain-Lain", value="🔐 Pengaturan\n✅ Tambahkan!\n❌ Batalkan!", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣', '🔐', '✅', '❌']
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for('reaction_add', check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_anilist(json_tables, emb_msg)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_episode(json_tables, emb_msg)
            elif to_react[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_role(json_tables, emb_msg)
            elif to_react[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_tlor(json_tables, emb_msg)
            elif to_react[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_tlcer(json_tables, emb_msg)
            elif to_react[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_encoder(json_tables, emb_msg)
            elif to_react[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_editor(json_tables, emb_msg)
            elif to_react[7] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_timer(json_tables, emb_msg)
            if to_react[8] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_tser(json_tables, emb_msg)
            elif to_react[9] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_qcer(json_tables, emb_msg)
            elif '🔐' in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_pengaturan(json_tables, emb_msg)
            elif '✅' in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif '❌' in str(res.emoji):
                print('[@] Cancelled')
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send('**Dibatalkan!**')

        # Everything are done and now processing data
        print('[!] Menyimpan utang baru.')
        embed=discord.Embed(title="Menambah Utang", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Membuat data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.edit(embed=embed)

        new_anime_data = {}
        staff_data = {}
        status = {}

        new_anime_data["anilist_id"] = json_tables['anilist_id']
        new_anime_data["last_update"] = str(current_time)
        new_anime_data["role_id"] = json_tables['role_id']

        staff_data["TL"] = json_tables['tlor_id']
        staff_data["TLC"] = json_tables['tlcer_id']
        staff_data["ENC"] = json_tables['encoder_id']
        staff_data["ED"] = json_tables['editor_id']
        staff_data["TM"] = json_tables['timer_id']
        staff_data["TS"] = json_tables['tser_id']
        staff_data["QC"] = json_tables['qcer_id']
        new_anime_data["staff_assignment"] = staff_data

        for x in range(int(json_tables['episodes'])):
            st_data = {}
            staff_status = {}

            staff_status["TL"] = "x"
            staff_status["TLC"] = "x"
            staff_status["ENC"] = "x"
            staff_status["ED"] = "x"
            staff_status["TM"] = "x"
            staff_status["TS"] = "x"
            staff_status["QC"] = "x"

            st_data["status"] = "not_released"
            st_data["airing_time"] = json_tables['time_data'][x]
            st_data["staff_status"] = staff_status
            status[str(x+1)] = st_data

        new_anime_data["status"] = status

        json_d[server_message]["anime"][json_tables['ani_title']] = new_anime_data

        embed=discord.Embed(title="Menambah Utang", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.edit(embed=embed)

        print("[@] Sending data")

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sended.')
        embed=discord.Embed(title="Menambah Utang", color=0x96df6a)
        embed.add_field(name="Sukses!", value='**{}** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi'.format(json_tables['ani_title']), inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)

        print("[%] Updating main database data")
        success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
        await emb_msg.delete()

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        await ctx.send("Berhasil menambahkan **{}** ke dalam database utama naoTimes".format(json_tables['ani_title']))


    @commands.command(aliases=['airing'])
    @commands.guild_only()
    async def jadwal(self, ctx):
        """
        Melihat jadwal anime musiman yang di ambil.
        """
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !jadwal at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        time_data_list = {}
        for ani in server_data['anime']:
            if ani == 'alias':
                continue
            time_data, time_until, episode = await fetch_anilist(server_data['anime'][ani]['anilist_id'], 1, jadwal_only=True)
            if not isinstance(time_data, str):
                continue
            if time_until in time_data_list: # For anime that air at the same time
                time_until += 1
                while True:
                    if time_until not in time_data_list:
                        break
                    time_until += 1
            time_data_list[int(time_until)] = [ani, time_data, episode]

        sorted_time = sorted(deepcopy(time_data_list))
        appendtext = ''
        for s in sorted_time:
            animay, time_data, episode = time_data_list[s]
            appendtext += '**{}** - #{}\n'.format(animay, episode)
            appendtext += time_data + '\n\n'

        if appendtext != '':
            print('Sending message...')
            await ctx.send(appendtext.strip())
        else:
            await ctx.send('**Tidak ada utang pada musim ini yang terdaftar**')


    @commands.command(aliases=['tukangdelay', 'pendelay'])
    @commands.guild_only()
    async def staff(self, ctx, *, judul):
        """
        Menagih utang fansub tukang diley maupun tidak untuk memberikan mereka tekanan
        ---
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !staff at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        staff_assignment = server_data['anime'][matches[0]]['staff_assignment']
        print('Got staff_asignment')

        rtext = 'Staff yang mengerjakaan **{}**\n**Admin**: '.format(matches[0])
        rtext += ''

        async def get_user_name(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return '{}#{}'.format(user_data.name, user_data.discriminator)
            except:
                return '[Rahasia]'

        new_srv_owner = []
        for adm in srv_owner:
            user = await get_user_name(adm)
            new_srv_owner.append(user)

        rtext += ', '.join(new_srv_owner)

        rtext += '\n**Role**: {}'.format(get_role_name(server_data['anime'][matches[0]]['role_id'], ctx.message.guild.roles))

        if 'kolaborasi' in json_d[server_message]['anime'][matches[0]]:
            k_list = []
            for other_srv in json_d[server_message]['anime'][matches[0]]['kolaborasi']:
                if server_message == other_srv:
                    continue
                server_data = self.bot.get_guild(int(other_srv))
                if not server_data:
                    print('[$] Unknown server: {}'.format(other_srv))
                    continue
                k_list.append(server_data.name)
            if k_list:
                rtext += '\n**Kolaborasi dengan**: {}'.format(', '.join(k_list))

        rtext += '\n\n'

        for k, v in staff_assignment.items():
            try:
                user = await get_user_name(v)
                rtext += '**{}**: {}\n'.format(k, user)
            except discord.errors.NotFound:
                rtext += '**{}**: Unknown\n'.format(k)

        rtext += '\n**Jika ada yang Unknown, admin dapat menggantikannya**'

        print('[@] Sending message...')
        await ctx.send(rtext)


    @commands.command(aliases=['mark'])
    @commands.guild_only()
    async def tandakan(self, ctx, posisi, episode_n, *, judul):
        """
        Mark something as done or undone for other episode without announcing it
        """
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !tandakan at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(sorted(srv_anilist))))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']

        current = get_current_ep(status_list)
        if not current:
            return await ctx.send('**Sudah beres digarap!**')

        koleb_list = []
        if 'kolaborasi' in program_info:
            koleb_data = program_info['kolaborasi']
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        posisi = posisi.upper()

        # Toggle status section
        if posisi.lower() not in ['tl', 'tlc', 'enc', 'ed', 'ts', 'tm', 'qc']:
            return await ctx.send('Tidak ada posisi tersebut!')

        if str(ctx.message.author.id) != program_info['staff_assignment'][posisi.upper()]:
            if str(ctx.message.author.id) not in srv_owner:
                return await ctx.send('**Bukan posisi situ untuk mengubahnya!**')

        pos_status = status_list[str(episode_n)]['staff_status']

        if koleb_list:
            for other_srv in koleb_list:
                if other_srv not in json_d:
                    continue
                if pos_status[posisi] == 'x':
                    json_d[other_srv]["anime"][matches[0]]['status'][str(episode_n)]['staff_status'][posisi] = 'y'
                elif pos_status[posisi] == 'y':
                    json_d[other_srv]["anime"][matches[0]]['status'][str(episode_n)]['staff_status'][posisi] = 'x'

        if pos_status[posisi] == 'x':
            json_d[server_message]["anime"][matches[0]]['status'][str(episode_n)]['staff_status'][posisi] = 'y'
            txt_msg = 'Berhasil mengubah status **{st}** **{an}** episode **#{ep}** ke **beres**'
        elif pos_status[posisi] == 'y':
            json_d[server_message]["anime"][matches[0]]['status'][str(episode_n)]['staff_status'][posisi] = 'x'
            txt_msg = 'Berhasil mengubah status **{st}** **{an}** episode **#{ep}** ke **belum beres**'

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Berhasil menandakan ke database local')
        await ctx.send(txt_msg.format(st=posisi, an=matches[0], ep=episode_n))

        print("[%] Updating main database data...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            if osrv not in json_d: # Skip if the server doesn't exist :pepega:
                continue
            print("[%] Updating collaboration server: {}".format(osrv))
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, json_d[osrv])
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                print('[%] Failed updating collaboration server: {}\n\tReason: {}'.format(osrv, msg2))

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)


class ShowtimesAlias(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cog_name = 'Showtimes Alias'

    def __str__(self):
        return 'Showtimes Alias'

    async def choose_anime(self, ctx, matches):
        print('[!] Asking user for input.')
        first_run = True
        matches = matches[:10]
        reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
        res_matches = []
        while True:
            if first_run:
                embed = discord.Embed(title='Mungkin:', color=0x8253b8)

                format_value = []
                for n, i in enumerate(matches):
                    format_value.append('{} **{}**'.format(reactmoji[n], i))
                format_value.append('❌ **Batalkan**')
                embed.description = '\n'.join(format_value)

                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
            reactmoji_extension = ['❌']

            reactmoji = reactmoji[:len(matches)]
            reactmoji.extend(reactmoji_extension)

            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                break
            if user != ctx.message.author:
                pass
            elif '❌' in str(res.emoji):
                await msg.clear_reactions()
                break
            else:
                await msg.clear_reactions()
                reaction_pos = reactmoji.index(str(res.emoji))
                res_matches.append(matches[reaction_pos])
                break
        await msg.delete()
        if res_matches:
            print('[#] Picked: {}'.format(res_matches[0]))
        return res_matches

    @commands.group()
    @commands.guild_only()
    async def alias(self, ctx):
        """
        Initiate alias creation for certain anime
        """
        if not ctx.invoked_subcommand:
            server_message = str(ctx.message.guild.id)
            print('[#] Requested !alias at: ' + server_message)
            json_d = await fetch_json()

            if server_message not in json_d:
                return
            server_data = json_d[server_message]
            print('[@] Found server info on database.')

            srv_anilist = []
            for ani in server_data['anime']:
                if ani == 'alias': # Don't use alias
                    continue
                srv_anilist.append(ani)

            if str(ctx.message.author.id) not in server_data['serverowner']:
                return await ctx.send('Hanya admin yang bisa menambah alias')

            if len(srv_anilist) < 1:
                return await ctx.send("Tidak ada anime yang terdaftar di database")

            print('Membuat data')
            embed = discord.Embed(title="Alias", color=0x56acf3)
            embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await ctx.send(embed=embed)
            msg_author = ctx.message.author
            json_tables = {
                "alias_anime": "",
                "target_anime": ""
            }

            def check_if_author(m):
                return m.author == msg_author

            async def process_anime(table, emb_msg, anime_list):
                print('[@] Memproses anime')
                embed = discord.Embed(title="Alias", color=0x96df6a)
                embed.add_field(name='Judul/Garapan Anime', value="Ketik judul animenya (yang asli), bisa disingkat", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)

                await_msg = await self.bot.wait_for('message', check=check_if_author)
                matches = get_close_matches(await_msg.content, anime_list)
                await await_msg.delete()
                if not matches:
                    await ctx.send('Tidak dapat menemukan judul tersebut di database')
                    return False, False
                elif len(matches) > 1:
                    matches = await self.choose_anime(ctx, matches)
                    if not matches:
                        return await ctx.send('**Dibatalkan!**')

                embed = discord.Embed(title="Alias", color=0x96df6a)
                embed.add_field(name='Apakah benar?', value="Judul: **{}**".format(matches[0]), inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)

                to_react = ['✅', '❌']
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for('reaction_add', check=check_react)
                if user != msg_author:
                    pass
                elif '✅' in str(res.emoji):
                    table['target_anime'] = matches[0]
                    await emb_msg.clear_reactions()
                elif '❌' in str(res.emoji):
                    await ctx.send('**Dibatalkan!**')
                    await emb_msg.clear_reactions()
                    return False, False

                return table, emb_msg

            async def process_alias(table, emb_msg):
                print('[@] Memproses alias')
                embed = discord.Embed(title="Alias", color=0x96df6a)
                embed.add_field(name='Alias', value="Ketik alias yang diinginkan", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)

                await_msg = await self.bot.wait_for('message', check=check_if_author)
                table['alias_anime'] = await_msg.content
                await await_msg.delete()

                return table, emb_msg

            json_tables, emb_msg = await process_anime(json_tables, emb_msg, srv_anilist)

            if not json_tables:
                return print('[@] Cancelled process.')

            json_tables, emb_msg = await process_alias(json_tables, emb_msg)
            print('[@] Making sure.')
            first_time = True
            cancel_toggled = False
            while True:
                embed=discord.Embed(title="Alias", description="Periksa data!\nReact jika ingin diubah.", color=0xe7e363)
                embed.add_field(name="1⃣ Anime/Garapan", value="{}".format(json_tables['target_anime']), inline=False)
                embed.add_field(name='2⃣ Alias', value="{}".format(json_tables['alias_anime']), inline=False)
                embed.add_field(name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                if first_time:
                    await emb_msg.delete()
                    emb_msg = await ctx.send(embed=embed)
                    first_time = False
                else:
                    await emb_msg.edit(embed=embed)

                to_react = ['1⃣', "2⃣", '✅', '❌']
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for('reaction_add', check=check_react)
                if user != ctx.message.author:
                    pass
                if to_react[0] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    json_tables, emb_msg = await process_anime(json_tables, emb_msg, srv_anilist)
                elif to_react[1] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    json_tables, emb_msg = await process_alias(json_tables, emb_msg)
                elif '✅' in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                elif '❌' in str(res.emoji):
                    print('[@] Cancelled.')
                    cancel_toggled = True
                    await emb_msg.clear_reactions()
                    break

            if cancel_toggled:
                return await ctx.send('**Dibatalkan!**')

            # Everything are done and now processing data
            print('[!] Menyimpan data alias.')
            embed=discord.Embed(title="Alias", color=0x56acf3)
            embed.add_field(name="Memproses!", value='Membuat data...', inline=True)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            if json_tables['alias_anime'] in server_data['alias']:
                embed=discord.Embed(title="Alias", color=0xe24545)
                embed.add_field(
                    name="Dibatalkan!", 
                    value='Alias **{}** sudah terdaftar untuk **{}**'.format(
                        json_tables['alias_anime'], 
                        server_data['alias'][json_tables['alias_anime']]
                        ), 
                    inline=True
                )
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.delete()
                return await ctx.send(embed=embed)

            json_d[server_message]['alias'][json_tables['alias_anime']] = json_tables['target_anime']

            embed=discord.Embed(title="Alias", color=0x56acf3)
            embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            print("[@] Sending data")

            with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                json.dump(json_d, f, indent=4)
            print('[@] Sended.')
            embed=discord.Embed(title="Alias", color=0x96df6a)
            embed.add_field(name="Sukses!", value='Alias **{} ({})** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi'.format(json_tables['alias_anime'], json_tables['target_anime']), inline=True)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await ctx.send(embed=embed)
            await emb_msg.delete()

            print("[%] Updating main database data")
            success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])

            if not success:
                print('[%] Failed to update main database data')
                print('\tReason: {}'.format(msg))
                if server_message not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(server_message)
                #await patch_error_handling(self.bot, ctx)

            await ctx.send("Berhasil menambahkan alias **{} ({})** ke dalam database utama naoTimes".format(json_tables['alias_anime'], json_tables['target_anime']))


    @alias.command(name="list")
    async def _list_alias(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !alias list at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_anilist = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(sorted(srv_anilist))))

        matches = get_close_matches(judul, srv_anilist)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        srv_anilist_alias = []
        for k, v in server_data['alias'].items():
            if v in matches:
                srv_anilist_alias.append(k)

        text_value = ''
        if not srv_anilist_alias:
            text_value += 'Tidak ada'

        if not text_value:
            text_value += make_numbered_alias(srv_anilist_alias)
        
        embed=discord.Embed(title="Alias list", color=0x47e0a7)
        embed.add_field(name=matches[0], value=text_value, inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)


    @alias.command(aliases=['remove'])
    async def hapus(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !alias hapus at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa menghapus alias')

        srv_anilist = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)

        if not server_data['alias']:
            return await ctx.send('Tidak ada alias yang terdaftar.')

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(sorted(srv_anilist))))

        matches = get_close_matches(judul, srv_anilist)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        srv_anilist_alias = []
        for k, v in server_data['alias'].items():
            if v in matches:
                srv_anilist_alias.append(k)

        if not srv_anilist_alias:
            return await ctx.send('Tidak ada alias yang terdaftar untuk judul **{}**'.format(matches[0]))
        
        alias_chunked = [srv_anilist_alias[i:i + 5] for i in range(0, len(srv_anilist_alias), 5)]

        first_run = True
        n = 1
        max_n = len(alias_chunked)
        while True:
            if first_run:
                n = 1
                first_run = False
                embed=discord.Embed(title="Alias list", color=0x47e0a7)
                embed.add_field(name='{}'.format(matches[0]), value=make_numbered_alias(alias_chunked[n-1]), inline=False)
                embed.add_field(name="*Informasi*", value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya\n⏩ Selanjutnya\n❌ Batalkan")
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                emb_msg = await ctx.send(embed=embed)

            react_ext = []
            to_react = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣'] # 5 per page
            if max_n == 1 and n == 1:
                pass
            elif n == 1:
                react_ext.append('⏩')
            elif n == max_n:
                react_ext.append('⏪')
            elif n > 1 and n < max_n:
                react_ext.extend(['⏪', '⏩'])

            react_ext.append('❌')
            to_react = to_react[0:len(alias_chunked[n-1])]
            to_react.extend(react_ext)

            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', check=check_react, timeout=30.0)
            except asyncio.TimeoutError:
                return await emb_msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif '⏪' in str(res.emoji):
                n = n - 1
                await emb_msg.clear_reactions()
                embed=discord.Embed(title="Alias list", color=0x47e0a7)
                embed.add_field(name='{}'.format(matches[0]), value=make_numbered_alias(alias_chunked[n-1]), inline=False)
                embed.add_field(name="*Informasi*", value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya\n⏩ Selanjutnya\n❌ Batalkan")
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)
            elif '⏩' in str(res.emoji):
                n = n + 1
                await emb_msg.clear_reactions()
                embed=discord.Embed(title="Alias list", color=0x47e0a7)
                embed.add_field(name='{}'.format(matches[0]), value=make_numbered_alias(alias_chunked[n-1]), inline=False)
                embed.add_field(name="*Informasi*", value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya\n⏩ Selanjutnya\n❌ Batalkan")
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)
            elif '❌' in str(res.emoji):
                await emb_msg.clear_reactions()
                return await ctx.send('**Dibatalkan!**')
            else:
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                index_del = to_react.index(str(res.emoji))
                n_del = alias_chunked[n-1][index_del]
                del json_d[server_message]['alias'][n_del]
                
                with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                    json.dump(json_d, f, indent=4)

                await ctx.send('Alias **{} ({})** telah dihapus dari database'.format(n_del, matches[0]))
                
                print("[%] Updating main database data")
                success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])

                if not success:
                    print('[%] Failed to update main database data')
                    print('\tReason: {}'.format(msg))
                    if server_message not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(server_message)
                    #await patch_error_handling(self.bot, ctx)

                await emb_msg.delete()


class ShowtimesKolaborasi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cog_name = 'Showtimes Kolaborasi'

    def __str__(self):
        return 'Showtimes Kolaborasi'

    async def choose_anime(self, ctx, matches):
        print('[!] Asking user for input.')
        first_run = True
        matches = matches[:10]
        reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
        res_matches = []
        while True:
            if first_run:
                embed = discord.Embed(title='Mungkin:', color=0x8253b8)

                format_value = []
                for n, i in enumerate(matches):
                    format_value.append('{} **{}**'.format(reactmoji[n], i))
                format_value.append('❌ **Batalkan**')
                embed.description = '\n'.join(format_value)

                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
            reactmoji_extension = ['❌']

            reactmoji = reactmoji[:len(matches)]
            reactmoji.extend(reactmoji_extension)

            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                break
            if user != ctx.message.author:
                pass
            elif '❌' in str(res.emoji):
                await msg.clear_reactions()
                break
            else:
                await msg.clear_reactions()
                reaction_pos = reactmoji.index(str(res.emoji))
                res_matches.append(matches[reaction_pos])
                break
        await msg.delete()
        if res_matches:
            print('[#] Picked: {}'.format(res_matches[0]))
        return res_matches

    @commands.group(aliases=['joint', 'join', 'koleb'])
    @commands.guild_only()
    async def kolaborasi(self, ctx):
        if not ctx.invoked_subcommand:
            helpmain = discord.Embed(title="Bantuan Perintah (!kolaborasi)", description="versi 2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='!kolaborasi', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!kolaborasi dengan <server_id_kolaborasi> <judul>', value="```Kolaborasi anime tertentu dengan fansub/server lain```", inline=False)
            helpmain.add_field(name='!kolaborasi konfirmasi <kode>', value="```Konfirmasi kolaborasi anime dengan kode unik```", inline=False)
            helpmain.add_field(name='!kolaborasi putus <judul>', value="```Memutuskan hubungan sinkronisasi data dengan semua fansub yang diajak kolaborasi```", inline=False)
            helpmain.add_field(name='!kolaborasi batalkan <server_id_kolaborasi> <kode>', value="```Membatalkan kode konfirmasi kolaborasi dengan fansub lain```", inline=False)
            helpmain.add_field(name='Aliases', value="!kolaborasi, !joint, !join, !koleb", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)

    @kolaborasi.command()
    async def dengan(self, ctx, server_id, *, judul):
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !kolaborasi dengan at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa memulai kolaborasi')

        if server_id not in json_d:
            return await ctx.send('Tidak dapat menemukan server tersebut di database')

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        if 'kolaborasi' in server_data['anime'][matches[0]]:
            if server_id in server_data['anime'][matches[0]]['kolaborasi']:
                return await ctx.send('Server tersebut sudah diajak kolaborasi.')

        randomize_confirm = ''.join(choice(ascii_lowercase+digits) for i in range(16))

        cancel_toggled = False
        first_time = True
        while True:
            try:
                server_identd = self.bot.get_guild(int(server_id))
                server_ident = server_identd.name
            except:
                server_ident = server_id
            embed=discord.Embed(title="Kolaborasi", description="Periksa data!\nReact jika ingin diubah.", color=0xe7e363)
            embed.add_field(name="Anime/Garapan", value=matches[0], inline=False)
            embed.add_field(name='Server', value=server_ident, inline=False)
            embed.add_field(name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            if first_time:
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = ['✅', '❌']
            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for('reaction_add', check=check_react)
            if user != ctx.message.author:
                pass
            elif '✅' in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif '❌' in str(res.emoji):
                print('[@] Cancelled.')
                cancel_toggled = True
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break

        if cancel_toggled:
            return await ctx.send('**Dibatalkan!**')

        table_data = {}
        table_data['anime'] = matches[0]
        table_data['server'] = server_message

        if 'konfirmasi' not in json_d[server_id]:
            json_d[server_id]['konfirmasi'] = {}
        json_d[server_id]['konfirmasi'][randomize_confirm] = table_data

        embed=discord.Embed(title="Kolaborasi", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.edit(embed=embed)

        print("[@] Sending data")

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sended.')
        embed=discord.Embed(title="Kolaborasi", color=0x96df6a)
        embed.add_field(name="Sukses!", value='Berikan kode berikut `{}` kepada fansub/server lain.\nDatabase utama akan diupdate sebentar lagi'.format(randomize_confirm), inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.delete()
        await ctx.send(embed=embed)

        print("[%] Updating main database data")
        success, msg = await self.bot.ntdb.kolaborasi_dengan(server_id, randomize_confirm, table_data)

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        await ctx.send("Berikan kode berikut `{rand}` kepada fansub/server lain.\nKonfirmasi di server lain dengan `!kolaborasi konfirmasi {rand}`".format(rand=randomize_confirm))


    @kolaborasi.command()
    async def konfirmasi(self, ctx, konfirm_id):
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !kolaborasi konfirmasi at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa konfirmasi kolaborasi.')

        if 'konfirmasi' not in server_data:
            return await ctx.send('Tidak ada kolaborasi yang harus dikonfirmasi.')
        if konfirm_id not in server_data['konfirmasi']:
            return await ctx.send('Tidak dapat menemukan kode kolaborasi yang diberikan.')

        klb_data = server_data['konfirmasi'][konfirm_id]

        try:
            server_identd = self.bot.get_guild(int(klb_data['server']))
            server_ident = server_identd.name
        except:
            server_ident = klb_data['server']

        embed=discord.Embed(title="Konfirmasi Kolaborasi", color=0xe7e363)
        embed.add_field(name="Anime/Garapan", value=klb_data['anime'], inline=False)
        embed.add_field(name='Server', value=server_ident, inline=False)
        embed.add_field(name="Lain-Lain", value="✅ Konfirmasi!\n❌ Batalkan!", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await ctx.send(embed=embed)

        to_react = ['✅', '❌']
        for react in to_react:
            await emb_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != emb_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        res, user = await self.bot.wait_for('reaction_add', check=check_react)
        if user != ctx.message.author:
            pass
        if '✅' in str(res.emoji):
            await emb_msg.clear_reactions()
        elif '❌' in str(res.emoji):
            print('[@] Cancelled.')
            await emb_msg.clear_reactions()
            return await ctx.send('**Dibatalkan!**')

        ani_srv_role = ''
        if klb_data['anime'] in server_data['anime']:
            print('[@] Existing data, removing and changing from other server')
            ani_srv_role += server_data['anime'][klb_data['anime']]['role_id']
            del server_data['anime'][klb_data['anime']]

        if not ani_srv_role:
            c_role = await ctx.message.guild.create_role(
                name=klb_data['anime'],
                colour=discord.Colour(0xdf2705),
                mentionable=True
            )
            ani_srv_role = str(c_role.id)

        other_anime_data = json_d[klb_data['server']]['anime'][klb_data['anime']]
        copied_data = deepcopy(other_anime_data)
        json_d[server_message]['anime'][klb_data['anime']] = copied_data
        json_d[server_message]['anime'][klb_data['anime']]['role_id'] = ani_srv_role

        join_srv = [klb_data['server'], server_message]
        if 'kolaborasi' in server_data['anime'][klb_data['anime']]:
            join_srv.extend(server_data['anime'][klb_data['anime']]['kolaborasi'])
        join_srv = list(dict.fromkeys(join_srv))
        if 'kolaborasi' in other_anime_data:
            join_srv.extend(other_anime_data['kolaborasi'])
        join_srv = list(dict.fromkeys(join_srv))
        other_anime_data['kolaborasi'] = join_srv

        json_d[server_message]['anime'][klb_data['anime']]['kolaborasi'] = join_srv
        del json_d[server_message]['konfirmasi'][konfirm_id]

        embed=discord.Embed(title="Kolaborasi", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.edit(embed=embed)

        print("[@] Sending data")

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sended.')
        embed=discord.Embed(title="Kolaborasi", color=0x96df6a)
        embed.add_field(name="Sukses!", value='Berhasil konfirmasi dengan server **{}**.\nDatabase utama akan diupdate sebentar lagi'.format(klb_data['server']), inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.delete()
        await ctx.send(embed=embed)

        print('[%] Updating main database data')
        success, msg = await self.bot.ntdb.kolaborasi_konfirmasi(
            klb_data['server'], server_message,
            json_d[klb_data['server']], json_d[server_message]
        )

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        await ctx.send("Berhasil menambahkan kolaborasi dengan **{}** ke dalam database utama naoTimes\nBerikan role berikut agar bisa menggunakan perintah staff <@&{}>".format(klb_data['server'], ani_srv_role))


    @kolaborasi.command()
    async def batalkan(self, ctx, server_id, konfirm_id):
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !kolaborasi batalkan at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa membatalkan kolaborasi')

        if server_id not in json_d:
            return await ctx.send('Tidak dapat menemukan server tersebut di database')

        other_srv_data = json_d[server_id]

        if 'konfirmasi' not in other_srv_data:
            return await ctx.send('Tidak ada kolaborasi yang harus dikonfirmasi.')
        if konfirm_id not in other_srv_data['konfirmasi']:
            return await ctx.send('Tidak dapat menemukan kode kolaborasi yang diberikan.')

        del json_d[server_id]['konfirmasi'][konfirm_id]

        print("[@] Sending data")

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sended.')
        embed=discord.Embed(title="Kolaborasi", color=0x96df6a)
        embed.add_field(name="Sukses!", value='Berhasil membatalkan kode konfirmasi **{}**.\nDatabase utama akan diupdate sebentar lagi'.format(konfirm_id), inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)

        print("[%] Updating main database data")
        success, msg = await self.bot.ntdb.kolaborasi_batalkan(server_id, konfirm_id)

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        await ctx.send("Berhasil membatalkan kode konfirmasi **{}** dari database utama naoTimes".format(konfirm_id))


    @kolaborasi.command()
    async def putus(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        print('[#] Requested !kolaborasi putus at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa memputuskan kolaborasi')

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        program_info = server_data['anime'][matches[0]]

        if 'kolaborasi' not in program_info:
            return await ctx.send('Tidak ada kolaborasi sama sekali pada judul ini.')

        for x in program_info['kolaborasi']:
            koleb_list_othersrv = deepcopy(json_d[x]['anime'][matches[0]]['kolaborasi'])
            koleb_list_othersrv.remove(server_message)

        for osrv in program_info['kolaborasi']:
            klosrv = deepcopy(json_d[osrv]['anime'][matches[0]]['kolaborasi'])
            klosrv.remove(server_message)

            remove_all = False
            if len(klosrv) == 1:
                if klosrv[0] == osrv:
                    remove_all = True

            if remove_all:
                del json_d[osrv]['anime'][matches[0]]['kolaborasi']
            else:
                json_d[osrv]['anime'][matches[0]]['kolaborasi'] = klosrv

        del json_d[server_message]['anime'][matches[0]]['kolaborasi']
        print("[@] Sending data")

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('[@] Sended.')
        embed=discord.Embed(title="Kolaborasi", color=0x96df6a)
        embed.add_field(name="Sukses!", value='Berhasil memputuskan kolaborasi **{}**.\nDatabase utama akan diupdate sebentar lagi'.format(matches[0]), inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)

        print("[%] Updating main database data")
        success, msg = await self.bot.ntdb.kolaborasi_putuskan(server_message, matches[0])

        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)
            #await patch_error_handling(self.bot, ctx)

        await ctx.send("Berhasil memputuskan kolaborasi **{}** dari database utama naoTimes".format(matches[0]))


class ShowtimesAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def __str__(self):
        return 'Showtimes Admin'


    @commands.group(aliases=['naotimesadmin', 'naoadmin'])
    @commands.is_owner()
    @commands.guild_only()
    async def ntadmin(self, ctx):
        if ctx.invoked_subcommand is None:
            helpmain = discord.Embed(title="Bantuan Perintah (!ntadmin)", description="versi 2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimesAdmin", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='!ntadmin', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!ntadmin tambah <server id> <id admin> <progress_channel>', value="```Menambahkan server baru ke naoTimes```", inline=False)
            helpmain.add_field(name='!ntadmin hapus <server id>', value="```Menghapus server dari naoTimes```", inline=False)
            helpmain.add_field(name='!ntadmin tambahadmin <server id> <id admin>', value="```Menambahkan admin baru ke server yang terdaftar```", inline=False)
            helpmain.add_field(name='!ntadmin hapusadmin <server id> <id admin>', value="```Menghapus admin dari server yang terdaftar```", inline=False)
            helpmain.add_field(name='!ntadmin fetchdb', value="```Mengambil database dan menguploadnya ke discord```", inline=False)
            helpmain.add_field(name='!ntadmin patchdb', value="```Menganti database dengan attachments yang dicantumkan\nTambah attachments lalu tulis !ntadmin patchdb dan enter```", inline=False)
            helpmain.add_field(name='!ntadmin forceupdate', value="```Memaksa update database utama gist dengan database local.```", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)


    @ntadmin.command()
    async def listserver(self, ctx):
        print('[#] Requested !ntadmin listserver by admin')
        json_d = await fetch_json()
        if not json_d:
            return

        srv_list = []
        for i, _ in json_d.items():
            if i == "supermod":
                continue
            srv_ = self.bot.get_guild(int(i))
            if not srv_:
                print('[$] Unknown server: {}'.format(i))
                continue
            srv_list.append("{} ({})".format(srv_.name, i))


        text = '**List server ({} servers):**\n'.format(len(srv_list))
        for x in srv_list:
            text += x + '\n'

        text = text.rstrip('\n')

        await ctx.send(text)


    @ntadmin.command()
    async def listresync(self, ctx):
        resynclist = self.bot.showtimes_resync
        if not resynclist:
            return await ctx.send("**Server that still need to be resynced**: None")
        resynclist = ["- {}\n".format(x) for x in resynclist]
        main_text = "**Server that still need to be resynced**:\n"
        main_text += "".join(resynclist)
        main_text = main_text.rstrip('\n')
        await ctx.send(main_text)


    @ntadmin.command()
    async def migratedb(self, ctx):
        await ctx.send("Mulai migrasi database!")
        url = 'https://gist.githubusercontent.com/{u}/{g}/raw/nao_showtimes.json'
        async with aiohttp.ClientSession() as session:
            while True:
                headers = {'User-Agent': 'naoTimes v2.0'}
                print('\t[#] Fetching nao_showtimes.json')
                async with session.get(url.format(u=bot_config['github_info']['username'], g=bot_config['gist_id']), headers=headers) as r:
                    try:
                        r_data = await r.text()
                        js_data = json.loads(r_data)
                        print('\t[@] Fetched and saved.')
                        break
                    except IndexError:
                        pass
        await ctx.send("Berhasil mendapatkan database dari github, mulai migrasi ke MongoDB")
        await self.bot.ntdb.patch_all_from_json(js_data)
        await ctx.send("Selesai migrasi database, silakan di coba cuk.")
    
    @ntadmin.command()
    async def initiate(self, ctx):
        """
        Initiate naoTimes on this server so it can be used on other server
        Make sure everything is filled first before starting this command
        """
        print('[@] Initiated naoTimes first-time setup')
        if bot_config['gist_id'] != "":
            print('[@] Already setup, skipping')
            return await ctx.send('naoTimes sudah dipersiapkan dan sudah bisa digunakan')

        print('Membuat data')
        embed = discord.Embed(title="naoTimes", color=0x56acf3)
        embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "id": "",
            "owner_id": str(msg_author.id),
            "progress_channel": ""
        }

        def check_if_author(m):
            return m.author == ctx.message.author

        async def process_gist(table, emb_msg, author):
            print('[@] Memproses database')
            embed = discord.Embed(title="naoTimes", color=0x96df6a)
            embed.add_field(name='Gist ID', value="Ketik ID Gist GitHub", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            await_msg = await self.bot.wait_for('message', check=check_if_author)
            table['id'] = str(await_msg.content)

            return table, emb_msg

        async def process_progchan(table, emb_msg, author):
            print('[@] Memproses #progress channel')
            embed = discord.Embed(title="naoTimes", color=0x96df6a)
            embed.add_field(name='#progress channel ID', value="Ketik ID channel", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                if await_msg.content.isdigit():
                    table['progress_channel'] = str(await_msg.content)
                    await await_msg.delete()
                    break
                await await_msg.delete()

            return table, emb_msg

        async def process_owner(table, emb_msg, author):
            print('[@] Memproses ID Owner')
            embed = discord.Embed(title="naoTimes", color=0x96df6a)
            embed.add_field(name='Owner ID', value="Ketik ID Owner server atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['owner_id'] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table['owner_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                await await_msg.delete()

            return table, emb_msg

        json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)

        print('[@] Making sure.')
        first_time = True
        cancel_toggled = False
        while True:
            embed=discord.Embed(title="naoTimes", description="Periksa data!\nReact jika ingin diubah.", color=0xe7e363)
            embed.add_field(name="1⃣ Gists ID", value="{}".format(json_tables['id']), inline=False)
            embed.add_field(name='2⃣ Owner ID', value="{}".format(json_tables['owner_id']), inline=False)
            embed.add_field(name='3⃣ #progress channel ID', value="{}".format(json_tables['progress_channel']), inline=False)
            embed.add_field(name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = ['1⃣', "2⃣", '3⃣', '✅', '❌']
            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for('reaction_add', check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_owner(json_tables, emb_msg, msg_author)
            elif to_react[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)
            elif '✅' in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif '❌' in str(res.emoji):
                print('[@] Cancelled')
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send('**Dibatalkan!**')

        embed=discord.Embed(title="naoTimes", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.edit(embed=embed)

        main_data = {}
        server_data = {}
        main_data['supermod'] = [json_tables['owner_id']]
        
        server_data['serverowner'] = [json_tables['owner_id']]
        server_data['announce_channel'] = json_tables['progress_channel']
        server_data['anime'] = {}
        server_data['alias'] = {}

        main_data[str(ctx.message.guild.id)] = server_data
        print('[@] Sending data')
        await dump_json(main_data)
        _ = await self.bot.ntdb.patch_all_from_json(main_data)

        print('[@] Reconfiguring config files')
        bot_config['gist_id'] = json_tables['gist_id']
        with open('config.json', 'w') as fp:
            json.dump(bot_config, fp, indent=4)
        print('[@] Reconfigured. Every configuration are done, please restart.')
        embed=discord.Embed(title="naoTimes", color=0x56acf3)
        embed.add_field(name="Sukses!", value='Sukses membuat database di github\nSilakan restart bot agar naoTimes dapat diaktifkan.\n\nLaporkan isu di: [GitHub Issue](https://github.com/noaione/naoTimes/issues)', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)
        await emb_msg.delete()

    @ntadmin.command()
    async def fetchdb(self, ctx):
        print('[#] Requested !ntadmin fetchdb by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        channel = ctx.message.channel

        print('Saving .json')
        save_file_name = str(int(round(time.time()))) + '_naoTimes_database.json'
        with open(save_file_name, 'w') as f:
            json.dump(json_d, f)

        print('Sending .json')
        await channel.send(content='Here you go!', file=discord.File(save_file_name))
        os.remove(save_file_name) # Cleanup


    @ntadmin.command()
    async def forcepull(self, ctx):
        print('[#] Requested !ntadmin forcepull by owner')
        json_d = await fetch_json()
        if not json_d:
            return
        channel = ctx.message.channel

        json_d = await self.bot.ntdb.fetch_all_as_json()
        with open('nao_showtimes.json', 'w', encoding="utf-8") as fp:
            json.dump(json_d, fp, indent=2)
        await channel.send('Newest database has been pulled and saved to local save')


    @ntadmin.command()
    @commands.guild_only()
    async def patchdb(self, ctx):
        """
        !! Warning !!
        This will patch entire database
        """
        print('[#] Requested !ntadmin patchdb by admin')

        if ctx.message.attachments == []:
            await ctx.message.delete()
            return await ctx.send('Please provide a valid .json file by uploading and add `!!ntadmin patchdb` command')

        print('[@] Fetching attachments')

        attachment = ctx.message.attachments[0]
        uri = attachment.url
        filename = attachment.filename

        if filename[filename.rfind('.'):] != '.json':
            await ctx.message.delete()
            return await ctx.send('Please provide a valid .json file by uploading and add `!!ntadmin patchdb` command')

        # Start downloading .json file
        print('[@] Downloading file')
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(uri) as resp:
                data = await resp.text()
                await ctx.message.delete()
                json_to_patch = json.loads(data)

        print('[@] Make sure.')
        preview_msg = await ctx.send('**Are you sure you want to patch the database with provided .json file?**')
        to_react = ['✅', '❌']
        for react in to_react:
            await preview_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != preview_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        try:
            res, user = await self.bot.wait_for('reaction_add', timeout=15, check=check_react)
        except asyncio.TimeoutError:
            await ctx.send('***Timeout!***')
            return await preview_msg.clear_reactions()
        if user != ctx.message.author:
            pass
        elif '✅' in str(res.emoji):
            with open('nao_showtimes.json', 'w') as fp:
                json.dump(json_to_patch, fp, indent=4)
            success = await self.bot.ntdb.patch_all_from_json(json_to_patch)
            await preview_msg.clear_reactions()
            if success:
                return await preview_msg.edit(content='**Patching success!, try it with !tagih**')
            await preview_msg.edit(content='**Patching failed!, try it again later**')
        elif '❌' in str(res.emoji):
            print('[@] Patch Cancelled')
            await preview_msg.clear_reactions()
            await preview_msg.edit(content='**Ok, cancelled process**')


    @ntadmin.command()
    async def tambah(self, ctx, srv_id, adm_id, prog_chan=None):
        """
        Menambah server baru ke database naoTimes
        
        :srv_id: server id
        :adm_id: admin id
        :prog_chan: #progress channel id
        """

        print('[#] Requested !ntadmin tambah by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            return await ctx.send('Tidak ada input server dari user')

        if adm_id is None:
            return await ctx.send('Tidak ada input admin dari user')

        if srv_id in json_d:
            return await ctx.send('Server `{}` tersebut telah terdaftar di database'.format(srv_id))

        new_srv_data = {}

        new_srv_data['serverowner'] = [str(adm_id)]
        if prog_chan:
            new_srv_data['announce_channel'] = str(prog_chan)
        new_srv_data['anime'] = {}
        new_srv_data['alias'] = {}

        json_d[str(srv_id)] = new_srv_data
        if str(adm_id) not in json_d['supermod']:
            json_d['supermod'].append(str(adm_id)) # Add to supermod list
        print('[#] Created new table for server: {}'.format(srv_id))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        if not prog_chan:
            prog_chan = None

        success, msg = await self.bot.ntdb.new_server(str(srv_id), str(adm_id), prog_chan)
        if not success:
            print('[%] Failed to update, reason: {}'.format(msg))
            if str(srv_id) not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(srv_id))
        await ctx.send('Sukses menambah server dengan info berikut:\n```Server ID: {s}\nAdmin: {a}\nMemakai #progress Channel: {p}```'.format(s=srv_id, a=adm_id, p=bool(prog_chan)))


    @ntadmin.command()
    async def hapus(self, ctx, srv_id):
        """
        Menghapus server dari database naoTimes
        
        :srv_id: server id
        """
        print('[#] Requested !ntadmin hapus by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            return await ctx.send('Tidak ada input server dari user')

        try:
            srv = json_d[str(srv_id)]
            adm_id = srv['serverowner'][0]
            print('Server found, deleting...')
            del json_d[str(srv_id)]
        except KeyError:
            return await ctx.send('Server tidak dapat ditemukan dalam database.')

        try:
            json_d['supermod'].remove(adm_id)
        except:
            return await ctx.send('Gagal menghapus admin dari data super admin')

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success, msg = await self.bot.ntdb.remove_server(srv_id, adm_id)
        if not success:
            await ctx.send("Terdapat kegagalan ketika ingin menghapus server\nalasan: {}".format(msg))
        await ctx.send('Sukses menghapus server `{s}` dari naoTimes'.format(s=srv_id))


    @ntadmin.command()
    async def tambahadmin(self, ctx, srv_id, adm_id):
        """
        Menambah admin ke server ke database naoTimes
        
        :srv_id: server id
        :adm_id: admin id
        """

        print('[#] Requested !ntadmin tambahadmin by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            return await ctx.send('Tidak ada input server dari user')

        if adm_id is None:
            return await ctx.send('Tidak ada input admin dari user')

        srv_id = str(srv_id)
        try:
            srv = json_d[srv_id]
            print('Server found, adding admin...')
            if adm_id in srv['serverowner']:
                return await ctx.send('Admin `{}` telah terdaftar di server tersebut.'.format(adm_id))
        except KeyError:
            return await ctx.send('Server tidak dapat ditemukan dalam database.')

        srv['serverowner'].append(str(adm_id))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success, msg = await self.bot.ntdb.update_data_server(srv_id, json_d[srv_id])
        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        await ctx.send('Sukses menambah admin `{a}` di server `{s}`'.format(s=srv_id, a=adm_id))


    @ntadmin.command()
    async def hapusadmin(self, ctx, srv_id, adm_id):
        """
        Menghapus admin dari server dari database naoTimes
        
        :srv_id: server id
        :adm_id: admin id
        """
        print('[#] Requested !ntadmin hapusadmin by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            return await ctx.send('Tidak ada input server dari user')

        if adm_id is None:
            return await ctx.send('Tidak ada input admin dari user')

        srv_id = str(srv_id)
        adm_id = str(adm_id)
        try:
            srv = json_d[srv_id]
            print('Server found, finding admin...')
            admlist = srv['serverowner']
            if adm_id in admlist:
                srv['serverowner'].remove(adm_id)
            else:
                return await ctx.send('Tidak dapat menemukan admin tersebut di server: `{}`'.format(srv_id))
        except KeyError:
            return await ctx.send('Server tidak dapat ditemukan dalam database.')

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        print('[%] Removing admin from main database')
        success, msg = await self.bot.ntdb.update_data_server(srv_id, json_d[srv_id])
        if not success:
            print('[%] Failed to update main database data')
            print('\tReason: {}'.format(msg))
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        await ctx.send('Sukses menghapus admin `{a}` dari server `{s}`'.format(s=srv_id, a=adm_id))
        if adm_id in admlist:
            success, msg = await self.bot.ntdb.remove_top_admin(adm_id)
            if not success:
                await ctx.send("Tetapi gagal menghapus admin dari top_admin.")

    
    @ntadmin.command()
    @commands.guild_only()
    async def forceupdate(self, ctx):
        print('[#] Requested forceupdate by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        print('[@] Make sure')
        
        preview_msg = await ctx.send('**Are you sure you want to patch the database with local .json file?**')
        to_react = ['✅', '❌']
        for react in to_react:
            await preview_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != preview_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        try:
            res, user = await self.bot.wait_for('reaction_add', timeout=15, check=check_react)
        except asyncio.TimeoutError:
            await ctx.send('***Timeout!***')
            return await preview_msg.clear_reactions()
        if user != ctx.message.author:
            pass
        elif '✅' in str(res.emoji):
            success = await self.bot.ntdb.patch_all_from_json(json_d)
            await preview_msg.clear_reactions()
            if success:
                return await preview_msg.edit(content='**Patching success!, try it with !tagih**')
            await preview_msg.edit(content='**Patching failed!, try it again later**')
        elif '❌' in str(res.emoji):
            print('[@] Patch Cancelled')
            await preview_msg.clear_reactions()
            await preview_msg.edit(content='**Ok, cancelled process**')


class ShowtimesConfigData(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def __str__(self):
        return 'Showtimes Data Configuration'


    async def choose_anime(self, ctx, matches):
        print('[!] Asking user for input.')
        first_run = True
        matches = matches[:10]
        reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
        res_matches = []
        while True:
            if first_run:
                embed = discord.Embed(title='Mungkin:', color=0x8253b8)

                format_value = []
                for n, i in enumerate(matches):
                    format_value.append('{} **{}**'.format(reactmoji[n], i))
                format_value.append('❌ **Batalkan**')
                embed.description = '\n'.join(format_value)

                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣']
            reactmoji_extension = ['❌']

            reactmoji = reactmoji[:len(matches)]
            reactmoji.extend(reactmoji_extension)

            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                await msg.clear_reactions()
                break
            if user != ctx.message.author:
                pass
            elif '❌' in str(res.emoji):
                await msg.clear_reactions()
                break
            else:
                await msg.clear_reactions()
                reaction_pos = reactmoji.index(str(res.emoji))
                res_matches.append(matches[reaction_pos])
                break
        await msg.delete()
        if res_matches:
            print('[#] Picked: {}'.format(res_matches[0]))
        return res_matches

    @commands.command()
    @commands.guild_only()
    async def ubahdata(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        print('[@] Requested !ubahdata at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('[@] Found server info on database.')

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            if ani == 'alias': # Don't use alias
                continue
            srv_anilist.append(ani)
        for k, _ in server_data['alias'].items():
            srv_anilist_alias.append(k)

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa mengubah data garapan.')

        if len(srv_anilist) < 1:
            return await ctx.send('**Tidak ada anime yang terdaftar di database**')

        if not judul:
            if len(srv_anilist) < 1:
                return await ctx.send('**Tidak ada anime yang terdaftar di database**')
            return await ctx.send('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('[!] Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            matches = await self.choose_anime(ctx, matches)
            if not matches:
                return await ctx.send('**Dibatalkan!**')

        program_info = json_d[server_message]['anime'][matches[0]]

        koleb_list = []
        if 'kolaborasi' in program_info:
            koleb_data = program_info['kolaborasi']
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        def check_if_author(m):
            return m.author == ctx.message.author

        async def get_user_name(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return '{}#{}'.format(user_data.name, user_data.discriminator)
            except:
                return 'ERROR'

        async def internal_change_staff(role, staff_list, emb_msg):
            better_names =  {
                "TL": "Translator",
                "TLC": "TLCer",
                "ENC": "Encoder",
                "ED": "Editor",
                "TM": "Timer",
                "TS": "Typesetter",
                "QC": "Quality Checker"
            }
            embed = discord.Embed(title="Mengubah Staff", color=0xeb79b9)
            embed.add_field(name='{} ID'.format(better_names[role]), value="Ketik ID {} atau mention orangnya".format(better_names[role]), inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        staff_list[role] = await_msg.content
                        await await_msg.delete()
                        break
                else:
                    staff_list[role] = str(mentions[0].id)
                    await await_msg.delete()
                    break
            return staff_list, emb_msg


        async def ubah_staff(emb_msg):
            first_run = True
            print('[@] Memproses Staff')
            while True:
                if first_run:
                    staff_list = deepcopy(json_d[server_message]['anime'][matches[0]]['staff_assignment'])
                    staff_list_key = list(staff_list.keys())
                    first_run = False

                staff_list_name = {}
                for k, v in staff_list.items():
                    usr_ = await get_user_name(v)
                    staff_list_name[k] = usr_

                embed=discord.Embed(title="Mengubah Staff", description="Anime: {}".format(matches[0]), color=0xeba279)
                embed.add_field(name="1⃣ TLor", value=staff_list_name['TL'], inline=False)
                embed.add_field(name='2⃣ TLCer', value=staff_list_name['TLC'], inline=False)
                embed.add_field(name='3⃣ Encoder', value=staff_list_name['ENC'], inline=False)
                embed.add_field(name="4⃣ Editor", value=staff_list_name['ED'], inline=True)
                embed.add_field(name="5⃣ Timer", value=staff_list_name['TM'], inline=True)
                embed.add_field(name="6⃣ Typeseter", value=staff_list_name['TS'], inline=True)
                embed.add_field(name="7⃣ QCer", value=staff_list_name['QC'], inline=True)
                embed.add_field(name="Lain-Lain", value="✅ Selesai!", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)

                reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '✅']

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for('reaction_add', check=check_react)
                if user != ctx.message.author:
                    pass
                elif '✅' in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                else:
                    await emb_msg.clear_reactions()
                    reaction_pos = reactmoji.index(str(res.emoji))
                    staff_list, emb_msg = await internal_change_staff(staff_list_key[reaction_pos], staff_list, emb_msg)

            json_d[server_message]['anime'][matches[0]]['staff_assignment'] = staff_list
            if koleb_list:
                for other_srv in koleb_list:
                    if other_srv not in json_d:
                        continue
                    json_d[other_srv]['anime'][matches[0]]['staff_assignment'] = staff_list

            return emb_msg


        async def ubah_role(emb_msg):
            print('[@] Memproses Role')
            embed = discord.Embed(title="Mengubah Role", color=0xeba279)
            embed.add_field(name='Role ID', value="Ketik ID Role atau mention rolenya\nAtau ketik `auto` untuk membuatnya otomatis", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)
                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        json_d[server_message]['anime'][matches[0]]['role_id'] = await_msg.content
                        await await_msg.delete()
                        break
                    elif await_msg.content.startswith('auto'):
                        c_role = await ctx.message.guild.create_role(
                            name=matches[0],
                            colour=discord.Colour(0xdf2705),
                            mentionable=True
                        )
                        json_d[server_message]['anime'][matches[0]]['role_id'] = str(c_role.id)
                        await await_msg.delete()
                        break
                else:
                    json_d[server_message]['anime'][matches[0]]['role_id'] = str(mentions[0].id)
                    await await_msg.delete()
                    break

            xdddd = await ctx.send('Berhasil menambah role ID ke {}'.format(json_d[server_message]['anime'][matches[0]]['role_id']))
            await asyncio.sleep(2)
            await xdddd.delete()

            return emb_msg

        async def tambah_episode(emb_msg):
            print('[@] Memproses Tambah Episode')

            status_list = program_info['status']
            max_episode = list(status_list.keys())[-1]
            _, _, _, time_data, _ = await fetch_anilist(program_info['anilist_id'], 1, max_episode, True)

            embed = discord.Embed(title="Menambah Episode", description='Jumlah Episode Sekarang: {}'.format(max_episode), color=0xeba279)
            embed.add_field(name='Masukan jumlah episode yang diinginkan.', value=tambahepisode_instruct, inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)

                if await_msg.content.isdigit():
                    jumlah_tambahan = int(await_msg.content)
                    await await_msg.delete()
                    break
            
            for x in range(int(max_episode) + 1, int(max_episode) + jumlah_tambahan + 1): # range(int(c), int(c)+int(x))
                st_data = {}
                staff_status = {}

                staff_status["TL"] = "x"
                staff_status["TLC"] = "x"
                staff_status["ENC"] = "x"
                staff_status["ED"] = "x"
                staff_status["TM"] = "x"
                staff_status["TS"] = "x"
                staff_status["QC"] = "x"

                st_data["status"] = "not_released"
                try:
                    st_data["airing_time"] = time_data[x-1]
                except IndexError:
                    pass
                st_data["staff_status"] = staff_status
                if koleb_list:
                    for other_srv in koleb_list:
                        if other_srv not in json_d:
                            continue
                        json_d[other_srv]['anime'][matches[0]]['status'][str(x)] = st_data
                json_d[server_message]['anime'][matches[0]]['status'][str(x)] = st_data

            if koleb_list:
                for other_srv in koleb_list:
                    if other_srv not in json_d:
                        continue
                    json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))
            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            xdddd = await ctx.send('Berhasil menambah {} episode baru'.format(jumlah_tambahan))
            await asyncio.sleep(2)
            await xdddd.delete()

            return emb_msg

        async def hapus_episode(emb_msg):
            print('[@] Memproses Hapus Episode')

            status_list = program_info['status']
            max_episode = list(status_list.keys())[-1]

            embed = discord.Embed(title="Menghapus Episode", description='Jumlah Episode Sekarang: {}'.format(max_episode), color=0xeba279)
            embed.add_field(name='Masukan range episode yang ingin dihapus.', value=hapusepisode_instruct, inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for('message', check=check_if_author)

                jumlah_tambahan = await_msg.content
                embed = discord.Embed(title="Menghapus Episode", color=0xeba279)
                embed.add_field(name='Apakah Yakin?', value="Range episode: **{}**".format(jumlah_tambahan), inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)

                reactmoji = ['✅', '❌']

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for('reaction_add', check=check_react)
                if user != ctx.message.author:
                    pass
                elif '✅' in str(res.emoji):
                    await await_msg.delete()
                    await emb_msg.clear_reactions()
                    break
                elif '❌' in str(res.emoji):
                    await await_msg.delete()
                    embed = discord.Embed(title="Menghapus Episode", description='Jumlah Episode Sekarang: {}'.format(max_episode), color=0xeba279)
                    embed.add_field(name='Masukan range episode yang ingin dihapus.', value=hapusepisode_instruct, inline=False)
                    embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                    await emb_msg.edit(embed=embed)
                await emb_msg.clear_reactions()


            total_episode = jumlah_tambahan.split('-')
            if len(total_episode) < 2:
                current = int(total_episode[0])
                total = int(total_episode[0])
            else:
                current = int(total_episode[0])
                total = int(total_episode[1])

            if koleb_list:
                for other_srv in koleb_list:
                    if other_srv not in json_d:
                        continue
                    for x in range(current, total+1): # range(int(c), int(c)+int(x))
                        del json_d[other_srv]['anime'][matches[0]]['status'][str(x)]
                    json_d[other_srv]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            for x in range(current, total+1): # range(int(c), int(c)+int(x))
                del json_d[server_message]['anime'][matches[0]]['status'][str(x)]
            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            xdddd = await ctx.send('Berhasil menghapus episode {} ke {}'.format(current, total))
            await asyncio.sleep(2)
            await xdddd.delete()

            return emb_msg

        async def hapus_utang_tanya(emb_msg):
            delete_ = False
            while True:
                embed=discord.Embed(title="Menghapus Utang", description="Anime: {}".format(matches[0]), color=0xcc1c20)
                embed.add_field(name='Peringatan!', value='Utang akan dihapus selama-lamanya dan tidak bisa dikembalikan!\nLanjutkan proses?', inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await emb_msg.edit(embed=embed)

                reactmoji = ['✅', '❌']

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for('reaction_add', check=check_react)
                if user != ctx.message.author:
                    pass
                elif '✅' in str(res.emoji):
                    await emb_msg.clear_reactions()
                    delete_ = True
                    break
                elif '❌' in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                await emb_msg.clear_reactions()
            return emb_msg, delete_

        first_run = True
        exit_command = False
        hapus_utang = False
        while True:
            guild_roles = ctx.message.guild.roles
            total_episodes = len(json_d[server_message]['anime'][matches[0]]['status'])
            role_id = json_d[server_message]['anime'][matches[0]]['role_id']
            embed=discord.Embed(title="Mengubah Data", description="Anime: {}".format(matches[0]), color=0xe7e363)
            embed.add_field(name="1⃣ Ubah Staff", value="Ubah staff yang mengerjakan anime ini.", inline=False)
            embed.add_field(name='2⃣ Ubah Role', value="Ubah role discord yang digunakan:\nRole sekarang: {}".format(get_role_name(role_id, guild_roles)), inline=False)
            embed.add_field(name='3⃣ Tambah Episode', value="Tambah jumlah episode\nTotal Episode sekarang: {}".format(total_episodes), inline=False)
            embed.add_field(name="4⃣ Hapus Episode", value="Hapus episode tertentu.", inline=False)
            embed.add_field(name="5⃣ Drop Garapan", value="Menghapus garapan ini dari daftar utang untuk selama-lamanya...", inline=False)
            embed.add_field(name="Lain-Lain", value="✅ Selesai!\n❌ Batalkan!", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            if first_run:
                emb_msg = await ctx.send(embed=embed)
                first_run = False
            else:
                await emb_msg.edit(embed=embed)

            reactmoji = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '✅', '❌']

            for react in reactmoji:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            res, user = await self.bot.wait_for('reaction_add', check=check_react)
            if user != ctx.message.author:
                pass
            elif reactmoji[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_staff(emb_msg)
            elif reactmoji[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_role(emb_msg)
            elif reactmoji[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await tambah_episode(emb_msg)
            elif reactmoji[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await hapus_episode(emb_msg)
            elif reactmoji[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg, hapus_utang = await hapus_utang_tanya(emb_msg)
                if hapus_utang:
                    await emb_msg.delete()
                    break
            elif reactmoji[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break
            elif reactmoji[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                exit_command = True
                break

        if exit_command:
            print('[!] Dibatalkan.')
            return await ctx.send('**Dibatalkan!**')
        if hapus_utang:
            print('[!] Menghapus dari daftar utang!')
            current = get_current_ep(program_info['status'])
            try:
                if program_info['status']['1']['status'] == 'not_released':
                    announce_it = False
                elif not current:
                    announce_it = False
                else:
                    announce_it = True
            except KeyError:
                announce_it = True

            del json_d[server_message]['anime'][matches[0]]
            for osrv in koleb_list:
                if "kolaborasi" in json_d[osrv]['anime'][matches[0]]:
                    if server_message in json_d[osrv]['anime'][matches[0]]['kolaborasi']:
                        klosrv = deepcopy(json_d[osrv]['anime'][matches[0]]['kolaborasi'])
                        klosrv.remove(server_message)

                        remove_all = False
                        if len(klosrv) == 1:
                            if klosrv[0] == osrv:
                                remove_all = True

                        if remove_all:
                            del json_d[osrv]['anime'][matches[0]]['kolaborasi']
                        else:
                            json_d[osrv]['anime'][matches[0]]['kolaborasi'] = klosrv

            with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                json.dump(json_d, f, indent=4)
            print('[@] Sending message to staff...')
            await ctx.send('Berhasil menghapus **{}** dari daftar utang'.format(matches[0]))

            print("[%] Updating main database data...")
            success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
            for osrv in koleb_list:
                if osrv == server_message:
                    continue
                if osrv not in json_d: # Skip if the server doesn't exist :pepega:
                    continue
                print("[%] Updating collaboration server: {}".format(osrv))
                res2, msg2 = await self.bot.ntdb.update_data_server(osrv, json_d[osrv])
                if not res2:
                    if osrv not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(osrv)
                    print('[%] Failed updating collaboration server: {}\n\tReason: {}'.format(osrv, msg2))

            if not success:
                print('[%] Failed to update main database data')
                print('\tReason: {}'.format(msg))
                if server_message not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(server_message)
                #await patch_error_handling(self.bot, ctx)

            if 'announce_channel' in server_data:
                announce_chan = server_data['announce_channel']
                target_chan = self.bot.get_channel(int(announce_chan))
                embed = discord.Embed(title="{}".format(matches[0]), color=0xb51e1e)
                embed.add_field(name='Dropped...', value="{} telah di drop dari fansub ini :(".format(matches[0]), inline=False)
                embed.set_footer(text="Pada: {}".format(get_current_time()))
                if announce_it:
                    print('[@] Sending message to user...')
                    if target_chan:
                        await target_chan.send(embed=embed)
            return

        print('[!] Menyimpan data baru untuk garapan: ' +  matches[0])
        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        print("[%] Updating main database data...")
        success, msg = await self.bot.ntdb.update_data_server(server_message, json_d[server_message])
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            if osrv not in json_d: # Skip if the server doesn't exist :pepega:
                continue
            print("[%] Updating collaboration server: {}".format(osrv))
            res2, msg2 = await self.bot.ntdb.update_data_server(osrv, json_d[osrv])
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                print('[%] Failed updating collaboration server: {}\n\tReason: {}'.format(osrv, msg2))

        if not success:
            print('[%] Failed to update, reason: {}'.format(msg))
            print('\tAdding to retry list')
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send('Berhasil menyimpan data baru untuk garapan **{}**'.format(matches[0]))


ShowTimesCommands = [Showtimes, ShowtimesAdmin, ShowtimesAlias, ShowtimesKolaborasi, ShowtimesConfigData]

def setup(bot):
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            print('\t[#] Loading {} Commands...'.format(str(ShowTCLoad)))
            bot.add_cog(ShowTCLoad)
            print('\t[@] Loaded.')
        except Exception as ex:
            print('\t[!] Failed: {}'.format(str(ex)))
