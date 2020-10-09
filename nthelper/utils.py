# -*- coding: utf-8 -*-

import asyncio
import functools
import logging
import os
import platform
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from string import ascii_lowercase, ascii_uppercase, digits
from typing import Any, Dict, List, Tuple, Union

import aiofiles
import aiohttp
import discord
import ujson
from discord import __version__ as discord_ver
from discord.ext import commands

__version__ = "2.0.1a"

main_log = logging.getLogger("nthelper.utils")
__CHROME_UA__ = ""


def sync_wrap(func):
    @asyncio.coroutine
    @functools.wraps(func)
    def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = functools.partial(func, *args, **kwargs)
        return loop.run_in_executor(executor, pfunc)

    return run


def get_server() -> str:
    """Generate a server information.

    :return: server info
    :rtype: str
    """
    uname = platform.uname()
    fmt_plat = "```py\nOS: {0.system} {0.release} v{0.version}\nCPU: {0.processor} ({1} threads)\nPID: {2}\n```".format(  # noqa: E501
        uname, os.cpu_count(), os.getpid()
    )
    return fmt_plat


def get_version() -> str:
    """Generate Python and Discord.py version

    :return: python and discord.py version
    :rtype: str
    """
    py_ver = sys.version
    return "```py\nDiscord.py v{d}\nPython {p}\n```".format(d=discord_ver, p=py_ver)


def prefixes_with_data(bot, message: discord.Message, prefixes_data: dict, default: str) -> list:
    """
    A modified version of discord.ext.command.when_mentioned_or
    """
    pre_data = []
    pre_data.append(default)

    if hasattr(message, "guild"):
        server = message.guild
        if server:
            srv_pre = prefixes_data.get(str(server.id))
            if srv_pre:
                pre_data.remove(default)
                pre_data.append(srv_pre)
    if "ntd." not in pre_data:
        pre_data.append("ntd.")
    pre_data.extend([bot.user.mention + " ", "<@!%s> " % bot.user.id])

    return pre_data


async def ping_website(url: str) -> Tuple[bool, float]:
    """Ping a website and return how long it takes
    ---

    :param url: Website to ping
    :type url: str
    :return: return a bool if ping success or not and time taken in ms.
    :rtype: Tuple[bool, float]
    """

    async def _internal_pinger(url: str):
        """Internal worker for the ping process."""
        try:
            async with aiohttp.ClientSession() as sesi:
                async with sesi.get(url) as resp:
                    await resp.text()
        except aiohttp.ClientError:
            return False
        return True

    t1 = time.perf_counter()
    try:
        # Wrap it around asyncio.wait_for to make sure it doesn't wait until 10+ secs
        res = await asyncio.wait_for(_internal_pinger(url), timeout=10.0)
        t2 = time.perf_counter()
    except asyncio.TimeoutError:
        return False, 99999.0
    return res, (t2 - t1) * 1000


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
        data = ujson.loads(data)
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
        data = ujson.dumps(
            data, ensure_ascii=False, encode_html_chars=False, escape_forward_slashes=False, indent=4,
        )
    elif isinstance(data, int):
        data = str(data)
    wmode = "w"
    if isinstance(data, bytes):
        wmode = "wb"
    async with aiofiles.open(fpath, wmode, encoding="utf-8") as fpw:
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
        data = ujson.loads(data)
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
        data = ujson.dumps(
            data, ensure_ascii=False, encode_html_chars=False, escape_forward_slashes=False, indent=4,
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


def get_current_time() -> str:
    """
    Return current time in `DD Month YYYY HH:MM TZ (+X)` format
    """
    current_time = datetime.now(timezone(timedelta(hours=7)))

    def month_in_idn(datetime_fmt):
        x = datetime_fmt.strftime("%B")
        tl_map = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": None,
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": None,
            "October": "Oktober",
            "November": None,
            "December": "Desember",
        }
        tled = tl_map.get(x, x)
        if tled is None:
            tled = x
        return tled

    d = current_time.strftime("%d")
    m = month_in_idn(current_time)
    rest = current_time.strftime("%Y %H:%M %Z (+7)")

    return "{} {} {}".format(d, m, rest)


# Message utils
async def send_timed_msg(ctx: Any, message: str, delay: Union[int, float] = 5):
    """Send a timed message to a discord channel.
    ---

    :param ctx: context manager of the channel
    :type ctx: Any
    :param message: message to send
    :type message: str
    :param delay: delay before deleting the message, defaults to 5
    :type delay: Union[int, float], optional
    """
    main_log.debug(f"sending message with {delay} delay")
    msg = await ctx.send(message)
    await asyncio.sleep(delay)
    await msg.delete()


async def confirmation_dialog(bot, ctx, message: str) -> bool:
    """Send a confirmation dialog.

    :param bot: the bot itself
    :type bot: naoTimesBot
    :param ctx: context manager of the channel
    :type ctx: Any
    :param message: message to verify
    :type message: str
    :return: a true or false using the reaction picked.
    """
    dis_msg = await ctx.send(message)
    to_react = ["✅", "❌"]
    for react in to_react:
        await dis_msg.add_reaction(react)

    def check_react(reaction, user):
        if reaction.message.id != dis_msg.id:
            return False
        if user != ctx.message.author:
            return False
        if str(reaction.emoji) not in to_react:
            return False
        return True

    dialog_tick = True
    while True:
        res, user = await bot.wait_for("reaction_add", check=check_react)
        if user != ctx.message.author:
            pass
        elif "✅" in str(res.emoji):
            await dis_msg.delete()
            break
        elif "❌" in str(res.emoji):
            dialog_tick = False
            await dis_msg.delete()
            break
    return dialog_tick


class HelpGenerator:
    """A class to generate a help
    -----

    Example:
    ```
    # Assuming this is on a async function of a command
    helpcmd = HelpGenerator(bot, "add", desc="do an addition")
    await helpcmd.generate_field(
        "add"
        [
            {"name": "num1", "type": "r"},
            {"name": "num2", "type": "r"},
        ],
        desc="Do an addition between `num1` and `num2`",
        examples=["1 1", "2 4"],
        inline=True
    )
    await helpcmd.generate_aliases(["tambah", "plus"], False)
    await ctx.send(embed=helpcmd()) # or await ctx.send(embed=helpcmd.get())
    ```
    """

    def __init__(self, bot: commands.Bot, cmd_name: str = "", desc: str = "", color=None):
        self.bot: commands.Bot = bot
        self.logger = logging.getLogger("nthelper.utils.HelpGenerator")

        self._ver = self.bot.semver
        self._pre = self.bot.prefix
        self._no_pre = False

        if cmd_name.endswith("[*]"):
            cmd_name = cmd_name.replace("[*]", "").strip()
            self._no_pre = True
        self.cmd_name = cmd_name
        self.color = color
        if self.color is None:
            self.color = 0xCEBDBD  # rgb(206, 189, 189) / HEX #CEBDBD
        self.desc_cmd = desc

        self.embed: discord.Embed = None
        self.__start_generate()

    def __call__(self) -> discord.Embed:
        if not isinstance(self.embed, discord.Embed):
            self.logger.warn("Embed are not generated yet.")
            raise ValueError("Embed are not generated yet.")
        self.logger.info("sending embed results")
        return self.embed

    def get(self) -> discord.Embed:
        """Return the final embed.
        -----

        :raises ValueError: If the embed attrs is empty
        :return: Final embed
        :rtype: discord.Embed
        """
        if not isinstance(self.embed, discord.Embed):
            self.logger.warn("Embed are not generated yet.")
            raise ValueError("Embed are not generated yet.")
        self.logger.info("sending embed results")
        return self.embed

    def __encapsule(self, name: str, t: str) -> str:
        """Encapsulate the command name with <> or []
        -----

        This is for internal use only

        :param name: command name
        :type name: str
        :param t: command type (`r` or `o`)
                  `r` for required command.
                  `o` for optional command.
        :type t: str
        :return: encapsuled command name
        :rtype: str
        """
        tt = {"r": ["`<", ">`"], "o": ["`[", "]`"]}
        pre, end = tt.get(t, ["`", "`"])
        return pre + name + end

    def __start_generate(self):
        """
        Start generating embed
        """
        self.logger.info(f"start generating embed for: {self.cmd_name}")
        embed = discord.Embed(color=self.color)
        embed.set_author(
            name=self.bot.user.display_name, icon_url=self.bot.user.avatar_url,
        )
        embed.set_footer(text=f"Dibuat oleh N4O#8868 | Versi {self._ver}")
        title = "Bantuan Perintah"
        if self.cmd_name != "":
            title += " ("
            if not self._no_pre:
                title += self._pre
            title += f"{self.cmd_name})"
        embed.title = title
        if self.desc_cmd != "":
            embed.description = self.desc_cmd
        self.embed = embed

    async def generate_field(
        self,
        cmd_name: str,
        opts: List[Dict[str, str]] = [],
        desc: str = "",
        examples: List[str] = [],
        inline: bool = False,
        use_fullquote: bool = False,
    ):
        """Generate a help fields
        ---

        :param cmd_name: command name
        :type cmd_name: str
        :param opts: command options, defaults to []
        :type opts: List[Dict[str, str]], optional
        :param desc: command description, defaults to ""
        :type desc: str, optional
        :param examples: command example, defaults to []
        :type examples: List[str], optional
        :param inline: put field inline with previous field, defaults to False
        :type inline: bool, optional
        :param use_fullquote: Use block quote, defaults to False
        :type use_fullquote: bool, optional
        """
        self.logger.debug(f"generating field: {cmd_name}")
        gen_name = self._pre + cmd_name
        final_desc = ""
        if desc:
            final_desc += desc
            final_desc += "\n"
        opts_list = []
        if opts:
            for opt in opts:
                a_t = opt["type"]
                a_n = opt["name"]
                try:
                    a_d = opt["desc"]
                except KeyError:
                    a_d = ""
                capsuled = self.__encapsule(a_n, a_t)
                opts_list.append(capsuled)

                if a_d:
                    if a_t == "o":
                        if final_desc != "":
                            final_desc += "\n"
                        final_desc += capsuled
                        final_desc += " itu **`[OPSIONAL]`**"
                    final_desc += f"\n{a_d}"
        if final_desc == "":
            final_desc = cmd_name

        if opts_list:
            opts_final = " ".join(opts_list)
            gen_name += f" {opts_final}"

        if use_fullquote:
            final_desc = "```\n" + final_desc + "\n```"

        self.embed.add_field(
            name=gen_name, value=final_desc, inline=inline,
        )
        if examples:
            examples = [f"- **{self._pre}{cmd_name}** {ex}" for ex in examples]
            self.embed.add_field(
                name="Contoh", value="\n".join(examples), inline=False,
            )

    async def generate_aliases(self, aliases: List[str] = [], add_note: bool = True):
        """Generate end part and aliases
        ---

        :param aliases: aliases for command, defaults to []
        :type aliases: List[str], optional
        :param add_note: add ending note or not, defaults to True
        :type add_note: bool, optional
        """
        self.logger.debug(f"generating for {self.cmd_name}")
        aliases = [f"{self._pre}{alias}" for alias in aliases]
        if aliases:
            self.embed.add_field(name="Aliases", value=", ".join(aliases), inline=False)
        if add_note:
            self.embed.add_field(
                name="*Note*",
                value="Semua perintah memiliki bagian bantuannya sendiri!\n"
                f"Gunakan `{self._pre}help [nama perintah]` untuk melihatnya!",
                inline=False,
            )
