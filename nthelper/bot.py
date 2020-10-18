import logging
import os
import platform
import traceback
from typing import Dict, List, Union

import aiohttp
import discord
from discord.ext import commands

from .anibucket import AnilistBucket
from .fsdb import FansubDBBridge
from .kbbiasync import KBBI
from .showtimes_helper import ShowtimesQueue, naoTimesDB
from .utils import __version__
from .vndbsocket import VNDBSockIOManager

discord_semver = tuple([int(ver) for ver in discord.__version__.split(".")])


class HostingData:
    def __init__(self, ip, location, timezone):
        self._ip: str = ip
        self._location: str = location
        self._timezone: str = timezone

    def __get_masked_ip(self):
        ip_data = self._ip
        if ":" in ip_data:
            ipv6_data = ip_data.split(":")
            fv6, lv6 = ipv6_data[0], ipv6_data[-1]
            masked_ipv6 = ["*" * len(ip) for ip in ipv6_data[1:-1]]
            ip_data = f"{fv6}:" + ":".join(masked_ipv6) + f":{lv6}"
        elif "." in ip_data:
            ipv4_data = ip_data.split(".")
            fv4, lv4 = ipv4_data[0], ipv4_data[-1]
            masked_ipv4 = ["*" * len(ip) for ip in ipv4_data[1:-1]]
            ip_data = f"{fv4}." + ".".join(masked_ipv4) + f".{lv4}"
        return ip_data

    @property
    def ip(self):
        """Return the Hosting Data IP Address."""
        return self._ip

    @property
    def masked_ip(self):
        """Return the Hosting Data Masked (192.***.***.1) IP Address."""
        return self.__get_masked_ip()

    @property
    def location(self):
        """Return the Hosting Data Location (Region, Country)."""
        return self._location

    @property
    def timezone(self):
        """Return the Hosting Data Timezone"""
        return self._timezone

    tz = timezone


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
        self.botconf: Dict[str, Union[str, int, bool, Dict[str, Union[str, int, bool]]]]
        self.prefix: str

        self.jsdb_streams: dict
        self.jsdb_currency: dict
        self.jsdb_crypto: dict

        self.fcwd: str
        self.error_logger: int = None

        self.fsdb: FansubDBBridge = None
        self.showqueue: ShowtimesQueue
        self.anibucket: AnilistBucket
        self.vndb_socket: VNDBSockIOManager = None
        self.kbbi: KBBI = None

        self.showtimes_resync: list = []
        self.copy_of_commands: Dict[str, commands.Command] = {}
        self.ntdb: naoTimesDB = None

        self.uptime: float
        self.owner: Union[discord.User, discord.TeamMember]

        self.is_team_bot: bool = False
        self.team_name: str
        self.team_members: List[discord.TeamMember] = []

        self._ip_hostname = ""
        self._host_country = ""
        self._host_region = ""
        self._host_tz = ""

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
        return f"<@{user_data.id}>"

    def teams_to_user(self, user_data):
        member_data = self.get_user(user_data.id)
        if not member_data:
            self.logger.warning("failed to convert TeamMember to User.")
            return user_data
        return member_data

    async def send_error_log(self, message=None, embed=None):
        """|coro|

        Send an error log to bot owner or the set channel.

        Parameters
        ----------
        message : str, optional
            The error message to send, by default None
        embed : discord.Embed, optional
            A formatted Discord Embed to send, by default None
        """
        content_to_send = {}
        if message is not None:
            content_to_send["content"] = message
        if embed is not None:
            content_to_send["embed"] = embed
        if self.error_logger is not None:
            channel_data = self.get_channel(self.error_logger)
            await channel_data.send(**content_to_send)
        else:
            await self.owner.send(**content_to_send)

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

    async def populate_data(self):
        """|coro|

        Populate the bot attributes with data like bot IP/Country
        and other stuff
        """
        self.logger.info("getting bot hardware info...")
        platform_info = platform.uname()
        self._host_os = platform_info.system
        self._host_os_ver = f"{platform_info.release}"
        self._host_name = platform_info.node
        self._host_arch = platform_info.machine

        self._host_proc = platform_info.processor
        self._host_proc_threads = os.cpu_count()
        self._host_pid = os.getpid()

        py_ver = platform.python_version()
        py_impl = platform.python_implementation()
        py_compiler = platform.python_compiler()
        self._host_pyver = f"{py_ver} ({py_impl}) [{py_compiler}]"
        self._host_dpyver = discord.__version__

        self.logger.info("getting bot connection info...")
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get("https://ifconfig.co/json") as resp:
                conn_data = await resp.json()

        country = conn_data["country"]
        region = conn_data["region_name"]
        timezone = conn_data["time_zone"]
        ip_hostname = conn_data["ip"]

        self._ip_hostname = ip_hostname
        self._host_country = country
        self._host_region = region
        self._host_tz = timezone

    @property
    def get_hostdata(self) -> HostingData:
        """Return the bot host data.

        Returns
        -------
        Host data: `dict`:
            A collection of dictionary that contains ip/country/region/tz.
        """
        return HostingData(self._ip_hostname, f"{self._host_region}, {self._host_country}", self._host_tz)
