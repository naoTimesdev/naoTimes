import logging
import random
from io import BytesIO
from typing import Any, Literal

import aiohttp
import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.i18n import ModuleTranslator
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import cutoff_text

_STATUS_KEYS = {
    "OL": [f"userinfo.status_online_{index}" for index in range(14)],
    "IDLE": [f"userinfo.status_idle_{index}" for index in range(13)],
    "DND": [f"userinfo.status_dnd_{index}" for index in range(24)],
    "OFF": [f"userinfo.status_off_{index}" for index in range(15)],
}


def pick_random_status(mode: Literal["OL", "IDLE", "DND", "OFF"], i18n: ModuleTranslator) -> str:
    status_keys = _STATUS_KEYS.get(mode.upper(), ["userinfo.status_unknown"])
    return i18n.t(random.choice(status_keys))  # nosec


class FunUserInfo(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.UserInfo")

        # Manually bind context menu
        self._user_info_ctx_menu = app_commands.ContextMenu(
            name="Informasi Akun",
            callback=self._fun_user_info_card_app_cmd,
        )
        self._avatar_ctx_menu = app_commands.ContextMenu(name="Avatar", callback=self._fun_user_avatar_app_cmd)
        # Bind cog
        # The bot installs a ContextMenu subclass with a ``cog`` property at
        # startup; discord.py's upstream type does not expose that extension.
        setattr(self._avatar_ctx_menu, "cog", self)
        setattr(self._user_info_ctx_menu, "cog", self)
        self.bot.tree.add_command(self._user_info_ctx_menu)
        self.bot.tree.add_command(self._avatar_ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self._user_info_ctx_menu.name, type=self._user_info_ctx_menu.type)
        self.bot.tree.remove_command(self._avatar_ctx_menu.name, type=self._avatar_ctx_menu.type)

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

    async def _create_image(self, request_data: dict[str, Any]):
        if self.bot.aiosession is None:
            self.logger.error("Cannot create user card without an HTTP session")
            return None
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with self.bot.aiosession.post(
                "https://naotimes-og.glitch.me/_gen/user-card", json=request_data, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    return None
                payload_img = await resp.read()
                return payload_img
        except Exception as e:
            self.logger.error(f"Failed to create image: {e}", exc_info=e)
            return None

    async def _create_embed(self, request_data: dict[str, Any], i18n: ModuleTranslator):
        create_title = request_data["u"] + "#" + request_data["ud"]
        embed = discord.Embed(title=cutoff_text(create_title, 120))
        embed.set_author(name=cutoff_text(create_title, 120), icon_url=request_data["avatar"])
        embed.set_thumbnail(url=request_data["avatar"])
        if "un" in request_data:
            embed.description = i18n.t("userinfo.card_nickname", nickname=request_data["un"])

    async def _generate_user_card_file(self, user_or_member: discord.Member | discord.User, i18n: ModuleTranslator):
        avatar = user_or_member.avatar
        if avatar is None:
            avatar = user_or_member.default_avatar

        # Use WebP to save cost
        avatar_static = avatar.replace(size=1024, format="webp", static_format="webp")

        role_name = None
        role_color = (185, 187, 190)
        if isinstance(user_or_member, discord.Member):
            role_name = user_or_member.top_role.name
            is_default = user_or_member.top_role.color.value == 0
            if not is_default:
                role_color = user_or_member.top_role.color.to_rgb()
            if role_name in ["@everyone", "semuanya"]:
                role_name = "N/A"

        nickname = None
        if isinstance(user_or_member, discord.Member):
            nickname = user_or_member.nick

        status_flavor = i18n.t("userinfo.status_unknown")
        status_code = "off"
        if isinstance(user_or_member, discord.Member) and user_or_member.status:
            if user_or_member.status == discord.Status.online:
                status_flavor = pick_random_status("OL", i18n)
                status_code = "online"
            elif user_or_member.status == discord.Status.idle:
                status_flavor = pick_random_status("IDLE", i18n)
                status_code = "idle"
            elif user_or_member.status == discord.Status.dnd or user_or_member.status == discord.Status.do_not_disturb:
                status_flavor = pick_random_status("DND", i18n)
                status_code = "dnd"
            elif user_or_member.status == discord.Status.offline or user_or_member.status == discord.Status.invisible:
                status_flavor = pick_random_status("OFF", i18n)
                status_code = "off"
        date_token = "dddd[,] DD MMMM YYYY [@] HH[:]mm[:]ss"

        joined_at = None
        if isinstance(user_or_member, discord.Member):
            if user_or_member.joined_at is not None:
                joined_at = arrow.get(user_or_member.joined_at).format(date_token, locale=i18n.language)
        created_at = arrow.get(user_or_member.created_at).format(date_token, locale=i18n.language)

        user_defined_flags = []
        public_flags = user_or_member.public_flags
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
        if isinstance(user_or_member, discord.Member):
            boost_since = user_or_member.premium_since
            if boost_since is not None:
                parsed_premium = arrow.get(boost_since)
                current_time = self.bot.now()
                passed_time = (current_time - parsed_premium).total_seconds()
                user_defined_flags.append(f"boost-{self._determine_nitro_boost_time(int(passed_time))}")

        if user_or_member.bot:
            user_defined_flags.append("bot")
            if public_flags.verified_bot:
                user_defined_flags.append("verified-bot")

        request_data = {
            "u": user_or_member.name,
            "ud": str(user_or_member.discriminator),
            "created": created_at,
            "joined": joined_at,
            "highRole": {"hName": role_name, "hCol": f"rgb{role_color!s}"},
            "status": {
                "sId": status_code,
                "sText": status_flavor,
            },
            "avatar": avatar_static.url,
            "flags": user_defined_flags,
        }
        if nickname is not None:
            request_data["un"] = nickname

        return await self._create_image(request_data)

    async def _fun_user_info_card_app_cmd(
        self, interaction: discord.Interaction, user_or_member: discord.Member | discord.User
    ):
        i18n = self.bot.i18n_for(interaction.guild, "fun")
        ctx = await self.bot.get_context(interaction)
        await ctx.defer()
        if not isinstance(user_or_member, (discord.Member, discord.User)):
            return await ctx.send(i18n.t("userinfo.user_not_found"))

        generated_img = await self._generate_user_card_file(user_or_member, i18n)
        if generated_img is None:
            return await ctx.send(i18n.t("userinfo.image_failed"))

        df_file = discord.File(BytesIO(generated_img), filename=f"UserCard.{user_or_member.id}.png")
        await ctx.send(file=df_file)

    @app_commands.command(
        name="userinfo",
        description=app_commands.locale_str("Lihat kartu informasi seorang user", key="fun.userinfo.description"),
    )
    @app_commands.describe(
        user=app_commands.locale_str("User yang ingin dilihat (default: kamu)", key="fun.userinfo.option_user")
    )
    async def _fun_user_info_card(self, inter: discord.Interaction, user: discord.User | None = None):
        """Lihat kartu informasi seorang user"""
        await self._fun_user_info_card_app_cmd(inter, user or inter.user)

    async def _fun_user_avatar_app_cmd(self, interaction: discord.Interaction, user: discord.User):
        i18n = self.bot.i18n_for(interaction.guild, "fun")
        ctx = await self.bot.get_context(interaction)
        await ctx.defer()
        if not isinstance(user, (discord.User, discord.Member)):
            return await ctx.send(i18n.t("userinfo.user_not_found"))

        avatar = user.avatar
        if avatar is None:
            avatar = user.default_avatar

        try:
            me = discord.Embed(title=i18n.t("avatar.embed_title"), description=f"{avatar.url}", color=0x708DD0)
            me.set_image(url=avatar.url)
            await ctx.send(embed=me)
        except discord.HTTPException:
            await ctx.send(f"{i18n.t('avatar.fallback_title')}\n{avatar.url}")

    @app_commands.command(
        name="avatar",
        description=app_commands.locale_str(
            "Lihat avatar seorang user (termasuk avatar peladen)", key="fun.avatar.description"
        ),
    )
    @app_commands.describe(
        user=app_commands.locale_str("User yang ingin dilihat avatarnya (default: kamu)", key="fun.avatar.option_user")
    )
    async def _fun_user_avatar(self, inter: discord.Interaction, user: discord.User | None = None):
        """Lihat avatar seorang user (termasuk avatar peladen)"""
        ctx = await self.bot.get_context(inter)
        i18n = self.bot.i18n_for(inter.guild, "fun")
        await ctx.defer()
        resolved_user = user or inter.user
        # Resolve the Member in this guild (if any) so guild avatars show up
        if inter.guild is not None and not isinstance(resolved_user, discord.Member):
            try:
                resolved_user = await inter.guild.fetch_member(resolved_user.id)
            except (discord.NotFound, discord.HTTPException):
                pass

        avatar = resolved_user.avatar or resolved_user.default_avatar
        guild_avatar: discord.Asset | None = None
        if isinstance(resolved_user, discord.Member):
            guild_avatar = resolved_user.guild_avatar

        avatars: list[discord.Embed] = []
        me = discord.Embed(
            title=i18n.t("avatar.embed_title"), description=f"{avatar.url}", timestamp=inter.created_at, color=0x708DD0
        )
        if guild_avatar is not None:
            me.description = i18n.t("avatar.description_main", url=avatar.url)
        me.set_image(url=avatar.url)
        avatars.append(me)
        if guild_avatar is not None:
            me_guild = discord.Embed(
                title=i18n.t("avatar.embed_title"),
                description=i18n.t("avatar.description_guild", url=guild_avatar.url),
                color=0x708DD0,
            )
            me_guild.set_image(url=guild_avatar.url)
            avatars.append(me_guild)
        ui_paginate = DiscordPaginatorUI(ctx, avatars, timeout=60)
        try:
            await ui_paginate.interact()
        except discord.HTTPException:
            chunked_data = i18n.t("avatar.fallback_title")
            if guild_avatar is None:
                chunked_data += f"\n{avatar.url}"
            else:
                chunked_data += "\n" + i18n.t("avatar.fallback_main", url=avatar.url)
                chunked_data += "\n" + i18n.t("avatar.fallback_guild", url=guild_avatar.url)
            await ctx.send(chunked_data)


async def setup(bot: naoTimesBot):
    await bot.add_cog(FunUserInfo(bot))
