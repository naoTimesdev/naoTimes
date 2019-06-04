# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import aiohttp
import discord
import discord.ext.commands as commands
import pytz

from bs4 import BeautifulSoup as BS4

def setup(bot):
    bot.add_cog(Anibin(bot))

async def query_take_first_result(query):
    print('Requesting page to anibin...')
    async with aiohttp.ClientSession() as sesi:
        async with sesi.get('http://anibin.blogspot.com/search?q={}'.format(query)) as resp:
            response = await resp.text()

    # Let's fiddle with the data
    soup_data = BS4(response, 'html.parser')
    first_query = soup_data.find('div', attrs={'class': 'date-posts'})

    # Query results
    query_title = first_query.find('h3', attrs={'class': 'post-title entry-title'}).text.strip()

    content_data = str(first_query.find('div', attrs={'class': 'post-body entry-content'}))
    n_from = content_data.find('評価:')
    if n_from == -1:
        return False, False, False
    nat_res = content_data[n_from + 3:]
    nat_res = nat_res[:nat_res.find('<br/>')]

    n_from2 = content_data.find('制作:')

    if n_from2 == -1:
        return [query_title, nat_res, 'Unknown']

    studio = content_data[n_from2 + 3:]
    studio = studio[:studio.find('<br/>')]

    return [query_title, nat_res, studio]


class Anibin:
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

    @commands.command(pass_context=True)
    async def anibin(self, ctx, *, query):
        """
        Mencari native resolution dari sebuah anime di anibin
        """
        server_message = str(ctx.message.server.id)
        print('Requested !anibin at: ' + server_message)

        search_title, search_native, search_studio = await query_take_first_result(query)

        if not search_title:
            return await self.bot.say('Tidak dapat menemukan anime yang diberikan, mohon gunakan kanji jika belum.')

        embed = discord.Embed(title="Anibin Native Resolution", color=0xffae00)
        embed.add_field(name=search_title, value=search_native, inline=False)
        #embed.add_field(name=last_text, value=last_status, inline=False)
        embed.set_footer(text="Studio Animasi: {}".format(search_studio))
        await self.bot.say(embed=embed)
