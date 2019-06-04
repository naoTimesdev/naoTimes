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
            helpmain = discord.Embed(title="Bantuan Perintah (!ntadmin)", description="versi 1.3.3.1", color=0x00aaaa)
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
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 1.3.3.1")
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
        if bot_config['gist_id'] != "":
            print('@@ Already setup, skipping')
            return await self.bot.say('naoTimes sudah dipersiapkan dan sudah bisa digunakan')


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

        json_d[str(srv_id)] = new_srv_data
        json_d['supermod'].append(str(adm_id)) # Add to supermod list
        print('Created new table for server: {}'.format(srv_id))

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
            await self.bot.say('***Timeout!***')
            await self.bot.clear_reactions(preview_msg)
            return
        elif '✅' in str(res.reaction.emoji):
            success = await patch_json(json_d)
            await self.bot.clear_reactions(preview_msg)
            if success:
                await self.bot.edit_message(preview_msg, '**Patching success!, try it with !tagih**')
                return
            await self.bot.edit_message(preview_msg, '**Patching failed!, try it again later**')
        elif '❌' in str(res.reaction.emoji):
            print('@@ Patch Cancelled')
            await self.bot.clear_reactions(preview_msg)
            await self.bot.edit_message(preview_msg, '**Ok, cancelled process**')


def setup(bot):
    bot.add_cog(ShowtimesAdmin(bot))
