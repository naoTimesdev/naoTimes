import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot

_F = "https://discordapp.com/assets/e99e3416d4825a09c106d7dfe51939cf.svg"
_KERANG = "https://www.shodor.org/~alexc/pics/MagicConch.png"
_8BALL = "https://www.horoscope.com/images-US/games/game-magic-8-ball-no-text.png"


class FunTanyaJawab(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.TanyaJawab")

    @app_commands.command(
        name="f",
        description=app_commands.locale_str("Berikan respek (press F)", key="fun.respek.description"),
    )
    @app_commands.describe(pesan=app_commands.locale_str("Untuk apa respeknya", key="fun.respek.option_pesan"))
    async def _fun_tanya_f(self, inter: discord.Interaction, pesan: str | None = None):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        pemberi_f = str(inter.user)
        if pesan:
            rtext = i18n.t("respek.embed_value", message=pesan)
        else:
            rtext = i18n.t("respek.embed_value_empty")

        embed = discord.Embed(timestamp=self.bot.now().datetime, color=discord.Colour.random())
        embed.set_thumbnail(url=_F)
        embed.add_field(name=pemberi_f, value=rtext)
        await inter.response.send_message(embed=embed)

    @app_commands.command(
        name="kerang",
        description=app_commands.locale_str("Tanya kerang ajaib", key="fun.kerang.description"),
    )
    @app_commands.describe(
        pertanyaan=app_commands.locale_str("Pertanyaan untuk kerang", key="fun.kerang.option_pertanyaan")
    )
    async def _fun_tanya_kerang(self, inter: discord.Interaction, pertanyaan: str):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        rand = random.random()
        author: discord.User | discord.Member = inter.user
        embed = discord.Embed(
            title=i18n.t("kerang.embed_title"), timestamp=self.bot.now().datetime, color=discord.Colour.random()
        )
        embed.set_thumbnail(url=_KERANG)
        answer = i18n.t("kerang.answer_yes")
        if rand <= 0.5:
            answer = i18n.t("kerang.answer_no")
        embed.description = i18n.t("kerang.embed_description", question=pertanyaan, answer=answer)
        embed.set_footer(text=i18n.t("kerang.embed_footer", author=author), icon_url=author.avatar)
        await inter.response.send_message(embed=embed)

    @app_commands.command(
        name="crot",
        description=app_commands.locale_str("Cek kekuatan... bertahan", key="fun.crot.description"),
    )
    @app_commands.describe(
        orang=app_commands.locale_str("Orang yang diperiksa (default: kamu)", key="fun.crot.option_orang")
    )
    async def _fun_tanya_crot(self, inter: discord.Interaction, orang: discord.Member | None = None):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        target_user: discord.User | discord.Member = orang or inter.user

        waktu = [i18n.t(f"crot.duration_{index}") for index in range(20)]

        pilih_waktu = random.choice(waktu)

        await inter.response.send_message(i18n.t("crot.result", target=target_user, duration=pilih_waktu))

    @app_commands.command(
        name="8ball",
        description=app_commands.locale_str("Tanya bola delapan", key="fun.eightball.description"),
    )
    @app_commands.describe(
        pertanyaan=app_commands.locale_str("Pertanyaan untuk bola delapan", key="fun.eightball.option_pertanyaan")
    )
    async def _fun_tanya_8ball(self, inter: discord.Interaction, pertanyaan: str):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        JAWABAN = {
            "positif": [i18n.t(f"eightball.positive_{index}") for index in range(10)],
            "netral": [i18n.t(f"eightball.neutral_{index}") for index in range(5)],
            "negatif": [i18n.t(f"eightball.negative_{index}") for index in range(5)],
        }
        WARNA_JAWABAN = {
            "positif": 0x6AC213,
            "netral": 0xFFDC4A,
            "negatif": 0xFF4A4A,
        }
        author: discord.User | discord.Member = inter.user

        # chance = 300
        positif_get = ["positif"] * 120
        netral_get = ["netral"] * 100
        negatif_get = ["negatif"] * 80

        full_get_data = positif_get + netral_get + negatif_get
        for _ in range(random.randint(3, 10)):
            random.shuffle(full_get_data)

        select_one = random.choice(full_get_data)
        jawaban = JAWABAN[select_one]
        colored = WARNA_JAWABAN[select_one]
        answer_of_life = random.choice(jawaban)

        embed = discord.Embed(
            title=i18n.t("eightball.embed_title"),
            timestamp=self.bot.now().datetime,
            color=colored,
        )
        embed.set_thumbnail(url=_8BALL)
        embed.description = i18n.t("eightball.embed_description", question=pertanyaan, answer=answer_of_life)
        embed.set_footer(text=i18n.t("eightball.embed_footer", author=author), icon_url=author.avatar)
        await inter.response.send_message(embed=embed)

    @app_commands.command(
        name="agama",
        description=app_commands.locale_str("Tanya agama seseorang/sesuatu", key="fun.agama.description"),
    )
    @app_commands.describe(
        tentang=app_commands.locale_str("Tentang apa (default: kamu)", key="fun.agama.option_tentang")
    )
    async def _fun_tanya_agama(self, inter: discord.Interaction, tentang: str = ""):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        if not tentang:
            tentang = str(inter.user)
        tentang = f"**{tentang}**"

        pilihan_agama = [i18n.t(f"agama.choice_{index}") for index in range(11)]

        await inter.response.send_message(i18n.t("agama.result", tentang=tentang, answer=random.choice(pilihan_agama)))

    @app_commands.command(
        name="ras",
        description=app_commands.locale_str("Tanya ras seseorang/sesuatu", key="fun.ras.description"),
    )
    @app_commands.describe(tentang=app_commands.locale_str("Tentang apa (default: kamu)", key="fun.ras.option_tentang"))
    async def _fun_tanya_ras(self, inter: discord.Interaction, tentang: str = ""):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        if not tentang:
            tentang = str(inter.user)
        tentang = f"**{tentang}**"

        pilihan_ras = [i18n.t(f"ras.choice_{index}") for index in range(26)]

        text_to_send = i18n.t("ras.result", tentang=tentang, answer=random.choice(pilihan_ras))
        embed = discord.Embed(description=text_to_send)
        embed.set_footer(text=i18n.t("ras.footer"))
        await inter.response.send_message(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(FunTanyaJawab(bot))
