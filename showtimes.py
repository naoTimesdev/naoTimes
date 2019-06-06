# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import asyncio
import json
import re
import os
import time
from calendar import monthrange
from datetime import datetime, timedelta

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
        if int(needed_role) == int(role.id):
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


def is_minus(x) -> bool:
    return x < 0


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


class Showtimes:
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


    @commands.command(pass_context=True, aliases=['blame', 'mana'])
    async def tagih(self, ctx, *, judul=None):
        """
        Menagih utang fansub tukang diley maupun tidak untuk memberikan mereka tekanan
        ---
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.server.id)
        print('Requested !tagih at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
            print('Found server list')
        except:
            return

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(sorted(srv_anilist))))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        program_info = server_data['anime'][matches[0]]
        last_update = int(program_info['last_update'])
        status_list = program_info['status']

        current = get_current_ep(status_list)
        if not current:
            return await self.bot.say('**Sudah beres digarap!**')

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
        await self.bot.say(embed=embed)


    @commands.command(pass_context=True, aliases=['release'])
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
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if len(srv_anilist) < 1:
            return await self.bot.say('**Tidak ada anime yang terdaftar di database**')

        if not data or data == []:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        if data[0] not in ['batch', 'semua']:
            """
            Merilis rilisan, hanya bisa dipakai sama role tertentu
            ---
            judul: Judul anime yang terdaftar
            """
            print('Inherited normal rilis command')

            judul = ' '.join(data)

            if judul == ' ' or judul == '' or judul == '   ' or not judul:
                return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['anime']['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

            program_info = server_data['anime'][matches[0]]
            status_list = program_info['status']

            current = get_current_ep(status_list)
            if not current:
                return await self.bot.say('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await self.bot.say('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            json_d[server_message]['anime'][matches[0]]['status'][current]['status'] = 'released'
            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                json.dump(json_d, f, indent=4)
            print('@@ Sending message...')
            await self.bot.say("**{} - #{}** telah dirilis".format(matches[0], current))

            success = await patch_json(json_d)

            if success:
                try:
                    announce_chan = server_data['announce_channel']
                    target_chan = discord.Object(announce_chan)
                    embed = discord.Embed(title="{}".format(matches[0]), color=0x1eb5a6)
                    embed.add_field(name='Rilis!', value="{} #{} telah dirilis!".format(matches[0], current), inline=False)
                    embed.set_footer(text="Pada: {}".format(get_current_time()))
                    return await self.bot.send_message(target_chan, embed=embed)
                except:
                    return
            server_in = self.bot.get_server(bot_config['main_server'])
            mod_mem_data = server_in.get_member(bot_config['owner_id'])
            await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))
        elif data[0] == 'batch':
            if not data[1].isdigit():
                await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))
                return await self.bot.say("Lalu tulis jumlah terlebih dahulu baru judul")
            if len(data) < 3:
                return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

            jumlah = data[1]
            judul = ' '.join(data[2:])

            print('Inherited batch rilis command')

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['anime']['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

            program_info = server_data['anime'][matches[0]]
            status_list = program_info['status']

            current = get_current_ep(status_list)
            if not current:
                return await self.bot.say('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await self.bot.say('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            for x in range(int(current), int(current)+int(jumlah)): # range(int(c), int(c)+int(x))
                json_d[server_message]['anime'][matches[0]]['status'][str(x)]['status'] = 'released'

            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                json.dump(json_d, f, indent=4)
            print('@@ Sending message...')
            await self.bot.say("**{} - #{} sampai #{}** telah dirilis".format(matches[0], current, int(current)+int(jumlah)-1))

            success = await patch_json(json_d)

            if success:
                try:
                    announce_chan = server_data['announce_channel']
                    target_chan = discord.Object(announce_chan)
                    embed = discord.Embed(title="{}".format(matches[0]), color=0x1eb5a6)
                    embed.add_field(name='Rilis!', value="{} #{} sampai #{} telah dirilis!".format(matches[0], current, int(current)+int(jumlah)-1), inline=False)
                    embed.set_footer(text="Pada: {}".format(get_current_time()))
                    return await self.bot.send_message(target_chan, embed=embed)
                except:
                    return
            server_in = self.bot.get_server(bot_config['main_server'])
            mod_mem_data = server_in.get_member(bot_config['owner_id'])
            await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))
        elif data[0] == 'semua':
            judul = ' '.join(data[1:])

            if judul == ' ' or judul == '' or judul == '   ' or not judul:
                return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

            print('Inherited all rilis command')

            matches = get_close_matches(judul, srv_anilist)
            if srv_anilist_alias:
                temp_anilias = get_close_matches(judul, srv_anilist_alias)
                for i in temp_anilias:
                    res = find_alias_anime(i, server_data['anime']['alias'])
                    if res not in matches: # To not duplicate result
                        matches.append(res)
            print('Matches: {}'.format(", ".join(matches)))

            if not matches:
                return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
            elif len(matches) > 1:
                return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

            program_info = server_data['anime'][matches[0]]
            status_list = program_info['status']

            all_status = get_not_released_ep(status_list)
            if not all_status:
                return await self.bot.say('**Sudah beres digarap!**')

            if str(ctx.message.author.id) != program_info['staff_assignment']['QC']:
                if str(ctx.message.author.id) not in srv_owner:
                    return await self.bot.say('**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**')

            for x in all_status:
                json_d[server_message]['anime'][matches[0]]['status'][x]['status'] = 'released'

            json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

            with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                json.dump(json_d, f, indent=4)
            print('@@ Sending message...')
            await self.bot.say("**{} - #{} sampai #{}** telah dirilis".format(matches[0], all_status[0], all_status[-1]))

            success = await patch_json(json_d)

            if success:
                try:
                    announce_chan = server_data['announce_channel']
                    target_chan = discord.Object(announce_chan)
                    embed = discord.Embed(title="{}".format(matches[0]), color=0x1eb5a6)
                    embed.add_field(name='Rilis!', value="{} #{} sampai #{} telah dirilis!".format(matches[0], all_status[0], all_status[-1]), inline=False)
                    embed.set_footer(text="Pada: {}".format(get_current_time()))
                    return await self.bot.send_message(target_chan, embed=embed)
                except:
                    return
            server_in = self.bot.get_server(bot_config['main_server'])
            mod_mem_data = server_in.get_member(bot_config['owner_id'])
            await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))


    @commands.command(pass_context=True, aliases=['done'])
    async def beres(self, ctx, posisi, *, judul):
        """
        Menyilang salah satu tugas pendelay
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.server.id)
        print('Requested !beres at: ' + server_message)
        posisi = posisi.lower()
        list_posisi = ['tl', 'tlc', 'enc', 'ed', 'tm', 'ts', 'qc']
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']

        if not check_role(program_info['role_id'], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = get_current_ep(status_list)
        if not current:
            return await self.bot.say('**Sudah beres digarap!**')

        _, poster_image, _ = await fetch_anilist(program_info['anilist_id'], current)

        if posisi not in list_posisi:
            return await self.bot.say('Tidak ada posisi itu\nYang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`')

        if str(ctx.message.author.id) != program_info['staff_assignment'][posisi.upper()]:
            if str(ctx.message.author.id) not in srv_owner:
                return await self.bot.say('**Bukan posisi situ untuk mengubahnya!**')

        json_d[server_message]['anime'][matches[0]]['status'][current]['staff_status'][posisi.upper()] = 'y'
        json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

        current_ep_status = status_list[current]['staff_status']

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('@@ Sending progress info to staff')
        await self.bot.say('Berhasil mengubah status garapan {} - #{}'.format(matches[0], current))

        success = await patch_json(json_d)

        if success:
            embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0x1eb5a6)
            embed.add_field(name='Status', value=parse_status(current_ep_status), inline=False)
            try:
                announce_chan = server_data['announce_channel']
                target_chan = discord.Object(announce_chan)
                embed.set_footer(text="Pada: {}".format(get_current_time()))
                print('@@ Sending progress info to everyone')
                await self.bot.send_message(target_chan, embed=embed)
                embed.add_field(name='Update Terakhir', value='Baru saja', inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                embed.set_thumbnail(url=poster_image)
                return await self.bot.say(embed=embed)
            except:
                print('@@ Failed to send message')
                embed.add_field(name='Update Terakhir', value='Baru saja', inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                embed.set_thumbnail(url=poster_image)
                return await self.bot.say(embed=embed)
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch `beres` pada server **{}**'.format(server_message))

    @commands.command(pass_context=True, aliases=['undone', 'cancel'])
    async def gakjadi(self, ctx, posisi, *, judul):
        """
        Menghilangkan tanda karena ada kesalahan
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.server.id)
        print('Requested !gakjadi at: ' + server_message)
        posisi = posisi.lower()
        list_posisi = ['tl', 'tlc', 'enc', 'ed', 'tm', 'ts', 'qc']
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']

        if not check_role(program_info['role_id'], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = get_current_ep(status_list)
        if not current:
            return await self.bot.say('**Sudah beres digarap!**')

        _, poster_image, title = await fetch_anilist(program_info['anilist_id'], current)

        if posisi not in list_posisi:
            return await self.bot.say('Tidak ada posisi itu\nYang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`')

        if str(ctx.message.author.id) != program_info['staff_assignment'][posisi.upper()]:
            if str(ctx.message.author.id) not in srv_owner:
                return await self.bot.say('**Bukan posisi situ untuk mengubahnya!**')

        json_d[server_message]['anime'][matches[0]]['status'][current]['staff_status'][posisi.upper()] = 'x'
        json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

        current_ep_status = status_list[current]['staff_status']

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('@@ Sending progress info to staff')
        await self.bot.say('Berhasil mengubah status garapan {} - #{}'.format(matches[0], current))

        success = await patch_json(json_d)

        if success:
            embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0xb51e1e)
            embed.add_field(name='Status', value=parse_status(current_ep_status), inline=False)
            try:
                announce_chan = server_data['announce_channel']
                target_chan = discord.Object(announce_chan)
                embed.set_footer(text="Pada: {}".format(get_current_time()))
                print('@@ Sending progress info to everyone')
                await self.bot.send_message(target_chan, embed=embed)
                embed.add_field(name='Update Terakhir', value='Baru saja', inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                embed.set_thumbnail(url=poster_image)
                return await self.bot.say(embed=embed)
            except:
                print('@@ Failed to send message')
                embed.add_field(name='Update Terakhir', value='Baru saja', inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                embed.set_thumbnail(url=poster_image)
                return await self.bot.say(embed=embed)
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch `gakjadi` pada server **{}**'.format(server_message))

    @commands.command(pass_context=True)
    async def ubahstaff(self, ctx, role_id, role_position, *, judul):
        server_message = str(ctx.message.server.id)
        print('Requested !ubahstaff at: ' + server_message)
        role_position = role_position.lower()
        list_posisi = ['tl', 'tlc', 'enc', 'ed', 'tm', 'ts', 'qc']
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await self.bot.say('Hanya admin yang bisa mengubah staff')

        if role_position not in list_posisi:
            return await self.bot.say('Tidak ada posisi itu\nYang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`')

        if len(srv_anilist) < 1:
            return await self.bot.say('**Tidak ada anime yang terdaftar di database**')

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        json_d[server_message]['anime'][matches[0]]['staff_assignment'][role_position.upper()] = role_id
        print('Changed {} id to: {}'.format(role_position.upper(), role_id))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)

        if success:
            return await self.bot.say("Berhasil mengubah staff **{}** untuk **{}**".format(role_position.upper(), matches[0]))
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))

    @commands.command(pass_context=True)
    async def ubahrole(self, ctx, role_id, *, judul):
        server_message = str(ctx.message.server.id)
        print('Requested !ubahrole at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await self.bot.say('Hanya admin yang bisa mengubah role')

        if len(srv_anilist) < 1:
            return await self.bot.say('**Tidak ada anime yang terdaftar di database**')

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        json_d[server_message]['anime'][matches[0]]['role_id'] = role_id
        print('Changed {} role id to: {}'.format(matches[0], role_id))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)

        if success:
            return await self.bot.say("Berhasil mengubah ID role **{}**".format(matches[0]))
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))

    @commands.command(pass_context=True)
    async def tambahepisode(self, ctx, jumlah, *, judul):
        server_message = str(ctx.message.server.id)
        print('Requested !tambahepisode at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await self.bot.say('Hanya admin yang bisa menambah episode')

        if len(srv_anilist) < 1:
            return await self.bot.say('**Tidak ada anime yang terdaftar di database**')

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']

        max_episode = list(status_list.keys())[-1]

        _, poster_image, title, time_data, correct_episode_num = await fetch_anilist(program_info['anilist_id'], 1, max_episode, True)

        for x in range(int(max_episode) + 1, int(max_episode) + int(jumlah) + 1): # range(int(c), int(c)+int(x))
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
            json_d[server_message]['anime'][matches[0]]['status'][str(x)] = st_data

        json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)

        if success:
            return await self.bot.say('Berhasil menambah {} episode untuk anime **{}**'.format(jumlah, matches[0]))
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))

    @commands.command(pass_context=True)
    async def hapusepisode(self, ctx, jumlah, *, judul):
        server_message = str(ctx.message.server.id)
        print('Requested !hapusepisode at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        # Parse 'jumlah'
        total_episode = jumlah.split('-')
        if len(total_episode) < 2:
            current = int(total_episode[0])
            total = int(total_episode[0])
        else:
            current = int(total_episode[0])
            total = int(total_episode[1])

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await self.bot.say('Hanya admin yang bisa menghilangkan episode')

        if len(srv_anilist) < 1:
            return await self.bot.say('**Tidak ada anime yang terdaftar di database**')

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        program_info = server_data['anime'][matches[0]]

        for x in range(current, total+1): # range(int(c), int(c)+int(x))
            del json_d[server_message]['anime'][matches[0]]['status'][str(x)]

        json_d[server_message]['anime'][matches[0]]['last_update'] = str(int(round(time.time())))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)

        if success:
            if len(total_episode) < 2:
                str_text = '**{} - #{}** telah dihapus'.format(matches[0], current)
            else:
                str_text = "**{} - #{} sampai #{}** telah dihapus".format(matches[0], current, total)
            return await self.bot.say(str_text)
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))

    @commands.command(pass_context=True, aliases=['buangutang', 'buang', 'lupakan', 'remove', 'drop'])
    async def lupakanutang(self, ctx, *, judul):
        """
        Lupakan utang lama buat utang baru :D
        """
        server_message = str(ctx.message.server.id)
        print('Requested !lupakanutang at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await self.bot.say('Hanya admin yang bisa membuang utang')

        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        current = get_current_ep(json_d[server_message]['anime'][matches[0]]['status'])
        try:
            if json_d[server_message]['anime'][matches[0]]['status']['1']['status'] == 'not_released':
                announce_it = False
            elif not current:
                announce_it = False
            else:
                announce_it = True
        except KeyError:
            announce_it = True

        del json_d[server_message]['anime'][matches[0]]

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('@@ Sending message to staff...')
        await self.bot.say('Berhasil menghapus **{}** dari daftar utang'.format(matches[0]))

        success = await patch_json(json_d)
        if success:
            try:
                announce_chan = server_data['announce_channel']
                target_chan = discord.Object(announce_chan)
                embed = discord.Embed(title="{}".format(matches[0]), color=0xb51e1e)
                embed.add_field(name='Dropped...', value="{} telah di drop dari fansub ini :(".format(matches[0]), inline=False)
                embed.set_footer(text="Pada: {}".format(get_current_time()))
                if announce_it:
                    print('@@ Sending message to user...')
                    await self.bot.send_message(target_chan, embed=embed)
                return
            except:
                return
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch `buangutang` pada server **{}**'.format(server_message))

    @commands.command(pass_context=True, aliases=['add', 'tambah'])
    async def tambahutang(self, ctx):
        """
        Membuat utang baru, ambil semua user id dan role id yang diperlukan.
        ----
        Menggunakan embed agar terlihat lebih enak dibanding sebelumnya
        Merupakan versi 2
        """
        server_message = str(ctx.message.server.id)
        print('Requested !tambahutang at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await self.bot.say('Hanya admin yang bisa menambah utang')

        print('Membuat data')
        embed = discord.Embed(title="Menambah Utang", color=0x56acf3)
        embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await self.bot.say(embed=embed)
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

        async def process_episode(table, emb_msg, author):
            print('@@ Memproses jumlah episode')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Jumlah Episode', value="Ketik Jumlah Episode perkiraan", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)
            
            while True:
                await_msg = await self.bot.wait_for_message(author=author)

                if await_msg.content.isdigit():
                    await self.bot.delete_message(await_msg)
                    break

                await self.bot.delete_message(await_msg)

            _, poster, title, time_data, correct_episode_num = await fetch_anilist(table['anilist_id'], 1, int(await_msg.content), True)
            table['episodes'] = correct_episode_num
            table['time_data'] = time_data

            return table, emb_msg

        async def process_anilist(table, emb_msg, author):
            print('@@ Memproses Anilist data')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.add_field(name='Anilist ID', value="Ketik ID Anilist untuk anime yang diinginkan\n\nBisa gunakan `!anime <judul>` dan melihat bagian bawah untuk IDnya\n\nKetik *cancel* untuk membatalkan proses", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, "", embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)

                if await_msg.content == ("cancel"):
                    return False, False

                if await_msg.content.isdigit():
                    await self.bot.delete_message(await_msg)
                    break

                await self.bot.delete_message(await_msg)

            _, poster_image, title, time_data, correct_episode_num = await fetch_anilist(await_msg.content, 1, 1, True)

            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=poster_image)
            embed.add_field(name='Apakah benar?', value="Judul: **{}**".format(title), inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            to_react = ['✅', '❌']
            for reaction in to_react:
                    await self.bot.add_reaction(emb_msg, reaction)
            def checkReaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(('✅', '❌'))

            res = await self.bot.wait_for_reaction(message=emb_msg, user=author, check=checkReaction)

            if '✅' in str(res.reaction.emoji):
                table['ani_title'] = title
                table['poster_img'] = poster_image
                table['anilist_id'] = str(await_msg.content)
                await self.bot.clear_reactions(emb_msg)
            elif '❌' in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                return False, False

            if correct_episode_num == 1:
                print('@@ Correct episode are not grabbed, asking user...')
                table, emb_msg = await process_episode(table, emb_msg, author)
            else:
                print('@@ Total episodes exist, using that to continue...')
                table['episodes'] = correct_episode_num
                table['time_data'] = time_data

            return table, emb_msg

        async def process_role(table, emb_msg, author):
            print('@@ Memproses Role')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Role ID', value="Ketik ID Role atau mention rolenya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)

                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        table['role_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['role_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break

                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_tlcer(table, emb_msg, author):
            print('@@ Memproses TLCer')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='TLCer ID', value="Ketik ID TLC atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['tlcer_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['tlcer_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_tlor(table, emb_msg, author):
            print('@@ Memproses TLor')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Translator ID', value="Ketik ID Translator atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['tlor_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['tlor_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_encoder(table, emb_msg, author):
            print('@@ Memproses Encoder')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Encoder ID', value="Ketik ID Encoder atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['encoder_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['encoder_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_editor(table, emb_msg, author):
            print('@@ Memproses Editor')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Editor ID', value="Ketik ID Editor atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['editor_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['editor_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_timer(table, emb_msg, author):
            print('@@ Memproses Timer')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Timer ID', value="Ketik ID Timer atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['timer_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['timer_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_tser(table, emb_msg, author):
            print('@@ Memproses Typesetter')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Typesetter ID', value="Ketik ID Typesetter atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['tser_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['tser_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_qcer(table, emb_msg, author):
            print('@@ Memproses QCer')
            embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
            embed.set_thumbnail(url=table['poster_img'])
            embed.add_field(name='Quality Checker ID', value="Ketik ID Quality Checker atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['qcer_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['qcer_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        def check_setting(gear):
            if not gear:
                return '❌'
            return '✅'

        async def process_pengaturan(table, emb_msg, author):
            # Inner settings
            async def gear_1(table, emb_msg, gear_data):
                print('@@ Mengatur time_data agar sama')
                if not gear_data:
                    table['old_time_data'] = table['time_data'] # Make sure old time data are not deleted
                    time_table = table['time_data']
                    new_time_table = []
                    for _ in time_table:
                        new_time_table.append(time_table[0])
                    
                    table['time_data'] = new_time_table
                    table['settings']['time_data_are_the_same'] = True
                    print(table['time_data'])
                    return table, emb_msg
                
                new_time_table = []
                for i, _ in enumerate(table['time_data']):
                    new_time_table.append(table['old_time_data'][i])

                table['old_time_data'] = [] # Remove old time data because it resetted
                table['settings']['time_data_are_the_same'] = False
                print(table['time_data'])
                return table, emb_msg

            print('@@ Showing toogleable settings.')
            while True:
                embed = discord.Embed(title="Menambah Utang", color=0x96df6a)
                embed.set_thumbnail(url=table['poster_img'])
                embed.add_field(name='1⃣ Samakan waktu tayang', value="Status: **{}**\n\nBerguna untuk anime Netflix yang sekali rilis banyak".format(check_setting(table['settings']['time_data_are_the_same'])), inline=False)
                embed.add_field(name='Lain-Lain', value="⏪ Kembali", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

                to_react = ['1⃣', '⏪'] # ["2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣', '✅', '❌']
                for reaction in to_react:
                        await self.bot.add_reaction(emb_msg, reaction)
                def checkReaction(reaction, user):
                    e = str(reaction.emoji)
                    return e.startswith(tuple(to_react))

                res = await self.bot.wait_for_reaction(message=emb_msg, user=msg_author, check=checkReaction)

                if to_react[0] in str(res.reaction.emoji):
                    await self.bot.clear_reactions(emb_msg)
                    table, emb_msg = await gear_1(table, emb_msg, table['settings']['time_data_are_the_same'])
                elif to_react[-1] in str(res.reaction.emoji):
                    await self.bot.clear_reactions(emb_msg)
                    return table, emb_msg

        json_tables, emb_msg = await process_anilist(json_tables, emb_msg, msg_author)

        if not json_tables:
            print('@@ Proses `tambahutang` dibatalkan')
            return await self.bot.say('**Dibatalkan.**')

        json_tables, emb_msg = await process_role(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_tlor(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_tlcer(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_encoder(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_editor(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_timer(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_tser(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_qcer(json_tables, emb_msg, msg_author)

        print(json_tables)

        async def fetch_username_from_id(_id):
            try:
                user = await self.bot.get_user_info(_id)
                return '{}#{}'.format(user.name, user.discriminator)
            except discord.errors.NotFound:
                return 'Unknown'

        print('@@ Checkpoint before sending')
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
            embed.add_field(name='3⃣ Role', value="{}".format(get_role_name(json_tables['role_id'], ctx.message.server.roles)), inline=False)
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
                await self.bot.delete_message(emb_msg)
                emb_msg = await self.bot.say(embed=embed)
                first_time = False
            else:
                emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            to_react = ['1⃣', "2⃣", '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '0⃣', '🔐', '✅', '❌']
            for reaction in to_react:
                    await self.bot.add_reaction(emb_msg, reaction)
            def checkReaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(tuple(to_react))

            res = await self.bot.wait_for_reaction(message=emb_msg, user=msg_author, check=checkReaction)

            if to_react[0] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_anilist(json_tables, emb_msg, msg_author)
            elif to_react[1] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_episode(json_tables, emb_msg, msg_author)
            elif to_react[2] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_role(json_tables, emb_msg, msg_author)
            elif to_react[3] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_tlor(json_tables, emb_msg, msg_author)
            elif to_react[4] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_tlcer(json_tables, emb_msg, msg_author)
            elif to_react[5] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_encoder(json_tables, emb_msg, msg_author)
            elif to_react[6] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_editor(json_tables, emb_msg, msg_author)
            elif to_react[7] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_timer(json_tables, emb_msg, msg_author)
            if to_react[8] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_tser(json_tables, emb_msg, msg_author)
            elif to_react[9] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_qcer(json_tables, emb_msg, msg_author)
            elif '🔐' in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_pengaturan(json_tables, emb_msg, msg_author)
            elif '✅' in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                break
            elif '❌' in str(res.reaction.emoji):
                print('@@ Cancelled')
                cancel_toggled = True
                await self.bot.clear_reactions(emb_msg)
                break

        if cancel_toggled:
            return await self.bot.say('**Dibatalkan!**')

        # Everything are done and now processing data
        print(json_tables)
        embed=discord.Embed(title="Menambah Utang", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Membuat data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

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
        emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

        print("@@ Sending data")

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('@@ Sended.')
        embed=discord.Embed(title="Menambah Utang", color=0x96df6a)
        embed.add_field(name="Sukses!", value='**{}** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi'.format(json_tables['ani_title']), inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await self.bot.say(embed=embed)

        success = await patch_json(json_d)
        await self.bot.delete_message(emb_msg)

        if success:
            print('@@ Sending message...')
            return await self.bot.say("Berhasil menambahkan **{}** ke dalam database utama naoTimes".format(json_tables['ani_title']))
        await self.bot.say('Gagal menambahkan ke database utama, owner telah diberikan pesan untuk membenarkan masalahnya')
        server_in = self.bot.get_server(bot_config['main_server'])
        mod_mem_data = server_in.get_member(bot_config['owner_id'])
        await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch `tambahutang` pada server **{}**'.format(server_message))


    @commands.command(pass_context=True, aliases=['airing'])
    async def jadwal(self, ctx):
        """
        Melihat jadwal anime musiman yang di ambil.
        """
        server_message = str(ctx.message.server.id)
        print('Requested !jadwal at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
            print('Found server list')
        except:
            return

        appendtext = ''
        for ani in server_data['anime']:
            if ani == 'alias':
                continue
            time_data, episode = await fetch_anilist(server_data['anime'][ani]['anilist_id'], 1, jadwal_only=True)
            if not isinstance(time_data, str):
                continue
            appendtext += '**{}** - #{}\n'.format(ani, episode)
            appendtext += time_data + '\n\n'

        if appendtext != '':
            print('Sending message...')
            await self.bot.say(appendtext.strip())
        else:
            await self.bot.say('**Tidak ada utang pada musim ini yang terdaftar**')

    @commands.command(pass_context=True, aliases=['tukangdelay', 'pendelay'])
    async def staff(self, ctx, *, judul):
        """
        Menagih utang fansub tukang diley maupun tidak untuk memberikan mereka tekanan
        ---
        judul: Judul anime yang terdaftar
        """
        server_message = str(ctx.message.server.id)
        print('Requested !staff at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
            print('Found server list')
        except:
            return

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(srv_anilist)))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        staff_assignment = server_data['anime'][matches[0]]['staff_assignment']
        print('Got staff_asignment')

        rtext = 'Staff yang mengerjakaan **{}**\n**Admin**: '.format(matches[0])
        rtext += ''

        for adm in srv_owner:
            user = await self.bot.get_user_info(adm)
            rtext += '{}#{}'.format(user.name, user.discriminator)
            if len(adm) > 1:
                if srv_owner[-1] != adm:
                    rtext += ', '

        rtext += '\n**Role**: {}'.format(get_role_name(server_data['anime'][matches[0]]['role_id'], ctx.message.server.roles))

        rtext += '\n\n'

        for k, v in staff_assignment.items():
            try:
                user = await self.bot.get_user_info(v)
                rtext += '**{}**: {}#{}\n'.format(k, user.name, user.discriminator)
            except discord.errors.NotFound:
                rtext += '**{}**: Unknown\n'.format(k)

        rtext += '\n**Jika ada yang Unknown, admin dapat menggantikannya**'
        print(rtext)

        print('@@ Sending message...')
        await self.bot.say(rtext)

    @commands.command(pass_context=True, aliases=['mark'])
    async def tandakan(self, ctx, posisi, episode_n, *, judul):
        """
        Mark something as done or undone for other episode without announcing it
        """
        server_message = str(ctx.message.server.id)
        print('Requested !tandakan at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        srv_owner = server_data['serverowner']
        srv_anilist = []
        srv_anilist_alias = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)
        for k, _ in server_data['anime']['alias'].items():
            srv_anilist_alias.append(k)

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(sorted(srv_anilist))))

        matches = get_close_matches(judul, srv_anilist)
        if srv_anilist_alias:
            temp_anilias = get_close_matches(judul, srv_anilist_alias)
            for i in temp_anilias:
                res = find_alias_anime(i, server_data['anime']['alias'])
                if res not in matches: # To not duplicate result
                    matches.append(res)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        program_info = server_data['anime'][matches[0]]
        status_list = program_info['status']

        current = get_current_ep(status_list)
        if not current:
            return await self.bot.say('**Sudah beres digarap!**')

        posisi = posisi.upper()

        # Toggle status section
        if posisi.lower() not in ['tl', 'tlc', 'enc', 'ed', 'ts', 'tm', 'qc']:
            return await self.bot.say('Tidak ada posisi tersebut!')

        if str(ctx.message.author.id) != program_info['staff_assignment'][posisi.upper()]:
            if str(ctx.message.author.id) not in srv_owner:
                return await self.bot.say('**Bukan posisi situ untuk mengubahnya!**')

        pos_status = status_list[str(episode_n)]['staff_status']

        if pos_status[posisi] == 'x':
            json_d[server_message]["anime"][matches[0]]['status'][str(episode_n)]['staff_status'][posisi] = 'y'
            txt_msg = 'Berhasil mengubah status **{st}** episode **#{ep}** ke **beres**'
        elif pos_status[posisi] == 'y':
            json_d[server_message]["anime"][matches[0]]['status'][str(episode_n)]['staff_status'][posisi] = 'x'
            txt_msg = 'Berhasil mengubah status **{st}** episode **#{ep}** ke **belum beres**'

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)
        print('@@ Berhasil menandakan ke database local')
        await self.bot.say(txt_msg.format(st=posisi, ep=episode_n))

        success = await patch_json(json_d)
        if not success:
            server_in = self.bot.get_server(bot_config['main_server'])
            mod_mem_data = server_in.get_member(bot_config['owner_id'])
            await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch pada server **{}**'.format(server_message))


    @commands.group(pass_context=True)
    async def alias(self, ctx):
        """
        Initiate alias creation for certain anime
        """
        if not ctx.invoked_subcommand:
            server_message = str(ctx.message.server.id)
            print('Requested !alias at: ' + server_message)
            json_d = await fetch_json()

            try:
                server_data = json_d[server_message]
            except:
                return

            srv_anilist = []
            for ani in server_data['anime']:
                srv_anilist.append(ani)

            if str(ctx.message.author.id) not in server_data['serverowner']:
                return await self.bot.say('Hanya admin yang bisa menambah alias')

            if len(srv_anilist) < 1:
                return await self.bot.say("Tidak ada anime yang terdaftar di database")

            print('Membuat data')
            embed = discord.Embed(title="Alias", color=0x56acf3)
            embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.say(embed=embed)
            msg_author = ctx.message.author
            json_tables = {
                "alias_anime": "",
                "target_anime": ""
            }

            async def process_anime(table, emb_msg, author, anime_list):
                print('@@ Memproses anime')
                embed = discord.Embed(title="Alias", color=0x96df6a)
                embed.add_field(name='Judul/Garapan Anime', value="Ketik judul animenya (yang asli), bisa disingkat", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

                await_msg = await self.bot.wait_for_message(author=author)
                matches = get_close_matches(await_msg.content, anime_list)
                await self.bot.delete_message(await_msg)
                if not matches:
                    await self.bot.say('Tidak dapat menemukan judul tersebut di database')
                    return False, False
                elif len(matches) > 1:
                    await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))
                    return False, False

                embed = discord.Embed(title="Alias", color=0x96df6a)
                embed.add_field(name='Apakah benar?', value="Judul: **{}**".format(matches[0]), inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await self.bot.delete_message(emb_msg)
                emb_msg = await self.bot.say(embed=embed)

                to_react = ['✅', '❌']
                for reaction in to_react:
                        await self.bot.add_reaction(emb_msg, reaction)
                def checkReaction(reaction, user):
                    e = str(reaction.emoji)
                    return e.startswith(('✅', '❌'))

                res = await self.bot.wait_for_reaction(message=emb_msg, user=author, check=checkReaction)

                if '✅' in str(res.reaction.emoji):
                    table['target_anime'] = matches[0]
                    await self.bot.clear_reactions(emb_msg)
                elif '❌' in str(res.reaction.emoji):
                    await self.bot.say('**Dibatalkan!**')
                    await self.bot.clear_reactions(emb_msg)
                    return False, False

                return table, emb_msg

            async def process_alias(table, emb_msg, author):
                print('@@ Memproses alias')
                embed = discord.Embed(title="Alias", color=0x96df6a)
                embed.add_field(name='Alias', value="Ketik alias yang diinginkan", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

                await_msg = await self.bot.wait_for_message(author=author)
                table['alias_anime'] = await_msg.content
                await self.bot.delete_message(await_msg)

                return table, emb_msg

            json_tables, emb_msg = await process_anime(json_tables, emb_msg, msg_author, srv_anilist)

            if not json_tables:
                return print('@@ Cancelled process.')

            json_tables, emb_msg = await process_alias(json_tables, emb_msg, msg_author)
            print('@@ Making sure.')
            first_time = True
            cancel_toggled = False
            while True:
                embed=discord.Embed(title="Alias", description="Periksa data!\nReact jika ingin diubah.", color=0xe7e363)
                embed.add_field(name="1⃣ Anime/Garapan", value="{}".format(json_tables['target_anime']), inline=False)
                embed.add_field(name='2⃣ Alias', value="{}".format(json_tables['alias_anime']), inline=False)
                embed.add_field(name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False)
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                if first_time:
                    await self.bot.delete_message(emb_msg)
                    emb_msg = await self.bot.say(embed=embed)
                    first_time = False
                else:
                    emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

                to_react = ['1⃣', "2⃣", '✅', '❌']
                for reaction in to_react:
                        await self.bot.add_reaction(emb_msg, reaction)
                def checkReaction(reaction, user):
                    e = str(reaction.emoji)
                    return e.startswith(tuple(to_react))

                res = await self.bot.wait_for_reaction(message=emb_msg, user=msg_author, check=checkReaction)

                if to_react[0] in str(res.reaction.emoji):
                    await self.bot.clear_reactions(emb_msg)
                    json_tables, emb_msg = await process_anime(json_tables, emb_msg, msg_author, srv_anilist)
                elif to_react[1] in str(res.reaction.emoji):
                    await self.bot.clear_reactions(emb_msg)
                    json_tables, emb_msg = await process_alias(json_tables, emb_msg, msg_author)
                elif '✅' in str(res.reaction.emoji):
                    await self.bot.clear_reactions(emb_msg)
                    break
                elif '❌' in str(res.reaction.emoji):
                    print('@@ Cancelled.')
                    cancel_toggled = True
                    await self.bot.clear_reactions(emb_msg)
                    break

            if cancel_toggled:
                return await self.bot.say('**Dibatalkan!**')

            # Everything are done and now processing data
            print(json_tables)
            embed=discord.Embed(title="Alias", color=0x56acf3)
            embed.add_field(name="Memproses!", value='Membuat data...', inline=True)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            if json_tables['alias_anime'] in server_data['anime']['alias']:
                embed=discord.Embed(title="Alias", color=0xe24545)
                embed.add_field(
                    name="Dibatalkan!",
                    value='Alias **{}** sudah terdaftar untuk **{}**'.format(
                        json_tables['alias_anime'],
                        server_data['anime']['alias'][json_tables['alias_anime']]
                        ),
                    inline=True
                )
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                await self.bot.delete_message(emb_msg)
                return await self.bot.say(embed=embed)

            json_d[server_message]['anime']['alias'][json_tables['alias_anime']] = json_tables['target_anime']

            embed=discord.Embed(title="Alias", color=0x56acf3)
            embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            print("@@ Sending data")

            with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                json.dump(json_d, f, indent=4)
            print('@@ Sended.')
            embed=discord.Embed(title="Alias", color=0x96df6a)
            embed.add_field(name="Sukses!", value='Alias **{} ({})** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi'.format(json_tables['alias_anime'], json_tables['target_anime']), inline=True)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await self.bot.say(embed=embed)
            await self.bot.delete_message(emb_msg)

            success = await patch_json(json_d)

            if success:
                print('@@ Sending message...')
                return await self.bot.say("Berhasil menambahkan alias **{} ({})** ke dalam database utama naoTimes".format(json_tables['alias_anime'], json_tables['target_anime']))
            await self.bot.say('Gagal menambahkan ke database utama, owner telah diberikan pesan untuk membenarkan masalahnya')
            server_in = self.bot.get_server(bot_config['main_server'])
            mod_mem_data = server_in.get_member(bot_config['owner_id'])
            await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch `alias` pada server **{}**'.format(server_message))


    @alias.command(pass_context=True)
    async def list(self, ctx, *, judul):
        server_message = str(ctx.message.server.id)
        print('Requested !alias list at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        srv_anilist = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(sorted(srv_anilist))))

        matches = get_close_matches(judul, srv_anilist)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        srv_anilist_alias = []
        for k, v in server_data['anime']['alias'].items():
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
        await self.bot.say(embed=embed)


    @alias.command(pass_context=True, aliases=['remove'])
    async def hapus(self, ctx, *, judul):
        server_message = str(ctx.message.server.id)
        print('Requested !alias hapus at: ' + server_message)
        json_d = await fetch_json()

        try:
            server_data = json_d[server_message]
        except:
            return

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await self.bot.say('Hanya admin yang bisa menghapus alias')

        srv_anilist = []
        for ani in server_data['anime']:
            srv_anilist.append(ani)

        if not server_data['anime']['alias']:
            return await self.bot.say('Tidak ada alias yang terdaftar.')

        if not judul:
            if len(srv_anilist) < 1:
                return await self.bot.say('**Tidak ada anime yang terdaftar di database**')
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(sorted(srv_anilist))))

        matches = get_close_matches(judul, srv_anilist)
        print('Matches: {}'.format(", ".join(matches)))

        if not matches:
            return await self.bot.say('Tidak dapat menemukan judul tersebut di database')
        elif len(matches) > 1:
            return await self.bot.say('**Mungkin**: {}'.format(', '.join(matches)))

        srv_anilist_alias = []
        for k, v in server_data['anime']['alias'].items():
            if v in matches:
                srv_anilist_alias.append(k)

        if not srv_anilist_alias:
            return await self.bot.say('Tidak ada alias yang terdaftar untuk judul **{}**'.format(matches[0]))

        alias_chunked = [srv_anilist_alias[i:i + 5] for i in range(0, len(srv_anilist_alias), 5)]
        print(alias_chunked)

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
                emb_msg = await self.bot.say(embed=embed)

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

            for reaction in to_react:
                await self.bot.add_reaction(emb_msg, reaction)

            def checkReaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(tuple(to_react))

            res = await self.bot.wait_for_reaction(message=emb_msg, user=ctx.message.author, timeout=30, check=checkReaction)
            if res is None:
                return await self.bot.clear_reactions(emb_msg)
            elif '⏪' in str(res.reaction.emoji):
                n = n - 1
                await self.bot.clear_reactions(emb_msg)
                embed=discord.Embed(title="Alias list", color=0x47e0a7)
                embed.add_field(name='{}'.format(matches[0]), value=make_numbered_alias(alias_chunked[n-1]), inline=False)
                embed.add_field(name="*Informasi*", value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya\n⏩ Selanjutnya\n❌ Batalkan")
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                emb_msg = await self.bot.edit_message(emb_msg, embed=embed)
            elif '⏩' in str(res.reaction.emoji):
                n = n + 1
                await self.bot.clear_reactions(emb_msg)
                embed=discord.Embed(title="Alias list", color=0x47e0a7)
                embed.add_field(name='{}'.format(matches[0]), value=make_numbered_alias(alias_chunked[n-1]), inline=False)
                embed.add_field(name="*Informasi*", value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya\n⏩ Selanjutnya\n❌ Batalkan")
                embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
                emb_msg = await self.bot.edit_message(emb_msg, embed=embed)
            elif '❌' in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                return await self.bot.say('**Dibatalkan!**')
            else:
                await self.bot.clear_reactions(emb_msg)
                index_del = to_react.index(str(res.reaction.emoji))
                n_del = alias_chunked[n-1][index_del]
                del json_d[server_message]['anime']['alias'][n_del]
                
                with open('nao_showtimes.json', 'w') as f: # Local save before commiting
                    json.dump(json_d, f, indent=4)

                await self.bot.say('Alias **{} ({})** telah dihapus dari database'.format(n_del, matches[0]))
                
                success = await patch_json(json_d)

                if success:
                    break
                await self.bot.say('Gagal menambahkan ke database utama, owner telah diberikan pesan untuk membenarkan masalahnya')
                server_in = self.bot.get_server(bot_config['main_server'])
                mod_mem_data = server_in.get_member(bot_config['owner_id'])
                return await self.bot.send_message(mod_mem_data, 'Terjadi kesalahan patch `alias hapus` pada server **{}**'.format(server_message))


    @commands.command(pass_context=True)
    async def globalpatcher(self, ctx):
        """
        Global showtimes patcher, dangerous to use.
        You can change this to batch modify the database
        """
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !globalpatcher by admin')
        return print('@@ No patch/command found, cancelling...')

def setup(bot):
    bot.add_cog(Showtimes(bot))
