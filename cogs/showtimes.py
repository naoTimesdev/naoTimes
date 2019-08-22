# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import asyncio
import json
import re
import os
import time
from calendar import monthrange
from copy import deepcopy
from datetime import datetime, timedelta
from random import choice
from string import ascii_lowercase, digits

import aiohttp
import discord
import discord.ext.commands as commands
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

with open('config.json', 'r') as fp:
    bot_config = json.load(fp)


async def fetch_json() -> dict:
    """
    Open local database
    """
    print('@@ Opening json file')
    if not os.path.isfile('nao_showtimes.json'):
        print('@@ naoTimes are not initiated, skipping.')
        return {}
    with open('nao_showtimes.json', 'r') as fp:
        json_data = json.load(fp)
    
    return json_data


async def patch_json(jsdata) -> bool:
    """
    Send modified data back to github
    """
    hh = {
        "description": "N4O Showtimes bot",
        "files": {
            "nao_showtimes.json": {
                "filename": "nao_showtimes.json",
                "content": json.dumps(jsdata, indent=4)
            }
        }
    }

    print('@@ Patching gists')
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(bot_config['github_info']['username'], bot_config['github_info']['password'])) as sesi2:
        async with sesi2.patch('https://api.github.com/gists/{}'.format(bot_config['gist_id']), json=hh) as resp:
            r = await resp.json()
    try:
        m = r['message']
        print('Can\'t patch: {}'.format(m))
        return False
    except KeyError:
        print('@@ Done patching')
        return True


def is_minus(x) -> bool:
    return x < 0


def parse_anilist_start_date(startDate) -> int:
    airing_start = datetime.strptime(startDate, '%Y%m%d')
    epoch_start = datetime(1970, 1, 1, 0, 0, 0)
    return int((airing_start - epoch_start).total_seconds())


def get_episode_airing(nodes, episode) -> tuple:
    for i in nodes:
        if i['episode'] == int(episode):
            return i['airingAt'], i['episode'] # return episodic data
    if len(nodes) == 1:
        return nodes[0]['airingAt'], nodes[-1]['episode'] # get the only airing data
    if len(nodes) == 0:
        return None, '1'
    return nodes[-1]['airingAt'], nodes[-1]['episode'] # get latest airing data


def get_original_time(x, total) -> int:
    for _ in range(total):
        x -= 24 * 3600 * 7
    return x


def parse_ani_time(x) -> str:
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
        except session.ClientError:
            return "ERROR: Koneksi terputus"

    if jadwal_only:
        try:
            time_until = entry['nextAiringEpisode']['timeUntilAiring']
            next_episode = entry['nextAiringEpisode']['episode']

            taimu = parse_ani_time(time_until)
        except:
            taimu = None
            next_episode = None

        return taimu, next_episode

    poster = entry['coverImage']['large']
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


def get_current_ep(status_list) -> list:
    """
    Find episode `not_released` status in showtimes database
    If not exist return None
    """
    for ep in status_list:
        if status_list[ep]['status'] == 'not_released':
            return ep
    return None


def get_not_released_ep(status_list) -> list:
    """
    Find all episode `not_released` status in showtimes database
    If not exist return None/False
    """
    ep_list = []
    for ep in status_list:
        if status_list[ep]['status'] == 'not_released':
            ep_list.append(ep)
    return ep_list


def get_close_matches(target, lists) -> list:
    """
    Find close matches from input target
    Sort everything if there's more than 2 results
    """
    target_compiler = re.compile('({})'.format(target), re.IGNORECASE)
    return sorted(list(filter(target_compiler.search, lists)))


def check_role(needed_role, user_roles) -> bool:
    """
    Check if there's needed role for the anime
    """
    for role in user_roles:
        if int(needed_role) == role.id:
            return True
    return False


def get_all_month_before(dt) -> int:
    current = int(dt.month)
    year = dt.year
    current_day_in_month = int(monthrange(year, dt.month)[1])
    while current > 1:
        current_day_in_month += int(monthrange(year, current)[1])
        current -= 1
    return current_day_in_month


def total_day_in_year(dt) -> int:
    year = dt.year
    first_month = int(monthrange(year, 1)[1])
    for x in range(2, 13):
        first_month += int(monthrange(year, x)[1])
    return first_month


def last_update_month_failsafe(deltatime, dayinmonth) -> int:
    x = int(round(deltatime / (86400 * dayinmonth)))
    if x == 0:
        return 1
    return x


def get_last_updated(oldtime) -> str:
    """
    Get last updated airing anime that return to a nice format
    """
    current_time = int(round(time.time()))
    oldtime = int(oldtime)
    deltatime = current_time - oldtime
    current_datetime = datetime.now()
    total_day = total_day_in_year(current_datetime)
    day_in_month = get_all_month_before(current_datetime)
    if deltatime < 60:
        text = 'Beberapa detik yang lalu'
    elif deltatime < 180:
        text = 'Beberapa menit yang lalu'
    elif deltatime < 3600:
        text = '{} menit yang lalu'.format(int(round(deltatime / 60)))
    elif deltatime < 86400:
        text = '{} jam yang lalu'.format(int(round(deltatime / 3600)))
    elif deltatime < 32 * 86400:
        text = '{} hari yang lalu'.format(int(round(deltatime / 86400)))
    elif deltatime < day_in_month * 86400 and (total_day - day_in_month)+1 <= total_day:
        text = '{} bulan yang lalu'.format(last_update_month_failsafe(deltatime, day_in_month))
    else:
        text = '{} tahun yang lalu'.format(int(round(deltatime / (total_day * 86400))))

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


def any_progress(status) -> bool:
    for _, v in status.items():
        if v == 'y':
            return False
    return True


def get_role_name(role_id, roles) -> str:
    for r in roles:
        if str(r.id) == str(role_id):
            return r.name
    return 'Unknown'


class Showtimes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def __local_check(self, ctx):
        if not ctx.guild:
            raise commands.NoPrivateMessage('Tidak bisa menjalankan perintah ini di private message.')
        return True


    async def __error(self, ctx, error):
        if not isinstance(error, commands.UserInputError):
            raise error

        try:
            await ctx.send(error)
        except discord.Forbidden:
            pass


    @commands.command(aliases=['blame', 'mana'])
    async def tagih(self, ctx, *, judul=None):
        """
        Menagih utang fansub tukang diley maupun tidak untuk memberikan mereka tekanan
        ---
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.server.id)
        print('Requested !tagih at: ' + server_message)
        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]
        print('Found server list')

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
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await ctx.send('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await ctx.send('**Mungkin**: {}'.format(', '.join(matches)))

        program_info = server_data['anime'][matches[0]]
        last_update = int(program_info['last_update'])
        status_list = program_info['status']

        current = get_current_ep(status_list)
        if not current:
            return await ctx.send('**Sudah beres digarap!**')

        time_data, poster_image, _ = await fetch_anilist(program_info['anilist_id'], current)

        if any_progress(status_list[current]['staff_status']):
            last_status = time_data
            last_text = 'Tayang'
        else:
            last_status = get_last_updated(last_update)
            last_text = 'Update Terakhir'

        current_ep_status = parse_status(status_list[current]['staff_status'])
        print('Sending message to user request...')
        print(current_ep_status)
        print(last_status)

        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0x1eb5a6)
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name='Status', value=current_ep_status, inline=False)
        embed.add_field(name=last_text, value=last_status, inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)


    @commands.command(aliases=['release'])
    async def rilis(self, ctx, *, data):
        data = data.split()

        server_message = str(ctx.message.server.id)
        print('Requested !rilis at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

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

        if data[0] not in ['batch', 'semua']:
            """
            Merilis rilisan, hanya bisa dipakai sama role tertentu
            ---
            judul: Judul anime yang terdaftar
            """
            print('Inherited normal rilis command')

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
            print('Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await ctx.send('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(matches)))

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

            current = get_current_ep(status_list)
            if not current:
                return await ctx.send('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await ctx.send('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            if koleb_list:
                for other_srv in koleb_list:
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

            print('Inherited batch rilis command')

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await ctx.send('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(matches)))

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

            current = get_current_ep(status_list)
            if not current:
                return await ctx.send('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await ctx.send('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            if koleb_list:
                for other_srv in koleb_list:
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

            print('Inherited all rilis command')

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await ctx.send('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                return await ctx.send('**Mungkin**: {}'.format(', '.join(matches)))

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

            all_status = get_not_released_ep(status_list)
            if not all_status:
                return await ctx.send('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await ctx.send('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            if koleb_list:
                for other_srv in koleb_list:
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
        print('@@ Sending message...')
        await ctx.send(text_data)

        success = await patch_json(json_d)

        if success:
            if koleb_list:
                for other_srv in koleb_list:
                    if 'announce_channel' in json_d[other_srv]:
                        print('@@ Sending progress info to everyone at {}'.format(other_srv))
                        announce_chan = json_d[other_srv]['announce_channel']
                        # TODO: check this this
                        target_chan = ctx.get_channel(int(announce_chan))
                        # target_chan = discord.Object(announce_chan)
                        embed = discord.Embed(title="{}".format(matches[0]), color=0x1eb5a6)
                        embed.add_field(name='Rilis!', value=embed_text_data, inline=False)
                        embed.set_footer(text="Pada: {}".format(get_current_time()))
                        await target_chan.send(embed=embed)
            if 'announce_channel' in server_data:
                announce_chan = server_data['announce_channel']
                # TODO: check this this
                target_chan = ctx.get_channel(int(announce_chan))
                # target_chan = discord.Object(announce_chan)
                embed = discord.Embed(title="{}".format(matches[0]), color=0x1eb5a6)
                embed.add_field(name='Rilis!', value=embed_text_data, inline=False)
                embed.set_footer(text="Pada: {}".format(get_current_time()))
                await target_chan.send(embed=embed)
            return

        server_in = self.bot.get_guild(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await mod_mem_data.send('Terjadi kesalahan patch pada server **{}**'.format(server_message))


def setup(bot):
    bot.add_cog(Showtimes(bot))
