import logging
from io import BytesIO

import discord
import orjson
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption
from naotimes.showtimes import Showtimes


class ShowtimesOwner(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.Owner")
        self.ntdb = bot.ntdb
        self.bot_config = bot.config

    @commands.group(name="ntadmin", aliases=["shadmin", "naotimesadmin", "showtimesadmin"])
    @commands.is_owner()
    @commands.guild_only()
    async def _showowner_main(self, ctx: naoTimesContext):
        if ctx.invoked_subcommand is None:
            helpcmd = ctx.create_help("ntadmin", desc=f"Versi {self.bot.semver}")
            helpcmd.add_fields(
                [
                    HelpField("ntadmin", "Memunculkan bantuan perintah ini."),
                    HelpField(
                        "ntadmin tambah",
                        "Menambah server baru ke database naoTimes",
                        [
                            HelpOption(
                                "server id",
                                required=True,
                            ),
                            HelpOption(
                                "admin id",
                                required=True,
                            ),
                            HelpOption("#progress channel"),
                        ],
                    ),
                    HelpField(
                        "ntadmin hapus",
                        "Menghapus server dari database naoTimes",
                        HelpOption("server id", required=True),
                    ),
                    HelpField(
                        "ntadmin tambahadmin",
                        "Menambah admin ke server baru yang terdaftar di database.",
                        [
                            HelpOption("server id", required=True),
                            HelpOption("admin id", required=True),
                        ],
                    ),
                    HelpField(
                        "ntadmin hapusadmin",
                        "Menghapus admin dari server yang terdaftar di database.",
                        [
                            HelpOption("server id", required=True),
                            HelpOption("admin id", required=True),
                        ],
                    ),
                    HelpField(
                        "ntadmin fetchdb",
                        "Mengambil database lokal dan kirim ke Discord",
                    ),
                    HelpField("ntadmin forcepull", "Update paksa database lokal dengan database remote!"),
                    HelpField("ntadmin showui", "Melihat password untuk akses naoTimesUI"),
                ]
            )
            helpcmd.add_aliases(["naotimesadmin", "showtimesadmin", "shadmin"])
            await ctx.send(embed=helpcmd.get())

    @_showowner_main.command(name="showui")
    async def _showowner_showui(self, ctx: naoTimesContext):
        do_continue = await ctx.confirm(
            "Perintah ini akan memperlihatkan kode rahasia untuk akses WebUI, lanjutkan?"
        )
        if not do_continue:
            return await ctx.send("Dibatalkan!")
        _, return_msg = await self.ntdb.generate_login_info(str(ctx.guild.id), True)
        await ctx.send(return_msg)

    @_showowner_main.command(name="listserver")
    async def _showowner_listserver(self, ctx: naoTimesContext):
        if self.ntdb is None:
            self.logger.info("Mohon aktifkan Showtimes/naoTimesDB terlebih dahulu!")
            return

        self.logger.info("Requested server list for naoTimes by bot owner")
        all_ntdb = await self.bot.redisdb.getall("showtimes_*")
        all_server_list = []
        for server in all_ntdb:
            db_show = Showtimes.from_dict(server)
            discord_guild = self.bot.get_guild(int(db_show.id))
            if discord_guild is None:
                self.logger.warning(f"Server {db_show.id} not found on Discord!")
                continue
            all_server_list.append(f"{discord_guild} ({db_show.id})")

        base_text = [f"**List server ({len(all_server_list)} servers):**"]
        base_text.extend(all_server_list)
        await ctx.send("\n".join(base_text))

    @_showowner_main.command(name="fetchdb")
    async def _showowner_fetchdb(self, ctx: naoTimesContext):
        self.logger.info("Requested fetching database")
        all_ntdb = await self.bot.redisdb.getall("showtimes_*")
        all_admins = await self.bot.redisdb.getall("showadmin_*")
        final_dataset = {
            "servers": all_ntdb,
            "supermod": all_admins,
        }
        dumped_data = orjson.dumps(final_dataset, option=orjson.OPT_INDENT_2)
        save_file_name = f"{self.bot.now().int_timestamp}_naoTimesDB_Snapshot.json"
        self.logger.info("Sending to requester...")
        await ctx.send(content="Here you go!", file=discord.File(BytesIO(dumped_data), save_file_name))

    @_showowner_main.command(name="forcepull")
    async def _showowner_forcepull(self, ctx: naoTimesContext):
        if self.ntdb is None:
            self.logger.info("Mohon aktifkan Showtimes/naoTimesDB terlebih dahulu!")
            return

        self.logger.info("Forcing local database with remote database.")
        js_data = await self.bot.ntdb.fetch_all_as_json()
        for admins in js_data["supermod"]:
            self.logger.info(f"saving admin {admins['id']} data to redis")
            await self.bot.redisdb.set(f"showadmin_{admins['id']}", admins)
        for server in js_data["servers"]:
            self.logger.info(f"saving server {server['id']} data to redis")
            await self.bot.redisdb.set("showtimes_" + server["id"], server)
        await ctx.send("Newest database has been pulled and saved to local save")

    @_showowner_main.command(name="forcepush")
    async def _showowner_forcepush(self, ctx: naoTimesContext, server_id: int = None):
        self.logger.info("Force pushing local data to main database")
        if server_id is None:
            all_ntdb = await self.bot.redisdb.getall("showtimes_*")
            for data in all_ntdb:
                show_data = Showtimes.from_dict(data)
                await self.bot.ntdb.update_server(show_data)
        else:
            ntdb_single = await self.bot.redisdb.get(f"showtimes_{server_id}")
            if ntdb_single is None:
                return await ctx.send("Unknown server")
            show_data = Showtimes.from_dict(ntdb_single)
            await self.bot.ntdb.update_server(show_data)
        await ctx.send("All done!")


def setup(bot: naoTimesBot):
    bot.add_cog(ShowtimesOwner(bot))
