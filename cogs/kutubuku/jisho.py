import logging
from functools import partial
from typing import Callable

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.http import JishoWord
from naotimes.paginator import DiscordPaginatorUI


class KutubukuJisho(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Jisho")

    @staticmethod
    def _generate_jisho_embed(result: JishoWord, t: Callable[..., str]) -> discord.Embed:
        entri = result.to_dict()
        embed = discord.Embed(color=0x41A51D)
        entri_nama = entri["word"]
        if entri["numbering"] > 0:
            entri_nama += f" [{entri['numbering'] + 1}]"
        embed.set_author(
            name=entri["word"],
            url=result.url,
            icon_url="https://assets.jisho.org/assets/touch-icon-017b99ca4bfd11363a97f66cc4c00b1667613a05e38d08d858aa5e2a35dce055.png",
        )

        deskripsi = ""
        if entri["reading"]:
            kana = entri["reading"].get("kana", None)
            romaji = entri["reading"].get("romaji", "-")
            if kana:
                deskripsi += t("jisho.reading", kana=kana, romaji=romaji) + "\n"
        if entri["other_forms"]:
            parsed_forms = []
            for other in entri["other_forms"]:
                build_text = ""
                build_text += other.get("word") + " "
                reading = other.get("reading", None)
                romaji = other.get("romaji", None)
                if isinstance(reading, str):
                    build_text += f"({reading}) "
                if isinstance(romaji, str):
                    build_text += f"[{romaji}] "
                parsed_forms.append(build_text.rstrip(" "))
            if parsed_forms:
                deskripsi += t("jisho.other_forms", forms="; ".join(parsed_forms)) + "\n"

        deskripsi += "\n"

        arti_data = []
        for n, meaning in enumerate(entri["definitions"], 1):
            build_txt = ""
            parts = " ".join(meaning.get("part", []))
            build_txt += f"**{n}**. "
            if parts:
                build_txt += f"*{parts}* "
            build_txt += meaning.get("definition") or t("jisho.no_definition")
            extra_info = meaning.get("extra_info", "")
            suggestion = meaning.get("suggestion", "")
            tags = meaning.get("tags", "")
            if extra_info:
                build_txt += f"\n  {extra_info}"
            if tags:
                build_txt += f"\n  {tags}"
            if suggestion:
                build_txt += "\n" + t("jisho.see_also", suggestion=suggestion)
            arti_data.append(build_txt)
        if len(arti_data) > 0:
            deskripsi += t("jisho.meanings_title") + "\n" + "\n".join(arti_data) + "\n"
        else:
            deskripsi += t("jisho.meanings_title") + "\n" + t("jisho.no_meanings") + "\n"

        deskripsi += "\n"

        terdapat_di = entri["appearances"]
        jlpt_level = terdapat_di.get("jlpt", None)
        wanikani_level = terdapat_di.get("wanikani", None)

        terdapat_di_data = []
        if isinstance(jlpt_level, str) and jlpt_level:
            terdapat_di_data.append("- " + jlpt_level)
        if isinstance(wanikani_level, str) and wanikani_level:
            terdapat_di_data.append("- " + wanikani_level)

        if terdapat_di_data:
            deskripsi += t("jisho.appears_in") + "\n"
            deskripsi += "\n".join(terdapat_di_data)

        deskripsi = deskripsi.rstrip()
        embed.description = deskripsi
        embed.set_footer(text=t("jisho.footer"))

        return embed

    @app_commands.command(
        name="jisho",
        description=app_commands.locale_str(
            "Melihat informasi atau arti sebuah kata/kanji di Jisho",
            key="kutubuku.jisho.description",
        ),
    )
    @app_commands.describe(
        kata=app_commands.locale_str("kata yang ingin dicari", key="kutubuku.jisho.option_kata"),
    )
    async def _kutubuku_jisho_slash(self, inter: discord.Interaction, kata: str):
        """Melihat informasi atau arti sebuah kata/kanji di Jisho"""
        ctx = await self.bot.get_context(inter)
        self.logger.info(f"searching: {kata}")

        await ctx.defer()
        if self.bot.jisho is None:
            return await ctx.send(ctx.t("jisho.service_unavailable"))
        jisho_results, error_msg = await self.bot.jisho.search(kata)
        if len(jisho_results) < 1:
            return await ctx.send(content=error_msg)

        ui_gen = DiscordPaginatorUI(ctx, jisho_results, 25.0)
        ui_gen.attach(partial(self._generate_jisho_embed, t=ctx.t))
        await ui_gen.interact()

    @app_commands.command(
        name="kanji",
        description=app_commands.locale_str(
            "Melihat informasi sebuah kanji",
            key="kutubuku.kanji.description",
        ),
    )
    @app_commands.describe(
        kanji=app_commands.locale_str("Kanji yang ingin dicari", key="kutubuku.kanji.option_kanji"),
    )
    async def _kutubuku_jisho_kanji(self, inter: discord.Interaction, kanji: str):
        """Melihat informasi sebuah kanji"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        self.logger.info(f"Searching for {kanji}")

        if self.bot.aiosession is None:
            return await ctx.send(ctx.t("kanji.http_unavailable"))
        async with self.bot.aiosession.get(f"https://api.ihateani.me/v1/jisho/kanji/{kanji}") as resp:
            try:
                res = await resp.json()
            except ValueError:
                return await ctx.send(ctx.t("kanji.api_error"))
            except aiohttp.ClientError:
                return await ctx.send(ctx.t("kanji.api_error"))

        if res["code"] != 200 and len(res["data"]) < 1:
            return await ctx.send(ctx.t("kanji.not_found"))

        entries = res["data"]

        def _design_kanji_embed(entri: dict):
            embed = discord.Embed(color=0x41A51D)
            entri_nama = entri["query"]
            pranala = f"https://jisho.org/search/{entri_nama}%20%23kanji"
            embed.set_author(
                name=entri_nama + " #kanji",
                url=pranala,
                icon_url="https://assets.jisho.org/assets/touch-icon-017b99ca4bfd11363a97f66cc4c00b1667613a05e38d08d858aa5e2a35dce055.png",
            )

            entri_radikal = entri["radical"]
            goresan = entri["strokes"]
            radicals = f"{entri_radikal['symbol']} ({entri_radikal['meaning']})"
            bagian = ", ".join(entri["parts"])
            arti = ", ".join(entri["meanings"])

            embed.description = ctx.t("kanji.header", meanings=arti, radicals=radicals) + "\n"
            embed.description += ctx.t("kanji.details", parts=bagian, strokes=goresan["count"])
            embed.set_thumbnail(url=goresan["gif"])
            embed.set_image(url=goresan["diagram"])

            kunyomis = entri["kunyomi"]
            kunyomi_writing = ""
            for n, kata in enumerate(kunyomis["words"], 1):
                kunyomi_writing += f"**{n}.** {kata['word']} [Romaji: `{kata['romaji']}`]\n"
            if kunyomi_writing and len(kunyomis.get("examples", [])) > 0:
                kunyomi_writing += "\n" + ctx.t("kanji.examples") + "\n"
            for n, contoh in enumerate(kunyomis["examples"], 1):
                kunyomi_writing += f"**{n}.** {contoh['word']} ({contoh['reading']}) [Romaji: `{contoh['romaji']}`]\n"
                kunyomi_writing += f"*{contoh['meaning']}*\n"
            kunyomi_writing = kunyomi_writing.rstrip()
            if kunyomi_writing:
                embed.add_field(name=ctx.t("kanji.kunyomi"), value=kunyomi_writing)

            onyomis = entri["onyomi"]
            onyomi_writing = ""
            for n, kata in enumerate(onyomis["words"], 1):
                onyomi_writing += f"**{n}.** {kata['word']} [Romaji: `{kata['romaji']}`]\n"
            if onyomi_writing and len(onyomis.get("examples", [])) > 0:
                onyomi_writing += "\n" + ctx.t("kanji.examples") + "\n"
            for n, contoh in enumerate(onyomis["examples"], 1):
                onyomi_writing += f"**{n}.** {contoh['word']} ({contoh['reading']}) [Romaji: `{contoh['romaji']}`]\n"
                onyomi_writing += f"*{contoh['meaning']}*\n"
            onyomi_writing = onyomi_writing.rstrip()
            if onyomi_writing:
                embed.add_field(name=ctx.t("kanji.onyomi"), value=onyomi_writing)

            footer_text = []
            if entri.get("jlpt"):
                footer_text.append(f"JLPT {entri['jlpt']}")
            if entri.get("taughtIn"):
                taught = entri["taughtIn"]
                if "grade" in taught:
                    taught = taught.replace("grade", ctx.t("kanji.grade"))
                elif "junior high" in taught.lower():
                    taught = ctx.t("kanji.junior_high")
                footer_text.append(ctx.t("kanji.taught_in", taught=taught))
            footer_text.append(ctx.t("kanji.footer"))
            embed.set_footer(text=" | ".join(footer_text).rstrip())
            return embed

        if not entries:
            return await ctx.send(ctx.t("kanji.not_found"))

        ui_gen = DiscordPaginatorUI(ctx, entries, 25.0)
        ui_gen.attach(_design_kanji_embed)
        await ui_gen.interact()


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuJisho(bot))
