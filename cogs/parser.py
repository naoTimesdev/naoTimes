# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import asyncio
import json
import os
import random
import re
import uuid

import aiohttp
import discord
import discord.ext.commands as commands
import pysubs2
import pytz

from bs4 import BeautifulSoup as BS4
from kbbi import KBBI
from textblob import TextBlob

LANGUAGES_LIST = [
    ('aa', 'Afar'),
    ('ab', 'Abkhazian'),
    ('af', 'Afrika'),
    ('ak', 'Akan'),
    ('sq', 'Albania'),
    ('am', 'Amharic'),
    ('ar', 'Arab'),
    ('an', 'Aragonese'),
    ('hy', 'Armenia'),
    ('as', 'Assamese'),
    ('av', 'Avaric'),
    ('ae', 'Avestan'),
    ('ay', 'Aymara'),
    ('az', 'Azerbaijani'),
    ('ba', 'Bashkir'),
    ('bm', 'Bambara'),
    ('eu', 'Basque'),
    ('be', 'Belarusia'),
    ('bn', 'Bengali'),
    ('bh', 'Bihari languages'),
    ('bi', 'Bislama'),
    ('bo', 'Tibet'),
    ('bs', 'Bosnia'),
    ('br', 'Breton'),
    ('bg', 'Bulgaria'),
    ('my', 'Burmese'),
    ('ca', 'Catalan'),
    ('cs', 'Czech'),
    ('ch', 'Chamorro'),
    ('ce', 'Chechen'),
    ('zh', 'China'),
    ('cu', 'Church Slavic'),
    ('cv', 'Chuvash'),
    ('kw', 'Cornish'),
    ('co', 'Corsica'),
    ('cr', 'Cree'),
    ('cy', 'Welsh'),
    ('cs', 'Czech'),
    ('da', 'Denmark'),
    ('de', 'Jerman'),
    ('dv', 'Divehi'),
    ('nl', 'Belanda'),
    ('dz', 'Dzongkha'),
    ('el', 'Yunani'),
    ('en', 'Inggris'),
    ('eo', 'Esperanto'),
    ('et', 'Estonia'),
    ('eu', 'Basque'),
    ('ee', 'Ewe'),
    ('fo', 'Faroese'),
    ('fa', 'Persia'),
    ('fj', 'Fijian'),
    ('fi', 'Finlandia'),
    ('fr', 'Perancis'),
    ('fy', 'Frisia Barat'),
    ('ff', 'Fulah'),
    ('Ga', 'Georgia'),
    ('gd', 'Gaelic'),
    ('ga', 'Irlandia'),
    ('gl', 'Galicia'),
    ('gv', 'Manx'),
    ('gn', 'Guarani'),
    ('gu', 'Gujarati'),
    ('ht', 'Haiti'),
    ('ha', 'Hausa'),
    ('he', 'Yahudi'),
    ('hz', 'Herero'),
    ('hi', 'Hindi'),
    ('ho', 'Hiri Motu'),
    ('hr', 'Kroatia'),
    ('hu', 'Hungaria'),
    ('hy', 'Armenia'),
    ('ig', 'Igbo'),
    ('is', 'Islandia'),
    ('io', 'Ido'),
    ('ii', 'Sichuan Yi'),
    ('iu', 'Inuktitut'),
    ('ie', 'Interlingue Occidental'),
    ('ia', 'Interlingua'),
    ('id', 'Indonesia'),
    ('ik', 'Inupiaq'),
    ('it', 'Italia'),
    ('jv', 'Jawa'),
    ('ja', 'Jepang'),
    ('kl', 'Kalaallisut'),
    ('kn', 'Kannada'),
    ('ks', 'Kashmiri'),
    ('ka', 'Georgia'),
    ('kr', 'Kanuri'),
    ('kk', 'Kazakh'),
    ('km', 'Khmer Tengah'),
    ('ki', 'Kikuyu'),
    ('rw', 'Kinyarwanda'),
    ('ky', 'Kyrgyz'),
    ('kv', 'Komi'),
    ('kg', 'Kongo'),
    ('ko', 'Korea'),
    ('kj', 'Kuanyama'),
    ('ku', 'Kurdish'),
    ('lo', 'Lao'),
    ('la', 'Latin'),
    ('lv', 'Latvian'),
    ('li', 'Limburgan'),
    ('ln', 'Lingala'),
    ('lt', 'Lithuania'),
    ('lb', 'Luxembourgish'),
    ('lu', 'Luba-Katanga'),
    ('lg', 'Ganda'),
    ('mk', 'Macedonia'),
    ('mh', 'Marshallese'),
    ('ml', 'Malayalam'),
    ('mi', 'Maori'),
    ('mr', 'Marathi'),
    ('ms', 'Melayu'),
    ('Mi', 'Micmac'),
    ('mg', 'Malagasy'),
    ('mt', 'Maltese'),
    ('mn', 'Mongolia'),
    ('mi', 'Maori'),
    ('my', 'Burmese'),
    ('na', 'Nauru'),
    ('nv', 'Navaho'),
    ('nr', 'Ndebele Selatan'),
    ('nd', 'Ndebele Utara'),
    ('ng', 'Ndonga'),
    ('ne', 'Nepali'),
    ('nn', 'Norwegia Nynorsk'),
    ('nb', 'Norwegia Bokmål'),
    ('no', 'Norwegia'),
    ('oc', 'Occitan (post 1500)'),
    ('oj', 'Ojibwa'),
    ('or', 'Oriya'),
    ('om', 'Oromo'),
    ('os', 'Ossetia'),
    ('pa', 'Panjabi'),
    ('fa', 'Persia'),
    ('pi', 'Pali'),
    ('pl', 'Polandia'),
    ('pt', 'Portugal'),
    ('ps', 'Pushto'),
    ('qu', 'Quechua'),
    ('rm', 'Romansh'),
    ('ro', 'Romania'),
    ('rn', 'Rundi'),
    ('ru', 'Rusia'),
    ('sg', 'Sango'),
    ('sa', 'Sanskrit'),
    ('si', 'Sinhala'),
    ('sk', 'Slovak'),
    ('sk', 'Slovak'),
    ('sl', 'Slovenia'),
    ('se', 'Sami Utara'),
    ('sm', 'Samoa'),
    ('sn', 'Shona'),
    ('sd', 'Sindhi'),
    ('so', 'Somali'),
    ('st', 'Sotho, Southern'),
    ('es', 'Spanyol'),
    ('sq', 'Albania'),
    ('sc', 'Sardinia'),
    ('sr', 'Serbia'),
    ('ss', 'Swati'),
    ('su', 'Sunda'),
    ('sw', 'Swahili'),
    ('sv', 'Swedia'),
    ('ty', 'Tahiti'),
    ('ta', 'Tamil'),
    ('tt', 'Tatar'),
    ('te', 'Telugu'),
    ('tg', 'Tajik'),
    ('tl', 'Tagalog'),
    ('th', 'Thailand'),
    ('bo', 'Tibetan'),
    ('ti', 'Tigrinya'),
    ('to', 'Tonga'),
    ('tn', 'Tswana'),
    ('ts', 'Tsonga'),
    ('tk', 'Turkmen'),
    ('tr', 'Turki'),
    ('tw', 'Twi'),
    ('ug', 'Uighur'),
    ('uk', 'Ukrania'),
    ('ur', 'Urdu'),
    ('uz', 'Uzbek'),
    ('ve', 'Venda'),
    ('vi', 'Vietnam'),
    ('vo', 'Volapük'),
    ('cy', 'Welsh'),
    ('wa', 'Walloon'),
    ('wo', 'Wolof'),
    ('xh', 'Xhosa'),
    ('yi', 'Yiddish'),
    ('yo', 'Yoruba'),
    ('za', 'Zhuang'),
    ('zu', 'Zulu')
]

text_replacing = {
    r"( \!\?)": r"!?",
    r"( \?\!)": r"?!",
    r"(\: )": r":",
    r"(\; )": r";",
    r"( \.\.\.)": r"..."
}

tags_replacing = {
    r"\\bord": r"\\DORB",
    r"\\xbord": r"\\XDORB",
    r"\\ybord": r"\\YDORB",
    r"\\shad": r"\\DHSA",
    r"\\xshad": r"\\XDHSA",
    r"\\yshad": r"\\YDHSA",
    r"\\be": r"\\B1U53DG3",
    r"\\blur": r"\\B1U5",
    r"\\fn": r"\\EMANTONF",
    r"\\fs": r"\\ESZITONF",
    r"\\fscx": r"\\TONFCX",
    r"\\fscy": r"\\TONFCY",
    r"\\fsp": r"\\TONFP",
    r"\\fr": r"\\ETATORLLA",
    r"\\frx": r"\\ETATORX",
    r"\\fry": r"\\ETATORY",
    r"\\frz": r"\\ETATORZ",
    r"\\fax": r"\\REASHX",
    r"\\fay": r"\\REASHY",
    r"\\an": r"\\NALGIN",
    r"\\q": r"\\RPAW",
    r"\\r": r"\\ESRTS",
    r"\\pos": r"\\OPSXET",
    r"\\move": r"\\OPSMV",
    r"\\org": r"\\ETATORGRO",
    r"\\p": r"\\RDWA",
    r"\\kf": r"\\INGSFD",
    r"\\ko": r"\\INGSO",
    r"\\k": r"\\INGSL",
    r"\\K": r"\\INGSU",
    r"\\fade": r"\\EDFAPX",
    r"\\fad": r"\\EDFAP",
    r"\\t": r"\\SNTRA",
    r"\\clip": r"\\EVCTRO",
    r"\\iclip": r"\\IEVCTRO",
    r"\\c": r"\\CLRRMIP",
    r"\\1c": r"\\CLRRMIP1",
    r"\\2c": r"\\CLRSDC2",
    r"\\3c": r"\\CLRDORB",
    r"\\4c": r"\\CLRDHSA",
    r"\\alpha": r"\\HPLA",
    r"\\1a": r"\\HPLA1",
    r"\\2a": r"\\HPLA2",
    r"\\3a": r"\\HPLA3",
    r"\\4a": r"\\HPLA4",
    r"\\a": r"\\NALGIO",
    r"\\i": r"\\1I1",
    r"\\b": r"\\1B1",
    r"\\u": r"\\1U1",
    r"\\s": r"\\1S1"
}

def fix_spacing(n):
    for x, y in text_replacing.items():
        n = re.sub(x, y, n)
    return n

def scramble_tags(n):
    for x, y in tags_replacing.items():
        n = re.sub(x, y, n)
    return n

def unscramble_tags(n):
    for x, y in tags_replacing.items():
        n = re.sub(y, x, n)
    return n

def fix_taggings(n):
    slashes1 = re.compile(r'(\\ )')
    slashes2 = re.compile(r'( \\)')
    open_ = re.compile(r'( \()')
    close_tags = re.compile(r'(\} )')

    n = re.sub(slashes1, r'\\', n)
    n = re.sub(slashes2, r'\\', n)
    n = re.sub(close_tags, r'}', n)
    return re.sub(open_, r'(', n)

async def query_take_first_result(query):
    print('Requesting page to anibin...')
    async with aiohttp.ClientSession() as sesi:
        async with sesi.get('http://anibin.blogspot.com/search?q={}'.format(query)) as resp:
            response = await resp.text()

    # Let's fiddle with the data
    soup_data = BS4(response, 'html.parser')
    first_query = soup_data.find('div', attrs={'class': 'date-posts'})

    if not first_query:
        return None, None, None

    # Query results
    query_title = first_query.find('h3', attrs={'class': 'post-title entry-title'}).text.strip()

    if not query_title:
        return None, None, None

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


async def chunked_translate(sub_data, number, target_lang, untranslated, mode='.ass'):
    """
    Process A chunked part of translation
    Since async keep crashing :/
    """
    # Translate every 30 lines
    print('@@ Processing lines number {} to {}'.format(number[0]+1, number[-1]+1))
    regex_tags = re.compile(r"[{}]+")
    regex_newline = re.compile(r"(\w)?\\N(\w)?")
    regex_newline_reverse = re.compile(r"(\w)?\\ LNGSX (\w?)")
    for n in number:
        org_line = sub_data[n].text
        tags_exists = re.match(regex_tags, org_line)
        line = re.sub(regex_newline, r"\1\\LNGSX \2", org_line) # Change newline
        if tags_exists:
            line = scramble_tags(line)
            line = re.sub(r'(})', r'} ', line) # Add some line for proper translating
        blob = TextBlob(line)
        try:
            res = str(blob.translate(to=target_lang))
            if tags_exists:
                res = fix_taggings(res)
                res = unscramble_tags(res)
            res = re.sub(regex_newline_reverse, r'\1\\N\2', res)
            res = fix_spacing(res)
            if mode == '.ass':
                sub_data[n].text = res + '{' + org_line + '}'
            else:
                sub_data[n].text = re.sub(r'{.*}', r"", res) # Just to make sure
        except Exception as err:
            print('Translation Problem (Line {nl}): {e}'.format(nl=n+1, e=err))
            untranslated += 1
    return sub_data, untranslated


async def post_requests(url, data):
    async with aiohttp.ClientSession() as sesi:
        async with sesi.post(url, data=data) as resp:
            response = await resp.json()
    return response

class WebParser(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["safelink"])
    async def pengaman(self, ctx, *, url_text):
        """
        Safelinking never been more safe before :)
        """
        server_message = str(ctx.message.guild.id)
        print('Requested !safelink at: ' + server_message)
        await ctx.message.delete()
        msg = await ctx.send('Mengamankan tautan...')

        regex_validator = re.compile(
                r'^(?:http|ftp)s?://' # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
                r'localhost|' #localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
                r'(?::\d+)?' # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if re.match(regex_validator, url_text) is None:
            return await ctx.send('Mohon gunakan format alamat tautan yang valid (gunakan `http://` atau `https://`)')
        
        post_response = await post_requests('https://meme.n4o.xyz/api/v1/safelink', {"secure": url_text})
        await msg.delete()

        await ctx.send('Tautan berhasil diamankan:\n<{l}>'.format(l=post_response['uri']))


    @commands.command(aliases=["shorten"])
    async def pemendek(self, ctx, *, url_text):
        """
        Shortening never be more eazy before :)
        """
        server_message = str(ctx.message.guild.id)
        print('Requested !pemendek at: ' + server_message)
        await ctx.message.delete()
        msg = await ctx.send('Memendekan tautan...')

        regex_validator = re.compile(
                r'^(?:http|ftp)s?://' # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
                r'localhost|' #localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
                r'(?::\d+)?' # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if re.match(regex_validator, url_text) is None:
            return await ctx.send('Mohon gunakan format alamat tautan yang valid (gunakan `http://` atau `https://`)')
        
        post_response = await post_requests('https://meme.n4o.xyz/api/v1/shorten', {"shorten": url_text})
        await msg.delete()

        await ctx.send('Tautan berhasil dipendekan:\n<{l}>'.format(l=post_response['uri']))


    @commands.command()
    async def anibin(self, ctx, *, query):
        """
        Mencari native resolution dari sebuah anime di anibin
        """
        server_message = str(ctx.message.guild.id)
        print('Requested !anibin at: ' + server_message)

        search_title, search_native, search_studio = await query_take_first_result(query)

        if not search_title:
            return await ctx.send('Tidak dapat menemukan anime yang diberikan, mohon gunakan kanji jika belum.')

        embed = discord.Embed(title="Anibin Native Resolution", color=0xffae00)
        embed.add_field(name=search_title, value=search_native, inline=False)
        embed.set_footer(text="Studio Animasi: {}".format(search_studio))
        await ctx.send(embed=embed)


    @commands.command()
    async def pilih(self, ctx, *, input_data):
        server_message = str(ctx.message.guild.id)
        print('Requested !pilih at: ' + server_message)

        inp_d = input_data.split(',')

        if not inp_d:
            return await ctx.send('Tidak ada input untuk dipilih\nGunakan `,` sebagai pemisah.')

        if len(inp_d) < 2:
            return await ctx.send('Hanya ada 1 input untuk dipilih\nGunakan `,` sebagai pemisah.')

        result = random.choice(inp_d)

        await ctx.send('**{user}** aku memilih: **{res}**'.format(user=ctx.message.author.name, res=result.strip()))


    @commands.command(pass_context=True, aliases=['fastsub', 'gtlsub'])
    async def speedsub(self, ctx, targetlang='id'):
        print('@@ Running speedsub command')
        channel = ctx.message.channel
        DICT_LANG = dict(LANGUAGES_LIST)

        if targetlang not in DICT_LANG:
            return await ctx.send('Tidak dapat menemukan bahasa tersebut\nSilakan cari informasinya di ISO 639-1')

        if not ctx.message.attachments:
            return await ctx.send('Mohon attach file subtitle lalu jalankan dengan `!speedsub`\nSubtitle yang didukung adalah: .ass dan .srt')
        attachment = ctx.message.attachments[0]
        uri = attachment['url']
        filename = attachment['filename']
        ext_ = filename[filename.rfind('.'):]

        if ext_ not in ['.ass', '.srt']:
            await ctx.message.delete()
            return await ctx.send('Mohon attach file subtitle lalu jalankan dengan `!speedsub`\nSubtitle yang didukung adalah: .ass dan .srt')

        await ctx.send('Memproses `{fn}`...\nTarget alihbahasa: **{t}**'.format(fn=filename, t=DICT_LANG[targetlang]))
        # Start downloading .json file
        print('@@ Downloading file')
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(uri) as resp:
                data = await resp.text()
                with open(filename, 'w') as f:
                    f.write(data)
                await ctx.message.delete()

        parsed_sub = pysubs2.load(filename)
        n_sub = range(len(parsed_sub))

        chunked_number = [n_sub[i:i + 30] for i in range(0, len(n_sub), 30)]

        untrans = 0
        print('@@ Processing a total of {} lines with `{}` mode'.format(len(n_sub), ext_))
        for n_chunk in chunked_number:
            # Trying this to test if discord.py will destroy itself because it waited to long.
            parsed_sub, untrans = await chunked_translate(parsed_sub, n_chunk, targetlang, untrans, ext_)

        print('@@ Dumping results...')
        output_file = "{fn}.{l}{e}".format(fn=filename, l=targetlang, e=ext_)
        parsed_sub.save(output_file)

        subtitle = 'Berkas telah dialihbahasakan ke bahasa **{}**'.format(DICT_LANG[targetlang])
        if untrans != 0:
            subtitle += '\nSebanyak **{}/{}** baris tidak dialihbahasakan'.format(untrans, len(n_sub))
        print('@@ Sending translated subtitle')
        await channel.send(file=output_file, content=subtitle)
        print('@@ Cleanup')
        os.remove(filename) # Original subtitle
        os.remove(output_file) # Translated subtitle


    @commands.command(pass_context=True)
    async def kbbi(self, ctx, * q_kbbi):
        print('@@ Running kbbi command')
        q_kbbi = " ".join(q_kbbi)

        try:
            cari_kata = KBBI(q_kbbi)
        except KBBI.TidakDitemukan:
            print('@@ No results.')
            return await ctx.send('Tidak dapat menemukan kata tersebut di KBBI')

        json_d = cari_kata.serialisasi()[q_kbbi]
        dataset = []
        for v in json_d:
            build_data = {}
            build_data['nama'] = v['nama']
            makna_tbl = []
            cnth_tbl = []
            for j in v['makna']:
                text = ''
                for z, _ in j['kelas'].items():
                    text += '*({z})* '.format(z=z)
                text += "; ".join(j['submakna'])
                makna_tbl.append(text)
                cnth_tbl.append("; ".join(j['contoh']).replace('-- ', '- ').replace('--, ', '- '))
            build_data['makna'] = "\n".join(makna_tbl)
            build_data['contoh'] = "\n".join(cnth_tbl)
            build_data['takbaku'] = ", ".join(v['bentuk_tidak_baku'])
            build_data['kata_dasar'] = ", ".join(v['kata_dasar'])
            dataset.append(build_data)

        def return_format(x):
            if isinstance(x, list):
                return []
            elif isinstance(x, dict):
                return {}
            return ''

        def sanity_check(dataset):
            for n, d in enumerate(dataset):
                for k, v in d.items():
                    if v.isspace():
                        dataset[n][k] = return_format(v)
            return dataset

        dataset = sanity_check(dataset)
        first_run = True
        dataset_total = len(dataset)
        pos = 1
        print(dataset)
        while True:
            if first_run:
                pos = 1
                datap = dataset[pos - 1]
                embed=discord.Embed(title="KBBI: {}".format(q_kbbi), color=0x81e28d)
                embed.add_field(name=datap['nama'], value=datap['makna'], inline=False)
                embed.add_field(name='Contoh',
                    value="Tidak ada" if not datap['contoh'] else datap['contoh'],
                    inline=False)
                embed.add_field(name='Kata Dasar',
                    value="Tidak ada" if not datap['kata_dasar'] else datap['kata_dasar'],
                    inline=False)
                embed.add_field(name='Bentuk tak baku',
                    value="Tidak ada" if not datap['takbaku'] else datap['takbaku'],
                    inline=False)
                msg = await ctx.send(embed=embed)
                first_run = False

            if dataset_total < 2:
                break
            elif pos == 1:
                to_react = ['⏩', '✅']
            elif dataset_total == pos:
                to_react = ['⏪', '✅']
            elif pos > 1 and pos < dataset_total:
                to_react = ['⏪', '⏩', '✅']

            for react in to_react:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                e = str(reaction.emoji)
                return user == ctx.message.author and str(reaction.emoji) in to_react

            try:
                res, user = await ctx.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            else:
                if user != ctx.message.author:
                    pass
                elif '✅' in str(res.reaction.emoji):
                    return await msg.clear_reactions()
                elif '⏪' in str(res.reaction.emoji):
                    await msg.clear_reactions()
                    pos -= 1
                    datap = dataset[pos - 1]
                    embed=discord.Embed(title="KBBI: {}".format(q_kbbi), color=0x81e28d)
                    embed.add_field(name=datap['nama'], value=datap['makna'], inline=False)
                    embed.add_field(name='Contoh',
                        value="Tidak ada" if not datap['contoh'] else datap['contoh'],
                        inline=False)
                    embed.add_field(name='Kata Dasar',
                        value="Tidak ada" if not datap['kata_dasar'] else datap['kata_dasar'],
                        inline=False)
                    embed.add_field(name='Bentuk tak baku',
                        value="Tidak ada" if not datap['takbaku'] else datap['takbaku'],
                        inline=False)
                    msg = await msg.edit(embed=embed)
                elif '⏩' in str(res.reaction.emoji):
                    await msg.clear_reactions()
                    pos += 1
                    datap = dataset[pos - 1]
                    embed=discord.Embed(title="KBBI: {}".format(q_kbbi), color=0x81e28d)
                    embed.add_field(name=datap['nama'], value=datap['makna'], inline=False)
                    embed.add_field(name='Contoh',
                        value="Tidak ada" if not datap['contoh'] else datap['contoh'],
                        inline=False)
                    embed.add_field(name='Kata Dasar',
                        value="Tidak ada" if not datap['kata_dasar'] else datap['kata_dasar'],
                        inline=False)
                    embed.add_field(name='Bentuk tak baku',
                        value="Tidak ada" if not datap['takbaku'] else datap['takbaku'],
                        inline=False)
                    msg = await msg.edit(embed=embed)


def setup(bot):
    bot.add_cog(WebParser(bot))