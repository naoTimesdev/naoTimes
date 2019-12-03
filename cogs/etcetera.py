import asyncio
import json
import os
from datetime import datetime

import aiohttp
import discord
import pytz
from discord.ext import commands

#### Text help section ####
simple_textdata = r"""```
<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin
```
"""

simple_textdata_fs = r"""```
<kode fansub>: Fansub yang didaftar ke list khusus secara manual (Cek dengan ketik "!tagihfs" saja)

<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin
```
"""

simpleplex_textdata = r"""```
<jumlah>: Jumlah episode yang mau dirilis (dari episode yang terakhir dirilis)
Misalkan lagi ngerjain Episode 4, terus mau rilis sampe episode 7
Total dari Episode 4 sampai 7 ada 4 (4, 5, 6, 7)
Maka tulis jumlahnya 4

<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin
```
"""

simpleplex_textdata2 = r"""```
<range>: Ranged number, bisa satu digit untuk 1 episode saja atau range dari episode x sampai y
Contoh: `4` untuk episode 4 || `4-6` untuk episode 4 sampai 6

<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin
```
"""

speedsub_help = r"""```
Tautkan/Tambahkan Attachments file .ass atau .srt dan isi pesannya dengan '!speedsub'

<kode bahasa>: Kode 2 huruf bahasa, silakan cari di google dengan query 'ISO 639-1'
```
"""

ubahstaff_textdata = r"""```
<id_staff>: Merupakan ID user discord per staff
Bisa diisi ID sendiri atau dirandom (ex: 123)
Cara ambilnya:
1. Nyalakan mode Developer di User Settings -> Appereance -> Developer Mode
2. Klik kanan nama usernya
3. Klik Copy ID
--> https://puu.sh/D3yTA/e11282996e.gif

<posisi>: tl, tlc, enc, ed, tm, ts, atau qc 
(Translator, Translation Checker, Encoder, Editor, Timer, Typesetter, Quality Checker)

<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin
```
"""

ubahrole_textdata = r"""```
<id_role>: ID Role tanpa `@&` khusus babu yang ngerjain anime ini 
(Mention role dengan tanda `\` ex: `\@Delayer`)
--> https://puu.sh/D3yVw/fd088611f3.gif

<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin
```
"""

animangavn_textdata = r"""```
<judul>: Judul anime ataupun manga yang ada di Anilist.co atau VN yang ada di vndb.org
```
"""

tanda_textdata = r"""```
<posisi>: tl, tlc, enc, ed, tm, ts, atau qc 
(Translator, Translation Checker, Encoder, Editor, Timer, Typesetter, Quality Checker)

<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin
```
"""

link_textdata = r"""```
<link>: URL yang ingin diamankan atau dipendekan.
URL harus ada 'https://' atau 'http://' sebagai awalan atau akan dianggap tidak valid

Jika ingin memakai pengaman disarankan memakai pemendek agar link lebih mudah diingat
```
"""

complex_textdata = r"""```
<anilist_id>: ID/Angka yang ada pada URL dari web anilist.co
> https://anilist.co/anime/101386/Hitoribocchi-no-Marumaru-Seikatsu/
`101386` merupakan ID nya

<total_ep>: Perkiraan total episode (Bisa diubah manual, silakan PM N4O#8868)

<id_role>: ID Role tanpa `@&` khusus babu yang ngerjain anime ini 
(Mention role dengan tanda `\` ex: `\@Delayer`)
--> https://puu.sh/D3yVw/fd088611f3.gif

<id_tlor sampai id_qcer>: Merupakan ID user discord per staff
Bisa diisi ID sendiri atau dirandom (ex: 123)
Cara ambilnya:
1. Nyalakan mode Developer di User Settings -> Appereance -> Developer Mode
2. Klik kanan nama usernya
3. Klik Copy ID
--> https://puu.sh/D3yTA/e11282996e.gif

Jika ada kesalahan PM N4O#8868
```
"""

tandakan_textdata = r"""```
<posisi>: tl, tlc, enc, ed, tm, ts, atau qc 
(Translator, Translation Checker, Encoder, Editor, Timer, Typesetter, Quality Checker)

<episode>: Episode yang ingin diubah tandanya

<judul>: Judul garapan yang terdaftar, bisa disingkat sesingkat mungkin

Note: Akan otomatis terubah dari `beres` ke `belum beres` atau sebaliknya jika command ini dipakai
Command ini tidak akan mengannounce perubahan ke channel publik
```
"""

with open('config.json', 'r') as fp:
    bot_config = json.load(fp)

def find_user_server(user_id, js_data):
    srv_list = []

    for i, _ in js_data.items():
        srv_list.append(i)

    srv_list.remove('supermod')

    srv_on_list = []

    for srv in srv_list:
        for mod in js_data[srv]['serverowner']:
            if mod == user_id:
                srv_on_list.append(srv)

    return int(srv_on_list[0])

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

def get_current_time() -> str:
    """
    Return current time in `DD Month YYYY HH:MM TZ (+X)` format
    """
    current_time = datetime.now(pytz.timezone('Asia/Jakarta'))

    def month_in_idn(datetime_fmt):
        x = datetime_fmt.strftime("%B")
        eng = ["January", "February", "March", "April",
                "May", "June", "July", "August",
                "September", "October", "November", "December"]
        idn = ["Januari", "Februari", "Maret", "April",
                "Mei", "Juni", "Juli", "Agustus",
                "September", "Oktober", "November", "Desember"]
        return idn[eng.index(x)]

    d = current_time.strftime("%d")
    m = month_in_idn(current_time)
    rest = current_time.strftime("%Y %H:%M %Z (+7)")

    return '{} {} {}'.format(d, m, rest)


class Helper(commands.Cog):
    """Helper module or etcetera module to show help and useless stuff"""
    def __init__(self, bot):
        self.bot = bot


    @commands.group(aliases=['bantuan'])
    async def help(self, ctx):
        if ctx.invoked_subcommand is None:
            helpmain = discord.Embed(title="Bantuan Perintah", description="versi 2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='!help', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!help showtimes', value="```Memunculkan bantuan perintah showtimes```", inline=False)
            helpmain.add_field(name='!help anilist', value="```Memunculkan bantuan perintah anilist```", inline=False)
            helpmain.add_field(name='!help parser', value="```Memunculkan bantuan perintah parser/webparsing```", inline=False)
            helpmain.add_field(name="!help fun", value="```Melihat bantuan perintah yang \"menyenangkan\"```", inline=False)
            if int(ctx.message.author.id) == int(bot_config['owner_id']):
                helpmain.add_field(name='!help admin', value="```Memunculkan bantuan perintah admin```", inline=False)
            helpmain.add_field(name="!help info", value="```Melihat Informasi bot```", inline=False)
            helpmain.add_field(name="!help vote/votekick/voteban", value="```Melihat Informasi vote system```", inline=False)
            helpmain.add_field(name="!help nyaa", value="```Melihat Informasi command untuk web Nyaa.si```", inline=False)
            helpmain.add_field(name="!help prefix <...>", value="```Per-server custom prefix (awalan untuk menjalankan perintah)```", inline=False)
            helpmain.add_field(name="!help ping", value="```pong!```", inline=False)
            helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)

    @help.command()
    @commands.is_owner()
    async def admin(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (Admin)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!supermotd', value="```Mengirimkan pesan berantai ke tiap admin fansub yang terdaftar di naoTimes```", inline=False)
        helpmain.add_field(name='!bundir', value="```Menyuruh bot untuk bundir```", inline=False)
        helpmain.add_field(name='!reinkarnasi', value="```Membunuh dan mematikan bot```", inline=False)
        helpmain.add_field(name='!reload <module>', value="```Mereload module tertentu```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def fun(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (Fun)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!ui <user>', value="```Melihat informasi user\n<user> itu opsional```", inline=False)
        helpmain.add_field(name='!avatar <user>', value="```Melihat avatar user\n<user> itu opsional```", inline=False)
        helpmain.add_field(name='!f <pesan>', value="```F\n<pesan> itu opsional```", inline=False)
        helpmain.add_field(name='!kerang <pertanyaan>', value="```Bertanya kepada kerang ajaib```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    @commands.is_owner()
    async def bundir(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!bundir)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!bundir', value="```Mematikan bot untuk maintenance atau semacamnya```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    @commands.is_owner()
    async def reinkarnasi(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!reinkarnasi)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!reinkarnasi', value="```Mematikan bot lalu menghidupkannya kembali ke Isekai```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    @commands.is_owner()
    async def reload(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!reload)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!reload <module>', value="```<module>: Nama module yang ingin direload.\nModule: etcetera, anilist, showtimes```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def showtimes(self, ctx):
        mode_n = 1
        first_run = True
        while True:
            if mode_n == 1:
                helpmain = discord.Embed(title="Bantuan Perintah (Showtimes) [1/2]", description="versi 2.0.0", color=0x00aaaa)
                helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
                helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
                helpmain.add_field(name='!tagih <judul>', value="```Menagih utang fansub tukang diley maupun tidak untuk memberikan mereka tekanan```", inline=False)
                helpmain.add_field(name='!jadwal', value="```Melihat jadwal anime musiman yang di ambil.```", inline=False)
                helpmain.add_field(name='!staff <judul>', value="```Melihat staff yang mengerjakan sebuah garapan```", inline=False)
                helpmain.add_field(name="!beres <posisi> <judul>", value="```Menandai salah satu tugas pendelay```", inline=False)
                helpmain.add_field(name="!gakjadi <posisi> <judul>", value="```Menghilangkan tanda salah satu tugas pendelay```", inline=False)
                helpmain.add_field(name="!rilis <...>", value="```Merilis garapan!```", inline=False)
                helpmain.add_field(name="!alias <...>", value="```Menambah, melihat, menghapus alias garaapan!```", inline=False)
                helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
                helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
                react_ext = ['⏩']
                if first_run:
                    first_run = False
                    emb_msg = await ctx.send(embed=helpmain)
                else:
                    emb_msg.edit(embed=helpmain)
                mode_n = 1
            elif mode_n == 2:
                helpmain = discord.Embed(title="Bantuan Perintah (Showtimes) [2/2]", description="versi 2.0.0", color=0x00aaaa)
                helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
                helpmain.add_field(name="!tambahutang <...>", value="```Menandai salah satu tugas pendelay```", inline=False)
                helpmain.add_field(name="!lupakanutang <judul>", value="```Melupakan (Drop!) utang lama buat utang baru```", inline=False)
                helpmain.add_field(name="!tambahepisode <jumlah> <judul>", value="```Menambah episode dari episode paling terakhir```", inline=False)
                helpmain.add_field(name="!hapusepisode <range> <judul>", value="```Menghapus episode tertentu dari database```", inline=False)
                helpmain.add_field(name="!ubahstaff <id_staff> <posisi> <judul>", value="```Mengubah staff yang mengerjakan suatu garapan```", inline=False)
                helpmain.add_field(name="!ubahrole <id_role> <judul>", value="```Mengubah role yang mengerjakan suatu garapan```", inline=False)
                helpmain.add_field(name="!tandakan <posisi> <episode> <judul>", value="```Mengubah status posisi untuk episode tertentu dari belum ke sudah atau sebaliknya```", inline=False)
                helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
                helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
                react_ext = ['⏪']
                emb_msg.edit(embed=helpmain)
                mode_n = 2

            for react in react_ext:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                return user == ctx.message.author and str(reaction.emoji) in react_ext

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=15.0, check=check_react)
            except asyncio.TimeoutError:
                return await emb_msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif '⏪' in str(res.emoji):
                await emb_msg.clear_reactions()
                mode_n = 1
            elif '⏩' in str(res.emoji):
                await emb_msg.clear_reactions()
                mode_n = 2

    @help.command()
    async def parser(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (Web Parsing)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!anibin <judul>', value="```Mencari tau resolusi asli sebuah anime lewat anibin```", inline=False)
        helpmain.add_field(name='!kbbi <kata>', value="```Mencari informasi kata di KBBI Daring```", inline=False)
        helpmain.add_field(name='!sinonim <kata>', value="```Mencari informasi sinonim di persamaankata.org```", inline=False)
        helpmain.add_field(name='!antonim <kata>', value="```Mencari informasi antonim di persamaankata.org```", inline=False)
        helpmain.add_field(name='!jisho <kata>', value="```Mencari informasi kata di Jisho```", inline=False)
        helpmain.add_field(name='!kurs <dari> <ke> <jumlah>', value="```Konversi satu mata uang ke mata uang lain seakurat mungkin```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def kbbi(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!kbbi)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!kbbi <kata>', value='```<kata> merupakan query yang akan dicari nanti```', inline=False)
        helpmain.add_field(name='Contoh', value="!kbbi contoh", inline=False)
        helpmain.add_field(name='Aliases', value="!kbbi", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)


    @help.command(aliases=['persamaankata', 'persamaan'])
    async def sinonim(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!sinonim)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!sinonim <kata>', value='```<kata> merupakan query yang akan dicari nanti```', inline=False)
        helpmain.add_field(name='Contoh', value="!sinonim duduk", inline=False)
        helpmain.add_field(name='Aliases', value="!sinonim, !persamaankata, !persamaan", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['lawankata'])
    async def antonim(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!antonim)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!antonim <kata>', value='```<kata> merupakan query yang akan dicari nanti```', inline=False)
        helpmain.add_field(name='Contoh', value="!antonim duduk", inline=False)
        helpmain.add_field(name='Aliases', value="!antonim, !lawankata", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['kanji'])
    async def jisho(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!jisho)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!jisho <kata>', value='```<kata> merupakan query yang akan dicari nanti```', inline=False)
        helpmain.add_field(name='Contoh', value="!jisho uchi", inline=False)
        helpmain.add_field(name='Aliases', value="!jisho, !kanji", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['konversiuang', 'currency'])
    async def kurs(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!kurs)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!kurs <dari> <ke> <jumlah>', value='```<dari> & <ke>: kode mata uang negara (3 huruf)\n<jumlah>: angka yang mau di konversi```', inline=False)
        helpmain.add_field(name='Contoh', value="!kurs jpy idr 500", inline=False)
        helpmain.add_field(name='Aliases', value="!kurs, !konversiuang, !currency", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['fastsub', 'gtlsub'])
    async def speedsub(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!speedsub)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!speedsub <kode bahasa>', value=speedsub_help, inline=False)
        helpmain.add_field(name='Contoh', value="!speedsub\n!speedsub jv (Translate ke jawa)", inline=False)
        helpmain.add_field(name='Aliases', value="!speedsub, !fastsub, !gtlsub", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['safelink'])
    async def pengaman(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!pengaman)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!pengaman <link>', value=speedsub_help, inline=False)
        helpmain.add_field(name='Contoh', value="!pengaman https://google.com", inline=False)
        helpmain.add_field(name='Aliases', value="!pengaman, !safelink", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['shorten'])
    async def pemendek(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!pemendek)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!pemendek <link>', value=speedsub_help, inline=False)
        helpmain.add_field(name='Contoh', value="!pemendek https://google.com", inline=False)
        helpmain.add_field(name='Aliases', value="!pemendek, !shorten", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def anilist(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (Anilist)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!anime <judul>', value="```Melihat informasi anime.```", inline=False)
        helpmain.add_field(name='!manga <judul>', value="```Melihat informasi manga.```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['animu', 'kartun'])
    async def anime(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!anime)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!anime <judul>', value=animangavn_textdata, inline=False)
        helpmain.add_field(name='Tambahan', value='⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** ✅ **(Selesai melihat)**\n⏳ **(Waktu Episode selanjutnya)** 👍 **(Melihat Info kembali)**', inline=False)
        helpmain.add_field(name='Contoh', value="```!anime hitoribocchi```", inline=False)
        helpmain.add_field(name='Aliases', value="!anime, !animu, !kartun, !ani", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['mango', 'komik'])
    async def manga(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!manga)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!manga <judul>', value=animangavn_textdata, inline=False)
        helpmain.add_field(name='Tambahan', value='⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** ✅ **(Selesai melihat)**', inline=False)
        helpmain.add_field(name='Contoh', value="```!manga hitoribocchi```", inline=False)
        helpmain.add_field(name='Aliases', value="!manga, !mango, !komik", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['vndb', 'visualnovel', 'eroge'])
    async def vn(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!vn)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!anime <judul>', value=animangavn_textdata, inline=False)
        helpmain.add_field(name='Tambahan', value='⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** 📸 **(Melihat screenshot)**\n✅ **(Melihat Info kembali)**', inline=False)
        helpmain.add_field(name='Contoh', value="```!vn steins;gate```", inline=False)
        helpmain.add_field(name='Aliases', value="!vn, !vndb, !visualnovel, !eroge", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def anibin(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!anibin)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name="!anibin <judul>", value=simple_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!anibin 私に天使が舞い降りた", inline=False)
        helpmain.add_field(name="Aliases", value="None (Tidak Ada)", inline=False)
        helpmain.add_field(name="Tambahan", value="Gunakan Kanji/Bahasa Jepangnya", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['blame', 'mana'])
    async def tagih(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!tagih)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!tagih <judul>', value=simple_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="```!tagih hitoribocchi```", inline=False)
        helpmain.add_field(name='Aliases', value="!tagih, !blame, !mana", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['airing'])
    async def jadwal(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!jadwal)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!jadwal', value="```Melihat jadwal anime musiman yang di ambil.```", inline=False)
        helpmain.add_field(name='Aliases', value="!jadwal, !airing", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['tukangdelay', 'pendelay'])
    async def staff(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!staff)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!staff <judul>', value=simple_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!staff hitoribocchi", inline=False)
        helpmain.add_field(name='Aliases', value="!staff, !tukangdelay, !pendelay", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['done'])
    async def beres(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!beres)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!beres <posisi> <judul>', value=tanda_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!beres enc hitoribocchi", inline=False)
        helpmain.add_field(name='Aliases', value="!beres, !done", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['undone', 'cancel'])
    async def gakjadi(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!gakjadi)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!gakjadi <posisi> <judul>', value=tanda_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!gakjadi enc hitoribocchi", inline=False)
        helpmain.add_field(name='Aliases', value="!gakjadi, !undone, !cancel", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['release'])
    async def rilis(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!rilis)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!rilis <judul>', value=simple_textdata, inline=False)
        helpmain.add_field(name='!rilis batch <jumlah> <judul>', value=simpleplex_textdata, inline=False)
        helpmain.add_field(name='!rilis semua <judul>', value=simple_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!rilis hitoribocchi\n!rilis batch 3 hitoribocchi\n!rilis semua hitoribocchi", inline=False)
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipake tukang QC dan Admin\n!rilis semua akan merilis episode terakhir yang dirilis sampai habis", inline=False)
        helpmain.add_field(name='Aliases', value="!rilis, !release", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def alias(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!alias)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!alias', value='```Tambahkan alias baru dengan command ini, cukup jalankan `!alias` untuk memulai proses```', inline=False)
        helpmain.add_field(name='!alias list <judul>', value=simple_textdata, inline=False)
        helpmain.add_field(name='!alias hapus <judul>', value=simple_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!alias\n!alias list hitoribocchi\n!alias hapus hitoribocchi", inline=False)
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipakai oleh Admin\n!alias list dan hapus hanya bisa memakai judul asli bukan aliasnya", inline=False)
        helpmain.add_field(name='Aliases', value="**!alias**: Tidak ada\n**!alias list**: Tidak ada\n**!alias hapus**: !alias remove", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def tambahepisode(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!tambahepisode)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!tambahepisode <jumlah> <judul>', value=simpleplex_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!tambahepisode 3 hitoribocchi", inline=False)
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipake oleh Admin", inline=False)
        helpmain.add_field(name='Aliases', value="None (Tidak ada)", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['hapus'])
    async def hapusepisode(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!hapusepisode)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!hapusepisode <range> <judul>', value=simpleplex_textdata2, inline=False)
        helpmain.add_field(name="Contoh", value="!hapusepisode 13 hitoribocchi\n!hapusepisode 13-14 hitoribocchi", inline=False)
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipake oleh Admin", inline=False)
        helpmain.add_field(name='Aliases', value="!hapusepisode, !hapus", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def ubahstaff(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!ubahstaff)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!ubahstaff <id_staff> <posisi> <judul>', value=ubahstaff_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!ubahstaff 499999999 tl tate", inline=False)
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipake oleh Admin", inline=False)
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def ubahrole(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!ubahrole)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!ubahrole <id_role> <judul>', value=ubahrole_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!ubahrole 564112534530031655 tate", inline=False)
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipake oleh Admin", inline=False)
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['mark'])
    async def tandakan(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!tandakan)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!tandakan <posisi> <episode> <judul>', value=tandakan_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!tandakan tl 3 tate", inline=False)
        helpmain.add_field(name='Aliases', value="!tandakan, !mark", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['add', 'tambah'])
    async def tambahutang(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!tambahutang)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!tambahutang', value="Jalankan dan masukan semua info dan ubah sebelum menambah ke database", inline=False)
        helpmain.add_field(name="Contoh", value="!tambahutang", inline=False)
        helpmain.add_field(name='Aliases', value="!tambahutang, !add, !tambah", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['buangutang', 'buang', 'lupakan', 'remove', 'drop'])
    async def lupakanutang(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!lupakanutang)", description="versi 1.3.5", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!lupakanutang <judul>', value=simple_textdata, inline=False)
        helpmain.add_field(name="Contoh", value="!lupakanutang hitoribocchi", inline=False)
        helpmain.add_field(name='Aliases', value="!lupakanutang, !buangutang, !buang, !lupakan, !remove, !drop", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def vote(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!vote)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!vote <judul> <timer> <opsi>', value="```<judul>: Judul voting (Gunakan kutip dua)\n<timer>: Waktu pengumpulan vote sebelum proses (Default: 3 menit, minimum: 3 menit)\n<opsi>: Pilihan, dapat ditulis sampai 10 opsi (Gunakan kutip dua)```", inline=False)
        helpmain.add_field(name="Contoh", value="!vote \"Mi Instan Terbaik\" 5 \"Indomie\" \"Mie Sedap\" \"Sarimi\" \"Lain-Lain\"", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def votekick(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!votekick)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!votekick <user> <limit> <timer>', value="```Melakukan votekick\n<user>: mention atau ketik IDnya\n<limit>: limit orang yang harus react (Default: 5, minimum: 5)\n<timer>: waktu pengumpulan vote sebelum proses (Default: 60 detik, minimum: 30 detik)```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def voteban(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!voteban)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!voteban <user> <limit> <timer>', value="```Melakukan voteban\n<user>: mention atau ketik IDnya\n<limit>: limit orang yang harus react (Default: 5, minimum: 5)\n<timer>: waktu pengumpulan vote sebelum proses (Default: 60 detik, minimum: 30 detik)```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def nyaa(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nyaa)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nyaa', value="```Memunculkan bantuan perintah```", inline=False)
        helpmain.add_field(name='!nyaa cari <argumen>', value="```Mencari torrent di nyaa.si (gunakan argumen -h untuk melihat bantuan)```", inline=False)
        helpmain.add_field(name='!nyaa terbaru <argumen>', value="```Melihat 10 torrents terbaru (gunakan argumen -h untuk melihat bantuan)```", inline=False)
        helpmain.add_field(name='!nyaa kategori <tipe>', value="```Melihat kategori apa aja yang bisa dipakai\n<tipe> ada 2 yaitu, normal dan sukebei```", inline=False)
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def perpus(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!perpus)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!perpus', value="```Memunculkan bantuan perintah```", inline=False)
        helpmain.add_field(name='!perpus cari <argumen>', value="```Mencari berkas di perpusindo.info (gunakan argumen -h untuk melihat bantuan)```", inline=False)
        helpmain.add_field(name='!perpus terbaru <argumen>', value="```Melihat 10 berkas terbaru (gunakan argumen -h untuk melihat bantuan)```", inline=False)
        helpmain.add_field(name='!perpus kategori', value="```Melihat kategori apa aja yang bisa dipakai```", inline=False)
        helpmain.add_field(name='Aliases', value="!perpus, !perpusindo, !pi", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def nh(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nh)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nyaa', value="```Memunculkan bantuan perintah```", inline=False)
        helpmain.add_field(name='!nyaa cari <argumen>', value="```Mencari torrent di nyaa.si (gunakan argumen -h untuk melihat bantuan)```", inline=False)
        helpmain.add_field(name='!nyaa terbaru <argumen>', value="```Melihat 10 torrents terbaru (gunakan argumen -h untuk melihat bantuan)```", inline=False)
        helpmain.add_field(name='!nyaa kategori <tipe>', value="```Melihat kategori apa aja yang bisa dipakai\n<tipe> ada 2 yaitu, normal dan sukebei```", inline=False)
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def info(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!info)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!info', value="Melihat Informasi bot ini", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def prefix(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!prefix)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!prefix <prefix>', value="Menambah server custom prefix baru ke server ini\nLihat custom prefix server dengan ketik `!prefix`", inline=False)
        helpmain.add_field(name='!prefix clear', value="Menghapus server custom prefix dari server ini", inline=False)
        helpmain.add_field(name='Minimum Permission', value="- Manage Server")
        helpmain.add_field(name='Aliases', value="!prefix\n!prefix clear, !prefix hapus, !prefix bersihkan", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def ping(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!ping)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!ping', value="Melihat cepat rambat koneksi dari server ke discord dan ke github", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @commands.command(aliases=['invite'])
    async def undang(self, ctx):
        invi = discord.Embed(title="Ingin invite Bot ini? Klik link di bawah ini!", description="[Invite](https://ihateani.me/andfansub)\n[Support Server](https://discord.gg/eJR3X9K)", color=0x1)
        invi.set_thumbnail(url="https://p.n4o.xyz/i/naotimes_ava.png")
        await ctx.send(embed=invi)

    @commands.command()
    @commands.guild_only()
    async def supermotd(self, ctx):
        if int(ctx.message.author.id) != int(bot_config['owner_id']):
            print('@@ Someone want to use supermotd but not the bot owner, ignoring...')
            print('@@ User that are trying to use it: ' + str(ctx.message.author.id))
            return

        print('@@ Super MOTD Activated')
        json_data = await fetch_json()
        if not json_data:
            return

        mod_list = json_data['supermod']

        starting_messages = await ctx.send('**Initiated Super MOTD, please write the content below**\n*Type `cancel` to cancel*')

        def check(m):
            return m.author == ctx.message.author

        motd_content = await self.bot.wait_for('message', check=check)

        if motd_content.content == ("cancel"):
            print('@@ MOTD Cancelled')
            return await ctx.send('**MOTD Message announcement cancelled.**')

        print('MOTD Content:\n{}'.format(motd_content.content))
        await starting_messages.edit('**Initiated Super MOTD, please write the content below**')

        preview_msg = await ctx.send('**MOTD Preview**\n```{}```\nAre you sure want to send this message?'.format(motd_content.content))
        to_react = ['✅', '❌']
        for reaction in to_react:
            await preview_msg.add_reaction(reaction)
        def checkReaction(reaction, user):
            return user == ctx.message.author and str(reaction.emoji) in to_react

        try:
            res, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=checkReaction)
        except asyncio.TimeoutError:
            await ctx.send('***Timeout!***')
            return await preview_msg.clear_reactions()
        if '✅' in str(res.emoji):
            print('@@ Sending MOTD')
            await preview_msg.clear_reactions()
            preview_msg = preview_msg.edit('**Sending to every admin...**')
            success_rate = 0
            failed_user = []
            for mod in mod_list:
                print('@@ Sending to: {}'.format(mod))
                try:
                    server_mod = find_user_server(mod, json_data)
                    server_in = self.bot.get_guild(server_mod)
                    srv_mod = server_in.get_member(int(mod))
                    await srv_mod.send("**Announcement dari N4O#8868 (Bot Owner):**\n\n{}\n\n*Pada: {}*".format(motd_content.content, get_current_time()))
                    success_rate += 1
                    print('@@ Success')
                except:
                    failed_user.append(mod)
                    print('@@ Failed')
            await preview_msg.edit('**Done! {}/{} user get the message**'.format(success_rate, len(mod_list)))
            if failed_user:
                print('Failed user list: {}'.format(', '.join(failed_user)))
        elif '❌' in str(res.emoji):
            print('@@ MOTD Cancelled')
            await preview_msg.clear_reactions()
            await preview_msg.edit('**MOTD Message announcement cancelled.**')


    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_server=True)
    async def prefix(self, ctx, *, msg=None):
        server_message = str(ctx.message.guild.id)
        print('Requested !prefix at: ' + server_message)
        with open('prefixes.json') as fp:
            prefix_data = json.load(fp)

        if not msg:
            helpmain = discord.Embed(title="Prefix", description="versi 2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='Prefix Server', value=prefix_data.get(server_message, 'Tidak ada'), inline=False)
            helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
            return await ctx.send(embed=helpmain)

        if msg in ['clear', 'bersihkan', 'hapus']:
            print(prefix_data)
            if server_message in prefix_data:
                print('@@ Server prefix exist, deleting...')
                del prefix_data[server_message]

                with open('prefixes.json', 'w') as fp:
                    json.dump(prefix_data, fp)

            return await ctx.send('Berhasil menghapus custom prefix dari server ini')

        if server_message in prefix_data:
            print('@@ Changing server prefix...')
            send_txt = 'Berhasil mengubah custom prefix ke `{pre_}` untuk server ini'
        else:
            print('@@ Adding server prefix')
            send_txt = 'Berhasil menambah custom prefix `{pre_}` untuk server ini'
        prefix_data[server_message] = msg

        with open('prefixes.json', 'w') as fp:
            json.dump(prefix_data, fp)

        await ctx.send(send_txt.format(pre_=msg))

    @prefix.error
    async def prefix_error(self, error, ctx):
        if isinstance(error, commands.errors.CheckFailure):
            server_message = str(ctx.message.guild.id)
            with open('prefixes.json') as fp:
                prefix_data = json.load(fp)
            helpmain = discord.Embed(title="Prefix", description="versi 2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='Prefix Server', value=prefix_data.get(server_message, 'Tidak ada'), inline=False)
            helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)


def setup(bot):
    bot.add_cog(Helper(bot))
