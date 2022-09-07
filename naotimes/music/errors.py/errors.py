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

from typing import TYPE_CHECKING, Optional, Tuple

from discord.ext.commands.errors import CommandError

if TYPE_CHECKING:
    from naotimes.context import naoTimesContext

__all__ = (
    "naoTimesMusicException",
    "UnsupportedURLFormat",
    "SpotifyUnavailable",
    "TidalUnavailable",
    "EnsureVoiceChannel",
    "EnsureBotVoiceChannel",
    "EnsureHaveRequirement",
)


class naoTimesMusicException(Exception):
    pass


class UnsupportedURLFormat(naoTimesMusicException):
    def __init__(self, url: str, *reason: Tuple[str, ...]) -> None:
        self.url: str = url
        merge_reason = None
        if reason:
            merge_reason = " ".join(reason)
        print(reason)
        self.reason: Optional[str] = merge_reason

        super().__init__(f"URL {url} tidak disupport oleh naoTimes\n{self.reason}")


class SpotifyUnavailable(naoTimesMusicException):
    pass


class TidalUnavailable(SpotifyUnavailable):
    pass


class EnsureVoiceChannel(CommandError):
    def __init__(self, ctx: naoTimesContext, main_check: bool = True) -> None:
        self.ctx: naoTimesContext = ctx
        self.main_check: bool = main_check
        super().__init__(f"{ctx.author} anda harus join VC terlebih dahulu")


class EnsureBotVoiceChannel(CommandError):
    """
    Ensure that the command was ran in a voice channel
    """

    def __init__(self, ctx: naoTimesContext) -> None:
        self.ctx: naoTimesContext = ctx
        super().__init__("Bot tidak terhubung dengan VC!")


class EnsureHaveRequirement(CommandError):
    """
    Ensure that the command was ran in a voice channel
    """

    def __init__(self, ctx: naoTimesContext, *reason: Tuple[str, ...]) -> None:
        self.ctx: naoTimesContext = ctx
        merge_reason = None
        if reason:
            merge_reason = " ".join(reason)
        self.reason: Optional[str] = merge_reason
        super().__init__(f"{self.reason}")


class WavelinkNoNodes(CommandError):
    """
    Ensure that the command was ran with any lavalink nodes available.
    """

    pass
