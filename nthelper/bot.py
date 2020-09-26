import logging
import traceback
from typing import Dict, List, Union

import discord
from discord.ext import commands

from .anibucket import AnilistBucket
from .fsdb import FansubDBBridge
from .showtimes_helper import ShowtimesQueue, naoTimesDB
from .utils import __version__


class naoTimesBot(commands.Bot):
    """A modified version of commands.Bot
    ---
    Reason making this is for easier typecasting.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger: logging.Logger = logging.getLogger("naoTimesBot")
        self.automod_folder: str

        self.semver: str = __version__
        self.botconf: Dict[str, Union[str, Dict[str, Union[str, int, bool]]]]
        self.prefix: str

        self.jsdb_streams: dict
        self.jsdb_currency: dict
        self.jsdb_crypto: dict

        self.fcwd: str

        self.kbbi_cookie: str
        self.kbbi_expires: int
        self.kbbi_auth: Dict[str, str]

        self.fsdb: FansubDBBridge
        self.showqueue: ShowtimesQueue
        self.anibucket: AnilistBucket

        self.showtimes_resync: list = []
        self.copy_of_commands: Dict[str, commands.Command] = {}
        self.ntdb: naoTimesDB

        self.uptime: float
        self.owner: Union[discord.User, discord.TeamMember]

        self.is_team_bot: bool = False
        self.team_name: str
        self.team_members: List[discord.TeamMember] = []

    def echo_error(self, error):
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        self.logger.error("Exception occured\n" + "".join(tb))

    def prefix_srv(self, ctx) -> str:
        prefix = self.command_prefix
        if callable(prefix):
            prefix = prefix(self, ctx.message)
        if isinstance(prefix, (list, tuple)):
            final_pre = prefix[0]
        else:
            final_pre = prefix
        return final_pre

    def is_mentionable(self, ctx, user_data):
        member = ctx.message.guild.get_member(user_data.id)
        if member is None:
            return f"{user_data.name}#{user_data.discriminator}"
        else:
            return f"<@{user_data.id}>"

    def teams_to_user(self, user_data):
        member_data = self.get_user(user_data.id)
        if not member_data:
            self.logger.warning("failed to convert TeamMember to User.")
            return user_data
        return member_data

    async def detect_teams_bot(self):
        """|coro|

        Detect if the current bot token is a Teams Bot or a normal User bot.

        If it's a Teams bot, it will assign it properly to not break everything.
        """
        app_info: discord.AppInfo = await self.application_info()
        team_data: discord.Team = app_info.team
        if team_data is None:
            self.owner = app_info.owner
        else:
            main_owner: discord.TeamMember = team_data.owner
            members_list: List[discord.TeamMember] = team_data.members

            self.owner = self.teams_to_user(main_owner)
            self.team_name = team_data.name
            self.is_team_bot = True
            for member in members_list:
                if member.id == main_owner.id:
                    continue
                self.team_members.append(self.teams_to_user(member))
