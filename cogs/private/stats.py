import logging
from typing import List

from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot


class PrivateCogsStatsUpdater(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("PrivateCog.ZStats")

    @tasks.loop(seconds=120.0)
    async def update_stats(self):
        all_commands: List[commands.Command] = self.bot.commands

        disallowed_cmds = []
        for cmd in all_commands:
            if cmd.checks:
                for check in cmd.checks:
                    primitive_name = check.__str__()
                    if "is_owner" in primitive_name:
                        disallowed_cmds.append(cmd)

        commands_total = len(all_commands) - len(disallowed_cmds)
        total_servers = len(self.bot.guilds)

        unique_users = []
        for guild in self.bot.guilds:
            for member in guild.members:
                if not member.bot and member.id not in unique_users:
                    unique_users.append(member.id)

        update_data = {"stats1": commands_total, "stats2": len(unique_users), "stats3": total_servers}

        self.logger.info("Updating shields.io statistics...")
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


def setup(bot: naoTimesBot):
    bot.add_cog(PrivateCogsStatsUpdater(bot))
