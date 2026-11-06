import logging
import typing as T
from functools import partial as ftpartial
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.http import (
    ParserReplacer,
    WebsterDefinedWord,
    WebsterTokenParser,
    WebsterWordThesaurus,
)
from naotimes.http.webster import parse_link_default
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import italic, str_or_none

_IKON = "https://merriam-webster.com/assets/mw/static/social-media-share/mw-logo-245x245@1x.png"
_TS_URL = "https://www.merriam-webster.com/thesaurus/"
_DF_URL = "https://www.merriam-webster.com/dictionary/"
_TOKEN_ITALIC = r"*\g<content>*"
_TOKEN_BOLD = r"**\g<content>**"
_TOKEN_BITALIC = r"***\g<content>***"


def parse_md_link(matched: T.Match[str], is_alink: bool = False) -> str:
    parsed_text = parse_link_default(matched, is_alink)

    url_id = str_or_none(matched.group("id"))
    if not url_id:
        url_id = parsed_text
    return f"[{parsed_text}]({_DF_URL}{quote(url_id)})"


def parse_md_xref_link(matched: T.Match[str]) -> str:
    text_contents = (str_or_none(matched.group("text")) or "").split(":")
    text_data = text_contents[0]
    suffix = ""
    if len(text_contents) > 1:
        text_data += f" entry {text_contents[1]}"
        suffix = f"#dictionary-entry-{text_contents[1]}"
    fields = str_or_none(matched.group("fields"))
    url_id = str_or_none(matched.group("id"))

    if fields and url_id and fields in ["illustration", "table"]:
        url_id = text_contents[0]
    if not url_id:
        url_id = text_contents[0]

    return f"[{text_data}]({_DF_URL}{quote(url_id)}{suffix})"


class KutubukuWebster(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot: naoTimesBot = bot
        self._mw = bot.merriam
        self.logger = logging.getLogger("Kutubuku.Webster")
        self._col = discord.Colour.from_rgb(48, 95, 122)
        # This is token formatter for Discord embed
        self._token_formatter: ParserReplacer = {
            "fmt-bold": _TOKEN_BOLD,
            "fmt-italic": _TOKEN_ITALIC,
            "word-phrase": _TOKEN_BITALIC,
            "word-quote": _TOKEN_ITALIC,
            "word-headword-text": _TOKEN_ITALIC,
            "xref-autolink": lambda m: parse_md_link(m, True),
            "xref-synonyms": lambda m: parse_md_xref_link(m),
            "xref-direct": lambda m: parse_md_xref_link(m),
            "xref-directlink": lambda m: parse_md_link(m),
            "xref-more-at": lambda m: parse_md_link(m),
            "xref-etymology": lambda m: parse_md_link(m),
            "xref-directitalic": lambda m: italic(parse_md_link(m)),
        }

    def _design_word_define_embed(self, data: WebsterDefinedWord, fallback_data: dict, t: T.Callable[..., str]):
        fb_word, fb_pr, fb_et = fallback_data["w"], fallback_data["p"], fallback_data["e"]
        embed = discord.Embed(color=self._col)
        embed.set_author(name=data.title, url=_DF_URL + quote(data.word), icon_url=_IKON)
        description = f"*({data.type})*\n"
        if data.pronounciation:
            description += t("webster.embed.pronunciation", value=data.pronounciation) + "\n"
        elif not data.pronounciation and fb_word == data.word and fb_pr:
            description += t("webster.embed.pronunciation", value=fb_pr) + "\n"
        if data.etymology:
            ety_parsed = WebsterTokenParser.parse(data.etymology, self._token_formatter)
            description += t("webster.embed.etymology", value=ety_parsed) + "\n"
        elif not data.etymology and fb_word == data.word and fb_et:
            ety_parsed = WebsterTokenParser.parse(fb_et, self._token_formatter)
            description += t("webster.embed.etymology", value=ety_parsed) + "\n"
        meanings_compilation = []
        for nn, meaning in enumerate(data.meanings, 1):
            m_text = ""
            if meaning.divider:
                m_text += f"*{meaning.divider}*\n"
            if isinstance(meaning.meanings, list):
                for senses in meaning.meanings:
                    num_n = senses.numbering
                    if not num_n:
                        num_n = str(nn)
                    fmt_sense = WebsterTokenParser.parse(senses.content, self._token_formatter)
                    text_joiner = f"**{num_n}** {fmt_sense}"
                    meanings_compilation.append(text_joiner)
            else:
                sense = meaning.meanings
                num_n = sense.numbering
                if not num_n:
                    num_n = str(nn)
                fmt_sense = WebsterTokenParser.parse(sense.content, self._token_formatter)
                text_joiner = f"**{num_n}** {fmt_sense}"
                meanings_compilation.append(text_joiner)
        description += "\n" + t("webster.embed.meanings") + "\n" + "\n".join(meanings_compilation)
        embed.description = description
        example_compilation = []
        for nn, example in enumerate(data.examples, 1):
            num_n = example.numbering
            if not num_n:
                num_n = str(nn)
            fmt_sense = WebsterTokenParser.parse(example.content, self._token_formatter)
            text_joiner = f"**{num_n}** {fmt_sense}"
            example_compilation.append(text_joiner)
        if len(example_compilation) > 0:
            embed.add_field(name=t("webster.embed.examples"), value="\n".join(example_compilation), inline=False)
        suggested_word = []
        for suggestion_number, suggest in enumerate(data.suggested, 1):
            num_n = suggest.numbering
            if not num_n:
                num_n = str(suggestion_number)
            fmt_sense = WebsterTokenParser.parse(suggest.content, self._token_formatter)
            text_joiner = f"**{num_n}** {fmt_sense}"
            suggested_word.append(text_joiner)
        if len(suggested_word) > 0:
            embed.add_field(name=t("webster.embed.similar_words"), value="\n".join(suggested_word), inline=False)
        embed.set_footer(text=t("webster.embed.footer"))
        return embed

    @app_commands.command(
        name="define",
        description=app_commands.locale_str(
            "Cari definisi kata bahasa inggris di Merriam-Webster",
            key="kutubuku.define.description",
        ),
    )
    @app_commands.describe(
        word=app_commands.locale_str("Kata yang ingin dicari", key="kutubuku.define.option_word"),
    )
    async def word_define_slash_cmd(self, inter: discord.Interaction, word: str):
        """Cari definisi kata bahasa inggris di Merriam-Webster"""
        ctx = await self.bot.get_context(inter)
        self.logger.info(f"Searching defintion for: {word}")
        await ctx.defer()
        if self._mw is None:
            return await ctx.send(ctx.t("webster.service_unavailable"))
        main_results = await self._mw.define(word)
        main_results = list(filter(lambda x: x.title != "", main_results))

        if len(main_results) < 1:
            self.logger.warning(f"No results returned for {word} definitions")
            return await ctx.send(content=ctx.t("define.not_found"))

        first_ety = main_results[0].etymology
        first_pronoun = main_results[0].pronounciation
        first_word = main_results[0].word

        ftp_gen = ftpartial(
            self._design_word_define_embed,
            fallback_data={"e": first_ety, "p": first_pronoun, "w": first_word},
            t=ctx.t,
        )

        self.logger.info(f"Got {len(main_results)} data for {word} definitions")
        main_gen = DiscordPaginatorUI(ctx, main_results, 25.0)
        main_gen.attach(ftp_gen)
        self.logger.info("Sending results to user...")
        await main_gen.interact()

    @app_commands.command(
        name="thesaurus",
        description=app_commands.locale_str(
            "Cari sinonim/antonim kata bahasa inggris di Merriam-Webster",
            key="kutubuku.thesaurus.description",
        ),
    )
    @app_commands.describe(
        word=app_commands.locale_str("Kata yang ingin dicari", key="kutubuku.thesaurus.option_word"),
    )
    async def thesaurus_cmd(self, inter: discord.Interaction, word: str):
        """Cari sinonim/antonim kata bahasa inggris di Merriam-Webster"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()

        self.logger.info(f"Searching thesaurus data for: {word}")
        if self._mw is None:
            return await ctx.send(ctx.t("webster.service_unavailable"))
        main_results = await self._mw.thesaurize(word)
        main_results = list(filter(lambda x: x.word != "", main_results))

        if len(main_results) < 1:
            self.logger.warning(f"No results returned for {word} thesaurus")
            return await ctx.send(ctx.t("thesaurus.not_found"))

        self.logger.info(f"Got {len(main_results)} data for {word} thesaurus")

        def _generate_embed(data: WebsterWordThesaurus):
            embed = discord.Embed(color=self._col)
            embed.set_author(name=data.word, url=_TS_URL + quote(data.word), icon_url=_IKON)
            deskripsi = f"*({data.type})*\n"
            formatted_strings = []
            for tts in data.thesaurus:
                text_inside = "- " + tts.meaning
                if len(tts.synonyms) > 0:
                    text_inside += "\n" + ctx.t("webster.embed.synonyms", value=", ".join(tts.synonyms))
                if len(tts.antonyms) > 0:
                    text_inside += "\n" + ctx.t("webster.embed.antonyms", value=", ".join(tts.antonyms))

                formatted_strings.append(text_inside)
            deskripsi += "\n".join(formatted_strings)
            embed.description = deskripsi
            embed.set_footer(text=ctx.t("webster.embed.footer"))
            return embed

        main_gen = DiscordPaginatorUI(ctx, main_results, 25.0)
        main_gen.attach(_generate_embed)
        self.logger.info("Sending results to user...")
        await main_gen.interact()


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuWebster(bot))
