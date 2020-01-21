# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import json
import os

import aiohttp
import discord
import discord.ext.commands as commands
from datetime import datetime
from urllib.parse import quote_plus

def setup(bot):
    bot.add_cog(SafelinkBypass(bot))

class SafelinkBypass(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['miskinkan', 'lewati'])
    async def bypass(self, ctx, *, uri: str):
        message = await ctx.send('Memulai proses bypass, mohon tunggu.')
        if uri.startswith('<') and uri.endswith('>'):
            uri = uri[1:-1]
        uri = quote_plus(uri)
        pecahkan = 'https://s.ihateani.me/api/pemecah/{url}'
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=500)) as sesi:
            async with sesi.get(pecahkan.format(url=uri)) as resp:
                try:
                    response = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError as cterr:
                    return await ctx.send('Terjadi kesalahan ketika menghubungi server.')
                if resp.status != 200:
                    error_msg = response['message']
                    if 'tidak didukung' in error_msg:
                        format_fs = ["- **{}**".format(i.capitalize()) for i in response['supported_web']]
                        error_msg = "{}\n{}".format(error_msg, "\n".join(format_fs))
                    return await ctx.send(error_msg)

        amount_final = len(response['hasil'])
        url_final = response['url']
        hasil_data = response['hasil'][:18]

        async def generate_embed(dataset):
            embed = discord.Embed(title="Safelink Bypass", description='<{}>\nFormat: **{}**'.format(url_final, dataset['format']), color=0x7396aa)
            if dataset['berkas']:
                for nama, url in dataset['berkas'].items():
                    if not url:
                        url = 'Proses'
                    else:
                        url = '[Klik]({})'.format(url)
                    embed.add_field(name=nama, value=url, inline=True)
            else:
                embed.add_field(name="Pesan", value="Sedang di proses dari pihak \"Fansub\"")
            embed.set_footer(text="Diprakasai dengan s.ihateani.me")
            return embed

        await message.delete()

        emote_list = [
            '1️⃣',
            '2️⃣',
            '3️⃣',
            '4️⃣',
            '5️⃣',
            '6️⃣',
            '7️⃣',
            '8️⃣',
            '9️⃣',
            '0️⃣',
            '🇦',
            '🇧',
            '🇨',
            '🇩',
            '🇪',
            '🇫',
            '🇬',
            '🇭'
        ]

        first_time = True
        melihat_listing = False
        num = 0
        while True:
            if first_time:
                embed = discord.Embed(title="Safelink Bypass", description="<{}>".format(url_final), color=0x7396aa)
                val = ''
                for n, data in enumerate(hasil_data):
                    val += "{em} **{fmt}**\n".format(em=emote_list[n], fmt=data['format'])
                embed.add_field(name="List Format", value=val)
                embed.set_footer(text="Diprakasai dengan s.ihateani.me")

                first_time = False
                msg = await ctx.send(embed=embed)

            if melihat_listing:
                amount_to_use = 0
            else:
                amount_to_use = amount_final

            emotes = emote_list[:amount_to_use]
            emotes.append('✅')

            for react in emotes:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in emotes:
                    return False
                return True

            res, user = await self.bot.wait_for('reaction_add', check=check_react)
            if user != ctx.message.author:
                pass
            elif '✅' in str(res.emoji):
                await msg.clear_reactions()
                if melihat_listing:
                    embed = discord.Embed(title="Safelink Bypass", description=url_final, color=0x7396aa)
                    val = ''
                    for n, data in enumerate(hasil_data):
                        val += "{em} **{fmt}**\n".format(em=emote_list[n], fmt=data['format'])
                    embed.add_field(name="List Format", value=val)
                    embed.set_footer(text="Diprakasai dengan s.ihateani.me")

                    melihat_listing = False
                    await msg.edit(embed=embed)
                else:
                    await msg.delete()
                    return await ctx.message.delete()
            elif emote_list[0] in str(res.emoji):
                await msg.clear_reactions()
                num = 0
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[1] in str(res.emoji):
                await msg.clear_reactions()
                num = 1
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[2] in str(res.emoji):
                await msg.clear_reactions()
                num = 2
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[3] in str(res.emoji):
                await msg.clear_reactions()
                num = 3
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[4] in str(res.emoji):
                await msg.clear_reactions()
                num = 4
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[5] in str(res.emoji):
                await msg.clear_reactions()
                num = 5
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[6] in str(res.emoji):
                await msg.clear_reactions()
                num = 6
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[7] in str(res.emoji):
                await msg.clear_reactions()
                num = 7
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[8] in str(res.emoji):
                await msg.clear_reactions()
                num = 8
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[9] in str(res.emoji):
                await msg.clear_reactions()
                num = 9
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[10] in str(res.emoji):
                await msg.clear_reactions()
                num = 10
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[11] in str(res.emoji):
                await msg.clear_reactions()
                num = 11
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[12] in str(res.emoji):
                await msg.clear_reactions()
                num = 12
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[13] in str(res.emoji):
                await msg.clear_reactions()
                num = 13
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[14] in str(res.emoji):
                await msg.clear_reactions()
                num = 14
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[15] in str(res.emoji):
                await msg.clear_reactions()
                num = 15
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[16] in str(res.emoji):
                await msg.clear_reactions()
                num = 16
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            elif emote_list[17] in str(res.emoji):
                await msg.clear_reactions()
                num = 17
                melihat_listing = True
                embed = await generate_embed(hasil_data[num])
                await msg.edit(embed=embed)
            else:
                await msg.clear_reactions()