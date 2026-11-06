import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import discord
import magic
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import owner_only
from naotimes.converters import StealedEmote


@dataclass
class EmoteServer:
    id: int  # Channel
    static: int  # Static message
    animated: int  # Animated message


class PrivateEmoteServer(commands.Cog):
    _GUILDS_MAP: ClassVar[dict[str, EmoteServer]] = {
        # N4O Emote Hideout
        "706767672116772874": EmoteServer(706767672116772877, 766679407053373440, 766679457015660544),
        # N4O Twitchery Emote Hideout
        "844175809463320576": EmoteServer(844175809463320579, 844178559782486027, 844178597819449374),
    }

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Private.EmoteServer")

    def _generate_emoji_sets(self, emoji_list: Sequence[discord.Emoji]):
        static_emotes = []
        animated_emotes = []
        for emote in emoji_list:
            if emote.animated:
                animated_emotes.append(f"<a:{emote.name}:{emote.id}>")
            else:
                static_emotes.append(f"<:{emote.name}:{emote.id}>")
        return " ".join(static_emotes), " ".join(animated_emotes)

    @commands.Cog.listener("on_guild_emojis_update")
    async def _pp_update_emote_server(
        self, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]
    ):
        mapping = self._GUILDS_MAP.get(str(guild.id))
        if mapping is None:
            return
        self.logger.info(f"{guild.id}: editing emote message...")
        chatter = guild.get_channel(mapping.id)
        if not isinstance(chatter, (discord.TextChannel, discord.Thread)):
            # For some reason, the channel is deleted?
            return

        static_chat = chatter.get_partial_message(mapping.static)
        animated_chat = chatter.get_partial_message(mapping.animated)

        static_emojis, animated_emojis = self._generate_emoji_sets(after)
        if not static_emojis:
            static_emojis = "*No static emote*"
        if not animated_emojis:
            animated_emojis = "*No animated emote*"

        await static_chat.edit(content=static_emojis)
        await animated_chat.edit(content=animated_emojis)

    def __propagate_emote(self, emojis: Sequence[discord.Emoji]):
        count_static = 0
        count_animated = 0
        emote_sets = []
        for emote in emojis:
            if emote.animated:
                count_animated += 1
            else:
                count_static += 1
            emote_sets.append(emote.name)
        return count_static, count_animated, emote_sets

    def _limit_error(self, animated: bool, limit: int) -> str:
        kind = "animated" if animated else "static"
        return f"Sorry, the server already reach {limit} {kind} emoji limit.\nPlease contact @noaione"

    @app_commands.command(name="nemote")
    @owner_only()
    @app_commands.guild_only()
    @app_commands.describe(gambar="Gambar emote (PNG, JPG, GIF, maksimal 256kb)", nama="Nama emote")
    async def _ppemote_nemote(self, inter: discord.Interaction, gambar: discord.Attachment, nama: str | None = None):
        """Tambah emote baru ke peladen emote"""
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(
                "Perintah ini hanya dapat digunakan di dalam server.", ephemeral=True
            )
        if str(guild.id) not in self._GUILDS_MAP:
            return await inter.response.send_message("Peladen ini bukan peladen emote.", ephemeral=True)

        CURRENT_STATIC, CURRENT_ANIMATED, EMOTE_SETS = self.__propagate_emote(guild.emojis)
        MAX_EMOTE = guild.emoji_limit

        if gambar.size >= 262140:
            return await inter.response.send_message("Image must be under 256kb.", ephemeral=True)

        await inter.response.defer(ephemeral=True)
        image_bytes = await gambar.read()
        file_path = Path(gambar.filename)
        filename, extension = file_path.stem, file_path.suffix
        mime_res = magic.Magic(mime=True).from_buffer(image_bytes)
        if extension.lower().lstrip(".") not in ("jpg", "jpeg", "png", "gif") and mime_res not in (
            "image/gif",
            "image/png",
            "image/jpg",
            "image/jpeg",
        ):
            return await inter.followup.send("Not a valid image (Must be PNG, JPG, or GIF).")

        animated = mime_res == "image/gif"
        if (CURRENT_ANIMATED if animated else CURRENT_STATIC) >= MAX_EMOTE:
            return await inter.followup.send(self._limit_error(animated, MAX_EMOTE))

        emote_name = nama or filename
        emote_idx = 1
        base_name = emote_name
        while emote_name in EMOTE_SETS:
            emote_name = f"{base_name}_{emote_idx}"
            emote_idx += 1

        self.logger.info(f"Adding emote {emote_name}...")
        res_emote: discord.Emoji = await guild.create_custom_emoji(name=emote_name, image=image_bytes)
        await inter.followup.send(f"Added new emote\n{res_emote!s} (`:{res_emote.name}:`)")

    @app_commands.command(name="emotesteal")
    @app_commands.guild_only()
    @app_commands.describe(emote="Emote kustom yang ingin dicuri")
    async def _ppemote_stealing(self, inter: discord.Interaction, emote: str):
        """Curi emote dari peladen lain ke peladen ini"""
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(
                "Perintah ini hanya dapat digunakan di dalam server.", ephemeral=True
            )
        if not isinstance(inter.user, discord.Member) or not inter.user.guild_permissions.manage_expressions:
            return await inter.response.send_message("Butuh permission Manage Expressions.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        try:
            stealed_emote = await StealedEmote().convert(await self.bot.get_context(inter), emote)
        except commands.CommandError:
            return await inter.followup.send("Gagal mendapatkan emote yang dimaksud.")

        CURRENT_STATIC, CURRENT_ANIMATED, EMOTE_SETS = self.__propagate_emote(guild.emojis)
        MAX_EMOTE = guild.emoji_limit
        image_bytes = await stealed_emote.read()
        animated = stealed_emote.animated
        if (CURRENT_ANIMATED if animated else CURRENT_STATIC) >= MAX_EMOTE:
            return await inter.followup.send(self._limit_error(animated, MAX_EMOTE))

        emote_name = stealed_emote.name
        base_name = emote_name
        emote_idx = 1
        while emote_name in EMOTE_SETS:
            emote_name = f"{base_name}_{emote_idx}"
            emote_idx += 1

        self.logger.info(f"Stealing emote {emote_name}...")
        res_emote: discord.Emoji = await guild.create_custom_emoji(name=emote_name, image=image_bytes)
        await inter.followup.send(f"Stealed new emote\n{res_emote!s} (`:{res_emote.name}:`)")


async def setup(bot: naoTimesBot):
    await bot.add_cog(PrivateEmoteServer(bot))
