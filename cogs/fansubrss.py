import asyncio
import difflib
import json
import os
import re
import time
from calendar import monthrange
from datetime import datetime
from time import mktime
from typing import Any, Tuple

import aiohttp
import discord
import feedparser
from discord.ext import commands, tasks
from markdownify import markdownify as mdparse


async def fetch_json() -> dict:
    """
    Open local database
    """
    print('[@] Opening json file')
    if not os.path.isfile('nao_showtimes.json'):
        print('[@] naoTimes are not initiated, skipping.')
        return {}
    with open('nao_showtimes.json', 'r') as fp:
        json_data = json.load(fp)
    
    return json_data

def filter_data(entries) -> dict:
    """Remove unnecessary tags that just gonna trashed the data"""
    remove_data = ['title_detail', 'links', 'authors', 'author_detail', 'content', 
            'updated', 'guidislink', 'summary_detail', 'comments', 
            'href', 'wfw_commentrss', 'slash_comments', 'media_content']

    for r in remove_data:
        try:
            del entries[r]
        except KeyError:
            pass
    
    if 'tags' in entries:
        try:
            tags = []
            for t in entries['tags']:
                tags.append(t['term'])
            entries['tags'] = tags
        except KeyError:
            entries['tags'] = []

    if 'media_thumbnail' in entries:
        try:
            entries['media_thumbnail'] = entries['media_thumbnail'][0]['url']
        except IndexError:
            entries['media_thumbnail'] = ''
        except KeyError:
            entries['media_thumbnail'] = ''

    if 'summary' in entries:
        entries['summary'] = mdparse(entries['summary'])

    if 'description' in entries:
        entries['description'] = mdparse(entries['description'])

    return entries

async def async_feedparse(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as r:
                r_data = await r.text()
        except session.ClientError:
            return None
    return feedparser.parse(r_data)


async def check_if_valid(url) -> bool:
    feed = await async_feedparse(url)

    if not feed:
        return False

    if not feed.entries:
        return False
    return True


async def parse_message(message, entry_data):
    matches = re.findall(r"(?P<data>{[^{}]+})", message, re.MULTILINE | re.IGNORECASE)
    msg_fmt_data = [m.strip(r'{}') for m in matches]

    for i in msg_fmt_data:
        try:
            message = message.replace('{' + i + '}', entry_data[i])
        except KeyError:
            pass

    return message.replace('\\n', '\n')


def replace_tz(string):
    for i in range(-12, 13):
        string = string.replace('+0{}:00'.format(i), '')
    return string


async def parse_embed(embed_data, entry_data):
    regex_embed = re.compile(r"(?P<data>{[^{}]+})", re.MULTILINE | re.IGNORECASE)

    filtered = {}
    for k, v in embed_data.items():
        if not v:
            continue
        if isinstance(v, bool):
            continue
        matches = re.findall(regex_embed, v)
        msg_fmt = [m.strip(r'{}') for m in matches]
        for i in msg_fmt:
            try:
                if isinstance(entry_data[i], list):
                    entry_data[i] = ', '.join(entry_data[i])
                v = v.replace('{' + i + '}', entry_data[i])
            except KeyError:
                pass
        filtered[k] = v

    if 'color' in filtered:
        if filtered['color'].isdigit():
            filtered['color'] = int(v)
        else:
            filtered['color'] = 16777215

    filtered['type'] = 'rich'
    if 'thumbnail' in filtered:
        ll = {}
        ll['url'] = filtered['thumbnail']
        filtered['thumbnail'] = ll
    if 'image' in filtered:
        ll = {}
        ll['url'] = filtered['image']
        filtered['image'] = ll

    if embed_data['timestamp']:
        try:
            filtered['timestamp'] = replace_tz(entry_data['published_parsed'])
        except:
            filtered['timestamp'] = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if 'footer' in filtered:
        new_f = {}
        new_f['text'] = filtered['footer']
        if 'footer_img' in filtered:
            new_f['icon_url'] = filtered['footer_img']
        del filtered['footer']
        if 'footer_img' in filtered:
            del filtered['footer_img']
        filtered['footer'] = new_f

    print(filtered)
    return filtered


async def recursive_check_feed(url, last):
    feed = await async_feedparse(url)
    if not feed:
        return None

    entries = feed.entries

    filtered_entry = []
    for n, entry in enumerate(entries):
        if entry['title'] == last:
            break
        filtered_entry.append(filter_data(entries[n]))

    return filtered_entry


def write_rss_data(rss_d):
    with open('fansubrss.json', 'w') as fp:
        json.dump(rss_d, fp, indent=4)


def read_rss_data():
    with open('fansubrss.json', 'r') as fp:
        json_d_rss = json.load(fp)
    return json_d_rss


class FansubRSS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_every_feed.start()


    @tasks.loop(minutes=5.0)
    async def check_every_feed(self):
        print('[@] Routine 5 minute checks of fansub rss')
        json_d_rss = read_rss_data()

        for k in json_d_rss.keys():
            print('[@] Checking `{}` feed'.format(k))
            entries = await recursive_check_feed(json_d_rss[k]['feedUrl'], json_d_rss[k]['lastUpdate'])
            if entries:
                channel = self.bot.get_channel(int(json_d_rss[k]['channel']))
                print('Sending result to: #{}'.format(channel))
                for entry in entries[::-1]:
                    if json_d_rss[k]['embed']:
                        embed22 = discord.Embed()
                        msg_format = await parse_message(json_d_rss[k]['message'], entry)
                        msg_emb = await parse_embed(json_d_rss[k]['embed'], entry)
                        embed22 = embed22.from_dict(msg_emb)
                        await channel.send(msg_format, embed=embed22)
                    else:
                        msg_format = await parse_message(json_d_rss[k]['message'], entry)
                        await channel.send(msg_format)
                json_d_rss[k]['lastUpdate'] = entries[0]['title']
                write_rss_data(json_d_rss)
            else:
                print('[@] No new update.')
        print("[@] Finish checking, now sleeping for 5 minutes")

    @check_every_feed.before_loop
    async def wait_until_ready(self):
        await self.bot.wait_until_ready()

    @commands.group(aliases=['rss'])
    @commands.guild_only()
    async def fansubrss(self, ctx):
        if ctx.invoked_subcommand is None:
            helpmain = discord.Embed(title="Bantuan Perintah (!fansubrss)", description="2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='!fansubrss', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!fansubrss aktifkan', value="```Mengaktifkan fansub rss di server ini```", inline=False)
            helpmain.add_field(name='!fansubrss formatpesan', value="```Mem-format pesan yang akan dikirim ke channel yang dipilih.```", inline=False)
            helpmain.add_field(name='!fansubrss formatembed', value="```Menggunakan embed dengan teks dari `formatpesan`.```", inline=False)
            helpmain.add_field(name='!fansubrss terakhir', value="```Melihat feed terakhir yang ada.```", inline=False)
            helpmain.add_field(name='Aliases', value="!fansubrss, !rss", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 2.0.0")
            await ctx.send(embed=helpmain)

    @fansubrss.command(aliases=['terakhir'])
    @commands.guild_only()
    async def lastupdate(self, ctx):
        json_d_rss = read_rss_data()
        server_message = str(ctx.message.guild.id)
        print('Requested !fansubrss lastupdate at: ' + server_message)

        if server_message not in json_d_rss:
            return

        feed = await async_feedparse(json_d_rss[server_message]['feedUrl'])
        if not feed:
            return await ctx.send('Tidak dapat membuat koneksi dengan RSS feed')
        entry = filter_data(feed.entries[0])

        if json_d_rss[server_message]['embed']:
            embed22 = discord.Embed()
            if json_d_rss[server_message]['message']:
                msg_format = await parse_message(json_d_rss[server_message]['message'], entry)
            msg_emb = await parse_embed(json_d_rss[server_message]['embed'], entry)
            embed22 = embed22.from_dict(msg_emb)
            if json_d_rss[server_message]['message']:
                await ctx.send(msg_format, embed=embed22)
            else:
                await ctx.send(embed=embed22)
        else:
            if json_d_rss[server_message]['message']:
                msg_format = await parse_message(json_d_rss[server_message]['message'], entry)
                await ctx.send(msg_format)
            else:
                print('[@] Tidak ada cara untuk mengirimkan pesan.')
                return await ctx.send('Tidak ada cara untuk mengirimkan pesan.')

    @fansubrss.command(aliases=['init'])
    @commands.guild_only()
    async def aktifkan(self, ctx):
        server_message = str(ctx.message.guild.id)
        print('Requested !fansubrss aktifkan at: ' + server_message)
        json_d_rss = read_rss_data()

        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa mengaktifkan rss fansub')

        if server_message in json_d_rss:
            return await ctx.send('RSS telah diaktifkan di server ini.')

        print('Membuat data')
        embed = discord.Embed(title="Fansub RSS", color=0x56acf3)
        embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "channel": "",
            "feedUrl": "",
            "message": r":newspaper: | Rilisan Baru: **{title}**\n{link}",
            "lastUpdate": ""
        }

        async def process_channel(table, emb_msg, author):
            print('[@] Memproses fansub rss channel')
            embed = discord.Embed(title="Fansub RSS", color=0x96df6a)
            embed.add_field(name='Channel', value="Ketik channel id untuk posting rilisan baru.", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            await_msg = await self.bot.wait_for('message', check=lambda m: m.author == author)
            table['channel'] = await_msg.content
            await await_msg.delete()

            return table, emb_msg


        async def process_feed(table, emb_msg, author):
            print('[@] Memproses fansub rss url')
            embed = discord.Embed(title="Fansub RSS", color=0x96df6a)
            embed.add_field(name='Feed URL', value="Ketik url feed xml yang valid.", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for('message', check=lambda m: m.author == author)
                embed.set_field_at(0, name='Feed URL', value="Memvalidasi URL", inline=False)
                await emb_msg.edit(embed=embed)
                if check_if_valid(await_msg):
                    feed = feedparser.parse(await_msg)
                    json_tables['lastUpdate'] = feed.entries[0]['title']
                    break
                else:
                    embed.set_field_at(0, name='Feed URL', value="Gagal memvalidasi URL\nSilakan masukan feed xml yang valid.", inline=False)
                    await emb_msg.edit(embed=embed)
            table['feedUrl'] = await_msg.content
            await await_msg.delete()

            return table, emb_msg

        json_tables, emb_msg = await process_feed(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_channel(json_tables, emb_msg, msg_author)

        print('[@] Making sure.')
        first_time = True
        cancel_toggled = False
        while True:
            embed=discord.Embed(title="Fansub RSS", description="Periksa data!\nReact jika ingin diubah.", color=0xe7e363)
            embed.add_field(name="1⃣ Feed URL", value="{}".format(json_tables['feed']), inline=False)
            embed.add_field(name='2⃣ Channel', value="{}".format(json_tables['channel']), inline=False)
            embed.add_field(name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                emb_msg.edit(embed=embed)

            to_react = ['1⃣', "2⃣", '✅', '❌']
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                return user == ctx.message.author and str(reaction.emoji) in to_react

            res, user = await self.bot.wait_for('reaction_add', check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_feed(json_tables, emb_msg, msg_author)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_channel(json_tables, emb_msg, msg_author)
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
        print(json_tables)
        json_d_rss[server_message] = json_tables

        embed=discord.Embed(title="Fansub RSS", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await emb_msg.edit(emb_msg, embed=embed)

        print("[@] Sending data")

        write_rss_data(json_d_rss)
        print('[@] Sended.')
        embed=discord.Embed(title="Fansub RSS", color=0x96df6a)
        embed.add_field(name="Sukses!", value='Berhasil mengaktifkan RSS.', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)
        await emb_msg.delete()


    @fansubrss.command(aliases=['pesan'])
    @commands.guild_only()
    async def formatpesan(self, ctx):
        server_message = str(ctx.message.guild.id)
        print('Requested !fansubrss formatpesan at: ' + server_message)
        json_d_rss = read_rss_data()

        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]

        if server_message not in json_d_rss:
            return

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return

        feed = await async_feedparse(json_d_rss[server_message]['feedUrl'])
        if not feed:
            return await ctx.send('Tidak dapat membuat koneksi dengan RSS feed')
        entries_data = feed.entries[0]
        entries_data = filter_data(entries_data)

        regex_uri = re.compile(
                r'^(?:http|ftp)s?://' # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
                r'localhost|' #localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
                r'(?::\d+)?' # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        text = 'Ubah format pesan yang akan dikirim:\nYang sekarang: `{}`'.format(json_d_rss[server_message]['message']) + '\n\nContoh data dari RSS ({DATA}: {ISI}):\n'
        for k, v in entries_data.items():
            if isinstance(v, str) and re.match(regex_uri, v):
                v = '<{}>'.format(v)
            text += '`{k}`: {v}\n'.format(k=k, v=v)
        text += '\nKetik `{DATA}` untuk memakai data dari RSS, misalkan ingin memakai judul dari RSS.\nMaka pakai `{title}`'

        msg_ = await ctx.send(text)
        await ctx.send('Ketik pesan yang ingin! (ketik *cancel* untuk membatalkannya, *clear* untuk menghapus pesan yang ada, *reset* untuk menormalkannya kembali)')

        def check(m):
            return m.author == ctx.message.author

        user_input = await self.bot.wait_for('message', check=check)

        if user_input.content == ("cancel"):
            print('[@] Cancelled')
            await msg_.delete()
            return await ctx.send('**Dibatalkan.**')

        if user_input.content == ("clear"):
            await msg_.delete()
            json_d_rss[server_message]['message'] = None
            write_rss_data(json_d_rss)
            return await ctx.send('Berhasil menghapus pesan.')

        if user_input.content == ("reset"):
            await msg_.delete()
            json_d_rss[server_message]['message'] = r":newspaper: | Rilisan Baru: **{title}**\n{link}"
            write_rss_data(json_d_rss)
            return await ctx.send('Berhasil mengembalikan pesan ke bawaan naoTimes.')

        konten_pesan = user_input.content

        await msg_.delete()
        fin = await ctx.send('Mengubah format pesan ke: `{}`'.format(konten_pesan))

        json_d_rss[server_message]['message'] = konten_pesan

        write_rss_data(json_d_rss)

        await fin.delete()
        await user_input.delete()
        await ctx.send('Berhasil mengubah format pesan ke `{}`'.format(konten_pesan))


    @fansubrss.command(aliases=['embed'])
    @commands.guild_only()
    async def formatembed(self, ctx):
        server_message = str(ctx.message.guild.id)
        print('Requested !fansubrss formatembed at: ' + server_message)
        json_d_rss = read_rss_data()

        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]

        if server_message not in json_d_rss:
            return

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return

        feed = await async_feedparse(json_d_rss[server_message]['feedUrl'])
        if not feed:
            return await ctx.send('Tidak dapat membuat koneksi dengan RSS feed')
        entries_data = feed.entries[0]
        entries_data = filter_data(entries_data)

        regex_uri = re.compile(
                r'^(?:http|ftp)s?://' # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
                r'localhost|' #localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
                r'(?::\d+)?' # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        text = 'Ubah format embed yang akan dikirim\n\nContoh data dari RSS (`{DATA}`: ISI):\n'
        for k, v in entries_data.items():
            if isinstance(v, str) and re.match(regex_uri, v):
                v = '<{}>'.format(v)
            text += '`{k}`: {v}\n'.format(k=k, v=v)

        msg_ = await ctx.send(text)
        msg2_ = await ctx.send('Ketik data embed yang dinginkan, lalu ketik `{DATA}` yang diinginkan')

        def check(m):
            return m.author == ctx.message.author

        valid_embed = ['title', 'description', 'url', 'color', 'thumbnail', 'image', 'footer', 'footer_img']
        embed = {
            "title": None,
            "description": None,
            "url": None,
            "thumbnail": None,
            "image": None,
            "footer": None,
            "footer_img": None,
            "color": None,
            "timestamp": False
        }
        cancel = False
        remove = False
        text_ = 'Data embed yang tersedia\n`title`, `description`, `url`, `color`, `image`, `thumbnail`, `footer`, `footer_img`, `timestamp`'
        if json_d_rss[server_message]['embed']:
            for k, v in json_d_rss[server_message]['embed'].items():
                embed[k] = v
                text_ += '\n`{}`: {}'.format(k, v)
        msg3_ = await ctx.send(text_)
        await ctx.send('Ketik pesan yang ingin! (ketik *cancel* untuk membatalkannya dan *done* jika sudah, atau *clear* untuk menghapus embed)')
        while True:
            user_input = await self.bot.wait_for('message', check=check)
            if user_input.content == ("cancel"):
                print('[@] Cancelled')
                cancel = True
                break
            if user_input.content == ("clear"):
                print('[@] Clearing...')
                remove = True
                break

            if user_input.content in valid_embed:
                print('Changing ' + user_input.content)
                msg__ = await ctx.send('Mengubah: `{}`{}'.format(user_input.content, '\n Bisa melihat angka warna di sini: <https://leovoel.github.io/embed-visualizer/>' if 'color' in user_input.content else ''))
                user_input2 = await self.bot.wait_for('message', check=check)

                if user_input2.content == ("cancel"):
                    print('[@] Cancelled')
                    await ctx.send('**Dibatalkan.**')

                embed[user_input.content.strip()] = user_input2.content
                await msg__.delete()
                await user_input.delete()
                await user_input2.delete()
            if user_input.content == ("done"):
                print('[@] Done')
                break
            if 'timestamp' in user_input.content:
                if not embed['timestamp']:
                    await ctx.send('Mengaktifkan timestamp')
                    embed['timestamp'] = True
                else:
                    await ctx.send('Menonaktifkan timestamp')
                    embed['timestamp'] = False

        if cancel:
            return await ctx.send('**Dibatalkan.**')
        if remove:
            await msg_.delete()
            await msg2_.delete()
            await msg3_.delete()
            embed = {}
            json_d_rss[server_message]['embed'] = embed
            write_rss_data(json_d_rss)
            return await ctx.send('Berhasil menghapus embed')

        await msg_.delete()
        await msg2_.delete()
        await msg3_.delete()
        formatted_dict = ''
        for k, v in embed.items():
            formatted_dict += '\n`{}`: {}'.format(k, v)
        fin = await ctx.send('Mengubah format embed ke:{}'.format(formatted_dict))

        json_d_rss[server_message]['embed'] = embed

        write_rss_data(json_d_rss)

        #await fin.delete()
        #await user_input.delete()
        await ctx.send('Berhasil mengubah format embed!'.format(formatted_dict))


def setup(bot):
    bot.add_cog(FansubRSS(bot))
