"""Globally set maintenance mode for naoTimes."""

import asyncio
from typing import Callable, Optional

import arrow
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.placeholder import PlaceHolderCommand


class BotBrainMaintenance(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot

        self._task1: asyncio.Task = self.bot.loop.create_task(
            self._propagate_maintenance(), name="ntbotbrain-propagate-maintenance"
        )
        self._task2: asyncio.Task = self.bot.loop.create_task(
            self._propagate_unmaintenance(), name="ntbotbrain-propagate-unmaintenance"
        )

    def cog_unload(self) -> None:
        self._task1.cancel()
        self._task2.cancel()

    async def maybe_async(self, predicate: Callable[..., None], *args, **kwargs):
        real_func = getattr(predicate, "func", predicate)
        if asyncio.iscoroutinefunction(real_func):
            return await predicate(*args, **kwargs)
        return predicate(*args, **kwargs)

    @commands.command(name="startmaintenance")
    @commands.is_owner()
    async def _bb_maintenance_start(self, ctx: naoTimesContext):
        """Start maintenance mode."""
        expected_start_time: Optional[arrow.Arrow] = None
        while True:
            question = await ctx.wait_content("Mohon ketik waktu mulai:", timeout=None)
            if question is False:
                break
            try:
                expected_start_time = arrow.get(question)
            except arrow.ParserError:
                await ctx.send_timed("Mohon ketik format waktu yang benar!", 2)
        if expected_start_time is None:
            return await ctx.send("Dibatalkan!")
        expected_end_time: Optional[arrow.Arrow] = None
        while True:
            question = await ctx.wait_content("Mohon ketik waktu akhir:", timeout=None)
            if question is False:
                break
            try:
                expected_end_time = arrow.get(question)
            except arrow.ParserError:
                await ctx.send_timed("Mohon ketik format waktu yang benar!", 2)
        if expected_end_time is None:
            return await ctx.send("Dibatalkan!")

        if expected_start_time > expected_end_time:
            return await ctx.send("Waktu mulai harus lebih awal dari waktu akhir!")

        st_timestamped = expected_start_time.int_timestamp
        et_timestamped = expected_end_time.int_timestamp

        visualize = f"Waktu maintenance akan mulai dari <t:{st_timestamped}:F> "
        visualize += f"ke <t:{et_timestamped}:F>, apakah anda yakin?"
        confirm = await ctx.confirm(visualize)

        if not confirm:
            return await ctx.send("Dibatalkan!")

        self.bot.set_maintenance(expected_start_time, expected_end_time)

    @staticmethod
    def _owner_only_command(command: commands.Command):
        if command.checks:
            for check in command.checks:
                fn_primitive_name = check.__str__()
                if "is_owner" in fn_primitive_name:
                    return True
        return False

    async def _propagate_command_maintenance(self):
        """Propagate maintenance mode to all servers."""
        command_mappings = self.bot.all_commands.copy()
        for name, command in self.bot.all_commands.items():
            if command.cog is not None:
                before_invoke = getattr(command.cog, "cog_maintenance", None)
                if before_invoke is not None:
                    await self.maybe_async(before_invoke, command.cog)

            is_placeholder = getattr(command.callback, "__nt_placeholder__", None)
            if is_placeholder is not None:
                continue

            if self._owner_only_command(command):
                continue

            original_command = command.copy()
            placeholder_command = PlaceHolderCommand(command.name, None)
            placeholder_command.bind(command)
            # TODO: Prepare custom text
            placeholder_command.set_custom()
            original_command.callback = placeholder_command.send_placeholder
            command_mappings[name] = original_command

        self.bot.all_commands = command_mappings

    async def _propagate_command_unmaintenance(self):
        """Propagate maintenance mode to all servers."""
        command_mappings = self.bot.all_commands.copy()
        for name, command in self.bot.all_commands.items():
            if command.cog is not None:
                before_invoke = getattr(command.cog, "cog_unmaintenance", None)
                if before_invoke is not None:
                    await self.maybe_async(before_invoke, command.cog)

            is_placeholder = getattr(command.callback, "__nt_placeholder__", None)
            if is_placeholder is None:
                continue

            original_command = command.copy()
            original_command.callback = is_placeholder
            command_mappings[name] = original_command

        self.bot.all_commands = command_mappings

    async def _propagate_maintenance(self):
        """Propagate maintenance mode to all servers."""
        try:
            await self.bot.wait_until_ready()

            while True:
                if (
                    self.bot.maintenance is not None
                    and not self.bot.maintenance.ready
                    and self.bot.maintenance.maintenance
                ):
                    await self._propagate_command_maintenance()
                    self.bot.maintenance.set()
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    async def _propagate_unmaintenance(self):
        try:
            await self.bot.wait_until_ready()

            while True:
                if (
                    self.bot.maintenance is not None
                    and self.bot.maintenance.ready
                    and not self.bot.maintenance.maintenance
                ):
                    await self._propagate_command_unmaintenance()
                    self.bot.maintenance = None
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainMaintenance(bot))
