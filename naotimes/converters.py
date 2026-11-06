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

from typing import TYPE_CHECKING, Self, cast

from discord.ext import commands

if TYPE_CHECKING:
    from .bot import naoTimesBot

__all__ = ("StealedEmote",)


class StealedEmote(commands.Converter["StealedEmote"]):
    """
    A Converter Class that will magically convert the input emote to ready to steal
    Emoji data.
    ---

    Example Usage:
    ```py
        async def steal_emote(self, ctx, stealed_emote: StealedEmote):
            print(stealed_emote.name)
    ```
    """

    _cached_emote_data: bytes
    _id: int | None
    _name: str | None

    def __init__(self, **kwargs):
        self._id = kwargs.get("id")
        self._name = kwargs.get("name")
        self.animated: bool = kwargs.get("animated", False)

        self._bot: naoTimesBot | None = None

    @property
    def id(self) -> int:
        if self._id is None:
            raise ValueError("Emote ID is unavailable before conversion")
        return self._id

    @id.setter
    def id(self, value: int) -> None:
        self._id = value

    @property
    def name(self) -> str:
        if self._name is None:
            raise ValueError("Emote name is unavailable before conversion")
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    def __str__(self):
        if self.animated:
            return f"<a:{self.name}:{self.id}>"
        return f"<:{self.name}:{self.id}>"

    def __repr__(self):
        return f"<StealedEmote id={self.id} name={self.name!r} animated={self.animated}>"

    def __hash__(self):
        return self.id >> 22

    async def convert(self, ctx: commands.Context, argument: str) -> Self:
        self._bot = cast("naoTimesBot", ctx.bot)
        if argument.startswith("<:") and argument.endswith(">"):
            message = argument[2:-1]
            try:
                emote_name, emote_id = message.split(":")
            except ValueError as err:
                raise commands.ConversionError(self, err) from err
            self.name = emote_name
            try:
                self.id = int(emote_id)
            except ValueError as err:
                raise commands.ConversionError(self, err) from err
            return self
        elif argument.startswith("<a:") and argument.endswith(">"):
            message = argument[1:-1]
            try:
                _, emote_name, emote_id = message.split(":")
            except ValueError as err:
                raise commands.ConversionError(self, err) from err
            self.name = emote_name
            try:
                self.id = int(emote_id)
            except ValueError as err:
                raise commands.ConversionError(self, err) from err
            self.animated = True
            return self
        else:
            raise commands.ConversionError(self, ValueError(f'Failed to convert "{argument}": missing emote'))

    @property
    def url(self) -> str:
        """Return URL formatted data for the Stealed Emote"""
        fmt = "gif" if self.animated else "png"
        return f"https://cdn.discordapp.com/emojis/{self.id}.{fmt}"

    async def read(self, bot: naoTimesBot | None = None) -> bytes:
        """Read from URL to bytes data.

        :raises ValueError: If ID not set
        :return: Emoji data in bytes
        :rtype: bytes
        """
        if hasattr(self, "_cached_emote_data") and self._cached_emote_data is not None:
            return self._cached_emote_data
        if self._id is None:
            raise ValueError("Failed to read since there's no data to read.")
        resolved_bot = self._bot or bot
        if resolved_bot is None:
            error_msg = "Failed to read, since there's no bot data in this class\n"
            error_msg += "Please pass the bot into this read function"
            raise ValueError(error_msg)
        if resolved_bot.aiosession is None:
            raise RuntimeError("Failed to read emote because the HTTP session is unavailable")
        self._bot = resolved_bot

        async with resolved_bot.aiosession.get(self.url) as resp:
            if resp.status != 200:
                if resp.status == 404:
                    raise FileNotFoundError("Failed to read data from URL, emote possibly deleted.")
                raise ConnectionError(f"Failed to read data from URL, got status: {resp.status}")
            results = await resp.read()
        self._cached_emote_data = results
        return results
