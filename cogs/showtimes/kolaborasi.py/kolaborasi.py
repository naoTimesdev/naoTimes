import logging
from typing import List

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption
from naotimes.showtimes import Showtimes, ShowtimesKonfirmasi
from naotimes.utils import generate_custom_code
from naotimes.views.multi_view import Selection


class ShowtimesKolaborasi(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.Kolaborasi")
        self.ntdb = bot.ntdb
        self.base = bot.showcogs
        self.queue = bot.showqueue

    @commands.group(name="kolaborasi", aliases=["joint", "koleb"])
    @commands.guild_only()
    async def _showkoleb_main(self, ctx: naoTimesContext):
        if not ctx.invoked_subcommand:
            helpcmd = ctx.create_help("kolaborasi", f"Versi {self.bot.semver}")
            helpcmd.add_fields(
                [
                    HelpField(
                        "kolaborasi",
                        "Memunculkan bantuan perintah",
                        use_fullquote=True,
                    ),
                    HelpField(
                        "kolaborasi dengan",
                        "Memulai proses kolaborasi garapan dengan Fansub lain.",
                        [
                            HelpOption(
                                "server id kolaborasi",
                                required=True,
                            ),
                            HelpOption(
                                "judul",
                                required=True,
                            ),
                        ],
                        use_fullquote=True,
                    ),
                    HelpField(
                        "kolaborasi konfirmasi",
                        "Konfirmasi proses kolaborasi garapan.",
                        HelpOption("kode unik", required=True),
                        use_fullquote=True,
                    ),
                    HelpField(
                        "kolaborasi putus",
                        "Memunculkan hubungan kolaborasi suatu garapan.",
                        HelpOption(
                            "judul",
                            required=True,
                        ),
                        use_fullquote=True,
                    ),
                    HelpField(
                        "kolaborasi batalkan",
                        "Membatalkan proses kolaborasi",
                        [
                            HelpOption(
                                "server id kolaborasi",
                                required=True,
                            ),
                            HelpOption("kode unik", required=True),
                        ],
                        use_fullquote=True,
                    ),
                ]
            )
            helpcmd.add_aliases(["joint", "koleb"])
            await ctx.send(embed=helpcmd.get())

    @_showkoleb_main.command(name="dengan", aliases=["with"])
    async def _showkoleb_dengan(
        self, ctx: naoTimesContext, guild: commands.GuildConverter, *, judul: str = None
    ):
        if not isinstance(guild, discord.Guild):
            self.logger.error(f"{ctx.guild.id}: Bot tidak dapat menemukan peladen tersebut")
            return await ctx.send("Bot tidak dapat menemukan peladen tersebut?")
        server_id = ctx.guild.id
        target_guild: discord.Guild = guild
        srv_data = await self.queue.fetch_database(server_id)
        if srv_data is None:
            self.logger.error(f"{server_id}: server not registered in Showtimes")
            return

        if not srv_data.is_admin(ctx.author.id):
            self.logger.warning(f"{server_id}: {ctx.author.id} attempted to use kolaborasi command")
            return await ctx.send("Hanya admin yang bisa memulai kolaborasi")

        target_data = await self.queue.fetch_database(target_guild.id)
        if target_data is None:
            self.logger.error(f"{target_guild.id}: server not registered in Showtimes")
            return await ctx.send(f"Tidak dapat menemukan peladen **{target_guild}** tersebut di database")

        if server_id == target_guild.id:
            return await ctx.send("Tidak bisa mengajak kolaborasi dengan peladen sendiri!")

        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        self.logger.info(f"{server_id}: getting close matches...")
        all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no close matches found for {judul}")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.warning(f"{server_id}: found {len(all_matches)} close matches for {judul}")
            select_match = await ctx.select_single(
                all_matches, lambda x: Selection(x.title, x.id), content="Pilih judul yang anda maksud!"
            )
            if select_match is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [select_match]

        project = all_matches[0]
        self.logger.info(f"{server_id}: found {project.title}")
        if target_guild.id in project.kolaborasi:
            self.logger.warning(f"{server_id}: {project.title} already in kolaborasi")
            return await ctx.send("Peladen tersebut sudah diajak kolaborasi.")

        random_confirm = generate_custom_code(16)
        self.logger.info(f"{server_id}:{target_guild.id}: confirming collaboration...")
        embed = discord.Embed(
            title="Kolaborasi",
            description="Periksa data!\nReact jika ingin diubah.",
            color=0xE7E363,
        )
        embed.add_field(name="Anime/Garapan", value=project.title, inline=False)
        embed.add_field(name="Server", value=target_guild.name, inline=False)
        embed.add_field(
            name="Lain-Lain",
            value="✅ Tambahkan!\n❌ Batalkan!",
            inline=False,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        base_message = await ctx.send(embed=embed)
        is_confirmed = await ctx.confirm(base_message, dont_remove=True)
        if not is_confirmed:
            self.logger.warning(f"{server_id}-{project.title}: cancelling...")
            return await ctx.send("**Dibatalkan!**")

        koleb_data = ShowtimesKonfirmasi(random_confirm, server_id, project.id)
        target_data.add_konfirm(koleb_data)

        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await base_message.edit(embed=embed)

        self.logger.info(f"{server_id}-{project.id}: storing data...")
        await self.queue.add_job(target_data)

        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value=f"Berikan kode berikut `{random_confirm}` kepada fansub/server lain.\n"
            "Database utama akan diupdate sebentar lagi",
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await base_message.delete()
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating database...")
        success, msg = await self.ntdb.update_server(target_data)
        if not success:
            self.logger.error(f"{target_data.id}: failed to update, reason: {msg}")
            if target_data.id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(target_data.id)

        await ctx.send(
            f"Berikan kode berikut `{random_confirm}` kepada fansub/peladen yang ditentukan tadi.\n"
            f"Konfirmasi di peladen tersebut dengan `{self.bot.prefixes(target_guild)}kolaborasi "
            f"konfirmasi {random_confirm}`"
        )

    @_showkoleb_main.command(name="konfirmasi", aliases=["confirm"])
    async def _showkoleb_konfirmasi(self, ctx: naoTimesContext, kode_konfirmasi: str):
        server_id = ctx.guild.id
        srv_data = await self.queue.fetch_database(server_id)
        if srv_data is None:
            return
        self.logger.info(f"{server_id}: data found.")

        if not srv_data.is_admin(ctx.author.id):
            self.logger.warning(f"{server_id}: not the server admin")
            return await ctx.send("Hanya admin yang bisa konfirmasi kolaborasi.")

        if len(srv_data.konfirmasi) < 1:
            self.logger.warning(f"{server_id}: nothing to confirm.")
            return await ctx.send("Tidak ada kolaborasi yang harus dikonfirmasi.")

        get_confirm = srv_data.get_konfirm(kode_konfirmasi)
        if get_confirm is None:
            self.logger.warning(f"{server_id}: code not found")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")

        server_ident = self.bot.get_guild(get_confirm.server)
        source_name = server_ident.name if server_ident is not None else get_confirm.server

        source_srv = await self.queue.fetch_database(get_confirm.server)
        if source_srv is None:
            self.logger.warning(f"{get_confirm.server}: apparently the server gone now?")
            return await ctx.send("Peladen yang mengajak hilang dari database?")

        project_info = source_srv.get_project(get_confirm.anime)
        if project_info is None:
            self.logger.warning(f"{get_confirm.anime}: anime not found")
            return await ctx.send("Tidak dapat menemukan anime yang akan diajak kolaborasi.")

        embed = discord.Embed(title="Konfirmasi Kolaborasi", color=0xE7E363)
        embed.add_field(name="Anime/Garapan", value=project_info.title, inline=False)
        embed.add_field(name="Server", value=source_name, inline=False)
        embed.add_field(name="Lain-Lain", value="✅ Konfirmasi!\n❌ Tolak!", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        base_message = await ctx.send(embed=embed)

        is_confirm = await ctx.confirm(base_message, dont_remove=True)
        if not is_confirm:
            srv_data.remove_konfirm(get_confirm)
            await self.queue.add_job(srv_data)
            success, msg = await self.ntdb.update_server(srv_data)
            if not success:
                self.logger.warning(f"{srv_data.id}: failed to update, reason: {msg}")
                if srv_data.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(srv_data.id)
            return await ctx.send("Ajakan kolaborasi telah ditolak!")

        previous_info = srv_data.get_project(project_info)

        other_collab_data = []
        old_role = None
        old_fsdb_info = None
        if previous_info is not None:
            other_collab_data.extend(previous_info.kolaborasi)
            old_role = previous_info.role
            old_fsdb_info = previous_info.fsdb

        if not old_role:
            self.logger.info(f"{server_id}: creating roles...")
            c_role = await ctx.guild.create_role(
                name=project_info.title, colour=discord.Colour.random(), mentionable=True
            )
            old_role = c_role.id

        clone_data = project_info.copy()
        clone_data.role = old_role
        if old_fsdb_info is not None:
            clone_data.fsdb = old_fsdb_info

        joint_koleb = [get_confirm.server, server_id]
        joint_koleb.extend(other_collab_data)
        joint_koleb.extend(project_info.kolaborasi)
        # Dedup
        joint_koleb = list(dict.fromkeys(joint_koleb))

        project_info.kolaborasi = joint_koleb
        clone_data.kolaborasi = joint_koleb
        source_srv.update_project(project_info)
        srv_data.update_project(clone_data, False)
        srv_data.remove_konfirm(get_confirm)

        update_queue = [source_srv, srv_data]
        for joint in joint_koleb:
            if joint in [get_confirm.server, server_id]:
                continue
            joint_srv = await self.queue.fetch_database(joint)
            if joint_srv is None:
                continue
            joint_project = joint_srv.get_project(project_info)
            if joint_project is None:
                continue
            joint_project.kolaborasi = joint_koleb
            joint_srv.update_project(joint_project)
            update_queue.append(joint_srv)

        self.logger.info(f"{project_info.id}-{server_id}: now updating database...")
        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await base_message.edit(embed=embed)

        for srv in update_queue:
            await self.queue.add_job(srv)

        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value=f"Berhasil konfirmasi dengan server **{source_name}**.\n"
            "Database utama akan diupdate sebentar lagi",
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await base_message.delete()
        await ctx.send(embed=embed)

        for srv in update_queue:
            self.logger.info(f"{srv.id}: updating database...")
            success, msg = await self.ntdb.update_server(srv)
            if not success:
                self.logger.warning(f"{srv.id}: failed to update, reason: {msg}")
                if srv.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(srv.id)
        await ctx.send(
            f"Berhasil menambahkan kolaborasi dengan **{get_confirm.server}** ke dalam database utama"
            f" naoTimes\nBerikan role berikut agar bisa menggunakan perintah staff <@&{old_role}>"
        )

    @_showkoleb_main.command(name="batalkan")
    async def _showkoleb_batalkan(
        self, ctx: naoTimesContext, guild: commands.GuildConverter, kode_konfirmasi: str
    ):
        if not guild:
            self.logger.warning("guild doesn't exist in discord")
            return await ctx.send("Peladen tidak dapat ditemukan!")
        target_id = guild.id
        server_id = ctx.guild.id
        self.logger.info(f"Requested batalkan at {server_id}")
        srv_data = await self.queue.fetch_database(server_id)
        if srv_data is None:
            self.logger.warning(f"{server_id}: database not found")
            return
        self.logger.info(f"{server_id}: checking ownership...")
        if not srv_data.is_admin(ctx.author.id):
            self.logger.info(f"{server_id}: not the correct admin")
            return

        target_srv = await self.queue.fetch_database(target_id)
        if target_srv is None:
            self.logger.warning(f"{target_id}: cannot be found at database")
            return await ctx.send("Peladen target tidak dapat ditemukan!")

        self.logger.info(f"{server_id}: checking {kode_konfirmasi} code...")
        get_confirm = target_srv.get_konfirm(kode_konfirmasi)
        if get_confirm is None:
            self.logger.warning(f"{server_id}: {kode_konfirmasi} cannot be found...")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")
        if get_confirm.server != server_id:
            self.logger.warning(f"{server_id}: can only be deleted by {get_confirm.server}")
            return await ctx.send("Anda tidak berhak untuk menghapus kode ini!")

        self.logger.info(f"{server_id}: deleting {kode_konfirmasi} code...")
        target_srv.remove_konfirm(kode_konfirmasi)
        self.logger.info(f"{server_id}: now updating database...")
        await self.queue.add_job(target_srv)
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value=f"Berhasil membatalkan kode konfirmasi **{kode_konfirmasi}**.\n"
            "Database utama akan diupdate sebentar lagi",
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating main database...")
        success, msg = await self.ntdb.update_server(srv_data)
        if not success:
            self.logger.warning(f"{server_id}: failed to update, reason: {msg}")
            if server_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_id)

        await ctx.send(f"Berhasil membatalkan kode konfirmasi **{kode_konfirmasi}**!")

    @_showkoleb_main.command(name="putus")
    async def _showkoleb_putus(self, ctx: naoTimesContext, *, judul: str):
        server_id = ctx.guild.id
        self.logger.info(f"{server_id}: checking database...")
        srv_data = await self.queue.fetch_database(server_id)

        if not srv_data:
            self.logger.warning(f"{server_id}: database not found")
            return
        self.logger.info(f"{server_id}: checking ownership...")
        if not srv_data.is_admin(ctx.author.id):
            self.logger.info(f"{server_id}: not the correct admin")
            return await ctx.send("Hanya admin yang bisa memputuskan kolaborasi")

        self.logger.info(f"{server_id}: finding {judul}...")
        all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: cannot find any match")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.warning(f"{server_id}: found more than one match")
            select_single = await ctx.select_single(
                all_matches, lambda x: Selection(x.title, x.id), content="Pilih judul yang anda maksud!"
            )
            if select_single is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [select_single]

        project = all_matches[0]
        self.logger.info(f"{server_id}: found {project.title}")
        if len(project.kolaborasi) < 1:
            self.logger.warning(f"{server_id}: no kolaborators found")
            return await ctx.send("Tidak ada kolaborasi yang berlangsung untuk judul tersebut!")

        self.logger.info(f"{server_id}: checking konfirmations...")
        is_confirm = await ctx.confirm(f"Apakah anda yakin ingin memputuskan kolaborasi `{project.title}`")
        if not is_confirm:
            return await ctx.send("Dibatalkan!")

        self.logger.info(f"{server_id}: removing kolaborators...")
        update_queue: List[Showtimes] = []
        for osrv in project.kolaborasi:
            if osrv == server_id:
                continue
            osrv_data = await self.queue.fetch_database(osrv)
            if osrv_data is None:
                self.logger.warning(f"{server_id}: cannot be found at database")
                continue
            osrv_anime = osrv_data.get_project(project)
            if osrv_anime is None:
                self.logger.warning(f"{server_id}: cannot be found at database")
                continue
            osrv_anime.remove_kolaborator(server_id)
            if len(osrv_anime.kolaborasi) < 2:
                first_person = osrv_anime.kolaborasi[0]
                if first_person == osrv:
                    # Clean the kolaborasi data
                    osrv_anime.kolaborasi = []

            osrv_data.update_project(osrv_anime)
            update_queue.append(osrv_data)

        # Remove FSDB binding
        is_fsdb_binded = False
        if project.fsdb is not None:
            is_fsdb_binded = True
            project.fsdb = None

        project.kolaborasi = []
        srv_data.update_project(project)
        update_queue.append(srv_data)

        self.logger.info(f"{server_id}: updating database...")
        for server in update_queue:
            await self.queue.add_job(server)

        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value=f"Berhasil memputuskan kolaborasi **{project.title}**.\n"
            "Database utama akan diupdate sebentar lagi",
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating main database...")
        for update in update_queue:
            success, msg = await self.ntdb.update_server(update)
            if not success:
                self.logger.warning(f"{server_id}: failed to update, reason: {msg}")
                if update.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(update.id)

        await ctx.send(f"Berhasil memputuskan kolaborasi **{project.title}** dari database utama naoTimes")
        if is_fsdb_binded:
            await ctx.send(
                "Binding FansubDB untuk anime terputus, "
                f"silakan hubungkan ulang dengan: `{self.bot.prefixes(ctx)}fsdb bind {project.title}`"
            )


async def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesKolaborasi(bot))
