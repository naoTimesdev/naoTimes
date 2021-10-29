import logging
from typing import List

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption
from naotimes.paginator import DiscordPaginatorUI
from naotimes.showtimes import Showtimes
from naotimes.showtimes.models import ShowtimesFSDB
from naotimes.utils import split_search_id


class ShowtimesFansubDB(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.FansubDB")

        self.queue = bot.showqueue
        self.base = bot.showcogs
        self.ntdb = bot.ntdb
        self.fsdb = bot.fsdb

    @commands.group(name="fsdb")
    @commands.guild_only()
    async def _showfsdb_main(self, ctx: naoTimesContext):
        if self.fsdb is None:
            return await ctx.send("FSDB tidak di initialisasi oleh owner bot")
        if ctx.invoked_subcommand is None:
            helpcmd = ctx.create_help("fsdb", f"Versi {self.bot.semver}")
            helpcmd.add_fields(
                [
                    HelpField("fsdb integrasi", "Mulai proses integrasi Showtimes dengan FansubDB"),
                    HelpField(
                        "fsdb bind",
                        "Memulai proses binding/penghubungan garapan dengan FansubDB",
                        HelpOption("judul"),
                    ),
                    HelpField(
                        "fsdb fansub",
                        "Mencari informasi Fansub di FansubDB",
                        HelpOption(
                            "kueri pencarian",
                            required=True,
                        ),
                    ),
                ]
            )
            helpcmd.add_aliases()
            await ctx.send(embed=helpcmd.get())

    @_showfsdb_main.command(name="integrasi", aliases=["integrate"])
    async def _showfsdb_integrasi(self, ctx: naoTimesContext):
        server_id = ctx.guild.id
        self.logger.info(f"{server_id}: finding server...")
        srv_data = await self.queue.fetch_database(server_id)
        if srv_data is None:
            self.logger.warning(f"{server_id}: server not found")
            return

        self.logger.info(f"{server_id}: server found, checking perms...")
        if not srv_data.is_admin(ctx.author):
            self.logger.warning(f"{server_id}: insufficient permissions")
            return await ctx.send("Hanya admin yang bisa menambah utang")

        if srv_data.fsdb_id is not None:
            self.logger.warning(f"{server_id}: already integrated")
            return await ctx.send("Fansub sudah terintegrasi dengan FansubDB.")

        self.logger.info(f"{server_id}: not integrated, starting integration...")
        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memulai Proses", value="Mempersiapkan...")
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        base_message = await ctx.send(embed=embed)
        fsdb_pre = self.bot.prefixes(ctx.guild) + "fsdb"

        async def _process_fsdb_internal():
            self.logger.info(f"{server_id}: processing fansubdb data...")
            embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
            embed.add_field(
                name="Fansub ID",
                value="Ketik ID Fansub yang terdaftar di FansubDB.\n\n"
                "Gunakan `!fsdb fansub <pencarian>` untuk mencari ID fansub."
                "\n\nKetik *cancel* untuk membatalkan proses",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            fsdb_id: int = None
            message = None
            while True:
                await_msg: str = await ctx.wait_content(
                    "Masukan Fansub ID dari FansubDB...",
                    delete_answer=True,
                    pass_message=message,
                    timeout=None,
                )
                if not await_msg:
                    return None
                if not await_msg.startswith(fsdb_pre):
                    if await_msg.isdigit():
                        fsdb_id = int(await_msg)
                        break

            return fsdb_id

        fsdb_id = await _process_fsdb_internal()
        if not fsdb_id:
            self.logger.warning(f"{server_id}: cancelled.")
            return await ctx.send("Dibatalkan oleh user")

        self.logger.info(f"{server_id}: processing data...")
        all_fansubs = await self.fsdb.fetch_fansubs()
        fsd_data = split_search_id(all_fansubs, "id", fsdb_id)
        if not fsd_data:
            self.logger.warning(f"{server_id}: not found")
            return await ctx.send("ID fansub tidak ditemukan di FansubDB, mohon ulangi dari awal!")

        fsd_name = fsd_data["name"]
        embed = discord.Embed(
            title="Integrasi FansubDB",
            description="Periksa data!\nReact jika ingin diubah.",
            color=0xE7E363,
        )
        embed.add_field(
            name="1⃣ ID Fansub",
            value=f"{fsd_name} ({fsdb_id})",
            inline=False,
        )
        embed.add_field(
            name="Lain-Lain",
            value="✅ Tambahkan!\n❌ Batalkan!",
            inline=False,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await base_message.delete()
        message = await ctx.send(embed=embed)

        is_confirm = await ctx.confirm(message, True)
        if not is_confirm:
            return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_id}: collecting registered anime data and such...")
        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Memproses Koneksi Anime...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await message.edit(embed=embed)
        collect_all_animes = await self.fsdb.fetch_animes()
        update_queue: List[Showtimes] = []
        if collect_all_animes:
            collect_all_animes.sort(key=lambda x: x["mal_id"])
            for project in srv_data.projects:
                mal_id = project.mal_id
                if mal_id is None:
                    continue
                fsani_data = split_search_id(collect_all_animes, "mal_id", mal_id)
                if fsani_data is None:
                    res, fsani_id = await self.fsdb.import_mal(int(mal_id))
                else:
                    fsani_id = fsani_data["id"]
                project.fsdb = ShowtimesFSDB(None, fsani_id)
                srv_data.update_project(project, False)

            fansubs_projects, _ = await self.fsdb.fetch_fansub_projects(fsdb_id)
            existing_projects = {str(data["anime"]["id"]): data["id"] for data in fansubs_projects}
            for project in srv_data.projects:
                kolaborasi_data = project.kolaborasi
                if kolaborasi_data and server_id in kolaborasi_data:
                    kolaborasi_data = kolaborasi_data.remove(server_id)
                fsani_id = str(project.fsdb.anime)
                if fsani_id in existing_projects:
                    self.logger.info(f"fsdb_ani{fsani_id}: using existing project in fansubdb...")
                    project.fsdb.id = existing_projects[fsani_id]
                else:
                    status_type = "Tentatif"
                    if project.get_current() is None:
                        status_type = "Tamat"
                    elif project.status[0].finished:
                        status_type = "Jalan"
                        if len(project.status) == 1:
                            status_type = "Tamat"
                    self.logger.info(f"fsdb_ani{fsani_id}: creating new project in fansubdb...")
                    proj_add_success, project_id = await self.fsdb.add_new_project(
                        fsani_id, fsdb_id, status_type
                    )
                    if proj_add_success:
                        self.logger.info(f"fsdb_ani{fsani_id}: appending proj{project_id} to database...")
                        project.fsdb.id = project_id
                srv_data.update_project(project, False)
                if kolaborasi_data:
                    for osrv in kolaborasi_data:
                        if osrv == server_id:
                            continue
                        osrv_data = await self.queue.fetch_database(osrv)
                        if osrv_data is None:
                            continue
                        osrv_anime = osrv_data.get_project(project)
                        if osrv_anime is None:
                            continue
                        osrv_anime.fsdb = project.fsdb
                        osrv_data.update_project(osrv_anime, False)
                        update_queue.append(osrv_data)

        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data akhir...")
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await message.edit(embed=embed)
        srv_data.fsdb_id = int(fsdb_id)
        update_queue.append(srv_data)

        self.logger.info(f"{server_id}: updating database...")
        for data in update_queue:
            await self.queue.add_job(data)
        embed = discord.Embed(title="Integrasi FansubDB", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Server sukses terintegrasi dengan FansubDB",
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)
        await message.delete()

        for data in update_queue:
            self.logger.info(f"{data.id}: updating main database...")
            res, msg = await self.ntdb.update_server(data)
            if not res:
                self.logger.error(f"{data.id}: failed to update main database: {msg}")
                if data.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(data.id)

        self.logger.info(f"{server_id}: integration completed!")

    @_showfsdb_main.command(name="bind", aliases=["hubungkan"])
    async def _showfsdb_bind(self, ctx: naoTimesContext, *, judul: str = None):
        server_id = ctx.guild.id
        self.logger.info(f"Requested FSDB binding at {server_id}")
        srv_data = await self.queue.fetch_database(server_id)
        if srv_data is None:
            self.logger.error(f"{server_id}: cannot find the server...")
            return
        self.logger.info(f"{server_id}: data found!")
        if srv_data.fsdb_id is None:
            self.logger.error(f"{server_id}: FSDB is not integrated yet!")
            return await ctx.send(
                "FansubDB belum diintegrasikan, silakan gunakan "
                f"`{self.bot.prefixes(ctx)}fsdb integrasi` terlebih dahulu!"
            )

        self.logger.info(f"{server_id}: trying to find the title first...")
        if not judul:
            self.logger.warning(f"{server_id}: no title provided!")
            return await self.base.send_all_projects(ctx, srv_data)

        msg = await ctx.send("Memulai proses binding...")
        all_matches = srv_data.find_projects(judul)
        if not all_matches:
            self.logger.warning(f"{server_id}: no matches found!")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.warning(f"{server_id}: multiple matches found!")
            select_match = await ctx.select_simple(all_matches, lambda x: x.title)
            if select_match is None:
                self.logger.warning(f"{server_id}: nothing was selected, cancelling")
                return await ctx.send("**Dibatalkan!**")
            all_matches = [select_match]

        project = all_matches[0]
        self.logger.info(f"{server_id}: found match: {project.title}")

        is_confirm = await ctx.confirm(
            f"Apakah anda yakin ingin menghubungkan judul proyek `{project.title}` dengan FansubDB?"
        )
        if not is_confirm:
            self.logger.warning(f"{server_id}: cancelled by user")
            return await ctx.send("**Dibatalkan!**")

        await msg.edit(content="Memeriksa data lama dari FansubDB...")
        fansubs_projects, _ = await self.fsdb.fetch_fansub_projects(srv_data.fsdb_id)
        existing_projects = {str(data["anime"]["mal_id"]): data["id"] for data in fansubs_projects}
        fansubs_projects.sort(key=lambda x: x["id"])
        if str(project.mal_id) in existing_projects:
            fansub_data = split_search_id(fansubs_projects, "id", existing_projects[str(project.mal_id)])
            if fansub_data is not None:
                self.logger.info(f"{server_id}-{project.id}: found old fansub data at FansubDB")
                confirm_ow = await ctx.confirm("Terdapat data lama di FansubDB, apakan ingin anda overwrite?")
                if not confirm_ow:
                    self.logger.warning(f"{server_id}-{project.id}: cancelled by user")
                    return await ctx.send("**Dibatalkan!**")
                await msg.edit(content="Membuang data lama...")
                if len(fansub_data["fansub"]) == 1:
                    self.logger.info(f"{server_id}-{project.id}: no collaboration found, deleting project...")
                    res, _ = await self.fsdb.delete_project(fansub_data["id"])
                    if not res:
                        self.logger.warning(f"{server_id}-{project.id}: failed to remove project data")
                        return await ctx.send("Gagal menghapus data lama, membatalkan proses!")
                else:
                    all_fs_id = list(map(lambda x: x["id"], fansub_data["fansub"]))
                    self.logger.info(f"{server_id}-{project.id}: collaboration found, removing self...")
                    try:
                        all_fs_id.remove(fansub_data["id"])
                    except ValueError:
                        self.logger.warning(f"{server_id}-{project.id}: failed to remove self data")
                        return await ctx.send("Gagal menghapus data lama, membatalkan proses!")
                    res, _ = await self.fsdb.update_project(
                        fansub_data["id"], "fansub", all_fs_id, task_mode=False
                    )
                    if not res:
                        self.logger.warning(f"{server_id}-{project.id}: failed to remove self data")
                        return await ctx.send("Gagal menghapus data lama, membatalkan proses!")

        self.logger.info(f"{server_id}-{project.id}: trying to bind project to FSDB...")
        await msg.edit(content="Menambahkan proyek baru...")

        anime_lists = await self.fsdb.fetch_animes()
        anifs_id = await self.fsdb.find_id_from_mal(project.mal_id, anime_lists)
        if anifs_id == 0:
            self.logger.warning(f"{server_id}-{project.id}: anime not found, importing...")
            _, anifs_id = await self.fsdb.import_mal(project.mal_id)

        status_type = "Tentatif"
        if project.get_current() is None:
            status_type = "Tamat"
        elif project.status[0].finished:
            status_type = "Jalan"
            if len(project.status) == 1:
                status_type = "Tamat"

        self.logger.info(f"{server_id}-{project.id}: adding project to FSDB...")
        res, project_id = await self.fsdb.add_new_project(anifs_id, srv_data.fsdb_id, status_type)
        if not res:
            self.logger.warning(f"{server_id}: failed to add project to database")
            return await ctx.send("Gagal menambahkan proyek baru!")
        project.fsdb = ShowtimesFSDB(project_id, anifs_id)
        self.logger.info(f"{server_id}-{project.id}: project added to database, saving...")
        srv_data.update_project(project, False)
        await self.queue.add_job(srv_data)

        self.logger.info(f"{server_id}-{project.id}: updating main database...")
        success, msg = await self.ntdb.update_server(srv_data)
        if not success:
            self.logger.warning(f"{server_id}: failed to update main database: {msg}")
            if server_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_id)

        self.logger.info(f"{server_id}-{project.id}: project binded with FSDB!")
        await ctx.send(f"Proyek `{project.title}` berhasil dihubungkan dengan FansubDB!")

    @_showfsdb_main.command(name="fansub")
    async def _showfsdb_fansub(self, ctx: naoTimesContext, *, pencarian: str):
        self.logger.info(f"Searching for: {pencarian}")

        results = await self.fsdb.fetch_fansubs(pencarian)

        def _create_fsdb_embed(data: dict):
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

        ui_paginate = DiscordPaginatorUI(ctx, results, 30.0)
        ui_paginate.attach(_create_fsdb_embed)
        await ui_paginate.interact()


def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    bot.add_cog(ShowtimesFansubDB(bot))
