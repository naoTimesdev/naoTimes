from typing import List

from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext


class MusikPlayerCommandAdmin(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot

    @commands.group(name="musikadmin", aliases=["md", "musicadmin"])
    async def musik_admin(self, ctx: naoTimesContext):
        return

    @musik_admin.command(name="active")
    async def musik_admin_active(self, ctx: naoTimesContext):
        active_players = list(self.bot.ntplayer.actives.keys())

        guild_named: List[str] = ["**Active guild players**\n"]
        for n, player in enumerate(active_players, 1):
            guild = self.bot.get_guild(player)
            if guild is None:
                guild_named.append(f"**{n}.** *Unknown* (`{player}`)")
            else:
                guild_named.append(f"**{n}.** {guild.name} (`{player}`)")

        await ctx.send("\n".join(guild_named))


def setup(bot: naoTimesBot) -> None:
    bot.add_cog(MusikPlayerCommandAdmin(bot))
