# -*- coding: utf-8 -*-
#!/usr/bin/env python3
import asyncio
import time
from datetime import datetime, timedelta

import aiohttp
import discord
import discord.ext.commands as commands

def setup(bot):
    bot.add_cog(Anilist(bot))

anilist_query = '''
query ($page: Int, $perPage: Int, $search: String) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            total
            currentPage
            lastPage
            hasNextPage
            perPage
        }
        media(search: $search, type: %s) {
            id
            title {
                romaji
                english
                native
            }
            coverImage {
                large
            }
            averageScore
            chapters
            volumes
            episodes
            format
            status
            source
            genres
            description(asHtml:false)
            startDate {
                year
                month
                day
            }
            endDate {
                year
                month
                day
            }
            nextAiringEpisode {
                airingAt
                timeUntilAiring
                episode
            }
        }
    }
}
'''


def monthintext(number):
    idn = ["Januari", "Februari", "Maret", "April",
            "Mei", "Juni", "Juli", "Agustus",
            "September", "Oktober", "November", "Desember"]
    if number is None:
        return "Unknown"
    x = number - 1
    if x < 0:
        return "Unknown"
    return idn[number - 1]


def create_time_format(secs):
    months = int(secs // 2592000) # 30 days format
    secs -= months * 2592000
    days = int(secs // 86400)
    secs -= days * 86400
    hours = int(secs // 3600)
    secs -= hours * 3600
    minutes = int(secs // 60)
    secs -= minutes * 60

    return_text = ''
    if months != 0:
        return_text += '{} bulan '.format(months)

    return return_text + '{} hari {} jam {} menit {} detik lagi'.format(days, hours, minutes, secs)


def html2markdown(text):
    re_list = {
        '<br>': '\n',
        '</br>': '\n',
        '<i>': '*',
        '</i>': '*',
        '<b>': '**',
        '</b>': '**',
        '\n\n': '\n'
    }
    for k, v in re_list.items():
        text = text.replace(k, v)
    return text


async def fetch_anilist(title, method):
    variables = {
        'search': title,
        'page': 1,
        'perPage': 50
    }
    async with aiohttp.ClientSession() as sesi:
        try:
            async with sesi.post('https://graphql.anilist.co', json={'query': anilist_query % method.upper(), 'variables': variables}) as r:
                try:
                    data = await r.json()
                except IndexError:
                    return 'ERROR: Terjadi kesalahan internal'
                if r.status != 200:
                    if r.status == 404:
                        return "ERROR: Tidak dapat menemukan anime tersebut"
                    elif r.status == 500:
                        return "ERROR: Internal Error :/"
                try:
                    query = data['data']['Page']['media']
                except IndexError:
                    return "ERROR: Tidak ada hasil."
        except aiohttp.ClientError:
            return 'ERROR: Koneksi terputus'

    # Koleksi translasi dan perubahan teks
    status_tl = {
        'finished': 'Tamat',
        'releasing': 'Sedang Berlangsung',
        'not_yet_released': 'Belum Rilis',
        'cancelled': 'Batal Tayang'
    }
    format_tl = {
        "TV": "Anime",
        "TV_SHORT": "Anime Pendek",
        "MOVIE": "Film",
        "SPECIAL": "Spesial",
        "OVA": "OVA",
        "ONA": "ONA",
        "MUSIC": "MV",
        "NOVEL": "Novel",
        "MANGA": "Manga",
        "ONE_SHOT": "One-Shot",
        None: "Lainnya"
    }
    source_tl = {
        "ORIGINAL": "Original",
        "MANGA": "Manga",
        "VISUAL_NOVEL": "Visual Novel",
        "LIGHT_NOVEL": "Novel Ringan",
        "VIDEO_GAME": "Gim",
        "OTHER": "Lainnya",
        None: "Lainnya"
    }

    full_query_result = []
    for entry in query:
        start_y = entry['startDate']['year']
        end_y = entry['endDate']['year']
        if not start_y:
            start = 'Belum Rilis'
        else:
            start = '{}'.format(start_y)
            start_m = entry['startDate']['month']
            if start_m:
                start = '{}/{}'.format(start, start_m)
                start_d = entry['startDate']['day']
                if start_d:
                    start = '{}/{}'.format(start, start_d)
        
        if not end_y:
            end = 'Belum Berakhir'
        else:
            end = '{}'.format(end_y)
            end_m = entry['endDate']['month']
            if end_m:
                end = '{}/{}'.format(end, end_m)
                end_d = entry['endDate']['day']
                if end_d:
                    end = '{}/{}'.format(end, end_d)

        title = entry['title']['romaji']
        ani_id = str(entry['id'])

        # Judul lain
        other_title = entry['title']['native']
        english_title = entry['title']['english']
        if english_title:
            if other_title:
                other_title += '\n' + english_title
            else:
                other_title = english_title

        score_rate = entry['averageScore']
        if score_rate:
            score_rate = '{}/10'.format(score_rate/10)
 
        description = entry['description']
        if description is not None:
            description = html2markdown(description)
            if len(description) > 1023:
                description = description[:1020] + '...'

        genres = ', '.join(entry['genres']).lower()
        status = entry['status'].lower()
        img = entry['coverImage']['large']
        ani_link = 'https://anilist.co/{m}/{id}'.format(m=method, id=ani_id)

        dataset = {
            'title': title,
            'title_other': other_title,
            'start_date': start,
            'end_date': end,
            'poster_img': img,
            'synopsis': description,
            'status': status_tl[status],
            'format': format_tl[entry['format']],
            'source_fmt': source_tl[entry['source']],
            'link': ani_link,
            'score': score_rate,
            'footer': "ID: {} | {}".format(ani_id, genres)
        }

        if method == 'manga':
            vol = entry['volumes']
            ch = entry['chapters']
            ch_vol = '{c} chapterXXC/{v} volumeXXV'.format(c=ch, v=vol).replace('None', '??')
            if ch:
                if ch > 1:
                    ch_vol = ch_vol.replace('XXC', 's')
            ch_vol = ch_vol.replace('XXC', '')
            if vol:
                if vol > 1:
                    ch_vol = ch_vol.replace('XXV', 's')
            ch_vol = ch_vol.replace('XXV', '')
            dataset['ch_vol'] = ch_vol
        if method == 'anime':
            dataset['episodes'] = entry["episodes"]
            if status in ['releasing', 'not_yet_released']:
                ne_data = entry['nextAiringEpisode']
                if ne_data:
                    airing_time = ne_data['airingAt']
                    d_airing_time = timedelta(seconds=abs(airing_time))
                    time_tuple = datetime(1,1,1) + d_airing_time

                    dataset['airing_date'] = '{d} {m} {y}'.format(d=time_tuple.day, m=monthintext(time_tuple.month), y=time.strftime('%Y'))
                    dataset['next_episode'] = ne_data['episode']
                    dataset['time_remain'] = create_time_format(ne_data['timeUntilAiring'])

        for k, v in dataset.items():
            if not v:
                dataset[k] = 'Tidak ada'

        full_query_result.append(dataset)
    return {'result': full_query_result, 'data_total': len(full_query_result)}


class Anilist:
    def __init__(self, bot):
        self.bot = bot

    async def __error(self, ctx, error):
        if not isinstance(error, commands.UserInputError):
            raise error
        
        try:
            await ctx.send(error)
        except discord.Forbidden:
            pass


    @commands.command(pass_context=True, aliases=['animu', 'kartun', 'ani'])
    async def anime(self, ctx, *, judul):
        """Mencari informasi anime lewat API anilist.co"""
        aqres = await fetch_anilist(judul, 'anime')
        if isinstance(aqres, str):
            return await self.bot.say(aqres)

        max_page = aqres['data_total']
        resdata = aqres['result']

        first_run = True
        time_table = False
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                embed = discord.Embed(color=0x19212d)

                embed.set_thumbnail(url=data['poster_img'])
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text=data['footer'])

                embed.add_field(name="Nama Lain", value=data['title_other'], inline=True)
                embed.add_field(name="Episode", value=data['episodes'], inline=True)
                embed.add_field(name="Status", value=data['status'], inline=True)
                embed.add_field(name="Skor", value=data['score'], inline=True)
                embed.add_field(name="Rilis", value=data['start_date'], inline=True)
                embed.add_field(name="Berakhir", value=data['end_date'], inline=True)
                embed.add_field(name="Format", value=data['format'], inline=True)
                embed.add_field(name="Adaptasi", value=data['source_fmt'], inline=True)
                embed.add_field(name="Sinopsis", value=data['synopsis'], inline=False)

                first_run = False
                msg = await self.bot.say(embed=embed)

            reactmoji = []
            if time_table:
                reactmoji.append('👍')
            elif max_page == 1 and num == 1:
                pass
            elif num == 1:
                reactmoji.append('⏩')
            elif num == max_page:
                reactmoji.append('⏪')
            elif num > 1 and num < max_page:
                reactmoji.extend(['⏪', '⏩'])
            if 'next_episode' in data and not time_table:
                reactmoji.append('⏳')
            reactmoji.append('✅')
            for reaction in reactmoji:
                await self.bot.add_reaction(msg, reaction)

            def check_reaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(tuple(reactmoji))

            res = await self.bot.wait_for_reaction(message=msg, user=ctx.message.author, timeout=30, check=check_reaction)
            if not res:
                return await self.bot.clear_reactions(msg)
            elif '⏪' in str(res.reaction.emoji):
                num = num - 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212d)

                embed.set_thumbnail(url=data['poster_img'])
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text=data['footer'])

                embed.add_field(name="Nama Lain", value=data['title_other'], inline=True)
                embed.add_field(name="Episode", value=data['episodes'], inline=True)
                embed.add_field(name="Status", value=data['status'], inline=True)
                embed.add_field(name="Skor", value=data['score'], inline=True)
                embed.add_field(name="Rilis", value=data['start_date'], inline=True)
                embed.add_field(name="Berakhir", value=data['end_date'], inline=True)
                embed.add_field(name="Format", value=data['format'], inline=True)
                embed.add_field(name="Adaptasi", value=data['source_fmt'], inline=True)
                embed.add_field(name="Sinopsis", value=data['synopsis'], inline=False)

                await self.bot.clear_reactions(msg)
                msg = await self.bot.edit_message(msg, embed=embed)
            elif '⏩' in str(res.reaction.emoji):
                num = num + 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212d)

                embed.set_thumbnail(url=data['poster_img'])
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text=data['footer'])

                embed.add_field(name="Nama Lain", value=data['title_other'], inline=True)
                embed.add_field(name="Episode", value=data['episodes'], inline=True)
                embed.add_field(name="Status", value=data['status'], inline=True)
                embed.add_field(name="Skor", value=data['score'], inline=True)
                embed.add_field(name="Rilis", value=data['start_date'], inline=True)
                embed.add_field(name="Berakhir", value=data['end_date'], inline=True)
                embed.add_field(name="Format", value=data['format'], inline=True)
                embed.add_field(name="Adaptasi", value=data['source_fmt'], inline=True)
                embed.add_field(name="Sinopsis", value=data['synopsis'], inline=False)

                await self.bot.clear_reactions(msg)
                msg = await self.bot.edit_message(msg, embed=embed)
            elif '👍' in str(res.reaction.emoji):
                embed = discord.Embed(color=0x19212d)

                embed.set_thumbnail(url=data['poster_img'])
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text=data['footer'])

                embed.add_field(name="Nama Lain", value=data['title_other'], inline=True)
                embed.add_field(name="Episode", value=data['episodes'], inline=True)
                embed.add_field(name="Status", value=data['status'], inline=True)
                embed.add_field(name="Skor", value=data['score'], inline=True)
                embed.add_field(name="Rilis", value=data['start_date'], inline=True)
                embed.add_field(name="Berakhir", value=data['end_date'], inline=True)
                embed.add_field(name="Format", value=data['format'], inline=True)
                embed.add_field(name="Adaptasi", value=data['source_fmt'], inline=True)
                embed.add_field(name="Sinopsis", value=data['synopsis'], inline=False)

                time_table = False
                await self.bot.clear_reactions(msg)
                msg = await self.bot.edit_message(msg, embed=embed)
            elif '⏳' in str(res.reaction.emoji):
                ep_txt = 'Episode ' + str(data['next_episode'])
                embed = discord.Embed(color=0x19212d)
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text='Akan tayang pada {}'.format(data['airing_date']))

                embed.add_field(name=ep_txt, value=data['time_remain'], inline=False)

                time_table = True
                await self.bot.clear_reactions(msg)
                msg = await self.bot.edit_message(msg, embed=embed)
            elif '✅' in str(res.reaction.emoji):
                await self.bot.delete_message(ctx.message)
                return await self.bot.delete_message(msg)


    @commands.command(pass_context=True, aliases=['komik', 'mango'])
    async def manga(self, ctx, *, judul):
        """Mencari informasi manga lewat API anilist.co"""
        aqres = await fetch_anilist(judul, 'manga')
        if isinstance(aqres, str):
            return await self.bot.say(aqres)

        max_page = aqres['data_total']
        resdata = aqres['result']

        first_run = True
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                embed = discord.Embed(color=0x19212d)

                embed.set_thumbnail(url=data['poster_img'])
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text=data['footer'])

                embed.add_field(name="Nama Lain", value=data['title_other'], inline=True)
                embed.add_field(name="Chapter/Volume", value=data['ch_vol'], inline=True)
                embed.add_field(name="Status", value=data['status'], inline=True)
                embed.add_field(name="Skor", value=data['score'], inline=True)
                embed.add_field(name="Rilis", value=data['start_date'], inline=True)
                embed.add_field(name="Berakhir", value=data['end_date'], inline=True)
                embed.add_field(name="Format", value=data['format'], inline=True)
                embed.add_field(name="Adaptasi", value=data['source_fmt'], inline=True)
                embed.add_field(name="Sinopsis", value=data['synopsis'], inline=False)

                first_run = False
                msg = await self.bot.say(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                pass
            elif num == 1:
                reactmoji.append('⏩')
            elif num == max_page:
                reactmoji.append('⏪')
            elif num > 1 and num < max_page:
                reactmoji.extend(['⏪', '⏩'])
            reactmoji.append('✅')
            for reaction in reactmoji:
                await self.bot.add_reaction(msg, reaction)

            def check_reaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(tuple(reactmoji))

            res = await self.bot.wait_for_reaction(message=msg, user=ctx.message.author, timeout=30, check=check_reaction)
            if not res:
                return await self.bot.clear_reactions(msg)
            elif '⏪' in str(res.reaction.emoji):
                num = num - 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212d)

                embed.set_thumbnail(url=data['poster_img'])
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text=data['footer'])

                embed.add_field(name="Nama Lain", value=data['title_other'], inline=True)
                embed.add_field(name="Chapter/Volume", value=data['ch_vol'], inline=True)
                embed.add_field(name="Status", value=data['status'], inline=True)
                embed.add_field(name="Skor", value=data['score'], inline=True)
                embed.add_field(name="Rilis", value=data['start_date'], inline=True)
                embed.add_field(name="Berakhir", value=data['end_date'], inline=True)
                embed.add_field(name="Format", value=data['format'], inline=True)
                embed.add_field(name="Adaptasi", value=data['source_fmt'], inline=True)
                embed.add_field(name="Sinopsis", value=data['synopsis'], inline=False)

                await self.bot.clear_reactions(msg)
                msg = await self.bot.edit_message(msg, embed=embed)
            elif '⏩' in str(res.reaction.emoji):
                num = num + 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212d)

                embed.set_thumbnail(url=data['poster_img'])
                embed.set_author(name=data['title'], url=data['link'], icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png")
                embed.set_footer(text=data['footer'])

                embed.add_field(name="Nama Lain", value=data['title_other'], inline=True)
                embed.add_field(name="Chapter/Volume", value=data['ch_vol'], inline=True)
                embed.add_field(name="Status", value=data['status'], inline=True)
                embed.add_field(name="Skor", value=data['score'], inline=True)
                embed.add_field(name="Rilis", value=data['start_date'], inline=True)
                embed.add_field(name="Berakhir", value=data['end_date'], inline=True)
                embed.add_field(name="Format", value=data['format'], inline=True)
                embed.add_field(name="Adaptasi", value=data['source_fmt'], inline=True)
                embed.add_field(name="Sinopsis", value=data['synopsis'], inline=False)

                await self.bot.clear_reactions(msg)
                msg = await self.bot.edit_message(msg, embed=embed)
            elif '✅' in str(res.reaction.emoji):
                await self.bot.delete_message(ctx.message)
                return await self.bot.delete_message(msg)

