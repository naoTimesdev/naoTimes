import logging
from collections import Counter
from typing import Literal

import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
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
        channels_count = Counter({"text": 0, "vc": 0, "news": 0, "stage": 0, "thread": 0, "forum": 0})
        for channel in server.channels:
            if channel.type == discord.ChannelType.text:
                channels_count["text"] += 1
            elif channel.type == discord.ChannelType.voice:
                channels_count["vc"] += 1
            elif channel.type == discord.ChannelType.news:
                channels_count["news"] += 1
            elif channel.type == discord.ChannelType.stage_voice:
                channels_count["stage"] += 1
            elif channel.type in (
                discord.ChannelType.public_thread,
                discord.ChannelType.private_thread,
                discord.ChannelType.news_thread,
            ):
                channels_count["thread"] += 1
            elif channel.type == discord.ChannelType.forum:
                channels_count["forum"] += 1
        return channels_count

    @app_commands.command(
        name="serverinfo",
        description=app_commands.locale_str("Lihat informasi peladen ini", key="fun.serverinfo.description"),
    )
    @app_commands.guild_only()
    async def _fun_server_info(self, inter: discord.Interaction):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        the_guild = inter.guild
        if the_guild is None:
            return await inter.response.send_message(i18n.t("serverinfo.guild_only"), ephemeral=True)
        await inter.response.defer()

        bot_permissions = the_guild.me.guild_permissions
        real_bot_perms = []
        for perm_name, perm_val in bot_permissions:
            if perm_val:
                real_bot_perms.append(perm_name)

        can_use_custom = False
        emote_guild = self.bot.get_guild(761916689113284638)
        if "external_emojis" in real_bot_perms and emote_guild is not None:
            can_use_custom = True

        mfa_levels_map = {
            "none": f"{fallback_custom_icons('mfa_none', can_use_custom)} {i18n.t('serverinfo.mfa_none')}",
            "low": f"{fallback_custom_icons('mfa_low', can_use_custom)} {i18n.t('serverinfo.mfa_low')}",
            "medium": f"{fallback_custom_icons('mfa_medium', can_use_custom)} {i18n.t('serverinfo.mfa_medium')}",
            "high": f"{fallback_custom_icons('mfa_high', can_use_custom)} {i18n.t('serverinfo.mfa_high')}",
            "extreme": f"{fallback_custom_icons('mfa_extreme', can_use_custom)} {i18n.t('serverinfo.mfa_extreme')}",
        }
        # text_channels = voice_channels = news_channels = stage_channels = []
        channels_count = await self.bot.loop.run_in_executor(None, self._count_server_channels, the_guild)

        # total_channels = len(text_channels) + len(voice_channels) + len(news_channels) + len(stage_channels)
        total_channels = (
            channels_count["text"] + channels_count["vc"] + channels_count["news"] + channels_count["stage"]
        )

        channels_data = []
        channels_data.append(i18n.t("serverinfo.channel_text", count=channels_count["text"]))
        channels_data.append(i18n.t("serverinfo.channel_voice", count=channels_count["vc"]))
        if channels_count["news"] > 0:
            channels_data.append(i18n.t("serverinfo.channel_news", count=channels_count["news"]))
        if channels_count["stage"] > 0:
            channels_data.append(i18n.t("serverinfo.channel_stage", count=channels_count["stage"]))
        if channels_count["thread"] > 0:
            channels_data.append(i18n.t("serverinfo.channel_thread", count=channels_count["thread"]))
        if channels_count["forum"] > 0:
            channels_data.append(i18n.t("serverinfo.channel_forum", count=channels_count["forum"]))

        verification_level = mfa_levels_map.get(str(the_guild.verification_level))
        mfa_status = "✔" if the_guild.mfa_level == 1 else "❌"
        # vc_region = region_map.get(the_guild.region.name, "Otomatis")
        creation_date = arrow.get(the_guild.created_at).format(
            "dddd[,] DD MMMM YYYY [@] HH[:]mm[:]ss", locale=i18n.language
        )

        server_features = the_guild.features
        is_public = "PUBLIC" in server_features or "DISCOVERABLE" in server_features
        if "COMMUNITY" in server_features:
            if is_public:
                server_type = i18n.t("serverinfo.type_community_public")
            else:
                server_type = i18n.t("serverinfo.type_community_private")
        elif is_public:
            server_type = i18n.t("serverinfo.type_public")
        else:
            server_type = i18n.t("serverinfo.type_private")
        if "VERIFIED" in server_features:
            server_type = i18n.t("serverinfo.type_verified", name=server_type)
        if "PARTNERED" in server_features:
            server_type = i18n.t("serverinfo.type_partnered", name=server_type)

        extra_infos_data = []
        boost_count = the_guild.premium_subscription_count
        if boost_count > 0:
            boost_lvl = the_guild.premium_tier
            text_data = fallback_custom_icons("boost", can_use_custom) + i18n.t(
                "serverinfo.boost_level", level=boost_lvl
            )
            text_data += i18n.t("serverinfo.boost_count", count=boost_count)
            extra_infos_data.append(text_data)

        server_bits_and_guts = []
        file_limit = humanize_size(the_guild.filesize_limit)
        bitrate_limit = humanize_size(the_guild.bitrate_limit, 1000.0)
        server_bits_and_guts.append(i18n.t("serverinfo.bits_emoji", count=the_guild.emoji_limit))
        server_bits_and_guts.append(i18n.t("serverinfo.bits_file", size=file_limit))
        server_bits_and_guts.append(i18n.t("serverinfo.bits_bitrate", size=bitrate_limit))

        extra_infos_data.append(" | ".join(server_bits_and_guts))

        all_invites = []
        try:
            invite_url = await the_guild.invites()
            for invite in invite_url:
                if invite.max_uses is not None and invite.max_age is not None:
                    all_invites.append(i18n.t("serverinfo.invite_normal", url=invite.url))
                    break
            if "VANITY_URL" in server_features:
                vanity_invite = await the_guild.vanity_invite()
                if vanity_invite is not None:
                    all_invites.append(i18n.t("serverinfo.invite_vanity", url=vanity_invite.url))
        except discord.Forbidden:
            pass

        embed = discord.Embed(colour=0xF7E43)
        embed.set_author(name=the_guild.name, icon_url=the_guild.icon)
        description = []
        description.append(server_type)
        description.append(i18n.t("serverinfo.embed_owner", owner_id=the_guild.owner_id))
        description.append(i18n.t("serverinfo.embed_created", date=creation_date))
        # description.append(vc_region)
        embed.description = "\n".join(description)
        if the_guild.icon is not None:
            embed.set_thumbnail(url=the_guild.icon)
        if "INVITE_SPLASH" in server_features and the_guild.splash:
            embed.set_image(url=the_guild.splash)
        embed.add_field(
            name=i18n.t("serverinfo.embed_members_name", count=the_guild.member_count),
            value=i18n.t("serverinfo.embed_members_value", count=the_guild.member_count),
            inline=False,
        )
        embed.add_field(
            name=i18n.t("serverinfo.embed_channels_name", count=total_channels),
            value="\n".join(channels_data),
            inline=False,
        )
        embed.add_field(
            name=i18n.t("serverinfo.embed_verification_name"),
            value=i18n.t("serverinfo.embed_verification_value", level=verification_level, status=mfa_status),
            inline=False,
        )
        if all_invites:
            embed.add_field(name=i18n.t("serverinfo.embed_invite_link"), value="\n".join(all_invites), inline=False)
        if extra_infos_data:
            embed.add_field(name=i18n.t("serverinfo.embed_extra"), value="\n".join(extra_infos_data), inline=False)
        footer_part = i18n.t("serverinfo.embed_footer", id=the_guild.id)
        if the_guild.shard_id is not None:
            footer_part += i18n.t(
                "serverinfo.embed_footer_shard", shard=the_guild.shard_id, total=self.bot.shard_count or 1
            )
        embed.set_footer(text=footer_part)
        await inter.followup.send(embed=embed)

    @app_commands.command(
        name="bigemote",
        description=app_commands.locale_str("Perbesar emote kustom", key="fun.serverinfo.bigemote_description"),
    )
    @app_commands.describe(
        emote=app_commands.locale_str("Emote kustom yang ingin diperbesar", key="fun.serverinfo.bigemote_option_emote")
    )
    async def _fun_server_bigemote(self, inter: discord.Interaction, emote: str):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        try:
            emoji = await StealedEmote().convert(await self.bot.get_context(inter), emote)
        except commands.CommandError:
            return await inter.response.send_message(i18n.t("serverinfo.bigemote_failed"), ephemeral=True)
        await inter.response.send_message(f"`:{emoji.name}:`\n{emoji.url}")


async def setup(bot: naoTimesBot):
    await bot.add_cog(FunServerInfo(bot))
