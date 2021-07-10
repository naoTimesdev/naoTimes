import io
import logging
import random
import re
from datetime import datetime
from typing import List, Union

import discord
from discord.utils import _bytes_to_base64_data
import numpy as np
from discord.ext import commands

from nthelper.bot import naoTimesBot
from nthelper.usercard import UserCard, UserCardGenerationFailure, UserCardHighRole, UserCardStatus
from nthelper.utils import StealedEmote

logger = logging.getLogger("cogs.fun")


def setup(bot):
    logger.debug("adding cogs...")
    bot.add_cog(Fun(bot))


def fallback_custom_icons(icon_name: str, customable: bool) -> str:
    icon_name_maps = {
        "mfa_none": "<:ntMFAL0:761931842923266050>",
        "mfa_low": "<:ntMFAL1:761931852788924418>",
        "mfa_medium": "<:ntMFAL2:761931862695870475>",
        "mfa_high": "<:ntMFAL3:761931871708905483>",
        "mfa_extreme": "<:ntMFAL4:761931880949219388>",
        "boost": "<:ntIconBoost:761958456865062923>",
        "s_ol": "<:ntStatL3:761945479511670794>",
        "s_off": "<:ntStatL0:761945452987285545>",
        "s_idle": "<:ntStatL2:761945472432209940>",
        "s_dnd": "<:ntStatL1:761945462424338493>",
    }
    fallback_name_maps = {
        "mfa_none": "0️⃣",
        "mfa_low": "1️⃣",
        "mfa_medium": "2️⃣",
        "mfa_high": "3️⃣",
        "mfa_extreme": "4️⃣",
        "boost": "🚀",
        "s_ol": "🟢",
        "s_off": "⚫",
        "s_idle": "🟡",
        "s_dnd": "🔴",
    }
    if customable:
        return icon_name_maps.get(icon_name, "")
    return fallback_name_maps.get(icon_name, "")


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
            "Rapat DPR",
            "Sedang merencanakan UU baru",
            "Dangdutan bareng polisi",
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
    return random.choice(status)  # nosec


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

    def __init__(self, bot: naoTimesBot):
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
            randd = random.uniform(0.5, 1.5)  # nosec

            if randd <= 0.9:
                ava = msg.author.avatar_url
                user_name = "{0.name}#{0.discriminator}".format(msg.author)
            else:
                guild_members = msg.guild.members
                guild_members = [member for member in guild_members if not member.bot]
                usr = random.choice(guild_members)  # nosec

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

    @commands.command(name="uic", aliases=["ui", "user", "uinfo", "userinfo"])
    async def user_card_nicer(self, ctx: commands.Context, *, name=""):
        if name:
            try:
                if name.isdigit():
                    user: discord.User = ctx.message.guild.get_member(int(name))
                else:
                    user: discord.User = ctx.message.mentions[0]
            except IndexError:
                user: discord.User = ctx.guild.get_member_named(name)
            if not user:
                user: discord.User = ctx.guild.get_member_named(name)
            if not user:
                return await ctx.send("Tidak bisa mencari user tersebut")
        else:
            user: discord.User = ctx.message.author

        avi_bytes = await user.avatar_url.read()
        base64_avi = _bytes_to_base64_data(avi_bytes)

        role_name = None
        role_color = (185, 187, 190)
        if isinstance(user, discord.Member):
            role_name = user.top_role.name
            is_default = user.top_role.color.value == 0
            if not is_default:
                role_color = user.top_role.color.to_rgb()
            if role_name in ["@everyone", "semuanya"]:
                role_name = "N/A"

        nickname = None
        if hasattr(user, "nick") and user.nick:
            nickname = user.nick

        real_status = "off"
        status_flavor = "Tidak diketahui"
        if hasattr(user, "status") and user.status:
            real_status = str(user.status).lower()
            if "online" in real_status:
                status_flavor = get_user_status("OL")
            elif "idle" in real_status:
                status_flavor = get_user_status("IDL")
            elif "dnd" in real_status:
                status_flavor = get_user_status("DND")
            elif "offline" in real_status:
                status_flavor = get_user_status("OFF")
                real_status = "off"

        joined_at = None
        if isinstance(user, discord.Member):
            joined_at = translate_date(user.joined_at.__format__("%A, %d %B %Y @ %H:%M:%S"))
        created_at = translate_date(user.created_at.__format__("%A, %d %B %Y @ %H:%M:%S"))

        all_flags = []
        pub_flags: discord.flags.PublicUserFlags = user.public_flags
        if pub_flags.staff:
            all_flags.append("staff")
        if pub_flags.partner:
            all_flags.append("partner")
        if pub_flags.hypesquad:
            all_flags.append("hype-event")
        if pub_flags.hypesquad_balance:
            all_flags.append("hype-balance")
        if pub_flags.hypesquad_bravery:
            all_flags.append("hype-bravery")
        if pub_flags.hypesquad_brilliance:
            all_flags.append("hype-briliance")
        if pub_flags.bug_hunter and not pub_flags.bug_hunter_level_2:
            all_flags.append("bug-l1")
        elif pub_flags.bug_hunter and pub_flags.bug_hunter_level_2:
            all_flags.append("bug-l2")
        elif pub_flags.bug_hunter_level_2:
            all_flags.append("bug-l2")
        if pub_flags.verified_bot_developer:
            all_flags.append("verified-dev")
        if pub_flags.early_supporter:
            all_flags.append("nitro-early")

        if user.bot:
            all_flags.append("bot")
            if pub_flags.verified_bot:
                all_flags.append("verified-bot")

        user_status = UserCardStatus(real_status, status_flavor)
        highest_role = UserCardHighRole(role_name, f"rgb{str(role_color)}")
        user_card = UserCard(
            user.name,
            user.discriminator,
            nickname,
            created_at,
            joined_at,
            highest_role,
            user_status,
            base64_avi,
            all_flags,
        )

        try:
            generated_img = await self.bot.usercard.generate(user_card)
        except UserCardGenerationFailure:
            return await ctx.send("Gagal membuat gambar untuk User card")

        df_file = discord.File(io.BytesIO(generated_img), f"UserCard.{user.id}.png")
        await ctx.send(file=df_file)

    @commands.command(aliases=["si"])
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        guilds_data: discord.Guild = ctx.message.guild
        channels_data: List[
            Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]
        ] = guilds_data.channels
        bot_member: discord.Member = guilds_data.get_member(self.bot.user.id)
        bot_perms: discord.Permissions = bot_member.permissions_in(ctx.message.channel)
        real_bot_perms = []
        for perm_name, perm_val in bot_perms:
            if perm_val:
                real_bot_perms.append(perm_name)
        can_use_custom = False
        emote_guild = self.bot.get_guild(761916689113284638)
        if "external_emojis" in real_bot_perms and emote_guild is not None:
            can_use_custom = True

        def _humanize_size(num, mul=1024.0, suffix="B"):
            for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
                if abs(num) < mul:
                    return "%3.1f%s%s" % (num, unit, suffix)
                num /= mul
            return "%.1f%s %s" % (num, "Yi", suffix)

        def _localize_time(dt_time: datetime) -> str:
            month_en = dt_time.strftime("%B")
            tl_map = {
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
            month_id = tl_map.get(month_en, month_en)
            final_data = dt_time.strftime("%d ") + month_id
            final_data += dt_time.strftime(" %Y, %H:%M:%S UTC")
            return final_data

        mfa_levels_map = {
            "none": f"{fallback_custom_icons('mfa_none', can_use_custom)} Tidak ada",
            "low": f"{fallback_custom_icons('mfa_low', can_use_custom)} Rendah (Surel harus terverifikasi)",
            "medium": f"{fallback_custom_icons('mfa_medium', can_use_custom)} Menengah (Terdaftar di Discord selama 5 menit)",  # noqa: E501
            "high": f"{fallback_custom_icons('mfa_high', can_use_custom)} Tinggi (Berada di peladen ini selama 10 menit)",  # noqa: E501
            "extreme": f"{fallback_custom_icons('mfa_extreme', can_use_custom)} Tertinggi (Nomor telepon harus terverifikasi)",  # noqa: E501
        }
        region_map = {
            "amsterdam": "🇳🇱 Amsterdam",
            "brazil": "🇧🇷 Brasil",
            "dubai": "🇪🇬 Dubai",
            "europe": "🇪🇺 Eropa",
            "eu_central": "🇪🇺 Eropa Tengah",
            "eu_west": "🇪🇺 Eropa Barat",
            "frankfurt": "🇩🇪 Frankfurt",
            "hongkong": "🇭🇰 Hong Kong",
            "india": "🇮🇳 India",
            "japan": "🇯🇵 Jepang",
            "london": "🇬🇧 London",
            "russia": "🇷🇺 Rusia",
            "singapore": "🇸🇬 Singapura",
            "southafrica": "🇿🇦 Afrika Selatan",
            "south_korea": "🇰🇷 Korea Selatan",
            "sydney": "🇦🇺 Sidney",
            "us_central": "🇺🇸 Amerika Tengah",
            "us_east": "🇺🇸 Amerika Timur",
            "us_south": "🇺🇸 Amerika Selatan",
            "us_west": "🇺🇸 Amerika Barat",
            "vip_amsterdam": "🇳🇱 Amsterdam (💳 VIP)",
            "vip_us_east": "🇺🇸 Amerika Timur (💳 VIP)",
            "vip_us_west": "🇺🇸 Amerika Barat (💳 VIP)",
        }

        text_channels = []
        voice_channels = []
        news_channels = []
        stage_channels = []
        for channel in channels_data:
            ctype = str(channel.type)
            if ctype == "voice":
                voice_channels.append(channel)
            elif ctype == "text":
                text_channels.append(channel)
            elif ctype == "news":
                news_channels.append(channel)
            elif ctype == "stage_voice":
                stage_channels.append(channel)

        total_channels = len(text_channels) + len(voice_channels) + len(news_channels) + len(stage_channels)

        channels_data = []
        channels_data.append(f"⌨ **{len(text_channels)}** kanal teks")
        channels_data.append(f"🔉 **{len(voice_channels)}** kanal suara")
        if len(news_channels) > 0:
            channels_data.append(f"📰 **{len(news_channels)}** kanal berita")
        if len(stage_channels) > 0:
            channels_data.append(f"📽 **{len(stage_channels)}** kanal panggung")

        verification_lvl = mfa_levels_map.get(str(guilds_data.verification_level))
        twofa_status = "✔" if guilds_data.mfa_level == 1 else "❌"
        vc_region = region_map.get(str(guilds_data.region))
        created_time = _localize_time(guilds_data.created_at)

        server_members: List[discord.Member] = guilds_data.members
        bot_accounts = []
        online_users = []
        idle_users = []
        dnd_users = []
        offline_users = []
        invisible_users = []
        for member in server_members:
            if member.bot:
                bot_accounts.append(member)
                continue
            status = str(member.status)
            if status == "online":
                online_users.append(member)
            elif status == "idle":
                idle_users.append(member)
            elif status == "dnd":
                dnd_users.append(member)
            elif status == "offline":
                offline_users.append(member)
            elif status == "invisible":
                invisible_users.append(member)

        server_features = guilds_data.features
        server_type = "Peladen Pribadi"
        if "PUBLIC" in server_features:
            server_type = "Peladen Publik"
        if "COMMUNITY" in server_features:
            server_type = server_type.replace("Peladen", "Komunitas")
        if "VERIFIED" in server_features:
            server_type = "✅ " + server_type + " **[Terverifikasi]**"
        if "PARTNERED" in server_features:
            server_type = "🤝 " + server_type + " **[Berpartner]**"
        extras_info_datas = []
        boost_count = guilds_data.premium_subscription_count
        if boost_count > 0:
            boost_lvl = guilds_data.premium_tier
            extras_info_datas.append(
                f"{fallback_custom_icons('boost', can_use_custom)} Level **{boost_lvl}** (**{boost_count}** boosts)"  # noqa: E501
            )
        extras_info_datas.append(
            "☺ **{}** emojis limit | 🎞 **{}** file limit | 🎵 **{}** bitrate limit".format(
                guilds_data.emoji_limit,
                _humanize_size(guilds_data.filesize_limit),
                _humanize_size(guilds_data.bitrate_limit, 1000.0),
            )
        )

        embed = discord.Embed(colour=0xF7E43)
        embed.set_author(name=guilds_data.name, icon_url=guilds_data.icon_url)
        description = []
        description.append(server_type)
        description.append(f"👑 **Penguasa**: {self.bot.is_mentionable(ctx, guilds_data.owner)}")
        description.append(f"📅 **Dibuat**: {created_time}")
        description.append(vc_region)
        user_data = []
        user_data.append(
            f"{fallback_custom_icons('s_ol', can_use_custom)} **{len(online_users)}** Daring | "
            f"{fallback_custom_icons('s_off', can_use_custom)} **{len(offline_users)}** Luring"
        )
        user_data.append(
            f"{fallback_custom_icons('s_idle', can_use_custom)} **{len(idle_users)}** Idle | "
            f"{fallback_custom_icons('s_dnd', can_use_custom)} **{len(dnd_users)}** DnD"
        )
        user_data.append(f"🤖 **{len(bot_accounts)}** Bot")
        embed.description = "\n".join(description)
        embed.set_thumbnail(url=guilds_data.icon_url)
        if "INVITE_SPLASH" in server_features and guilds_data.splash:
            embed.set_image(url=guilds_data.splash_url)
        embed.add_field(name=f"Member [{len(server_members)}]", value="\n".join(user_data), inline=False)
        embed.add_field(name=f"Kanal [{total_channels}]", value="\n".join(channels_data), inline=False)
        embed.add_field(
            name="Level Verifikasi",
            value=f"{verification_lvl}\n**2FA** Enabled? {twofa_status}",
            inline=False,
        )
        if extras_info_datas:
            embed.add_field(name="Info Ekstra", value="\n".join(extras_info_datas))
        footer_part = f"💻 ID: {guilds_data.id}"
        if guilds_data.shard_id is not None:
            footer_part += f" | 🔮 Shard: {guilds_data.shard_id}"
        embed.set_footer(text=footer_part)
        await ctx.send(embed=embed)

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
            if not user and name.isdigit():
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
    async def bigemote(self, ctx, emoji: StealedEmote):
        fmt_msg = f"`:{emoji.name}:`\n{emoji.url}"
        await ctx.send(fmt_msg)

    @bigemote.error
    async def bigemote_error(self, ctx, error):
        if isinstance(error, commands.ConversionError):
            return await ctx.send("Gagal mendapatkan emote yang dimaksud.")

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
        rand = random.randint(0, 1)  # nosec
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
        length = random.randint(2, 12)  # nosec

        txt = "Panjang kntl **{}** adalah:\n".format(ctx.message.author.name)

        multiplier = random.choice([1, 2, 5])  # nosec
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
            total_output.append(random.choice(dice_faces_range))  # nosec

        total_output_txt = [f"**{do}**" for do in total_output]

        output_text = f"Hasil kocok dadu (**{dice_type}**): "
        output_text += " + ".join(total_output_txt)
        if len(total_output) > 1:
            output_text += f" = **{sum(total_output)}**"
        await ctx.send(output_text)

    @commands.command(name="kocok", aliases=["roll"])
    async def roll_dice_ranged(self, ctx, max_num: int):
        dice_faces_range = list(range(1, max_num + 1))
        roll_outcome = random.choice(dice_faces_range)  # nosec

        await ctx.send(f"Hasil kocok dadu: **{roll_outcome}** (**1**-**{max_num}**)")

    @commands.command(name="8ball")
    async def _8ball(self, ctx, *, input_):
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

        for _ in range(random.randint(3, 10)):  # nosec
            random.shuffle(randomized_dataset)

        pick_dataset = randomized_dataset[random.randint(0, 9)]  # nosec

        answer_of_life = random.choice(jawaban_[pick_dataset])  # nosec

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

    @commands.command()
    async def agama(self, ctx, *, hal=""):
        if not hal:
            hal = f"**{ctx.message.author.name}**"
        else:
            hal = f"**{hal}**"

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

        text_to_send = f"Agama {hal} itu apa?\n"
        text_to_send += f"{random.choice(pilihan_agama)}."
        await ctx.send(text_to_send)
