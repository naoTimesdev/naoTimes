# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import asyncio
import json
import os
import re
import time
from calendar import monthrange
from datetime import datetime, timedelta

import aiohttp
import discord
import discord.ext.commands as commands
import pytz


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


class ShowtimesAdmin:
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

    @commands.group(pass_context=True, aliases=['naotimesadmin', 'naoadmin'])
    async def ntadmin(self, ctx):
        if ctx.invoked_subcommand is None:
            if int(ctx.message.author.id) != int(bot_config['owner_id']):
                return
            helpmain = discord.Embed(title="Bantuan Perintah (!ntadmin)", description="versi 1.4.1", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimesAdmin", icon_url="https://cdn.discordapp.com/avatars/558256913926848537/3ea22efbc3100ba9a68ee19ef931b7bc.webp?size=1024")
            helpmain.add_field(name='!ntadmin', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!ntadmin tambah <server id> <id admin> <progress_channel>', value="```Menambahkan server baru ke naoTimes```", inline=False)
            helpmain.add_field(name='!ntadmin hapus <server id>', value="```Menghapus server dari naoTimes```", inline=False)
            helpmain.add_field(name='!ntadmin tambahadmin <server id> <id admin>', value="```Menambahkan admin baru ke server yang terdaftar```", inline=False)
            helpmain.add_field(name='!ntadmin hapusadmin <server id> <id admin>', value="```Menghapus admin dari server yang terdaftar```", inline=False)
            helpmain.add_field(name='!ntadmin fetchdb', value="```Mengambil database dan menguploadnya ke discord```", inline=False)
            helpmain.add_field(name='!ntadmin patchdb', value="```Menganti database dengan attachments yang dicantumkan\nTambah attachments lalu tulis !ntadmin patchdb dan enter`", inline=False)
            helpmain.add_field(name='!ntadmin forceupdate', value="```Memaksa update database utama gist dengan database local.```", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 1.4.1")
            await self.bot.say(embed=helpmain)


    @ntadmin.command(pass_context=True)
    async def listserver(self, ctx):
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !ntadmin listserver by admin')
        json_d = await fetch_json()
        if not json_d:
            return

        srv_list = []
        for i, _ in json_d.items():
            srv_list.append(i)

        srv_list.remove('supermod')

        text = '**List server:**\n'
        for x in srv_list:
            text += x + '\n'

        text = text.rstrip('\n')
        
        await self.bot.say(text)


    @ntadmin.command(pass_context=True)
    async def initiate(self, ctx):
        """
        Initiate naoTimes on this server so it can be used on other server
        Make sure everything is filled first before starting this command
        """
        print('@@ Initiated naoTimes first-time setup')
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        if bot_config['gist_id'] != "":
            print('@@ Already setup, skipping')
            return await self.bot.say('naoTimes sudah dipersiapkan dan sudah bisa digunakan')

        print('Membuat data')
        embed = discord.Embed(title="naoTimes", color=0x56acf3)
        embed.add_field(name='Memulai Proses!', value="Mempersiapkan...", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await self.bot.say(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "id": "",
            "owner_id": str(msg_author.id),
            "progress_channel": ""
        }

        async def process_gist(table, emb_msg, author):
            print('@@ Memproses database')
            embed = discord.Embed(title="naoTimes", color=0x96df6a)
            embed.add_field(name='Gist ID', value="Ketik ID Gist GitHub", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            await_msg = await self.bot.wait_for_message(author=author)
            table['id'] = await_msg.content

            return table, emb_msg

        async def process_progchan(table, emb_msg, author):
            print('@@ Memproses #progress channel')
            embed = discord.Embed(title="naoTimes", color=0x96df6a)
            embed.add_field(name='#progress channel ID', value="Ketik ID channel", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                if await_msg.content.isdigit():
                    table['progress_channel'] = await_msg.content
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        async def process_owner(table, emb_msg, author):
            print('@@ Memproses ID Owner')
            embed = discord.Embed(title="naoTimes", color=0x96df6a)
            embed.add_field(name='Owner ID', value="Ketik ID Owner server atau mention orangnya", inline=False)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            while True:
                await_msg = await self.bot.wait_for_message(author=author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table['owner_id'] = await_msg.content
                        await self.bot.delete_message(await_msg)
                        break
                else:
                    table['owner_id'] = mentions[0].id
                    await self.bot.delete_message(await_msg)
                    break
                await self.bot.delete_message(await_msg)

            return table, emb_msg

        json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)

        print('@@ Making sure.')
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
                await self.bot.delete_message(emb_msg)
                emb_msg = await self.bot.say(embed=embed)
                first_time = False
            else:
                emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

            to_react = ['1⃣', "2⃣", '3⃣', '✅', '❌']
            for reaction in to_react:
                    await self.bot.add_reaction(emb_msg, reaction)
            def checkReaction(reaction, user):
                e = str(reaction.emoji)
                return e.startswith(tuple(to_react))

            res = await self.bot.wait_for_reaction(message=emb_msg, user=msg_author, check=checkReaction)

            if to_react[0] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
            elif to_react[1] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_owner(json_tables, emb_msg, msg_author)
            elif to_react[2] in str(res.reaction.emoji):
                await self.bot.clear_reactions(emb_msg)
                json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)
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

        embed=discord.Embed(title="naoTimes", color=0x56acf3)
        embed.add_field(name="Memproses!", value='Mengirim data...', inline=True)
        embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
        emb_msg = await self.bot.edit_message(emb_msg, embed=embed)

        main_data = {}
        server_data = {}
        main_data['supermod'] = [json_tables['owner_id']]
        
        server_data['serverowner'] = [json_tables['owner_id']]
        server_data['announce_channel'] = json_tables['progress_channel']
        server_data['anime'] = {}
        server_data['alias'] = {}

        main_data[str(ctx.message.server.id)] = server_data
        print('@@ Sending data')

        hh = {
            "description": "N4O Showtimes bot",
            "files": {
                "nao_showtimes.json": {
                    "filename": "nao_showtimes.json",
                    "content": json.dumps(main_data, indent=4)
                }
            }
        }

        print('@@ Patching gists')
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(bot_config['github_info']['username'], bot_config['github_info']['password'])) as sesi2:
            async with sesi2.patch('https://api.github.com/gists/{}'.format(json_tables['gist_id']), json=hh) as resp:
                r = await resp.json()
        try:
            m = r['message']
            print('@@ Failed to patch: {}'.format(m))
            return await self.bot.say('@@ Gagal memproses silakan cek bot log, membatalkan...')
        except KeyError:
            print('@@ Reconfiguring config files')
            bot_config['gist_id'] = json_tables['gist_id']
            with open('config.json', 'w') as fp:
                json.dump(bot_config, fp, indent=4)
            print('@@ Reconfigured. Every configuration are done, please restart.')
            embed=discord.Embed(title="naoTimes", color=0x56acf3)
            embed.add_field(name="Sukses!", value='Sukses membuat database di github\nSilakan restart bot agar naoTimes dapat diaktifkan.\n\nLaporkan isu di: [GitHub Issue](https://github.com/noaione/naoTimes/issues)', inline=True)
            embed.set_footer(text="Dibawakan oleh naoTimes™®", icon_url='https://p.n4o.xyz/i/nao250px.png')
            await self.bot.say(embed=embed)
            await self.bot.delete_message(emb_msg)

    @ntadmin.command(pass_context=True)
    async def fetchdb(self, ctx):
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !ntadmin fetchdb by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        channel = ctx.message.channel

        print('Saving .json')
        save_file_name = str(int(round(time.time()))) + '_naoTimes_database.json'
        with open(save_file_name, 'w') as f:
            json.dump(json_d, f)

        print('Sending .json')
        await self.bot.send_file(channel, save_file_name, content='Here you go!')
        os.remove(save_file_name) # Cleanup


    @ntadmin.command(pass_context=True)
    async def patchdb(self, ctx):
        """
        !! Warning !!
        This will patch entire database
        """
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !ntadmin patchdb by admin')

        if ctx.message.attachments == []:
            await self.bot.delete_message(ctx.message)
            await self.bot.say('Please provide a valid .json file by uploading and add `!!ntadmin patchdb` command')
            return

        print('@@ Fetching attachments')

        attachment = ctx.message.attachments[0]
        uri = attachment['url']
        filename = attachment['filename']

        if filename[filename.rfind('.'):] != '.json':
            await self.bot.delete_message(ctx.message)
            await self.bot.say('Please provide a valid .json file by uploading and add `!!ntadmin patchdb` command')
            return

        # Start downloading .json file
        print('@@ Downloading file')
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(uri) as resp:
                data = await resp.text()
                await self.bot.delete_message(ctx.message)
                json_to_patch = json.loads(data)

        print('@@ Make sure.')
        preview_msg = await self.bot.say('**Are you sure you want to patch the database with provided .json file?**')
        to_react = ['✅', '❌']
        for reaction in to_react:
                await self.bot.add_reaction(preview_msg, reaction)
        def checkReaction(reaction, user):
            e = str(reaction.emoji)
            return e.startswith(('✅', '❌'))

        res = await self.bot.wait_for_reaction(message=preview_msg, user=ctx.message.author, timeout=15, check=checkReaction)

        if res is None:
            await self.bot.say('***Timeout!***')
            await self.bot.clear_reactions(preview_msg)
            return
        elif '✅' in str(res.reaction.emoji):
            success = await patch_json(json_to_patch)
            await self.bot.clear_reactions(preview_msg)
            if success:
                await self.bot.edit_message(preview_msg, '**Patching success!, try it with !tagih**')
                return
            await self.bot.edit_message(preview_msg, '**Patching failed!, try it again later**')
        elif '❌' in str(res.reaction.emoji):
            print('@@ Patch Cancelled')
            await self.bot.clear_reactions(preview_msg)
            await self.bot.edit_message(preview_msg, '**Ok, cancelled process**')


    @ntadmin.command(pass_context=True)
    async def tambah(self, ctx, srv_id, adm_id, prog_chan=None):
        """
        Menambah server baru ke database naoTimes
        
        :srv_id: server id
        :adm_id: admin id
        :prog_chan: #progress channel id
        """
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !ntadmin tambah by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            await self.bot.say('Tidak ada input server dari user')
            return

        if adm_id is None:
            await self.bot.say('Tidak ada input admin dari user')
            return

        new_srv_data = {}

        new_srv_data['serverowner'] = [str(adm_id)]
        if prog_chan:
            new_srv_data['announce_channel'] = str(prog_chan)
        new_srv_data['anime'] = {}
        new_srv_data['alias'] = {}

        json_d[str(srv_id)] = new_srv_data
        json_d['supermod'].append(str(adm_id)) # Add to supermod list
        print('Created new table for server: {}'.format(srv_id))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)
        if success:
            await self.bot.say('Sukses menambah server dengan info berikut:\n```Server ID: {s}\nAdmin: {a}\nMemakai #progress Channel: {p}```'.format(s=srv_id, a=adm_id, p=bool(prog_chan)))
            return
        await self.bot.say('Gagal dalam menambah server baru :(')


    @ntadmin.command(pass_context=True)
    async def hapus(self, ctx, srv_id):
        """
        Menghapus server dari database naoTimes
        
        :srv_id: server id
        """
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !ntadmin hapus by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            await self.bot.say('Tidak ada input server dari user')
            return

        try:
            srv = json_d[str(srv_id)]
            adm_id = srv['serverowner'][0]
            print('Server found, deleting...')
            del json_d[str(srv_id)]
        except KeyError:
            await self.bot.say('Server tidak dapat ditemukan dalam database.')
            return

        try:
            json_d['supermod'].remove(adm_id)
        except:
            await self.bot.say('Gagal menghapus admin dari data super admin')
            return

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)
        if success:
            await self.bot.say('Sukses menghapus server `{s}` dari naoTimes'.format(s=srv_id))
            return
        await self.bot.say('Gagal menghapus server :(')


    @ntadmin.command(pass_context=True)
    async def tambahadmin(self, ctx, srv_id, adm_id):
        """
        Menghapus server dari database naoTimes
        
        :srv_id: server id
        """
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !ntadmin tambahadmin by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            await self.bot.say('Tidak ada input server dari user')
            return

        if adm_id is None:
            await self.bot.say('Tidak ada input admin dari user')
            return

        try:
            srv = json_d[str(srv_id)]
            print('Server found, adding admin...')
        except KeyError:
            await self.bot.say('Server tidak dapat ditemukan dalam database.')
            return

        srv['serverowner'].append(str(adm_id))

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)
        if success:
            await self.bot.say('Sukses menambah admin `{a}` di server `{s}`'.format(s=srv_id, a=adm_id))
            return
        await self.bot.say('Gagal menambah admin :(')


    @ntadmin.command(pass_context=True)
    async def hapusadmin(self, ctx, srv_id, adm_id):
        """
        Menghapus server dari database naoTimes
        
        :srv_id: server id
        """
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        print('Requested !ntadmin hapusadmin by admin')
        json_d = await fetch_json()
        if not json_d:
            return
        if srv_id is None:
            await self.bot.say('Tidak ada input server dari user')
            return

        if adm_id is None:
            await self.bot.say('Tidak ada input admin dari user')
            return

        try:
            srv = json_d[str(srv_id)]
            print('Server found, finding admin...')
            admlist = srv['serverowner']
            if str(adm_id) in admlist:
                srv['serverowner'].remove(str(adm_id))
            else:
                await self.bot.say('Tidak dapat menemukan admin tersebut di server: `{}`'.format(srv_id))
                return
        except KeyError:
            await self.bot.say('Server tidak dapat ditemukan dalam database.')
            return

        with open('nao_showtimes.json', 'w') as f: # Local save before commiting
            json.dump(json_d, f, indent=4)

        success = await patch_json(json_d)
        if success:
            await self.bot.say('Sukses menghapus admin `{a}` dari server `{s}`'.format(s=srv_id, a=adm_id))
            return
        await self.bot.say('Gagal menghapus admin :(')

    
    @ntadmin.command(pass_context=True)
    async def forceupdate(self, ctx):
        print('Requested forceupdate by admin')
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            return
        json_d = await fetch_json()
        if not json_d:
            return
        print('@@ Make sure')
        
        preview_msg = await self.bot.say('**Are you sure you want to patch the database with local .json file?**')
        to_react = ['✅', '❌']
        for reaction in to_react:
                await self.bot.add_reaction(preview_msg, reaction)
        def checkReaction(reaction, user):
            e = str(reaction.emoji)
            return e.startswith(('✅', '❌'))

        res = await self.bot.wait_for_reaction(message=preview_msg, user=ctx.message.author, timeout=15, check=checkReaction)

        if res is None:
            await self.bot.clear_reactions(preview_msg)
            return await self.bot.say('***Timeout!***')
        elif '✅' in str(res.reaction.emoji):
            success = await patch_json(json_d)
            await self.bot.clear_reactions(preview_msg)
            if success:
                return await self.bot.edit_message(preview_msg, '**Patching success!, try it with !tagih**')
            await self.bot.edit_message(preview_msg, '**Patching failed!, try it again later**')
        elif '❌' in str(res.reaction.emoji):
            print('@@ Patch Cancelled')
            await self.bot.clear_reactions(preview_msg)
            await self.bot.edit_message(preview_msg, '**Ok, cancelled process**')


def setup(bot):
    bot.add_cog(ShowtimesAdmin(bot))
