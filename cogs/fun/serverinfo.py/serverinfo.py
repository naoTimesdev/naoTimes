import logging
from collections import Counter
from typing import Literal

import arrow
import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.converters import StealedEmote


def humanize_size(num, mul=1024.0, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < mul:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= mul
    return "%.1f%s %s" % (num, "Yi", suffix)


IconLiteral = Literal[
    "mfa_none",
    "mfa_low",
    "mfa_medium",
    "mfa_high",
    "mfa_extreme",
    "boost",
    "s_ol",
    "s_off",
    "s_idle",
    "s_dnd",
]


def fallback_custom_icons(icon_name: IconLiteral, customable: bool) -> str:
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


class FunServerInfo(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.ServerInfo")

    def _count_server_channels(self, server: discord.Guild) -> Counter[str]:
        channels_count = Counter({"text": 0, "vc": 0, "news": 0, "stage": 0})
        for channel in server.channels:
            if channel.type == discord.ChannelType.text:
                channels_count["text"] += 1
            elif channel.type == discord.ChannelType.voice:
                channels_count["vc"] += 1
            elif channel.type == discord.ChannelType.news:
                channels_count["news"] += 1
            elif channel.type == discord.ChannelType.stage_voice:
                channels_count["stage"] += 1
        return channels_count

    def _count_server_members(self, server: discord.Guild) -> Counter[str]:
        users_counter = Counter({"bot": 0, "online": 0, "idle": 0, "dnd": 0, "offline": 0, "invisible": 0})
        for member in server.members:
            if member.bot:
                users_counter["bot"] += 1
                continue
            if member.status == discord.Status.online:
                users_counter["online"] += 1
            elif member.status == discord.Status.idle:
                users_counter["idle"] += 1
            elif member.status == discord.Status.dnd:
                users_counter["dnd"] += 1
            elif member.status == discord.Status.offline:
                users_counter["offline"] += 1
            elif member.status == discord.Status.invisible:
                users_counter["invisible"] += 1
        return users_counter

    @commands.command(name="serverinfo", aliases=["si"])
    @commands.guild_only()
    async def _fun_server_info(self, ctx: naoTimesContext):
        the_guild: discord.Guild = ctx.guild

        bot_member = the_guild.get_member(self.bot.user.id)
        bot_permissions = bot_member.guild_permissions
        real_bot_perms = []
        for perm_name, perm_val in bot_permissions:
            if perm_val:
                real_bot_perms.append(perm_name)

        can_use_custom = False
        emote_guild = self.bot.get_guild(761916689113284638)
        if "external_emojis" in real_bot_perms and emote_guild is not None:
            can_use_custom = True

        mfa_levels_map = {
            "none": f"{fallback_custom_icons('mfa_none', can_use_custom)} Tidak ada",
            "low": f"{fallback_custom_icons('mfa_low', can_use_custom)} Rendah (Surel harus terverifikasi)",
            "medium": f"{fallback_custom_icons('mfa_medium', can_use_custom)} Menengah (Terdaftar di Discord selama 5 menit)",  # noqa: E501
            "high": f"{fallback_custom_icons('mfa_high', can_use_custom)} Tinggi (Berada di peladen ini selama 10 menit)",  # noqa: E501
            "extreme": f"{fallback_custom_icons('mfa_extreme', can_use_custom)} Tertinggi (Nomor telepon harus terverifikasi)",  # noqa: E501
        }
        # text_channels = voice_channels = news_channels = stage_channels = []
        channels_count = await self.bot.loop.run_in_executor(None, self._count_server_channels, the_guild)

        # total_channels = len(text_channels) + len(voice_channels) + len(news_channels) + len(stage_channels)
        total_channels = (
            channels_count["text"] + channels_count["vc"] + channels_count["news"] + channels_count["stage"]
        )

        channels_data = []
        channels_data.append(f"⌨ **{channels_count['text']}** kanal teks")
        channels_data.append(f"🔉 **{channels_count['vc']}** kanal suara")
        if channels_count["news"] > 0:
            channels_data.append(f"📰 **{channels_count['news']}** kanal berita")
        if channels_count["stage"] > 0:
            channels_data.append(f"📽 **{channels_count['stage']}** kanal panggung")

        verification_level = mfa_levels_map.get(str(the_guild.verification_level))
        mfa_status = "✔" if the_guild.mfa_level == 1 else "❌"
        # vc_region = region_map.get(the_guild.region.name, "Otomatis")
        creation_date = arrow.get(the_guild.created_at).format("dddd[,] DD MMMM YYYY [@] HH[:]mm[:]ss")

        users_counter = await self.bot.loop.run_in_executor(None, self._count_server_members, the_guild)

        server_features = the_guild.features
        server_type = "Peladen Pribadi"
        if "PUBLIC" in server_features or "DISCOVERABLE" in server_features:
            server_type = "Peladen Publik"
        if "COMMUNITY" in server_features:
            server_type = server_type.replace("Peladen", "Komunitas")
        if "VERIFIED" in server_features:
            server_type = f"✅ {server_type} **[Terverifikasi]**"
        if "PARTNERED" in server_features:
            server_type += " **[Berpartner]**"
            server_type = f"🤝 {server_type}"

        extra_infos_data = []
        boost_count = the_guild.premium_subscription_count
        if boost_count > 0:
            boost_lvl = the_guild.premium_tier
            text_data = fallback_custom_icons("boost", can_use_custom) + f" Level **{boost_lvl}**"
            text_data += f" (**{boost_count}** boosts)"
            extra_infos_data.append(text_data)

        server_bits_and_guts = []
        file_limit = humanize_size(the_guild.filesize_limit)
        bitrate_limit = humanize_size(the_guild.bitrate_limit, 1000.0)
        server_bits_and_guts.append(f"☺ **{the_guild.emoji_limit}** emojis limit")
        server_bits_and_guts.append(f"🎞 **{file_limit}** file limit")
        server_bits_and_guts.append(f"🎵 **{bitrate_limit}** bitrate limit")

        extra_infos_data.append(" | ".join(server_bits_and_guts))

        all_invites = []
        try:
            invite_url = await the_guild.invites()
            for invite in invite_url:
                if invite.max_uses is not None and invite.max_age is not None:
                    all_invites.append(f"👉 Invite: {invite.url}")
                    break
            if "VANITY_URL" in server_features:
                vanity_invite = await the_guild.vanity_invite()
                if vanity_invite is not None:
                    all_invites.append(f"✨ Vanity Invite: {vanity_invite.url}")
        except discord.Forbidden:
            pass

        embed = discord.Embed(colour=0xF7E43)
        embed.set_author(name=the_guild.name, icon_url=the_guild.icon)
        description = []
        description.append(server_type)
        description.append(f"👑 **Penguasa**: {self.bot.is_mentionable(ctx, the_guild.owner)}")
        description.append(f"📅 **Dibuat**: {creation_date}")
        # description.append(vc_region)
        user_data = []
        user_data.append(
            f"{fallback_custom_icons('s_ol', can_use_custom)} **{users_counter['online']}** Daring | "
            f"{fallback_custom_icons('s_off', can_use_custom)} **{users_counter['offline']}** Luring"
        )
        user_data.append(
            f"{fallback_custom_icons('s_idle', can_use_custom)} **{users_counter['idle']}** Idle | "
            f"{fallback_custom_icons('s_dnd', can_use_custom)} **{users_counter['dnd']}** DnD"
        )
        user_data.append(f"🤖 **{users_counter['bot']}** Bot")
        embed.description = "\n".join(description)
        if the_guild.icon is not None:
            embed.set_thumbnail(url=the_guild.icon)
        if "INVITE_SPLASH" in server_features and the_guild.splash:
            embed.set_image(url=the_guild.splash)
        embed.add_field(name=f"Member [{the_guild.member_count}]", value="\n".join(user_data), inline=False)
        embed.add_field(name=f"Kanal [{total_channels}]", value="\n".join(channels_data), inline=False)
        embed.add_field(
            name="Level Verifikasi",
            value=f"{verification_level}\n**2FA** Enabled? {mfa_status}",
            inline=False,
        )
        if all_invites:
            embed.add_field(name="Invite Link", value="\n".join(all_invites), inline=False)
        if extra_infos_data:
            embed.add_field(name="Info Ekstra", value="\n".join(extra_infos_data), inline=False)
        footer_part = f"💻 ID: {the_guild.id}"
        if the_guild.shard_id is not None:
            footer_part += f" | 🔮 Shard: {the_guild.shard_id}"
        embed.set_footer(text=footer_part)
        await ctx.send(embed=embed)

    @commands.command(name="bigemote", aliases=["be", "bigemoji"])
    async def _fun_server_bigemote(self, ctx: naoTimesContext, emoji: StealedEmote):
        fmt_msg = f"`:{emoji.name}:`\n{emoji.url}"
        await ctx.send(fmt_msg)

    @_fun_server_bigemote.error
    async def _fun_server_bigemote_error(self, ctx: naoTimesContext, error: Exception):
        if isinstance(error, commands.ConversionError):
            return await ctx.send("Gagal mendapatkan emote yang dimaksud.")


async def setup(bot: naoTimesBot):
    await bot.add_cog(FunServerInfo(bot))
