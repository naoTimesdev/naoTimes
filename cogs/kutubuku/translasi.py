import json
import logging
import re
from dataclasses import dataclass, field
from html import unescape
from typing import ClassVar, Literal
from uuid import uuid4

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.utils import FIREFOX_USER_AGENT

LANGUAGES_LIST = [
    ("auto", "Deteksi Otomatis"),
    ("ab", "Abkhaz"),
    ("ace", "Aceh"),
    ("ach", "Acoli"),
    ("aa", "Afar"),
    ("af", "Afrikaans"),
    ("sq", "Albania"),
    ("alz", "Alur"),
    ("am", "Amharik"),
    ("ar", "Arab"),
    ("hy", "Armenia"),
    ("as", "Assam"),
    ("av", "Avar"),
    ("awa", "Awadhi"),
    ("ay", "Aymara"),
    ("az", "Azerbaijan"),
    ("ban", "Bali"),
    ("bal", "Baluchi"),
    ("bm", "Bambara"),
    ("bci", "Baoulé"),
    ("ba", "Bashkir"),
    ("eu", "Bask"),
    ("btx", "Batak Karo"),
    ("bts", "Batak Simalungun"),
    ("bbc", "Batak Toba"),
    ("nl", "Belanda"),
    ("be", "Belarusia"),
    ("bem", "Bemba"),
    ("bn", "Bengali"),
    ("bew", "Betawi"),
    ("bho", "Bhojpuri"),
    ("bik", "Bikol"),
    ("bs", "Bosnia"),
    ("br", "Breton"),
    ("bg", "Bulgaria"),
    ("bua", "Buriat"),
    ("cs", "Ceko"),
    ("ch", "Chamorro"),
    ("ce", "Chechen"),
    ("ny", "Chichewa"),
    ("zh-CN", "China"),
    ("zh-TW", "China (Aks. Tradisional)"),
    ("chk", "Chuuke"),
    ("cv", "Chuvash"),
    ("fa-AF", "Dari"),
    ("da", "Denmark"),
    ("din", "Dinka"),
    ("dv", "Divehi"),
    ("doi", "Dogri"),
    ("dov", "Dombe"),
    ("dyu", "Dyula"),
    ("dz", "Dzongkha"),
    ("eo", "Esperanto"),
    ("et", "Estonia"),
    ("ee", "Ewe"),
    ("fo", "Faroe"),
    ("fa", "Farsi"),
    ("fj", "Fiji"),
    ("fi", "Finlandia"),
    ("fon", "Fon"),
    ("fy", "Frisia"),
    ("fur", "Friuli"),
    ("ff", "Fulani"),
    ("gaa", "Ga"),
    ("gd", "Gaelik Skotlandia"),
    ("gl", "Galisia"),
    ("ka", "Georgia"),
    ("gn", "Guarani"),
    ("gu", "Gujarati"),
    ("cnh", "Hakha Chin"),
    ("ha", "Hausa"),
    ("haw", "Hawaii"),
    ("hil", "Hiligaynon"),
    ("hi", "Hindi"),
    ("hmn", "Hmong"),
    ("hu", "Hungaria"),
    ("hrx", "Hunsrik"),
    ("iba", "Iban"),
    ("iw", "Ibrani"),
    ("ig", "Igbo"),
    ("ilo", "Iloko"),
    ("id", "Indonesia"),
    ("en", "Inggris"),
    ("iu-Latn", "Inuktut (Latin)"),
    ("iu", "Inuktut (Silabis)"),
    ("ga", "Irlandia"),
    ("is", "Islandia"),
    ("it", "Italia"),
    ("jw", "Jawa"),
    ("ja", "Jepang"),
    ("de", "Jerman"),
    ("kac", "Jingpo"),
    ("kl", "Kalaallisut"),
    ("kn", "Kannada"),
    ("kr", "Kanuri"),
    ("ca", "Katalan"),
    ("kk", "Kazakh"),
    ("kek", "Kekchi"),
    ("kha", "Khasi"),
    ("km", "Khmer"),
    ("cgg", "Kiga"),
    ("rw", "Kinyarwanda"),
    ("ky", "Kirgiz"),
    ("ktu", "Kituba"),
    ("trp", "Kokborok"),
    ("kv", "Komi"),
    ("kg", "Kongo"),
    ("gom", "Konkani"),
    ("ko", "Korea"),
    ("co", "Korsika"),
    ("ht", "Kreol Haiti"),
    ("mfe", "Kreol Mauritius"),
    ("crs", "Kreol Seselwa"),
    ("kri", "Krio"),
    ("hr", "Kroasia"),
    ("ku", "Kurdi (Kurmanji)"),
    ("ckb", "Kurdi (Sorani)"),
    ("lo", "Lao"),
    ("ltg", "Latgalia"),
    ("la", "Latin"),
    ("lv", "Latvia"),
    ("lij", "Liguria"),
    ("li", "Limburgia"),
    ("ln", "Lingala"),
    ("lt", "Lituania"),
    ("lmo", "Lombard"),
    ("lg", "Luganda"),
    ("lb", "Luksemburg"),
    ("luo", "Luo"),
    ("mad", "Madura"),
    ("mai", "Maithili"),
    ("mak", "Makassar"),
    ("mk", "Makedonia"),
    ("mg", "Malagasi"),
    ("ml", "Malayalam"),
    ("mt", "Malta"),
    ("mam", "Mam"),
    ("gv", "Manx"),
    ("mi", "Maori"),
    ("mr", "Marathi"),
    ("mh", "Marshall"),
    ("mwr", "Marwari"),
    ("yua", "Maya Yukatek"),
    ("chm", "Meadow Mari"),
    ("mni-Mtei", "Meitei (Manipuri)"),
    ("ms", "Melayu"),
    ("ms-Arab", "Melayu (Jawi)"),
    ("min", "Minangkabau"),
    ("lus", "Mizo"),
    ("mn", "Mongolia"),
    ("my", "Myanmar"),
    ("bm-Nkoo", "N'Ko"),
    ("nhe", "Nahuatl (Huasteca Timur)"),
    ("ndc-ZW", "Ndau"),
    ("nr", "Ndebele (Selatan)"),
    ("ne", "Nepal"),
    ("new", "Nepal Bhasa (Newari)"),
    ("no", "Norwegia"),
    ("nus", "Nuer"),
    ("or", "Odia (Oriya)"),
    ("om", "Oromo"),
    ("oc", "Ositania"),
    ("os", "Ossetia"),
    ("pam", "Pampanga"),
    ("pag", "Pangasina"),
    ("pap", "Papiamento"),
    ("ps", "Pashto"),
    ("jam", "Patois Jamaika"),
    ("pl", "Polandia"),
    ("pt", "Portugis (Brasil)"),
    ("pt-PT", "Portugis (Portugal)"),
    ("fr", "Prancis"),
    ("fr-CA", "Prancis (Kanada)"),
    ("pa", "Punjabi (Gurmukhi)"),
    ("pa-Arab", "Punjabi (Shahmukhi)"),
    ("qu", "Quechua"),
    ("rom", "Romani"),
    ("ro", "Rumania"),
    ("rn", "Rundi"),
    ("ru", "Rusia"),
    ("se", "Sami (Utara)"),
    ("sm", "Samoa"),
    ("sg", "Sango"),
    ("sa", "Sanskerta"),
    ("sat", "Santali (Chiki Lama)"),
    ("sat-Latn", "Santali (Latin)"),
    ("ceb", "Sebuano"),
    ("nso", "Sepedi"),
    ("sr", "Serb"),
    ("st", "Sesotho"),
    ("shn", "Shan"),
    ("sn", "Shona"),
    ("szl", "Silesia"),
    ("sd", "Sindhi"),
    ("si", "Sinhala"),
    ("scn", "Sisilia"),
    ("sk", "Slovakia"),
    ("sl", "Slovenia"),
    ("so", "Somali"),
    ("es", "Spanyol"),
    ("su", "Sunda"),
    ("sus", "Susu"),
    ("sw", "Swahili"),
    ("ss", "Swati"),
    ("sv", "Swedia"),
    ("tl", "Tagalog"),
    ("ty", "Tahiti"),
    ("tg", "Tajik"),
    ("ber-Latn", "Tamazight"),
    ("ber", "Tamazight (Tifinagh)"),
    ("ta", "Tamil"),
    ("tt", "Tatar"),
    ("crh-Latn", "Tatar Krimea (Latin)"),
    ("crh", "Tatar Krimea (Sirilik)"),
    ("te", "Telugu"),
    ("tet", "Tetun"),
    ("th", "Thai"),
    ("bo", "Tibet"),
    ("ti", "Tigrinya"),
    ("tiv", "Tiv"),
    ("tpi", "Tok Pisin"),
    ("to", "Tonga"),
    ("lua", "Tshiluba"),
    ("ts", "Tsonga"),
    ("tn", "Tswana"),
    ("tcy", "Tulu"),
    ("tum", "Tumbuka"),
    ("tr", "Turkiye"),
    ("tk", "Turkmen"),
    ("tyv", "Tuvinia"),
    ("ak", "Twi"),
    ("udm", "Udmurt"),
    ("uk", "Ukraina"),
    ("ur", "Urdu"),
    ("ug", "Uyghur"),
    ("uz", "Uzbek"),
    ("ve", "Venda"),
    ("vec", "Venesia"),
    ("vi", "Vietnam"),
    ("war", "Warai"),
    ("cy", "Welsh"),
    ("wo", "Wolof"),
    ("xh", "Xhosa"),
    ("sah", "Yakut"),
    ("yi", "Yiddi"),
    ("yo", "Yoruba"),
    ("el", "Yunani"),
    ("zap", "Zapotek"),
    ("zu", "Zulu"),
    ("jp", ["ja", "Jepang"]),
    ("zh", ["zh-CN", "China"]),
    ("zh-HK", ["yue", "Kanton"]),
    ("he", ["iw", "Ibrani"]),
    ("jv", ["jw", "Jawa"]),
]
_LANGUAGE_CANONICAL: dict[str, str] = {code.lower(): code for code, _ in LANGUAGES_LIST}

_IKON = "https://p.ihateani.me/gvhombft.png"


@dataclass
class TLRequest:
    input: str
    output: str | None = None

    source: str = "auto"
    target: str | None = None

    translator: Literal["gtl"] = "gtl"

    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        self.source = _LANGUAGE_CANONICAL.get(self.source.lower(), self.source.lower())
        if self.target:
            self.target = _LANGUAGE_CANONICAL.get(self.target.lower(), self.target.lower())
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


class GoogleFreeTranslation:
    URL_EXT = "https://translate-pa.googleapis.com/v1/translateHtml"
    API_KEY = "AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520"

    _REFERER = "https://translate.google.com/"
    _LANGUAGE_CONVERSION: ClassVar[dict[str, str]] = {"zh-hk": "yue"}

    # `_translateNew` keeps Google's inline markup and drops non printable characters.
    _MULTI_GROUP_RE = re.compile(r"(?:<i>.*?</i> ?<b>(.*?)</b>)")
    _NON_PRINTABLE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

    def __init__(self, session: aiohttp.ClientSession | None = None):
        self.logger = logging.getLogger("AsyncTranslator")
        self._DEFAULT_HEADERS = {
            "Referer": self._REFERER,
            "Origin": self._REFERER,
            "Content-Type": "application/json+protobuf",
            "x-goog-api-key": self.API_KEY,
            "User-Agent": FIREFOX_USER_AGENT,
        }

        if session is None:
            self.logger.info("Spawning in new session...")
            self.session = aiohttp.ClientSession(headers=self._DEFAULT_HEADERS)
        else:
            self.session = session

    @classmethod
    def _extract_translation(cls, raw_translation: str) -> str:
        translation = ""
        for match in cls._MULTI_GROUP_RE.finditer(raw_translation):
            translation += match.group(1) + " "

        if translation == "":
            # Single return translation
            translation = raw_translation

        # Remove non printable characters
        return cls._NON_PRINTABLE_RE.sub("", translation)

    @classmethod
    def _parse_response(cls, result: list[object]) -> str:
        # `translateHtml` returns `[["translated text"]]`, the JS port flattens
        # the payload once before reading the first item.
        flattened: list[object] = []
        for item in result:
            if isinstance(item, list):
                flattened.extend(item)
            else:
                flattened.append(item)

        if not flattened:
            return ""

        translation = flattened[0]
        if isinstance(translation, list):
            translation = translation[0] if translation else ""
        if not isinstance(translation, str):
            return ""
        return translation

    async def translate(self, request: TLRequest) -> tuple[TLRequest | None, str | None]:
        default_error = "Gagal memproses hasil translasi dari Google, mohon coba lagi!"
        target = self._LANGUAGE_CONVERSION.get(request.target or "id", request.target or "id")
        source = request.source or "auto"

        body = json.dumps([[[request.input], source, target], "te_lib"], ensure_ascii=False)
        self.logger.info("Translating<%s>: %s (%s => %s)", request.id, request.input, source, target)
        try:
            async with self.session.post(self.URL_EXT, headers=self._DEFAULT_HEADERS, data=body) as response:
                if response.status != 200:
                    error_body = await response.text()
                    self.logger.error("Google Translate returned HTTP %s: %s", response.status, error_body)
                    return None, f"{default_error} ({response.status})"
                raw_result = await response.text()
        except TimeoutError:
            self.logger.error("Google Translate request timed out")
            return None, default_error
        except aiohttp.ClientError as error:
            self.logger.error("Failed to contact Google Translate: %s", error)
            return None, default_error

        try:
            result = json.loads(raw_result)
        except json.JSONDecodeError as error:
            self.logger.error("Failed to decode Google Translate response", exc_info=error)
            return None, default_error

        if not isinstance(result, list):
            self.logger.error("Google Translate response was not a JSON array")
            return None, default_error

        raw_translation = self._parse_response(result)
        if not raw_translation.strip():
            self.logger.error("Google Translate response did not contain translated text")
            return None, default_error

        translation = self._extract_translation(raw_translation)
        tl_output = unescape(translation).strip()
        if tl_output == request.input:
            raise SameTranslatedMessage(request.translator, request)
        request.output = tl_output
        return request, None


class KutubukuTranslator(commands.Cog):
    _BASE_ERROR = "Gagal memproses translasi, mohon coba lagi!"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Translator")
        self.DICT_LANG = dict(LANGUAGES_LIST)
        self.DICT_LANG_CASEFOLD = {code.casefold(): code for code in self.DICT_LANG}

        self.gtl = GoogleFreeTranslation(session=self.bot.aiosession)

    def resolve_lang(self, lang: str) -> str | None:
        if not lang:
            return None
        return self.DICT_LANG_CASEFOLD.get(lang.strip().casefold())

    def pick_lang(self, lang: str) -> str:
        code = self.resolve_lang(lang)
        if code is not None:
            data_lang = self.DICT_LANG[code]
            if isinstance(data_lang, str):
                return data_lang
            return data_lang[1]
        return lang.upper()

    async def _actually_translate(self, request: TLRequest) -> str | discord.Embed:
        try:
            translated_request, error_msg = await self.gtl.translate(request)
        except SameTranslatedMessage:
            return "Translasi yang didapatkan sama dengan request input anda!"
        except Exception as e:
            self.logger.error(f"Translasi<{request.id}>: Exception occured", exc_info=e)
            return self._BASE_ERROR
        if error_msg is not None:
            return error_msg
        if translated_request is None:
            return self._BASE_ERROR
        request = translated_request
        if error_msg is None:
            embed = discord.Embed(title="Translasi", color=discord.Colour.random(), timestamp=self.bot.now().datetime)
            description_sec = f"**Masukan (`{self.pick_lang(request.source)}`)**\n{request.input}"
            description_sec += f"\n\n**Hasil (`{self.pick_lang(request.target or 'auto')}`)**\n{request.output or ''}"
            embed.description = description_sec
            embed.set_footer(text="Diprakasai oleh Google Translate", icon_url=_IKON)
            embed.set_thumbnail(url=_IKON)
            return embed
        return error_msg

    @app_commands.command(name="translasi")
    @app_commands.describe(
        kalimat="Kalimat/kata yang ingin di alih bahasakan",
        target="Target bahasa translasi",
        awal="Bahasa awal kalimat",
    )
    async def _kutubuku_translasi_slash(
        self, inter: discord.Interaction, kalimat: str, target: str = "id", awal: str = "auto"
    ):
        """Translasi dari satu bahasa ke bahasa lainnya!"""
        ctx = await self.bot.get_context(inter)
        if not target:
            target = "id"
        target_code = self.resolve_lang(target)
        if target_code is None:
            return await ctx.send("Target bahasa tidak dapat dimengerti!")
        target = target_code
        awal = self.resolve_lang(awal) or "auto"
        source_data = self.DICT_LANG[awal]
        if isinstance(source_data, list):
            awal = source_data[0]
        target_data = self.DICT_LANG[target]
        if isinstance(target_data, list):
            target = target_data[0]
        self.logger.info(f"Trying to translate: {kalimat} ({awal} => {target})")

        if len(kalimat) > 1000:
            self.logger.warning(f"Translasi<{ctx.id}>: Text input is way too long")
            return await ctx.send("Teks terlalu panjang, maksimal adalah 1000 karakter!")

        await ctx.defer()
        tl_request = TLRequest(kalimat, target=target, source=awal)
        self.logger.info(f"Translating(Slash): {tl_request}")
        embed_or_string = await self._actually_translate(tl_request)
        if isinstance(embed_or_string, str):
            return await ctx.send(embed_or_string)
        await ctx.send(embed=embed_or_string)


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuTranslator(bot))
