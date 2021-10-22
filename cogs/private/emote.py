import logging
import os
from typing import NamedTuple, Sequence, Tuple

import discord
import magic
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.converters import StealedEmote


class EmoteServer(NamedTuple):
    id: int  # Channel
    static: int  # Static message
    animated: int  # Animated message


class PrivateEmoteServer(commands.Cog):
    _GUILDS_MAP = {
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
        if chatter is None:
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

    def __propagate_emote(self, emojis: Tuple[discord.Emoji]):
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

    @commands.command(name="nemote")
    @commands.guild_only()
    async def _ppemote_nemote(self, ctx: naoTimesContext, emote_name: str = ""):
        guild: discord.Guild = ctx.guild
        if str(guild.id) not in self._GUILDS_MAP:
            return

        CURRENT_STATIC, CURRENT_ANIMATED, EMOTE_SETS = self.__propagate_emote(guild.emojis)
        MAX_EMOTE = guild.emoji_limit

        self.logger.info("Adding emote...")
        attachments = ctx.message.attachments
        if not attachments:
            await ctx.send_timed("Please attach an image (PNG, JPG, GIF).", 5)
            return await ctx.message.delete(no_log=True)

        self.logger.info("Fetching attachments...")
        image_data: discord.Attachment = attachments[0]
        if image_data.size >= 262140:
            await ctx.send_timed("Image must be under 256kb.", 5)
            return await ctx.message.delete(no_log=True)

        image_bytes = await image_data.read()
        filename, extension = os.path.splitext(image_data.filename)
        self.logger.info("Checking mimetypes...")
        magic_mime = magic.Magic(mime=True)
        mime_res = magic_mime.from_buffer(image_bytes)
        if extension.lower() not in ("jpg", "jpeg", "png", "gif") and mime_res not in (
            "image/gif",
            "image/png",
            "image/jpg",
            "image/jpeg",
        ):
            await ctx.send_timed("Not a valid image (Must be PNG, JPG, or GIF).", 5)
            return await ctx.message.delete(no_log=True)

        self.logger.info("Checking server limit...")
        if mime_res == "image/gif":
            if CURRENT_ANIMATED >= MAX_EMOTE:
                await ctx.send_timed(
                    f"Sorry, the server already reach {MAX_EMOTE} animated emoji limit.\n"
                    "Please contact N4O#8868.",
                    5,
                )
                return await ctx.message.delete(no_log=True)
        else:
            if CURRENT_STATIC >= MAX_EMOTE:
                await ctx.send_timed(
                    f"Sorry, the server already reach {MAX_EMOTE} static emoji limit.\n"
                    "Please contact N4O#8868.",
                    5,
                )
                return await ctx.message.delete(no_log=True)

        if not emote_name:
            emote_name = filename

        emote_idx = 1
        while True:
            if emote_name not in EMOTE_SETS:
                break
            emote_name = f"{emote_name}_{emote_idx}"
            emote_idx += 1

        self.logger.info(f"Adding emote {emote_name}...")
        res_emote: discord.Emoji = await guild.create_custom_emoji(name=emote_name, image=image_bytes)
        await ctx.send_timed(
            f"Added new emote\n{str(res_emote)} (`:{res_emote.name}:`)",
            5,
        )
        await ctx.message.delete(no_log=True)

    @commands.command(name="emotesteal", aliases=["stealemote"])
    @commands.guild_only()
    async def _ppemote_stealing(self, ctx: naoTimesContext, stealed_emote: StealedEmote):
        guild: discord.Guild = ctx.guild

        CURRENT_STATIC, CURRENT_ANIMATED, EMOTE_SETS = self.__propagate_emote(guild.emojis)
        MAX_EMOTE = guild.emoji_limit

        self.logger.info("Stealing emote...")
        image_bytes = await stealed_emote.read()
        self.logger.info("Checking server limit...")
        if stealed_emote.animated:
            if CURRENT_ANIMATED >= MAX_EMOTE:
                await ctx.send_timed(
                    f"Sorry, the server already reach {MAX_EMOTE} animated emoji limit.\n"
                    "Please contact N4O#8868.",
                    5,
                )
                return await ctx.message.delete(no_log=True)
        else:
            if CURRENT_STATIC >= MAX_EMOTE:
                await ctx.send_timed(
                    f"Sorry, the server already reach {MAX_EMOTE} static emoji limit.\n"
                    "Please contact N4O#8868.",
                    5,
                )
                return await ctx.message.delete(no_log=True)

        emote_idx = 1
        emote_name = stealed_emote.name
        while True:
            if emote_name not in EMOTE_SETS:
                break
            emote_name = f"{emote_name}_{emote_idx}"
            emote_idx += 1

        self.logger.info(f"Stealing emote {emote_name}...")
        res_emote: discord.Emoji = await guild.create_custom_emoji(name=emote_name, image=image_bytes)
        await ctx.send_timed(
            f"Stealed new emote\n{str(res_emote)} (`:{res_emote.name}:`)",
            5,
        )


def setup(bot: naoTimesBot):
    bot.add_cog(PrivateEmoteServer(bot))
