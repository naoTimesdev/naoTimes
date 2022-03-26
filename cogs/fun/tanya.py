import logging
import random

import disnake
from disnake.ext import commands

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

        embed = disnake.Embed(timestamp=self.bot.now().datetime, color=disnake.Colour.random())
        embed.set_thumbnail(url=_F)
        embed.add_field(name=pemberi_f, value=rtext)
        await ctx.send(embed=embed)

    @commands.command(name="kerang", aliases=["kerangajaib"])
    async def _fun_tanya_kerang(self, ctx: naoTimesContext, *, pertanyaan: str):
        rand = random.random()
        author: disnake.User = ctx.author
        embed = disnake.Embed(
            title="Kerang Ajaib", timestamp=self.bot.now().datetime, color=disnake.Colour.random()
        )
        embed.set_thumbnail(url=_KERANG)
        answer = "Ya"
        if rand <= 0.5:
            answer = "Tidak"
        embed.description = f"**{pertanyaan}**\n{answer}"
        embed.set_footer(text=f"Ditanyakan oleh: {author}", icon_url=author.avatar)
        await ctx.send(embed=embed)

    @commands.command(name="crot")
    async def _fun_tanya_crot(self, ctx: naoTimesContext, *, orang: commands.MemberConverter = None):
        if orang is None:
            orang = ctx.author

        if not isinstance(orang, (disnake.Member, disnake.User)):
            return await ctx.send(
                "Bot tidak menemukan orang tersebut, jadi tidak bisa memeriksa kekuatan crot!"
            )

        waktu = [
            "1 detik",
            "5 detik",
            "20 detik",
            "1 menit",
            "5 menit",
            "15 menit",
            "30 menit",
            "1 jam",
            "4 jam",
            "12 jam",
            "24 jam",
            "sepekan",
            "1 bulan",
            "3 bulan",
            "6 bulan",
            "1 tahun",
            "10 tahun",
            "25 tahun",
            "50 tahun",
            "69 tahun",
        ]

        pilih_waktu = random.choice(waktu)

        pesan = f"**{orang}** bertahan selama {pilih_waktu} lalu akhirnya klimaks dan crot"
        await ctx.send(pesan)

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
        author: disnake.User = ctx.author

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

        embed = disnake.Embed(
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
            "Sunda",
        ]

        text_to_send = f"Agama {tentang} itu apa?\n"
        text_to_send += f"{random.choice(pilihan_agama)}."
        await ctx.send(text_to_send)

    @commands.command(name="ras")
    async def _fun_tanya_ras(self, ctx: naoTimesContext, *, tentang: str = ""):
        if not tentang:
            tentang = str(ctx.author)
        tentang = f"**{tentang}**"

        pilihan_ras = [
            "Jawa",
            "Sunda",
            "Batak",
            "Cina",
            "Bugis",
            "Asmat",
            "Mongoloid",
            "Melayu",
            "YOASOBI Gendut",
            "Samin",
            "Yahudi",
            "Arya",
            "Ngapak",
            "Madura",
            "Minang",
            "Dayak",
            "Banjar",
            "Arab",
            "Wibu",
            "Gay-mer",
            "Ras hanip, kontol anjing",
            "Cebong",
            "Kampret",
            "Pembuat mobil",
            "Kadrun",
            "Gen Halilintar",
        ]

        text_to_send = f"Ras {tentang} itu apa?\n"
        text_to_send += f"{random.choice(pilihan_ras)}."
        embed = disnake.Embed(description=text_to_send)
        embed.set_footer(text="Jangan dibawa serius :)")
        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(FunTanyaJawab(bot))
