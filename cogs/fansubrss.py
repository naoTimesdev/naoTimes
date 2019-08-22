import asyncio
import difflib
import json
import re
import time
from calendar import monthrange
from datetime import datetime,
import os
from typing import Tuple, Any

import aiohttp
import discord
import feedparser
from discord.ext import commands, tasks


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

def filter_data(entries) -> dict:
    """Remove unnecessary tags that just gonna trashed the data"""
    remove_data = ['title_detail', 'links', 'authors', 'author_detail', 'content', 
            'updated', 'guidislink', 'summary', 'summary_detail', 'comments', 
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

    return entries

async def check_available_opts(url) -> Tuple[list, Any]:
    feed = feedparser.parse(url)
    return list(feed.entries[0].keys()), feed.entries[0]


async def check_if_valid(url) -> bool:
    feed = feedparser.parse(url)

    if not feed.entries:
        return False
    return True


async def parse_message(message, entry_data):
    matches = re.findall(r"(?P<data>{[^{}]+})", message, re.MULTILINE | re.IGNORECASE)
    msg_fmt_data = [m.strip(r'{}') for m in matches]

    for i in msg_fmt_data:
        message = message.replace('{' + i + '}', entry_data[i])

    return message


async def recursive_check_feed(url, last):
    feed = feedparser.parse(url)

    entries = feed.entries

    filtered_entry = []
    for n, entry in enumerate(entries):
        if entry['title'] != last:
            filtered_entry.append(entries[n])

    return filter_data(filtered_entry)


class FansubRSS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_every_feed.start()


    @tasks.loop(minutes=5.0)
    async def check_every_feed(self):
        print('@@ Routine 5 minute checks of fansub rss')
        with open('fansubrss.json', 'r') as fp:
            json_d_rss = json.load(fp)

        for k in json_d_rss.keys():
            print('@@ Checking `{}` feed'.format(k))
            entries = await recursive_check_feed(json_d_rss[k]['feedUrl'], json_d_rss[k]['lastUpdate'])
            if entries:
                channel = self.bot.get_channel(int(json_d_rss[k]['channel']))
                for entry in entries:
                    msg_format = await parse_message(json_d_rss[k]['message'], entry)
                    await channel.send(msg_format)
            else:
                print('@@ No new update.')
        print("@@ Finish checking, now sleeping for 5 minutes")

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
            helpmain.add_field(name='Aliases', value="!fansubrss, !rss", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 2.0.0")
            await ctx.send(embed=helpmain)
    
    @fansubrss.command(aliases=['init'])
    @commands.guild_only()
    async def aktifkan(self, ctx):
        server_message = str(ctx.message.guild.id)
        print('Requested !fansubrss at: ' + server_message)
        with open('fansubrss.json', 'r') as fp:
            json_d_rss = json.load(fp)

        json_d = await fetch_json()

        if server_message not in json_d:
            return
        server_data = json_d[server_message]

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return await ctx.send('Hanya admin yang bisa mengaktifkan rss fansub')

        print('Membuat data')
        embed = discord.Embed(title="Fansub RSS", color=0x56acf3)
        embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "channel": "",
            "feedUrl": "",
            "message": r":newspaper: | Rilisan Baru {title}\\n{url}",
            "lastUpdate": ""
        }

        async def process_channel(table, emb_msg, author):
            print('@@ Memproses fansub rss channel')
            embed = discord.Embed(title="Fansub RSS", color=0x96df6a)
            embed.add_field(name='Channel', value="Ketik channel id untuk posting rilisan baru.", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await emb_msg.edit(embed=embed)

            await_msg = await self.bot.wait_for('message', check=lambda m: m.author == author)
            table['channel'] = await_msg.content
            await await_msg.delete()

            return table, emb_msg


        async def process_feed(table, emb_msg, author):
            print('@@ Memproses fansub rss url')
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

        print('@@ Making sure.')
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
                print('@@ Cancelled.')
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

        print("@@ Sending data")

        with open('fansubrss.json', 'w') as f: # Local save before commiting
            json.dump(json_d_rss, f, indent=4)
        print('@@ Sended.')
        embed=discord.Embed(title="Fansub RSS", color=0x96df6a)
        embed.add_field(name="Sukses!", value='Berhasil mengaktifkan RSS.', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        await ctx.send(embed=embed)
        await emb_msg.delete()


    @fansubrss.command(aliases=['format'])
    @commands.guild_only()
    async def formatpesan(self, ctx):
        server_message = str(ctx.message.guild.id)
        print('Requested !fansubrss formatpesan at: ' + server_message)
        with open('fansubrss.json', 'r') as fp:
            json_d_rss = json.load(fp)

        if server_message not in json_d_rss:
            return
        server_data = json_d_rss[server_message]

        if str(ctx.message.author.id) not in server_data['serverowner']:
            return

        feed = feedparser.parse(json_d_rss[server_message]['feedUrl'])
        entries_data = feed.entries[0]
        entries_data = filter_data(entries_data)

        text = 'Ubah format pesan yang akan dikirim:\nYang sekarang: `{}`\n\nContoh data dari RSS (\{DATA\}: \{ISI\}):\n'.format(json_d_rss[server_message]['message'])
        for k, v in entries_data.items():
            text += '`{k}`: {v}\n'.format(k=k, v=v)
        text = '\nKetik `\{DATA\}` untuk memakai data dari RSS, misalkan ingin memakai judul dari RSS.\nMaka pakai `\{title\}`'

        msg_ = await ctx.send(text)
        await ctx.send('Ketik pesan yang ingin! (ketik *cancel* untuk membatalkannya)')

        def check(m):
            return m.author == ctx.message.author

        user_input = await self.bot.wait_for('message', check=check)

        if user_input.content == ("cancel"):
            print('@@ Cancelled')
            return await ctx.send('**Dibatalkan.**')

        konten_pesan = user_input.content

        await msg_.delete()
        fin = await ctx.send('Mengubah format pesan ke: `{}`'.format(konten_pesan))

        json_d_rss[server_message]['message'] = konten_pesan

        with open('fansubrss.json', 'w') as fp:
            json.dump(json_d_rss, fp, indent=4)

        await fin.delete()
        await user_input.delete()
        await ctx.send('Berhasil mengubah format pesan ke `{}`'.format(konten_pesan))

def setup(bot):
    bot.add_cog(FansubRSS(bot))
