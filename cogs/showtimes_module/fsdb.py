# -*- coding: utf-8 -*-

import asyncio
import logging
from functools import partial

import discord
from discord.ext import commands

from nthelper.bot import naoTimesBot
from nthelper.showtimes_helper import ShowtimesQueueData
from nthelper.utils import HelpGenerator

from .base import ShowtimesBase


class ShowtimesFansubDB(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesFansubDB, self).__init__()
        self.bot = bot
        self.ntdb = bot.ntdb
        self.showqueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, redisdb=bot.redisdb)
        self.srv_dumps = partial(self.dumps_showtimes, redisdb=bot.redisdb)
        self.logger = logging.getLogger("cogs.showtimes_module.fsdb.ShowtimesFansubDB")
        self.fsdb_conn = bot.fsdb

    def __str__(self):
        return "Showtimes FansubDB"

    @commands.group(name="fsdb")
    async def fsdb_cmd(self, ctx):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        if self.fsdb_conn is None:
            return await ctx.send("FSDB Tidak di initialisasi oleh owner bot")
        if ctx.invoked_subcommand is None:
            helpcmd = HelpGenerator(self.bot, "fsdb", f"Versi {self.bot.semver}")
            await helpcmd.generate_field("fsdb", desc="Memunculkan bantuan perintah")
            await helpcmd.generate_field(
                "fsdb integrasi", desc="Memulai proses integrasi fansubdb.",
            )
            await helpcmd.generate_field(
                "fsdb bind",
                desc="Memulai proses binding garapan dengan fansubdb.",
                opts=[{"name": "judul", "type": "o"}],
            )
            await helpcmd.generate_field(
                "fsdb fansub",
                desc="Mencari Informasi Fansub di FansubDB",
                opts=[{"name": "kueri pencarian", "type": "r"}],
            )
            await ctx.send(embed=helpcmd.get())

    @commands.command(name="integrasi_fsdb", aliases=["fsdb_integrate"])
    async def old_fsdb_command(self, ctx):
        await ctx.send(f"Command dipindahkan ke: `{self.bot.prefix}fsdb integrasi`")

    @fsdb_cmd.command(name="integrasi", aliases=["integrate"])
    async def fsdb_integrasi(self, ctx):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa menambah utang")

        if "fsdb_id" in srv_data:
            self.logger.warning(f"{server_message}: already integrated with fsdb.")
            return await ctx.send("Fansub sudah terintegrasi dengan FansubDB.")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        self.logger.info(f"{server_message}: creating initial data...")
        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "fs_id": "",
        }
        cancel_toggled = False  # Some easy check if it's gonna fucked up
        first_time = True

        def check_if_author(m):
            return m.author == msg_author

        async def process_fsdb(table, emb_msg):
            self.logger.info(f"{server_message}: processing fansubdb data...")
            embed = discord.Embed(title="Integrasi FansubDB", color=0x96DF6A)
            embed.add_field(
                name="Fansub ID",
                value="Ketik ID Fansub yang terdaftar di FansubDB.\n\n"
                "Gunakan `!fsdb fansub <pencarian>` untuk mencari ID fansub."
                "\n\nKetik *cancel* untuk membatalkan proses",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if not await_msg.content.startswith("!fsdb"):
                    if await_msg.content == ("cancel"):
                        return False, "Dibatalkan oleh user."

                    if await_msg.content.isdigit():
                        await await_msg.delete()
                        break

                    await await_msg.delete()

            table["fs_id"] = int(await_msg.content)
            return table, emb_msg

        async def find_fansub_name(fansubs_db: list, fansub_id: int):
            fansub_name = "Tidak diketahui"
            fs_data = await self.split_search_id(fansubs_db, "id", fansub_id)
            fansub_name = fs_data["name"]
            return fansub_name

        json_tables, emb_msg = await process_fsdb(json_tables, emb_msg)
        if not json_tables:
            self.logger.warning(f"{server_message}: {emb_msg}")
            return await ctx.send(emb_msg)

        self.logger.info(f"{server_message}: checkpoint before commiting")
        all_fansubs = await self.fsdb_conn.fetch_fansubs()
        while True:
            fs_name = await find_fansub_name(all_fansubs, json_tables["fs_id"])
            embed = discord.Embed(
                title="Integrasi FansubDB",
                description="Periksa data!\nReact jika ingin diubah.",
                color=0xE7E363,
            )
            embed.add_field(
                name="1⃣ ID Fansub", value="{} ({})".format(fs_name, json_tables["fs_id"]), inline=False,
            )
            embed.add_field(
                name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = [
                "1⃣",
                "✅",
                "❌",
            ]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_fsdb(json_tables, emb_msg)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                self.logger.warning(f"{server_message}: process cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: adding fsdb_id to anime data...")
        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Memproses Koneksi Anime...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)
        collect_anime_dataset = await self.fsdb_conn.fetch_animes()
        osrv_dumped = {}
        if collect_anime_dataset:
            collect_anime_dataset.sort(key=lambda x: x["mal_id"])
            for ani in srv_anilist:
                mal_id = srv_data["anime"][ani]["mal_id"]
                fsdata = await self.split_search_id(collect_anime_dataset, "mal_id", mal_id)
                if fsdata is None:
                    res, fs_id = await self.fsdb_conn.import_mal(int(mal_id))
                else:
                    fs_id = fsdata["id"]
                srv_data["anime"][ani]["fsdb_data"] = {"ani_id": fs_id}

            fansubs_projects, _ = await self.fsdb_conn.fetch_fansub_projects(json_tables["fs_id"])
            existing_projects = {str(data["anime"]["id"]): data["id"] for data in fansubs_projects}
            for ani, ani_data in srv_data["anime"].items():
                kolaborasi_data = []
                if "kolaborasi" in ani_data:
                    kolaborasi_data = ani_data["kolaborasi"]
                if kolaborasi_data:
                    kolaborasi_data.remove(server_message)
                fsani_id = str(ani_data["fsdb_data"]["ani_id"])
                if fsani_id in existing_projects:
                    self.logger.info(f"fsdb_ani{fsani_id}: using existing project in fansubdb...")
                    srv_data["anime"][ani]["fsdb_data"]["id"] = existing_projects[fsani_id]
                    if kolaborasi_data:
                        for osrv in kolaborasi_data:
                            if osrv == server_message:
                                continue
                            osrv_data = await self.showqueue.fetch_database(osrv)
                            if osrv_data is not None:
                                if "fsdb_data" not in osrv_data["anime"][ani]:
                                    osrv_data["anime"][ani]["fsdb_data"] = {
                                        "id": existing_projects[fsani_id],
                                        "ani_id": srv_data["anime"][ani]["fsdb_data"]["ani_id"],
                                    }
                                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))
                                    osrv_dumped[osrv] = osrv_data
                            else:
                                self.logger.warning(f"Unknown bang server ini: {osrv}")
                else:
                    first_ep = list(ani_data["status"].keys())[0]
                    final_ep = list(ani_data["status"].keys())[-1]
                    status_add = "Tentatif"
                    if ani_data["status"][final_ep]["status"] == "released":
                        status_add = "Tamat"
                    elif ani_data["status"][first_ep]["status"] == "released":
                        status_add = "Jalan"
                    self.logger.info(f"fsdb_ani{fsani_id}: creating new project in fansubdb...")
                    scd, project_id = await self.fsdb_conn.add_new_project(
                        fsani_id, json_tables["fs_id"], status_add
                    )
                    if scd:
                        self.logger.info(f"fsdb_ani{fsani_id}: appending proj{project_id} to database...")
                        srv_data["anime"][ani]["fsdb_data"]["id"] = project_id
                        if kolaborasi_data:
                            for osrv in kolaborasi_data:
                                if osrv == server_message:
                                    continue
                                osrv_data = await self.showqueue.fetch_database(osrv)
                                if osrv_data is not None:
                                    if "fsdb_data" not in osrv_data["anime"][ani]:
                                        osrv_data["anime"][ani]["fsdb_data"] = {
                                            "id": project_id,
                                            "ani_id": srv_data["anime"][ani]["fsdb_data"]["ani_id"],
                                        }
                                        await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))
                                        osrv_dumped[osrv] = osrv_data
                                else:
                                    self.logger.warning(f"Unknown bang server ini: {osrv}")

        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data akhir...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        srv_data["fsdb_id"] = json_tables["fs_id"]

        self.logger.info(f"{server_message}: saving to local database...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Integrasi FansubDB", color=0x96DF6A)
        embed.add_field(
            name="Sukses!", value="Server sukses terintegrasi dengan FansubDB", inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")
        await emb_msg.delete()

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        self.logger.info(f"{server_message}: done processing!")

    @fsdb_cmd.command(name="bind", aliases=["hubungkan"])
    async def fsdb_binding(self, ctx, *, judul=None):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if "fsdb_id" not in srv_data:
            return await ctx.send(
                f"FansubDB belum dibinding, silakan gunakan `{self.bot.semver}` to continue."
            )

        msg = await ctx.send("Memulai proses binding...")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        res = await self.confirmation_dialog(
            self.bot, ctx, f"Apakah yakin ingin binding untuk judul **{matches[0]}**"
        )
        if not res:
            return await ctx.send("Dibatalkan.")

        await msg.edit(content="Memeriksa data lama...")
        fansubs_projects, _ = await self.fsdb_conn.fetch_fansub_projects(srv_data["fsdb_id"])
        existing_projects = {str(data["anime"]["mal_id"]): data["id"] for data in fansubs_projects}
        fansubs_projects.sort(key=lambda x: x["id"])
        if str(program_info["mal_id"]) in existing_projects:
            fansub_data = await self.split_search_id(
                fansubs_projects, "id", existing_projects[str(program_info["mal_id"])]
            )
            if fansub_data is not None:
                res = await self.confirmation_dialog(
                    self.bot, ctx, "Terdapat data di FansubID, apakah ingin di overwrite?"
                )
                if not res:
                    return await ctx.send("Dibatalkan.")
                await msg.edit(content="Membuang data lama...")
                if len(fansub_data["fansub"]) == 1:
                    res, _ = await self.fsdb_conn.delete_project(fansub_data["id"])
                    if not res:
                        return await ctx.send("Gagal menghapus data lama, membatalkan...")
                else:
                    all_fs_id = [fsd["id"] for fsd in fansub_data["fansub"]]
                    try:
                        all_fs_id.remove(srv_data["fsdb_id"])
                    except ValueError:
                        return await ctx.send("Gagal menghapus data lama, membatalkan...")
                    res, _ = await self.fsdb_conn.update_project(fansub_data["id"], "fansub", all_fs_id)
                    if not res:
                        return await ctx.send("Gagal menghapus data lama, membatalkan...")

        await msg.edit(content="Menambahkan project baru...")
        anime_lists = await self.fsdb_conn.fetch_animes()
        anifs_id = await self.fsdb_conn.find_id_from_mal(program_info["mal_id"], anime_lists)
        if anifs_id == 0:
            _, anifs_id = await self.fsdb_conn.import_mal(program_info["mal_id"])

        final_ep = list(program_info["status"].keys())[-1]
        first_ep = list(program_info["status"].keys())[0]
        status_add = "Tentatif"
        if program_info["status"][final_ep]["status"] == "released":
            status_add = "Tamat"
        elif program_info["status"][first_ep]["status"] == "released":
            status_add = "Jalan"

        res, project_id = await self.fsdb_conn.add_new_project(anifs_id, srv_data["fsdb_id"], status_add)
        if not res:
            return await ctx.send("Gagal menambahkan project baru ke FansubDB")
        srv_data["anime"][matches[0]]["fsdb_data"] = {
            "id": project_id,
            "ani_id": anifs_id,
        }

        self.logger.info(f"{server_message}: saving to local database...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        self.logger.info(f"{server_message}: done processing!")
        await ctx.send(f"Selesai membinding judul **{matches[0]}**")

    @fsdb_cmd.command(name="fansub")
    async def fsdb_fansub(self, ctx, *, pencarian):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info(f"Searching for: {pencarian}")
        results = await self.fsdb_conn.fetch_fansubs(pencarian)
        results = results[:10]

        async def create_fsdb_embed(data):
            embed = discord.Embed(color=0x19212D)
            embed.set_footer(text="(C) FansubDB Indonesia")
            embed.title = data["name"]
            desc = f"ID: {data['id']}"
            if data["description"]:
                desc += f"\n{data['description']}"
            embed.description = desc

            url_link_info = []
            if data["website"]:
                url_link_info.append(f"[Website]({data['website']})")
            if data["facebook"]:
                url_link_info.append(f"[Facebook]({data['facebook']})")
            if data["discord"]:
                url_link_info.append(f"[Discord]({data['discord']})")
            if url_link_info:
                embed.add_field(name="URL", value="\n".join(url_link_info))
            return embed

        first_run = True
        num = 1
        max_page = len(results)
        while True:
            if first_run:
                self.logger.info("showing results...")
                data = results[num - 1]
                embed = await create_fsdb_embed(data)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                break
            if num == 1:
                reactmoji.append("⏩")
            elif num == max_page:
                reactmoji.append("⏪")
            reactmoji.append("✅")

            self.logger.debug("reacting message...")
            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                self.logger.debug("now waiting for reaction...")
                res, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check_react)
            except asyncio.TimeoutError:
                self.logger.warn("timeout, removing reactions...")
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                self.logger.debug("going backward...")
                num = num - 1
                data = results[num - 1]
                embed = await create_fsdb_embed(data)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                self.logger.debug("going forward...")
                num = num + 1
                data = results[num - 1]
                embed = await create_fsdb_embed(data)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
                self.logger.warn("deleting embed...")
                await msg.clear_reactions()
                return await msg.delete()
