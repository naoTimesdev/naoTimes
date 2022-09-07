import ctypes
import logging
from dataclasses import dataclass, field
from html import unescape
from typing import Dict, List, Literal, Optional, Tuple, Union
from uuid import uuid4

import aiohttp
import discord
import orjson
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext

LANGUAGES_LIST = [
    ("auto", "Deteksi Otomatis"),
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
    ("jp", ["ja", "Jepang"]),
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


@dataclass
class TLRequest:
    input: str
    output: Optional[str] = None

    source: str = "auto"
    target: Optional[str] = None

    translator: Literal["gtl"] = "gtl"

    id: str = field(default_factory=uuid4)

    def __post_init__(self):
        self.source = self.source.lower()
        if self.target:
            self.target = self.target.lower()
        self.id = str(self.id)

        self.output = None


class TranslationFailed(Exception):
    def __init__(self, engine: str, *args: object):
        self.engine: str = engine
        super().__init__(*args)


class SameTranslatedMessage(TranslationFailed):
    def __init__(self, engine: str, request: TLRequest):
        self.request: TLRequest = request
        self.engine: str = engine
        super().__init__(f"Translasi dari {engine} menghasilkan output yang sama seperti input")


class AsyncTranslatorV2:
    # V2 URL
    URL_EXT = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&hl=en-US&dt=t&dt=bd&dj=1&source=icon"
    )

    def __init__(self, session: aiohttp.ClientSession = None):
        self.logger = logging.getLogger("AsyncTranslator")

        self._DEFAULT_HEADERS = {
            "Accept": "*/*",
            "Connection": "keep-alive",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) "
                "AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.168 Safari/535.19"  # noqa: E501
            ),
        }

        self.session: aiohttp.ClientSession = session
        if session is None:
            self.logger.info("Spawning in new session...")
            self.session = aiohttp.ClientSession(headers=self._DEFAULT_HEADERS)

    @staticmethod
    def _calculate_tk(source: str) -> str:
        """Reverse engineered cross-site request protection."""
        # Source: http://www.liuxiatool.com/t.php

        tkk = [406398, 561666268 + 1526272306]
        b = tkk[0]

        d = source.encode("utf-8")

        def RL(a: int, b: str):
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

    def _build_query_url(self, request: TLRequest) -> Dict[str, str]:
        query_data = {
            "sl": request.source if request.source is not None else "auto",
            "tl": request.target,
            "tk": self._calculate_tk(request.input),
            "q": request.input,
        }
        return query_data

    async def translate(self, request: TLRequest) -> Tuple[Optional[TLRequest], Optional[str]]:
        req_params = self._build_query_url(request)
        self.logger.info(f"Translating<{request.id}>: {request.input} ({request.source} => {request.target})")
        real_result: Optional[dict] = None
        try:
            async with self.session.get(
                self.URL_EXT, headers=self._DEFAULT_HEADERS, params=req_params
            ) as response:
                text_res = await response.text()
                try:
                    real_result = orjson.loads(text_res)
                except orjson.JSONDecodeError as jde:
                    self.logger.error(f"Failed to decode response: {text_res}", exc_info=jde)
                    return None, "Gagal memproses hasil translasi dari Google, mohon coba lagi!"
        except aiohttp.ClientResponseError as cre:
            self.logger.error(f"Failed to get response: {cre}", exc_info=cre)
            return None, f"{cre.message} ({cre.status})"

        _DEFAULT_ERR = "Gagal memproses hasil translasi dari Google, mohon coba lagi!"
        _DEFAULT_ERR_LOG = f"TranslateError<{request.id}>: Unable to get translated sentences!"
        self.logger.debug(f"Translated<{request.id}>: {real_result}")
        sentences: List[str] = []
        raw_sentences = real_result.get("sentences", [])
        if not isinstance(raw_sentences, list):
            self.logger.error(_DEFAULT_ERR_LOG)
            return None, _DEFAULT_ERR
        if not raw_sentences:
            self.logger.error(_DEFAULT_ERR_LOG)
            return None, _DEFAULT_ERR
        for sentence in raw_sentences:
            translated = sentence.get("trans")
            if translated is None:
                continue
            sentences.append(translated)
        if not sentences:
            self.logger.error(_DEFAULT_ERR_LOG)
            return None, _DEFAULT_ERR
        tl_output = unescape("".join(sentences).strip())
        tl_src = real_result.get("src") or request.source
        if tl_output == request.input:
            raise SameTranslatedMessage(request.translator, request)
        request.output = tl_output
        request.source = tl_src
        return request, None


class KutubukuTranslator(commands.Cog):
    _BASE_ERROR = "Gagal memproses translasi, mohon coba lagi!"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Translator")
        self.DICT_LANG = dict(LANGUAGES_LIST)

        self.gtl = AsyncTranslatorV2(session=self.bot.aiosession)

    def pick_lang(self, lang: str) -> str:
        if lang in self.DICT_LANG:
            data_lang = self.DICT_LANG[lang]
            if isinstance(data_lang, str):
                return data_lang
            return data_lang[1]
        return lang.upper()

    async def _actually_translate(self, request: TLRequest) -> Union[str, discord.Embed]:
        try:
            request, error_msg = await self.gtl.translate(request)
        except SameTranslatedMessage:
            return "Translasi yang didapatkan sama dengan request input anda!"
        except Exception as e:
            self.logger.error(f"Translasi<{request.id}>: Exception occured", exc_info=e)
            return self._BASE_ERROR
        if error_msg is None:
            embed = discord.Embed(
                title="Translasi", color=discord.Colour.random(), timestamp=self.bot.now().datetime
            )
            description_sec = f"**Masukan (`{self.pick_lang(request.source)}`)**\n{request.input}"
            description_sec += f"\n\n**Hasil (`{self.pick_lang(request.target)}`)**\n{request.output}"
            embed.description = description_sec
            embed.set_footer(text="Diprakasai oleh Google Translate", icon_url=_IKON)
            embed.set_thumbnail(url=_IKON)
            return embed
        return error_msg

    @commands.command(name="translasi", aliases=["tl", "alihbahasa"])
    async def _kutubuku_translasi(self, ctx: naoTimesContext, *, full_query: str):
        DEFAULT_TARGET = "id"

        split_query = full_query.split(" ", 1)
        lang = DEFAULT_TARGET
        if len(split_query) > 1:
            lang = split_query[0]
            if lang not in self.DICT_LANG:
                lang = DEFAULT_TARGET
                full_query = full_query
            else:
                internal_lang = self.DICT_LANG[lang]
                if isinstance(internal_lang, list):
                    lang = internal_lang[0]
                full_query = split_query[1]

        if len(full_query) > 1000:
            self.logger.warning(f"Translasi<{ctx.message.id}>: Text input is way too long")
            return await ctx.send("Teks terlalu panjang, maksimal adalah 1000 karakter!")

        tl_request = TLRequest(full_query, target=lang)
        self.logger.info(f"Translating: {tl_request}")
        embed_or_string = await self._actually_translate(tl_request)
        if isinstance(embed_or_string, str):
            return await ctx.send(embed_or_string)
        await ctx.send(embed=embed_or_string)

    @app_commands.command(name="translasi")
    @app_commands.describe(
        kalimat="Kalimat/kata yang ingin di alih bahasakan", target="Target bahasa translasi"
    )
    async def _kutubuku_translasi_slash(self, inter: discord.Interaction, kalimat: str, target: str = "id"):
        """Translasi dari satu bahasa ke bahasa lainnya!"""
        ctx = await self.bot.get_context(inter)
        if not target:
            target = "id"
        if target not in self.DICT_LANG:
            return await ctx.send("Target bahasa tidak dapat dimengerti!")
        target_data = self.DICT_LANG[target]
        if isinstance(target_data, list):
            target = target_data[0]
        self.logger.info(f"Trying to translate: {kalimat} (=> {target})")

        if len(kalimat) > 1000:
            self.logger.warning(f"Translasi<{ctx.id}>: Text input is way too long")
            return await ctx.send("Teks terlalu panjang, maksimal adalah 1000 karakter!")

        await ctx.defer()
        tl_request = TLRequest(kalimat, target=target)
        self.logger.info(f"Translating(Slash): {tl_request}")
        embed_or_string = await self._actually_translate(tl_request)
        if isinstance(embed_or_string, str):
            return await ctx.send(embed_or_string)
        await ctx.send(embed=embed_or_string)


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuTranslator(bot))
