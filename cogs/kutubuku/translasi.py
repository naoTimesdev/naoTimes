import ctypes
import logging
from urllib.parse import urlencode

import aiohttp
import discord
import orjson
from discord.ext import app, commands

from naotimes.bot import naoTimesBot

LANGUAGES_LIST = [
    ("aa", "Afar"),
    ("ab", "Abkhazian"),
    ("af", "Afrika"),
    ("ak", "Akan"),
    ("sq", "Albania"),
    ("am", "Amharic"),
    ("ar", "Arab"),
    ("an", "Aragonese"),
    ("hy", "Armenia"),
    ("as", "Assamese"),
    ("av", "Avaric"),
    ("ae", "Avestan"),
    ("ay", "Aymara"),
    ("az", "Azerbaijani"),
    ("ba", "Bashkir"),
    ("bm", "Bambara"),
    ("eu", "Basque"),
    ("be", "Belarusia"),
    ("bn", "Bengali"),
    ("bh", "Bihari languages"),
    ("bi", "Bislama"),
    ("bo", "Tibet"),
    ("bs", "Bosnia"),
    ("br", "Breton"),
    ("bg", "Bulgaria"),
    ("my", "Burmese"),
    ("ca", "Catalan"),
    ("cs", "Czech"),
    ("ch", "Chamorro"),
    ("ce", "Chechen"),
    ("zh", "China"),
    ("cu", "Church Slavic"),
    ("cv", "Chuvash"),
    ("kw", "Cornish"),
    ("co", "Corsica"),
    ("cr", "Cree"),
    ("cy", "Welsh"),
    ("cs", "Czech"),
    ("da", "Denmark"),
    ("de", "Jerman"),
    ("dv", "Divehi"),
    ("nl", "Belanda"),
    ("dz", "Dzongkha"),
    ("el", "Yunani"),
    ("en", "Inggris"),
    ("eo", "Esperanto"),
    ("et", "Estonia"),
    ("eu", "Basque"),
    ("ee", "Ewe"),
    ("fo", "Faroese"),
    ("fa", "Persia"),
    ("fj", "Fijian"),
    ("fi", "Finlandia"),
    ("fr", "Perancis"),
    ("fy", "Frisia Barat"),
    ("ff", "Fulah"),
    ("Ga", "Georgia"),
    ("gd", "Gaelic"),
    ("ga", "Irlandia"),
    ("gl", "Galicia"),
    ("gv", "Manx"),
    ("gn", "Guarani"),
    ("gu", "Gujarati"),
    ("ht", "Haiti"),
    ("ha", "Hausa"),
    ("he", "Yahudi"),
    ("hz", "Herero"),
    ("hi", "Hindi"),
    ("ho", "Hiri Motu"),
    ("hr", "Kroatia"),
    ("hu", "Hungaria"),
    ("hy", "Armenia"),
    ("ig", "Igbo"),
    ("is", "Islandia"),
    ("io", "Ido"),
    ("ii", "Sichuan Yi"),
    ("iu", "Inuktitut"),
    ("ie", "Interlingue Occidental"),
    ("ia", "Interlingua"),
    ("id", "Indonesia"),
    ("ik", "Inupiaq"),
    ("it", "Italia"),
    ("jv", "Jawa"),
    ("ja", "Jepang"),
    ("kl", "Kalaallisut"),
    ("kn", "Kannada"),
    ("ks", "Kashmiri"),
    ("ka", "Georgia"),
    ("kr", "Kanuri"),
    ("kk", "Kazakh"),
    ("km", "Khmer Tengah"),
    ("ki", "Kikuyu"),
    ("rw", "Kinyarwanda"),
    ("ky", "Kyrgyz"),
    ("kv", "Komi"),
    ("kg", "Kongo"),
    ("ko", "Korea"),
    ("kj", "Kuanyama"),
    ("ku", "Kurdish"),
    ("lo", "Lao"),
    ("la", "Latin"),
    ("lv", "Latvian"),
    ("li", "Limburgan"),
    ("ln", "Lingala"),
    ("lt", "Lithuania"),
    ("lb", "Luxembourgish"),
    ("lu", "Luba-Katanga"),
    ("lg", "Ganda"),
    ("mk", "Macedonia"),
    ("mh", "Marshallese"),
    ("ml", "Malayalam"),
    ("mi", "Maori"),
    ("mr", "Marathi"),
    ("ms", "Melayu"),
    ("Mi", "Micmac"),
    ("mg", "Malagasy"),
    ("mt", "Maltese"),
    ("mn", "Mongolia"),
    ("mi", "Maori"),
    ("my", "Burmese"),
    ("na", "Nauru"),
    ("nv", "Navaho"),
    ("nr", "Ndebele Selatan"),
    ("nd", "Ndebele Utara"),
    ("ng", "Ndonga"),
    ("ne", "Nepali"),
    ("nn", "Norwegia Nynorsk"),
    ("nb", "Norwegia Bokmål"),
    ("no", "Norwegia"),
    ("oc", "Occitan (post 1500)"),
    ("oj", "Ojibwa"),
    ("or", "Oriya"),
    ("om", "Oromo"),
    ("os", "Ossetia"),
    ("pa", "Panjabi"),
    ("fa", "Persia"),
    ("pi", "Pali"),
    ("pl", "Polandia"),
    ("pt", "Portugal"),
    ("ps", "Pushto"),
    ("qu", "Quechua"),
    ("rm", "Romansh"),
    ("ro", "Romania"),
    ("rn", "Rundi"),
    ("ru", "Rusia"),
    ("sg", "Sango"),
    ("sa", "Sanskrit"),
    ("si", "Sinhala"),
    ("sk", "Slovak"),
    ("sk", "Slovak"),
    ("sl", "Slovenia"),
    ("se", "Sami Utara"),
    ("sm", "Samoa"),
    ("sn", "Shona"),
    ("sd", "Sindhi"),
    ("so", "Somali"),
    ("st", "Sotho, Southern"),
    ("es", "Spanyol"),
    ("sq", "Albania"),
    ("sc", "Sardinia"),
    ("sr", "Serbia"),
    ("ss", "Swati"),
    ("su", "Sunda"),
    ("sw", "Swahili"),
    ("sv", "Swedia"),
    ("ty", "Tahiti"),
    ("ta", "Tamil"),
    ("tt", "Tatar"),
    ("te", "Telugu"),
    ("tg", "Tajik"),
    ("tl", "Tagalog"),
    ("th", "Thailand"),
    ("bo", "Tibetan"),
    ("ti", "Tigrinya"),
    ("to", "Tonga"),
    ("tn", "Tswana"),
    ("ts", "Tsonga"),
    ("tk", "Turkmen"),
    ("tr", "Turki"),
    ("tw", "Twi"),
    ("ug", "Uighur"),
    ("uk", "Ukrania"),
    ("ur", "Urdu"),
    ("uz", "Uzbek"),
    ("ve", "Venda"),
    ("vi", "Vietnam"),
    ("vo", "Volapük"),
    ("cy", "Welsh"),
    ("wa", "Walloon"),
    ("wo", "Wolof"),
    ("xh", "Xhosa"),
    ("yi", "Yiddish"),
    ("yo", "Yoruba"),
    ("za", "Zhuang"),
    ("zu", "Zulu"),
]
_IKON = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/Google_Translate_logo.svg/480px-Google_Translate_logo.svg.png"  # noqa: E501


class AsyncTranslator:
    def __init__(self, target_lang=None, session: aiohttp.ClientSession = None):
        self.target_l = target_lang
        if self.target_l is None:
            self.target_l = "id"
        self.source_l = None
        self.logger = logging.getLogger("AsyncTranslator")

        self.url = "http://translate.google.com/translate_a/t?client=webapp&dt=bd&dt=ex&dt=ld&dt=md&dt=qca&dt=rw&dt=rm&dt=ss&dt=t&dt=at&ie=UTF-8&oe=UTF-8&otf=2&ssel=0&tsel=0&kc=1"  # noqa: E501

        self._DEFAULT_HEADERS = {
            "Accept": "*/*",
            "Connection": "keep-alive",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) "
                "AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.168 Safari/535.19"  # noqa: E501
            ),
        }

        if session is None:
            self.logger.info("Spawning new Session...")
            self.session = aiohttp.ClientSession(headers=self._DEFAULT_HEADERS)
        else:
            self.session = session
        # await self.detect_language()

    def set_target(self, target_lang):
        self.target_l = target_lang

    @property
    def source_language(self) -> str:
        return self.source_l

    @staticmethod
    def _calculate_tk(source):
        """Reverse engineered cross-site request protection."""
        # Source: http://www.liuxiatool.com/t.php

        tkk = [406398, 561666268 + 1526272306]
        b = tkk[0]

        d = source.encode("utf-8")

        def RL(a, b):
            for c in range(0, len(b) - 2, 3):
                d = b[c + 2]
                d = ord(d) - 87 if d >= "a" else int(d)
                xa = ctypes.c_uint32(a).value
                d = xa >> d if b[c + 1] == "+" else xa << d
                a = a + d & 4294967295 if b[c] == "+" else a ^ d
            return ctypes.c_int32(a).value

        a = b

        for di in d:
            a = RL(a + di, "+-a^+6")

        a = RL(a, "+-3^+b+-f")
        a ^= tkk[1]
        a = a if a >= 0 else ((a & 2147483647) + 2147483648)
        a %= pow(10, 6)

        tk = "{0:d}.{1:d}".format(a, a ^ b)
        return tk

    async def close_connection(self):
        await self.session.close()

    async def detect_language(self, test_string: str):
        if self.source_l:
            return None
        data = {"q": test_string}
        url = "{url}&sl=auto&tk={tk}&{q}".format(
            url=self.url, tk=self._calculate_tk(test_string), q=urlencode(data)
        )
        self.logger.info("detecting source language...")
        response = await self.session.get(url, headers=self._DEFAULT_HEADERS)
        resp = await response.text()
        _, language = orjson.loads(resp)
        self.source_l = language
        self.logger.info(f"source language: {self.source_l}")

        return language

    async def translate(self, string_=None):
        data = {"q": string_}
        url = "{url}&sl={from_lang}&tl={to_lang}&hl={to_lang}&tk={tk}&{q}&client={client}&format={format}".format(  # noqa: E501
            url=self.url,
            from_lang="auto",
            to_lang=self.target_l,
            tk=self._calculate_tk(string_),
            q=urlencode(data),
            client="te",
            format="html",
        )
        self.logger.info(f"Translating {string_} ({self.source_l} => {self.target_l})")
        response = await self.session.get(url, headers=self._DEFAULT_HEADERS)
        resp = await response.text()
        result = orjson.loads(resp)
        self.logger.info(f"Result: {result}")
        if isinstance(result, list):
            try:
                result, source_lang = result
                if result.strip() == string_.strip():
                    raise SyntaxError("Translation is the same!")
                return result, source_lang
            except (IndexError, ValueError):
                raise ValueError("An error detected while translating...")
        raise ValueError("An error detected while translating...")


class KutubukuTranslator(commands.Cog):
    _BASE_ERROR = "Gagal memproses translasi, mohon coba lagi!"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Translator")
        self._TLProg = AsyncTranslator(session=self.bot.aiosession)

    @commands.command(name="translasi", aliases=["tl", "alihbahasa"])
    async def _kutubuku_translasi(self, ctx: commands.Context, *, full_query: str):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"running command at {server_message}")
        DICT_LANG = dict(LANGUAGES_LIST)
        DEFAULT_TARGET = "id"

        split_query = full_query.split(" ", 1)
        lang = DEFAULT_TARGET
        if len(split_query) > 1:
            lang = split_query[0]
            if lang not in DICT_LANG:
                lang = DEFAULT_TARGET
                full_query = full_query
            else:
                full_query = split_query[1]

        if len(full_query) > 1000:
            return await ctx.send("Teks terlalu panjang, maksimal adalah 1000 karakter!")

        self.logger.info(f"Translating to {lang}...")
        self._TLProg.set_target(lang)
        try:
            result, source_lang = await self._TLProg.translate(full_query)
            embed = discord.Embed(title="Translasi", color=discord.Colour.random())
            embed.add_field(name=f"Masukan ({source_lang.upper()})", value=full_query, inline=False)
            embed.add_field(name=f"Hasil ({lang.upper()})", value=result, inline=False)
            embed.set_footer(text="Diprakasai oleh Google Translate", icon_url=_IKON)
            embed.set_thumbnail(url=_IKON)
            await ctx.send(embed=embed)
        except SyntaxError:
            return await ctx.send("Hasil translasi sama dengan input!")
        except ValueError:
            return await ctx.send(self._BASE_ERROR)
        except Exception:
            return await ctx.send(self._BASE_ERROR)

    @app.slash_command(
        name="translasi",
        description="Translasi dari satu bahasa ke bahasa lainnya!",
    )
    @app.option("kalimat", str, description="Kalimat/kata yang ingin di alih bahasakan")
    @app.option("target", str, description="Target bahasa translasi", default="id")
    async def _kutubuku_translasi_slash(self, ctx: app.ApplicationContext, kalimat: str, target: str = "id"):
        if not target:
            target = "id"
        DICT_LANG = dict(LANGUAGES_LIST)
        if target not in DICT_LANG:
            return await ctx.send("Target bahasa tidak dapat dimengerti!")
        self.logger.info(f"Trying to translate: {kalimat} (=> {target})")

        if len(kalimat) > 1000:
            return await ctx.send("Teks terlalu panjang, maksimal adalah 1000 karakter!")

        await ctx.defer()
        self._TLProg.set_target(target)
        try:
            result, source_lang = await self._TLProg.translate(kalimat)
            embed = discord.Embed(title="Translasi", color=discord.Colour.random())
            embed.add_field(name=f"Masukan ({source_lang.upper()})", value=kalimat, inline=False)
            embed.add_field(name=f"Hasil ({target.upper()})", value=result, inline=False)
            embed.set_footer(text="Diprakasai oleh Google Translate", icon_url=_IKON)
            embed.set_thumbnail(url=_IKON)
            await ctx.send(embed=embed)
        except SyntaxError:
            return await ctx.send("Hasil translasi sama dengan input!")
        except ValueError:
            return await ctx.send("Gagal memproses translasi, mohon coba lagi!")
        except Exception:
            return await ctx.send("Gagal memproses translasi, mohon coba lagi!")


def setup(bot: naoTimesBot):
    bot.add_cog(KutubukuTranslator(bot))
