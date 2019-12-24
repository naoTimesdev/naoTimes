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

simplex_ubahdata = r"""```
Mengatur ulang isi data dari sebuah judul
Terdapat 5 mode:
    - Ubah Staff
    - Ubah Role
    - Tambah Episode
    - Hapus Episode
    - (!) Drop

Ubah data merupakan tipe command yang interaktif.
```"""

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
    print('[@] Opening json file')
    if not os.path.isfile('nao_showtimes.json'):
        print('[@] naoTimes are not initiated, skipping.')
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
            if ctx.message.author.id == self.bot.owner.id:
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
        helpmain.add_field(name='!pilih <input>', value="```Menyuruh bot untuk memilih jawaban```", inline=False)
        helpmain.add_field(name='!8ball <pertanyaan>', value="```Bertanya kepada bola 8 ajaib```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['user', 'uinfo', 'userinfo'])
    async def ui(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!ui)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!ui <user>', value="```Melihat informasi user\n<user> bisa ketik namanya, atau mention orangnya, atau ketik ID usernya.```", inline=False)
        helpmain.add_field(name='Contoh', value="!ui N4O\n!ui @N4O\n!ui 466469077444067372", inline=False)
        helpmain.add_field(name='Aliases', value="!ui, !user, !uinfo, !userinfo", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['pp', 'profile', 'bigprofile', 'ava'])
    async def avatar(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!avatar)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!avatar <user>', value="```Melihat profile picture user\n<user> bisa ketik namanya, atau mention orangnya, atau ketik ID usernya.```", inline=False)
        helpmain.add_field(name='Contoh', value="!avatar N4O\n!avatar @N4O\n!avatar 466469077444067372", inline=False)
        helpmain.add_field(name='Aliases', value="!avatar, !pp, !profile, !bigprofile, !ava", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def f(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!f)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!f <pesan>', value="```Press F to pay respect.\n<pesan> itu opsional.```", inline=False)
        helpmain.add_field(name='Contoh', value="!f\n!f dislike youtube rewind", inline=False)
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['kerangajaib'])
    async def kerang(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!kerang)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!kerang <pertanyaan>', value="```Menanyakan <pertanyaan> kepada kerang ajaib.```", inline=False)
        helpmain.add_field(name='Contoh', value="!kerang apakah saya bisa membereskan utang saya hari ini juga?", inline=False)
        helpmain.add_field(name='Aliases', value="!kerang, !kerangajaib", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def pilih(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!kerang)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!pilih <pilihan>', value="```<pilihan> dipisah dengan koma (,)\nminimal ada 2 pilihan```", inline=False)
        helpmain.add_field(name='Contoh', value="!pilih tidur, ngesub, nonton anime, baca manga", inline=False)
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(name="8ball")
    async def _8ball(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!8ball)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!8ball <pertanyaan>', value="```Menanyakan <pertanyaan> kepada bola 8 ajaib```", inline=False)
        helpmain.add_field(name='Contoh', value="!8ball apakah saya bisa membereskan utang saya hari ini juga?", inline=False)
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
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
        helpmain = discord.Embed(title="Bantuan Perintah (Showtimes)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!tagih <judul>', value="```Menagih utang fansub tukang diley maupun tidak untuk memberikan mereka tekanan```", inline=False)
        helpmain.add_field(name='!jadwal', value="```Melihat jadwal anime musiman yang di ambil.```", inline=False)
        helpmain.add_field(name='!staff <judul>', value="```Melihat staff yang mengerjakan sebuah garapan```", inline=False)
        helpmain.add_field(name="!beres <posisi> <judul>", value="```Menandai salah satu tugas pendelay```", inline=False)
        helpmain.add_field(name="!gakjadi <posisi> <judul>", value="```Menghilangkan tanda salah satu tugas pendelay```", inline=False)
        helpmain.add_field(name="!rilis <...>", value="```Merilis garapan!```", inline=False)
        helpmain.add_field(name="!alias <...>", value="```Menambah, melihat, menghapus alias garaapan!```", inline=False)
        helpmain.add_field(name="!tambahutang <...>", value="```Menandai salah satu tugas pendelay```", inline=False)
        helpmain.add_field(name="!ubahdata <judul>", value="```Mengubah informasi data suatu garapan```", inline=False)
        helpmain.add_field(name="!tandakan <posisi> <episode> <judul>", value="```Mengubah status posisi untuk episode tertentu dari belum ke sudah atau sebaliknya```", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)
 
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
        helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
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
        helpmain.add_field(name='!vn <judul>', value=animangavn_textdata, inline=False)
        helpmain.add_field(name='Tambahan', value='⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** 📸 **(Melihat screenshot)**\n✅ **(Melihat Info kembali)**', inline=False)
        helpmain.add_field(name='Contoh', value="```!vn steins;gate```", inline=False)
        helpmain.add_field(name='Aliases', value="!vn, !vndb, !visualnovel, !eroge", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command(aliases=['randomvisualnovel', 'randomeroge', 'vnrandom'])
    async def randomvn(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!vn)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!randomvn', value="```Melihat VN random```", inline=False)
        helpmain.add_field(name='Tambahan', value='⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** 📸 **(Melihat screenshot)**\n✅ **(Melihat Info kembali)**', inline=False)
        helpmain.add_field(name='Contoh', value="```!randomvn```", inline=False)
        helpmain.add_field(name='Aliases', value="!randomvn, !randomvisualnovel, !randomeroge, !vnrandom", inline=False)
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
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipakai tukang QC dan Admin\n!rilis semua akan merilis episode terakhir yang dirilis sampai habis", inline=False)
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
    async def ubahdata(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!ubahdata)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!ubahdata <judul>', value=simplex_ubahdata, inline=False)
        helpmain.add_field(name="Contoh", value="!ubahdata hitoribocchi", inline=False)
        helpmain.add_field(name="Tambahan", value="Hanya bisa dipakai oleh Admin", inline=False)
        helpmain.add_field(name='Aliases', value="None (Tidak ada)", inline=False)
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
        helpmain.add_field(name="Contoh", value="!votekick @N4O\n!votekick 466469077444067372", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.command()
    async def voteban(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!voteban)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!voteban <user> <limit> <timer>', value="```Melakukan voteban\n<user>: mention atau ketik IDnya\n<limit>: limit orang yang harus react (Default: 5, minimum: 5)\n<timer>: waktu pengumpulan vote sebelum proses (Default: 60 detik, minimum: 30 detik)```", inline=False)
        helpmain.add_field(name="Contoh", value="!voteban @N4O\n!voteban 466469077444067372", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.group(name='nyaa')
    async def nyaahelp(self, ctx):
        if not ctx.invoked_subcommand:
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

    @nyaahelp.command(aliases=['search'])
    async def cari(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nyaa cari)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nyaa cari <opsi> <pencarian>', value="```Mencari sesuatu dari nyaa, opsi dapat dilihat dengan:\n!nyaa cari -h```", inline=False)
        helpmain.add_field(name="Contoh", value="!nyaa cari -C anime --trusted -u HorribleSubs \"Hitoribocchi\"", inline=False)
        helpmain.add_field(name='Aliases', value="!nyaa cari, !nyaa search", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @nyaahelp.command(aliases=['latest'])
    async def terbaru(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nyaa terbaru)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nyaa terbaru <opsi>', value="```Melihat 10 torrent terbaru dari nyaa, opsi dapat dilihat dengan:\n!nyaa terbaru -h```", inline=False)
        helpmain.add_field(name="Contoh", value="!nyaa terbaru -C anime --trusted -u HorribleSubs", inline=False)
        helpmain.add_field(name='Aliases', value="!nyaa terbaru, !nyaa latest", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @nyaahelp.command(aliases=['category'])
    async def kategori(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nyaa cari)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nyaa katergori <tipe>', value="```Melihat kategori\n<tipe> ada 2 yaitu:\n- normal\n- sukebei```", inline=False)
        helpmain.add_field(name="Contoh", value="!nyaa kategori normal\n!nyaa kategori sukebei", inline=False)
        helpmain.add_field(name='Aliases', value="!nyaa kategori, !nyaa category", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.group(name='perpus', aliases=['pi', 'perpusindo'])
    async def perpushelp(self, ctx):
        if not ctx.invoked_subcommand:
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

    @perpushelp.command(aliases=['search'])
    async def cari(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!perpus cari)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!perpus cari <opsi> <pencarian>', value="```Mencari sesuatu dari PerpusIndo, opsi dapat dilihat dengan:\n!perpus cari -h```", inline=False)
        helpmain.add_field(name="Contoh", value="!perpus cari -C audio --trusted -u N4O \"FLAC\"", inline=False)
        helpmain.add_field(name='Aliases', value="!perpus cari, !perpus search", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @perpushelp.command(aliases=['latest'])
    async def terbaru(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!perpus terbaru)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!perpus terbaru <opsi>', value="```Melihat 10 berkas terbaru dari PerpusIndo, opsi dapat dilihat dengan:\n!nyaa terbaru -h```", inline=False)
        helpmain.add_field(name="Contoh", value="!perpus terbaru -C audio --trusted -u N4O", inline=False)
        helpmain.add_field(name='Aliases', value="!perpus terbaru, !perpus latest", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @perpushelp.command(aliases=['category'])
    async def kategori(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!perpus kategori)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!perpus katergori', value="```Melihat kategori```", inline=False)
        helpmain.add_field(name="Contoh", value="!perpus kategori", inline=False)
        helpmain.add_field(name='Aliases', value="!perpus kategori, !perpus category", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @help.group(name='nh')
    async def nh_help(self, ctx):
        if not ctx.invoked_subcommand:
            helpmain = discord.Embed(title="Bantuan Perintah (!nh)", description="versi 2.0.0", color=0x00aaaa)
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            helpmain.add_field(name='!nh atau !help nh', value="```Memunculkan bantuan perintah```", inline=False)
            helpmain.add_field(name='!nh cari <query>', value="```Mencari kode nuklir.```", inline=False)
            helpmain.add_field(name='!nh info <kode>', value="```Melihat informasi kode nuklir.```", inline=False)
            helpmain.add_field(name='!nh baca <kode>', value="```Membaca langsung kode nuklir.```", inline=False)
            helpmain.add_field(name='!nh unduh <kode>', value="```Mendownload kode nuklir dan dijadikan .zip file (limit file adalah 3 hari sebelum dihapus dari server).```", inline=False)
            helpmain.add_field(name='Aliases', value="Tidak ada", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)

    @nh_help.command(aliases=['search'])
    async def cari(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nh cari)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nh cari <pencarian>', value="```Mencari <pencarian> di nHentai\nFitur pencarian 1:1 dengan fitur pencarian dari nHentainya langsung.```", inline=False)
        helpmain.add_field(name="Contoh", value="!nh cari \"females only\"\n!nh cari \"hibike euphonium\"\n!nh cari metamorphosis", inline=False)
        helpmain.add_field(name='Aliases', value="!nh cari, !nh search", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @nh_help.command(name='info', aliases=['informasi'])
    async def infonh(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nh info)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nh info <kode_nuklir>', value="```Mencari informasi tentang <kode_nuklir> di nHentai```", inline=False)
        helpmain.add_field(name="Contoh", value="!nh info 177013\n!nh info 290691", inline=False)
        helpmain.add_field(name='Aliases', value="!nh info, !nh informasi", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @nh_help.command(aliases=['read'])
    async def baca(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nh baca)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nh baca <kode_nuklir>', value="```Membaca langsung dari Discord\nGambar akan di proxy agar tidak kena efek blok internet positif\nMaka dari itu, gambar akan butuh waktu untuk di cache\nSemakin banyak gambar, semakin lama.```", inline=False)
        helpmain.add_field(name="Contoh", value="!nh baca 177013\n!nh baca 290691", inline=False)
        helpmain.add_field(name='Aliases', value="!nh baca, !nh read", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
        helpmain.set_footer(text="Dibawakan oleh naoTimes || Dibuat oleh N4O#8868 versi 2.0.0")
        await ctx.send(embed=helpmain)

    @nh_help.command(aliases=['down', 'dl', 'download'])
    async def unduh(self, ctx):
        helpmain = discord.Embed(title="Bantuan Perintah (!nh unduh)", description="versi 2.0.0", color=0x00aaaa)
        helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
        helpmain.set_author(name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
        helpmain.add_field(name='!nh unduh <kode_nuklir>', value="```Mengunduh <kode_nuklir>\nJika gambar belum sempat di proxy, akan memakan waktu lebih lama\nDisarankan menggunakan command !nh baca baru !nh unduh```", inline=False)
        helpmain.add_field(name="Contoh", value="!nh unduh 177013\n!nh unduh 290691", inline=False)
        helpmain.add_field(name='Aliases', value="!nh unduh, !nh down, !nh dl, !nh download", inline=False)
        helpmain.add_field(name="*Catatan*", value="Semua command bisa dilihat infonya dengan !help <nama command>", inline=False)
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
        invi = discord.Embed(title="Ingin invite Bot ini? Klik link di bawah ini!", description="[Invite](https://ihateani.me/andfansub)\n[Support Server](https://discord.gg/UNXukwt)", color=0x1)
        invi.set_thumbnail(url="https://p.n4o.xyz/i/naotimes_ava.png")
        await ctx.send(embed=invi)

    @commands.command()
    @commands.guild_only()
    async def supermotd(self, ctx):
        if ctx.message.author.id != self.bot.owner.id:
            print('[@] Someone want to use supermotd but not the bot owner, ignoring...')
            print('[@] User that are trying to use it: ' + str(ctx.message.author.id))
            return

        print('[@] Super MOTD Activated')
        json_data = await fetch_json()
        if not json_data:
            return

        mod_list = json_data['supermod']

        starting_messages = await ctx.send('**Initiated Super MOTD, please write the content below**\n*Type `cancel` to cancel*')

        def check(m):
            return m.author == ctx.message.author

        motd_content = await self.bot.wait_for('message', check=check)

        if motd_content.content == ("cancel"):
            print('[@] MOTD Cancelled')
            return await ctx.send('**MOTD Message announcement cancelled.**')

        print('MOTD Content:\n{}'.format(motd_content.content))
        await starting_messages.edit('**Initiated Super MOTD, please write the content below**')

        preview_msg = await ctx.send('**MOTD Preview**\n```{}```\nAre you sure want to send this message?'.format(motd_content.content))
        to_react = ['✅', '❌']
        for reaction in to_react:
            await preview_msg.add_reaction(reaction)

        def check_react(reaction, user):
            if reaction.message.id != preview_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        try:
            res, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check_react)
        except asyncio.TimeoutError:
            await ctx.send('***Timeout!***')
            return await preview_msg.clear_reactions()
        if '✅' in str(res.emoji):
            print('[@] Sending MOTD')
            await preview_msg.clear_reactions()
            preview_msg = preview_msg.edit('**Sending to every admin...**')
            success_rate = 0
            failed_user = []
            for mod in mod_list:
                print('[@] Sending to: {}'.format(mod))
                try:
                    server_mod = find_user_server(mod, json_data)
                    server_in = self.bot.get_guild(server_mod)
                    srv_mod = server_in.get_member(int(mod))
                    await srv_mod.send("**Announcement dari N4O#8868 (Bot Owner):**\n\n{}\n\n*Pada: {}*".format(motd_content.content, get_current_time()))
                    success_rate += 1
                    print('[@] Success')
                except:
                    failed_user.append(mod)
                    print('[@] Failed')
            await preview_msg.edit('**Done! {}/{} user get the message**'.format(success_rate, len(mod_list)))
            if failed_user:
                print('Failed user list: {}'.format(', '.join(failed_user)))
        elif '❌' in str(res.emoji):
            print('[@] MOTD Cancelled')
            await preview_msg.clear_reactions()
            await preview_msg.edit('**MOTD Message announcement cancelled.**')


    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_server=True)
    async def prefix(self, ctx, *, msg=None):
        server_message = str(ctx.message.guild.id)
        print('Requested !prefix at: ' + server_message)
        if not os.path.isfile('prefixes.json'):
            prefix_data = {}
            print('[#] Creating prefixes.json')
            with open('prefixes.json', 'w') as fw:
                json.dump({}, fw)
        else:
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
                print('[@] Server prefix exist, deleting...')
                del prefix_data[server_message]

                with open('prefixes.json', 'w') as fp:
                    json.dump(prefix_data, fp)

            return await ctx.send('Berhasil menghapus custom prefix dari server ini')

        if server_message in prefix_data:
            print('[@] Changing server prefix...')
            send_txt = 'Berhasil mengubah custom prefix ke `{pre_}` untuk server ini'
        else:
            print('[@] Adding server prefix')
            send_txt = 'Berhasil menambah custom prefix `{pre_}` untuk server ini'
        prefix_data[server_message] = msg

        with open('prefixes.json', 'w') as fp:
            json.dump(prefix_data, fp)

        await ctx.send(send_txt.format(pre_=msg))

    @prefix.error
    async def prefix_error(self, error, ctx):
        if isinstance(error, commands.errors.CheckFailure):
            server_message = str(ctx.message.guild.id)
            if not os.path.isfile('prefixes.json'):
                prefix_data = {}
                print('[#] Creating prefixes.json')
                with open('prefixes.json', 'w') as fw:
                    json.dump({}, fw)
            else:
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
