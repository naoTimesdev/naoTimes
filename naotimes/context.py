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

import logging
from collections.abc import Callable, Coroutine
from math import ceil
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    TypedDict,
    TypeVar,
    Union,
    Unpack,
    cast,
    overload,
)

import discord
from discord import app_commands
from discord.ext import commands

from .i18n import MissingTranslation
from .t import T
from .views import ConfirmView, MultiButtonView, MultiSelectionView, Selection

if TYPE_CHECKING:
    from .bot import naoTimesBot

__all__ = (
    "OwnerGroup",
    "naoTimesAppTree",
    "naoTimesContext",
    "owner_only",
)

logger = logging.getLogger("naotimes.context")


def _module_from_path(module_path: str) -> str | None:
    """Map a ``cogs.<module>.<file>`` module path to an i18n module."""
    parts = (module_path or "").split(".")
    if len(parts) >= 3 and parts[0] == "cogs":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "cogs":
        return parts[-1]
    return None


def _resolve_cog_module(cog: commands.Cog | None) -> str:
    """Return the i18n module that belongs to a cog."""
    if cog is None:
        return "common"
    explicit = getattr(type(cog), "module", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return _module_from_path(getattr(cog, "__module__", "")) or "common"


def _resolve_context_module(ctx: naoTimesContext) -> str:
    """Resolve the i18n module for a context, including pure slash commands.

    ``commands.Context.cog`` assumes ``command.cog`` exists, which vanilla
    ``app_commands.Command`` objects do not provide, so fall back to the
    command binding or the callback module.
    """
    try:
        cog = ctx.cog
    except AttributeError:
        cog = None
    if cog is not None:
        return _resolve_cog_module(cog)
    command = getattr(ctx, "command", None)
    binding = getattr(command, "binding", None)
    if isinstance(binding, commands.Cog):
        return _resolve_cog_module(binding)
    callback = getattr(command, "callback", None)
    return _module_from_path(getattr(callback, "__module__", "")) or "common"


def _translate_interaction(interaction: discord.Interaction, key: str, **kwargs: Any) -> str | None:
    """Resolve a shared string for the interaction's guild, or None when unavailable."""
    i18n_for = getattr(interaction.client, "i18n_for", None)
    if i18n_for is None:
        return None
    try:
        return i18n_for(interaction.guild).resolve_key(key, **kwargs)
    except MissingTranslation:
        return None


BotT = TypeVar("BotT", bound="naoTimesBot")
CogT = TypeVar("CogT", bound="commands.Cog")
ValidatorSync = Callable[[str], bool]
ValidatorAsync = Callable[[str], Coroutine[Any, Any, bool]]
ValidatorT = Union[ValidatorSync, ValidatorAsync]


class ContextSendKwargs(TypedDict, total=False):
    content: str | None
    tts: bool
    embed: discord.Embed
    delete_after: float
    nonce: str | int
    allowed_mentions: discord.AllowedMentions
    reference: discord.Message | discord.MessageReference | discord.PartialMessage
    mention_author: bool
    view: discord.ui.View
    suppress_embeds: bool
    ephemeral: bool
    silent: bool
    poll: discord.Poll


class _NoLogDeletable(Protocol):
    async def delete(self, *, delay: float | None = None, no_log: bool = False) -> None: ...


async def _delete_without_logging(message: discord.Message) -> None:
    # naotimes.monke adds this keyword to discord.Message.delete at runtime.
    await cast(_NoLogDeletable, message).delete(no_log=True)


class naoTimesContext(commands.Context["naoTimesBot"]):
    """A custom naoTimes context for most stuff"""

    bot: naoTimesBot

    @property
    def id(self):
        return self.message.id

    def is_interaction(self):
        """Check if the message is interaction"""
        return self.interaction is not None

    @property
    def i18n(self):
        """Get the i18n instance"""
        guild = self.guild
        default_inst = self.bot.i18n_bot.getdefault()
        if guild is None:
            return default_inst
        guild_id = str(guild.id)
        return self.bot.get_i18n(guild_id) or default_inst

    @property
    def locale(self) -> str:
        """The language code used by this context."""
        return self.i18n.language

    @property
    def cog_module(self) -> str:
        """The i18n module that belongs to the current cog."""
        return _resolve_context_module(self)

    def t(self, translation_key: str, *args: Any, **kwargs: Any) -> str:
        """Translate a module-relative key and never raise on a missing key."""
        mod = self.i18n
        module = self.cog_module
        if "." in translation_key:
            head, rest = translation_key.split(".", 1)
            if head in self.bot.i18n_bot.known_modules:
                module, translation_key = head, rest
        try:
            return mod.resolve(module, translation_key, *args, **kwargs)
        except MissingTranslation as exc:
            logger.error("i18n: %s", exc)
            return translation_key
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("i18n: failed to format %s.%s: %s", module, translation_key, exc)
            return translation_key

    async def confirm(
        self, message: str | discord.Message, embed: discord.Embed | None = None, dont_remove: bool = False
    ):
        """Send a confirmation dialog

        :param bot: The bot instance
        :type bot: naoTimesBot
        :param message: The message
        :type message: str
        """
        view = ConfirmView(self)
        if isinstance(message, str):
            if embed is None:
                msg = await self.send(message, view=view)
            else:
                msg = await self.send(message, embed=embed, view=view)
        else:
            msg = await message.edit(view=view)
        await view.wait()
        if not dont_remove:
            try:
                await _delete_without_logging(msg)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass
        else:
            await self._remove_view(msg)
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
        choices: list[T],
        generator: Callable[[T], Selection],
        delete_later: bool = True,
        **extra_kwargs: Unpack[ContextSendKwargs],
    ) -> T | None:
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
        generated_selections: list[Selection] = []
        for choice in choices:
            gen_choice = generator(choice)
            if not isinstance(gen_choice, Selection):
                raise TypeError(f"Generator must return a Selection, not {type(gen_choice)}")
            generated_selections.append(gen_choice)

        view = MultiSelectionView(self, generated_selections)
        extra_kwargs.pop("view", None)
        extra_kwargs.pop("delete_after", None)
        extra_kwargs["view"] = view
        message = await self.send(**extra_kwargs)
        await view.wait()
        if view.cancelled:
            await self._remove_view(message)
            return None
        if view.selected is None:
            await self._remove_view(message)
            return None
        sel_choice: T | None = None
        for choice in choices:
            gen_choice = generator(choice)
            if gen_choice.name == view.selected.value:
                sel_choice = choice
                break
        if delete_later:
            try:
                await _delete_without_logging(message)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass
        else:
            await self._remove_view(message)
        return sel_choice

    @overload
    async def select_single_button(
        self,
        message: str | discord.Embed | discord.Message,
        selections: list[Selection],
        timeout: float | None = ...,  # ruff: ignore[async-function-with-timeout]
    ) -> Selection | Literal[False] | None: ...

    @overload
    async def select_single_button(
        self,
        message: str | discord.Embed | discord.Message,
        selections: list[Selection],
        timeout: float | None = ...,  # ruff: ignore[async-function-with-timeout]
        no_cancelation: bool = True,
    ) -> Selection | None: ...

    @overload
    async def select_single_button(
        self,
        message: str | discord.Embed | discord.Message,
        selections: list[Selection],
        timeout: float | None = None,  # ruff: ignore[async-function-with-timeout]
        no_cancelation: bool = True,
    ) -> Selection: ...

    async def select_single_button(
        self,
        message: str | discord.Embed | discord.Message,
        selections: list[Selection],
        timeout: float | None = 180.0,  # ruff: ignore[async-function-with-timeout]
        no_cancelation: bool = False,
    ) -> Selection | Literal[False] | None:
        """
        Do a multiple button selection to select one choice!
        It will returns None if it's timeout, False if the "Cancel" button
        is selected.

        Maximum choice is 24 choices (the last one is for cancel button)
        """
        view_timeout = 180 if timeout is None else ceil(timeout)
        view = MultiButtonView(self, selections, timeout=view_timeout, no_cancel=no_cancelation)
        if isinstance(message, discord.Message):
            msg = await message.edit(view=view)
        else:
            if isinstance(message, discord.Embed):
                msg = await self.send(embed=message, view=view)
            elif isinstance(message, str):
                msg = await self.send(message, view=view)
            else:
                raise TypeError(f"message must be a string, Embed, or Message, not {type(message).__name__}")

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
            chunks: list[str] = []
            current_chunk: list[str] = []
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
        if not message.components:
            return
        await message.edit(view=None)


class OwnerGroup(app_commands.Group):
    """A slash command group that can only be used by the bot owner (or team members)."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        client = interaction.client
        if isinstance(client, commands.Bot) and await client.is_owner(interaction.user):
            return True
        message = _translate_interaction(interaction, "common.errors.owner_only")
        await interaction.response.send_message(message or "Perintah ini hanya untuk owner bot.", ephemeral=True)
        return False


async def _owner_check(interaction: discord.Interaction) -> bool:
    client = interaction.client
    if isinstance(client, commands.Bot) and await client.is_owner(interaction.user):
        return True
    message = _translate_interaction(interaction, "common.errors.owner_only")
    await interaction.response.send_message(message or "Perintah ini hanya untuk owner bot.", ephemeral=True)
    return False


def owner_only():
    """``app_commands.check`` decorator for single commands that only the bot owner may run."""
    return app_commands.check(_owner_check)


class naoTimesAppTree(app_commands.CommandTree["naoTimesBot"]):
    client: naoTimesBot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global gate: maintenance mode and owner-disabled commands."""
        command = interaction.command
        if command is None:
            return True
        bot = self.client
        # The owner can always run commands (needed to end maintenance / re-enable commands).
        if await bot.is_owner(interaction.user):
            return True

        maintenance = bot.maintenance
        if maintenance is not None and maintenance.maintenance:
            end = maintenance.end.int_timestamp
            message = _translate_interaction(interaction, "common.errors.maintenance", end=end)
            await interaction.response.send_message(
                message or f"Bot sedang dalam masa pemeliharaan (maintenance), selesai <t:{end}:R>.",
                ephemeral=True,
            )
            return False

        root = command.qualified_name.split(" ")[0]
        for name in (command.qualified_name, root):
            if name in bot.disabled_commands:
                msg = _translate_interaction(interaction, "common.errors.disabled", command=name)
                msg = msg or f"Perintah **`{name}`** dinon-aktifkan oleh owner bot ini."
                reason = bot.disabled_commands[name]
                if reason:
                    reason_msg = _translate_interaction(interaction, "common.errors.disabled_reason", reason=reason)
                    msg += "\n" + (reason_msg or f"**Alasan**: {reason}")
                await interaction.response.send_message(msg, ephemeral=True)
                return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        # Dispatch the error to on_app_command_error
        wrapped_ctx = await self.client.get_context(interaction)
        self.client.dispatch("application_command_error", wrapped_ctx, error)
