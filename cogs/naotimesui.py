# A bridge between Showtimes and ShowtimesUI

import asyncio
import logging
import platform
import socket
from base64 import b64encode
from inspect import iscoroutinefunction
from typing import Union

import discord
import ujson
from discord.ext import commands, tasks

from nthelper.bot import naoTimesBot
from nthelper.utils import get_current_time


def maybe_int(data, fallback=None):
    if isinstance(data, int):
        return data
    try:
        return int(data)
    except ValueError:
        return fallback if isinstance(fallback, int) else data


class naoTimesUIBridge(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("cogs.naotimesui.Socket")

        self._authenticated_sid = getattr(self.bot, "naotimesui", [])
        naotimesui = bot.botconf.get("naotimesui", {}).get("socket", {})
        self._auth_passwd = naotimesui.get("password")
        self._socket_port = maybe_int(naotimesui.get("port", 25670))
        if not isinstance(self._socket_port, int):
            self._socket_port = 25670

        self.server = None
        self.server_lock = False
        self.run_server.start()

        self._event_map = {
            "authenticate": self.authenticate_user,
            "pull data": self.on_pull_data,
            "get server": self.get_server_info,
            "get user": self.get_user_info,
            "get channel": self.on_channel_info_request,
            "get user perms": self.get_user_server_permission,
            "create role": self.show_create_role,
            "announce drop": self.on_announce_request,
            "ping": self.on_ping,
        }

    def cog_unload(self):
        self.run_server.cancel()
        setattr(self.bot, "naotimesui", self._authenticated_sid)

    @staticmethod
    def hash_ip(addr):
        if addr is None:
            return "unknowniphashed"
        if isinstance(addr, (tuple, list)):
            addr = addr[0]
        if not isinstance(addr, str):
            if isinstance(addr, int):
                addr = str(addr)
            else:
                addr = ujson.dumps(addr, ensure_ascii=False)
        return b64encode(addr.encode("utf-8")).decode("utf-8")

    @staticmethod
    async def maybe_asyncute(cb, *args, **kwargs):
        real_func = cb
        if hasattr(real_func, "func"):
            real_func = cb.func
        if iscoroutinefunction(real_func):
            return await cb(*args, **kwargs)
        return cb(*args, **kwargs)

    @tasks.loop(seconds=1, count=1)
    async def run_server(self):
        if self.server_lock:
            return
        self.logger.info("starting ws server...")
        server = await asyncio.start_server(self.handle_message, "0.0.0.0", self._socket_port)
        if platform.system() == "Linux":
            server.sockets[0].setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 1)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 3)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
        elif platform.system() == "Darwin":
            TCP_KEEPALIVE = 0x10
            server.sockets[0].setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, TCP_KEEPALIVE, 3)
        elif platform.system() == "Windows":
            server.sockets[0].ioctl(socket.SIO_KEEPALIVE_VALS, (1, 10000, 3000))
        addr = server.sockets[0].getsockname()
        self.server_lock = True
        self.logger.info(f"serving on: {addr[0]}:{addr[1]}")
        self.server = server
        try:
            async with server:
                await server.serve_forever()
        except asyncio.CancelledError:
            self.logger.warning("close request received, shutting down...")
            self.server.close()
            await server.wait_closed()
        self.logger.info("server closed.")

    async def on_pull_data(self, sid, data):
        self.logger.info(f"{sid}: requested pull data for {data}")
        remote_data = await self.bot.ntdb.get_server(data)
        if not remote_data:
            self.logger.error(f"{sid}:{data}: unknown server, ignoring!")
            return
        await self.bot.redisdb.set(f"showtimes_{remote_data['id']}", remote_data)
        return "ok"

    def on_ping(self, sid, data):
        self.logger.info(f"{sid}: requested ping")
        return "pong"

    def _check_auth(self, sid):
        if self._auth_passwd is None:
            return True
        if sid not in self._authenticated_sid:
            return False
        return True

    def authenticate_user(self, sid, data):
        self.logger.info(f"trying to authenticating {sid}, comparing s::{data} and t::{self._auth_passwd}")
        if self._auth_passwd is None:
            self._authenticated_sid.append(sid)
            return "ok"
        if data == self._auth_passwd:
            self.logger.info(f"authenticated {sid}")
            self._authenticated_sid.append(sid)
            return "ok"
        return {"message": "not ok", "success": 0}

    def get_user_info(self, sid, data):
        self.logger.info(f"{sid}: requested user info for {data}")
        try:
            user_id = int(data)
        except (KeyError, ValueError, IndexError):
            return {"message": "not a number", "success": 0}
        user_data: Union[discord.User, None] = self.bot.get_user(user_id)
        if user_data is None:
            return {"message": "cannot find user", "success": 0}
        parsed_user = {}
        parsed_user["id"] = str(user_data.id)
        parsed_user["name"] = user_data.name
        parsed_user["avatar_url"] = str(user_data.avatar_url)
        return parsed_user

    async def on_announce_request(self, sid, data):
        self.logger.info(f"{sid}: requested anime drop announcement for {data}")
        try:
            server_id = data["id"]
            channel_id = data["channel_id"]
            anime_data = data["anime"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Kurang data untuk melakukan announce", "success": 0}
        try:
            anime_title = anime_data["title"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Tidak dapat menemukan judul anime di data `anime`", "success": 0}
        try:
            guild_id = int(server_id)
        except (KeyError, ValueError, IndexError):
            return {"message": "Server ID bukanlah angka", "success": 0}
        try:
            kanal_id = int(channel_id)
        except (KeyError, ValueError, IndexError):
            return {"message": "Channel ID bukanlah angka", "success": 0}
        guild_info: Union[discord.Guild, None] = self.bot.get_guild(guild_id)
        if guild_id is None:
            return {"message": "Tidak dapat menemukan server", "success": 0}
        channel: Union[discord.TextChannel, None] = guild_info.get_channel(kanal_id)
        if not isinstance(channel, discord.TextChannel):
            return {"message": "Kanal bukanlah kanal teks", "success": 0}
        embed = discord.Embed(title=anime_title, color=0xB51E1E)
        embed.add_field(
            name="Dropped...", value=f"{anime_title} telah di drop dari Fansub ini :(", inline=False,
        )
        embed.set_footer(text=f"Pada: {get_current_time()}")
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass
        return "ok"

    def on_channel_info_request(self, sid, data):
        self.logger.info(f"{sid}: requested channel info for {data}")
        try:
            channel_id = int(data["id"])
            server_id = int(data["server"])
        except (KeyError, ValueError, IndexError):
            return {"message": "ID bukanlah angka", "success": 0}
        guild_info: Union[discord.Guild, None] = self.bot.get_guild(server_id)
        if guild_info is None:
            return {"message": "Tidak dapat menemukan server", "success": 0}
        channel_info: Union[discord.abc.GuildChannel, None] = guild_info.get_channel(channel_id)
        if channel_info is None:
            return {"message": "Tidak dapat menemukan channel", "success": 0}
        if not isinstance(channel_info, discord.TextChannel):
            return {"message": "Channel bukan TextChannel", "success": 0}
        return {"id": str(channel_info.id), "name": channel_info.name}

    async def show_create_role(self, sid, data):
        self.logger.info(f"{sid}: requested role creation for {data}")
        try:
            server_id = data["id"]
            role_name = data["name"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Gagal unpack data dari server", "success": 0}
        try:
            guild_id = int(server_id)
        except (KeyError, ValueError, IndexError):
            return {"message": "ID bukanlah angka", "success": 0}
        guild_info: Union[discord.Guild, None] = self.bot.get_guild(guild_id)
        if guild_info is None:
            return {"message": "Tidak dapat menemukan server", "success": 0}
        try:
            new_guild_id = await guild_info.create_role(
                name=role_name, mentionable=True, colour=discord.Colour.random()
            )
        except discord.Forbidden:
            return {
                "message": "Bot naoTimes tidak memiliki akses untuk membuat role di server anda.",
                "success": 0,
            }
        except discord.HTTPException:
            return {
                "message": "Bot naoTimes tidak dapat membuat role tersebut, mohon coba sesaat lagi.",
                "success": 0,
            }
        return {"id": str(new_guild_id.id), "name": new_guild_id.name}

    def get_user_server_permission(self, sid, data):
        self.logger.info(f"{sid}: requested member perms info for {data}")
        try:
            server_id = data["id"]
            admin_id = data["admin"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Gagal unpack data dari server", "success": 0}
        try:
            guild_id = int(server_id)
            user_id = int(admin_id)
        except (KeyError, ValueError, IndexError):
            return {"message": "ID bukanlah angka", "success": 0}
        guild_info: Union[discord.Guild, None] = self.bot.get_guild(guild_id)
        if guild_info is None:
            return {"message": "cannot find server", "success": 0}
        member_info: Union[discord.Member, None] = guild_info.get_member(user_id)
        if member_info is None:
            return {"message": "cannot find member", "success": 0}
        perms_sets = member_info.guild_permissions
        user_perms = []
        for perm_name, perm_val in perms_sets:
            if perm_val:
                user_perms.append(perm_name)
        if isinstance(guild_info.owner, discord.Member):
            if str(guild_info.owner.id) == str(member_info.id):
                user_perms.append("owner")
        return user_perms

    def get_server_info(self, sid, data):
        self.logger.info(f"{sid}: requested server info for {data}")
        try:
            guild_id = int(data)
        except (KeyError, ValueError, IndexError):
            return {"message": "not a number", "success": 0}
        guild_info: Union[discord.Guild, None] = self.bot.get_guild(guild_id)
        if guild_info is None:
            return {"message": "cannot find server", "success": 0}
        guild_parsed = {}
        guild_parsed["name"] = guild_info.name
        guild_parsed["icon_url"] = str(guild_info.icon_url)
        guild_parsed["id"] = str(guild_info.id)
        owner_info = {}
        if guild_info.owner:
            owner_data: discord.Member = guild_info.owner
            owner_info["id"] = str(owner_data.id)
            owner_info["name"] = owner_data.name
            owner_info["avatar_url"] = str(owner_data.avatar_url)
        guild_parsed["owner"] = owner_info
        return guild_parsed

    @staticmethod
    def parse_json(recv_bytes: bytes):
        if b"\x04" == recv_bytes[-len(b"\x04") :]:
            recv_bytes = recv_bytes[: -len(b"\x04")]
        decoded = recv_bytes.decode("utf-8").strip()
        return ujson.loads(decoded)

    @staticmethod
    def encode_message(any_data) -> bytes:
        if isinstance(any_data, tuple):
            any_data = list(any_data)
        if isinstance(any_data, (list, dict)):
            any_data = ujson.dumps(any_data)
        elif isinstance(any_data, (int, float)):
            any_data = str(any_data)
        elif isinstance(any_data, bytes):
            if b"\x04" != any_data[-len(b"\x04") :]:
                any_data = any_data + b"\x04"
            return any_data
        return any_data.encode("utf-8") + b"\x04"

    async def on_message_emitter(self, sid: str, recv_data: bytes):
        parsed = self.parse_json(recv_data)
        if not isinstance(parsed, dict):
            return {"message": "unknown message received", "success": 0, "event": None}
        if "event" not in parsed:
            return {"message": "unknown event", "success": 0, "event": None}
        event = parsed["event"]
        if event == "ping":
            parsed["data"] = None
        is_auth = self._check_auth(sid)
        if not is_auth and event != "authenticate":
            return {"message": "not authenticated", "success": -1, "event": event}
        if "data" not in parsed:
            return {"message": "no data received", "success": 0, "event": event}
        data = parsed["data"]
        callback = self._event_map.get(event)
        if not callable(callback):
            return {"message": "unknown event, ignored", "success": 1, "event": event}
        try:
            res = await self.maybe_asyncute(callback, sid, data)
        except Exception as e:
            return {
                "message": f"An error occured while trying to execute callback, {str(e)}",
                "success": 0,
                "event": event,
            }
        if isinstance(res, object):
            if "success" in res and "message" in res:
                return {**res, "event": event}
            elif "success" in res:
                return {
                    "message": "success" if res["success"] == 1 else "failed",
                    "success": res["success"],
                    "event": event,
                }
            elif "message" in res:
                return {"message": res["message"], "success": 1, "event": "event"}
        return {"message": res, "success": 1, "event": event}

    async def handle_message(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.logger.info("request received, reading data...")
        try:
            data = await reader.readuntil(b"\x04")
            addr = writer.get_extra_info("peername")
            answer = await self.on_message_emitter(self.hash_ip(addr), data)
        except asyncio.IncompleteReadError:
            self.logger.error("incomplete data acquired")
            answer = {"message": "incomplete data received", "status": 0}
        writer.write(self.encode_message(answer))
        await writer.drain()
        writer.close()


def setup(bot: naoTimesBot):
    bot.add_cog(naoTimesUIBridge(bot))
