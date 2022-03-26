import logging

import aiohttp
import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesAppContext, naoTimesContext
from naotimes.http import JishoWord
from naotimes.paginator import DiscordPaginatorUI


class KutubukuJisho(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.Jisho")

    @staticmethod
    def _generate_jisho_embed(result: JishoWord) -> disnake.Embed:
        entri = result.to_dict()
        embed = disnake.Embed(color=0x41A51D)
        entri_nama = entri["word"]
        if entri["numbering"] > 0:
            entri_nama += f" [{entri['numbering'] + 1}]"
        embed.set_author(
            name=entri["word"],
            url=result.url,
            icon_url="https://assets.jisho.org/assets/touch-icon-017b99ca4bfd11363a97f66cc4c00b1667613a05e38d08d858aa5e2a35dce055.png",  # noqa: E501
        )

        deskripsi = ""
        if entri["reading"]:
            kana = entri["reading"].get("kana", None)
            romaji = entri["reading"].get("romaji", "-")
            if kana:
                deskripsi += f"**Pelafalan**: {kana} [Romaji: {romaji}]\n"
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
                deskripsi += "**Bentuk lain**: " + "; ".join(parsed_forms) + "\n"

        deskripsi += "\n"

        arti_data = []
        for n, meaning in enumerate(entri["definitions"], 1):
            build_txt = ""
            parts = " ".join(meaning.get("part", []))
            build_txt += f"**{n}**. "
            if parts:
                build_txt += f"*{parts}* "
            build_txt += meaning.get("definition", "Tidak ada definisi")
            extra_info = meaning.get("extra_info", "")
            suggestion = meaning.get("suggestion", "")
            tags = meaning.get("tags", "")
            if extra_info:
                build_txt += f"\n  {extra_info}"
            if tags:
                build_txt += f"\n  {tags}"
            if suggestion:
                build_txt += f"\n  Lihat juga: {suggestion}"
            arti_data.append(build_txt)
        if len(arti_data) > 0:
            deskripsi += "**Makna/Arti**\n" + "\n".join(arti_data) + "\n"
        else:
            deskripsi += "**Makna/Arti**\n*Tidak ada makna/arti*\n"

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
            deskripsi += "**Terdapat di**:\n"
            deskripsi += "\n".join(terdapat_di_data)

        deskripsi = deskripsi.rstrip()
        embed.description = deskripsi
        embed.set_footer(text="Menggunakan Jisho + Romkan dan data JMDict")

        return embed

    @commands.command(name="jisho")
    async def _kutubuku_jisho(self, ctx: naoTimesContext, *, keyword: str = ""):
        if not keyword:
            return await ctx.send("Mohon berikan kata atau kalimat yang ingin dicari")

        self.logger.info(f"searching: {keyword}")
        jisho_results, error_msg = await self.bot.jisho.search(keyword)
        if len(jisho_results) < 1:
            return await ctx.send(error_msg)

        ui_gen = DiscordPaginatorUI(ctx, jisho_results, 25.0)
        ui_gen.attach(self._generate_jisho_embed)
        await ui_gen.interact()

    @commands.slash_command(name="jisho")
    async def _kutubuku_jisho_slash(self, ctx: naoTimesAppContext, kata: str):
        """Melihat informasi atau arti sebuah kata/kanji di Jisho

        Parameters
        ----------
        kata: Kata yang ingin dicari
        """
        self.logger.info(f"searching: {kata}")

        await ctx.defer()
        jisho_results, error_msg = await self.bot.jisho.search(kata)
        if len(jisho_results) < 1:
            return await ctx.send(content=error_msg)

        first_result = self._generate_jisho_embed(jisho_results[0])
        await ctx.send(embed=first_result)

    @commands.command(name="kanji")
    async def _kutubuku_jisho_kanji(self, ctx: naoTimesContext, kanji: str):
        self.logger.info(f"Searching for {kanji}")

        async with self.bot.aiosession.get(f"https://api.ihateani.me/v1/jisho/kanji/{kanji}") as resp:
            try:
                res = await resp.json()
            except ValueError:
                return await ctx.send("Tidak bisa menghubungi API...")
            except aiohttp.ClientError:
                return await ctx.send("Tidak bisa menghubungi API...")

        if res["code"] != 200 and len(res["data"]) < 1:
            return await ctx.send("Kanji tidak dapat ditemukan!")

        entries = res["data"]

        def _design_kanji_embed(entri: dict):
            embed = disnake.Embed(color=0x41A51D)
            entri_nama = entri["query"]
            pranala = f"https://jisho.org/search/{entri_nama}%20%23kanji"
            embed.set_author(
                name=entri_nama + " #kanji",
                url=pranala,
                icon_url="https://assets.jisho.org/assets/touch-icon-017b99ca4bfd11363a97f66cc4c00b1667613a05e38d08d858aa5e2a35dce055.png",  # noqa: E501
            )

            entri_radikal = entri["radical"]
            goresan = entri["strokes"]
            radicals = f"{entri_radikal['symbol']} ({entri_radikal['meaning']})"
            bagian = ", ".join(entri["parts"])
            arti = ", ".join(entri["meanings"])

            embed.description = f"**Arti**: {arti}\n**Radikal**: {radicals}\n"
            embed.description += f"**Bagian**: {bagian}\n**Goresan**: {goresan['count']}"
            embed.set_thumbnail(url=goresan["gif"])
            embed.set_image(url=goresan["diagram"])

            kunyomis = entri["kunyomi"]
            kunyomi_writing = ""
            for n, kata in enumerate(kunyomis["words"], 1):
                kunyomi_writing += f"**{n}.** {kata['word']} [Romaji: `{kata['romaji']}`]\n"
            if kunyomi_writing:
                kunyomi_writing += "\n**Contoh**\n"
            for n, contoh in enumerate(kunyomis["examples"], 1):
                kunyomi_writing += (
                    f"**{n}.** {contoh['word']} ({contoh['reading']}) [Romaji: `{contoh['romaji']}`]\n"
                )
                kunyomi_writing += f"*{contoh['meaning']}*\n"
            embed.add_field(name="Kunyomi", value=kunyomi_writing.rstrip())

            onyomis = entri["onyomi"]
            onyomi_writing = ""
            for n, kata in enumerate(onyomis["words"], 1):
                onyomi_writing += f"**{n}.** {kata['word']} [Romaji: `{kata['romaji']}`]\n"
            if onyomi_writing:
                onyomi_writing += "\n**Contoh**\n"
            for n, contoh in enumerate(onyomis["examples"], 1):
                onyomi_writing += (
                    f"**{n}.** {contoh['word']} ({contoh['reading']}) [Romaji: `{contoh['romaji']}`]\n"
                )
                onyomi_writing += f"*{contoh['meaning']}*\n"
            embed.add_field(name="Onyomi", value=onyomi_writing.rstrip())

            footer_text = []
            if "jlpt" in entri and entri["jlpt"]:
                footer_text.append(f"JLPT {entri['jlpt']}")
            if "taughtIn" in entri and entri["taughtIn"]:
                taught = entri["taughtIn"]
                if "grade" in taught:
                    taught = taught.replace("grade", "kelas")
                elif "junior high" in taught.lower():
                    taught = "kelas SMP"
                footer_text.append(f"Diajarkan pada {taught}")
            footer_text.append("Diprakasai oleh Jisho")
            embed.set_footer(text=" | ".join(footer_text).rstrip())
            return embed

        ui_gen = DiscordPaginatorUI(ctx, entries, 25.0)
        ui_gen.attach(_design_kanji_embed)
        await ui_gen.interact()


def setup(bot: naoTimesBot):
    bot.add_cog(KutubukuJisho(bot))
