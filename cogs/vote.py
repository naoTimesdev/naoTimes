import argparse
import asyncio
import json
import os
import shlex
from datetime import datetime

import aiohttp
import discord
import pytz
from discord import Permissions
from discord.ext import commands, tasks
import redis

with open('config.json', 'r') as fp:
    bot_config = json.load(fp)

redis_srv = redis.Redis().from_url(url=bot_config["redissrv_vote"])

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
    parser.add_argument('data', help='Apa yang mau vote atau orang yang mau di vote')

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
    vote_data = redis_srv.get('vote_data')
    kick_data = redis_srv.get('kick_data')
    ban_data = redis_srv.get('ban_data')

    blank_data = r"{}"

    if not vote_data:
        redis_srv.set('vote_data', blank_data)
    if not kick_data:
        redis_srv.set('kick_data', blank_data)
    if not ban_data:
        redis_srv.set('ban_data', blank_data)

    if vote:
        return json.loads(vote_data)
    elif kick:
        return json.loads(kick_data)
    elif ban:
        return json.loads(ban_data)
    return json.loads(vote_data)


async def write_tally(key: str, data: dict):
    redis_srv.set(key, json.dumps(data))

class VotingWatcher(commands.Cog):
    """A shitty voting tally system"""
    def __init__(self, bot):
        self.bot = bot
        print('[$] Starting Main Vote Watcher.')
        self.main_vote_watcher.start()
        print('[$] Starting Kick Vote Watcher.')
        self.kick_vote_watcher.start()
        print('[$] Starting Ban Vote Watcher.')
        self.ban_vote_watcher.start()

    def __str__(self):
        return "nT Voting Watcher/Tally Tasks"

    @tasks.loop(seconds=1.0)
    async def main_vote_watcher(self):
        v_ = 'vote_data'
        reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']
        vote_data = await read_tally(vote=True)
        if vote_data:
            for k_main, v_main in dict(vote_data.items()).items():
                server = self.bot.get_guild(int(v_main['server']))
                channel = server.get_channel(int(v_main['channel']))
                message = await channel.fetch_message(int(k_main))
                embed = discord.Embed().from_dict(message.embeds[0].to_dict())
                timer = v_main['timer']
                if timer < 1:
                    c = 0
                    winner = ''
                    n___dex = 0
                    for k, v in v_main['options'].items():
                        n = len(v['voter'])
                        if n > c:
                            c = n
                            winner = v['name']
                            n___dex = int(k)

                    embed.set_footer(text=f"Waktu Habis!")
                    await message.edit(embed=embed)
                    del vote_data[k_main]
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
                        tally_ = vote_data[k_main]['options'][str(x)]['voter']
                        embed.set_field_at(x, name='{} {}'.format(reactions[x], option), value='Votes: {}'.format(len(tally_)), inline=False)
                    embed.set_footer(text="Sisa Waktu: {} menit".format(round(timer / 60)))
                    await message.edit(embed=embed)
                    timer -= 1
                    vote_data[k_main]['timer'] = timer
                    await write_tally(v_, vote_data)


    @tasks.loop(seconds=1.0)
    async def kick_vote_watcher(self):
        v_ = 'kick_data'
        vote_data = await read_tally(kick=True)
        if vote_data:
            for k_main, v_main in dict(vote_data.items()).items():
                server = self.bot.get_guild(int(v_main['server']))
                channel = server.get_channel(int(v_main['channel']))
                user_ = server.get_member(int(v_main['user_id']))
                message = await channel.fetch_message(int(k_main))
                embed = discord.Embed().from_dict(message.embeds[0].to_dict())
                timer = v_main['timer']
                limit = v_main['limit']
                tally = int(v_main['tally'])

                if timer < 1:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah vote kick **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        del vote_data[k_main]
                        await write_tally(v_, vote_data)
                        await server.kick(user=user_, reason="Kick musyawarah dan mufakat oleh member server ini dengan bot naoTimes.")
                        await channel.send('User **{}#{}** telah dikick secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        await channel.send('Voting selesai, user tidak akan dikick karena kurangnya orang yang react ({} <= {})'.format(tally, limit))
                        del vote_data[k_main]
                        await write_tally(v_, vote_data)
                else:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah vote kick **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        del vote_data[k_main]
                        await write_tally(v_, vote_data)
                        await server.kick(user=user_, reason="Kick musyawarah dan mufakat oleh member server ini dengan bot naoTimes.")
                        await channel.send('User **{}#{}** telah dikick secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        embed.set_field_at(0, name='Jumlah vote (Dibutuhkan: {})'.format(limit), value=str(tally), inline=False)
                        embed.set_field_at(1, name='Sisa waktu', value=f'{timer} detik', inline=False)
                        await message.edit(embed=embed)
                        timer -= 1
                        vote_data[k_main]['timer'] = timer
                        await write_tally(v_, vote_data)


    @tasks.loop(seconds=1.0)
    async def ban_vote_watcher(self):
        v_ = 'ban_data'
        vote_data = await read_tally(ban=True)
        if vote_data:
            for k_main, v_main in dict(vote_data.items()).items():
                server = self.bot.get_guild(int(v_main['server']))
                channel = server.get_channel(int(v_main['channel']))
                user_ = server.get_member(int(v_main['user_id']))
                message = await channel.fetch_message(int(k_main))
                embed = discord.Embed().from_dict(message.embeds[0].to_dict())
                timer = v_main['timer']
                limit = v_main['limit']
                tally = int(v_main['tally'])

                if timer < 1:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah telah vote ban **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        del vote_data[k_main]
                        await write_tally(v_, vote_data)
                        await server.ban(user=user_, reason="Ban musyawarah dan mufakat oleh member server ini dengan bot naoTimes.", delete_message_days=0)
                        await channel.send('User **{}#{}** telah diban secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        await channel.send('Voting selesai, user tidak akan diban karena kurangnya orang yang react ({} <= {})'.format(tally, limit))
                        del vote_data[k_main]
                        await write_tally(v_, vote_data)
                else:
                    if tally >= limit:
                        await channel.send('Sebanyak **{}** orang telah telah vote ban **{}#{}**, melaksanakan tugas!'.format(tally, user_.name, user_.discriminator))
                        del vote_data[k_main]
                        await write_tally(v_, vote_data)
                        await server.ban(user=user_, reason="Ban musyawarah dan mufakat oleh member server ini dengan bot naoTimes.", delete_message_days=0)
                        await channel.send('User **{}#{}** telah diban secara musyawarah dan mufakat'.format(user_.name, user_.discriminator))
                    else:
                        embed.set_field_at(0, name='Jumlah vote (Dibutuhkan: {})'.format(limit), value=str(tally), inline=False)
                        embed.set_field_at(1, name='Sisa waktu', value=f'{timer} detik', inline=False)
                        await message.edit(embed=embed)
                        timer -= 1
                        vote_data[k_main]['timer'] = timer
                        await write_tally(v_, vote_data)



class VotingSystem(commands.Cog):
    """A shitty voting system"""
    def __init__(self, bot):
        self.bot = bot

    def __str__(self):
        return "nT Voting System"

    @commands.Cog.listener(name="on_reaction_add")
    async def vote_reaction_added(self, reaction, user):
        vote_data_main = await read_tally(vote=True)
        vote_data_kick = await read_tally(kick=True)
        vote_data_ban = await read_tally(ban=True)

        if str(reaction.message.id) in vote_data_kick:
            v_ = 'kick_data'
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    if str(user.id) != str(vote_data_kick[str(reaction.message.id)]['user_id']): # Don't add the user that will be kicked/ban
                        print('Adding kick tally from: {}'.format(user.id))
                        vote_data[str(reaction.message.id)]['tally'] = str(int(vote_data_kick[str(reaction.message.id)]['tally']) + 1)
                        await write_tally(v_, vote_data_kick)
        elif str(reaction.message.id) in vote_data_ban:
            v_ = 'ban_data'
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    if str(user.id) != str(vote_data_ban[str(reaction.message.id)]['user_id']): # Don't add the user that will be kicked/ban
                        print('Adding ban tally from: {}'.format(user.id))
                        vote_data[str(reaction.message.id)]['tally'] = str(int(vote_data_ban[str(reaction.message.id)]['tally']) + 1)
                        await write_tally(v_, vote_data_ban)
        elif str(reaction.message.id) in vote_data_main:
            reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']
            v_ = 'vote_data'
            vote_l = vote_data_main[str(reaction.message.id)]
            if user != self.bot.user:
                if str(reaction.emoji) in reactions:
                    n_index = reactions.index(str(reaction.emoji))
                    voter_list = []
                    for i in range(len(vote_data_main[str(reaction.message.id)]['options'])):
                        voter_list.extend(vote_data_main[str(reaction.message.id)]['options'][str(i)]['voter'])
                    if str(user.id) not in voter_list:
                        print('Adding vote tally from: {}'.format(user.id))
                        vote_data_main[str(reaction.message.id)]['options'][str(n_index)]['voter'].append(str(user.id))
                        await write_tally(v_, vote_data_main)

    @commands.Cog.listener(name="on_reaction_remove")
    async def vote_reaction_removal(self, reaction, user):
        vote_data_main = await read_tally(vote=True)
        vote_data_kick = await read_tally(kick=True)
        vote_data_ban = await read_tally(ban=True)

        if str(reaction.message.id) in vote_data_kick:
            v_ = 'kick_data'
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    if str(user.id) != str(vote_data_kick[str(reaction.message.id)]['user_id']): # Don't add the user that will be kicked/ban
                        print('Remove kick tally from: {}'.format(user.id))
                        vote_data[str(reaction.message.id)]['tally'] = str(int(vote_data_kick[str(reaction.message.id)]['tally']) - 1)
                        await write_tally(v_, vote_data_kick)
        elif str(reaction.message.id) in vote_data_ban:
            v_ = 'ban_data'
            if '✅' in str(reaction.emoji):
                if user != self.bot.user:
                    if str(user.id) != str(vote_data_ban[str(reaction.message.id)]['user_id']): # Don't add the user that will be kicked/ban
                        print('Remove ban tally from: {}'.format(user.id))
                        vote_data[str(reaction.message.id)]['tally'] = str(int(vote_data_ban[str(reaction.message.id)]['tally']) - 1)
                        await write_tally(v_, vote_data_ban)
        elif str(reaction.message.id) in vote_data_main:
            reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']
            v_ = 'vote_data'
            vote_l = vote_data_main[str(reaction.message.id)]
            if user != self.bot.user:
                if str(reaction.emoji) in reactions:
                    n_index = reactions.index(str(reaction.emoji))
                    voter_list = vote_data_main[str(reaction.message.id)]['options'][str(n_index)]['voter']
                    if str(user.id) in voter_list:
                        print('Remove vote tally from: {}'.format(user.id))
                        vote_data_main[str(reaction.message.id)]['options'][str(n_index)]['voter'].remove(str(user.id))
                        await write_tally(v_, vote_data_main)


    @commands.command(pass_context=True)
    @commands.has_permissions(kick_members=True)
    async def votekick(self, ctx, *, args_=''):
        vote_data = await read_tally(kick=True)
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
        js_['tally'] = '0'

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
        js_['timer'] = timer
        js_['limit'] = limit

        if user_.guild_permissions.administrator:
            return await ctx.send('Tidak dapat mengkick admin.')
        hirarki_bot = srv.get_member(self.bot.user.id).top_role.position
        if user_.top_role.position >= hirarki_bot:
            return await ctx.send('Hirarki orang tersebut lebih tinggi.')

        embed = discord.Embed(title="Vote Kick - {0.name}#{0.discriminator}".format(user_), description='React jika ingin user ini dikick.', color=0x3f0a16)
        embed.add_field(name='Jumlah vote (Dibutuhkan: {})'.format(limit), value='0', inline=False)
        embed.add_field(name='Sisa waktu'.format(limit), value=f'{timer} detik', inline=False)
        emb_msg = await ctx.send(embed=embed)
        vote_data[str(emb_msg.id)] = js_

        await emb_msg.add_reaction('✅')
        await write_tally(v_, vote_data)


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
        js_['tally'] = '0'

        mentions = msg.mentions

        if not mentions:
            if user.isdigit():
                try:
                    user_ = msg.guild.get_member(int(user))
                    js_['user_id'] = str(user)
                except:
                    return await ctx.send('Mention orang/ketik ID yang valid')
            else:
                return await ctx.send('Mention orang/ketik ID yang ingin di ban')
        else:
            js_['user_id'] = str(mentions[0].id)
            user_ = mentions[0]

        if user_.guild_permissions.administrator:
            return await ctx.send('Tidak dapat memban admin.')
        hirarki_bot = srv.get_member(self.bot.user.id).top_role.position
        if user_.top_role.position >= hirarki_bot:
            return await ctx.send('Hirarki orang tersebut lebih tinggi.')

        js_['server'] = str(ctx.message.guild.id)
        js_['channel'] = str(ctx.message.channel.id)
        js_['timer'] = timer
        js_['limit'] = limit

        embed = discord.Embed(title="Vote Ban - {0.name}#{0.discriminator}".format(user_), description='React jika ingin user ini diban.', color=0x3f0a16)
        embed.add_field(name='Jumlah vote (Dibutuhkan: {})'.format(limit), value='0', inline=False)
        embed.add_field(name='Sisa waktu'.format(limit), value=f'{timer} detik', inline=False)
        emb_msg = await ctx.send(embed=embed)
        vote_data[str(emb_msg.id)] = js_

        await emb_msg.add_reaction('✅')
        await write_tally(v_, vote_data)


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

        vote_data = await read_tally(vote=True)
        usr_ava = ctx.message.author.avatar_url
        if not usr_ava:
            usr_ava = ctx.message.author.default_avatar_url

        embed = discord.Embed(title=message, colour=discord.Colour(0x36), description="Masukan pilihanmu dengan ngeklik reaction di bawah ini")

        embed.set_author(name='Voting oleh {}'.format(ctx.message.author.name), icon_url=usr_ava)
        embed.set_footer(text="Sisa Waktu: {} menit".format(round(timer / 60)))

        reactions = ['1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟']

        vote_d = dict()
        vote_list = dict()
        for x, option in enumerate(options):
            embed.add_field(name='{} {}'.format(reactions[x], option), value='Votes: 0', inline=False)
            ll = dict()
            ll['name'] = option
            ll['voter'] = []
            vote_list[str(x)] = ll

        vote_d['q'] = message
        vote_d['server'] = str(ctx.message.guild.id)
        vote_d['channel'] = str(ctx.message.channel.id)
        vote_d['timer'] = timer
        vote_d['options'] = vote_list

        emb_msg = await ctx.send(embed=embed)
        vote_data[str(emb_msg.id)] = vote_d

        for x, _ in enumerate(options):
            await emb_msg.add_reaction(reactions[x])

        await write_tally(v_, vote_data)

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

VoteCogs = [VotingSystem, VotingWatcher]

def setup(bot):
    for VoteC in VoteCogs:
        try:
            VoteCLoad = VoteC(bot)
            print('\t[#] Loading {} Commands...'.format(str(VoteCLoad)))
            bot.add_cog(VoteCLoad)
            print('\t[@] Loaded.')
        except Exception as ex:
            print('\t[!] Failed: {}'.format(str(ex)))
