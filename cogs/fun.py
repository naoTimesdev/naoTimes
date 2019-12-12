import random
import re

import discord
from discord.ext import commands


def setup(bot):
    bot.add_cog(Fun(bot))

def getStatus(mode):
    if mode == 'OL':
        status = [
            'Terhubung',
            'Berselancar di Internet',
            'Online',
            'Aktif',
            'Masih Hidup',
            'Belum mati',
            'Belum ke-isekai',
            'Masih di Bumi',
            'Ada koneksi Internet',
            'Dar(l)ing',
            'Daring',
            'Bersama keluarga besar (Internet)',
            'Ngobrol',
            'Nge-meme bareng'
        ]
        finalOne = random.choice(status)
    elif mode == 'IDL':
        status = [
            'Halo kau di sana?',
            'Ketiduran',
            'Nyawa di pertanyakan',
            'Halo????',
            'Riajuu mungkin',
            'Idle',
            'Gak aktif',
            'Jauh dari keyboard',
            'Lagi baper bentar',
            'Nonton Anime',
            'Lupa matiin data',
            'Lupa disconnect wifi',
            'Bengong'
        ]
        finalOne = random.choice(status)
    elif mode == 'DND':
        status = [
            'Lagi riajuu bentar',
            'Sibuk ~~onani/masturbasi~~',
            'Pacaran (joudan desu)',
            'Mungkin tidur',
            'Memantau keadaan',
            'Jadi satpam',
            'Mata-mata jadinya sibuk',
            'Bos besar supersibuk',
            'Ogah di-spam',
            'Nonton Anime',
            'Nonton Boku no Pico',
            'Nonton Dorama',
            'Sok sibuk',
            'Status kesukaan Kresbayyy',
            'Gangguin Mantan',
            'Ngestalk Seseorang',
            'Nge-roll gacha',
            'Nonton JAV',
            'Baca Doujinshi R-18++++'
        ]
        finalOne = random.choice(status)
    elif mode == 'OFF':
        status = [
            'Mokad',
            'Off',
            'Tidak online',
            'Bosen hidup',
            'Dah bundir',
            'Dah di Isekai',
            'zzz',
            'Pura-pura off',
            'Invisible deng',
            'Memantau dari kejauhan',
            'Lagi comfy camping',
            'Riajuu selamanya',
            'Gak punya koneksi',
            'Gak ada sinyal',
            'Kuota habis'
        ]
        finalOne = random.choice(status)
    finalOne = str(finalOne)
    return finalOne

def translate_date(str_):
    hari = {
        "Monday": "Senin",
        "Tuesday": "Selasa",
        "Wednesday": "Rabu",
        "Thursday": "Kamis",
        "Friday": "Jumat",
        "Saturday": "Sabtu",
        "Sunday": "Minggu"
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
        "December": "Desember"
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

    @commands.Cog.listener()
    async def on_message(self, msg):
        if self.bot.user.id == msg.author.id:
            return

        channeru = msg.channel

        cermin_compiler = re.compile(r"cermin(?:,|) cermin di dinding(?:,|) siapa(?:kah|)(?: orang|) yang(?: paling|) (?:ter|)(?:cantik|ganteng|cakep|tampan|manis|populer|keren|amjat|bangsat|kontol|ampas|jelek|buruk|goblok|sinting|bego) dari mereka semua(?:\?|)", re.IGNORECASE)
        if re.findall(cermin_compiler, msg.clean_content):
            randd = random.randint(0, 1)

            if not randd:
                ava = msg.author.avatar_url
                user_name = '{0.name}#{0.discriminator}'.format(msg.author)
            else:
                guild_members = msg.guild.members
                usr = random.choice(guild_members)

                ava = usr.avatar_url
                user_name = '{0.name}#{0.discriminator}'.format(usr)

            ans = discord.Embed(title="Cermin yang ada di dinding", description="Tentu saja: {}".format(user_name), timestamp=msg.created_at, color=0x3974b8)
            ans.set_image(url=ava)
            ans.set_thumbnail(url="https://p.ihateani.me/WUNfxPei")
            await channeru.send(embed=ans)


    @commands.command(aliases=['user', 'uinfo', 'userinfo'])
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
                user = self.bot.get_user(int(name))
            if not user:
                await ctx.send('Tidak bisa mencari user tersebut')
                return
        else:
            user = ctx.message.author

        avi = user.avatar_url

        if isinstance(user, discord.Member):
            role = user.top_role.name
            if role == "@everyone" or role == "semuanya":
                role = "N/A"
            voice_state = None if not user.voice else user.voice_channel

        try:
            status = user.status
            status = str(status).capitalize()
            if 'Online' in status:
                status = getStatus('OL')
            elif 'Idle' in status:
                status = getStatus('IDL')
            elif 'Dnd' in status:
                status = getStatus('DND')
            elif 'Offline' in status:
                status = getStatus('OFF')
            if user.nick == None:
                nickname = 'Tidak ada'
            else:
                nickname = user.nick
            em = discord.Embed(timestamp=ctx.message.created_at, color=0x708DD0)
            em.add_field(name='ID User', value=user.id, inline=True)
            if isinstance(user, discord.Member):
                em.add_field(name='Panggilan', value=nickname, inline=True)
                em.add_field(name='Status', value=status, inline=True)
                em.add_field(name='Tahta Tertinggi', value=role, inline=True)
                em.add_field(name='Akun dibuat', value=translate_date(user.created_at.__format__('%A, %d. %B %Y @ %H:%M:%S')))
            if isinstance(user, discord.Member):
                em.add_field(name='Bergabung di server ini', value=translate_date(user.joined_at.__format__('%A, %d. %B %Y @ %H:%M:%S')))
            em.set_thumbnail(url=avi)
            em.set_author(name=user, icon_url="https://p.n4o.xyz/i/naotimes_ava.png")
            await ctx.send(embed=em)
        except discord.errors.HTTPException:
            if isinstance(user, discord.Member):
                msg = '**User Info:** ```User ID: %s\nNick: %s\nStatus: %s\nIn Voice: %s\nGame: %s\nHighest Role: %s\nAccount Created: %s\nJoin Date: %s\nAvatar url:%s```' % (user.id, user.nick, user.status, voice_state, user.activity, role, translate_date(user.created_at.__format__('%A, %d. %B %Y @ %H:%M:%S')), translate_date(user.joined_at.__format__('%A, %d. %B %Y @ %H:%M:%S')), avi)
            else:
                msg = '**User Info:** ```User ID: %s\nAccount Created: %s\nAvatar url:%s```' % (user.id, user.created_at.__format__('%A, %d. %B %Y @ %H:%M:%S'), avi)
            await ctx.send(msg)


    @commands.command(aliases=['pp', 'profile', 'bigprofile', 'ava'])
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
                await ctx.send('Tidak bisa mencari user tersebut')
                return
        else:
            user = ctx.message.author

        avi = user.avatar_url

        try:
            em = discord.Embed(title='Ini dia', timestamp=ctx.message.created_at, color=0x708DD0)
            em.set_image(url=avi)
            await ctx.send(embed=em)
        except discord.errors.HTTPException:
            await ctx.send('Ini dia!\n{}'.format(avi))

    @commands.command(aliases=['be', 'bigemoji'])
    async def bigemote(self, ctx, emoji: discord.Emoji):
        uri = emoji.url
        uri = uri.replace(
            'https://discordapp.com', 'https://cdn.discordapp.com'
        ).replace(
            '/api', ''
        ) + '?v=1'
        await ctx.send(uri)

    @commands.command()
    async def f(self, ctx, *, pesan=None):
        userthatsayF = str(ctx.message.author.name)
        if pesan is None:
            respecctxt = 'telah memberikan respek.'
        else:
            respecctxt = "telah memberikan respek kepada `{}`".format(str(pesan))
        Fpaid=discord.Embed(color=0xe3d957, timestamp=ctx.message.created_at)
        Fpaid.set_thumbnail(url="https://discordapp.com/assets/e99e3416d4825a09c106d7dfe51939cf.svg")
        Fpaid.add_field(name=userthatsayF, value=respecctxt, inline=False)
        await ctx.send(embed=Fpaid)

    @commands.command(aliases=['kerangajaib'])
    async def kerang(self, ctx, *, pertanyaan):
        rand = random.randint(0, 1)
        userasking = str(ctx.message.author)
        useravatar = str(ctx.message.author.avatar_url)
        textasker = 'Ditanyakan oleh: ' + userasking
        pertanyaan = pertanyaan[0].upper() + pertanyaan[1:]
        rel1=discord.Embed(title="Kerang Ajaib", timestamp=ctx.message.created_at, color=0x8ceeff)
        rel1.set_thumbnail(url="https://www.shodor.org/~alexc/pics/MagicConch.png")
        rel1.add_field(name=pertanyaan, value=['Ya', 'Tidak'][rand], inline=False)
        rel1.set_footer(text=textasker, icon_url=useravatar)
        await ctx.send(embed=rel1)

    @commands.command()
    async def pilih(self, ctx, *, input_data):
        server_message = str(ctx.message.guild.id)
        print('Requested !pilih at: ' + server_message)

        inp_d = input_data.split(',')

        if not inp_d:
            return await ctx.send('Tidak ada input untuk dipilih\nGunakan `,` sebagai pemisah.')

        if len(inp_d) < 2:
            return await ctx.send('Hanya ada 1 input untuk dipilih\nGunakan `,` sebagai pemisah.')

        result = random.choice(inp_d)

        await ctx.send('**{user}** aku memilih: **{res}**'.format(user=ctx.message.author.name, res=result.strip()))


    @commands.command(name='8ball')
    async def _8ball(self, ctx, *, input_):
        server_message = str(ctx.message.guild.id)
        print('Requested !8ball at: ' + server_message)

        jawaban_ = {
            "positif": [
                'Pastinya.',
                'Woiyadong.',
                'Takusah ragu.',
                'Tentu saja.',
                'Kalau kau yakin, mungkin saja.',
                'Kalau begitu, iya.',
                'Sudah seharusnya.',
                'Mungkin saja.',
                'Yoi.',
                'Aku sih "yes."'
            ],
            "netral": [
                'Masih belum pasti, coba lagi.',
                'Tanyakan lain waktu, ya.',
                'Nanti akan kuberitahu.',
                'Aku tidak bisa menebaknya sekarang.',
                'Konsentrasi lalu coba lagi.'
            ],
            "negatif": [
                'Jangan harap.',
                'Gak.',
                'Kata bapak tebe, "Gak boleh!"',
                'Tidak mungkin.',
                'Ya enggak lah, pekok!'
            ]
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
        ditanyakan = 'Ditanyakan oleh: ' + ctx.message.author

        pertanyaan = input_[0].upper() + input_[1:]

        color_of_choice = {
            "positif": 0x6ac213,
            "netral": 0xffdc4a,
            "negatif": 0xff4a4a
        }

        ans = discord.Embed(title="Bola delapan (8ball)", timestamp=ctx.message.created_at, color=color_of_choice[pick_dataset])
        ans.set_thumbnail(url="https://www.horoscope.com/images-US/games/game-magic-8-ball-no-text.png")
        ans.add_field(name=pertanyaan, value=answer_of_life, inline=False)
        ans.set_footer(text=ditanyakan, icon_url=avatar)
        await ctx.send(embed=ans)

