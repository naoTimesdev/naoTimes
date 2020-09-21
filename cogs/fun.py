import logging
import random
import re

import discord
import numpy as np
from discord.ext import commands

logger = logging.getLogger("cogs.fun")


def setup(bot):
    logger.debug("adding cogs...")
    bot.add_cog(Fun(bot))


def get_user_status(mode: str) -> str:
    statuses_list = {
        "OL": [
            "Terhubung",
            "Berselancar di Internet",
            "Online",
            "Aktif",
            "Masih Hidup",
            "Belum mati",
            "Belum ke-isekai",
            "Masih di Bumi",
            "Ada koneksi Internet",
            "Dar(l)ing",
            "Daring",
            "Bersama keluarga besar (Internet)",
            "Ngobrol",
            "Nge-meme bareng",
        ],
        "IDL": [
            "Halo kau di sana?",
            "Ketiduran",
            "Nyawa di pertanyakan",
            "Halo????",
            "Riajuu mungkin",
            "Idle",
            "Gak aktif",
            "Jauh dari keyboard",
            "Lagi baper bentar",
            "Nonton Anime",
            "Lupa matiin data",
            "Lupa disconnect wifi",
            "Bengong",
        ],
        "DND": [
            "Lagi riajuu bentar",
            "Sibuk ~~onani/masturbasi~~",
            "Pacaran (joudan desu)",
            "Mungkin tidur",
            "Memantau keadaan",
            "Jadi satpam",
            "Mata-mata jadinya sibuk",
            "Bos besar supersibuk",
            "Ogah di-spam",
            "Nonton Anime",
            "Nonton Boku no Pico",
            "Nonton Dorama",
            "Sok sibuk",
            "Status kesukaan Kresbayyy",
            "Gangguin Mantan",
            "Ngestalk Seseorang",
            "Nge-roll gacha",
            "Nonton JAV",
            "Baca Doujinshi R-18++++",
            "Do not disturb",
            "Jangan ganggu",
        ],
        "OFF": [
            "Mokad",
            "Off",
            "Tidak online",
            "Bosen hidup",
            "Dah bundir",
            "Dah di Isekai",
            "zzz",
            "Pura-pura off",
            "Invisible deng",
            "Memantau dari kejauhan",
            "Lagi comfy camping",
            "Riajuu selamanya",
            "Gak punya koneksi",
            "Gak ada sinyal",
            "Kuota habis",
        ],
    }
    status = statuses_list.get(mode, ["Unknown"])
    return random.choice(status)


def translate_date(str_: str) -> str:
    hari = {
        "Monday": "Senin",
        "Tuesday": "Selasa",
        "Wednesday": "Rabu",
        "Thursday": "Kamis",
        "Friday": "Jumat",
        "Saturday": "Sabtu",
        "Sunday": "Minggu",
    }

    bulan = {
        "January": "Januari",
        "February": "Februari",
        "March": "Maret",
        "April": "April",
        "May": "Mei",
        "June": "Juni",
        "July": "Juli",
        "August": "Agustus",
        "September": "September",
        "October": "Oktober",
        "November": "November",
        "December": "Desember",
    }

    for k, v in hari.items():
        str_ = str_.replace(k, v)
    for k, v in bulan.items():
        str_ = str_.replace(k, v)
    return str_


class Fun(commands.Cog):
    """A shitty fun system"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.fun.Fun")

    @commands.Cog.listener()
    async def on_message(self, msg):
        if self.bot.user.id == msg.author.id:
            return

        channeru = msg.channel

        cermin_compiler = re.compile(
            r"cermin(?:,|) cermin di dinding(?:,|) siapa(?:kah|)(?: orang|) yang(?: paling|) (?:ter|)(?:\w+) dari mereka semua(?:\?|)",  # noqa: E501
            re.IGNORECASE,
        )
        if re.findall(cermin_compiler, msg.clean_content):
            randd = random.uniform(0.5, 1.5)

            if randd <= 0.9:
                ava = msg.author.avatar_url
                user_name = "{0.name}#{0.discriminator}".format(msg.author)
            else:
                guild_members = msg.guild.members
                guild_members = [member for member in guild_members if not member.bot]
                usr = random.choice(guild_members)

                ava = usr.avatar_url
                user_name = "{0.name}#{0.discriminator}".format(usr)

            ans = discord.Embed(
                title=msg.clean_content,
                description="Tentu saja: {}".format(user_name),
                timestamp=msg.created_at,
                color=0x3974B8,
            )
            ans.set_image(url=ava)
            await channeru.send(embed=ans)

        # titikduaV = re.compile(
        #     r"((:|\uFF1A|\uFE55|\uFE13)v|v(:|\uFF1A|\uFE55|\uFF13))",
        #     re.IGNORECASE,
        # )

    @commands.command(aliases=["user", "uinfo", "userinfo"])
    async def ui(self, ctx, *, name=""):
        if name:
            try:
                if name.isdigit():
                    user = ctx.message.guild.get_member(int(name))
                else:
                    user = ctx.message.mentions[0]
            except IndexError:
                user = ctx.guild.get_member_named(name)
            if not user:
                user = ctx.guild.get_member_named(name)
            if not user:
                return await ctx.send("Tidak bisa mencari user tersebut")
        else:
            user = ctx.message.author

        avi = user.avatar_url

        if isinstance(user, discord.Member):
            role = user.top_role.name
            if role == "@everyone" or role == "semuanya":
                role = "N/A"

        try:
            status = user.status
            status = str(status).capitalize()
            if "Online" in status:
                status = get_user_status("OL")
                if status not in ("Aktif", "Online", "OL"):
                    status += "\n`(Online)`"
            elif "Idle" in status:
                status = get_user_status("IDL")
                if status not in ("Idle"):
                    status += "\n`(Idle)`"
            elif "Dnd" in status:
                status = get_user_status("DND")
                if status not in ("Do not disturb", "Jangan ganggu"):
                    status += "\n`(DnD)`"
            elif "Offline" in status:
                status = get_user_status("OFF")
                if status not in ("Offline", "Off"):
                    status += "\n`(Offline/Invisible)`"
            if user.nick is None:
                nickname = "Tidak ada"
            else:
                nickname = user.nick
            em = discord.Embed(timestamp=ctx.message.created_at, color=0x708DD0)
            em.add_field(name="ID User", value=user.id, inline=True)
            if isinstance(user, discord.Member):
                em.add_field(name="Panggilan", value=nickname, inline=True)
                em.add_field(name="Status", value=status, inline=True)
                em.add_field(name="Tahta Tertinggi", value=role, inline=True)
                em.add_field(
                    name="Akun dibuat",
                    value=translate_date(user.created_at.__format__("%A, %d. %B %Y @ %H:%M:%S")),
                )
            if isinstance(user, discord.Member):
                em.add_field(
                    name="Bergabung di server ini",
                    value=translate_date(user.joined_at.__format__("%A, %d. %B %Y @ %H:%M:%S")),
                )
            em.set_thumbnail(url=avi)
            em.set_author(name=user, icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            await ctx.send(embed=em)
        except discord.errors.HTTPException:
            if isinstance(user, discord.Member):
                msg = (
                    "**User Info:** ```User ID: %s\nNick: %s\nStatus: %s\nGame: %s\nHighest Role: %s\nAccount Created: %s\nJoin Date: %s\nAvatar url:%s```"  # noqa: E501
                    % (
                        user.id,
                        user.nick,
                        user.status,
                        user.activity,
                        role,
                        translate_date(user.created_at.__format__("%A, %d. %B %Y @ %H:%M:%S")),
                        translate_date(user.joined_at.__format__("%A, %d. %B %Y @ %H:%M:%S")),
                        avi,
                    )
                )
            else:
                msg = "**User Info:** ```User ID: %s\nAccount Created: %s\nAvatar url:%s```" % (  # noqa: E501
                    user.id,
                    user.created_at.__format__("%A, %d. %B %Y @ %H:%M:%S"),
                    avi,
                )
            await ctx.send(msg)

    @commands.command(aliases=["pp", "profile", "bigprofile", "ava"])
    async def avatar(self, ctx, *, name=""):
        if name:
            try:
                if name.isdigit():
                    user = ctx.message.guild.get_member(int(name))
                else:
                    user = ctx.message.mentions[0]
            except IndexError:
                user = ctx.guild.get_member_named(name)
            if not user:
                user = self.bot.get_user(int(name))
            if not user:
                await ctx.send("Tidak bisa mencari user tersebut")
                return
        else:
            user = ctx.message.author

        avi = user.avatar_url

        try:
            em = discord.Embed(title="Ini dia", timestamp=ctx.message.created_at, color=0x708DD0,)
            em.set_image(url=avi)
            await ctx.send(embed=em)
        except discord.errors.HTTPException:
            await ctx.send("Ini dia!\n{}".format(avi))

    @commands.command(aliases=["be", "bigemoji"])
    async def bigemote(self, ctx, emoji: discord.Emoji):
        uri = emoji.url
        uri = uri.replace("https://discordapp.com", "https://cdn.discordapp.com").replace("/api", "") + "?v=1"
        await ctx.send(uri)

    @commands.command()
    async def f(self, ctx, *, pesan=None):
        userthatsayF = str(ctx.message.author.name)
        rtxt = "telah memberikan respek."
        if pesan is not None:
            rtxt = f"telah memberikan respek untuk `{str(pesan)}`"
        Fpaid = discord.Embed(color=0xE3D957, timestamp=ctx.message.created_at)
        Fpaid.set_thumbnail(
            url="https://discordapp.com/assets/e99e3416d4825a09c106d7dfe51939cf.svg"  # noqa: E501
        )
        Fpaid.add_field(name=userthatsayF, value=rtxt, inline=False)
        await ctx.send(embed=Fpaid)

    @commands.command(aliases=["kerangajaib"])
    async def kerang(self, ctx, *, pertanyaan):
        rand = random.randint(0, 1)
        userasking = str(ctx.message.author)
        useravatar = str(ctx.message.author.avatar_url)
        textasker = "Ditanyakan oleh: " + userasking
        pertanyaan = pertanyaan[0].upper() + pertanyaan[1:]
        rel1 = discord.Embed(title="Kerang Ajaib", timestamp=ctx.message.created_at, color=0x8CEEFF,)
        rel1.set_thumbnail(url="https://www.shodor.org/~alexc/pics/MagicConch.png")
        rel1.add_field(name=pertanyaan, value=["Ya", "Tidak"][rand], inline=False)
        rel1.set_footer(text=textasker, icon_url=useravatar)
        await ctx.send(embed=rel1)

    @commands.command()
    async def pilih(self, ctx, *, input_data):
        server_message = str(ctx.message.guild.id)
        print("Requested !pilih at: " + server_message)

        inp_d = input_data.split(",")
        inp_d = [d for d in inp_d if d]

        if not inp_d:
            return await ctx.send("Tidak ada input untuk dipilih\nGunakan `,` sebagai pemisah.")

        if len(inp_d) < 2:
            return await ctx.send("Hanya ada 1 input untuk dipilih\nGunakan `,` sebagai pemisah.")

        gen_num = np.random.uniform(0.0, float(len(inp_d) - 1))

        result = inp_d[round(gen_num)]

        await ctx.send(
            "**{user}** aku memilih: **{res}**".format(user=ctx.message.author.name, res=result.strip())
        )

    @commands.command(aliases=["penis", "dick", "kntl"])
    async def kontol(self, ctx):
        print("Requested !kontol")
        length = random.randint(2, 12)

        txt = "Panjang kntl **{}** adalah:\n".format(ctx.message.author.name)

        multiplier = random.choice([1, 2, 5])
        if multiplier == 1:
            length_name = "cm"
        elif multiplier == 2:
            length_name = "m"
        elif multiplier == 5:
            length_name = "km"
        else:
            length_name = "??"

        txt += "`8"
        txt += "=" * length * multiplier
        txt += "D`"
        txt += " {le}{nam}".format(le=length, nam=length_name)

        await ctx.send(txt)

    @commands.command(name="dadu", aliases=["dice"])
    async def roll_dice(self, ctx, dice_type: str):
        try:
            roll_amount, dice_faces = dice_type.split("d")
        except ValueError:
            return await ctx.send("Jenis dadu tidak diketahui, gunakan format seperti `d20`")

        if roll_amount.strip() == "":
            roll_amount = 1  # type: ignore
        else:
            if not roll_amount.isdigit():
                return await ctx.send(f"Jumlah roll `{roll_amount}` bukanlah angka")
            roll_amount = int(roll_amount)  # type: ignore
        if not dice_faces.isdigit():
            return await ctx.send(f"Jumlah sisi dadu `{dice_faces}` bukanlah angka")
        dice_faces = int(dice_faces)  # type: ignore
        dice_faces_range = list(range(1, dice_faces + 1))  # type: ignore

        total_output = []
        for _ in range(roll_amount):  # type: ignore
            total_output.append(random.choice(dice_faces_range))

        total_output_txt = [f"**{do}**" for do in total_output]

        output_text = f"Hasil kocok dadu (**{dice_type}**): "
        output_text += " + ".join(total_output_txt)
        if len(total_output) > 1:
            output_text += f" = **{sum(total_output)}**"
        await ctx.send(output_text)

    @commands.command(name="kocok", aliases=["roll"])
    async def roll_dice_ranged(self, ctx, max_num: int):
        dice_faces_range = list(range(1, max_num + 1))
        roll_outcome = random.choice(dice_faces_range)

        await ctx.send(f"Hasil kocok dadu: **{roll_outcome}** (**1**-**{max_num}**)")

    @commands.command(name="8ball")
    async def _8ball(self, ctx, *, input_):
        server_message = str(ctx.message.guild.id)
        print("Requested !8ball at: " + server_message)

        jawaban_ = {
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

        # chance 300
        positif_data = ["positif"] * 120
        netral_data = ["netral"] * 67
        negatif_data = ["negatif"] * 63

        randomized_dataset = positif_data + netral_data + negatif_data

        for _ in range(random.randint(3, 10)):
            random.shuffle(randomized_dataset)

        pick_dataset = randomized_dataset[random.randint(0, 9)]

        answer_of_life = random.choice(jawaban_[pick_dataset])

        avatar = str(ctx.message.author.avatar_url)
        ditanyakan = "Ditanyakan oleh: {0.name}#{0.discriminator}".format(ctx.message.author)

        pertanyaan = input_[0].upper() + input_[1:]

        color_of_choice = {
            "positif": 0x6AC213,
            "netral": 0xFFDC4A,
            "negatif": 0xFF4A4A,
        }

        ans = discord.Embed(
            title="Bola delapan (8ball)",
            timestamp=ctx.message.created_at,
            color=color_of_choice[pick_dataset],
        )
        ans.set_thumbnail(
            url="https://www.horoscope.com/images-US/games/game-magic-8-ball-no-text.png"  # noqa: E501
        )
        ans.add_field(name=pertanyaan, value=answer_of_life, inline=False)
        ans.set_footer(text=ditanyakan, icon_url=avatar)
        await ctx.send(embed=ans)
