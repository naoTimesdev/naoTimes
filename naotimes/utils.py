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
import functools
import logging
import os
import pathlib
import platform
import random
import sys
from collections.abc import Mapping, Sequence
from string import ascii_lowercase, ascii_uppercase, digits
from time import struct_time
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar, cast

import aiofile
import arrow
import discord
import orjson
from discord import __version__ as discord_ver
from discord.ext import commands

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from concurrent.futures import ThreadPoolExecutor

    from .bot import naoTimesBot

FuncT = TypeVar("FuncT")
ItemT = TypeVar("ItemT")

WalkValue: TypeAlias = (
    bool | int | float | str | list["WalkValue"] | tuple["WalkValue", ...] | dict[str | int, "WalkValue"] | None
)

__all__ = (
    "FIREFOX_USER_AGENT",
    "AttributeDict",
    "blocking_read_files",
    "blocking_write_files",
    "bold",
    "complex_walk",
    "cutoff_text",
    "explode_filepath_into_pieces",
    "generate_custom_code",
    "get_current_time",
    "get_indexed",
    "get_server",
    "get_version",
    "italic",
    "linkify",
    "list_or_none",
    "month_in_text",
    "prefixes_with_data",
    "quote",
    "quoteblock",
    "read_files",
    "split_search_id",
    "str_or_none",
    "sync_wrap",
    "time_struct_dt",
    "traverse",
    "try_catch_valid",
    "try_catch_valid_sync",
    "underline",
    "write_files",
)

FIREFOX_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0"

main_log = logging.getLogger("naoTimes.Utils")


def sync_wrap(func):
    @functools.wraps(func)
    async def run(
        *args: Any,
        loop: AbstractEventLoop | None = None,
        executor: ThreadPoolExecutor | None = None,
        **kwargs: Any,
    ):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)

    return run


# Markdown helper
def bold(data: str, italic: bool = False) -> str:
    if italic:
        return f"***{data}***"
    return f"**{data}**"


def italic(data: str) -> str:
    return f"*{data}*"


def underline(data: str) -> str:
    return f"__{data}__"


def linkify(url, title: str | None = None) -> str:
    t = url
    if isinstance(title, str):
        t = title
    return f"[{t}]({url})"


def quote(data: str, triple: bool = False, code: str | None = None) -> str:
    if triple:
        if code:
            return f"```{code}\n{data}\n```"
        return f"```\n{data}\n```"
    return f"`{data}`"


quoteblock = functools.partial(quote, triple=True)


def traverse(data: dict | list, notations: str) -> Any:
    for nots in notations.split("."):
        if nots.isdigit():
            nots = int(nots, 10)  # type: ignore
        data = data[nots]  # type: ignore
    return data


def get_indexed(data: Sequence[ItemT], n: int) -> ItemT | None:
    if not data:
        return None
    try:
        return data[n]
    except (ValueError, IndexError):
        return None


def complex_walk(dictionary: Mapping[Any, Any] | list[Any] | tuple[Any, ...], paths: str) -> WalkValue | None:
    if not dictionary:
        return None
    expanded_paths = paths.split(".")
    skip_it = False
    current: Any = dictionary
    for n, path in enumerate(expanded_paths):
        if skip_it:
            skip_it = False
            continue
        path_key: str | int = int(path) if path.isdigit() else path
        if path == "*" and isinstance(current, list):
            new_concat: list[WalkValue] = []
            next_path = get_indexed(expanded_paths, n + 1)
            if next_path is None:
                return None
            skip_it = True
            for content in current:
                if not isinstance(content, Mapping):
                    continue
                try:
                    new_concat.append(content[next_path])
                except (TypeError, ValueError, IndexError, KeyError, AttributeError):
                    pass
            if len(new_concat) < 1:
                return new_concat
            current = new_concat
            continue
        try:
            if isinstance(current, Mapping):
                current = current[path_key]
            elif isinstance(current, (list, tuple)):
                if not isinstance(path_key, int):
                    return None
                current = current[path_key]
            else:
                return None
        except (TypeError, ValueError, IndexError, KeyError, AttributeError):
            return None
    return cast(WalkValue, current)


def cutoff_text(text: str, max_len: int) -> str:
    extend = " [...]"
    max_len -= len(extend)
    max_len -= 2
    if len(text) > max_len:
        text = text[:max_len] + extend
    return text


def explode_filepath_into_pieces(filepath: str) -> list[str]:
    """Split a filepath into pieces
    ---
    :param filepath: file path
    :type filepath: str
    :return: file path pieces
    :rtype: list
    """
    filepath = filepath.replace("\\", "/")
    return filepath.split("/")


def str_or_none(text: str | bytes | None, default: str | None = "") -> str | None:
    if text is None:
        return default
    if isinstance(text, bytes):
        return text.decode("utf-8")
    return text


def list_or_none(lists: list[ItemT] | None, default: list[ItemT] = []) -> list[ItemT]:
    if not isinstance(lists, list):
        return default
    return lists


def split_search_id(dataset: list, needed_id: str, matching_id: int, sort=False):
    """
    A not so fast searching algorithm
    """

    def to_int(x):
        if isinstance(x, str):
            x = int(x)
        return x

    if sort:
        dataset.sort(key=lambda x: x[sort])

    mid_num = len(dataset) // 2
    mid_data = dataset[mid_num]
    match_data = to_int(mid_data[needed_id])
    if match_data == matching_id:
        return mid_data
    if match_data > matching_id:
        for data in dataset[:mid_num]:
            if to_int(data[needed_id]) == matching_id:
                return data
    elif match_data < matching_id:
        for data in dataset[mid_num:]:
            if to_int(data[needed_id]) == matching_id:
                return data
    for data in dataset:
        if to_int(data[needed_id]) == matching_id:
            return data
    return None


def try_catch_valid_sync(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
        return True
    except Exception:
        return False


async def try_catch_valid(func, *args, **kwargs):
    try:
        await func(*args, **kwargs)
        return True
    except Exception:
        return False


def get_server() -> str:
    """Generate a server information.

    :return: server info
    :rtype: str
    """
    uname = platform.uname()
    fmt_plat = f"OS: {uname.system} {uname.release} v{uname.version}\n"
    fmt_plat += f"CPU: {uname.processor} ({os.cpu_count()} threads)\n"
    fmt_plat += f"PID: {os.getpid()}"
    return quote(fmt_plat, True, "py")


def get_version() -> str:
    """Generate Python and Discord.py version

    :return: python and discord.py version
    :rtype: str
    """
    py_ver = sys.version
    return quote(f"Python: {py_ver}\nndiscord.py: {discord_ver}", True, "py")


def prefixes_with_data(
    bot: naoTimesBot,
    context: discord.Message | discord.TextChannel | discord.Guild | commands.Context,
    prefixes_data: dict,
    default: str,
) -> list:
    """
    A modified version of discord.ext.command.when_mentioned_or
    """
    pre_data = []
    pre_data.append(default)

    guild: discord.Guild | None = None
    if isinstance(context, (discord.Message, discord.TextChannel)):
        guild = context.guild
    elif isinstance(context, discord.Guild):
        guild = context
    elif isinstance(context, commands.Context):
        guild = context.guild

    if guild is not None and hasattr(guild, "id"):
        srv_pre = prefixes_data.get(str(guild.id))
        if srv_pre:
            pre_data.remove(default)
            pre_data.append(srv_pre)
    if "ntd." not in pre_data:
        pre_data.append("ntd.")
    bot_user = bot.user
    if bot_user is None:
        raise AttributeError("Bot user is not available before login")
    pre_data.extend([bot_user.mention + " ", "<@!%s> " % bot_user.id])

    return pre_data


async def read_files(fpath: str) -> Any:
    """Read a files
    ---

    :param fpath: file path
    :type fpath: str
    :return: file contents, parsed with ujson if it's list or dict
             if file doesn't exist, return None
    :rtype: Any
    """
    loop = asyncio.get_event_loop()
    is_file = await loop.run_in_executor(None, os.path.isfile, fpath)
    if not is_file:
        return None
    async with aiofile.async_open(fpath, "r", encoding="utf-8") as fp:
        data = await fp.read()
    try:
        data = orjson.loads(data)
    except ValueError:
        pass
    return data


async def write_files(data: Any, fpath: str):
    """Write data to files
    ---

    :param data: data to write, can be any
    :type data: Any
    :param fpath: file path
    :type fpath: str
    """
    if isinstance(data, (dict, list, tuple)):
        data = orjson.dumps(
            data,
            option=orjson.OPT_INDENT_2,
        )
    elif isinstance(data, int):
        data = str(data)
    wmode = "w"
    if isinstance(data, bytes):
        wmode = "wb"
    async with aiofile.async_open(fpath, wmode, encoding="utf-8") as fpw:
        await fpw.write(data)


def blocking_read_files(fpath: str) -> Any:
    """Read a files with blocking
    ---

    :param fpath: file path
    :type fpath: str
    :return: file contents, parsed with ujson if it's list or dict
             if file doesn't exist, return None
    :rtype: Any
    """
    if not pathlib.Path(fpath).is_file():
        return None
    with pathlib.Path(fpath).open("r", encoding="utf-8") as fp:
        data = fp.read()
    try:
        data = orjson.loads(data)
    except ValueError:
        pass
    return data


def blocking_write_files(data: Any, fpath: str):
    """Write data to files with blocking
    ---

    :param data: data to write, can be any
    :type data: Any
    :param fpath: file path
    :type fpath: str
    """
    if isinstance(data, (dict, list, tuple)):
        data = orjson.dumps(
            data,
            option=orjson.OPT_INDENT_2,
        )
    elif isinstance(data, int):
        data = str(data)
    wmode = "w"
    if isinstance(data, bytes):
        wmode = "wb"
    with pathlib.Path(fpath).open(wmode, encoding="utf-8") as fpw:
        fpw.write(data)


def generate_custom_code(length: int = 8, include_numbers: bool = False, include_uppercase: bool = False) -> str:
    """Generate a random custom code to be used by anything.

    :param length: int: the code length
    :param include_numbers: bool: include numbers in generated code or not.
    :param include_uppercase: bool: include uppercased letters in generated code or not.
    :return: a custom generated string that could be used for anything.
    :rtype: str
    """
    letters_used = ascii_lowercase
    if include_numbers:
        letters_used += digits
    if include_uppercase:
        letters_used += ascii_uppercase
    generated = "".join([random.choice(letters_used) for _ in range(length)])  # nosec
    return generated


def month_in_text(t: int) -> str:
    tdata = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]
    return tdata[t - 1]


def get_current_time(locale: str = "id") -> str:
    """
    Return current time in `DD Month YYYY HH:MM TZ (+X)` format
    """
    current_time = arrow.now(tz="Asia/Jakarta")
    return current_time.format("DD MMMM YYYY HH:mm [UTC]ZZ (+7)", locale)


def time_struct_dt(time_struct: struct_time) -> tuple[str, arrow.Arrow]:
    if not isinstance(time_struct, struct_time):
        return time_struct
    yymmdd_fmt = []
    mm_norm = None
    hh_norm = None
    hhmmss_fmt = []
    try:
        dd = time_struct.tm_mday
        yymmdd_fmt.append(str(dd).zfill(2))
    except AttributeError:
        pass
    try:
        mm = time_struct.tm_mon
        mm_norm = str(mm).zfill(2)
        yymmdd_fmt.append(month_in_text(mm))
    except AttributeError:
        pass
    try:
        yyyy = time_struct.tm_year
        yymmdd_fmt.append(str(yyyy))
    except AttributeError:
        pass

    try:
        hh = time_struct.tm_hour
        hh_norm = hh
        hhmmss_fmt.append(str(hh + 7).zfill(2))
    except AttributeError:
        pass
    try:
        mm = time_struct.tm_min
        hhmmss_fmt.append(str(mm).zfill(2))
    except AttributeError:
        pass
    try:
        ss = time_struct.tm_sec
        hhmmss_fmt.append(str(ss).zfill(2))
    except AttributeError:
        pass

    strftime_str = " ".join(yymmdd_fmt)
    strftime_str += " " + ":".join(hhmmss_fmt)
    dt_data = arrow.get(f"{yymmdd_fmt[2]}-{mm_norm}-{yymmdd_fmt[0]} {hh_norm}:{hhmmss_fmt[1]}:{hhmmss_fmt[2]}")
    return strftime_str, dt_data


def hex_to_color(hex_str: str) -> discord.Colour:
    hex_str = hex_str.removeprefix("#")
    hex_str = hex_str.upper()
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return discord.Colour.from_rgb(r, g, b)


def rgb_to_color(r: int, g: int, b: int) -> discord.Colour:
    return discord.Colour.from_rgb(r, g, b)


def verify_port_open(port: int, host: str = "0.0.0.0") -> bool:
    """Check that a port is free by trying to bind to it.

    Unlike scanning connections with psutil, this needs no elevated permission (macOS refuses
    ``psutil.net_connections()`` for non-root users).
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if os.name == "posix":
            # Don't let lingering TIME_WAIT sockets report the port as taken.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


class AttributeDict(dict):
    """An attribute-based dictionary."""

    def __init__(self, *args, **kwargs):
        def from_nested_dict(data):
            """Construct nested AttributeDict from nested dictionaries."""
            if not isinstance(data, (dict, list, tuple)):
                return data
            else:
                if isinstance(data, dict):
                    return AttributeDict({k: from_nested_dict(data[k]) for k in data.keys()})
                else:
                    return [from_nested_dict(item) for item in data]

        super().__init__(*args, **kwargs)
        self.__dict__ = self

        for key in self.keys():
            self[key] = from_nested_dict(self[key])

    def __repr__(self):
        concat_data = []
        for key in self.keys():
            concat_data.append(f"{key}={self[key]!r}")
        return f"<AttributeDict {' '.join(concat_data)}>"
