from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import dataclass

import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
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
    def from_dict(cls: type[SimpleReminder], data: dict):
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

        self._reminder_tasks: dict[str, asyncio.Task] = {}

    @property
    def redisdb(self):
        if self.bot.redisdb is None:
            raise RuntimeError("Reminder storage is unavailable")
        return self.bot.redisdb

    async def cog_unload(self) -> None:
        for task in self._reminder_tasks.values():
            task.cancel()

    async def cog_load(self) -> None:
        all_reminder = await self.redisdb.getalldict("ntreminderv2_*")
        invalid_reminder: list[str] = []
        valid_reminder: list[SimpleReminder] = []
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
            await self.redisdb.rm(keyname)

        current = self.bot.now().int_timestamp
        for reminder in valid_reminder:
            self._schedule_reminder(reminder, current)

    async def _remove_reminder(self, reminder: SimpleReminder):
        await self.redisdb.rm("ntreminderv2_" + reminder.message)

    def _deregister_reminder(self, task: asyncio.Task, reminder: SimpleReminder):
        task_name = task.get_name()
        try:
            self.logger.info(f"Reminder task {task_name} has finished running")
            self._reminder_tasks.pop(task_name, None)
        except (ValueError, KeyError, IndexError, AttributeError):
            self.logger.error(f"Failed to deregister task {task_name}, probably missing!")
        removal_task_name = f"removalsoon-{task_name}"
        removal_task = asyncio.create_task(self._remove_reminder(reminder), name=removal_task_name)
        self._reminder_tasks[removal_task_name] = removal_task
        removal_task.add_done_callback(self._on_reminder_finished)

    def _schedule_reminder(self, reminder: SimpleReminder, time: int):
        task_name = f"reminder-bot-{reminder.message}_{time}"
        try:
            task: asyncio.Task = self.bot.loop.create_task(self._delayed_reminder(reminder))
            self._reminder_tasks[task_name] = task
            after_reminder_done = functools.partial(self._deregister_reminder, reminder=reminder)
            task.add_done_callback(after_reminder_done)
            self.logger.info("Scheduled reminder %s", task_name)
        except Exception as e:
            self.logger.error("Failed to schedule reminder %s: %s", task_name, e, exc_info=e)

    async def _create_reminder(self, reminder: SimpleReminder):
        current = self.bot.now().int_timestamp
        await self.redisdb.set("ntreminderv2_" + reminder.message, reminder.to_dict())
        self._schedule_reminder(reminder, current)

    async def _safely_send_message(
        self,
        message: str,
        target: discord.abc.Messageable,
        reference: discord.Message | discord.MessageReference | discord.PartialMessage | None = None,
    ):
        chunks = [message[i : i + 2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            try:
                if reference is None:
                    reference = await target.send(chunk)
                else:
                    reference = await target.send(chunk, reference=reference)
            except Exception as e:
                self.logger.error("Failed to send message %s: %s", chunk, e, exc_info=e)

    async def _ping_reminder(self, reminder: SimpleReminder):
        channel = self.bot.get_channel(int(reminder.channel))
        if channel is None:
            self.logger.error("Channel %s not found, removing reminder!", reminder.channel)
            await self._remove_reminder(reminder)
            return

        if not isinstance(channel, discord.abc.Messageable):
            self.logger.error("Channel %s cannot receive messages, removing reminder!", reminder.channel)
            await self._remove_reminder(reminder)
            return

        reference = None
        if not reminder.from_slash and isinstance(channel, (discord.TextChannel, discord.Thread)):
            reference = channel.get_partial_message(int(reminder.message))
        await self._safely_send_message(f"<@{reminder.user}> {reminder.reminder}", channel, reference)
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
        except (TimeoutError, asyncio.CancelledError):
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

    @app_commands.command(
        name="ingatkan",
        description=app_commands.locale_str(
            "Ingatkan anda sesuatu dalam waktu yang ditentukan.", key="fun.ingatkan.description"
        ),
    )
    @app_commands.describe(
        reminder=app_commands.locale_str("Apa yang ingin bot ingatkan?", key="fun.ingatkan.option_reminder"),
        timeout=app_commands.locale_str(
            "Durasi waktu, format time string (ex: 5m, 1h, 1d, 1w) [Default: 5 menit]",
            key="fun.ingatkan.option_timeout",
        ),
    )
    async def _reminder_cmd_slash(
        self,
        interaction: discord.Interaction,
        reminder: str,
        timeout: str = "5m",  # ruff: ignore[async-function-with-timeout]
    ):
        """Ingatkan anda sesuatu dalam waktu yang ditentukan."""
        ctx = await self.bot.get_context(interaction)
        i18n = self.bot.i18n_for(interaction.guild, "fun")
        try:
            timeout_real = TimeString.parse(timeout)
        except TimeStringParseError:
            self.logger.error("Failed to parse time string %s", timeout)
            return await ctx.send(i18n.t("ingatkan.invalid_time"))

        current = self.bot.now().int_timestamp
        target = int(current + timeout_real.timestamp())

        reminder_sim = SimpleReminder(
            target, reminder, str(ctx.message.id), str(ctx.channel.id), str(ctx.author.id), True
        )

        await self._create_reminder(reminder_sim)
        await ctx.send(i18n.t("ingatkan.success", duration=timeout_real.to_string()))


async def setup(bot: naoTimesBot):
    if bot.redisdb is None:
        bot.logger.warning("Redis is unavailable; skipping reminder cog")
        return
    await bot.add_cog(FunReminder(bot))
