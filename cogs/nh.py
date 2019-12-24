# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import json
import os

import aiohttp
import discord
import discord.ext.commands as commands
from datetime import datetime

def setup(bot):
    bot.add_cog(nHController(bot))

async def nsfw_channel(ctx):
    if ctx.guild:
        return ctx.channel.is_nsfw()
    raise commands.NoPrivateMessage('Perintah tidak bisa dipakai di private message.')

class NotNSFWChannel(Exception):
    pass

class nHController(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['nh'])
    @commands.check(nsfw_channel)
    async def nhi(self, ctx):
        if not ctx.invoked_subcommand:
            helpmain = discord.Embed(title="Bantuan Perintah (!nh)", description="versi 2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='!nh', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!nh cari <query>', value="```Mencari kode nuklir.```", inline=False)
            helpmain.add_field(name='!nh info <kode>', value="```Melihat informasi kode nuklir.```", inline=False)
            helpmain.add_field(name='!nh baca <kode>', value="```Membaca langsung kode nuklir.```", inline=False)
            helpmain.add_field(name='!nh unduh <kode>', value="```Mendownload kode nuklir dan dijadikan .zip file (limit file adalah 3 hari sebelum dihapus dari server).```", inline=False)
            helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)


    @nhi.command(aliases=['search'])
    async def cari(self, ctx, *, query):
        message = await ctx.send('Memulai proses pencarian, mohon tunggu.')
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get('https://s.ihateani.me/api/search?q={}'.format(query)) as resp:
                try:
                    response = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError as cterr:
                    return await ctx.send('Terjadi kesalahan ketika menghubungi server.')
                if resp.status != 200:
                    return await ctx.send('Tidak dapat menemukan apa-apa dengan kata tersebut.')

        await message.edit(content='Pencarian didapatkan.')

        #print(response)
        resdata = response['results']
        max_page = len(resdata)

        first_run = True
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                embed = discord.Embed(title="Pencarian: {}".format(query), color=0x1f1f1f, url=data['url'])
                embed.set_footer(text='Kode: {} | Diprakasai oleh s.ihateani.me'.format(data['nuke_code']))
                embed.description = '**{}**'.format(data['title'])
                embed.set_image(url=data['cover'])

                first_run = False
                msg = await ctx.send(embed=embed)
                await message.delete()

            reactmoji = []
            if max_page == 1 and num == 1:
                pass
            elif num == 1:
                reactmoji.append('⏩')
            elif num == max_page:
                reactmoji.append('⏪')
            elif num > 1 and num < max_page:
                reactmoji.extend(['⏪', '⏩'])
            reactmoji.append('\N{INFORMATION SOURCE}')
            reactmoji.append('✅')
            for reaction in reactmoji:
                await msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
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
                await msg.clear_reactions()
                await ctx.message.delete()
                return await msg.delete()
            elif '⏪' in str(res.emoji):
                num = num - 1
                data = resdata[num - 1]

                embed = discord.Embed(title="Pencarian: {}".format(query), color=0x1f1f1f, url=data['url'])
                embed.set_footer(text='Kode: {} | Diprakasai oleh s.ihateani.me'.format(data['nuke_code']))
                embed.description = '**{}**'.format(data['title'])
                embed.set_image(url=data['cover'])

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif '⏩' in str(res.emoji):
                num = num + 1
                data = resdata[num - 1]

                embed = discord.Embed(title="Pencarian: {}".format(query), color=0x1f1f1f, url=data['url'])
                embed.set_footer(text='Kode: {} | Diprakasai oleh s.ihateani.me'.format(data['nuke_code']))
                embed.description = '**{}**'.format(data['title'])
                embed.set_image(url=data['cover'])

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif '\u2139' in str(res.emoji):
                message = await ctx.send('Memulai proses pengumpulan informasi, mohon tunggu.')
                async with aiohttp.ClientSession() as sesi:
                    async with sesi.get('https://s.ihateani.me/api/info/{}'.format(data['nuke_code'])) as resp:
                        data2 = await resp.json()

                await message.delete()
                await msg.clear_reactions()
                first_run_2 = True
                TAG_TRANSLATION = {
                    'parodies': ':nut_and_bolt: Parodi',
                    'characters': ':nut_and_bolt: Karakter',
                    'tags': ':nut_and_bolt: Label',
                    'artists': ':nut_and_bolt: Seniman',
                    'groups': ':nut_and_bolt: Circle/Grup',
                    'languages': ':nut_and_bolt: Bahasa',
                    'categories': ':nut_and_bolt: Kategori'
                }
                download_text_open = False
                while True:
                    reactmoji2 = []
                    if not download_text_open:
                        reactmoji2.append('\N{OPEN BOOK}') # Read
                        reactmoji2.append('\N{INBOX TRAY}') # Down
                    reactmoji2.append('✅') # Back

                    if first_run_2:
                        embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                        for tag in data2['tags'].keys():
                            if data2['tags'][tag]:
                                tag_parsed = [aaa[0].capitalize() for aaa in data2['tags'][tag]]
                                embed.add_field(name=TAG_TRANSLATION[tag], value=', '.join(tag_parsed))
                        embed.add_field(name=':nut_and_bolt: Total Halaman', value='{} halaman'.format(data2['total_pages']))
                        embed.set_footer(text='Favorit: {} | Diprakasai oleh s.ihateani.me'.format(data2['favorites']))
                        embed.set_image(url=data2['cover'])

                        first_run_2 = False
                        await msg.edit(embed=embed)

                    for reaction in reactmoji2:
                        await msg.add_reaction(reaction)

                    def check_react2(reaction, user):
                        if reaction.message.id != msg.id:
                            return False
                        if user != ctx.message.author:
                            return False
                        if str(reaction.emoji) not in reactmoji2:
                            return False
                        return True

                    res2, user2 = await self.bot.wait_for('reaction_add', check=check_react2)
                    if user2 != ctx.message.author:
                        pass
                    elif '✅' in str(res2.emoji):
                        await msg.clear_reactions()
                        if not download_text_open:
                            embed = discord.Embed(title="Pencarian: {}".format(query), color=0x1f1f1f, url=data['url'])
                            embed.set_footer(text='Kode: {} | Diprakasai oleh s.ihateani.me'.format(data['nuke_code']))
                            embed.description = '**{}**'.format(data['title'])
                            embed.set_image(url=data['cover'])

                            await msg.edit(embed=embed)
                            break
                        else:
                            embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                            for tag in data2['tags'].keys():
                                if data2['tags'][tag]:
                                    tag_parsed = [aaa[0].capitalize() for aaa in data2['tags'][tag]]
                                    embed.add_field(name=TAG_TRANSLATION[tag], value=', '.join(tag_parsed))
                            embed.add_field(name=':nut_and_bolt: Total Halaman', value='{} halaman'.format(data2['total_pages']))
                            embed.set_footer(text='Favorit: {} | Diprakasai oleh s.ihateani.me'.format(data2['favorites']))
                            embed.set_image(url=data2['cover'])

                            await msg.edit(embed=embed)
                            download_text_open = False
                    elif '\N{INBOX TRAY}' in str(res2.emoji): # Download
                        embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                        embed.description = 'Klik link dibawah ini untuk mendownload\n<https://s.ihateani.me/unduh?id={}>\n\nJika gambar banyak, akan memakan waktu lebih lama ketika proses sebelum download.'.format(data['nuke_code'])
                        embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                        embed.set_thumbnail(url=data['cover'])

                        download_text_open = True
                        await msg.clear_reactions()
                        await msg.edit(embed=embed)
                    elif '\N{OPEN BOOK}' in str(res2.emoji): # Download
                        page_total = data2['total_pages']
                        time_calc = ((page_total / 5) * ((300 * 5) + 1000)) // 1000 + 5

                        message = await ctx.send('Memulai proses proxy gambar, mohon tunggu.\n(Akan memakan waktu **±{}** detik jika belum pernah di cache.)'.format(time_calc))
                        async with aiohttp.ClientSession() as sesi:
                            async with sesi.get('https://s.ihateani.me/api/mirror/{}'.format(data['nuke_code'])) as resp:
                                data3 = await resp.json()

                        await message.delete()
                        await msg.clear_reactions()

                        dataset_img = data3['proxied_images']
                        dataset_total = len(dataset_img)
                        first_run_3 = True
                        pospos = 1
                        while True:
                            if first_run_3:
                                img_link = dataset_img[pospos - 1]

                                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                                embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                                embed.set_image(url=img_link)
                                embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                                first_run_3 = False
                                await msg.edit(embed=embed)

                            reactmoji3 = []
                            if dataset_total < 2:
                                break
                            elif pospos == 1:
                                reactmoji3 = ['⏩']
                            elif dataset_total == pospos:
                                reactmoji3 = ['⏪']
                            elif pospos > 1 and pospos < dataset_total:
                                reactmoji3 = ['⏪', '⏩']
                            reactmoji3.append('✅')
                            for reaction in reactmoji3:
                                await msg.add_reaction(reaction)

                            def check_react3(reaction, user):
                                if reaction.message.id != msg.id:
                                    return False
                                if user != ctx.message.author:
                                    return False
                                if str(reaction.emoji) not in reactmoji3:
                                    return False
                                return True

                            res3, user3 = await self.bot.wait_for('reaction_add', check=check_react3)
                            if user3 != ctx.message.author:
                                pass
                            if '✅' in str(res3.emoji):
                                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                                for tag in data2['tags'].keys():
                                    if data2['tags'][tag]:
                                        tag_parsed = [aaa[0].capitalize() for aaa in data2['tags'][tag]]
                                        embed.add_field(name=TAG_TRANSLATION[tag], value=', '.join(tag_parsed))
                                embed.add_field(name=':nut_and_bolt: Total Halaman', value='{} halaman'.format(data2['total_pages']))
                                embed.set_footer(text='Favorit: {} | Diprakasai oleh s.ihateani.me'.format(data2['favorites']))
                                embed.set_image(url=data2['cover'])

                                await msg.clear_reactions()
                                await msg.edit(embed=embed)
                                break
                            elif '⏪' in str(res3.emoji):
                                pospos = pospos - 1
                                img_link = dataset_img[pospos - 1]

                                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                                embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                                embed.set_image(url=img_link)
                                embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                                await msg.clear_reactions()
                                await msg.edit(embed=embed)
                            elif '⏩' in str(res3.emoji):
                                pospos = pospos + 1
                                img_link = dataset_img[pospos - 1]

                                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                                embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                                embed.set_image(url=img_link)
                                embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                                await msg.clear_reactions()
                                await msg.edit(embed=embed)


    @nhi.command(aliases=['informasi'])
    async def info(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send('Masukan kode nuklir yang benar.')

        message = await ctx.send('Memulai proses pengumpulan informasi, mohon tunggu.')
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get('https://s.ihateani.me/api/info/{}'.format(kode_nuklir)) as resp:
                try:
                    data2 = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError as cterr:
                    return await ctx.send('Terjadi kesalahan ketika menghubungi server.')
                if resp.status != 200:
                    return await ctx.send('Tidak dapat menemukan apa-apa dengan kata tersebut.')

        await message.delete()
        first_run_2 = True
        TAG_TRANSLATION = {
            'parodies': ':nut_and_bolt: Parodi',
            'characters': ':nut_and_bolt: Karakter',
            'tags': ':nut_and_bolt: Label',
            'artists': ':nut_and_bolt: Seniman',
            'groups': ':nut_and_bolt: Circle/Grup',
            'languages': ':nut_and_bolt: Bahasa',
            'categories': ':nut_and_bolt: Kategori'
        }
        data2['url'] = 'https://nhentai.net/g/' + kode_nuklir
        download_text_open = False
        while True:
            reactmoji2 = []
            if not download_text_open:
                reactmoji2.append('\N{OPEN BOOK}') # Read
                reactmoji2.append('\N{INBOX TRAY}') # Down
            reactmoji2.append('✅') # Back

            if first_run_2:
                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                for tag in data2['tags'].keys():
                    if data2['tags'][tag]:
                        tag_parsed = [aaa[0].capitalize() for aaa in data2['tags'][tag]]
                        embed.add_field(name=TAG_TRANSLATION[tag], value=', '.join(tag_parsed))
                embed.add_field(name=':nut_and_bolt: Total Halaman', value='{} halaman'.format(data2['total_pages']))
                embed.set_footer(text='Favorit: {} | Diprakasai oleh s.ihateani.me'.format(data2['favorites']))
                embed.set_image(url=data2['cover'])

                first_run_2 = False
                msg = await ctx.send(embed=embed)

            for reaction in reactmoji2:
                await msg.add_reaction(reaction)

            def check_react2(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji2:
                    return False
                return True

            res2, user2 = await self.bot.wait_for('reaction_add', check=check_react2)
            if user2 != ctx.message.author:
                pass
            elif '✅' in str(res2.emoji):
                await msg.clear_reactions()
                if not download_text_open:
                    await ctx.message.delete()
                    return await msg.delete()
                else:
                    embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                    for tag in data2['tags'].keys():
                        if data2['tags'][tag]:
                            tag_parsed = [aaa[0].capitalize() for aaa in data2['tags'][tag]]
                            embed.add_field(name=TAG_TRANSLATION[tag], value=', '.join(tag_parsed))
                    embed.add_field(name=':nut_and_bolt: Total Halaman', value='{} halaman'.format(data2['total_pages']))
                    embed.set_footer(text='Favorit: {} | Diprakasai oleh s.ihateani.me'.format(data2['favorites']))
                    embed.set_image(url=data2['cover'])

                    await msg.edit(embed=embed)
                    download_text_open = False
            elif '\N{INBOX TRAY}' in str(res2.emoji): # Download
                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                embed.description = 'Klik link dibawah ini untuk mendownload\n<https://s.ihateani.me/unduh?id={}>\n\nJika gambar banyak, akan memakan waktu lebih lama ketika proses sebelum download.'.format(kode_nuklir)
                embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                embed.set_thumbnail(url=data2['cover'])

                download_text_open = True
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif '\N{OPEN BOOK}' in str(res2.emoji): # Download
                page_total = data2['total_pages']
                time_calc = ((page_total / 5) * ((300 * 5) + 1000)) // 1000 + 5

                message = await ctx.send('Memulai proses proxy gambar, mohon tunggu.\n(Akan memakan waktu **±{}** detik jika belum pernah di cache.)'.format(time_calc))
                async with aiohttp.ClientSession() as sesi:
                    async with sesi.get('https://s.ihateani.me/api/mirror/{}'.format(kode_nuklir)) as resp:
                        data3 = await resp.json()

                await message.delete()
                await msg.clear_reactions()

                dataset_img = data3['proxied_images']
                dataset_total = len(dataset_img)
                first_run_3 = True
                pospos = 1
                while True:
                    if first_run_3:
                        img_link = dataset_img[pospos - 1]

                        embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                        embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                        embed.set_image(url=img_link)
                        embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                        first_run_3 = False
                        await msg.edit(embed=embed)

                    reactmoji3 = []
                    if dataset_total < 2:
                        break
                    elif pospos == 1:
                        reactmoji3 = ['⏩']
                    elif dataset_total == pospos:
                        reactmoji3 = ['⏪']
                    elif pospos > 1 and pospos < dataset_total:
                        reactmoji3 = ['⏪', '⏩']
                    reactmoji3.append('✅')
                    for reaction in reactmoji3:
                        await msg.add_reaction(reaction)

                    def check_react3(reaction, user):
                        if reaction.message.id != msg.id:
                            return False
                        if user != ctx.message.author:
                            return False
                        if str(reaction.emoji) not in reactmoji3:
                            return False
                        return True

                    res3, user3 = await self.bot.wait_for('reaction_add', check=check_react3)
                    if user3 != ctx.message.author:
                        pass
                    elif '✅' in str(res3.emoji):
                        embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                        for tag in data2['tags'].keys():
                            if data2['tags'][tag]:
                                tag_parsed = [aaa[0].capitalize() for aaa in data2['tags'][tag]]
                                embed.add_field(name=TAG_TRANSLATION[tag], value=', '.join(tag_parsed))
                        embed.add_field(name=':nut_and_bolt: Total Halaman', value='{} halaman'.format(data2['total_pages']))
                        embed.set_footer(text='Favorit: {} | Diprakasai oleh s.ihateani.me'.format(data2['favorites']))
                        embed.set_image(url=data2['cover'])

                        await msg.clear_reactions()
                        await msg.edit(embed=embed)
                        break
                    elif '⏪' in str(res3.emoji):
                        pospos = pospos - 1
                        img_link = dataset_img[pospos - 1]

                        embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                        embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                        embed.set_image(url=img_link)
                        embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                        await msg.clear_reactions()
                        await msg.edit(embed=embed)
                    elif '⏩' in str(res3.emoji):
                        pospos = pospos + 1
                        img_link = dataset_img[pospos - 1]

                        embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                        embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                        embed.set_image(url=img_link)
                        embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                        await msg.clear_reactions()
                        await msg.edit(embed=embed)

    @nhi.command(aliases=['down', 'dl', 'download'])
    async def unduh(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send('Masukan kode nuklir yang benar.')

        message = await ctx.send('Memulai proses pengumpulan informasi, mohon tunggu.')
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get('https://s.ihateani.me/api/info/{}'.format(kode_nuklir)) as resp:
                try:
                    data2 = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError as cterr:
                    return await ctx.send('Terjadi kesalahan ketika menghubungi server.')
                if resp.status != 200:
                    return await ctx.send('Tidak dapat menemukan apa-apa dengan kata tersebut.')

        await message.delete()
        data2['url'] = 'https://nhentai.net/g/' + kode_nuklir

        embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
        embed.description = 'Klik link dibawah ini untuk mendownload\n<https://s.ihateani.me/unduh?id={}>\n\nJika gambar banyak, akan memakan waktu lebih lama ketika proses sebelum download.'.format(kode_nuklir)
        embed.set_footer(text='Diprakasai oleh s.ihateani.me')
        embed.set_thumbnail(url=data2['cover'])

        msg = await ctx.send(embed=embed)

        while True:
            reactmoji = ['✅']
            for reaction in reactmoji:
                await msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
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
                await msg.clear_reactions()
                await ctx.message.delete()
                return await msg.delete()

    @nhi.command(aliases=['read'])
    async def baca(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send('Masukan kode nuklir yang benar.')

        message = await ctx.send('Memulai proses pengumpulan informasi, mohon tunggu.')
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get('https://s.ihateani.me/api/info/{}'.format(kode_nuklir)) as resp:
                try:
                    data2 = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError as cterr:
                    return await ctx.send('Terjadi kesalahan ketika menghubungi server.')
                if resp.status != 200:
                    return await ctx.send('Tidak dapat menemukan apa-apa dengan kata tersebut.')

        await message.delete()
        data2['url'] = 'https://nhentai.net/g/' + kode_nuklir
        page_total = data2['total_pages']
        time_calc = ((page_total / 5) * ((300 * 5) + 1000)) // 1000 + 5

        message = await ctx.send('Memulai proses proxy gambar, mohon tunggu.\n(Akan memakan waktu **±{}** detik jika belum pernah di cache.)'.format(time_calc))
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get('https://s.ihateani.me/api/mirror/{}'.format(kode_nuklir)) as resp:
                data3 = await resp.json()

        await message.delete()

        dataset_img = data3['proxied_images']
        dataset_total = len(dataset_img)
        first_run_3 = True
        pospos = 1
        while True:
            if first_run_3:
                img_link = dataset_img[pospos - 1]

                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                embed.set_image(url=img_link)
                embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                first_run_3 = False
                msg = await ctx.send(embed=embed)

            reactmoji3 = []
            if dataset_total < 2:
                break
            elif pospos == 1:
                reactmoji3 = ['⏩']
            elif dataset_total == pospos:
                reactmoji3 = ['⏪']
            elif pospos > 1 and pospos < dataset_total:
                reactmoji3 = ['⏪', '⏩']
            reactmoji3.append('✅')
            for reaction in reactmoji3:
                await msg.add_reaction(reaction)

            def check_react3(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji3:
                    return False
                return True

            res3, user3 = await self.bot.wait_for('reaction_add', check=check_react3)
            if user3 != ctx.message.author:
                pass
            elif '✅' in str(res3.emoji):
                await msg.clear_reactions()
                await ctx.message.delete()
                return await msg.delete()
            elif '⏪' in str(res3.emoji):
                pospos = pospos - 1
                img_link = dataset_img[pospos - 1]

                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                embed.set_image(url=img_link)
                embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif '⏩' in str(res3.emoji):
                pospos = pospos + 1
                img_link = dataset_img[pospos - 1]

                embed = discord.Embed(title=data2['title'], color=0x1f1f1f, url=data2['url'], timestamp=datetime.fromtimestamp(data2['posted_time']))
                embed.description = '{}/{}\n<{}>'.format(pospos, dataset_total, img_link)
                embed.set_image(url=img_link)
                embed.set_footer(text='Diprakasai oleh s.ihateani.me')
                await msg.clear_reactions()
                await msg.edit(embed=embed)


    @nhi.error
    async def nhi_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send('Untuk menggunakan perintah ini, dibutuhkan channel yang sudah diaktifkan mode NSFW-nya.')