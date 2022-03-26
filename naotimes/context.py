"""
MIT License

Copyright (c) 2019-2021 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable, List, Optional, TypeVar, Union

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from .helpgenerator import HelpGenerator
from .t import T

if TYPE_CHECKING:
    from .bot import naoTimesBot

__all__ = ("naoTimesContext", "naoTimesAppContext")
BotT = TypeVar("BotT", bound="naoTimesBot")
CogT = TypeVar("CogT", bound="commands.Cog")


class naoTimesContext(commands.Context[BotT]):
    """A custom naoTimes context for most stuff"""

    bot: naoTimesBot

    def empty_subcommand(self, threshold: int = 3) -> bool:
        """Check if the message is empty for subcommand stuff
        Mainly use for !help command, etc.

        :param threshold: the threshold before it's being counted as empty
        :type threshold: int
        :return: if the message empty
        :rtype: bool
        """
        clean_msg: str = self.message.clean_content
        split_content = clean_msg.split(" ")
        split_content = filter(lambda m: m != "", split_content)
        return len(list(split_content)) < threshold

    def create_help(self, *args, **kwargs) -> HelpGenerator:
        """Create a help generator"""
        bot = self.bot
        return HelpGenerator(bot, self, *args, **kwargs)

    async def wait_content(
        self,
        message: str,
        delete_prompt: bool = False,
        delete_answer: bool = False,
        timeout: int = 30,
        return_all: bool = False,
        pass_message: disnake.Message = None,
        allow_cancel: bool = True,
    ) -> Optional[Union[str, bool]]:
        """Sent a message and wait for a response from user

        :param bot: The bot instance
        :type bot: naoTimesBot
        :param message: The message
        :type message: str
        """
        bot = self.bot
        if allow_cancel:
            message += "\nUntuk membatalkan, ketik: `cancel`"
        prompt: disnake.Message
        if pass_message is not None:
            prompt = pass_message
            await prompt.edit(content=message)
        else:
            prompt = await self.send(message)

        def check_author(m: disnake.Message):
            return m.author == self.message.author and m.channel == self.message.channel

        try:
            await_msg: disnake.Message = await bot.wait_for("message", check=check_author, timeout=timeout)
            msg_content = await_msg.content
            if delete_answer:
                try:
                    await await_msg.delete(no_log=True)
                except disnake.Forbidden:
                    pass
            if delete_prompt:
                try:
                    await prompt.delete()
                except disnake.Forbidden:
                    pass
            if isinstance(msg_content, str) and msg_content.lower() == "cancel" and allow_cancel:
                if return_all:
                    return [False, prompt, await_msg]
                return False
            if return_all:
                return [msg_content, prompt, await_msg]
            return msg_content
        except asyncio.TimeoutError:
            if return_all:
                return [None, prompt, None]
            return None

    async def send_timed(self, message: str, delay: Union[str, float] = 3):
        """Send a timed message to a channel or context

        :param message: The message to be sent
        :type message: str
        :param delay: How long the message will be alive
        :type delay: Union[str, float]
        """
        msg: disnake.Message = await self.send(message)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        try:
            await msg.delete()
        except (disnake.Forbidden, disnake.HTTPException, disnake.NotFound):
            pass

    async def confirm(self, message: Union[str, disnake.Message], dont_remove: bool = False):
        """Send a confirmation dialog

        :param bot: The bot instance
        :type bot: naoTimesBot
        :param message: The message
        :type message: str
        """
        bot = self.bot
        if isinstance(message, str):
            message: disnake.Message = await self.send(message)
        is_dm = isinstance(self.channel, disnake.DMChannel)
        to_react = ["✅", "❌"]
        for react in to_react:
            try:
                await message.add_reaction(react)
            except disnake.Forbidden:
                await self.send("Tidak dapat menambah reaksi ke pesan konfirmasi!")
                return False

        def check_react(reaction: disnake.Reaction, user: disnake.User):
            if reaction.message.id != message.id:
                return False
            if user.id != self.message.author.id:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        res: disnake.Reaction
        user: disnake.Member
        dialog_tick = True
        while True:
            res, user = await bot.wait_for("reaction_add", check=check_react)
            if user != self.message.author:
                continue
            if not is_dm:
                await message.clear_reactions()
            if "✅" in str(res.emoji):
                try:
                    if not dont_remove:
                        await message.delete()
                except (disnake.Forbidden, disnake.HTTPException, disnake.NotFound):
                    pass
                break
            elif "❌" in str(res.emoji):
                dialog_tick = False
                try:
                    if not dont_remove:
                        await message.delete()
                except (disnake.Forbidden, disnake.HTTPException, disnake.NotFound):
                    pass
                break
        return dialog_tick

    async def select_simple(self, choices: List[T], generator: Callable[[T], str]) -> Optional[T]:
        """
        Create a embed selection using reaction

        :param choices: The choices for the bot to Use
        :type choices: List[T]
        :param generator: The function generator to use
        :type generator: Callable[[T], str]
        :return: The selected or None if not selection anything
        :rtype: T
        """
        bot: "naoTimesBot" = self.bot
        bot.logger.info("Asking for user input...")
        choices = choices[:10]
        reactmoji = [
            "1⃣",
            "2⃣",
            "3⃣",
            "4⃣",
            "5⃣",
            "6⃣",
            "7⃣",
            "8⃣",
            "9⃣",
            "0⃣",
        ]
        selected = None
        first_run = True
        while True:
            if first_run:
                embed = disnake.Embed(title="Pilih:", color=disnake.Color.random())
                formatted_value = []
                for pos, content in enumerate(choices):
                    parse_content = generator(content)
                    formatted_value.append(f"{reactmoji[pos]} **{parse_content}**")
                formatted_value.append("❌ **Batalkan**")
                embed.description = "\n".join(formatted_value)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™", icon_url="https://naoti.me/assets/img/nt192.png"
                )
                first_run = False
                message: disnake.Message = await self.send(embed=embed)

            reactmote_ext = ["❌"]
            reactmoji_cont = reactmoji[: len(choices)]
            reactmoji_cont.extend(reactmote_ext)

            for react in reactmoji_cont:
                await message.add_reaction(react)

            def check_reaction(reaction: disnake.Reaction, user: disnake.User):
                if reaction.message.id != message.id:
                    return False
                if user.id != self.message.author.id:
                    return False
                if str(reaction.emoji) not in reactmoji_cont:
                    return False
                return True

            res: disnake.Reaction
            user: disnake.Member
            try:
                res, user = await bot.wait_for("reaction_add", check=check_reaction)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break
            if user != self.message.author:
                pass
            elif "❌" in str(res.emoji):
                await message.clear_reactions()
                break
            else:
                await message.clear_reactions()
                react_pos = reactmoji.index(str(res.emoji))
                selected = choices[react_pos]
                break
        await message.delete()
        return selected

    async def send_chunked(self, message: str, *, limit: int = 2048, fast: bool = False):
        """Send a string to a channel or target
        This will try to send it in chunk without breaking the limit.

        :param message: The message to be sent
        :type message: str
        :param limit: The limit characters to be sent each chunks, defaults to 2048
        :type limit: int, optional
        :param fast: Will not split the sentences properly, defaults to False
        :type fast: bool, optional
        """

        # Dont chunk if the message is too short to the limit
        if len(message) < limit:
            return await self.send(message)

        if fast:
            # Quick splitting method.
            # Will split the character according to the limit
            # So it can split it like "This is a full word" into
            # "This is a fu" and "ll word". Would be bad
            # So if we eexpect a really long message just use this chunking method
            # Or the user can override it.
            chunks = [message[i : i + limit] for i in range(0, len(message), limit)]
        else:
            # Slow chunking operation, basically joining and checking if the chunk
            # will hit the limit, if we add more sentences or word to it.
            # If yes, join it and push it into chunks list
            # Much more easier to read but slower. Example: "This is a full word"
            # Will be split into "This is a" and "full word"
            chunks: List[str] = []
            current_chunk: List[str] = []
            split_chunks = message.split()
            for split in split_chunks:
                current = len(" ".join(current_chunk))
                if current + len(split) > limit:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                current_chunk.append(split)
            if current_chunk:
                chunks.append(" ".join(current_chunk))

        for chunk in chunks:
            # Actually send the chunked messages
            await self.send(chunk)


class naoTimesAppContext(ApplicationCommandInteraction):
    """A custom naoTimes application command context for most stuff

    Mainly for extra typing.
    """

    client: naoTimesBot

    @property
    def cog(self) -> CogT:
        return self.application_command.cog

    @property
    def bot(self) -> naoTimesBot:
        return self.client

    def get_cog(self, name: str) -> Optional[CogT]:
        """Shortcut to get a cog from the bot."""
        return self.client.get_cog(name)

    async def defer(self, *, ephemeral: bool = False, with_message: bool = False) -> None:
        """|coro|

        Defers the interaction response.

        This is typically used when the interaction is acknowledged
        and a secondary action will be done later.

        This is a shortcut to :meth:`ApplicationCommandInteraction.response.defer`.

        Parameters
        ----------
        ephemeral: :class:`bool`
            Whether the deferred message will eventually be ephemeral.
        with_message: :class:`bool`
            Whether the response will be a message with thinking state (bot is thinking...).
            This only applies to interactions of type :attr:`InteractionType.component`.

            .. versionadded:: 2.4

        Raises
        ------
        HTTPException
            Deferring the interaction failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        await self.response.defer(ephemeral=ephemeral, with_message=with_message)
