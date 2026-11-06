from __future__ import annotations

import asyncio
import logging
import math
import os
import pathlib
import sys
import threading
from dataclasses import dataclass

import discord
import orjson
import wavelink
from anyio import Path as AsyncPath
from discord import app_commands
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot
from naotimes.utils import write_files

HERE_DIR = pathlib.Path(__file__).parent.resolve().parent.parent
TEXTFILE_DIRECTORY = HERE_DIR / "logs" / "node_exporter"


def escape_string(value: str) -> str:
    return value.replace('"', '\\"').replace("'", "\\'")


@dataclass
class Collector:
    id: str
    description: str
    value: str | int | float | dict = 0.0
    registry: GrafanaCollector | None = None

    def __post_init__(self):
        if self.registry is not None:
            self.registry.bind(self)

    def incr(self):
        if isinstance(self.value, (int, float)):
            self.value += 1

    def decr(self):
        if isinstance(self.value, (int, float)):
            self.value -= 1

    def set(self, value: str | int | float | dict):
        self.value = value

    def is_info(self):
        return isinstance(self.value, (str, dict))

    def _as_dict(self, key: str, value: str | int | float):
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
    def __init__(self, save_path: str):
        self._collector: list[Collector] = []
        self._save_path = save_path
        self._lock = asyncio.Lock()

    async def __aenter__(self, *args, **kwargs):
        await self._lock.acquire()

    async def __aexit__(self, *args, **kwargs):
        try:
            self._lock.release()
        except RuntimeError:
            pass

    @property
    def save_path(self):
        return self._save_path

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


def _count_through_users(guilds: list[discord.Guild]):
    valid_users: list[int] = []
    for guild in guilds:
        for member in guild.members:
            if not member.bot and member.id not in valid_users:
                valid_users.append(member.id)
    return len(valid_users)


def _count_through_channels(guilds: list[discord.Guild]):
    channel_count = 0
    for guild in guilds:
        channel_count += len(guild.channels)
    return channel_count


def _count_through_showtimes(showtimes_servers: list[dict]):
    showtimes_projects = []
    for server in showtimes_servers:
        if "anime" in server and isinstance(server["anime"], list):
            for anime in server["anime"]:
                if anime["id"] not in showtimes_projects:
                    showtimes_projects.append(anime["id"])
    return len(showtimes_projects)


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


class PrivateGrafanaProm(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Private.Grafana")
        pathlib.Path(TEXTFILE_DIRECTORY).mkdir(exist_ok=True, parents=True)
        self.ntcollector = GrafanaCollector(str(pathlib.Path(TEXTFILE_DIRECTORY) / "naotimes.prom"))
        self.lavacollector = GrafanaCollector(str(pathlib.Path(TEXTFILE_DIRECTORY) / "naotimes_lava.prom"))

        self.all_collector = {
            "ping": Collector("naotimes_ws_ping", "The websocket ping", registry=self.ntcollector),
            "server": Collector(
                "naotimes_server_total",
                "The total of the server available in naoTimes",
                registry=self.ntcollector,
            ),
            "users": Collector(
                "naotimes_user_total",
                "The total of all user that can use naoTimes",
                registry=self.ntcollector,
            ),
            "channels": Collector(
                "naotimes_channel_total",
                "The total of all channel that are viewable by naoTimes",
                registry=self.ntcollector,
            ),
            "commands": Collector(
                "naotimes_command_total", "The total of available command to use", registry=self.ntcollector
            ),
            "owner": Collector("naotimes_owner", "The main owner of the Bot", registry=self.ntcollector),
            "showtimes": Collector(
                "naotimes_showtimes_total", "Total server using Showtimes service", registry=self.ntcollector
            ),
            "showtimes_anime": Collector(
                "naotimes_showtimes_anime_total", "Total anime/project registered", registry=self.ntcollector
            ),
            "discord_version": Collector(
                "naotimes_discord_version",
                "The version of the discord.py being used",
                registry=self.ntcollector,
            ),
            "python_version": Collector(
                "naotimes_python_version", "Python version being used by the bot", registry=self.ntcollector
            ),
            "naotimes_version": Collector("naotimes_version", "The version of the bot", registry=self.ntcollector),
        }

        self.all_lava_collector = {
            "player_count": Collector(
                "naotimes_player_count",
                "The total of players currently connected to the lava server",
                registry=self.lavacollector,
            ),
            "queued_songs": Collector(
                "naotimes_inqueue",
                "Total songs are in queue and waiting to be played.",
                registry=self.lavacollector,
            ),
        }

        self._created_tasks: list[asyncio.Task] = []

        self.update_metrics.start()
        self.update_music_player_metrics.start()

    async def cog_unload(self):
        self.update_metrics.cancel()
        self.update_music_player_metrics.cancel()
        await self.async_write_textfiles(self.ntcollector)
        await self.async_write_textfiles(self.lavacollector)
        for task in self._created_tasks:
            task.cancel()

    async def async_write_textfiles(self, collector: GrafanaCollector):
        tmppath = "%s.%s.%s" % (collector.save_path, os.getpid(), threading.current_thread().ident)
        self.logger.info(f"Saving grafana stats to: {collector.save_path}")
        try:
            await write_files(collector.export(), tmppath)
        except ValueError:
            return

        temp_file = AsyncPath(tmppath)
        save_file = AsyncPath(collector.save_path)
        if os.name == "nt":
            await temp_file.replace(save_file)
        else:
            await temp_file.rename(save_file)

    def on_save_task_done(self, task: asyncio.Task):
        task_name = task.get_name()
        try:
            self._created_tasks.remove(task)
            self.logger.info(f"Metrics save task finished for {task_name}")
        except Exception:
            self.logger.error(f"Unable to deregister task {task_name}")

    @tasks.loop(seconds=60.0)
    async def update_music_player_metrics(self):
        # Make sure no dupes
        async with self.lavacollector:
            all_active_players = 0
            all_nodes = wavelink.Pool.nodes
            for node in all_nodes.values():
                node_stats = getattr(node, "stats", None)
                if node_stats is not None:
                    all_active_players += getattr(node_stats, "playing_players", 0)

            queued_songs = 0
            if self.bot.ntplayer is not None:
                for instance in self.bot.ntplayer.actives.values():
                    queued_songs += instance.queue.qsize()

            # Register all possessions
            self.all_lava_collector["player_count"].set(all_active_players)
            self.all_lava_collector["queued_songs"].set(queued_songs)

            task = self.bot.loop.create_task(self.async_write_textfiles(self.lavacollector), name="lava-collector-mk1")
            task.add_done_callback(self.on_save_task_done)
            self._created_tasks.append(task)

    @tasks.loop(seconds=60.0)
    async def update_metrics(self):
        # Make sure no dupes
        async with self.ntcollector:
            loop = self.bot.loop
            ws_ping = self.bot.latency
            bot_version = self.bot.semver

            if math.isnan(ws_ping):
                ws_ping = 9999.99

            server_lists = list(self.bot.guilds)

            user_count = await loop.run_in_executor(None, _count_through_users, server_lists)
            total_channels = await loop.run_in_executor(None, _count_through_channels, server_lists)

            showtimes_servers = await self.bot.redisdb.getall("showtimes_*") if self.bot.redisdb is not None else []
            showproject_count = await loop.run_in_executor(None, _count_through_showtimes, showtimes_servers)

            command_total = await self.bot.loop.run_in_executor(None, _count_all_commands, self.bot)
            py3_ver = sys.version_info
            merged_version = f"{py3_ver.major}.{py3_ver.minor}.{py3_ver.micro}"

            # Register all possession
            self.all_collector["ping"].set(ws_ping)
            self.all_collector["server"].set(len(server_lists))
            self.all_collector["users"].set(user_count)
            self.all_collector["channels"].set(total_channels)
            self.all_collector["owner"].set({"name": str(self.bot._owner)})
            self.all_collector["commands"].set(command_total)
            self.all_collector["showtimes"].set(len(showtimes_servers))
            self.all_collector["showtimes_anime"].set(showproject_count)
            self.all_collector["discord_version"].set({"version": discord.__version__})
            self.all_collector["python_version"].set({"version": merged_version})
            self.all_collector["naotimes_version"].set({"version": bot_version})

            task = self.bot.loop.create_task(
                self.async_write_textfiles(self.ntcollector), name="naotimes-collector-mk1"
            )
            task.add_done_callback(self.on_save_task_done)
            self._created_tasks.append(task)


async def setup(bot: naoTimesBot):
    try:
        await AsyncPath(TEXTFILE_DIRECTORY).mkdir(exist_ok=True, parents=True)
    except OSError as exc:
        bot.logger.warning(f"Grafana textfile directory unavailable ({exc}), not loading the Grafana exporter.")
        return
    await bot.add_cog(PrivateGrafanaProm(bot))
