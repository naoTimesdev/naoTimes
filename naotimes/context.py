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

import discord
from discord.ext import app, commands

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
        pass_message: discord.Message = None,
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
        prompt: discord.Message
        if pass_message is not None:
            prompt = pass_message
            await prompt.edit(content=message)
        else:
            prompt = await self.send(message)

        def check_author(m: discord.Message):
            return m.author == self.message.author and m.channel == self.message.channel

        try:
            await_msg: discord.Message = await bot.wait_for("message", check=check_author, timeout=timeout)
            msg_content = await_msg.content
            if delete_answer:
                try:
                    await await_msg.delete(no_log=True)
                except discord.Forbidden:
                    pass
            if delete_prompt:
                try:
                    await prompt.delete()
                except discord.Forbidden:
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
        msg: discord.Message = await self.send(message)
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            pass

    async def confirm(self, message: Union[str, discord.Message], dont_remove: bool = False):
        """Send a confirmation dialog

        :param bot: The bot instance
        :type bot: naoTimesBot
        :param message: The message
        :type message: str
        """
        bot = self.bot
        if isinstance(message, str):
            message: discord.Message = await self.send(message)
        is_dm = isinstance(self.channel, discord.DMChannel)
        to_react = ["✅", "❌"]
        for react in to_react:
            await message.add_reaction(react)

        def check_react(reaction: discord.Reaction, user: discord.User):
            if reaction.message.id != message.id:
                return False
            if user.id != self.message.author.id:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        res: discord.Reaction
        user: discord.Member
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
                except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                    pass
                break
            elif "❌" in str(res.emoji):
                dialog_tick = False
                try:
                    if not dont_remove:
                        await message.delete()
                except (discord.Forbidden, discord.HTTPException, discord.NotFound):
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
                embed = discord.Embed(title="Pilih:", color=discord.Color.random())
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
                message: discord.Message = await self.send(embed=embed)

            reactmote_ext = ["❌"]
            reactmoji_cont = reactmoji[: len(choices)]
            reactmoji_cont.extend(reactmote_ext)

            for react in reactmoji_cont:
                await message.add_reaction(react)

            def check_reaction(reaction: discord.Reaction, user: discord.User):
                if reaction.message.id != message.id:
                    return False
                if user.id != self.message.author.id:
                    return False
                if str(reaction.emoji) not in reactmoji_cont:
                    return False
                return True

            res: discord.Reaction
            user: discord.Member
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


class naoTimesAppContext(app.ApplicationContext[BotT, CogT]):
    """A custom naoTimes application command context for most stuff

    Mainly for extra typing.
    """

    bot: naoTimesBot

    if TYPE_CHECKING:
        cog: CogT
