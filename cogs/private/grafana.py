from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional, Union

import discord
import orjson
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot
from naotimes.utils import blocking_write_files, write_files

TEXTFILE_DIRECTORY = "/media/sdac/mizore/private/discord-bot/grafana/node_exporter"
if os.name == "nt":
    TEXTFILE_DIRECTORY = os.path.join(os.getenv("HOME"), "node_exporter")


def escape_string(value: str) -> str:
    return value.replace('"', '\\"').replace("'", "\\'")


@dataclass
class Collector:
    id: str
    description: str
    value: Union[str, int, float, dict] = 0.0
    registry: Optional[GrafanaCollector] = None

    def __post_init__(self):
        if self.registry is not None:
            self.registry.bind(self)

    def incr(self):
        if isinstance(self.value, (int, float)):
            self.value += 1

    def decr(self):
        if isinstance(self.value, (int, float)):
            self.value -= 1

    def set(self, value: Union[str, int, dict, str]):
        self.value = value

    def is_info(self):
        return isinstance(self.value, (str, dict))

    def _as_dict(self, key: str, value: str):
        return key + '="' + escape_string(str(value)) + '"'

    def _internal_export(self):
        if isinstance(self.value, (int, float)):
            return f" {float(self.value)}"
        elif isinstance(self.value, str):
            return "{" + self._as_dict("value", self.value) + "} 1.0"
        elif isinstance(self.value, dict):
            parsed_json = []
            for key, value in self.value.items():
                if isinstance(value, (int, float, str)):
                    parsed_json.append(self._as_dict(key, value))
                else:
                    parsed_json.append(self._as_dict(key, orjson.dumps(value).decode("utf-8")))
            merged_json = ",".join(parsed_json)
            return "{" + merged_json + "} 1.0"
        return " 1.0"

    def export(self):
        id_name = self.id
        if self.is_info():
            id_name += "_info"
        RETURN_VALUE = f"# HELP {id_name} {self.description}"
        RETURN_VALUE += f"\n# TYPE {id_name} gauge"
        RETURN_VALUE += f"\n{id_name}{self._internal_export()}"
        return RETURN_VALUE


class GrafanaCollector:
    def __init__(self):
        self._collector: List[Collector] = []

    @property
    def collector(self):
        return self._collector

    def bind(self, collector: Collector):
        self._collector.append(collector)

    def export(self):
        joined = []
        for collector in self._collector:
            joined.append(collector.export())
        return "\n".join(joined) + "\n"


class PrivateGrafanaProm(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.collector = GrafanaCollector()
        self.logger = logging.getLogger("Private.Grafana")
        os.makedirs(TEXTFILE_DIRECTORY, exist_ok=True)
        self._save_path = os.path.join(TEXTFILE_DIRECTORY, "naotimes.prom")

        self._lock = asyncio.Lock()

        self.all_collector = {
            "ping": Collector("naotimes_ws_ping", "The websocket ping", registry=self.collector),
            "server": Collector(
                "naotimes_server_total",
                "The total of the server available in naoTimes",
                registry=self.collector,
            ),
            "users": Collector(
                "naotimes_user_total", "The total of all user that can use naoTimes", registry=self.collector
            ),
            "commands": Collector(
                "naotimes_command_total", "The total of available command to use", registry=self.collector
            ),
            "owner": Collector("naotimes_owner", "The main owner of the Bot", registry=self.collector),
            "showtimes": Collector(
                "naotimes_showtimes_total", "Total server using Showtimes service", registry=self.collector
            ),
            "showtimes_anime": Collector(
                "naotimes_showtimes_anime_total", "Total anime/project registered", registry=self.collector
            ),
            "discord_version": Collector(
                "naotimes_discord_version",
                "The version of the discord.py being used",
                registry=self.collector,
            ),
            "python_version": Collector(
                "naotimes_python_version", "Python version being used by the bot", registry=self.collector
            ),
            "naotimes_version": Collector(
                "naotimes_version", "The version of the bot", registry=self.collector
            ),
        }

        self.update_metrics.start()

    def cog_unload(self):
        self.update_metrics.cancel()
        blocking_write_files(self.collector.export(), self._save_path)

    async def async_write_textfiles(self):
        tmppath = "%s.%s.%s" % (self._save_path, os.getpid(), threading.current_thread().ident)
        self.logger.info(f"Saving grafana stats to: {self._save_path}")
        try:
            await write_files(self.collector.export(), tmppath)
        except ValueError:
            return

        if os.name == "nt":
            if sys.version_info <= (3, 3):
                try:
                    os.remove(self._save_path)
                except FileNotFoundError:
                    pass
                os.rename(tmppath, self._save_path)
            else:
                os.replace(tmppath, self._save_path)
        else:
            os.rename(tmppath, self._save_path)

    @tasks.loop(seconds=30.0)
    async def update_metrics(self):
        # Make sure no dupes
        async with self._lock:
            ws_ping = self.bot.latency
            bot_version = self.bot.semver

            if ws_ping == float("nan"):
                ws_ping = 9999.99

            server_lists: List[discord.Guild] = self.bot.guilds

            users_lists = []
            total_channels = 0
            for srv in server_lists:
                total_channels += len(srv.channels)
                for user in srv.members:
                    if not user.bot and user.id not in users_lists:
                        users_lists.append(user.id)

            showtimes_servers = await self.bot.redisdb.getall("showtimes_*")
            showtimes_projects = []
            for server in showtimes_servers:
                if "anime" in server and isinstance(server["anime"], list):
                    for anime in server["anime"]:
                        if anime["id"] not in showtimes_projects:
                            showtimes_projects.append(anime["id"])

            all_commands: List[commands.Command] = self.bot.commands
            disallowed_cmds = []
            for command in all_commands:
                if command.checks:
                    for check in command.checks:
                        primitive = check.__str__()
                        if "is_owner" in primitive:
                            disallowed_cmds.append(command)

            command_total = len(all_commands) - len(disallowed_cmds)
            py3_ver = sys.version_info
            merged_version = f"{py3_ver.major}.{py3_ver.minor}.{py3_ver.micro}"

            # Register all possession
            self.all_collector["ping"].set(ws_ping)
            self.all_collector["server"].set(len(server_lists))
            self.all_collector["users"].set(len(users_lists))
            self.all_collector["owner"].set({"name": str(self.bot._owner)})
            self.all_collector["commands"].set(command_total)
            self.all_collector["showtimes"].set(len(showtimes_servers))
            self.all_collector["showtimes_anime"].set(len(showtimes_projects))
            self.all_collector["discord_version"].set({"version": discord.__version__})
            self.all_collector["python_version"].set({"version": merged_version})
            self.all_collector["naotimes_version"].set({"version": bot_version})

            await self.async_write_textfiles()


def setup(bot: naoTimesBot):
    bot.add_cog(PrivateGrafanaProm(bot))
