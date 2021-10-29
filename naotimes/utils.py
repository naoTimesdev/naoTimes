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
import functools
import logging
import os
import platform
import random
import sys
from string import ascii_lowercase, ascii_uppercase, digits
from time import struct_time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, TypeVar, Union

import aiofiles
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

__all__ = (
    "sync_wrap",
    "bold",
    "italic",
    "underline",
    "linkify",
    "traverse",
    "quote",
    "quoteblock",
    "get_indexed",
    "complex_walk",
    "cutoff_text",
    "explode_filepath_into_pieces",
    "str_or_none",
    "list_or_none",
    "split_search_id",
    "get_server",
    "get_version",
    "prefixes_with_data",
    "read_files",
    "write_files",
    "blocking_read_files",
    "blocking_write_files",
    "generate_custom_code",
    "month_in_text",
    "get_current_time",
    "time_struct_dt",
    "AttributeDict",
)

__CHROME_UA__ = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"  # noqa: E501

main_log = logging.getLogger("naoTimes.Utils")


def sync_wrap(func):
    @functools.wraps(func)
    async def run(
        *args: List[Any],
        loop: Optional[AbstractEventLoop] = None,
        executor: Optional[ThreadPoolExecutor] = None,
        **kwargs: Dict[str, Any],
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


def linkify(url, title: str = None) -> str:
    t = url
    if isinstance(title, str):
        t = title
    return f"[{t}]({url})"


def quote(data: str, triple: bool = False, code: str = None) -> str:
    if triple:
        if code:
            return f"```{code}\n{data}\n```"
        return f"```\n{data}\n```"
    return f"`{data}`"


quoteblock = functools.partial(quote, triple=True)


def traverse(data: Union[dict, list], notations: str) -> Any:
    for nots in notations.split("."):
        if nots.isdigit():
            nots = int(nots, 10)  # type: ignore
        data = data[nots]  # type: ignore
    return data


def get_indexed(data: list, n: int):
    if not data:
        return None
    try:
        return data[n]
    except (ValueError, IndexError):
        return None


def complex_walk(dictionary: Union[dict, list], paths: str):
    if not dictionary:
        return None
    expanded_paths = paths.split(".")
    skip_it = False
    for n, path in enumerate(expanded_paths):
        if skip_it:
            skip_it = False
            continue
        if path.isdigit():
            path = int(path)  # type: ignore
        if path == "*" and isinstance(dictionary, list):
            new_concat = []
            next_path = get_indexed(expanded_paths, n + 1)
            if next_path is None:
                return None
            skip_it = True
            for content in dictionary:
                try:
                    new_concat.append(content[next_path])
                except (TypeError, ValueError, IndexError, KeyError, AttributeError):
                    pass
            if len(new_concat) < 1:
                return new_concat
            dictionary = new_concat
            continue
        try:
            dictionary = dictionary[path]  # type: ignore
        except (TypeError, ValueError, IndexError, KeyError, AttributeError):
            return None
    return dictionary


def cutoff_text(text: str, max_len: int) -> str:
    extend = " [...]"
    max_len -= len(extend)
    max_len -= 2
    if len(text) > max_len:
        text = text[:max_len] + extend
    return text


def explode_filepath_into_pieces(filepath: str) -> List[str]:
    """Split a filepath into pieces
    ---
    :param filepath: file path
    :type filepath: str
    :return: file path pieces
    :rtype: list
    """
    filepath = filepath.replace("\\", "/")
    return filepath.split("/")


def str_or_none(text: Union[str, bytes, None], default: str = ""):
    if text is None:
        return default
    if isinstance(text, bytes):
        return text.decode("utf-8")
    return text


def list_or_none(lists: Union[list, None], default: list = []):
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
    context: Union[discord.Message, discord.TextChannel, discord.Guild, commands.Context],
    prefixes_data: dict,
    default: str,
) -> list:
    """
    A modified version of discord.ext.command.when_mentioned_or
    """
    pre_data = []
    pre_data.append(default)

    guild: discord.Guild = None
    if isinstance(context, (discord.Message, discord.TextChannel)):
        if hasattr(context, "guild"):
            try:
                guild = context.guild
            except AttributeError:
                pass
    elif isinstance(context, discord.Guild):
        guild = context
    elif isinstance(context, commands.Context):
        if hasattr(context, "guild"):
            try:
                guild = context.guild
            except AttributeError:
                pass
        elif hasattr(context, "message"):
            try:
                if hasattr(context.message, "guild"):
                    guild = context.message.guild
            except AttributeError:
                pass
    elif hasattr(context, "guild"):
        guild = context.guild
    elif hasattr(context, "message"):
        msg = context.message
        if hasattr(msg, "guild"):
            guild = msg.guild

    if guild is not None and hasattr(guild, "id"):
        srv_pre = prefixes_data.get(str(guild.id))
        if srv_pre:
            pre_data.remove(default)
            pre_data.append(srv_pre)
    if "ntd." not in pre_data:
        pre_data.append("ntd.")
    pre_data.extend([bot.user.mention + " ", "<@!%s> " % bot.user.id])

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
    if not os.path.isfile(fpath):
        return None
    async with aiofiles.open(fpath, "r", encoding="utf-8") as fp:
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
            option=orjson.OPT_INDEN_2,
        )
    elif isinstance(data, int):
        data = str(data)
    wmode = "w"
    if isinstance(data, bytes):
        wmode = "wb"
    async with aiofiles.open(fpath, wmode, encoding="utf-8") as fpw:  # type: ignore
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
    if not os.path.isfile(fpath):
        return None
    with open(fpath, "r", encoding="utf-8") as fp:
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
            option=orjson.OPT_INDEN_2,
        )
    elif isinstance(data, int):
        data = str(data)
    wmode = "w"
    if isinstance(data, bytes):
        wmode = "wb"
    with open(fpath, wmode, encoding="utf-8") as fpw:
        fpw.write(data)


def generate_custom_code(
    length: int = 8, include_numbers: bool = False, include_uppercase: bool = False
) -> str:
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


def get_current_time() -> str:
    """
    Return current time in `DD Month YYYY HH:MM TZ (+X)` format
    """
    current_time = arrow.now(tz="Asia/Jakarta")
    return current_time.format("DD MMMM YYYY HH:mm [UTC]ZZ (+7)", "id")


def time_struct_dt(time_struct: struct_time) -> Tuple[str, arrow.Arrow]:
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
    dt_data = arrow.get(
        f"{yymmdd_fmt[2]}-{mm_norm}-{yymmdd_fmt[0]} {hh_norm}:{hhmmss_fmt[1]}:{hhmmss_fmt[2]}"
    )
    return strftime_str, dt_data


def hex_to_color(hex_str: str) -> discord.Colour:
    hex_str = hex_str.replace("#", "").upper()
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return discord.Colour.from_rgb(r, g, b)


def rgb_to_color(r: int, g: int, b: int) -> discord.Colour:
    return discord.Colour.from_rgb(r, g, b)


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

        super(AttributeDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

        for key in self.keys():
            self[key] = from_nested_dict(self[key])

    def __repr__(self):
        concat_data = []
        for key in self.keys():
            concat_data.append(f"{key}={self[key]!r}")
        return f"<AttributeDict {' '.join(concat_data)}>"
