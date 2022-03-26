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

import argparse
import shlex
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from disnake.ext import commands

from .context import naoTimesContext
from .showtimes import ShowtimesProject
from .timeparse import TimeString

if TYPE_CHECKING:
    from .bot import naoTimesBot

__all__ = ("Arguments", "CommandArgParse", "StealedEmote", "TimeConverter")


class ArgumentParserError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class HelpException(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class BotArgumentParser(argparse.ArgumentParser):
    def print_help(self, file=None):
        raise HelpException(self.format_help())

    def exit(self, status=0, message=None):
        raise HelpException(message)

    def error(self, message=None):
        raise ArgumentParserError(message)


bot_parser = BotArgumentParser(prog="!", usage="!", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
subparser = bot_parser.add_subparsers(dest="command")


class Arguments:
    def __init__(self, name):
        self._cmd_args = []
        self._cmd_name = name

    def add_args(self, *args, **kwargs):
        self._cmd_args.insert(0, (args, kwargs))

    @property
    def name(self):
        return self._cmd_name

    @name.setter
    def name(self, name: str):
        self._cmd_name = name

    @property
    def args(self):
        return self._cmd_args

    def get_args(self):
        return self._cmd_args

    def copy(self):
        new_self = Arguments(self.name)
        for arg in self.args:
            base_args = arg[0]
            base_kwargs = arg[1]
            new_self.add_args(*base_args, **base_kwargs)
        return new_self


class CommandArgParse(commands.Converter[argparse.Namespace]):
    def __init__(self, args: Arguments):
        self._args: Arguments = args
        self._defaults_map: Dict[str, Any] = {}
        self._any_kw = False
        self._init_args()

    @staticmethod
    def _parse_error(err_str: str) -> str:
        if err_str.startswith("unrecognized arguments"):
            err_str = err_str.replace("unrecognized arguments", "Argumen tidak diketahui")
        elif err_str.startswith("the following arguments are required"):
            err_str = err_str.replace(
                "the following arguments are required",
                "Argumen berikut wajib diberikan",
            )
        if "usage" in err_str:
            err_str = (
                err_str.replace("usage", "Gunakan")
                .replace("positional arguments", "Argumen yang diwajibkan")
                .replace("optional arguments", "Argumen opsional")
                .replace(
                    "show this help message and exit",
                    "Perlihatkan bantuan perintah",
                )
            )
            err_str = err_str.replace("Gunakan: ! ", "Gunakan: !")
        return err_str

    def _init_args(self):
        parser = subparser.add_parser(self._args.name)
        if self._args.get_args():
            for arg_args, arg_kwargs in self._args.get_args():
                get_args_path = arg_args[0]
                default = arg_kwargs.get("default")
                if default is not None and get_args_path.startswith("-"):
                    self._defaults_map[get_args_path] = default
                if not get_args_path.startswith("-") and not self._any_kw:
                    self._any_kw = True
                parser.add_argument(*arg_args, **arg_kwargs)

        self._parser = parser

    def _parse_args(self, argument: str):
        try:
            return self._parser.parse_args(shlex.split(argument))
        except ArgumentParserError as argserror:
            return self._parse_error(str(argserror))
        except HelpException as help_:
            return self._parse_error(str(help_))

    async def convert(self, ctx, argument):
        return self._parse_args(argument)

    def show_help(self):
        return self._parse_args("-h")


class TimeConverter(commands.Converter[TimeString]):
    """
    A converter Class that will convert a string-formatted text of time into a proper time data
    that can be used.

    This will convert the string into `:class:`TimeString

    Example Usage:
    ```py
        async def to_seconds(self, ctx, timething: TimeConverter):
            print(timething.timestamp())
    ```
    """

    async def convert(self, ctx: naoTimesContext, argument: str) -> TimeString:
        converted = TimeString.parse(argument)
        return converted


class StealedEmote(commands.Converter):
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

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.animated: bool = kwargs.get("animated", False)

        self._bot: Optional[naoTimesBot] = None

    def __str__(self):
        if self.animated:
            return "<a:{0.name}:{0.id}>".format(self)
        return "<:{0.name}:{0.id}>".format(self)

    def __repr__(self):
        return "<StealedEmote id={0.id} name={0.name!r} animated={0.animated}>".format(self)

    def __hash__(self):
        return self.id >> 22

    async def convert(self, ctx: naoTimesContext, argument: str):
        self._bot = ctx.bot
        if argument.startswith("<:") and argument.endswith(">"):
            message = argument[2:-1]
            try:
                emote_name, emote_id = message.split(":")
            except ValueError as err:
                raise commands.ConversionError(
                    f'Failed to convert "{message}" to Stealed Emoji Data.', err.__cause__
                )
            self.name = emote_name
            try:
                self.id = int(emote_id)
            except ValueError as err:
                raise commands.ConversionError(
                    f'Failed to convert "{message}" to Stealed Emoji Data.', err.__cause__
                )
            return self
        elif argument.startswith("<a:") and argument.endswith(">"):
            message = argument[1:-1]
            try:
                _, emote_name, emote_id = message.split(":")
            except ValueError as err:
                raise commands.ConversionError(
                    f'Failed to convert "{message}" to Stealed Emoji Data.', err.__cause__
                )
            self.name = emote_name
            try:
                self.id = int(emote_id)
            except ValueError as err:
                raise commands.ConversionError(
                    f'Failed to convert "{message}" to Stealed Emoji Data.', err.__cause__
                )
            self.animated = True
            return self
        else:
            raise commands.ConversionError(
                f'Failed to convert "{argument}" to Stealed Emoji Data.', "Missing emote"
            )

    @property
    def url(self) -> str:
        """Return URL formatted data for the Stealed Emote"""
        _fmt = "gif" if self.animated else "png"
        return f"https://cdn.discordapp.com/emojis/{self.id}.{_fmt}"

    async def read(self, bot: "naoTimesBot" = None) -> bytes:
        """Read from URL to bytes data.

        :raises ValueError: If ID not set
        :return: Emoji data in bytes
        :rtype: bytes
        """
        if hasattr(self, "_cached_emote_data") and self._cached_emote_data is not None:
            return self._cached_emote_data
        if self.id is None:
            raise ValueError("Failed to read since there's no data to read.")
        if self._bot is None and bot is None:
            error_msg = "Failed to read, since there's no bot data in this class\n"
            error_msg += "Please pass the bot into this read function"
            raise ValueError(error_msg)
        elif self._bot is None and bot is not None:
            self._bot = bot

        async with self._bot.aiosession.get(self.url) as resp:
            if resp.status != 200:
                if resp.status == 404:
                    raise FileNotFoundError("Failed to read data from URL, emote possibly deleted.")
                raise ConnectionError(f"Failed to read data from URL, got status: {resp.status}")
            results = await resp.read()
        self._cached_emote_data = results
        return results


class ShowtimesConverter(commands.Converter[List[ShowtimesProject]]):
    """
    A converter class that will try to match the a title
    of a Showtimes project.
    ---

    Example Usage:
    ```py
        async def showtimes_cmd(self, ctx, *, titles: ShowtimesConverter):
            print(titles)
    ```
    """

    async def convert(self, ctx: naoTimesContext, argument: str):
        _bot: "naoTimesBot" = ctx.bot
        if not argument:
            return None
        guild = ctx.guild
        if guild is None:
            return None
        fetch_sh = await _bot.showqueue.fetch_database(guild.id)
        if fetch_sh is None:
            return None

        matched_list = fetch_sh.find_projects(argument)
        return matched_list
