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
from inspect import iscoroutinefunction
from string import ascii_lowercase, ascii_uppercase, digits
from typing import Any, Dict, List, Tuple, Union

import aiofiles
import aiohttp
import discord
from discord import __version__ as discord_ver
from discord.ext import commands

import ujson

__version__ = "2.0.2"

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


# Markdown helper
def bold(data: str, italic: bool = False) -> str:
    if italic:
        return "***" + data + "***"
    return "**" + data + "**"


def italic(data: str) -> str:
    return "*" + data + "*"


def underline(data: str) -> str:
    return "__" + data + "__"


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
        commit = self.bot.get_commit
        if commit["hash"] is not None:
            self._ver += f" ({commit['hash']})"
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
            self.logger.warning("Embed are not generated yet.")
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
            self.logger.warning("Embed are not generated yet.")
            raise ValueError("Embed are not generated yet.")
        self.logger.info("sending embed results")
        return self.embed

    @staticmethod
    def __encapsule(name: str, t: str) -> str:
        """Encapsulate the command name with <> or []
        -----

        This is for internal use only

        :param name: command name
        :type name: str
        :param t: command type (`r` or `o`, or `c`)
                  `r` for required command.
                  `o` for optional command.
        :type t: str
        :return: encapsuled command name
        :rtype: str
        """
        tt = {"r": ["`<", ">`"], "o": ["`[", "]`"], "c": ["`[", "]`"]}
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

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.animated: bool = kwargs.get("animated", False)
        self._cached_emote_data: bytes

    def __str__(self):
        if self.animated:
            return "<a:{0.name}:{0.id}>".format(self)
        return "<:{0.name}:{0.id}>".format(self)

    def __repr__(self):
        return "<StealedEmote id={0.id} name={0.name!r} animated={0.animated}>".format(self)

    def __hash__(self):
        return self.id >> 22

    async def convert(self, ctx, argument: str):
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

    async def read(self) -> bytes:
        """Read from URL to bytes data.

        :raises ValueError: If ID not set
        :return: Emoji data in bytes
        :rtype: bytes
        """
        if self.id is None:
            raise ValueError("Failed to read since there's no data to read.")
        if hasattr(self, "_cached_emote_data") and self._cached_emote_data is not None:
            return self._cached_emote_data

        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/{__version__} (https://github.com/noaione/naoTimes)"}
        ) as session:
            async with session.get(self.url) as resp:
                if resp.status != 200:
                    if resp.status == 404:
                        raise FileNotFoundError("Failed to read data from URL, emote possibly deleted.")
                    raise ConnectionError(f"Failed to read data from URL, got status: {resp.status}")
                results = await resp.read()
        self._cached_emote_data = results
        return results


class PaginatorNoGenerator(Exception):
    pass


class PaginatorNoMoreEmotes(Exception):
    pass


class PaginatorHandlerNoResult(Exception):
    pass


class DiscordPaginator:
    """A helper class to generate paginating pages utilizing Discord Embed or something.

    This is a bad code, dont use it anywhere else except for this bot.
    """

    def __init__(self, bot: commands.Bot, ctx: commands.Context, extra_emotes=[], no_paginate=False):
        self.emotes_map = {k: None for k in extra_emotes}
        self.bot = bot
        self.ctx = ctx
        self.logger = logging.getLogger("nthelper.utils.DiscordPaginator")
        self._generator = None
        self._generator_num = False
        self.remove_at_check = True
        self.break_on_no_results = False
        self._no_paginate = no_paginate

    def checker(self):
        if self.remove_at_check:
            self.remove_at_check = False
        else:
            self.remove_at_check = True

    def breaker(self):
        if self.break_on_no_results:
            self.break_on_no_results = False
        else:
            self.break_on_no_results = True

    async def _maybe_asyncute(self, cb, *args, **kwargs):
        real_func = cb
        if hasattr(real_func, "func"):
            real_func = cb.func
        if iscoroutinefunction(real_func):
            return await cb(*args, **kwargs)
        else:
            return cb(*args, **kwargs)

    def add_handler(self, callback, generator=None):
        empty_loc = None
        for emote, handler in self.emotes_map.items():
            if handler is None:
                empty_loc = emote

        if empty_loc is None:
            raise PaginatorNoMoreEmotes("There's no more emote available to be added to the handler.")

        self.emotes_map[empty_loc] = {"check": callback, "gen": generator}

    def set_handler(self, position, callback, generator=None):
        emote_sets = list(self.emotes_map.keys())
        if position >= len(emote_sets):
            raise PaginatorNoMoreEmotes("Emote position went pass the limit")

        self.emotes_map[emote_sets[position]] = {"check": callback, "gen": generator}

    def set_generator(self, generator, return_num=False):
        if not callable(generator):
            raise TypeError
        self._generator = generator
        self._generator_num = return_num

    @staticmethod
    def _gen_kwargs(data: Any) -> Dict[str, Any]:
        raw_msg = embed = None
        if isinstance(data, (list, tuple)):
            if len(data) == 2:
                raw_msg = data[0]
                embed = data[1]
        elif isinstance(data, discord.Embed):
            embed = data
        elif isinstance(data, (str, int)):
            if isinstance(data, int):
                data = str(data)
            raw_msg = data
        if not raw_msg and not embed:
            raise PaginatorHandlerNoResult
        kwargs_done = {}
        if raw_msg is not None:
            kwargs_done["content"] = raw_msg
        if embed is not None:
            kwargs_done["embed"] = embed
        return kwargs_done

    async def start(
        self,
        datasets: List[Any],
        timeout: int = None,
        message: discord.Message = None,
        pass_emote: bool = False,
    ):
        if not callable(self._generator):
            raise PaginatorNoGenerator
        if len(datasets) < 1:
            return
        first_run = True
        position = 1
        max_page = len(datasets)
        is_timeout = False
        while True:
            if first_run:
                data = datasets[position - 1]
                args_to_send = [data]
                if self._generator_num:
                    args_to_send.append(position - 1)
                generated = await self._maybe_asyncute(self._generator, *args_to_send)
                first_run = False
                kwargs_done = self._gen_kwargs(generated)
                if not kwargs_done:
                    raise PaginatorHandlerNoResult
                if message is None:
                    message = await self.ctx.send(**kwargs_done)
                else:
                    await message.edit(**kwargs_done)

            reactmoji = []
            if max_page == 1 and position == 1:
                if self.break_on_no_results:
                    self.logger.warning("No more results!")
                    break
            elif position == 1:
                if not self._no_paginate:
                    reactmoji.append("⏩")
            elif position == max_page:
                if not self._no_paginate:
                    reactmoji.append("⏪")
            elif position > 1 and position < max_page and not self._no_paginate:
                reactmoji.extend(["⏪", "⏩"])
            for emote, handler in self.emotes_map.items():
                is_success = await self._maybe_asyncute(handler["check"], position - 1, datasets)
                if is_success:
                    reactmoji.append(emote)
            reactmoji.append("✅")

            for react in reactmoji:
                await message.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != message.id:
                    return False
                if user != self.ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", timeout=timeout, check=check_react)
            except asyncio.TimeoutError:
                is_timeout = True
                self.logger.warning("timeout, removing reactions...")
                await message.clear_reactions()
                return is_timeout
            if user != self.ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                position -= 1
                try:
                    data = datasets[position - 1]
                except IndexError:
                    return
                args_to_send = [data]
                if self._generator_num:
                    args_to_send.append(position - 1)
                generated = await self._maybe_asyncute(self._generator, *args_to_send)
                kwargs_done = self._gen_kwargs(generated)
                if not kwargs_done:
                    raise PaginatorHandlerNoResult
                await message.clear_reactions()
                await message.edit(**kwargs_done)
            elif "⏩" in str(res.emoji):
                position += 1
                try:
                    data = datasets[position - 1]
                except IndexError:
                    return
                args_to_send = [data]
                if self._generator_num:
                    args_to_send.append(position - 1)
                generated = await self._maybe_asyncute(self._generator, *args_to_send)
                kwargs_done = self._gen_kwargs(generated)
                if not kwargs_done:
                    raise PaginatorHandlerNoResult
                await message.clear_reactions()
                await message.edit(**kwargs_done)
            elif str(res.emoji) in list(self.emotes_map.keys()):
                handler_data = self.emotes_map[str(res.emoji)]
                if callable(handler_data["gen"]):
                    generator_to_send = [handler_data["gen"], datasets, position - 1, message]
                    if pass_emote:
                        generator_to_send.append(str(res.emoji))
                    executed_child = await self._maybe_asyncute(*generator_to_send)
                    try:
                        generated, message, timeout_error = executed_child
                    except ValueError:
                        generated, message = executed_child
                        timeout_error = False
                    if timeout_error:
                        is_timeout = True
                        await message.clear_reactions()
                        return is_timeout
                    if generated is None:
                        args_to_send = [datasets[position - 1]]
                        if self._generator_num:
                            args_to_send.append(position - 1)
                        generated = await self._maybe_asyncute(self._generator, *args_to_send)
                else:
                    args_to_send = [datasets[position - 1]]
                    if self._generator_num:
                        args_to_send.append(position - 1)
                    generated = await self._maybe_asyncute(self._generator, *args_to_send)
                await message.clear_reactions()
                if generated:
                    kwargs_done = self._gen_kwargs(generated)
                    await message.edit(**kwargs_done)
            elif "✅" in str(res.emoji):
                await message.clear_reactions()
                if self.remove_at_check:
                    await message.delete()
                return is_timeout
        return is_timeout
