from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Type

import arrow
import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesAppContext, naoTimesContext
from naotimes.timeparse import TimeString, TimeStringParseError


@dataclass
class SimpleReminder:
    target: int
    reminder: str

    message: str
    channel: str
    user: str
    from_slash: bool = False

    @classmethod
    def from_dict(cls: Type[SimpleReminder], data: dict):
        metadata = data["meta"]
        from_slash = metadata.get("slash", False)
        return cls(
            data["target"],
            data["reminder"],
            metadata["id"],
            metadata["channel"],
            metadata["user"],
            from_slash,
        )

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "reminder": self.reminder,
            "meta": {
                "id": self.message,
                "channel": self.channel,
                "user": self.user,
                "slash": self.from_slash,
            },
        }


class FunReminder(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Fun.Reminder")

        self._reminder_tasks: Dict[str, asyncio.Task] = {}

    def cog_unload(self) -> None:
        for task in self._reminder_tasks.values():
            task.cancel()

    async def cog_load(self) -> None:
        all_reminder = await self.bot.redisdb.getalldict("ntreminderv2_*")
        invalid_reminder: List[str] = []
        valid_reminder: List[SimpleReminder] = []
        for keyname, reminder in all_reminder.items():
            try:
                reminder_sim = SimpleReminder.from_dict(reminder)
            except Exception as e:
                self.logger.error("Failed to parse reminder %s: %s", keyname, e, exc_info=e)
                invalid_reminder.append(keyname)
                continue
            valid_reminder.append(reminder_sim)

        for keyname in invalid_reminder:
            self.logger.warning("Reminder %s is invalid, removing", keyname)
            await self.bot.redisdb.rm(keyname)

        current = self.bot.now().int_timestamp
        for reminder in valid_reminder:
            self._schedule_reminder(reminder, current)

    async def _remove_reminder(self, reminder: SimpleReminder):
        await self.bot.redisdb.rm("ntreminderv2_" + reminder.message)

    def _schedule_reminder(self, reminder: SimpleReminder, time: int):
        _task_name = f"reminder-bot-{reminder.message}_{time}"
        try:
            task: asyncio.Task = self.bot.loop.create_task(self._delayed_reminder(reminder))
            self._reminder_tasks[_task_name] = task
            task.add_done_callback(self._remove_reminder)
            self.logger.info("Scheduled reminder %s", _task_name)
        except Exception as e:
            self.logger.error("Failed to schedule reminder %s: %s", _task_name, e, exc_info=e)

    async def _create_reminder(self, reminder: SimpleReminder):
        current = self.bot.now().int_timestamp
        await self.bot.redisdb.set("ntreminderv2_" + reminder.message, reminder.to_dict())
        self._schedule_reminder(reminder, current)

    async def _safely_send_message(
        self, message: str, target: disnake.abc.Messageable, reference: disnake.Message = None
    ):
        chunks = [message[i : i + 2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            try:
                reference = await target.send(chunk, reference=reference)
            except Exception as e:
                self.logger.error("Failed to send message %s: %s", chunk, e, exc_info=e)

    async def _ping_reminder(self, reminder: SimpleReminder):
        channel = self.bot.get_channel(int(reminder.channel))
        if channel is None:
            self.logger.error("Channel %s not found, removing reminder!", reminder.channel)
            await self._remove_reminder(reminder)
            return

        partial_msg = None
        if not reminder.from_slash:
            partial_msg = channel.get_partial_message(int(reminder.message))
        await self._safely_send_message(f"<@{reminder.user}> {reminder.message}", channel, partial_msg)
        await self._remove_reminder(reminder)

    async def _delayed_reminder(self, reminder: SimpleReminder):
        target_time = arrow.get(reminder.target, tzinfo="UTC")
        current = self.bot.now()
        difference = target_time - current

        difference_seconds = difference.total_seconds()
        if difference_seconds < 0:
            difference_seconds = 1

        self.logger.info(f"[{reminder.message}] Sleeping for %s seconds before reminding", difference_seconds)
        try:
            await asyncio.sleep(difference_seconds)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.logger.warning("Reminder %s was cancelled because cogs got unloaded", reminder.message)
            return

        await self._ping_reminder(reminder)

    def _on_reminder_finished(self, task: asyncio.Task):
        task_name = task.get_name()
        try:
            self.logger.info("Reminder %s finished", task_name)
            self._reminder_tasks.pop(task_name)
        except KeyError:
            self.logger.warning("Reminder %s was not found", task_name)

    @commands.slash_command(name="ingatkan")
    async def _reminder_cmd_slash(self, ctx: naoTimesAppContext, reminder: str, timeout: str = "5m"):
        """Ingatkan anda sesuatu dalam waktu yang ditentukan.

        Parameters
        ----------
        reminder: Apa yang ingin bot ingatkan?
        timeout: Durasi waktu, format time string (ex: 5m, 1h, 1d, 1w). Default 5 menit
        """
        try:
            timeout_real = TimeString.parse(timeout)
        except TimeStringParseError:
            self.logger.error("Failed to parse time string %s", timeout)
            return await ctx.send("Waktu yang kamu tulis tidak valid!")

        current = self.bot.now().int_timestamp
        target = current + timeout_real.timestamp()

        reminder_sim = SimpleReminder(
            target, reminder, str(ctx.id), str(ctx.channel.id), str(ctx.author.id), True
        )

        await self._create_reminder(reminder_sim)
        await ctx.send(f"Akan diingatkan dalam {timeout.to_string()}!")

    @commands.command(name="ingatkan", aliases=["ingat", "remind", "remindme", "reminder"])
    async def _reminder_cmd(self, ctx: naoTimesContext, *, sacred_text: str = ""):
        sacred_text = sacred_text.strip()

        if not sacred_text:
            return await ctx.send("Tolong tulis apa yang ingin kamu ingatkan! (Dan waktunya!)")

        split_text = sacred_text.split(" ", 1)
        if len(split_text) < 2:
            return await ctx.send("Tolong tulis apa yang ingin kamu ingatkan! (Dan waktunya!)")

        try:
            timeout = TimeString.parse(split_text[0])
        except TimeStringParseError:
            self.logger.error("Failed to parse time string %s", split_text[0])
            return await ctx.send("Waktu yang kamu tulis tidak valid!")

        reminder = split_text[1]

        current = self.bot.now().int_timestamp
        target = current + timeout.timestamp()

        reminder_sim = SimpleReminder(
            target, reminder, str(ctx.message.id), str(ctx.channel.id), str(ctx.author.id)
        )

        await self._create_reminder(reminder_sim)
        await ctx.send(f"Akan diingatkan dalam {timeout.to_string()}!", reference=ctx.message)


def setup(bot: naoTimesBot):
    bot.add_cog(FunReminder(bot))
