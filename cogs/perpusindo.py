# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import argparse
import asyncio
import re
import shlex
import sys
import time

import aiohttp
import discord
import discord.ext.commands as commands
from bs4 import BeautifulSoup

__KATEGORI__ = {
    'anime': ['amv', 'anime', 'animeinter', 'animeraw'],
    'amv': 'amv',
    'animelokal': 'anime',
    'animeinter': 'animeinter',
    'animeraw': 'animeraw',
    'audio': 'audio',
    'buku': ['buku', 'bukuinter', 'bukuraw'],
    'bukulokal': 'buku',
    'bukuinter': 'bukuinter',
    'bukuraw': 'bukuraw',
    'gambar': 'gbr',
    'la': ['la', 'lainter', 'lapv', 'lapvinter', 'laraw'],
    'lalokal': 'la',
    'lainter': 'lainter',
    'lapv': 'lapv',
    'lapvinter': 'lapvinter',
    'laraw': 'laraw',
    'softgame': '-Software/Gim'
}
__CHROME_UA__ = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36'}
__KATEGORI_DICT__ = {
    'anime': '-Semua kategori Anime',
    'amv': 'Anime Music Video',
    'animelokal': 'Anime Bahasa',
    'animeinter': 'Anime Non-Bahasa',
    'animeraw': 'Anime Raw',
    'audio': '-Audio/Musik',
    'buku': '-Semua Kategori Buku',
    'bukulokal': 'Buku Bahasa',
    'bukuinter': 'Buku Non-Bahasa',
    'bukuraw': 'Buku Raw',
    'gambar': '-Gambar/Foto',
    'la': '-Semua Kategori Live-Action',
    'lalokal': 'Live-Action Bahasa',
    'lainter': 'Live-Action Non-Bahasa',
    'laraw': 'Live-Action Raw',
    'lapv': 'PV/Musik Video/Idol',
    'lapvinter': 'PV/Musik Video/Idol Non-Bahasa',
    'softgame': '-Software/Gim'
}

class ArgumentParserError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message

class HelpException(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message

class BotArgumentParser(argparse.ArgumentParser):
    def print_help(self, file=None):
        raise HelpException(self.format_help())

    def exit(self, status=0, message=None):
        raise HelpException(message)

    def error(self, message=None):
        raise ArgumentParserError(message)


def parse_error(err_str):
    if err_str.startswith('unrecognized arguments'):
        err_str = err_str.replace('unrecognized arguments', 'Argumen tidak diketahui')
    elif err_str.startswith('the following arguments are required'):
        err_str = err_str.replace('the following arguments are required', 'Argumen berikut wajib diberikan')
    if 'usage' in err_str:
        err_str = err_str.replace(
            'usage', 'Gunakan'
        ).replace(
            'positional arguments', 'Argumen yang diwajibkan'
        ).replace(
            'optional arguments', 'Argumen opsional'
        ).replace(
            'show this help message and exit', 'Perlihatkan bantuan perintah'
        )
    return err_str

def parse_args(str_txt: str, s: str, search_mode=True):
    '''parse an argument that passed'''
    parser = BotArgumentParser(prog="!perpus " + s, usage="!perpus " + s, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    if search_mode:
        parser.add_argument('input', help='Apa yang mau dicari')
    parser.add_argument('--category', '-C', required=False, default=[], dest='kategori', action='append', help='Kategori pencarian - cek dengan !perpus kategori')
    parser.add_argument('--user', '-u', required=False, default=[], action='append', help='Cari berkas hanya pada user yang diberikan')
    parser.add_argument('--biasa', required=False, default=False, action='store_true', help='Tambah filter untuk berkas biasa/normal')
    parser.add_argument('--aplus', required=False, default=False, action='store_true', help='Tambah filter untuk berkas A+')
    parser.add_argument('--remake', required=False, default=False, action='store_true', help='Tambah filter untuk berkas remake')
    parser.add_argument('--trusted', required=False, default=False, action='store_true', help='Tambah filter untuk berkas Trusted')
    try:
        return parser.parse_args(shlex.split(str_txt))
    except ArgumentParserError as argserror:
        return str(argserror)
    except HelpException as help_:
        return '```\n' + str(help_) + '\n```'

# 'src': 'Chihayafuru', # Search Input
# 'category': '',
# 'user[]': ['KentutNeraka', 'S7z'], # User
# 'cartel': '', # Biasa: 1, Remake: 4, Trusted: 2, A+: 3

async def check_user(user):
    payload = {
        'page': 1,
        'src': '', # Search Input
        'category': '',
        'user[]': [user], # User
        'cartel': '', # Biasa: 1, Remake: 4, Trusted: 2, A+: 3
        'fansub': '',
        'anime': '',
        'pageLoad': 'lobby'
    }
    async with aiohttp.ClientSession(headers=__CHROME_UA__) as sesi:
        async with sesi.post('https://www.perpusindo.info/commonajax/bindcontentfiles', data=payload) as r:
            data = await r.text()
            if r.status != 200:
                return False
            if data[:3] != '000':
                return False
    return True


async def fetch_perpus(keyword=None, kategori=[], user=[], berkas_biasa=False, berkas_aplus=False, berkas_remake=False, berkas_trust=False):
    """Cari dan parse perpusindo.info"""
    payload = {
        'page': 1,
        'fansub': '',
        'anime': '',
        'pageLoad': 'lobby'
    }
    if kategori:
        temp_kat = []
        for k in kategori:
            if k not in __KATEGORI__.keys():
                return 'Kategori `{}` tidak diketahui. cek lagi dengan `!perpus kategori`'.format(k)
            te = __KATEGORI__[k]
            if isinstance(te, list):
                temp_kat.extend(te)
            elif isinstance(te, str):
                temp_kat.append(te)
        payload['category[]'] = list(dict.fromkeys(temp_kat))
    else:
        payload['category'] = ''

    if user:
        for u in user:
            res_user = await check_user(u)
            if not res_user:
                return 'Tidak dapat menemukan user `{}`.'.format(u)
        payload['user[]'] = user
    else:
        payload['user'] = ''

    kartel = []
    if berkas_biasa:
        kartel.append(1)
    if berkas_remake:
        kartel.append(4)
    if berkas_aplus:
        kartel.append(3)
    if berkas_trust:
        kartel.append(2)

    if kartel:
        payload['cartel[]'] = kartel
    else:
        payload['cartel'] = ''

    if keyword:
        payload['src'] = keyword
    else:
        payload['src'] = ''

    print('[@] Sending PerpusIndo Payload:')
    print(payload)

    async with aiohttp.ClientSession(headers=__CHROME_UA__) as sesi:
        try:
            async with sesi.post('https://www.perpusindo.info/commonajax/bindcontentfiles', data=payload) as r:
                data = await r.text()
                if r.status > 310:
                    print('Error: {}'.format(data[4:]))
                    return "Tidak ada hasil."
                if data[:3] != '000':
                    print('Error: {}'.format(data[4:]))
                    return 'Tidak ada hasil.'
        except aiohttp.ClientError:
            return 'Koneksi error'

    soup = BeautifulSoup(data[4:], 'html.parser')
    all_data = soup.find_all('td', attrs={'class': 'judulBerkas'})

    queried_link = []
    for a in all_data:
        queried_link.append(a.find('a')['href'])

    if not queried_link:
        return 'Tidak ada hasil.'

    if not keyword:
        queried_link = queried_link[:10]

    full_query_results = []
    user_profile_pic = {}
    print('[@] Parsing result')
    async with aiohttp.ClientSession(headers=__CHROME_UA__) as sesi:
        for query in queried_link:
            try:
                async with sesi.get(query) as r:
                    data = await r.text()
                    if r.status > 310:
                        continue
            except aiohttp.ClientError:
                continue

            information = None
            is_remake = False
            is_trusted = False
            is_aplus = False

            soup = BeautifulSoup(data, 'html.parser')
            normal_data = soup.find('div', {'class': 'berkas-1'})
            test_aplus = soup.find('div', {'class': 'berkas-3'})
            test_trust = soup.find('div', {'class': 'berkas-2'})
            test_remake = soup.find('div', {'class': 'berkas-4'})
            if normal_data:
                name = normal_data.find('h3').text.rstrip().strip('\n')
                information = normal_data.find('span').text.rstrip().strip('\n')
            if test_aplus:
                name = test_aplus.find('h3').text.rstrip().strip('\n')
                information = test_aplus.find('span').text.rstrip().strip('\n')
                is_aplus = True
            if test_trust:
                name = test_trust.find('h3').text.rstrip().strip('\n')
                information = test_trust.find('span').text.rstrip().strip('\n')
                is_trusted = True
            if test_remake:
                name = test_remake.find('h3').text.rstrip().strip('\n')
                information = test_remake.find('span').text.rstrip().strip('\n')
                is_remake = True

            dl_links = dict()
            for dl in soup.find_all('a', {'class': 'btnDownload'}):
                dl_links[dl.text.rstrip().strip('\n')] = dl['href']

            url = None
            submitter = None
            create_date = None
            views = None
            sites = None
            likes = None
            category = None
            user_pp = None

            table_detail = soup.find('table', {'class': 'table tblShareFileDetail'}).find_all('td')
            for n, i in enumerate(table_detail):
                if i.text.rstrip().strip('\n').startswith('Tautan'):
                    url = table_detail[n+1].text.rstrip().strip('\n')
                if i.text.rstrip().strip('\n').startswith('Dibuat Oleh'):
                    submitter = table_detail[n+1].text.rstrip().strip('\n')
                    submitter_uri = table_detail[n+1].find('a')['href']
                    if submitter not in user_profile_pic:
                        try:
                            fetched = True
                            async with sesi.get(submitter_uri) as r:
                                data2 = await r.text()
                                fetched = True
                                if r.status > 310:
                                    fetched = False
                        except aiohttp.ClientError:
                            fetched = False
                        if fetched:
                            soup2 = BeautifulSoup(data2, 'html.parser')
                            img_uri = soup2.find('img', {'class': 'img-thumbnail img-circle thumb128'})['src']
                            user_profile_pic[submitter] = img_uri
                if i.text.rstrip().strip('\n').startswith('Berkas Dibuat'):
                    create_date = table_detail[n+1].text.rstrip().strip('\n')
                if i.text.rstrip().strip('\n').startswith('Berkas Dilihat'):
                    views = table_detail[n+1].text.rstrip().strip('\n')
                if i.text.rstrip().strip('\n').startswith('Berkas Disukai'):
                    likes = table_detail[n+1].text.rstrip().strip('\n')[1:]
                if i.text.rstrip().strip('\n').startswith('Situs'):
                    sites = table_detail[n+1].find('a')['href']
                    if not re.search(r"((http(|s))\:\/\/)", sites):
                        sites = 'http://' + sites
                if i.text.rstrip().strip('\n').startswith('Kategori Berkas'):
                    category = table_detail[n+1].text.rstrip().strip('\n')

            dataset = {
                'name': name,
                'information': information,
                'submitter': submitter,
                'creation': create_date,
                'category': category,
                'views': views,
                'likes': likes,
                'situs': sites,
                'download_links': dl_links,
                'url': url,
                'is_trusted': is_trusted,
                'is_remake': is_remake,
                'is_aplus': is_aplus
            }

            full_query_results.append(dataset)

    return {'result': full_query_results, 'data_total': len(full_query_results), 'upp': user_profile_pic}


def color_bar(t_=False, r_=False, ap_=False):
    if t_:
        return 0xa7d195
    elif r_:
        return 0xd88787
    elif ap_:
        return 0x4b90ce
    return 0x362090

class PerpusIndo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['perpusindo', 'pi'])
    @commands.guild_only()
    async def perpus(self, ctx):
        if not ctx.invoked_subcommand:
            helpmain = discord.Embed(title="Bantuan Perintah (!perpus)", description="versi 1.5.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='!perpus', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!perpus cari <argumen>', value="```Mencari berkas di perpusindo.info (gunakan argumen -h untuk melihat bantuan)```", inline=False)
            helpmain.add_field(name='!perpus terbaru <argumen>', value="```Melihat 10 berkas terbaru (gunakan argumen -h untuk melihat bantuan)```", inline=False)
            helpmain.add_field(name='!perpus kategori', value="```Melihat kategori apa aja yang bisa dipakai```", inline=False)
            helpmain.add_field(name='Aliases', value="!perpus, !perpusindo, !pi", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 1.5.0")
            await ctx.send(embed=helpmain)


    @perpus.command(aliases=['category'])
    async def kategori(self, ctx):
        text_ = '**Berikut adalah kategorinya**\n**Format Penulisan**: *Kode* - *Nama*\n'
        for k, v in __KATEGORI_DICT__.items():
            if v.startswith('-'):
                text_ += '\n'
                v = v[1:]
            text_ += '**`{}`** - **{}**\n'.format(k, v)

        msg = await ctx.send(text_)
        reactmoji = ['✅']
        for react in reactmoji:
            await msg.add_reaction(react)

        def check_react(reaction, user):
            return user == ctx.message.author and str(reaction.emoji) in reactmoji

        res, user = await self.bot.wait_for('reaction_add', check=check_react)
        if user != ctx.message.author:
            pass
        elif '✅' in str(res.emoji):
            await msg.clear_reactions()
            await ctx.message.delete()
            return await msg.delete()


    @perpus.command(aliases=['search'])
    async def cari(self, ctx, *, args_=''):
        args = parse_args(args_, 'cari')
        if isinstance(args, str):
            return await ctx.send(parse_error(args))
        piqres = await fetch_perpus(args.input, args.kategori, args.user, args.biasa, args.aplus, args.remake, args.trusted)
        if isinstance(piqres, str):
            return await ctx.send(piqres)

        max_page = piqres['data_total']
        resdata = piqres['result']
        profile_ = piqres['upp']

        first_run = True
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                kwargs_embed = {
                    'color': color_bar(data['is_trusted'], data['is_remake'], data['is_aplus'])
                }
                if data['information']:
                    kwargs_embed['description'] = data['information']
                footer_icon = "https://www.perpusindo.info/assets/PINew/img/logo-single.png"
                if data['submitter'] in profile_:
                    if profile_[data['submitter']]:
                        footer_icon = profile_[data['submitter']]
                embed = discord.Embed(**kwargs_embed)
                embed.set_author(name=data['name'], url=data['url'], icon_url=footer_icon)
                embed.set_footer(text='Dibuat: {}'.format(data['creation']), icon_url="https://www.perpusindo.info/assets/PINew/img/logo-single.png")

                vi, li = data['views'], data['likes']
                dl_link_fmt = '📥 \||'
                if data['situs']:
                    dl_link_fmt += ' [Website]({}) \||'.format(data['situs'])
                for namae, uri in data['download_links'].items():
                    dl_link_fmt += ' **[{n}]({li})** \||'.format(n=namae, li=uri)

                embed.add_field(name="Uploader", value=data['submitter'], inline=True)
                embed.add_field(name="Kategori", value=data['category'], inline=True)
                embed.add_field(name="Stats", value='**Views**: {}\n**Likes**: {}'.format(vi, li), inline=False)
                embed.add_field(name="Download", value=dl_link_fmt.rstrip(' \||').rstrip(' \||'), inline=False)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                break
            elif num == 1:
                reactmoji.append('⏩')
            elif num == max_page:
                reactmoji.append('⏪')
            elif num > 1 and num < max_page:
                reactmoji.extend(['⏪', '⏩'])
            for reaction in reactmoji:
                await msg.add_reaction(reaction)

            def check_react(reaction, user):
                return user == ctx.message.author and str(reaction.emoji) in reactmoji

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif '⏪' in str(res.emoji):
                num = num - 1
                data = resdata[num - 1]

                kwargs_embed = {
                    'color': color_bar(data['is_trusted'], data['is_remake'], data['is_aplus'])
                }
                if data['information']:
                    kwargs_embed['description'] = data['information']
                footer_icon = "https://www.perpusindo.info/assets/PINew/img/logo-single.png"
                if data['submitter'] in profile_:
                    if profile_[data['submitter']]:
                        footer_icon = profile_[data['submitter']]
                embed = discord.Embed(**kwargs_embed)
                embed.set_author(name=data['name'], url=data['url'], icon_url=footer_icon)
                embed.set_footer(text='Dibuat: {}'.format(data['creation']), icon_url="https://www.perpusindo.info/assets/PINew/img/logo-single.png")

                vi, li = data['views'], data['likes']
                dl_link_fmt = '📥 \||'
                if data['situs']:
                    dl_link_fmt += ' [Website]({}) \||'.format(data['situs'])
                for namae, uri in data['download_links'].items():
                    dl_link_fmt += ' **[{n}]({li})** \||'.format(n=namae, li=uri)

                embed.add_field(name="Uploader", value=data['submitter'], inline=True)
                embed.add_field(name="Kategori", value=data['category'], inline=True)
                embed.add_field(name="Stats", value='**Views**: {}\n**Likes**: {}'.format(vi, li), inline=False)
                embed.add_field(name="Download", value=dl_link_fmt.rstrip(' \||'), inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif '⏩' in str(res.emoji):
                num = num + 1
                data = resdata[num - 1]

                kwargs_embed = {
                    'color': color_bar(data['is_trusted'], data['is_remake'], data['is_aplus'])
                }
                if data['information']:
                    kwargs_embed['description'] = data['information']
                footer_icon = "https://www.perpusindo.info/assets/PINew/img/logo-single.png"
                if data['submitter'] in profile_:
                    if profile_[data['submitter']]:
                        footer_icon = profile_[data['submitter']]
                embed = discord.Embed(**kwargs_embed)
                embed.set_author(name=data['name'], url=data['url'], icon_url=footer_icon)
                embed.set_footer(text='Dibuat: {}'.format(data['creation']), icon_url="https://www.perpusindo.info/assets/PINew/img/logo-single.png")

                vi, li = data['views'], data['likes']
                dl_link_fmt = '📥 \||'
                if data['situs']:
                    dl_link_fmt += ' [Website]({}) \||'.format(data['situs'])
                for namae, uri in data['download_links'].items():
                    dl_link_fmt += ' **[{n}]({li})** \||'.format(n=namae, li=uri)

                embed.add_field(name="Uploader", value=data['submitter'], inline=True)
                embed.add_field(name="Kategori", value=data['category'], inline=True)
                embed.add_field(name="Stats", value='**Views**: {}\n**Likes**: {}'.format(vi, li), inline=False)
                embed.add_field(name="Download", value=dl_link_fmt.rstrip(' \||'), inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)


    @perpus.command(aliases=['latest'])
    async def terbaru(self, ctx, *, args_=''):
        args = parse_args(args_, 'terbaru', False)
        if isinstance(args, str):
            return await ctx.send(parse_error(args))
        piqres = await fetch_perpus(None, args.kategori, args.user, args.biasa, args.aplus, args.remake, args.trusted)
        if isinstance(piqres, str):
            return await ctx.send(piqres)

        max_page = piqres['data_total']
        resdata = piqres['result']
        profile_ = piqres['upp']

        first_run = True
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                kwargs_embed = {
                    'color': color_bar(data['is_trusted'], data['is_remake'], data['is_aplus'])
                }
                if data['information']:
                    kwargs_embed['description'] = data['information']
                footer_icon = "https://www.perpusindo.info/assets/PINew/img/logo-single.png"
                if data['submitter'] in profile_:
                    if profile_[data['submitter']]:
                        footer_icon = profile_[data['submitter']]
                embed = discord.Embed(**kwargs_embed)
                embed.set_author(name=data['name'], url=data['url'], icon_url=footer_icon)
                embed.set_footer(text='Dibuat: {}'.format(data['creation']), icon_url="https://www.perpusindo.info/assets/PINew/img/logo-single.png")

                vi, li = data['views'], data['likes']
                dl_link_fmt = '📥 \||'
                if data['situs']:
                    dl_link_fmt += ' [Website]({}) \||'.format(data['situs'])
                for namae, uri in data['download_links'].items():
                    dl_link_fmt += ' **[{n}]({li})** \||'.format(n=namae, li=uri)

                embed.add_field(name="Uploader", value=data['submitter'], inline=True)
                embed.add_field(name="Kategori", value=data['category'], inline=True)
                embed.add_field(name="Stats", value='**Views**: {}\n**Likes**: {}'.format(vi, li), inline=False)
                embed.add_field(name="Download", value=dl_link_fmt.rstrip(' \||'), inline=False)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                break
            elif num == 1:
                reactmoji.append('⏩')
            elif num == max_page:
                reactmoji.append('⏪')
            elif num > 1 and num < max_page:
                reactmoji.extend(['⏪', '⏩'])
            for reaction in reactmoji:
                await msg.add_reaction(reaction)

            def check_react(reaction, user):
                return user == ctx.message.author and str(reaction.emoji) in reactmoji

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif '⏪' in str(res.emoji):
                num = num - 1
                data = resdata[num - 1]

                kwargs_embed = {
                    'color': color_bar(data['is_trusted'], data['is_remake'], data['is_aplus'])
                }
                if data['information']:
                    kwargs_embed['description'] = data['information']
                footer_icon = "https://www.perpusindo.info/assets/PINew/img/logo-single.png"
                if data['submitter'] in profile_:
                    if profile_[data['submitter']]:
                        footer_icon = profile_[data['submitter']]
                embed = discord.Embed(**kwargs_embed)
                embed.set_author(name=data['name'], url=data['url'], icon_url=footer_icon)
                embed.set_footer(text='Dibuat: {}'.format(data['creation']), icon_url="https://www.perpusindo.info/assets/PINew/img/logo-single.png")

                vi, li = data['views'], data['likes']
                dl_link_fmt = '📥 \||'
                if data['situs']:
                    dl_link_fmt += ' [Website]({}) \||'.format(data['situs'])
                for namae, uri in data['download_links'].items():
                    dl_link_fmt += ' **[{n}]({li})** \||'.format(n=namae, li=uri)

                embed.add_field(name="Uploader", value=data['submitter'], inline=True)
                embed.add_field(name="Kategori", value=data['category'], inline=True)
                embed.add_field(name="Stats", value='**Views**: {}\n**Likes**: {}'.format(vi, li), inline=False)
                embed.add_field(name="Download", value=dl_link_fmt.rstrip(' \||'), inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif '⏩' in str(res.emoji):
                num = num + 1
                data = resdata[num - 1]

                kwargs_embed = {
                    'color': color_bar(data['is_trusted'], data['is_remake'], data['is_aplus'])
                }
                if data['information']:
                    kwargs_embed['description'] = data['information']
                footer_icon = "https://www.perpusindo.info/assets/PINew/img/logo-single.png"
                if data['submitter'] in profile_:
                    if profile_[data['submitter']]:
                        footer_icon = profile_[data['submitter']]
                embed = discord.Embed(**kwargs_embed)
                embed.set_author(name=data['name'], url=data['url'], icon_url=footer_icon)
                embed.set_footer(text='Dibuat: {}'.format(data['creation']), icon_url="https://www.perpusindo.info/assets/PINew/img/logo-single.png")

                vi, li = data['views'], data['likes']
                dl_link_fmt = '📥 \||'
                if data['situs']:
                    dl_link_fmt += ' [Website]({}) \||'.format(data['situs'])
                for namae, uri in data['download_links'].items():
                    dl_link_fmt += ' **[{n}]({li})** \||'.format(n=namae, li=uri)

                embed.add_field(name="Uploader", value=data['submitter'], inline=True)
                embed.add_field(name="Kategori", value=data['category'], inline=True)
                embed.add_field(name="Stats", value='**Views**: {}\n**Likes**: {}'.format(vi, li), inline=False)
                embed.add_field(name="Download", value=dl_link_fmt.rstrip(' \||'), inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)


def setup(bot):
    bot.add_cog(PerpusIndo(bot))
