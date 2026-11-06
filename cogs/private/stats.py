import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot


def _count_through_users(guilds: list[discord.Guild]):
    valid_users: list[int] = []
    for guild in guilds:
        for member in guild.members:
            if not member.bot and member.id not in valid_users:
                valid_users.append(member.id)
    return len(valid_users)


def _count_all_commands(bot: naoTimesBot):
    """Count public slash commands (leaf commands only, owner-only groups excluded)."""
    from naotimes.context import OwnerGroup

    total = 0
    for app_cmd in bot.tree.walk_commands():
        if isinstance(app_cmd, app_commands.Group):
            continue
        root = app_cmd.root_parent or app_cmd
        if isinstance(root, OwnerGroup):
            continue
        if any("is_owner" in str(check) for check in getattr(app_cmd, "checks", [])):
            continue
        total += 1
    return total


class PrivateCogsStatsUpdater(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("PrivateCog.ZStats")

        self.update_stats.start()

    async def cog_unload(self) -> None:
        self.update_stats.cancel()

    @tasks.loop(seconds=120.0)
    async def update_stats(self):
        commands_total = await self.bot.loop.run_in_executor(None, _count_all_commands, self.bot)
        server_lists = list(self.bot.guilds)
        total_servers = len(server_lists)

        # Dont block event loop
        user_count = await self.bot.loop.run_in_executor(None, _count_through_users, server_lists)
        showtimes_servers = await self.bot.redisdb.getall("showtimes_*") if self.bot.redisdb is not None else []

        update_data = {
            "stats1": commands_total,
            "stats2": user_count,
            "stats3": total_servers,
            "stats4": len(showtimes_servers),
        }

        self.logger.info("Updating shields.io statistics...")
        if self.bot.aiosession is None:
            self.logger.warning("Skipping shields.io update because the HTTP session is unavailable")
            return
        async with self.bot.aiosession.post(
            "https://api.ihateani.me/shield/update",
            headers={"Content-Type": "application/json"},
            json=update_data,
        ) as resp:
            await resp.json()
            if resp.status != 200:
                self.logger.error("Shields update failed Madge")
            else:
                self.logger.info("Shields updated!")


async def setup(bot: naoTimesBot):
    await bot.add_cog(PrivateCogsStatsUpdater(bot))
