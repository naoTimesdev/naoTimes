import logging
import random

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext

_F = "https://discordapp.com/assets/e99e3416d4825a09c106d7dfe51939cf.svg"
_KERANG = "https://www.shodor.org/~alexc/pics/MagicConch.png"
_8BALL = "https://www.horoscope.com/images-US/games/game-magic-8-ball-no-text.png"


class FunTanyaJawab(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.TanyaJawab")

    @commands.command(name="f")
    async def _fun_tanya_f(self, ctx: naoTimesContext, *, pesan: str = None):
        pemberi_f = str(ctx.author)
        rtext = "telah memberikan respek"
        if pesan:
            rtext += f" untuk `{pesan}`"
        rtext += "."

        embed = discord.Embed(timestamp=self.bot.now().datetime, color=discord.Colour.random())
        embed.set_thumbnail(url=_F)
        embed.add_field(name=pemberi_f, value=rtext)
        await ctx.send(embed=embed)

    @commands.command(name="kerang", aliases=["kerangajaib"])
    async def _fun_tanya_kerang(self, ctx: naoTimesContext, *, pertanyaan: str):
        rand = random.random()
        author: discord.User = ctx.author
        embed = discord.Embed(
            title="Kerang Ajaib", timestamp=self.bot.now().datetime, color=discord.Colour.random()
        )
        embed.set_thumbnail(url=_KERANG)
        answer = "Ya"
        if rand <= 0.5:
            answer = "Tidak"
        embed.description = f"**{pertanyaan}**\n{answer}"
        embed.set_footer(text=f"Ditanyakan oleh: {author}", icon_url=author.avatar)
        await ctx.send(embed=embed)

    @commands.command(name="8ball")
    async def _fun_tanya_8ball(self, ctx: naoTimesContext, *, pertanyaan: str):
        JAWABAN = {
            "positif": [
                "Pastinya.",
                "Woiyadong.",
                "Takusah ragu.",
                "Tentu saja.",
                "Kalau kau yakin, mungkin saja.",
                "Kalau begitu, iya.",
                "Sudah seharusnya.",
                "Mungkin saja.",
                "Yoi.",
                'Aku sih "yes."',
            ],
            "netral": [
                "Masih belum pasti, coba lagi.",
                "Tanyakan lain waktu, ya.",
                "Nanti akan kuberitahu.",
                "Aku tidak bisa menebaknya sekarang.",
                "Konsentrasi lalu coba lagi.",
            ],
            "negatif": [
                "Jangan harap.",
                "Gak.",
                'Kata bapak tebe, "Gak boleh!"',
                "Tidak mungkin.",
                "Ya enggak lah, pekok!",
            ],
        }
        WARNA_JAWABAN = {
            "positif": 0x6AC213,
            "netral": 0xFFDC4A,
            "negatif": 0xFF4A4A,
        }
        author: discord.User = ctx.author

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

        tukang_tanya = f"Ditanyakan oleh: {str(author)}"

        embed = discord.Embed(
            title="Bola delapan (8 Ball)",
            timestamp=self.bot.now().datetime,
            color=colored,
        )
        embed.set_thumbnail(url=_8BALL)
        embed.description = f"**{pertanyaan}**\n{answer_of_life}"
        embed.set_footer(text=tukang_tanya, icon_url=author.avatar)
        await ctx.send(embed=embed)

    @commands.command(name="agama")
    async def _fun_tanya_agama(self, ctx: naoTimesContext, *, tentang: str = ""):
        if not tentang:
            tentang = str(ctx.author)
        tentang = f"**{tentang}**"

        pilihan_agama = [
            "Islam",
            "Katolik",
            "Protestan",
            "Kong Hu Cu",
            "Budha",
            "Hindu",
            "Atheis",
            "Agnostik",
            "Shinto",
            "Yahudi",
        ]

        text_to_send = f"Agama {tentang} itu apa?\n"
        text_to_send += f"{random.choice(pilihan_agama)}."
        await ctx.send(text_to_send)


def setup(bot: naoTimesBot):
    bot.add_cog(FunTanyaJawab(bot))
