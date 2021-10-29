import logging
import random
from io import BytesIO
from typing import Literal

import arrow
import discord
from discord.ext import commands
from discord.utils import _bytes_to_base64_data

from naotimes.bot import naoTimesBot
from naotimes.card import CardGenerationFailure, UserCard, UserCardHighRole, UserCardStatus
from naotimes.context import naoTimesContext


def pick_random_status(mode: Literal["OL", "IDLE", "DND", "OFF"]) -> str:
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
        "IDLE": [
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
    status = statuses_list.get(mode.upper(), ["Tidak diketahui"])
    return random.choice(status)  # nosec


class FunUserInfo(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.UserInfo")

    def _determine_nitro_boost_time(self, seconds_passed: int) -> str:
        # Assume 30 days
        MONTH = 30 * 24 * 60 * 60
        if seconds_passed < 2 * MONTH:
            return "1m"
        elif seconds_passed < 3 * MONTH:
            return "2m"
        elif seconds_passed < 6 * MONTH:
            return "3m"
        elif seconds_passed < 9 * MONTH:
            return "6m"
        elif seconds_passed < 12 * MONTH:
            return "9m"
        elif seconds_passed < 15 * MONTH:
            return "12m"
        elif seconds_passed < 18 * MONTH:
            return "15m"
        elif seconds_passed < 24 * MONTH:
            return "18m"
        return "24m"

    @commands.command(name="uic", aliases=["ui", "user", "uinfo", "userinfo"])
    async def _fun_user_info_card(self, ctx: naoTimesContext, user: commands.UserConverter = None):
        if user is None:
            user = ctx.author

        if not isinstance(user, (discord.User, discord.Member)):
            return await ctx.send("Tidak bisa menemukan user tersebut")

        avatar_bytes = await user.avatar.read()
        base64_avi = _bytes_to_base64_data(avatar_bytes)

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

        status_flavor = "Tidak diketahui"
        status_code = "off"
        if hasattr(user, "status") and user.status:
            if user.status == discord.Status.online:
                status_flavor = pick_random_status("OL")
                status_code = "online"
            elif user.status == discord.Status.idle:
                status_flavor = pick_random_status("IDLE")
                status_code = "idle"
            elif user.status == discord.Status.dnd or user.status == discord.Status.do_not_disturb:
                status_flavor = pick_random_status("DND")
                status_code = "dnd"
            elif user.status == discord.Status.offline or user.status == discord.Status.invisible:
                status_flavor = pick_random_status("OFF")
                status_code = "off"
        date_token = "dddd[,] DD MMMM YYYY [@] HH[:]mm[:]ss"

        joined_at = None
        if isinstance(user, discord.Member):
            joined_at = arrow.get(user.joined_at).format(date_token)
        created_at = arrow.get(user.created_at).format(date_token)

        user_defined_flags = []
        public_flags = user.public_flags
        if public_flags.staff:
            user_defined_flags.append("staff")
        if public_flags.partner:
            user_defined_flags.append("partner")
        if public_flags.hypesquad:
            user_defined_flags.append("hype-event")
        if public_flags.hypesquad_balance:
            user_defined_flags.append("hype-balance")
        if public_flags.hypesquad_brilliance:
            user_defined_flags.append("hype-brilliance")
        if public_flags.hypesquad_bravery:
            user_defined_flags.append("hype-bravery")
        if public_flags.bug_hunter and not public_flags.bug_hunter_level_2:
            user_defined_flags.append("bug-l1")
        elif public_flags.bug_hunter_level_2:
            user_defined_flags.append("bug-l2")
        if public_flags.verified_bot_developer:
            user_defined_flags.append("verified-dev")
        if public_flags.early_supporter:
            user_defined_flags.append("nitro-early")
        if public_flags.discord_certified_moderator:
            user_defined_flags.append("moderator")
        if isinstance(user, discord.Member):
            boost_since = user.premium_since
            if boost_since is not None:
                parsed_premium = arrow.get(boost_since)
                current_time = self.bot.now()
                passed_time = (current_time - parsed_premium).total_seconds()
                user_defined_flags.append(f"boost-{self._determine_nitro_boost_time(passed_time)}")

        if user.bot:
            user_defined_flags.append("bot")
            if public_flags.verified_bot:
                user_defined_flags.append("verified-bot")

        user_status = UserCardStatus(status_code, status_flavor)
        high_role = UserCardHighRole(role_name, f"rgb{str(role_color)}")
        user_card = UserCard(
            user.name,
            user.discriminator,
            nickname,
            created_at,
            joined_at,
            high_role,
            user_status,
            base64_avi,
            user_defined_flags,
        )

        try:
            generated_img = await self.bot.cardgen.generate("usercard", user_card)
        except CardGenerationFailure:
            return await ctx.send("Gagal membuat gambar untuk User card")

        df_file = discord.File(BytesIO(generated_img), f"UserCard.{user.id}.png")
        await ctx.send(file=df_file)

    @commands.command(name="avatar", aliases=["pp", "profile", "bigprofile", "bp", "ava"])
    async def _fun_user_avatar(self, ctx: naoTimesContext, user: commands.UserConverter = None):
        if user is None:
            user = ctx.author

        if not isinstance(user, (discord.User, discord.Member)):
            return await ctx.send("Tidak bisa menemukan user tersebut")

        avatar = user.avatar

        try:
            em = discord.Embed(
                title="Ini dia", description=f"{avatar.url}", timestamp=ctx.message.created_at, color=0x708DD0
            )
            em.set_image(url=avatar.url)
            await ctx.send(embed=em)
        except discord.HTTPException:
            await ctx.send(f"Ini dia!\n{avatar.url}")


def setup(bot: naoTimesBot):
    bot.add_cog(FunUserInfo(bot))
