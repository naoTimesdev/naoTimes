import logging
from typing import Any, List, Union
from urllib.parse import urlparse

import discord
import feedparser
from discord.ext import commands
from schema import SchemaError

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.showtimes import FansubRSS, FansubRSSEmbed, FansubRSSFeed, Showtimes
from naotimes.socket import ntsocket
from naotimes.utils import generate_custom_code, get_current_time

from .fansubrss import fansubRSSSchemas, normalize_rss_data


class ShowtimesUIBridge(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.nTUIBridge")

    # pull data
    @ntsocket("pull data")
    async def on_pull_data(self, sid: str, data: str):
        self.logger.info(f"{sid}: requested pull data for {data}")
        remote_data = await self.bot.ntdb.get_server(data)
        if remote_data is None:
            self.logger.error(f"{sid}:{data}: unknown server, ignoring!")
            return {"message": "Unknown server", "success": 0}
        await self.bot.redisdb.set(f"showtimes_{remote_data.id}", remote_data.serialize())
        return "ok"

    # pull admin
    @ntsocket("pull admin")
    async def on_pull_admin_data(self, sid: str, data: str):
        self.logger.info(f"{sid}: requested pull admin data for {data}")
        remote_data = await self.bot.ntdb.get_admin(data)
        if remote_data is None:
            self.logger.error(f"{sid}:{data}: unknown admin, ignoring!")
            return {"message": "Unknown admin", "success": 0}
        await self.bot.redisdb.set(f"showadmin_{remote_data.id}", remote_data.serialize())
        return "ok"

    # get server
    @ntsocket("get server")
    def on_discord_server_request(self, sid: str, data: str):
        self.logger.info(f"{sid}: requested server info for {data}")
        try:
            guild_id = int(data)
        except (KeyError, ValueError, IndexError):
            return {"message": "not a number", "success": 0}

        guild_info = self.bot.get_guild(guild_id)
        if guild_info is None:
            return {"message": "Unknown server", "success": 0}

        ikon = guild_info.icon
        if ikon is not None:
            ikon = str(ikon)

        guild_parsed = {}
        guild_parsed["id"] = str(guild_info.id)
        guild_parsed["name"] = guild_info.name
        guild_parsed["icon_url"] = ikon
        owner_data = guild_info.owner
        owner_info = {}
        if owner_data is not None:
            owner_info["id"] = str(owner_data.id)
            owner_info["name"] = owner_data.name
            owner_info["avatar_url"] = str(owner_data.avatar)
        guild_parsed["owner"] = owner_info
        return {"message": guild_parsed, "success": 1}

    # get servers (fetch all showtimes server)
    @ntsocket("get servers")
    async def on_showtimes_server_request(self, sid: str):
        self.logger.info(f"{sid}: requested all server info")
        showtimes_server = await self.bot.redisdb.getall("showtimes_*")
        all_server = []
        for server in showtimes_server:
            if not server:
                continue
            all_server.append(
                {
                    "id": server.get("id"),
                    "name": server.get("name"),
                }
            )
        return all_server

    # get user
    @ntsocket("get user")
    def on_discord_user_info(self, sid: str, data: str):
        self.logger.info(f"{sid}: requested user info for {data}")
        try:
            user_id = int(data)
        except (KeyError, ValueError, IndexError):
            return {"message": "not a number", "success": 0}

        user_info = self.bot.get_user(user_id)
        if user_info is None:
            return {"message": "Unknown user", "success": 0}
        user_parsed = {}
        user_parsed["id"] = str(user_info.id)
        user_parsed["name"] = user_info.name
        user_parsed["avatar_url"] = str(user_info.avatar)
        user_parsed["is_bot"] = user_info.bot
        return {"message": user_parsed, "success": 1}

    # get user perms
    @ntsocket("get user perms")
    def on_discord_user_perms(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested user perms for {data}")
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

        guild_info = self.bot.get_guild(guild_id)
        if guild_info is None:
            return {"message": "Guild tidak dapat ditemukan", "success": 0}
        member_info = guild_info.get_member(user_id)
        if member_info is None:
            return {"message": "User tidak dapat ditemukan", "success": 0}

        perms_sets = member_info.guild_permissions
        user_perms = []
        for perm_name, perm_val in perms_sets:
            if perm_val:
                user_perms.append(perm_name)
        if isinstance(guild_info.owner, discord.Member):
            if guild_info.owner == member_info:
                user_perms.append("owner")
        return {"message": user_perms, "success": 1}

    # get channel
    @ntsocket("get channel")
    def on_channel_info_request(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested channel info for {data}")
        try:
            channel_id = int(data["id"])
            server_id = int(data["server"])
        except (KeyError, ValueError, IndexError):
            return {"message": "ID bukanlah angka", "success": 0}
        guild_info = self.bot.get_guild(server_id)
        if guild_info is None:
            return {"message": "Guild tidak dapat ditemukan", "success": 0}
        channel_info = guild_info.get_channel(channel_id)
        if channel_info is None:
            return {"message": "Kanal tidak dapat ditemukan", "success": 0}
        if not isinstance(channel_info, discord.TextChannel):
            return {"message": "Kanal yang dipilih bukanlah kanal teks", "success": 0}
        channel_parsed = {}
        channel_parsed["id"] = str(channel_info.id)
        channel_parsed["name"] = channel_info.name
        return {"message": channel_parsed, "success": 1}

    # get server channels (get all text channel in a server)
    @ntsocket("get server channel")
    def on_channel_list_request(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested channel info for {data}")
        try:
            server_id = int(data["id"])
        except (KeyError, ValueError, IndexError):
            return {"message": "ID bukanlah angka", "success": 0}
        guild_info = self.bot.get_guild(server_id)
        if guild_info is None:
            return {"message": "Guild tidak dapat ditemukan", "success": 0}
        text_channels = []
        for kanal in guild_info.channels:
            if isinstance(kanal, discord.TextChannel):
                text_channels.append({"id": str(kanal.id), "name": kanal.name})
        return {"message": text_channels, "success": 1}

    # get user servers and return that have valid access
    @ntsocket("get user privileged")
    async def on_user_privileged_servers(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested user privileged servers for {data}")
        try:
            user_id = int(data["id"])
        except (KeyError, ValueError, IndexError):
            return {"message": "ID bukanlah angka", "success": 0}
        try:
            server_selected = data["servers"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Gagal unpack data dari server", "success": 0}

        if not isinstance(server_selected, list):
            return {"message": "Data server yang dipilih bukan list", "success": 0}

        unregistered_servers = []
        registered_servers = []
        for server in server_selected:
            try:
                server_id = int(server)
            except (KeyError, ValueError, IndexError):
                continue
            guild_info = self.bot.get_guild(server_id)
            if guild_info is None:
                continue
            member_info = guild_info.get_member(user_id)
            if member_info is None:
                continue
            showtimes_info = await self.bot.showqueue.fetch_database(server_id)
            if showtimes_info is None:
                perms_sets = member_info.guild_permissions
                if isinstance(guild_info.owner, discord.Member):
                    if guild_info.owner == member_info:
                        unregistered_servers.append(
                            {"id": str(server_id), "name": guild_info.name, "avatar": str(guild_info.icon)}
                        )
                        continue
                user_perms = []
                for perm_name, perm_val in perms_sets:
                    if perm_val:
                        user_perms.append(perm_name)
                if (
                    "manage_guild" in user_perms
                    or "manage_server" in user_perms
                    or "administrator" in user_perms
                ):
                    unregistered_servers.append(
                        {"id": str(server_id), "name": guild_info.name, "avatar": str(guild_info.icon)}
                    )
            else:
                if showtimes_info.is_admin(user_id):
                    registered_servers.append(
                        {"id": str(server_id), "name": guild_info.name, "avatar": str(guild_info.icon)}
                    )

        return {"message": {"r": registered_servers, "u": unregistered_servers}, "success": 1}

    # create role
    @ntsocket("create role")
    async def on_role_creation_request(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested role creation for {data}")
        try:
            server_id = data["id"]
            role_name = data["name"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Gagal unpack data dari server", "success": 0}
        try:
            guild_id = int(server_id)
        except (KeyError, ValueError, IndexError):
            return {"message": "ID server bukanlah angka", "success": 0}

        guild_info = self.bot.get_guild(guild_id)
        if guild_info is None:
            return {"message": "Guild tidak dapat ditemukan", "success": 0}

        # Let's check if we can find role with matching name
        role_found = None
        for role in guild_info.roles:
            if role.name == role_name:
                role_found = role
                break

        if role_found is not None:
            # Role already exist, lets return this one shall we?
            role_info = {
                "id": str(role_found.id),
                "name": role_found.name,
            }
            return {"message": role_info, "success": 1}

        # Role not found, let's create it
        try:
            new_guild_role = await guild_info.create_role(
                name=role_name, mentionable=True, colour=discord.Color.random()
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
        role_info = {
            "id": str(new_guild_role.id),
            "name": new_guild_role.name,
        }
        return {"message": role_info, "success": 1}

    # announce drop
    @ntsocket("announce drop")
    async def on_announce_drop_request(self, sid: str, data: dict):
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

        guild_info = self.bot.get_guild(guild_id)
        if guild_info is None:
            return {"message": "Guild tidak dapat ditemukan", "success": 0}
        channel_info = guild_info.get_channel(kanal_id)
        if channel_info is None:
            return {"message": "Kanal tidak dapat ditemukan", "success": 0}
        embed = discord.Embed(title=anime_title, color=0xB51E1E)
        embed.add_field(
            name="Dropped...",
            value=f"{anime_title} telah di drop dari Fansub ini :(",
            inline=False,
        )
        embed.set_footer(text=f"Pada: {get_current_time()}")
        try:
            await channel_info.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass
        return "ok"

    # delete server (showtimes)
    @ntsocket("delete server")
    async def on_delete_server_request(self, sid: str, data: str):
        self.logger.info(f"{sid}: requested server deletion for {data}")
        await self.bot.redisdb.rm(f"showtimes_{data}")
        return "ok"

    # delete admin (showtimes)
    @ntsocket("delete admin")
    async def on_delete_server_admin_request(self, sid: str, data: str):
        self.logger.info(f"{sid}: requested supermod removal for {data}")
        await self.bot.redisdb.rm(f"showadmin_{data}")
        return "ok"

    # delete role, delete roles (showtimes)
    @ntsocket("delete role")
    @ntsocket("delete roles")
    async def on_role_deletion_request(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested role deletion for {data}")
        try:
            server_id = int(data["id"])
            roles_list = data["roles"]
            if isinstance(roles_list, str):
                roles_list = [roles_list]
            fixed_roles = []
            for role in roles_list:
                try:
                    fixed_roles.append(int(role))
                except ValueError:
                    pass
        except (KeyError, ValueError, IndexError):
            return {"message": "ID bukanlah angka", "success": 0}

        guild_info = self.bot.get_guild(server_id)
        if guild_info is None:
            return {"message": "Guild tidak dapat ditemukan", "success": 0}

        for role in fixed_roles:
            role_info = guild_info.get_role(role)
            if role_info is not None:
                try:
                    await role_info.delete(reason="Showtimes project got deleted")
                except (discord.Forbidden, discord.HTTPException):
                    pass
        return "ok"

    # fsrss get (fansubrss)
    @ntsocket("fsrss get")
    async def on_fansubrss_get_event(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested fansubrss data for {data}")
        try:
            server_id = data["id"]
        except (KeyError, ValueError, IndexError):
            return {"message": "missing data", "success": 0}
        try:
            hash_id = data["hash"]
        except (KeyError, ValueError, IndexError):
            hash_id = None

        rss_metadata = await self.bot.redisdb.get(f"ntfsrss_{server_id}")
        if rss_metadata is None:
            return {"message": None, "success": 1}
        parsed_rss = FansubRSS.from_dict(server_id, rss_metadata)

        if hash_id is None:
            return {"message": parsed_rss.serialize(), "success": 1}

        select_feed = parsed_rss.get_feed(hash_id)
        if select_feed is None:
            return {"message": None, "success": 1}
        return {
            "message": {"feeds": [select_feed.serialize()], "premium": parsed_rss.has_premium},
            "success": 1,
        }

    # fsrss parse (fansubrss)
    @ntsocket("fsrss parse")
    async def on_fansubrss_parse_event(self, sid: str, data: Any):
        self.logger.info(f"{sid}: requested fansubrss parsing...")
        parsed = feedparser.parse(data)
        if parsed is None:
            return {"message": "RSS tidak valid", "success": 0}
        if not parsed.entries:
            return {"message": "RSS tidak memiliki entri", "success": 0}

        base_url = parsed["feed"]["link"]
        parsed_base_url = urlparse(base_url)

        skema_uri = parsed_base_url.scheme
        if skema_uri == "":
            skema_uri = "http"
        base_url_for_real = f"{skema_uri}://{parsed_base_url.netloc}"

        entries = parsed.entries

        filtered_entries = []
        for entry in entries:
            filtered_entries.append(normalize_rss_data(entry, base_url_for_real))

        return {"message": filtered_entries, "success": 1}

    # fsrss create (fansubrss)
    @ntsocket("fsrss create")
    async def on_fansubrss_create_request(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested fansubrss creation for {data}")
        try:
            channel_id = data["channel"]
            feed_url = data["url"]
            server_id = data["id"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Missing data", "success": 0}

        valid_parsed = []
        try:
            sample_url = data["sample"]
            if isinstance(sample_url, list):
                correct_url = []
                for sample in sample_url:
                    if isinstance(sample, str):
                        correct_url.append(sample)
                valid_parsed.extend(correct_url)
        except (KeyError, ValueError, IndexError):
            pass

        try:
            guild_id = int(server_id)
        except (KeyError, ValueError, IndexError):
            return {"message": "id is not a number", "success": 0}
        try:
            kanal_id = int(channel_id)
        except (KeyError, ValueError, IndexError):
            return {"message": "channel is not a number", "success": 0}

        server = self.bot.get_guild(guild_id)
        if server is None:
            return {"message": "Tidak dapat menemukan server, mohon invite Bot!", "success": 0}
        channel = server.get_channel(kanal_id)
        if not isinstance(channel, discord.TextChannel):
            return {"message": "Kanal tersebut bukan merupakan kanal teks", "success": 0}

        rss_metadata = await self.bot.redisdb.get(f"ntfsrss_{server_id}")
        if rss_metadata is None:
            rss_metadata = {"feeds": [], "premium": []}
        parsed_metadata = FansubRSS.from_dict(server_id, rss_metadata)

        registered_hash = str(guild_id)[5:]
        registered_hash += generate_custom_code(10, True)
        new_feeds = {
            "id": registered_hash,
            "channel": channel_id,
            "feedUrl": feed_url,
            "message": r":newspaper: | Rilisan Baru: **{title}**\n{link}",
            "lastEtag": "",
            "lastModified": "",
            "embed": {},
        }
        parsed_metadata.add_feed(FansubRSSFeed.from_dict(new_feeds))

        try:
            fansubRSSSchemas.validate(parsed_metadata.serialize())
        except SchemaError as e:
            self.logger.error(f"Failed to validate feeds meta for {server_id}", exc_info=e)
            return {
                "message": "Gagal memvalidasi hasil perubahan baru, kemungkinan ada yang salah",
                "success": 0,
            }
        await self.bot.redisdb.set(f"ntfsrss_{server_id}", parsed_metadata.serialize())
        await self.bot.redisdb.set(f"ntfsrssd_{server_id}_{registered_hash}", {"fetchedURL": valid_parsed})

        return {"message": {"id": registered_hash}, "success": 1}

    # fsrss update (fansubrss)
    @ntsocket("fsrss update")
    async def on_fansubrss_update_request(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested fansubrss update for {data}")
        try:
            server_id = data["id"]
        except (KeyError, ValueError, IndexError):
            return {"message": "missing server ID", "success": 0}
        try:
            hash_id = data["hash"]
        except (KeyError, ValueError, IndexError):
            return {"message": "missing hash ID", "success": 0}
        try:
            changes: dict = data["changes"]
            if not isinstance(changes, dict):
                return {"message": "`changes` are not a dict", "success": 0}
        except (KeyError, ValueError, IndexError):
            return {"message": "missing `changes` data", "success": 0}

        rss_metadata = await self.bot.redisdb.get(f"ntfsrss_{server_id}")
        if rss_metadata is None:
            return {"message": "Tidak dapat menemukan server tersebut", "success": 0}

        parsed_metadata = FansubRSS.from_dict(server_id, rss_metadata)
        hash_feeds = parsed_metadata.get_feed(hash_id)
        if hash_feeds is None:
            return {"message": "Tidak dapat menemukan hash untuk RSS tersebut", "success": 0}

        allowed_keys = ["channel", "feedUrl", "message", "embed"]
        expected_data = {
            "channel": str,
            "feedUrl": str,
            "embed": dict,
            "message": str,
        }
        hash_serialized = hash_feeds.serialize()
        for change_key, change_value in changes.items():
            if change_key in allowed_keys:
                expected_fmt = expected_data[change_key]
                if not isinstance(change_value, expected_fmt):
                    return {"message": f"Data `{change_key}` memiliki value yang salah", "success": 0}
                hash_serialized[change_key] = change_value

        hash_feeds = FansubRSSEmbed.from_dict(hash_serialized)
        parsed_metadata.feeds = hash_feeds
        try:
            fansubRSSSchemas.validate(parsed_metadata.serialize())
        except SchemaError:
            self.logger.error(f"Failed to validate feeds meta for {server_id}")
            return {
                "message": "Gagal memvalidasi hasil perubahan baru, kemungkinan ada yang salah",
                "success": 0,
            }
        await self.bot.redisdb.set(f"ntfsrss_{server_id}", parsed_metadata.serialize())
        return "ok"

    # fsrss delete (fansubrss)
    @ntsocket("fsrss delete")
    async def on_fansubrss_deletion_request(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested deletion for {data}")
        try:
            hash_id = data["hash"]
            server_id = data["id"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Missing data", "success": 0}
        rss_metadata = await self.bot.redisdb.get(f"ntfsrss_{server_id}")
        if rss_metadata is None:
            return {"message": "Tidak dapat menemukan server tersebut", "success": 0}

        parsed_metadata = FansubRSS.from_dict(server_id, rss_metadata)
        parsed_metadata.remove_feed(hash_id)

        try:
            fansubRSSSchemas.validate(parsed_metadata.serialize())
        except SchemaError:
            self.logger.error(f"Failed to validate feeds meta for {server_id}")
            return {
                "message": "Gagal memvalidasi hasil perubahan baru, kemungkinan ada yang salah",
                "success": 0,
            }

        await self.bot.redisdb.rm(f"ntfsrssd_{server_id}_{hash_id}")
        await self.bot.redisdb.set(f"ntfsrss_{server_id}", parsed_metadata.serialize())
        return "ok"

    # collab create (showtimes)
    @ntsocket("collab create")
    async def on_showtimes_collab_confirmation(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested collab accept for {data}")
        try:
            collab_id = data["id"]
            server_id = data["target"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Missing data", "success": 0}

        target_srvdis: Union[discord.Guild, None] = None
        try:
            server_id = int(server_id)
            target_srvdis = self.bot.get_guild(server_id)
        except (AttributeError, ValueError, TypeError):
            return {"message": "Peladen target tidak dapat ditemukan!", "success": 0}

        if target_srvdis is None:
            return {"message": "Peladen target tidak dapat ditemukan!", "success": 0}

        srv_data = await self.bot.showqueue.fetch_database(server_id)
        if srv_data is None:
            return {"message": "Tidak dapat menemukan peladen target", "success": 0}

        if len(srv_data.konfirmasi) < 1:
            return {"message": "Tidak ada kolaborasi yang harus dikonfirmasi.", "success": 0}

        confirm_data = srv_data.get_konfirm(collab_id)
        if confirm_data is None:
            return {"message": "Tidak dapat menemukan kolaborasi tersebut", "success": 0}

        source_srv = await self.bot.showqueue.fetch_database(confirm_data.server)
        if source_srv is None:
            return {"message": "Tidak bisa menemukan peladen source?", "success": 0}

        selected_anime = source_srv.get_project(confirm_data.anime)
        if selected_anime is None:
            return {"message": "Tidak bisa menemukan anime tersebut", "success": 0}

        target_anime = srv_data.get_project(confirm_data.anime)

        anime_server_role = None
        old_collab_data = []
        if target_anime is not None:
            self.logger.warning(f"{sid}: existing project, changing with new one...")
            anime_server_role = target_anime.role
            old_collab_data.extend(target_anime.kolaborasi)

        if anime_server_role is None:
            self.logger.info(f"{sid}: no role, creating roles...")
            col = selected_anime.poster.color
            if col is None:
                real_color = discord.Color.random()
            else:
                real_color = discord.Color(col)
            c_role = await target_srvdis.create_role(
                name=selected_anime.title,
                color=real_color,
                mentionable=True,
            )
            anime_server_role = c_role.id

        mirror_data = selected_anime.copy()
        mirror_data.role = anime_server_role

        collab_data = [confirm_data.server, server_id]
        if len(old_collab_data) > 0:
            collab_data.extend(old_collab_data)
        collab_data = list(dict.fromkeys(collab_data))
        if len(selected_anime.kolaborasi) > 0:
            collab_data.extend(selected_anime.kolaborasi)
        collab_data = list(dict.fromkeys(collab_data))
        selected_anime.kolaborasi = collab_data
        source_srv.update_project(selected_anime)
        mirror_data.kolaborasi = collab_data
        srv_data.update_project(mirror_data)

        full_update: List[Showtimes] = []
        full_update.append(source_srv)
        for osrv in collab_data:
            if osrv in (confirm_data.server, server_id):
                continue
            osrv_data = await self.bot.showqueue.fetch_database(f"showtimes_{osrv}")
            if osrv_data is None:
                continue
            osrv_anime = osrv_data.get_project(mirror_data.id)
            if osrv_anime is None:
                continue
            osrv_anime.kolaborasi = collab_data
            osrv_data.update_project(osrv_anime)
            full_update.append(osrv_data)

        srv_data.remove_konfirm(collab_id)
        full_update.append(srv_data)

        self.logger.info(f"{sid}: collab accepted, updating all showtimes...")
        for update in full_update:
            await self.bot.redisdb.set(f"showtimes_{update.id}", update.serialize())

        self.logger.info(f"{sid}: updating showtimes main database...")
        for peladen in full_update:
            self.logger.info(f"{sid}:{peladen.id}: Updating database...")
            success, msg = await self.bot.ntdb.update_server(peladen)
            if not success:
                if peladen.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(peladen.id)
                self.logger.warning(f"{sid}:{peladen.id}: Failed to update database: {msg}")

        return "Kolaborasi sukses"

    # collab delete (showtimes)
    @ntsocket("collab delete")
    async def on_showtimes_collab_disconnect(self, sid: str, data: dict):
        self.logger.info(f"{sid}: requested collab disconnection for {data}")
        try:
            server_id = data["id"]
            anime_id = data["anime_id"]
        except (KeyError, ValueError, IndexError):
            return {"message": "Missing data", "success": 0}

        try:
            server_id = int(server_id)
            test_target = self.bot.get_guild(server_id)
            if test_target is None:
                return {"message": "Peladen target tidak dapat ditemukan!", "success": 0}
        except (AttributeError, ValueError, TypeError):
            return {"message": "Peladen target tidak dapat ditemukan!", "success": 0}

        srv_data = await self.bot.showqueue.fetch_database(server_id)
        if srv_data is None:
            return {"message": "Peladen tidak dapat ditemukan!", "success": 0}

        program_info = srv_data.get_project(anime_id)
        if program_info is None:
            return {"message": "Anime tidak dapat ditemukan!", "success": 0}

        if len(program_info.kolaborasi) < 1:
            return {"message": "Tidak ada kolaborasi sama sekali pada judul ini!", "success": 0}

        self.logger.info(f"{sid}: start removing server from other server...")
        update_queue: List[Showtimes] = []
        for osrv in program_info.kolaborasi:
            if osrv == server_id:
                continue
            osrv_data = await self.bot.showqueue.fetch_database(osrv)
            if osrv_data is None:
                continue
            osrv_anime = osrv_data.get_project(anime_id)
            if osrv_anime is None:
                continue
            try:
                osrv_anime.remove_kolaborator(server_id)
            except ValueError:
                pass

            if len(osrv_anime.kolaborasi) == 1 and osrv_anime.kolaborasi[0] == osrv:
                osrv_anime.kolaborasi = []

            osrv_data.update_project(osrv_anime)
            update_queue.append(osrv_data)

        program_info.fsdb = None
        program_info.kolaborasi = []
        srv_data.update_project(program_info)
        update_queue.append(srv_data)

        self.logger.info(f"{sid}: storing new data to database...")
        for peladen in update_queue:
            await self.bot.redisdb.set(f"showtimes_{peladen.id}", peladen.serialize())

        self.logger.info(f"{sid}: updating showtimes main database...")
        for peladen in update_queue:
            self.logger.info(f"{sid}:{peladen.id}: Updating database...")
            success, msg = await self.bot.ntdb.update_server(peladen)
            if not success:
                if peladen.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(peladen.id)
                self.logger.warning(f"{sid}:{peladen.id}: Failed to update database: {msg}")
        return "Kolaborasi diputuskan!"

    @commands.command(name="showui", aliases=["ntui"])
    async def _showntui_ntui(self, ctx: naoTimesContext, guild: commands.GuildConverter = None):
        if self.bot.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return

        server_id = None
        is_guild_id = False
        if guild is not None:
            server_id = guild.id
            is_guild_id = True
        if ctx.guild is not None:
            server_id = ctx.guild.id
            is_guild_id = False
        if server_id is None:
            return await ctx.send(
                "Mohon jalankan di server, atau berikan ID server!\n"
                f"Contoh: `{self.bot.prefixes(ctx)}showui xxxxxxxxxxx`"
            )

        self.logger.info(f"{ctx.author} requested showui for {server_id}")
        srv_data = await self.bot.showqueue.fetch_database(server_id)
        if srv_data is None:
            self.logger.warning("cannot find the server in database")
            if is_guild_id:
                await ctx.send(f"Tidak dapat menemukan ID `{server_id}` di database Showtimes")
            return

        author_id = ctx.author.id
        if not srv_data.is_admin(author_id):
            self.logger.warning(f"{ctx.author} is not admin of {server_id}")
            return await ctx.send("Anda tidak berhak untuk menggunakan perintah ini!")

        self.logger.info("Making new login info!")
        do_continue = await ctx.confirm(
            "Perintah ini akan memperlihatkan kode rahasia untuk login di WebUI, lanjutkan?"
        )
        if not do_continue:
            return await ctx.send("*Dibatalkan*")

        _, return_msg = await self.bot.ntdb.generate_login_info(server_id)
        await ctx.send(return_msg)


async def setup(bot: naoTimesBot):
    await bot.add_cog(ShowtimesUIBridge(bot))
