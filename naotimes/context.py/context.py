"""
MIT License

Copyright (c) 2019-2022 naoTimesdev

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
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    TypeVar,
    Union,
    overload,
)

import discord
from discord import app_commands
from discord.ext import commands

from .helpgenerator import HelpGenerator
from .t import T
from .views import ConfirmView, MultiButtonView, MultiSelectionView, Selection

if TYPE_CHECKING:
    from .bot import naoTimesBot

__all__ = (
    "naoTimesContext",
    "naoTimesAppTree",
)
BotT = TypeVar("BotT", bound="naoTimesBot")
CogT = TypeVar("CogT", bound="commands.Cog")


class naoTimesContext(commands.Context[BotT]):
    """A custom naoTimes context for most stuff"""

    bot: naoTimesBot

    @property
    def id(self):
        return self.message.id

    def is_interaction(self):
        """Check if the message is interaction"""
        return self.interaction is not None

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

    @property
    def i18n(self):
        """Get the i18n instance"""
        guild = self.guild
        default_inst = self.bot.i18n_bot.getdefault()
        if guild is None:
            return default_inst
        guild_id = str(guild.id)
        return self.bot.get_i18n(guild_id) or default_inst

    @overload
    async def wait_content(
        self,
        message: str,
        delete_prompt: bool = ...,
        delete_answer: bool = ...,
        timeout: int = ...,
        return_all: bool = False,
        pass_message: discord.Message = ...,
        allow_cancel: bool = ...,
    ) -> Optional[Union[str, bool]]:
        ...

    @overload
    async def wait_content(
        self,
        message: str,
        delete_prompt: bool = ...,
        delete_answer: bool = ...,
        timeout: int = ...,
        return_all: bool = True,
        pass_message: discord.Message = ...,
        allow_cancel: bool = ...,
    ) -> Tuple[Optional[Union[str, bool]], Optional[discord.Message], Optional[discord.Message]]:
        ...

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
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        try:
            await msg.delete()
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            pass

    async def confirm(
        self, message: Union[str, discord.Message], embed: discord.Embed = None, dont_remove: bool = False
    ):
        """Send a confirmation dialog

        :param bot: The bot instance
        :type bot: naoTimesBot
        :param message: The message
        :type message: str
        """
        view = ConfirmView(self, timeout=None)
        if isinstance(message, str):
            msg = await self.send(message, embed=embed, view=view)
        else:
            msg = await message.edit(view=view)
        await view.wait()
        if not dont_remove:
            try:
                await msg.delete()
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass
        else:
            await self._remove_view(message)
        if view.value:
            return True
        return False

    async def _remove_view(self, message: discord.Message):
        try:
            await message.edit(view=None)
        except Exception:
            pass

    async def select_single(
        self,
        choices: List[T],
        generator: Callable[[T], Selection],
        delete_later: bool = True,
        **extra_kwargs: Dict[str, Any],
    ) -> Optional[T]:
        """
        Create a embed selection using reaction

        :param choices: The choices for the bot to Use
        :type choices: List[T]
        :param generator: The function generator to use, must return :class:`Selection`
        :type generator: Callable[[T], Selection]
        :param extra_kwargs: Extra keyword arguments for ctx.send
        :type extra_kwargs: Dict[str, Any]
        :return: The selected or None if not selection anything
        :rtype: T
        """
        bot = self.bot
        bot.logger.info("Asking for user selection...")
        generated_selections: Dict[str, Selection] = []
        for choice in choices:
            gen_choice = generator(choice)
            if not isinstance(gen_choice, Selection):
                raise TypeError(f"Generator must return a Selection, not {type(gen_choice)}")
            generated_selections.append(gen_choice)

        view = MultiSelectionView(self, generated_selections, timeout=None)
        extra_kwargs.pop("view", None)
        extra_kwargs.pop("delete_after", None)
        message = await self.send(**extra_kwargs, view=view)
        await view.wait()
        if view.cancelled:
            await self._remove_view(message)
            return None
        if view.selected is None:
            await self._remove_view(message)
            return None
        sel_choice: Optional[T] = None
        for choice in choices:
            gen_choice = generator(choice)
            if gen_choice.name == view.selected.value:
                sel_choice = choice
                break
        if delete_later:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass
        else:
            await self._remove_view(message)
        return sel_choice

    async def select_single_button(
        self,
        message: Union[str, discord.Message],
        selections: List[Selection],
        timeout: Optional[float] = 180.0,
    ) -> Optional[Union[Selection, Literal[False]]]:
        """
        Do a multiple button selection to select one choice!
        It will returns None if it's timeout, False if the "Cancel" button
        is selected.

        Maximum choice is 24 choices (the last one is for cancel button)
        """
        view = MultiButtonView(self, selections, timeout=timeout)
        if isinstance(message, discord.Message):
            msg = await message.edit(view=view)
        else:
            if isinstance(message, discord.Embed):
                msg = await self.send(embed=message, view=view)
            else:
                msg = await self.send(message, view=view)

        await view.wait()
        await self._remove_view(msg)
        if view.selected is None:
            return None
        if view.cancelled:
            return False
        return view.selected

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

    def get_cog(self):
        return self.cog

    async def clear_view(self, message: discord.Message):
        """Clear the view of a message"""
        # Check if we have any view
        if not message.view:
            return
        await message.edit(view=None)


class naoTimesAppTree(app_commands.CommandTree):
    client: naoTimesBot

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        # Dispatch the error to on_app_command_error
        wrapped_ctx = await self.client.get_context(interaction)
        self.client.dispatch("application_command_error", wrapped_ctx, error)
