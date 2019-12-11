# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import asyncio
import ctypes
import json
import os
import random
import re
from datetime import datetime
from typing import Union
from urllib.parse import urlencode

import aiohttp
import discord
import discord.ext.commands as commands
import pysubs2
from bs4 import BeautifulSoup as BS4
from kbbi import KBBI
from textblob import TextBlob

from nthelper.romkan import to_hepburn

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

async def fix_spacing(n):
    for x, y in text_replacing.items():
        n = re.sub(x, y, n)
    return n

async def secure_tags(n, reverse=False):
    for x, y in tags_replacing.items():
        tags_ = [x, y, n]
        if reverse:
            tags_ = [y, x, n]
        n = re.sub(*tags_)

async def fix_taggings(n):
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
    query_list = soup_data.find_all('div', attrs={'class': 'date-posts'})

    if not query_list:
        return None, None, None

    if query_list[0].find('table'):
        if len(query_list) < 2: # Skip if there's nothing anymore :(
            return None, None, None
        first_query = query_list[1]
    else:
        first_query = query_list[0]

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


class AsyncTranslator:
    def __init__(self, target_lang):
        print('[@] AsyncTranslator: Spawning new ClientSession')
        self.target_l = target_lang
        self.source_l = None

        self.url = "http://translate.google.com/translate_a/t?client=webapp&dt=bd&dt=ex&dt=ld&dt=md&dt=qca&dt=rw&dt=rm&dt=ss&dt=t&dt=at&ie=UTF-8&oe=UTF-8&otf=2&ssel=0&tsel=0&kc=1"

        headers = {
            'Accept': '*/*',
            'Connection': 'keep-alive',
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) '
                'AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.168 Safari/535.19')
        }

        self.session = aiohttp.ClientSession(headers=headers)
        #await self.detect_language()

    def _calculate_tk(self, source):
        """Reverse engineered cross-site request protection."""
        # Source: https://github.com/soimort/translate-shell/issues/94#issuecomment-165433715
        # Source: http://www.liuxiatool.com/t.php

        tkk = [406398, 561666268 + 1526272306]
        b = tkk[0]

        d = source.encode('utf-8')

        def RL(a, b):
            for c in range(0, len(b) - 2, 3):
                d = b[c + 2]
                d = ord(d) - 87 if d >= 'a' else int(d)
                xa = ctypes.c_uint32(a).value
                d = xa >> d if b[c + 1] == '+' else xa << d
                a = a + d & 4294967295 if b[c] == '+' else a ^ d
            return ctypes.c_int32(a).value

        a = b

        for di in d:
            a = RL(a + di, "+-a^+6")

        a = RL(a, "+-3^+b+-f")
        a ^= tkk[1]
        a = a if a >= 0 else ((a & 2147483647) + 2147483648)
        a %= pow(10, 6)

        tk = '{0:d}.{1:d}'.format(a, a ^ b)
        return tk

    async def close_connection(self):
        await self.session.close()

    async def detect_language(self, test_string):
        if self.source_l:
            return None
        data = {'q': test_string}
        url = u'{url}&sl=auto&tk={tk}&{q}'.format(url=self.url, tk=self._calculate_tk(test_string), q=urlencode(data))
        print('[@] AsyncTranslator: Detecting source language...')
        response = await self.session.get(url)
        resp = await response.text()
        result, language = json.loads(resp)
        self.source_l = language
        print('[@] AsyncTranslator: Detected: {}'.format(language))

        return language

    async def translate(self, string_=None):
        if not self.source_l:
            print('[@] AsyncTranslator: Source not detected yet, detecting...')
            await self.detect_language(string_)
        data = {"q": string_}
        url = u'{url}&sl={from_lang}&tl={to_lang}&hl={to_lang}&tk={tk}&{q}'.format(
            url=self.url,
            from_lang=self.source_l,
            to_lang=self.target_l,
            tk=self._calculate_tk(string_),
            q=urlencode(data)
        )
        response = await self.session.get(url)
        resp = await response.text()
        result = json.loads(resp)
        if isinstance(result, list):
            try:
                result = result[0]  # ignore detected language
            except IndexError:
                pass

        # Validate
        if not result:
            raise Exception('An error detected while translating..')
        if result.strip() == string_.strip():
            raise Exception('Returned result are the same as input.')
        return result


async def chunked_translate(sub_data, number, target_lang, untranslated, mode='.ass'):
    """
    Process A chunked part of translation
    Since async keep crashing :/
    """
    # Translate every 30 lines
    print('[@] Processing lines number {} to {}'.format(number[0]+1, number[-1]+1))
    regex_tags = re.compile(r"[{}]+")
    regex_newline = re.compile(r"(\w)?\\N(\w)?")
    regex_newline_reverse = re.compile(r"(\w)?\\ LNGSX (\w?)")
    Translator = AsyncTranslator(target_lang)
    for n in number:
        org_line = sub_data[n].text
        tags_exists = re.match(regex_tags, org_line)
        line = re.sub(regex_newline, r"\1\\LNGSX \2", org_line) # Change newline
        if tags_exists:
            line = await secure_tags(line)
            line = re.sub(r'(})', r'} ', line) # Add some line for proper translating
        try:
            res = await Translator.translate(line)
            if tags_exists:
                res = await fix_taggings(res)
                res = await secure_tags(res, True)
            res = re.sub(regex_newline_reverse, r'\1\\N\2', res)
            res = await fix_spacing(res)
            if mode == '.ass':
                sub_data[n].text = res + '{' + org_line + '}'
            else:
                sub_data[n].text = re.sub(r'{.*}', r"", res) # Just to make sure
        except Exception as err:
            print('Translation Problem (Line {nl}): {e}'.format(nl=n+1, e=err))
            untranslated += 1
    await Translator.close_connection() # Close connection
    return sub_data, untranslated


async def persamaankata(cari: str, mode: str = 'sinonim') -> Union[str, None]:
    """Mencari antonim/sinonim dari persamaankata.com"""
    async with aiohttp.ClientSession() as sesi:
        async with sesi.get('http://m.persamaankata.com/search.php?q={}'.format(cari)) as resp:
            response = await resp.text()
            if resp.status > 299:
                return 'Tidak dapat terhubung dengan API.'

    soup_data = BS4(response, 'html.parser')
    tesaurus = soup_data.find_all('div', attrs={'class': 'thesaurus_group'})

    if not tesaurus:
        return 'Tidak ada hasil.'

    if mode == 'antonim' and len(tesaurus) < 2:
        return 'Tidak ada hasil.'
    elif mode == 'antonim' and len(tesaurus) > 1:
        result = tesaurus[1].text.strip().splitlines()[1:]
        return list(filter(None, result))
    else:
        result = tesaurus[0].text.strip().splitlines()[1:]
        return list(filter(None, result))
    return 'Tidak ada hasil.'


async def fetch_jisho(query: str) -> Union[None, dict]:
    async with aiohttp.ClientSession() as sesi:
        try:
            async with sesi.get('http://jisho.org/api/v1/search/words?keyword={}'.format(query)) as r:
                try:
                    data = await r.json()
                except IndexError:
                    return 'ERROR: Terjadi kesalahan internal'
                if r.status != 200:
                    if r.status == 404:
                        return "ERROR: Tidak dapat menemukan kata tersebut"
                    elif r.status == 500:
                        return "ERROR: Internal Error :/"
                try:
                    query_result = data['data']
                except IndexError:
                    return "ERROR: Tidak ada hasil."
        except aiohttp.ClientError:
            return 'ERROR: Koneksi terputus'

    full_query_results = []
    for q in query_result:
        words_ = []
        for w in q['japanese']:
            word = w['word']
            reading = w['reading']
            hepburn = to_hepburn(reading)
            words_.append((word, reading, hepburn))

        senses_ = []
        for s in q['senses']:
            try:
                english_def = s['english_definitions']
            except:
                english_def = '(?)'
            senses_.append((english_def))

        dataset = {
            "words": words_,
            "senses": senses_
        }

        full_query_results.append(dataset)
    return {'result': full_query_results, 'data_total': len(full_query_results)}


async def yahoo_finance(from_, to_):
    data_ = {
        "data": {
            "base": from_.upper(),
            "period": "day",
            "term": to_.upper()
        },
        "method": "spotRateHistory"
    }
    base_head = {
        'Host': 'adsynth-ofx-quotewidget-prod.herokuapp.com',
        'Origin': 'https://widget-yahoo.ofx.com',
        'Referer': 'https://widget-yahoo.ofx.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36',
    }
    async with aiohttp.ClientSession(headers=base_head) as sesi:
        async with sesi.post("https://adsynth-ofx-quotewidget-prod.herokuapp.com/api/1", json=data_) as resp:
            try:
                response = await resp.json()
                if response['data']['HistoricalPoints']:
                    latest = response['data']['HistoricalPoints'][-1]
                else:
                    return response["data"]["CurrentInterbankRate"]
            except:
                response = await resp.text()
                return 'Tidak dapat terhubung dengan API.\nAPI Response: ```\n' + response + '\n```'

    return latest['InterbankRate']


async def coinmarketcap(from_, to_) -> float:
    base_head = {
        'accept': 'application/json, text/plain, */*',
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'en-US,en;q=0.9,id-ID;q=0.8,id;q=0.7,ja-JP;q=0.6,ja;q=0.5',
        'cache-control': 'no-cache',
        'origin': 'https://coinmarketcap.com',
        'referer': 'https://coinmarketcap.com/converter/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36'
    }
    # USD: 2781
    url_to_search = 'https://web-api.coinmarketcap.com/v1/tools/price-conversion?amount=1&convert_id={}&id={}'.format(to_, from_)
    async with aiohttp.ClientSession(headers=base_head) as sesi:
        async with sesi.get(url_to_search) as resp:
            response = await resp.json()
            if response['status']['error_message']:
                return 'Tidak dapat terhubung dengan API.\nAPI Response: ```\n' + response['status']['error_message'] + '\n```'
            if resp.status > 299:
                return 'Tidak dapat terhubung dengan API.\nAPI Response: ```\n' + response['status']['error_message'] + '\n```'

    return response["data"]["quote"][to_]["price"]


def proper_rounding(curr_now: float, total: float) -> float:
    nnr = 2
    while True:
        conv_num = round(curr_now * total, nnr)
        str_ = str(conv_num).replace('.', '')
        if str_.count('0') != len(str_):
            break
        nnr += 1
    mm = str(conv_num)
    if 'e-' in mm:
        nnr = int(mm.split('e-')[1]) + 1
    fmt_ = ',.' + str(nnr) + 'f'
    fmt_data = format(conv_num, fmt_)
    return fmt_data, nnr


async def post_requests(url, data):
    async with aiohttp.ClientSession() as sesi:
        async with sesi.post(url, data=data) as resp:
            response = await resp.json()
    return response

class WebParser(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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


    @commands.command(aliases=['fastsub', 'gtlsub'])
    async def speedsub(self, ctx, targetlang='id'):
        print('[@] Running speedsub command')
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
        # Start downloading .ass/.srt file
        print('[@] Downloading file')
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
        print('[@] Processing a total of {} lines with `{}` mode'.format(len(n_sub), ext_))
        for n_chunk in chunked_number:
            # Trying this to test if discord.py will destroy itself because it waited to long.
            parsed_sub, untrans = await chunked_translate(parsed_sub, n_chunk, targetlang, untrans, ext_)

        print('[@] Dumping results...')
        output_file = "{fn}.{l}{e}".format(fn=filename, l=targetlang, e=ext_)
        parsed_sub.save(output_file)

        subtitle = 'Berkas telah dialihbahasakan ke bahasa **{}**'.format(DICT_LANG[targetlang])
        if untrans != 0:
            subtitle += '\nSebanyak **{}/{}** baris tidak dialihbahasakan'.format(untrans, len(n_sub))
        print('[@] Sending translated subtitle')
        await channel.send(file=output_file, content=subtitle)
        print('[@] Cleanup')
        os.remove(filename) # Original subtitle
        os.remove(output_file) # Translated subtitle


    @commands.command(aliases=['konversiuang', 'currency'])
    async def kurs(self, ctx, from_, to_, total=None):
        if total:
            try:
                total = float(total)
            except ValueError:
                return await ctx.send('Bukan jumlah uang yang valid (jangan memakai koma, pakai titik)')

        mode = 'normal'

        mode_list = {
            'crypto': {
                'source': 'CoinMarketCap dan yahoo!finance',
                'logo': 'https://p.ihateani.me/PoEnh1XN.png'
            },
            'normal': {
                'source': 'yahoo!finance',
                'logo': 'https://ihateani.me/o/y!.png'
            }
        }

        with open('currencydata.json', 'r', encoding='utf-8') as fp:
            currency_data = json.load(fp)

        with open('cryptodata.json', 'r', encoding='utf-8') as fp:
            crypto_data = json.load(fp)

        from_, to_ = from_.upper(), to_.upper()

        full_crypto_mode = False
        if from_ in crypto_data and to_ in crypto_data:
            mode = 'crypto'
            crypto_from = str(crypto_data[from_]['id'])
            crypto_to = str(crypto_data[to_]['id'])
            curr_sym_from = crypto_data[from_]['symbol']
            curr_sym_to = crypto_data[to_]['symbol']
            curr_name_from = crypto_data[from_]['name']
            curr_name_to = crypto_data[to_]['name']
            full_crypto_mode = True
        elif from_ in crypto_data:
            mode = 'crypto'
            crypto_from = str(crypto_data[from_]['id'])
            crypto_to = '2781'
            curr_sym_from = crypto_data[from_]['symbol']
            curr_sym_to = currency_data[to_]['symbols'][0]
            curr_name_from = crypto_data[from_]['name']
            curr_name_to = currency_data[to_]['name']
            from_ = 'USD'
            to_ = to_
            if to_ not in currency_data:
                return await ctx.send('Tidak dapat menemukan kode negara mata utang **{}** di database'.format(to_))
        elif to_ in crypto_data:
            mode = 'crypto'
            crypto_from = '2781'
            crypto_to = str(crypto_data[to_]['id'])
            curr_sym_from = currency_data[from_]['symbols'][0]
            curr_sym_to = crypto_data[to_]['symbol']
            curr_name_from = currency_data[from_]['name']
            curr_name_to = crypto_data[to_]['name']
            from_ = from_
            to_ = 'USD'
            if from_ not in currency_data:
                return await ctx.send('Tidak dapat menemukan kode negara mata utang **{}** di database'.format(from_))


        if mode == 'normal':
            if from_ not in currency_data:
                return await ctx.send('Tidak dapat menemukan kode negara mata utang **{}** di database'.format(from_))
            if to_ not in currency_data:
                return await ctx.send('Tidak dapat menemukan kode negara mata utang **{}** di database'.format(to_))
            curr_sym_from = currency_data[from_]['symbols'][0]
            curr_sym_to = currency_data[to_]['symbols'][0]
            curr_name_from = currency_data[from_]['name']
            curr_name_to = currency_data[to_]['name']

        if mode == 'crypto':
            curr_crypto = await coinmarketcap(crypto_from, crypto_to)

        if not full_crypto_mode:
            curr_ = await yahoo_finance(from_, to_)
            if isinstance(curr_, str):
                return await ctx.send(curr_)

        if not total:
            total = 1.0
        if full_crypto_mode and mode == 'crypto':
            curr_ = curr_crypto
        elif not full_crypto_mode and mode == 'crypto':
            curr_ = curr_ * curr_crypto

        conv_num, rounding_used = proper_rounding(curr_, total)
        embed = discord.Embed(title=":gear: Konversi mata uang",
        colour=discord.Colour(0x50e3c2), 
        description=":small_red_triangle_down: {f_} ke {d_}\n:small_orange_diamond: {sf_}{sa_:,}\n:small_blue_diamond: {df_}{da_}".format(
            f_ = curr_name_from,
            d_ = curr_name_to,
            sf_ = curr_sym_from,
            sa_ = total,
            df_ = curr_sym_to,
            da_ = conv_num
        ),
        timestamp=datetime.now())
        embed.set_footer(text="Diprakasai dengan {}".format(mode_list[mode]['source']), icon_url=mode_list[mode]['logo'])

        await ctx.send(embed=embed)

    @commands.command(aliases=['persamaankata', 'persamaan'])
    async def sinonim(self, ctx, * q_):
        if not isinstance(q_, str):
            q_ = " ".join(q_)
        print('[@] Running sinonim command')

        result = await persamaankata(q_, 'Sinonim')
        if not isinstance(result, list):
            return await ctx.send(result)
        result = "\n".join(result)
        embed = discord.Embed(title="Sinonim: {}".format(q_), color=0x81e28d)
        embed.set_footer(text='Diprakasai dengan: persamaankata.com')
        if not result:
            embed.add_field(name=q_, value='Tidak ada hasil', inline=False)
            return await ctx.send(embed=embed)

        embed.add_field(name=q_, value=result, inline=False)
        await ctx.send(embed=embed)

    @commands.command(aliases=['lawankata'])
    async def antonim(self, ctx, * q_):
        if not isinstance(q_, str):
            q_ = " ".join(q_)
        print('[@] Running antonim command')

        result = await persamaankata(q_, 'antonim')
        if not isinstance(result, list):
            return await ctx.send(result)
        result = "\n".join(result)
        embed = discord.Embed(title="Antonim: {}".format(q_), color=0x81e28d)
        embed.set_footer(text='Diprakasai dengan: persamaankata.com')
        if not result:
            embed.add_field(name=q_, value='Tidak ada hasil', inline=False)
            return await ctx.send(embed=embed)

        embed.add_field(name=q_, value=result, inline=False)
        await ctx.send(embed=embed)


    @commands.command(aliases=['kanji'])
    async def jisho(self, ctx, *, q_):
        if not isinstance(q_, str):
            q_ = " ".join(q_)

        print('[@] Running jisho command')

        jqres = await fetch_jisho(q_)
        if isinstance(jqres, str):
            return await ctx.send(jqres)

        dataset_total = jqres['data_total']
        dataset = jqres['result']

        first_run = True
        pos = 1
        while True:
            if first_run:
                data = dataset[pos - 1]
                embed = discord.Embed(color=0x81e28d)
                embed.set_author(name='Jisho: ' + q_, url='https://jisho.org/search/%s' % q_, icon_url="https://ihateani.me/o/jishoico.png")

                for i in data['words']:
                    format_value = '**Cara baca**: {}\n**Hepburn**: {}'.format(i[1], i[2])
                    embed.add_field(name=i[0], value=format_value, inline=False)

                eng_ = [i[0] if i[0] is not None else '(?)' for i in data['senses']]
                embed.add_field(name="Definisi", value='\n'.join(eng_), inline=True)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if dataset_total < 2:
                break
            elif pos == 1:
                reactmoji = ['⏩']
            elif dataset_total == pos:
                reactmoji = ['⏪']
            elif pos > 1 and pos < dataset_total:
                reactmoji = ['⏪', '⏩']

            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                e = str(reaction.emoji)
                return user == ctx.message.author and str(reaction.emoji) in reactmoji

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif '⏪' in str(res.emoji):
                await msg.clear_reactions()
                pos -= 1
                data = dataset[pos - 1]
                embed = discord.Embed(color=0x81e28d)
                embed.set_author(name='Jisho: ' + q_, url='https://jisho.org/search/%s' % q_, icon_url="https://ihateani.me/o/jishoico.png")

                for i in data['words']:
                    format_value = '**Cara baca**: {}\n**Hepburn**: {}'.format(i[1], i[2])
                    embed.add_field(name=i[0], value=format_value, inline=False)

                eng_ = [i[0] if i[0] is not None else '(?)' for i in data['senses']]
                embed.add_field(name="Definisi", value='\n'.join(eng_), inline=True)
                await msg.edit(embed=embed)
            elif '⏩' in str(res.emoji):
                await msg.clear_reactions()
                pos += 1
                data = dataset[pos - 1]
                embed = discord.Embed(color=0x81e28d)
                embed.set_author(name='Jisho: ' + q_, url='https://jisho.org/search/%s' % q_, icon_url="https://ihateani.me/o/jishoico.png")

                for i in data['words']:
                    format_value = '**Cara baca**: {}\n**Hepburn**: {}'.format(i[1], i[2])
                    embed.add_field(name=i[0], value=format_value, inline=False)

                eng_ = [i[0] if i[0] is not None else '(?)' for i in data['senses']]
                embed.add_field(name="Definisi", value='\n'.join(eng_), inline=True)
                await msg.edit(embed=embed)


    @commands.command()
    async def kbbi(self, ctx, *, q_kbbi):
        print('[@] Running kbbi command')

        try:
            cari_kata = KBBI(q_kbbi)
        except KBBI.TidakDitemukan:
            print('[@] No results.')
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
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif '✅' in str(res.emoji):
                return await msg.clear_reactions()
            elif '⏪' in str(res.emoji):
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
                await msg.edit(embed=embed)
            elif '⏩' in str(res.emoji):
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
                await msg.edit(embed=embed)


def setup(bot):
    bot.add_cog(WebParser(bot))
