from __future__ import annotations

import asyncio
import logging
import re
from typing import AnyStr, List, NamedTuple, Optional, Pattern, Union

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot, naoTimesContext

WordCheck = Union[str, List[str]]
WordPattern = Union[str, Pattern[AnyStr]]

DEFAULT_AUTOMOD_WORDS = [
    "nigger",
    "nigeer",
    "NIGGER",
    "nigg3r",
    "nigg er",
    "n igger",
    "ni gger",
    "nig ger",
    "nigge r",
    "n i g g e r",
    "n i gger",
    "nlgger",
]


class AutomodManagerChild:
    def __init__(self, guild_id: int):
        self._id = int(guild_id)
        self._enabled = True
        self._words: List[WordPattern] = []

    def __eq__(self, other: Union[int, AutomodManagerChild]):
        if isinstance(other, AutomodManagerChild):
            return self._id == other._id
        elif isinstance(other, int):
            return self._id == other
        return False

    def __repr__(self) -> str:
        return f"<AutomodManager id={self._id} words={self._words!r}>"

    def __add__(self, other: WordCheck):
        if isinstance(other, str):
            self.add(other)
        elif isinstance(other, list):
            only_string = list(filter(lambda x: isinstance(x, str), other))
            self.bulk_add(only_string)
        return self

    def __iadd__(self, other: WordCheck):
        self.__add__(other)
        return self

    def __sub__(self, other: WordCheck):
        if isinstance(other, str):
            self.remove(other)
        elif isinstance(other, list):
            only_string = list(filter(lambda x: isinstance(x, str), other))
            self.bulk_remove(only_string)

    def __isub__(self, other: WordCheck):
        self.__sub__(other)
        return self

    def __contains__(self, other: str):
        if isinstance(other, str):
            return other in self._words
        return False

    def disable(self):
        self._enabled = False

    def enable(self):
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def words(self) -> List[WordPattern]:
        return self._words

    def _dedup(self) -> None:
        self._words = list(set(self._words))

    def bulk_add(self, words: List[str]) -> None:
        self._words.extend(words)
        self._dedup()

    def add(self, word: WordPattern) -> None:
        if word.startswith("|regex|"):
            compiled = re.compile(word[7:])
            if compiled not in self._words:
                self._words.append(compiled)
        else:
            if word not in self._words:
                self._words.append(word)

    def remove(self, word: WordPattern) -> None:
        if word.startswith("|regex|"):
            regex_pattern = word[7:]
            find_idx = -1
            for n, reword in enumerate(self._words):
                if isinstance(reword, re.Pattern):
                    if reword.pattern == regex_pattern:
                        find_idx = n
                        break
            if find_idx != -1:
                del self._words[find_idx]
        else:
            if word in self._words:
                self._words.remove(word)

    def bulk_remove(self, words: List[str]) -> None:
        for word in words:
            self.remove(word)

    def _internal_get(self, word: WordPattern):
        if word.startswith("|regex|"):
            pattern = word[7:]
            for rewp in self._words:
                if isinstance(rewp, re.Pattern):
                    if rewp.pattern == pattern:
                        return word
        else:
            if word in self._words:
                return self._words[self._words.index(word)]
        return None

    def get(self, words: WordCheck) -> Optional[WordCheck]:
        if isinstance(words, str):
            self._internal_get(words)
        elif isinstance(words, list):
            only_string = list(filter(lambda x: isinstance(x, str), words))
            valid_string = []
            for word in only_string:
                wording = self._internal_get(word)
                if wording is not None:
                    valid_string.append(wording)
            return valid_string
        return None

    def _validate_re(self, pattern: Pattern, msg: str) -> bool:
        if not isinstance(pattern, re.Pattern):
            return False
        return pattern.match(msg) is not None

    def check(self, message: str) -> bool:
        if not self._enabled:
            return False
        msg_data = message.lower()
        triggered = False
        for word in self._words:
            if self._validate_re(word, msg_data):
                triggered = True
                break
            if word in msg_data:
                triggered = True
                break
        return triggered

    def serialize(self):
        all_words = []
        for word in self._words:
            if isinstance(word, re.Pattern):
                all_words.append(f"|regex|{word.pattern}")
            else:
                all_words.append(word)
        return {"words": all_words, "id": self._id, "enabled": self._enabled}

    @classmethod
    def from_dict(cls, data: dict):
        guild_id = data.get("id")
        if guild_id is None:
            raise ValueError("Missing id in the data")
        words = data.get("words", [])
        enabled = data.get("enabled", True)
        base_cls = cls(guild_id)
        if not enabled:
            base_cls.disable()
        base_cls += words
        return base_cls


class AutomodManager:
    def __init__(self):
        self._manager: List[AutomodManagerChild] = []

    def __contains__(self, other: int):
        if isinstance(other, int):
            for child in self._manager:
                if child == other:
                    return True
        return False

    def get_child(self, guild_id: int) -> AutomodManagerChild:
        for child in self._manager:
            if child == guild_id:
                return child
        return self.add_child(guild_id)

    def add_child(self, data: Union[int, dict]) -> AutomodManagerChild:
        if isinstance(data, int):
            child = AutomodManagerChild(data)
            self._manager.append(child)
        elif isinstance(data, dict):
            child = AutomodManagerChild.from_dict(data)
            self._manager.append(child)
        return child

    def remove_child(self, guild_id: int) -> AutomodManagerChild:
        child = self.get_child(guild_id)
        self._manager.remove(child)
        return child

    def get_from_child(self, guild_id: int, data: WordCheck) -> Optional[WordCheck]:
        child = self.get_child(guild_id)
        return child.get(data)

    def add_to_child(self, guild_id: int, data: WordCheck) -> None:
        child = self.get_child(guild_id)
        child += data

    def remove_from_child(self, guild_id: int, data: WordCheck) -> None:
        child = self.get_child(guild_id)
        child -= data

    def check_word(self, guild_id: int, message: str) -> bool:
        child = self.get_child(guild_id)
        return child.check(message)

    def serialize(self):
        all_data = {}
        for child in self._manager:
            all_data[str(child._id)] = child.serialize()
        return all_data

    def enable_child(self, guild_id: int):
        child = self.get_child(guild_id)
        child.enable()

    def disable_child(self, guild_id: int):
        child = self.get_child(guild_id)
        child.disable()


class AutomodHolding(NamedTuple):
    msg: discord.Message
    is_edit: bool = False


class ModToolsAutomoderator(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("ModTools.Automoderator")

        self._manager = AutomodManager()
        self._delete_queue = asyncio.Queue[AutomodHolding]()
        self._deletion_task: asyncio.Task = asyncio.Task(self._automod_message_deletion())
        self.bot.loop.create_task(self._automod_startup(), name="automod-startup")

    def cog_unload(self):
        self._deletion_task.cancel()

    async def _automod_startup(self):
        self.logger.info("Collecting automoderator words...")
        all_yabe_words = await self.bot.redisdb.getalldict("ntmodtools_yabai_*")
        for server_id, yabai_meta in all_yabe_words.items():
            server_id = server_id[17:]
            self._manager.add_child(yabai_meta)
        self.logger.info(f"Collected {len(all_yabe_words.keys())} automod process")

    async def _automod_message_deletion(self):
        self.logger.info("Starting automoderator message deletion task")
        while True:
            try:
                msg_queue = await self._delete_queue.get()
                is_success = False
                try:
                    await msg_queue.msg.delete(no_log=True)
                    is_success = True
                except discord.NotFound:
                    self.logger.warning(f"Message {msg_queue.msg.id} is deleted already...")
                except discord.HTTPException:
                    self.logger.warning(f"Failed to delete message {msg_queue.msg.id}")
                except Exception as e:
                    self.logger.error("An error occured", exc_info=e)
                if is_success:
                    warn_msg = "⚠️ Auto-mod trigger."
                    if msg_queue.is_edit:
                        warn_msg += " (Edited message)"
                    warn_msg += f"\n{msg_queue.msg.author.mention}"
                    the_channel: discord.TextChannel = msg_queue.msg.channel
                    if isinstance(the_channel, discord.TextChannel):
                        try:
                            await the_channel.send(warn_msg)
                        except discord.Forbidden:
                            pass
                        except discord.HTTPException:
                            pass
                self._delete_queue.task_done()
            except asyncio.CancelledError:
                break
        self.logger.info("Task are cancelled or done!")

    def _automod_can_continue(self, message: discord.Message) -> bool:
        channel: discord.TextChannel = message.channel
        guild: discord.Guild = message.guild
        if guild is None:
            return False
        if not isinstance(channel, discord.TextChannel):
            return False
        if guild.id not in self._manager:
            return False
        if message.author.bot:
            return False
        channel_perm: discord.Permissions = channel.permissions_for(guild.get_member(self.bot.user.id))
        if not channel_perm.manage_messages:
            return False
        return True

    @commands.Cog.listener("on_message")
    async def _modtools_automod_watcher(self, message: discord.Message):
        is_valid = self._automod_can_continue(message)
        if not is_valid:
            return

        content = message.content
        if self._manager.check_word(message.guild.id, content):
            await self._delete_queue.put(AutomodHolding(message, False))

    @commands.Cog.listener("on_message_edit")
    async def _modtools_automod_edit_watcher(self, before: discord.Message, after: discord.Message):
        is_valid = self._automod_can_continue(after)
        if not is_valid:
            return

        content = after.content
        if self._manager.check_word(after.guild.id, content):
            await self._delete_queue.put(AutomodHolding(after, True))

    @commands.group(name="automod")
    @commands.has_guild_permissions(manage_messages=True)
    @commands.guild_only()
    async def mdt_automod(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        if not ctx.invoked_subcommand:
            if guild_id not in self._manager:
                confirm = await ctx.confirm("👮⚙️ Apakah anda ingin mengaktifkan Automod?")
                if confirm:
                    self.logger.info(f"{guild_id}: Automod is reenabled!")
                    self._manager.enable_child(guild_id)
                    self._manager.add_to_child(guild_id, DEFAULT_AUTOMOD_WORDS)
                    await self.bot.redisdb.set(
                        f"ntmodtools_yabai_{guild_id}", self._manager.get_child(guild_id).serialize()
                    )
                    await ctx.send("👮⚙️ Automod diaktifkan!")
            else:
                confirm = await ctx.confirm("👮⚙️ Apakah anda ingin mengaktifkan Automod kembali?")
                if confirm:
                    self.logger.info(f"{guild_id}: Automod is reenabled!")
                    self._manager.enable_child(guild_id)
                    await self.bot.redisdb.set(
                        f"ntmodtools_yabai_{guild_id}", self._manager.get_child(guild_id).serialize()
                    )
                    await ctx.send("👮⚙️ Automod telah diaktifkan kembali!")
                else:
                    await ctx.send("👮⚙️ *Dibatalkan*")

    @mdt_automod.command(name="add", aliases=["tambah"])
    async def _modtools_automod_add(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        if guild_id not in self._manager:
            return await ctx.send("👮⚙️ Automod belum diaktifkan!")

        new_words_holding: List[str] = []

        async def ask_words(use_timeout=False):
            prompt = "Mohon ketik kata baru, untuk menulis lebih dari satu"
            prompt += " pisah dengan `, `, contoh: `kata 1, kata 2`"
            new_words = await ctx.wait_content(prompt, True, True)
            if new_words is None:
                if use_timeout:
                    await ctx.send_timed("***Timeout***")
                else:
                    await ctx.send("***Timeout***")
                return
            if not new_words:
                if use_timeout:
                    await ctx.send_timed("*Dibatalkan*")
                else:
                    await ctx.send("*Dibatalkan*")
                return

            new_words = new_words.split(", ")
            new_words_holding.extend(new_words)

        async def ask_regex():
            prompt = "Mohon ketik pattern regex yang benar"
            while True:
                new_regex = await ctx.wait_content(prompt, True, True)
                if new_regex is None:
                    return await ctx.send_timed("***Timeout***")
                if not new_regex:
                    return await ctx.send_timed("*Dibatalkan*")

                try:
                    re.compile(new_regex)
                    new_words_holding.append(f"|regex|{new_regex}")
                    break
                except Exception:
                    await ctx.send_timed("Regex yang dimasukan bukanlah regex yang valid, mohon ketik ulang!")

        await ask_words()

        def design_description():
            contained = []
            for words in new_words_holding:
                if words.startswith("|regex|"):
                    contained.append(f"- `{words[7:20]} [...]` (Regex)")
                else:
                    contained.append(f"- `{words}`")
            return "\n".join(contained)

        react_andy = [
            "➕",
            "🔨",
            "✅",
            "❌",
        ]
        react_info = [
            "➕ Tambah kata baru",
            "🔨 Tambah regex",
            "✅ Selesai",
            "❌ Batal",
        ]

        first_run = True
        cancelled = False
        timeout = False
        react_msg: discord.Message
        while True:
            embed = discord.Embed(title="Automod", color=discord.Color.random())
            embed.set_thumbnail(url="https://github.com/noaione/potia-muse/raw/master/assets/avatar.png")
            embed.description = design_description()
            embed.add_field(name="*Tambahan*", value="\n".join(react_info), inline=False)
            embed.set_footer(text="👮‍♂️ Automod")
            if first_run:
                first_run = False
                react_msg = await ctx.send(embed=embed)
            else:
                await react_msg.edit(embed=embed)

            def _check_react(reaction: discord.Reaction, user: discord.Member):
                return (
                    reaction.message.id == react_msg.id
                    and user.id == ctx.author.id
                    and reaction.emoji in react_andy
                )

            for react in react_andy:
                await react_msg.add_reaction(react)

            reaction: discord.Reaction
            user: discord.Member
            try:
                reaction, user = await self.bot.wait_for("reaction_add", check=_check_react, timeout=60)
            except asyncio.TimeoutError:
                await react_msg.clear_reactions()
                cancelled = True
                timeout = True
                break
            if user.id != ctx.author.id:
                pass
            elif reaction.emoji == "➕":
                await react_msg.clear_reactions()
                await ask_words(True)
            elif reaction.emoji == "🔨":
                await react_msg.clear_reactions()
                await ask_regex()
            elif reaction.emoji == "✅":
                await react_msg.clear_reactions()
                break
            elif reaction.emoji == "❌":
                await react_msg.clear_reactions()
                cancelled = True

        if cancelled and timeout:
            return await ctx.send("Timeout! Mohon ulangi dari awal!")
        elif cancelled:
            return await ctx.send("***Dibatalkan***")

        self._manager.add_to_child(guild_id, new_words_holding)
        await self.bot.redisdb.set(
            f"ntmodtools_yabai_{guild_id}", self._manager.get_child(guild_id).serialize()
        )
        await ctx.send("👮⚙️ Kata baru telah disimpan!")

    @mdt_automod.command(name="disable", aliases=["matikan"])
    async def _modtools_automod_disable(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id

        if guild_id not in self._manager:
            return await ctx.send("👮⚙️ Automod belum diaktifkan!")

        self._manager.disable_child(guild_id)
        await self.bot.redisdb.set(
            f"ntmodtools_yabai_{guild_id}", self._manager.get_child(guild_id).serialize()
        )
        self.logger.info(f"{guild_id}: Automod has been disabled!")
        atcmd = f"{self.bot.prefixes(ctx)}automod"
        await ctx.send(
            "👮⚙️ Automod telah dinonaktifkan untuk peladen ini!\n"
            f"Untuk mengaktikfan kembali, gunakan: {atcmd}"
        )

    @mdt_automod.command(name="info")
    async def _modtools_automod_info(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id

        if guild_id not in self._manager:
            return await ctx.send("👮⚙️ Automod belum diaktifkan!")

        automod_info = self._manager.get_child(guild_id)

        def design_description():
            contained = []
            for words in automod_info.words:
                if isinstance(words, re.Pattern):
                    contained.append(f"- `{words.pattern[7:20]} [...]` (Regex)")
                else:
                    contained.append(f"- `{words}`")
            return "\n".join(contained)

        atcmd = f"{self.bot.prefixes(ctx)}automod"
        automod_extra = [
            f"➕ Ingin menambah? Gunakan `{atcmd} tambah`",
            f"❌ Ingin menonaktifkan? Gunakan `{atcmd} matikan`",
        ]
        embed = discord.Embed(title=f"Automod ({len(automod_info.words)})", color=discord.Color.random())
        embed.set_thumbnail(url="https://github.com/noaione/potia-muse/raw/master/assets/avatar.png")
        embed.description = design_description()
        embed.add_field(name="*Tambahan*", value="\n".join(automod_extra), inline=False)
        embed.set_footer(text="👮‍♂️ Automod")

        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(ModToolsAutomoderator(bot))
