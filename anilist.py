# -*- coding: utf-8 -*-
#!/usr/bin/env python3
import discord
import discord.ext.commands as commands

import asyncio
import time
import aiohttp
from datetime import datetime, timedelta

def setup(bot):
    bot.add_cog(Anilist(bot))

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
            }
            coverImage {
                large
            }
            averageScore
            volumes
            episodes
            status
            genres
            description
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

async def alistAnimu(title, num=1):
    num = num - 1
    variables = {
        'search': title,
        'page': 1,
        'perPage': 50
    }
    api_link = 'https://graphql.anilist.co'
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_link, json={'query': anilist_query % ('ANIME'), 'variables': variables}) as r:
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
                    entry = data['data']['Page']['media'][num]
                except IndexError:
                    return "ERROR: Tidak ada hasil."
        except session.ClientError:
            return "ERROR: Koneksi terputus"
        
        dataLen = data['data']['Page']['pageInfo']['total']

        sY = entry['startDate']['year']
        if sY is None:
            start = 'Belum Rilis'
        else:
            start = '{}'.format(str(sY))
            sM = entry['startDate']['month']
            if sM is None:
                start = start
            else:
                start = '{}/{}'.format(start,str(sM))
                sD = entry['startDate']['day']
                if sD is None:
                    start = start
                else:
                    start = '{}/{}'.format(start,str(sD))

        eY = entry['endDate']['year']
        if eY is None:
            end = 'Belum Selesai'
        else:
            end = '{}'.format(str(eY))
            eM = entry['endDate']['month']
            if eM is None:
                end = end
            else:
                end = '{}/{}'.format(end,str(eM))
                eD = entry['endDate']['day']
                if eD is None:
                    end = end
                else:
                    end = '{}/{}'.format(end,str(eD))

        title = entry['title']['romaji']
        ani_id = str(entry['id'])

        epTotal = str(entry["episodes"])
        rate = entry['averageScore']
        if rate is None:
            rate = 'None'
        else:
            rate = int(rate)/10
        
        status = str(entry["status"]).lower().capitalize()

        synop = str(entry['description'])
        synop = synop.replace("<br>", ' ')

        genre = entry['genres']
        genres = ', '.join(genre).lower()

        img = str(entry['coverImage']['large'])
        
        aniID = str(entry['id'])
        aniLink = 'https://anilist.co/anime/{}'.format(aniID)
        print('GOT EVERYSHIT UWU')

        if status == 'Releasing' or status == "Not_yet_released":
            nextEp = entry['nextAiringEpisode']
            if not nextEp:
                return (title, epTotal, status.replace('_', ' '), rate, start, end, img, synop, "ID: {} | {}".format(ani_id, genres), aniLink, dataLen)
            airingDate = nextEp['airingAt']
            deltaAirDate = timedelta(seconds=int(airingDate))
            timeTuple = datetime(1,1,1) + deltaAirDate
            timeremain = nextEp['timeUntilAiring']
            nextUp = nextEp['episode']
            consYear = time.strftime('%Y')
            airingDate = f'{timeTuple.day} {monthintext(timeTuple.month)} {consYear}'
            remainTime = create_time_format(timeremain)
            return (title, epTotal, status.replace('_', ' '), rate, start, end, img, synop, "ID: {} | {}".format(ani_id, genres), aniLink, dataLen, nextUp, airingDate, remainTime)
        else:
            return (title, epTotal, status.replace('_', ' '), rate, start, end, img, synop, "ID: {} | {}".format(ani_id, genres), aniLink, dataLen)

async def alistMango(title, num=1):
    num = num - 1
    variables = {
        'search': title,
        'page': 1,
        'perPage': 50
    }
    api_link = 'https://graphql.anilist.co'
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_link, json={'query': anilist_query % ('MANGA'), 'variables': variables}) as r:
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
                    entry = data['data']['Page']['media'][num]
                except IndexError:
                    return "ERROR: Tidak ada hasil."
        except session.ClientError:
            return "ERROR: Koneksi terputus"

        dataLen = len(data['data']['Page']['media'])

        sY = entry['startDate']['year']
        if sY is None:
            start = 'Belum Rilis'
        else:
            start = '{}'.format(str(sY))
            sM = entry['startDate']['month']
            if sM is None:
                start = start
            else:
                start = '{}/{}'.format(start,str(sM))
                sD = entry['startDate']['day']
                if sD is None:
                    start = start
                else:
                    start = '{}/{}'.format(start,str(sD))

        eY = entry['endDate']['year']
        if eY is None:
            end = 'Belum Selesai'
        else:
            end = '{}'.format(str(eY))
            eM = entry['endDate']['month']
            if eM is None:
                end = end
            else:
                end = '{}/{}'.format(end,str(eM))
                eD = entry['endDate']['day']
                if eD is None:
                    end = end
                else:
                    end = '{}/{}'.format(end,str(eD))

        title = entry['title']['romaji']

        volumes = entry['volumes']
        rate = entry['averageScore']
        if rate is None:
            rate = 'None'
        else:
            rate = int(rate)/10
        status = str(entry["status"]).lower().capitalize()
        synop = str(entry['description'])

        genre = entry['genres']
        genres = ', '.join(genre).lower()

        img = str(entry['coverImage']['large'])
        
        ani_id = str(entry['id'])
        aniLink = 'https://anilist.co/manga/{}'.format(ani_id)

        finalResult = {"title": title, 'status': status, 'volume': volumes,'score': rate, 'startDate': start, 'endDate': end, 'posterImg': img, 'synopsis': synop, 'genre': "ID: {} | {}".format(ani_id, genres), 'link': aniLink, 'dataLength': dataLen}
        return finalResult

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
    async def anime(self, ctx, *, judulAnime):
        """Search anime info via anilist.co."""
        init = await alistAnimu(judulAnime, 1)
        if type(init) is str:
            await self.bot.say(init)
            return 'No result'
        else:
            pass

        maxPage = init[10]
        firstRun = True
        time_table = False
        num = 1
        while True:
            #(title, epTotal, status, rate, start, end, img, synop, genres, aniLink, nextUp, airingDate, remainTime, dataLen)
            if firstRun:
                firstRun = False
                num = 1
                find = await alistAnimu(judulAnime, num)
                title = '[{}]({})'.format(find[0], find[9])
                embed=discord.Embed(title="Anime Info", color=0x81e28d)
                embed.set_image(url=find[6])
                embed.add_field(name='Judul', value=title, inline=False)
                embed.add_field(name='Episode', value=find[1], inline=True)
                embed.add_field(name='Status', value=find[2], inline=True)
                embed.add_field(name='Skor', value=find[3], inline=True)
                embed.add_field(name='Tanggal Mulai', value=find[4], inline=True)
                embed.add_field(name='Tanggal Berakhir', value=find[5], inline=True)
                embed.set_footer(text=find[8])
                try:
                    embed.add_field(name='Deskripsi', value=find[7], inline=False)
                    two_part = False
                    msg = await self.bot.say(embed=embed)
                except discord.errors.HTTPException:
                    fmtSyn = '```{}```'.format(str(find[7]))
                    embed.remove_field(-1)
                    two_part = True
                    msg = await self.bot.say(embed=embed)
                    msg2 = await self.bot.say(fmtSyn)

            if str(find[2]) == 'Releasing' and time_table == True and len(find) != 11 or str(find[2]) == 'Not yet released' and time_table == True and len(find) != 11:
                toReact = ['👍', '✅']
            elif maxPage == 1 and num == 1:
                if str(find[2]) == 'Releasing' and time_table == False and len(find) != 11 or str(find[2]) == 'Not yet released' and time_table == False and len(find) != 11:
                    toReact = ['⏳', '✅']
                else:
                    toReact = ['✅']
            elif num == 1:
                if str(find[2]) == 'Releasing' and time_table == False and len(find) != 11 or str(find[2]) == 'Not yet released' and time_table == False and len(find) != 11:
                    toReact = ['⏩', '⏳', '✅']
                else:
                    toReact = ['⏩', '✅']
            elif num == maxPage:
                if str(find[2]) == 'Releasing' and time_table == False and len(find) != 11 and time_table == False and len(find) != 11 or str(find[2]) == 'Not yet released' and time_table == False and len(find) != 11:
                    toReact = ['⏪', '⏳', '✅']
                else:
                    toReact = ['⏪', '✅']
            elif num > 1 and num < maxPage:
                if str(find[2]) == 'Releasing' and time_table == False and len(find) != 11 or str(find[2]) == 'Not yet released' and time_table == False and len(find) != 11:
                    toReact = ['⏪', '⏩', '⏳', '✅']
                else:
                    toReact = ['⏪', '⏩', '✅']
            for reaction in toReact:
                if two_part:
                    await self.bot.add_reaction(msg2, reaction)
                else:
                    await self.bot.add_reaction(msg, reaction)
            #feel free to change ✅ to 🆗 or the opposite
            def checkReaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(('⏪', '⏩', '✅', '⏳', '👍'))

            if two_part:
                res = await self.bot.wait_for_reaction(message=msg2, user=ctx.message.author, timeout=30, check=checkReaction)
            else:
                res = await self.bot.wait_for_reaction(message=msg, user=ctx.message.author, timeout=30, check=checkReaction)
            if res is None:
                if two_part:
                    await self.bot.clear_reactions(msg2)
                else:
                    await self.bot.clear_reactions(msg)
                return
            elif '⏪' in str(res.reaction.emoji):
                num = num - 1
                time_table = False
                find = await alistAnimu(judulAnime, num)
                title = '[{}]({})'.format(find[0], find[9])
                embed=discord.Embed(title="Anime Info", color=0x81e28d)
                embed.set_image(url=find[6])
                embed.add_field(name='Judul', value=title, inline=False)
                embed.add_field(name='Episode', value=find[1], inline=True)
                embed.add_field(name='Status', value=find[2], inline=True)
                embed.add_field(name='Skor', value=find[3], inline=True)
                embed.add_field(name='Tanggal Mulai', value=find[4], inline=True)
                embed.add_field(name='Tanggal Berakhir', value=find[5], inline=True)
                embed.set_footer(text=find[8])
                fmtSyn = '```{}```'.format(str(find[7]))
                try:
                    embed.add_field(name='Deskripsi', value=find[7], inline=False)
                    if two_part:
                        await self.bot.delete_message(msg2)
                    else:
                        await self.bot.clear_reactions(msg)
                    two_part = False
                    msg = await self.bot.edit_message(msg, embed=embed)
                except discord.errors.HTTPException:
                    fmtSyn = '```{}```'.format(str(find[7]))
                    embed.remove_field(-1)
                    if two_part:
                        await self.bot.clear_reactions(msg2)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.edit_message(msg2, fmtSyn)
                    else:
                        await self.bot.clear_reactions(msg)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.say(fmtSyn)
                    two_part = True
            elif '⏩' in str(res.reaction.emoji):
                num = num + 1
                time_table = False
                find = await alistAnimu(judulAnime, num)
                title = '[{}]({})'.format(find[0], find[9])
                embed=discord.Embed(title="Anime Info", color=0x81e28d)
                embed.set_image(url=find[6])
                embed.add_field(name='Judul', value=title, inline=False)
                embed.add_field(name='Episode', value=find[1], inline=True)
                embed.add_field(name='Status', value=find[2], inline=True)
                embed.add_field(name='Skor', value=find[3], inline=True)
                embed.add_field(name='Tanggal Mulai', value=find[4], inline=True)
                embed.add_field(name='Tanggal Berakhir', value=find[5], inline=True)
                embed.set_footer(text=find[8])
                try:
                    embed.add_field(name='Deskripsi', value=find[7], inline=False)
                    if two_part:
                        await self.bot.delete_message(msg2)
                    else:
                        await self.bot.clear_reactions(msg)
                    msg = await self.bot.edit_message(msg, embed=embed)
                    two_part = False
                except discord.errors.HTTPException:
                    fmtSyn = '```{}```'.format(str(find[7]))
                    embed.remove_field(-1)
                    if two_part:
                        await self.bot.clear_reactions(msg2)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.edit_message(msg2, fmtSyn)
                    else:
                        await self.bot.clear_reactions(msg)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.say(fmtSyn)
                    two_part = True
            elif '👍' in str(res.reaction.emoji):
                time_table = False
                title = '[{}]({})'.format(find[0], find[9])
                embed=discord.Embed(title="Anime Info", color=0x81e28d)
                embed.set_image(url=find[6])
                embed.add_field(name='Judul', value=title, inline=False)
                embed.add_field(name='Episode', value=find[1], inline=True)
                embed.add_field(name='Status', value=find[2], inline=True)
                embed.add_field(name='Skor', value=find[3], inline=True)
                embed.add_field(name='Tanggal Mulai', value=find[4], inline=True)
                embed.add_field(name='Tanggal Berakhir', value=find[5], inline=True)
                embed.set_footer(text=find[8])
                try:
                    embed.add_field(name='Deskripsi', value=find[7], inline=False)
                    if two_part:
                        await self.bot.delete_message(msg2)
                    else:
                        await self.bot.clear_reactions(msg)
                    msg = await self.bot.edit_message(msg, embed=embed)
                    two_part = False
                except discord.errors.HTTPException:
                    fmtSyn = '```{}```'.format(str(find[7]))
                    embed.remove_field(-1)
                    if two_part:
                        await self.bot.clear_reactions(msg2)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.edit_message(msg2, fmtSyn)
                    else:
                        await self.bot.clear_reactions(msg)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.say(fmtSyn)
                    two_part = True
            elif '⏳' in str(res.reaction.emoji):
                time_table = True
                find = await alistAnimu(judulAnime, num)
                epiTxt = 'Episode ' + str(find[11])
                fmtFooter = f'Akan tayang pada {find[12]}'
                embed=discord.Embed(title=find[0], color=0x81e28d)
                embed.add_field(name=epiTxt, value=str(find[13]), inline=False)
                embed.set_footer(text=fmtFooter)
                if two_part:
                    await self.bot.delete_message(msg2)
                else:
                    await self.bot.clear_reactions(msg)
                msg = await self.bot.edit_message(msg, embed=embed)
                two_part = False
            elif '✅' in str(res.reaction.emoji):
                await self.bot.delete_message(ctx.message)
                if two_part:
                    await self.bot.delete_message(msg2)
                await self.bot.delete_message(msg)
                break


    @commands.command(pass_context=True, aliases=['komik', 'mango'])
    async def manga(self, ctx, *, title):
        """Search manga info via anilist.co."""
        init = await alistMango(title, 1)
        if type(init) is str:
            await self.bot.say(init)
            return 'No result'
        else:
            pass

        maxPage = int(init['dataLength'])
        firstRun = True
        while True:
            if firstRun:
                firstRun = False
                num = 1
                find = await alistMango(title, num)
                embed=discord.Embed(title="Anime Info", url=find['link'], color=0x81e28d)
                embed.set_image(url=find['posterImg'])
                embed.add_field(name='Judul', value=find['title'], inline=False)
                embed.add_field(name='Volume', value=find['volume'], inline=True)
                embed.add_field(name='Status', value=find['status'], inline=True)
                embed.add_field(name='Skor', value=find['score'], inline=True)
                embed.add_field(name='Tanggal Mulai', value=find['startDate'], inline=True)
                embed.add_field(name='Tanggal Berakhir', value=find['endDate'], inline=True)
                embed.set_footer(text=find['genre'])
                try:
                    embed.add_field(name='Deskripsi', value=find['synopsis'], inline=False)
                    two_part = False
                    msg = await self.bot.say(embed=embed)
                except:
                    fmtSyn = '```{}```'.format(find['synopsis'])
                    two_part = True
                    msg = await self.bot.say(embed=embed)
                    msg2 = await self.bot.say(fmtSyn)

            if maxPage == 1 and num == 1:
                toReact = ['✅']
            elif num == 1:
                toReact = ['⏩', '✅']
            elif num == maxPage:
                toReact = ['⏪', '✅']
            elif num > 1 and num < maxPage:
                toReact = ['⏪', '⏩', '✅']
            for reaction in toReact:
                if two_part:
                    await self.bot.add_reaction(msg2, reaction)
                else:
                    await self.bot.add_reaction(msg, reaction)
            #feel free to change ✅ to 🆗 or the opposite
            def checkReaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(('⏪', '⏩', '✅'))

            if two_part:
                res = await self.bot.wait_for_reaction(message=msg2, user=ctx.message.author, timeout=30, check=checkReaction)
            else:
                res = await self.bot.wait_for_reaction(message=msg, user=ctx.message.author, timeout=30, check=checkReaction)
            if res is None:
                break
            elif '⏪' in str(res.reaction.emoji):
                num = num - 1
                find = await alistMango(title, num)
                embed=discord.Embed(title="Anime Info", url=find['link'], color=0x81e28d)
                embed.set_image(url=find['posterImg'])
                embed.add_field(name='Judul', value=find['title'], inline=False)
                embed.add_field(name='Volume', value=find['volume'], inline=True)
                embed.add_field(name='Status', value=find['status'], inline=True)
                embed.add_field(name='Skor', value=find['score'], inline=True)
                embed.add_field(name='Tanggal Mulai', value=find['startDate'], inline=True)
                embed.add_field(name='Tanggal Berakhir', value=find['endDate'], inline=True)
                embed.set_footer(text=find['genre'])
                try:
                    embed.add_field(name='Deskripsi', value=find['synopsis'], inline=False)
                    if two_part:
                        await self.bot.delete_message(msg2)
                        await self.bot.clear_reactions(msg2)
                    else:
                        await self.bot.clear_reactions(msg)
                    two_part = False
                    msg = await self.bot.edit_message(msg, embed=embed)
                except:
                    fmtSyn = '```{}```'.format(find['synopsis'])
                    if two_part:
                        await self.bot.clear_reactions(msg2)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.edit_message(msg2, fmtSyn)
                    else:
                        await self.bot.clear_reactions(msg)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.say(fmtSyn)
                    two_part = True
            elif '⏩' in str(res.reaction.emoji):
                num = num + 1
                find = await alistMango(title, num)
                embed=discord.Embed(title="Anime Info", url=find['link'], color=0x81e28d)
                embed.set_image(url=find['posterImg'])
                embed.add_field(name='Judul', value=find['title'], inline=False)
                embed.add_field(name='Volume', value=find['volume'], inline=True)
                embed.add_field(name='Status', value=find['status'], inline=True)
                embed.add_field(name='Skor', value=find['score'], inline=True)
                embed.add_field(name='Tanggal Mulai', value=find['startDate'], inline=True)
                embed.add_field(name='Tanggal Berakhir', value=find['endDate'], inline=True)
                embed.set_footer(text=find['genre'])
                try:
                    embed.add_field(name='Deskripsi', value=find['synopsis'], inline=False)
                    if two_part:
                        await self.bot.delete_message(msg2)
                        await self.bot.clear_reactions(msg2)
                    else:
                        await self.bot.clear_reactions(msg)
                    two_part = False
                    msg = await self.bot.edit_message(msg, embed=embed)
                except:
                    fmtSyn = '```{}```'.format(find['synopsis'])
                    if two_part:
                        await self.bot.clear_reactions(msg2)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.edit_message(msg2, fmtSyn)
                    else:
                        await self.bot.clear_reactions(msg)
                        msg = await self.bot.edit_message(msg, embed=embed)
                        msg2 = await self.bot.say(fmtSyn)
                    two_part = True
            elif '✅' in str(res.reaction.emoji):
                await self.bot.delete_message(ctx.message)
                if two_part:
                    await self.bot.delete_message(msg2)
                await self.bot.delete_message(msg)
                break

