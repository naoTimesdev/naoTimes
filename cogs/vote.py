import argparse
import asyncio
import json
import os
import shlex
import time
from datetime import datetime

import aiohttp
import discord
import pytz
from discord import Permissions
from discord.ext import commands, tasks

with open('config.json', 'r') as fp:
    bot_config = json.load(fp)

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


def parse_args(str_txt: str, s: str):
    '''parse an argument that passed'''
    parser = BotArgumentParser(prog="!vote" + s, usage="!vote" + s, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('yang_ingin_di_vote', help='Apa yang mau vote atau orang yang mau di vote')

    if s == '':
        parser.add_argument('--opsi', '-O', required=True, dest='opsi', action='append', help='Opsi (Batas 10, Min 2)')
        parser.add_argument('--timer', '-t', required=False, default=3, dest='menit', action='store', help='Waktu sebelum voting ditutup (Dalam menit, Min 3 menit)')
    else:
        parser.add_argument('--limit', '-l', required=False, default=5, dest='batas', action='store', help='Limit user untuk kick/ban')
        parser.add_argument('--timer', '-t', required=False, default=60, dest='detik', action='store', help='Waktu sebelum voting ditutup (Dalam detik, Min 30 detik)')
    try:
        return parser.parse_args(shlex.split(str_txt))
    except ArgumentParserError as argserror:
        return str(argserror)
    except HelpException as help_:
        return '```\n' + str(help_) + '\n```'


async def read_tally(vote=False, kick=False, ban=False):
    with open("vote_data.json", "r") as fp:
        data = json.load(fp)
    if vote:
        return data['vote_data']
    elif kick:
        return data['kick_data']
    elif ban:
        return data['ban_data']
    return data['vote_data']


async def write_tally(key: str, kdata: dict):
    with open("vote_data.json", "r") as fp:
        data = json.load(fp)
    data[key] = kdata
    with open("vote_data.json", 'w') as fp:
        json.dump(data, fp, indent=2)


class VotingSystem(commands.Cog):
    """A shitty voting system"""
    def __init__(self, bot):
        self.bot = bot
        print('[$] Preparing Voting System...')
        self.kick_data_fast = {}
        self.ban_data_fast = {}
        self.vote_data_fast = {}
        self.rw_json_lock = False
        self.rw_kick_lock = False
        self.rw_vote_lock = False
        self.rw_ban_lock = False
        print('[$] Starting Main Vote Watcher.')
        self.main_vote_watcher.start()
        print('[$] Starting Kick Vote Watcher.')
        self.kick_vote_watcher.start()
        print('[$] Starting Ban Vote Watcher.')
        self.ban_vote_watcher.start()

    def __str__(self):
        return "nT Voting System"

    async def acquire_lock(self, mode="vote_data"):
        print('[nT Vote] Acquiring file lock...')
        mode_list = {
            "vote_data": [True, False, False],
            "kick_data": [False, True, False],
            "ban_data": [False, False, True]
        }
        acquire_mode = mode_list.get(mode, [True, False, False])
        if not self.rw_json_lock:
            print('[nT Vote] Lock acquired.')
            self.rw_json_lock = True
            return (await read_tally(*acquire_mode))
        # Lock still not released, try every 2 seconds to acquire lock
        print('[nT Vote] Lock not released, retrying every 1 seconds')
        while True:
            if not self.rw_json_lock:
                print('[nT Vote] Lock acquired.')
                self.rw_json_lock = True
                return (await read_tally(*acquire_mode))
            await asyncio.sleep(1)

    async def acquire_lock_self(self, mode):
        if mode == "vote_data":
            if not self.rw_vote_lock:
                print('[nT Vote: Vote] Lock acquired.')
                self.rw_vote_lock = True
            # Lock still not released, try every 2 seconds to acquire lock
            print('[nT Vote: Vote] Lock not released, retrying every 1 seconds')
            while True:
                if not self.rw_vote_lock:
                    print('[nT Vote: Vote] Lock acquired.')
                    self.rw_vote_lock = True
                    break
                await asyncio.sleep(1)
        elif mode == "kick_data":
            if not self.rw_kick_lock:
                print('[nT Vote: Kick] Lock acquired.')
                self.rw_kick_lock = True
            # Lock still not released, try every 2 seconds to acquire lock
            print('[nT Vote: Kick] Lock not released, retrying every 1 seconds')
            while True:
                if not self.rw_kick_lock:
                    print('[nT Vote: Kick] Lock acquired.')
                    self.rw_kick_lock = True
                    break
                await asyncio.sleep(1)
        elif mode == "ban_data":
            if not self.rw_ban_lock:
                print('[nT Vote: Ban] Lock acquired.')
                self.rw_ban_lock = True
            # Lock still not released, try every 2 seconds to acquire lock
            print('[nT Vote: Ban] Lock not released, retrying every 1 seconds')
            while True:
                if not self.rw_ban_lock:
                    print('[nT Vote: Ban] Lock acquired.')
                    self.rw_ban_lock = True
                    break
                await asyncio.sleep(1)


    async def release_lock(self):
        print('[nT Vote] Releasing lock...')
        self.rw_json_lock = False

    async def release_lock_self(self, mode):
        if mode == "vote_data":
            print('[nT Vote: Vote] Lock released.')
            self.rw_vote_lock = False
        elif mode == "kick_data":
            print('[nT Vote: Kick] Lock released.')
            self.rw_kick_lock = False
        elif mode == "ban_data":
            print('[nT Vote: Ban] Lock released.')
            self.rw_ban_lock = False

    @tasks.loop(seconds=1.0)
    async def main_vote_watcher(self):
        v_ = 'vote_data'
        reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']
        await self.acquire_lock_self(mode=v_)
        current_time = round(time.time())
        if self.vote_data_fast:
            vote_data = await self.acquire_lock(mode=v_)
            for k_fast, v_fast in self.vote_data_fast.items():
                v_main = vote_data[k_fast]
                timer = current_time - v_fast['start_time']
                if timer > v_fast['max_time']:
                    server = self.bot.get_guild(int(v_main['server']))
                    channel = server.get_channel(int(v_main['channel']))
                    message = await channel.fetch_message(int(k_fast))
                    embed = discord.Embed().from_dict(message.embeds[0].to_dict())
                    c = 0
                    winner = ''
                    n___dex = 0
                    for k, v in v_main['options'].items():
                        n = len(v['voter'])
                        if n > c:
                            c = n
                            winner = v['name']
                            n___dex = int(k)

                    embed.set_footer(text="Waktu Habis!")
                    await message.edit(embed=embed)
                    del vote_data[k_fast]
                    del self.vote_data_fast[k_fast]
                    await write_tally(v_, vote_data)

                    if c == 0:
                        await channel.send('Dan pemenang dari **{q}** adalah: Tidak ada'.format(q=v_main['q']))
                    else:
                        await channel.send('Dan pemenang dari **{q}** adalah: {r} {opt} '.format(q=v_main['q'], r=reactions[n___dex], opt=winner))
                else:
                    options = []
                    for k, v in v_main['options'].items():
                        options.append(v['name'])
                    for x, option in enumerate(options):
                        tally_ = vote_data[k_fast]['options'][str(x)]['voter']
                        embed.set_field_at(x, name='{} {}'.format(reactions[x], option), value='Votes: {}'.format(len(tally_)), inline=False)
                    embed.set_footer(text="Sisa Waktu: {} menit".format(round(timer / 60)))
                    await message.edit(embed=embed)
            await self.release_lock()
        await self.release_lock_self(v_)

    @tasks.loop(seconds=1.0)
    async def kick_vote_watcher(self):
        v_ = 'kick_data'
        await self.acquire_lock_self(mode=v_)
        current_time = round(time.time())
        if self.kick_data_fast:
            for k_fast, v_fast in self.kick_data_fast.items():
                timer = current_time - v_fast['start_time']
                tally = v_fast['tally']
                limit = v_fast['limit']

                vote_data = await self.acquire_lock(mode=v_)
                v_main = vote_data[k_fast]
                server = self.bot.get_guild(int(v_main['server']))
                channel = server.get_channel(int(v_main['channel']))
                user_ = server.get_member(int(v_main['user_id']))
                message = await channel.fetch_message(int(k_fast))
                embed = discord.Embed().from_dict(message.embeds[0].to_dict())
                if timer > v_fast['max_time']:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah vote kick **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        await server.kick(user=user_, reason="Kick musyawarah dan mufakat oleh member server ini dengan bot naoTimes.")
                        await channel.send('User **{}#{}** telah dikick secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        await channel.send('Voting selesai, user tidak akan dikick karena kurangnya orang yang react ({} <= {})'.format(tally, limit))
                    del vote_data[k_fast]
                    del self.kick_data_fast[k_fast]
                    await write_tally(v_, vote_data)
                else:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah vote kick **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        del vote_data[k_fast]
                        await write_tally(v_, vote_data)
                        await server.kick(user=user_, reason="Kick musyawarah dan mufakat oleh member server ini dengan bot naoTimes.")
                        await channel.send('User **{}#{}** telah dikick secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        embed.set_field_at(0, name='Jumlah vote (Dibutuhkan: {})'.format(limit), value=str(tally), inline=False)
                        embed.set_field_at(1, name='Sisa waktu', value=f'{timer} detik', inline=False)
                        await message.edit(embed=embed)
            await self.release_lock()
        await self.release_lock_self(v_)

    @tasks.loop(seconds=1.0)
    async def ban_vote_watcher(self):
        v_ = 'ban_data'
        await self.acquire_lock_self(mode=v_)
        current_time = round(time.time())
        if self.ban_data_fast:
            for k_fast, v_fast in self.ban_data_fast.items():
                timer = current_time - v_fast['start_time']
                tally = v_fast['tally']
                limit = v_fast['limit']

                vote_data = await self.acquire_lock(mode=v_)
                v_main = vote_data[k_fast]
                server = self.bot.get_guild(int(v_main['server']))
                channel = server.get_channel(int(v_main['channel']))
                user_ = server.get_member(int(v_main['user_id']))
                message = await channel.fetch_message(int(k_fast))
                embed = discord.Embed().from_dict(message.embeds[0].to_dict())
                if timer > v_fast['max_time']:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah vote kick **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        await server.kick(user=user_, reason="Kick musyawarah dan mufakat oleh member server ini dengan bot naoTimes.")
                        await channel.send('User **{}#{}** telah dikick secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        await channel.send('Voting selesai, user tidak akan dikick karena kurangnya orang yang react ({} <= {})'.format(tally, limit))
                    del vote_data[k_fast]
                    del self.ban_data_fast[k_fast]
                    await write_tally(v_, vote_data)
                else:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah vote kick **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        del vote_data[k_fast]
                        del self.ban_data_fast[k_fast]
                        await write_tally(v_, vote_data)
                        await server.kick(user=user_, reason="Kick musyawarah dan mufakat oleh member server ini dengan bot naoTimes.")
                        await channel.send('User **{}#{}** telah dikick secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        embed.set_field_at(0, name='Jumlah vote (Dibutuhkan: {})'.format(limit), value=str(tally), inline=False)
                        embed.set_field_at(1, name='Sisa waktu', value=f'{timer} detik', inline=False)
                        await message.edit(embed=embed)
            await self.release_lock()
        await self.release_lock_self(v_)

    @commands.Cog.listener(name="on_reaction_add")
    async def vote_reaction_added(self, reaction, user):
        await self.acquire_lock_self("vote_data")
        await self.acquire_lock_self("kick_data")
        await self.acquire_lock_self("ban_data")

        if str(reaction.message.id) in self.kick_data_fast:
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    print('Adding kick tally from: {}'.format(user.id))
                    self.kick_data_fast[str(reaction.message.id)]['tally'] = self.kick_data_fast[str(reaction.message.id)]['tally'] + 1
        elif str(reaction.message.id) in self.ban_data_fast:
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    print('Adding ban tally from: {}'.format(user.id))
                    self.ban_data_fast[str(reaction.message.id)]['tally'] = self.ban_data_fast[str(reaction.message.id)]['tally'] + 1
        elif str(reaction.message.id) in self.vote_data_fast:
            reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']
            if user != self.bot.user:
                if str(reaction.emoji) in reactions:
                    n_index = reactions.index(str(reaction.emoji))
                    voter_list = []
                    for i in range(len(self.vote_data_fast[str(reaction.message.id)]['options'])):
                        voter_list.extend(self.vote_data_fast[str(reaction.message.id)]['options'][str(i)])
                    if str(user.id) not in voter_list:
                        print('Adding vote tally from: {}'.format(user.id))
                        self.vote_data_fast[str(reaction.message.id)]['options'][str(n_index)].append(str(user.id))
        await self.release_lock_self("vote_data")
        await self.release_lock_self("kick_data")
        await self.release_lock_self("ban_data")

    @commands.Cog.listener(name="on_reaction_remove")
    async def vote_reaction_removal(self, reaction, user):
        await self.acquire_lock_self("vote_data")
        await self.acquire_lock_self("kick_data")
        await self.acquire_lock_self("ban_data")

        if str(reaction.message.id) in self.kick_data_fast:
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    print('Adding kick tally from: {}'.format(user.id))
                    self.kick_data_fast[str(reaction.message.id)]['tally'] = self.kick_data_fast[str(reaction.message.id)]['tally'] - 1
        elif str(reaction.message.id) in self.ban_data_fast:
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    print('Adding ban tally from: {}'.format(user.id))
                    self.ban_data_fast[str(reaction.message.id)]['tally'] = self.ban_data_fast[str(reaction.message.id)]['tally'] - 1
        elif str(reaction.message.id) in self.vote_data_fast:
            reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']
            if user != self.bot.user:
                if str(reaction.emoji) in reactions:
                    n_index = reactions.index(str(reaction.emoji))
                    voter_list = self.vote_data_fast[str(reaction.message.id)]['options'][str(n_index)]
                    if str(user.id) in voter_list:
                        print('Remove vote tally from: {}'.format(user.id))
                        self.vote_data_fast[str(reaction.message.id)]['options'][str(n_index)].remove(str(user.id))
        await self.release_lock_self("vote_data")
        await self.release_lock_self("kick_data")
        await self.release_lock_self("ban_data")


    @commands.command(pass_context=True)
    @commands.has_permissions(kick_members=True)
    async def votekick(self, ctx, *, args_=''):
        v_ = 'kick_data'
        srv = ctx.message.guild

        args = parse_args(args_, 'kick')
        if isinstance(args, str):
            return await ctx.send(parse_error(args))

        msg = ctx.message
        timer = int(args.detik)
        limit = int(args.batas)
        user = args.data
        if limit < 5:
            return await ctx.send('Limit react tidak boleh kurang dari 5 orang')
        if timer < 30:
            return await ctx.send('Timer tidak boleh kurang dari 30 detik')

        js_ = dict()
        js_extra = dict()
        js_extra['tally'] = 0

        mentions = msg.mentions

        if not mentions:
            if user.isdigit():
                try:
                    user_ = msg.guild.get_member(int(user))
                    js_['user_id'] = str(user)
                except:
                    return await ctx.send('Mention orang/ketik ID yang valid')
            else:
                return await ctx.send('Mention orang/ketik ID yang ingin di kick')
        else:
            js_['user_id'] = str(mentions[0].id)
            user_ = mentions[0]

        js_['server'] = str(ctx.message.guild.id)
        js_['channel'] = str(ctx.message.channel.id)
        js_extra['max_time'] = timer
        js_extra['start_time'] = round(time.time())
        js_extra['limit'] = limit

        if user_.guild_permissions.administrator:
            return await ctx.send('Tidak dapat mengkick admin.')
        hirarki_bot = srv.get_member(self.bot.user.id).top_role.position
        if user_.top_role.position >= hirarki_bot:
            return await ctx.send('Hirarki orang tersebut lebih tinggi.')

        embed = discord.Embed(title="Vote Kick - {0.name}#{0.discriminator}".format(user_), description='React jika ingin user ini dikick.', color=0x3f0a16)
        embed.add_field(name='Jumlah vote (Dibutuhkan: {})'.format(limit), value='0', inline=False)
        embed.add_field(name='Sisa waktu', value=f'{timer} detik', inline=False)
        emb_msg = await ctx.send(embed=embed)
        await emb_msg.add_reaction('✅')

        vote_data = await self.acquire_lock(v_)
        await self.acquire_lock_self(v_)
        vote_data[str(emb_msg.id)] = js_
        self.kick_data_fast[str(emb_msg.id)] = js_extra

        await write_tally(v_, vote_data)
        await self.release_lock()
        await self.release_lock_self(v_)


    @commands.command(pass_context=True)
    @commands.has_permissions(ban_members=True)
    async def voteban(self, ctx, *, args_=''):
        vote_data = await read_tally(ban=True)
        v_ = 'ban_data'
        srv = ctx.message.guild

        args = parse_args(args_, 'ban')
        if isinstance(args, str):
            return await ctx.send(parse_error(args))
        msg = ctx.message
        timer = int(args.detik)
        limit = int(args.batas)
        user = args.data
        if limit < 5:
            return await ctx.send('Limit react tidak boleh kurang dari 5 orang')
        if timer < 30:
            return await ctx.send('Timer tidak boleh kurang dari 30 detik')

        js_ = dict()
        js_extra = dict()
        js_extra['tally'] = 0

        mentions = msg.mentions

        if not mentions:
            if user.isdigit():
                try:
                    user_ = msg.guild.get_member(int(user))
                    js_['user_id'] = str(user)
                except:
                    return await ctx.send('Mention orang/ketik ID yang valid')
            else:
                return await ctx.send('Mention orang/ketik ID yang ingin di kick')
        else:
            js_['user_id'] = str(mentions[0].id)
            user_ = mentions[0]

        js_['server'] = str(ctx.message.guild.id)
        js_['channel'] = str(ctx.message.channel.id)
        js_extra['max_time'] = timer
        js_extra['start_time'] = round(time.time())
        js_extra['limit'] = limit

        if user_.guild_permissions.administrator:
            return await ctx.send('Tidak dapat nge-ban admin.')
        hirarki_bot = srv.get_member(self.bot.user.id).top_role.position
        if user_.top_role.position >= hirarki_bot:
            return await ctx.send('Hirarki orang tersebut lebih tinggi.')

        embed = discord.Embed(title="Vote Ban - {0.name}#{0.discriminator}".format(user_), description='React jika ingin user ini diban.', color=0x3f0a16)
        embed.add_field(name='Jumlah vote (Dibutuhkan: {})'.format(limit), value='0', inline=False)
        embed.add_field(name='Sisa waktu', value=f'{timer} detik', inline=False)
        emb_msg = await ctx.send(embed=embed)
        await emb_msg.add_reaction('✅')

        vote_data = await self.acquire_lock(v_)
        await self.acquire_lock_self(v_)
        vote_data[str(emb_msg.id)] = js_
        self.ban_data_fast[str(emb_msg.id)] = js_extra

        await write_tally(v_, vote_data)
        await self.release_lock()
        await self.release_lock_self(v_)


    @commands.command(pass_context=True)
    async def vote(self, ctx, *, args_=''):
        v_ = 'vote_data'

        args = parse_args(args_, '')
        if isinstance(args, str):
            return await ctx.send(parse_error(args))
        timer = int(args.menit)
        options = args.opsi
        message = args.data
        if len(options) <= 1:
            return await ctx.send('Membutuhkan 2 atau lebih opsi untuk memulai')
        if len(options) > 10:
            return await ctx.send('Opsi tidak bisa lebih dari 10')
        if timer < 3:
            return await ctx.send('Timer tidak boleh kurang dari 3 menit')
        timer = timer * 60

        usr_ava = ctx.message.author.avatar_url
        if not usr_ava:
            usr_ava = ctx.message.author.default_avatar_url

        embed = discord.Embed(title=message, colour=discord.Colour(0x36), description="Masukan pilihanmu dengan ngeklik reaction di bawah ini")

        embed.set_author(name='Voting oleh {}'.format(ctx.message.author.name), icon_url=usr_ava)
        embed.set_footer(text="Sisa Waktu: {} menit".format(round(timer / 60)))

        reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']

        vote_d = dict()
        vote_q = dict()
        vote_list = dict()
        vote_list_e = dict()
        for x, option in enumerate(options):
            embed.add_field(name='{} {}'.format(reactions[x], option), value='Votes: 0', inline=False)
            ll = dict()
            ll['name'] = option
            ll['voter'] = []
            vote_list[str(x)] = ll
            vote_list_e[str(x)] = []

        vote_d['q'] = message
        vote_d['server'] = str(ctx.message.guild.id)
        vote_d['channel'] = str(ctx.message.channel.id)
        vote_d['options'] = vote_list

        vote_q['max_time'] = timer
        vote_q['start_time'] = round(time.time())
        vote_q['options'] = vote_list_e

        emb_msg = await ctx.send(embed=embed)
        vote_data = await self.acquire_lock(v_)
        await self.acquire_lock_self(v_)
        vote_data[str(emb_msg.id)] = vote_d
        self.vote_data_fast[str(emb_msg.id)] = vote_q

        await write_tally(v_, vote_data)
        await self.release_lock()
        await self.release_lock_self(v_)

        for x, _ in enumerate(options):
            await emb_msg.add_reaction(reactions[x])

    @voteban.error
    async def voteban_err(self, ctx, error):
        if isinstance(error, commands.errors.CheckFailure):
            await ctx.send('Tidak memiliki izin yang mencukupi (Butuh: Ban Members)')
        elif isinstance(error, commands.errors.CommandInvokeError):
            await ctx.send(error)
        await ctx.send(error)

    @votekick.error
    async def votekick_err(self, ctx, error):
        if isinstance(error, commands.errors.CheckFailure):
            await ctx.send('Tidak memiliki izin yang mencukupi (Butuh: Kick Members)')
        elif isinstance(error, commands.errors.CommandInvokeError):
            await ctx.send(error)
        await ctx.send(error)

    @vote.error
    async def vote_err(self, ctx, error):
        if isinstance(error, commands.errors.CommandInvokeError):
            await ctx.send(error)
        await ctx.send(error)

VoteCogs = []

def setup(bot):
    for VoteC in VoteCogs:
        try:
            VoteCLoad = VoteC(bot)
            print('\t[#] Loading {} Commands...'.format(str(VoteCLoad)))
            bot.add_cog(VoteCLoad)
            print('\t[@] Loaded.')
        except Exception as ex:
            print('\t[!] Failed: {}'.format(str(ex)))
