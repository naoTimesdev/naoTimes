"""
Yet another implementation of Merriam-Webster API.
Have a parser that can replace specific merriam token with actual
formatting. Can be customized!

---

MIT License

Copyright (c) 2019-2022 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import re
import typing as T

import aiohttp

from ..utils import complex_walk, get_indexed, list_or_none, str_or_none

__all__ = (
    "MerriamWebsterClient",
    "WebsterTokenParser",
    "WebsterDefinedWord",
    "WebsterWordThesaurus",
    "ParserReplacer",
)

# https://github.com/lukebui/mw-collegiate/blob/main/src/types/entry.ts
ParserReplacer = T.Dict[
    str,
    T.Union[
        # Subtitute with string
        T.AnyStr,
        # A lambda function with single text parameter and return a string
        T.Callable[[T.Match[T.AnyStr]], T.AnyStr],
    ],
]
_TOKEN_BASE = r"\g<content>"


class ParsedWordMeaning(T.NamedTuple):
    numbering: str
    content: str


class ParsedWordMeaningGrouped(T.NamedTuple):
    meanings: T.Union[ParsedWordMeaning, T.List[ParsedWordMeaning]]
    divider: T.Optional[str] = None


class WebsterDefinedWord(T.NamedTuple):
    word: str
    title: str
    type: str
    meanings: T.List[ParsedWordMeaningGrouped]
    examples: T.List[ParsedWordMeaning]
    suggested: T.List[ParsedWordMeaning]
    etymology: T.Optional[str] = None
    pronounciation: T.Optional[str] = None


class ThesaurizeThis(T.NamedTuple):
    meaning: str
    synonyms: T.List[str] = []
    antonyms: T.List[str] = []


class WebsterWordThesaurus(T.NamedTuple):
    word: str
    type: str
    thesaurus: T.List[ThesaurizeThis]


def to_superscript(text: str) -> str:
    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-=()"
    subtitute = "ᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾQᴿˢᵀᵁⱽᵂˣʸᶻᵃᵇᶜᵈᵉᶠᵍʰᶦʲᵏˡᵐⁿᵒᵖ۹ʳˢᵗᵘᵛʷˣʸᶻ⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾"
    transltable = text.maketrans("".join(normal), "".join(subtitute))
    return text.translate(transltable)


def to_subscript(text: str) -> str:
    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-=()"
    subtitute = "ₐ₈CDₑբGₕᵢⱼₖₗₘₙₒₚQᵣₛₜᵤᵥwₓᵧZₐ♭꜀ᑯₑբ₉ₕᵢⱼₖₗₘₙₒₚ૧ᵣₛₜᵤᵥwₓᵧ₂₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎"
    transltable = text.maketrans("".join(normal), "".join(subtitute))
    return text.translate(transltable)


def to_smallcaps(text: str) -> str:
    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-=()"
    subtitute = "ABCDEFGHIJKLMNOPQRSTUVWXYZᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789+-=()"
    transltable = text.maketrans("".join(normal), "".join(subtitute))
    return text.translate(transltable)


def parse_grouping_default(
    matched: T.Match[T.AnyStr], is_moreat: bool = False, is_dxdef: bool = False
) -> T.AnyStr:
    content = str_or_none(matched.group("content")).rstrip()
    if is_dxdef:
        return f"({content})"
    pre = " - "
    if is_moreat:
        pre += "more at "
    pre += content
    return pre


def parse_link_default(matched: T.Match[T.AnyStr], is_alink: bool = False) -> T.AnyStr:
    if is_alink:
        return matched.group("id")

    content = str_or_none(matched.group("text")).split(":")
    pre_joined = content[0]
    if len(content) > 1:
        pre_joined += f"[{content[1]}]"
    return pre_joined


def parse_xref_link_default(matched: T.Match[T.AnyStr]) -> T.AnyStr:
    text_contents = str_or_none(matched.group("text")).split(":")
    text_data = text_contents[0]
    if len(text_contents) > 1:
        text_data += f" entry {text_contents[1]}"
    fields_data = str_or_none(matched.group("fields"))

    if fields_data and fields_data not in ["illustration", "table"]:
        text_data += f" sense {fields_data}"
    return text_data


def parse_date_ref_default(matched: T.Match[T.AnyStr]):
    verbdiv = str_or_none(matched.group("verbdiv"))
    senseno = str_or_none(matched.group("senseno"))
    sensealpha = str_or_none(matched.group("sense"))
    psenseno = str_or_none(matched.group("psenseno"))
    pre = ", in the meaning defined at "
    if verbdiv == "t":
        pre += "transitive "
    elif verbdiv == "i":
        pre += "intransitive "
    pre += "sense "
    build_sense = f"{senseno}{sensealpha}"
    if psenseno:
        build_sense += f"({psenseno})"
    pre += build_sense
    return pre


class WebsterTokenParser:
    def __init__(self) -> None:
        self._tokenizer = [
            # Formatting and punctuation tokens
            # https://www.dictionaryapi.com/products/json#sec-2.fmttokens
            # Bold text
            [re.compile(r"{b}(?P<content>[\W\S_]+?){\\?/b}"), "fmt-bold"],
            [re.compile(r"{bc}"), "fmt-semicolon"],
            [re.compile(r"{inf}(?P<content>[\W\S_]+?){\\?/inf}"), "fmt-subscript"],
            [re.compile(r"{it}(?P<content>[\W\S_]+?){\\?/it}"), "fmt-italic"],
            [re.compile(r"{ldquo}"), "fmt-left-quote"],  # “
            [re.compile(r"{rdquo}"), "fmt-right-quote"],  # ”
            [re.compile(r"{sc}(?P<content>[\W\S_]+?){\\?/sc}"), "fmt-smallcaps"],
            [re.compile(r"{sup}(?P<content>[\W\S_]+?){\\?/sup}"), "fmt-superscript"],
            # Word-marking and gloss tokens
            # https://www.dictionaryapi.com/products/json#sec-2.wordtokens
            # Bold italics
            [re.compile(r"{phrase}(?P<content>[\W\S_]+?){\\?/phrase}"), "word-phrase"],
            # Italic + Square brackets: [text]
            [re.compile(r"{gloss}(?P<content>[\W\S_]+?){\\?/gloss}"), "word-gloss"],
            # Bold smallcaps and enclose it
            [re.compile(r"{parahw}(?P<content>[\W\S_]+?){\\?/parahw}"), "word-headword-paragraph"],
            # Italics
            [re.compile(r"{qword}(?P<content>[\W\S_]+?){\\?/qword}"), "word-quote"],
            # Italics
            [re.compile(r"{wi}(?P<content>[\W\S_]+?){\\?/wi}"), "word-headword-text"],
            # Cross-reference grouping token
            # https://www.dictionaryapi.com/products/json#sec-2.xrefregtokens
            # Create a new line, and add em dash (—)
            [re.compile(r"{dx}(?P<content>[\W\S_]+?){\\?/dx}"), "xrefg-content"],
            # Enclose the text inside the content with parenthesis -> ()
            [re.compile(r"{dx\_def}(?P<content>[\W\S_]+?){\\?/dx\_def}"), "xrefg-enclosed-word"],
            # Enclose the etymology inside the content with parenthesis
            [re.compile(r"{dx\_ety}(?P<content>[\W\S_]+?){\\?/dx\_ety}"), "xrefg-enclosed-etymology"],
            # Add em dash, then add the text "more at"
            [re.compile(r"{ma}(?P<content>[\W\S_]+?){\\?/ma}"), "xrefg-more-at"],
            # Cross-reference tokens
            # https://www.dictionaryapi.com/products/json#sec-2.xreftokens
            # This is an autolink to the original word, mostly in the same page.
            [re.compile(r"{a_link\|(?P<id>[\W\S_]+?)}"), "xref-autolink"],
            [re.compile(r"{d_link\|(?P<text>[\W\S_]+?)\|(?P<id>[\W\S_]+?)?}"), "xref-directlink"],
            [re.compile(r"{i_link\|(?P<text>[\W\S_]+?)\|(?P<id>[\W\S_]+?)?}"), "xref-directitalic"],
            [re.compile(r"{et_link\|(?P<text>[\W\S_]+?)\|(?P<id>[\W\S_]+?)?}"), "xref-etymology"],
            [re.compile(r"{mat\|(?P<text>[\W\S_]+?)\|(?P<id>[\W\S_]+?)?"), "xref-more-at"],
            [
                re.compile(r"{sx\|(?P<text>[\W\S_]+?)\|(?P<id>[\W\S_]+?)??\|(?P<fields>[\W\S_]+?)??}"),
                "xref-synonyms",
            ],
            [
                re.compile(r"{dxt\|(?P<text>[\W\S_]+?)\|(?P<id>[\W\S_]+?)??\|(?P<fields>[\W\S_]+?)??}"),
                "xref-direct",
            ],
            # Date tokens
            # https://www.dictionaryapi.com/products/json#sec-2.dstoken
            # Example: {ds|t|1|a|1}
            # Result: transitive sense 1a(1)
            # i means intransitive, if none remove that.
            [
                re.compile(
                    r"{ds\|(?P<verbdiv>[it])?\|(?P<senseno>[\d]+?)?\|"
                    + r"(?P<sense>[a-z])?\|(?P<psenseno>[\d]+?)?}"
                ),
                "date-ref",
            ],
        ]
        self._original_replacer: ParserReplacer = {
            # Formatting token
            "fmt-bold": _TOKEN_BASE,
            "fmt-semicolon": r" : ",
            "fmt-subscript": lambda x: to_subscript(x.group("content")),
            "fmt-italic": _TOKEN_BASE,
            "fmt-left-quote": r"“",
            "fmt-right-quote": r"”",
            "fmt-smallcaps": lambda x: to_smallcaps(x.group("content")),
            "fmt-superscript": lambda x: to_superscript(x.group("content")),
            # Word making and gloss token
            "word-phrase": _TOKEN_BASE,
            "word-gloss": r"[\g<content>]",
            "word-headword-paragraph": r"(\g<content>)",
            "word-quote": _TOKEN_BASE,
            "word-headword-text": _TOKEN_BASE,
            # Cross-reference grouping token
            "xrefg-content": lambda x: parse_grouping_default(x),
            "xrefg-enclosed-word": lambda x: parse_grouping_default(x, False, True),
            "xrefg-enclosed-etymology": lambda x: parse_grouping_default(x),
            "xrefg-more-at": lambda x: parse_grouping_default(x, True),
            # Cross-reference token
            "xref-autolink": lambda x: parse_link_default(x, True),
            "xref-directlink": lambda x: parse_link_default(x),
            "xref-directitalic": lambda x: parse_link_default(x),
            "xref-etymology": lambda x: parse_link_default(x),
            "xref-more-at": lambda x: parse_link_default(x),
            "xref-synonyms": lambda x: parse_xref_link_default(x),
            "xref-direct": lambda x: parse_xref_link_default(x),
            # Date token
            "date-ref": lambda x: parse_date_ref_default(x),
        }
        self._replacer: ParserReplacer = self._original_replacer

    def _get_replacer(self, token_name: str):
        try:
            return self._replacer[token_name]
        except KeyError:
            return self._original_replacer[token_name]

    def _token_replacer(self, text: str, prefix_replacer: str):
        all_parser = list(filter(lambda x: x[1].startswith(prefix_replacer), self._tokenizer))
        for parser in all_parser:
            compiled_re, token_name = parser
            replacer = self._get_replacer(token_name)
            text = re.sub(compiled_re, replacer, text)
        return text

    def _internal_parse(self, text: str):
        parsed_text = self._token_replacer(text, "xrefg-")
        parsed_text = self._token_replacer(parsed_text, "xref-")
        parsed_text = self._token_replacer(parsed_text, "word-")
        parsed_text = self._token_replacer(parsed_text, "fmt-")
        return parsed_text

    @classmethod
    def parse(cls, text: str, replacer: ParserReplacer = None):
        init = cls()
        if replacer is not None:
            init.replacer = replacer
        return init._internal_parse(text)

    @classmethod
    def parse_date(cls, text: str, replacer: ParserReplacer = None):
        init = cls()
        if replacer is not None:
            init.replacer = replacer
        return init._token_replacer(text, "date-")

    @property
    def replacer(self):
        return self._replacer

    @replacer.setter
    def replacer(self, new_replacer: ParserReplacer):
        self._replacer = new_replacer
        for original_key, original_value in self._original_replacer.items():
            if original_key not in self._replacer:
                self._replacer[original_key] = original_value


def parse_sense_data(complex_data: T.Mapping[str, T.Union[T.List[T.List[str]], str, dict]]):
    format_text = str_or_none(complex_walk(complex_data, "sn"))
    all_lists_fmt = list_or_none(complex_walk(complex_data, "dt"))
    texts_only = list(map(lambda x: x[1], (filter(lambda x: x[0] == "text", all_lists_fmt))))
    joined_text = " ".join(texts_only)
    return ParsedWordMeaning(format_text, joined_text)


def parse_pseq_data(
    complex_lists: T.List[
        T.Union[
            T.Tuple[T.Literal["sense"], T.Mapping[str, T.Union[T.List[T.List[str]], str, dict]]],
            T.Tuple[
                T.Literal["bs"],
                T.Mapping[T.Literal["sense"], T.Mapping[str, T.Union[T.List[T.List[str]], str, dict]]],
            ],
        ],
    ],
):
    collected_senses: T.List[ParsedWordMeaning] = []
    first_sn = None
    for n, complex in enumerate(complex_lists):
        if complex[0] == "sense":
            format_text = str_or_none(complex_walk(complex, "1.sn"))
            if first_sn is None and format_text and not format_text.startswith("(") and n == 0:
                first_sn = format_text
            all_lists_fmt = list_or_none(complex_walk(complex, "1.dt"))
            texts_only = list(map(lambda x: x[1], (filter(lambda x: x[0] == "text", all_lists_fmt))))
            joined_text = " ".join(texts_only)
            if first_sn and n > 0:
                format_text = f"{first_sn} {format_text}"
            wm = ParsedWordMeaning(format_text, joined_text)
            collected_senses.append(wm)
        elif complex[0] == "bs":
            format_text = complex_walk(complex, "1.sense.sn")
            if first_sn is None and format_text and not format_text.startswith("(") and n == 0:
                first_sn = format_text
            all_lists_fmt = list_or_none(complex_walk(complex, "1.sense.dt"))
            texts_only = list(map(lambda x: x[1], (filter(lambda x: x[0] == "text", all_lists_fmt))))
            joined_text = " ".join(texts_only)
            wm = ParsedWordMeaning(format_text, joined_text)
            collected_senses.append(wm)
    return collected_senses


class MerriamWebsterClient:
    ROUTE_WORDS = "https://dictionaryapi.com/api/v3/references/collegiate/json/"
    ROUTE_THESAURUS = "https://dictionaryapi.com/api/v3/references/thesaurus/json/"

    def __init__(self, api_keys: T.Dict[str, str]) -> None:
        self._api_key = api_keys["words"]
        self._api_key_the = api_keys["thesaurus"]
        self._tokenizer: ParserReplacer = {}

    @property
    def can_thesaurize(self) -> bool:
        return self._api_key_the is not None

    @property
    def can_define(self) -> bool:
        return self._api_key is not None

    def _parse_define_results(self, api_results: T.List[dict], word_fallback: str):
        collected_words: T.List[WebsterDefinedWord] = []
        for words in api_results:
            headword = str_or_none(complex_walk(words, "hwi.hw"), word_fallback)
            just_headword = str_or_none(complex_walk(words, "hwi.hw"), word_fallback)
            word_no = complex_walk(words, "hom")
            if word_no is not None:
                headword = f"{headword} ({word_no})"
            prononciations = str_or_none(complex_walk(words, "hwi.prs.0.mw"), None)
            word_type = complex_walk(words, "fl")
            etimology = list_or_none(complex_walk(words, "et"))
            etimology_texts = list(filter(lambda x: isinstance(x[0], str) and x[0] == "text", etimology))
            full_etimology_text = None
            if len(etimology_texts) > 0:
                mapped_eti = list(map(lambda x: x[1], etimology_texts))
                full_etimology_text = " ".join(mapped_eti)
            word_definitions = list_or_none(complex_walk(words, "def"))
            list_makna = []
            for makna_wrapper in word_definitions:
                makna_sense_sequences = list_or_none(complex_walk(makna_wrapper, "sseq"))
                makna_verb_divider = complex_walk(makna_wrapper, "vd")
                for makna_sequnces in makna_sense_sequences:
                    for makna_konten in makna_sequnces:
                        makna_type = makna_konten[0]
                        if makna_type == "pseq":
                            meanings_multi = parse_pseq_data(makna_konten[1])
                            list_makna.append(ParsedWordMeaningGrouped(meanings_multi, makna_verb_divider))
                        elif makna_type == "sense":
                            meaning_simple = parse_sense_data(makna_konten[1])
                            list_makna.append(ParsedWordMeaningGrouped(meaning_simple, makna_verb_divider))

            examples_data = []
            examples_dros = list_or_none(complex_walk(words, "dros"))
            for n, example in enumerate(examples_dros, 1):
                exmp_head = complex_walk(example, "drp")
                exmp_definition = str_or_none(
                    complex_walk(example, "def.0.sseq.0.0.1.dt.0.1"), "No example definition"
                )
                wmex = ParsedWordMeaning(str(n), r"{b}" + exmp_head + r"{\/b}" + f" {exmp_definition}")
                examples_data.append(wmex)

            other_words = []
            uros_data = list_or_none(complex_walk(words, "uros"))
            for n, uros_data in enumerate(uros_data, 1):
                text_fmt = str_or_none(complex_walk(uros_data, "ure")).replace("*", "")
                uros_pron = str_or_none(complex_walk(uros_data, "prs.0.mw"))
                fl_uros = str_or_none(complex_walk(uros_data, "fl"))
                uros_mean = ""
                if fl_uros:
                    uros_mean += r"({it}" + fl_uros + r"{\/it}) "
                uros_mean += text_fmt
                if uros_pron:
                    uros_mean += f" ({uros_pron})"
                other_words.append(ParsedWordMeaning(str(n), uros_mean))

            mw_word = WebsterDefinedWord(
                just_headword,
                headword,
                word_type,
                list_makna,
                examples_data,
                other_words,
                full_etimology_text,
                prononciations,
            )
            collected_words.append(mw_word)
        return collected_words

    def _parse_thesaurus_results(self, api_results: T.List[dict], word_fallback: str):
        collected_thesaurus: T.List[WebsterWordThesaurus] = []
        for words in api_results:
            synonyms = list_or_none(complex_walk(words, "meta.syns"))
            antonyms = list_or_none(complex_walk(words, "meta.ants"))
            headword = str_or_none(complex_walk(words, "hwi.hw"), word_fallback)
            function_label = str_or_none(complex_walk(words, "fl"))
            shortdef = list_or_none(complex_walk(words, "shortdef"))

            collected_meanings: T.List[ThesaurizeThis] = []
            for n, defs in enumerate(shortdef):
                defant = list_or_none(get_indexed(antonyms, n))
                defsyn = get_indexed(synonyms, n)
                collected_meanings.append(ThesaurizeThis(defs, defsyn, defant))
            mwt_word = WebsterWordThesaurus(headword, function_label, collected_meanings)
            collected_thesaurus.append(mwt_word)
        return collected_thesaurus

    async def define(self, word: str):
        if not self.can_define:
            return []
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(self.ROUTE_WORDS + word, params={"key": self._api_key}) as resp:
                if resp.status >= 400:
                    return []
                content_type = resp.content_type
                if "application/json" not in content_type:
                    return []
                api_results = await resp.json()

        return self._parse_define_results(api_results, word)

    async def thesaurize(self, word: str):
        if not self.can_thesaurize:
            return []
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(self.ROUTE_THESAURUS + word, params={"key": self._api_key_the}) as resp:
                if resp.status >= 400:
                    return []
                content_type = resp.content_type
                if "application/json" not in content_type:
                    return []
                api_results = await resp.json()

        return self._parse_thesaurus_results(api_results, word)
