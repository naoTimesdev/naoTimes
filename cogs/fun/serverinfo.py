import logging
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

    @commands.command(name="serverinfo", aliases=["si"])
    @commands.guild_only()
    async def _fun_server_info(self, ctx: naoTimesContext):
        the_guild: discord.Guild = ctx.guild

        all_channels = the_guild.channels
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
        text_channels = voice_channels = news_channels = stage_channels = []
        for channel in all_channels:
            if channel.type == discord.ChannelType.text:
                text_channels.append(channel)
            elif channel.type == discord.ChannelType.voice:
                voice_channels.append(channel)
            elif channel.type == discord.ChannelType.news:
                news_channels.append(channel)
            elif channel.type == discord.ChannelType.stage_voice:
                stage_channels.append(channel)

        total_channels = len(text_channels) + len(voice_channels) + len(news_channels) + len(stage_channels)

        channels_data = []
        channels_data.append(f"⌨ **{len(text_channels)}** kanal teks")
        channels_data.append(f"🔉 **{len(voice_channels)}** kanal suara")
        if len(news_channels) > 0:
            channels_data.append(f"📰 **{len(news_channels)}** kanal berita")
        if len(stage_channels) > 0:
            channels_data.append(f"📽 **{len(stage_channels)}** kanal panggung")

        verification_level = mfa_levels_map.get(str(the_guild.verification_level))
        mfa_status = "✔" if the_guild.mfa_level == 1 else "❌"
        vc_region = region_map.get(the_guild.region.name, "Otomatis")
        creation_date = arrow.get(the_guild.created_at).format("dddd[,] DD MMMM YYYY [@] HH[:]mm[:]ss")

        server_members = the_guild.members
        bot_accounts = []
        online_users = idle_users = dnd_users = offline_users = invisible_users = []

        for member in server_members:
            if member.bot:
                bot_accounts.append(member)
                continue
            if member.status == discord.Status.online:
                online_users.append(member)
            elif member.status == discord.Status.idle:
                idle_users.append(member)
            elif member.status == discord.Status.dnd:
                dnd_users.append(member)
            elif member.status == discord.Status.offline:
                offline_users.append(member)
            elif member.status == discord.Status.invisible:
                invisible_users.append(member)

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
        embed.set_thumbnail(url=the_guild.icon)
        if "INVITE_SPLASH" in server_features and the_guild.splash:
            embed.set_image(url=the_guild.splash)
        embed.add_field(name=f"Member [{len(server_members)}]", value="\n".join(user_data), inline=False)
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


def setup(bot: naoTimesBot):
    bot.add_cog(FunServerInfo(bot))
