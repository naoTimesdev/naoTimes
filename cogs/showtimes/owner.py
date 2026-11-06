import logging
from io import BytesIO

import discord
import orjson
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import OwnerGroup
from naotimes.showtimes import Showtimes


class ShowtimesOwner(commands.Cog):
    # OwnerGroup rejects everyone but the bot owner; replies are ephemeral because they carry secrets/dumps.
    ntadmin = OwnerGroup(
        name="ntadmin",
        description=app_commands.locale_str("Perintah admin naoTimes (owner bot)", key="showtimes.owner.description"),
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.Owner")
        self.ntdb = bot.ntdb
        self.bot_config = bot.config

    @ntadmin.command(
        name="showui",
        description=app_commands.locale_str("Lihat kode rahasia untuk akses naoTimesUI", key="showtimes.owner.showui"),
    )
    async def _showowner_showui(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        await inter.response.defer(ephemeral=True)
        if self.ntdb is None or inter.guild is None:
            return await inter.followup.send(ctx.t("owner.no_database"), ephemeral=True)
        _, return_msg = await self.ntdb.generate_login_info(str(inter.guild.id), True)
        await inter.followup.send(return_msg, ephemeral=True)

    @ntadmin.command(
        name="listserver",
        description=app_commands.locale_str(
            "Daftar server yang terdaftar di Showtimes", key="showtimes.owner.listserver"
        ),
    )
    async def _showowner_listserver(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        await inter.response.defer(ephemeral=True)
        self.logger.info("Requested server list for naoTimes by bot owner")
        if self.bot.redisdb is None:
            return await inter.followup.send(ctx.t("owner.no_redis"), ephemeral=True)
        all_ntdb = await self.bot.redisdb.getall("showtimes_*")
        all_server_list = []
        for server in all_ntdb:
            db_show = Showtimes.from_dict(server)
            discord_guild = self.bot.get_guild(int(db_show.id))
            if discord_guild is None:
                self.logger.warning(f"Server {db_show.id} not found on Discord!")
                continue
            all_server_list.append(f"{discord_guild} ({db_show.id})")

        base_text = [ctx.t("owner.server_list_title", count=len(all_server_list))]
        base_text.extend(all_server_list)
        text = "\n".join(base_text)
        if len(text) > 1990:
            return await inter.followup.send(
                ctx.t("owner.list_too_long"),
                file=discord.File(BytesIO(text.encode("utf-8")), "servers.txt"),
                ephemeral=True,
            )
        await inter.followup.send(text, ephemeral=True)

    @ntadmin.command(
        name="fetchdb",
        description=app_commands.locale_str(
            "Ambil snapshot database lokal sebagai file", key="showtimes.owner.fetchdb"
        ),
    )
    async def _showowner_fetchdb(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        await inter.response.defer(ephemeral=True)
        self.logger.info("Requested fetching database")
        if self.bot.redisdb is None:
            return await inter.followup.send(ctx.t("owner.no_redis"), ephemeral=True)
        all_ntdb = await self.bot.redisdb.getall("showtimes_*")
        all_admins = await self.bot.redisdb.getall("showadmin_*")
        final_dataset = {"servers": all_ntdb, "supermod": all_admins}
        dumped_data = orjson.dumps(final_dataset, option=orjson.OPT_INDENT_2)
        save_file_name = f"{self.bot.now().int_timestamp}_naoTimesDB_Snapshot.json"
        self.logger.info("Sending to requester...")
        await inter.followup.send(
            ctx.t("owner.here_you_go"), file=discord.File(BytesIO(dumped_data), save_file_name), ephemeral=True
        )

    @ntadmin.command(
        name="forcepull",
        description=app_commands.locale_str(
            "Paksa database lokal mengikuti database utama", key="showtimes.owner.forcepull"
        ),
    )
    async def _showowner_forcepull(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        await inter.response.defer(ephemeral=True)
        self.logger.info("Forcing local database with remote database.")
        if self.bot.ntdb is None or self.bot.redisdb is None:
            return await inter.followup.send(ctx.t("owner.no_database_redis"), ephemeral=True)
        js_data = await self.bot.ntdb.fetch_all_as_json()
        for admins in js_data["supermod"]:
            self.logger.info(f"saving admin {admins['id']} data to redis")
            await self.bot.redisdb.set(f"showadmin_{admins['id']}", admins)
        for server in js_data["servers"]:
            self.logger.info(f"saving server {server['id']} data to redis")
            await self.bot.redisdb.set("showtimes_" + server["id"], server)
        await inter.followup.send(ctx.t("owner.pulled"), ephemeral=True)

    @ntadmin.command(
        name="forcepush",
        description=app_commands.locale_str(
            "Paksa kirim data lokal ke database utama", key="showtimes.owner.forcepush"
        ),
    )
    @app_commands.describe(
        server_id=app_commands.locale_str(
            "ID server (kosongkan untuk semua server)", key="showtimes.owner.option_server_id"
        )
    )
    async def _showowner_forcepush(self, inter: discord.Interaction, server_id: str | None = None):
        ctx = await self.bot.get_context(inter)
        await inter.response.defer(ephemeral=True)
        self.logger.info("Force pushing local data to main database")
        if self.bot.ntdb is None or self.bot.redisdb is None:
            return await inter.followup.send(ctx.t("owner.no_database_redis"), ephemeral=True)
        if server_id is None:
            all_ntdb = await self.bot.redisdb.getall("showtimes_*")
            for data in all_ntdb:
                await self.bot.ntdb.update_server(Showtimes.from_dict(data))
        else:
            ntdb_single = await self.bot.redisdb.get(f"showtimes_{server_id}")
            if ntdb_single is None:
                return await inter.followup.send(ctx.t("owner.unknown_server"), ephemeral=True)
            await self.bot.ntdb.update_server(Showtimes.from_dict(ntdb_single))
        await inter.followup.send(ctx.t("owner.done"), ephemeral=True)


async def setup(bot: naoTimesBot):
    await bot.add_cog(ShowtimesOwner(bot))
