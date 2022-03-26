import logging
from enum import Enum
from typing import List, Optional

import disnake
from disnake.embeds import EmptyEmbed
from disnake.ext import commands, tasks

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.showtimes import Showtimes, ShowtimesEpisodeStatus, ShowtimesProject
from naotimes.utils import get_current_time, get_indexed


class ReleaseEnum(Enum):
    SINGLE = 0
    BATCH = 1
    ALL = 2


class ProgressEnum(Enum):
    DONE = 1
    UNDONE = -1
    TOGGLE = 0


class ShowtimesStaff(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.queue = bot.showqueue
        self.base = bot.showcogs
        self.ntdb = bot.ntdb
        self.logger = logging.getLogger("Showtimes.Staff")

        self.resync_failed_server.start()

    def cog_unload(self):
        self.resync_failed_server.cancel()

    @tasks.loop(minutes=1.0)
    async def resync_failed_server(self):
        if not self.bot.showtimes_resync:
            return
        self.logger.info("Trying to resynchronizing failed server...")
        for server in self.bot.showtimes_resync:
            self.logger.info(f"Resyncing {server}")
            srv_data = await self.queue.fetch_database(server)
            if srv_data is None:
                self.bot.showtimes_resync.remove(server)
                continue
            res, msg = await self.ntdb.update_server(srv_data)
            if not res:
                self.logger.error(f"Failed to resync {server}: {msg}")
                continue
            self.logger.info(f"{server} resynced successfully!")
            self.bot.showtimes_resync.remove(server)
        lefts = len(self.bot.showtimes_resync)
        self.logger.info(f"Finished! Leftover to resync are {lefts} servers")

    async def _do_release(
        self,
        ctx: naoTimesContext,
        server: Showtimes,
        title: str = None,
        mode: ReleaseEnum = ReleaseEnum.SINGLE,
        episode: Optional[int] = None,
        progress: ProgressEnum = ProgressEnum.DONE,
    ):
        self.logger.info(f"Requested release {title} at {server.id} with mode {mode}")

        all_matches = server.find_projects(title)
        if len(all_matches) < 1:
            self.logger.warning(f"{server.id}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.info(f"{server.id}: found multiple matches!")
            selected_anime = await ctx.select_simple(all_matches, lambda x: x.title)
            if selected_anime is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [selected_anime]

        matched_anime = all_matches[0]
        self.logger.info(f"{server.id}: matched {matched_anime.title}")
        current_episode = matched_anime.get_current()
        if progress == ProgressEnum.UNDONE:
            current_episode = matched_anime.get_previous_episode()
            if current_episode is None:
                return await ctx.send("Belum ada Episode yang dirilis?")
        else:
            if current_episode is None:
                return await ctx.send("Anime telah selesai digarap!")
        first_episode = matched_anime.status[0]
        final_episode = matched_anime.status[-1]
        should_update_fsdb = False
        fsdb_update_to = "Tentatif"

        if not matched_anime.assignment.can_release(ctx.author) and not server.is_admin(ctx.author):
            return await ctx.send(
                "**Tidak secepat itu ferguso, yang bisa melakukan perintah rilis hanyalah admin atau QCer**"
            )

        if episode is None and mode == ReleaseEnum.BATCH:
            return await ctx.send("Mohon ketik jumlah episode yang benar")
        if progress == ProgressEnum.DONE:
            if mode == ReleaseEnum.SINGLE:
                if current_episode.episode == final_episode.episode:
                    should_update_fsdb = True
                    fsdb_update_to = "Tamat"
                elif current_episode.episode >= first_episode.episode:
                    fsdb_update_to = "Jalan"
                    should_update_fsdb = True
                    if current_episode.episode == final_episode.episode:
                        fsdb_update_to = "Tamat"
            elif mode == ReleaseEnum.BATCH:
                fsdb_update_to = "Jalan"
                should_update_fsdb = True
            elif mode == ReleaseEnum.ALL:
                fsdb_update_to = "Tamat"
                should_update_fsdb = True
        elif progress == ProgressEnum.UNDONE:
            if mode == ReleaseEnum.SINGLE:
                if current_episode.episode == first_episode.episode:
                    should_update_fsdb = True
                elif current_episode.episode > first_episode.episode:
                    should_update_fsdb = True
                    fsdb_update_to = "Jalan"
            elif mode == ReleaseEnum.BATCH:
                should_update_fsdb = True
                fsdb_update_to = "Jalan"
            elif mode == ReleaseEnum.ALL:
                should_update_fsdb = True

        joined_koleb: List[Showtimes] = []
        for kolaborasi in matched_anime.kolaborasi:
            if kolaborasi == server.id:
                continue
            osrv_info = await self.queue.fetch_database(kolaborasi)
            if osrv_info is not None:
                joined_koleb.append(osrv_info)

        updated_episode = []
        text_update = f"**{matched_anime.title} - #{current_episode.episode}** telah dirilis"
        embed_update = f"{matched_anime.title} - #{current_episode.episode} telah dirilis!"
        if progress == ProgressEnum.UNDONE:
            text_update = (
                f"Berhasil membatalkan rilisan **{matched_anime.title}** episode #{current_episode.episode}"
            )
            embed_update = (
                f"Rilisan **episode #{current_episode.episode}** dibatalkan dan sedang dikerjakan kembali"
            )
        if mode == ReleaseEnum.SINGLE:
            updated_episode.append(current_episode.episode)
        elif mode == ReleaseEnum.BATCH:
            # start episode
            start_ep = current_episode.episode
            hop_step = 1
            if progress == ProgressEnum.DONE:
                end_ep = start_ep + episode
                if end_ep >= final_episode.episode:
                    should_update_fsdb = True
                    fsdb_update_to = "Tamat"
                    end_ep = final_episode.episode
            elif progress == ProgressEnum.UNDONE:
                end_ep = start_ep - episode
                if end_ep < first_episode.episode:
                    should_update_fsdb = True
                    fsdb_update_to = "Tentatif"
                    end_ep = first_episode.episode
                hop_step = -1
            text_update = f"**{matched_anime.title} - #{start_ep} sampai #{end_ep}** telah dirilis"
            embed_update = f"{matched_anime.title} - #{start_ep} sampai #{end_ep} telah dirilis!"
            updated_episode.extend(range(start_ep, end_ep + hop_step, hop_step))
            if progress == ProgressEnum.UNDONE:
                text_update = f"Berhasil membatalkan rilisan **{matched_anime.title}** "
                text_update += f"episode #{end_ep} sampai #{start_ep}"
                embed_update = f"Rilisan **episode #{end_ep} sampai {start_ep}** dibatalkan"
                embed_update += " dan sedang dikerjakan kembali"
        elif mode == ReleaseEnum.ALL:
            # start episode
            start_ep = current_episode.episode
            hop_step = 1
            if progress == ProgressEnum.DONE:
                end_ep = final_episode.episode
            elif progress == ProgressEnum.UNDONE:
                end_ep = first_episode.episode
                hop_step = -1
            updated_episode.extend(range(start_ep, end_ep + hop_step, hop_step))
            text_update = f"**{matched_anime.title} - #{start_ep} sampai #{end_ep}** telah dirilis"
            embed_update = f"{matched_anime.title} - #{start_ep} sampai #{end_ep} telah dirilis!"
            if progress == ProgressEnum.UNDONE:
                text_update = f"Berhasil membatalkan rilisan **{matched_anime.title}** "
                text_update += f"episode #{end_ep} sampai #{start_ep}"
                embed_update = f"Rilisan **episode #{end_ep} sampai {start_ep}** dibatalkan"
                embed_update += " dan sedang dikerjakan kembali"

        for episode in updated_episode:
            if episode == current_episode.episode:
                current_episode.finished = progress == ProgressEnum.DONE
                matched_anime.status = current_episode
                continue
            the_episode = matched_anime.get_episode(episode)
            if the_episode is None:
                continue
            the_episode.finished = progress == ProgressEnum.DONE
            matched_anime.status = the_episode

        save_queue: List[Showtimes] = []
        server.update_project(matched_anime)
        save_queue.append(server)
        for osrv in joined_koleb:
            osrv_project = osrv.get_project(matched_anime)
            if osrv_project is None:
                continue
            any_update = False
            for episode in updated_episode:
                osrv_episode = osrv_project.get_episode(episode)
                if osrv_episode is None:
                    continue
                any_update = True
                osrv_episode.finished = True
                osrv_project.status = osrv_episode
            if any_update:
                osrv.update_project(osrv_project)
                save_queue.append(osrv)

        for all_srv in save_queue:
            self.logger.info(f"Saving to ShowQueue: {all_srv.id}")
            await self.queue.add_job(all_srv)

        self.logger.info(f"{server.id}: sending success message!")
        await ctx.send(text_update)

        if matched_anime.fsdb is not None and should_update_fsdb and self.bot.fsdb is not None:
            self.logger.info(
                f"{matched_anime.id}: Updating FSDB status data for project to {fsdb_update_to}..."
            )
            if matched_anime.fsdb.id is not None:
                await self.bot.fsdb.update_project(matched_anime.fsdb.id, "status", fsdb_update_to)
        for all_srv in save_queue:
            self.logger.info(f"{all_srv.id}: updating server...")
            res, msg = await self.ntdb.update_server(all_srv)
            if not res:
                if all_srv.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(all_srv.id)
                self.logger.error(f"{all_srv.id}: failed to update, reason: {msg}")

        for update in save_queue:
            embed = disnake.Embed(title=matched_anime.title, color=0x1EB5A6)
            nn_embed = "Rilis!"
            if progress == ProgressEnum.UNDONE:
                nn_embed = "Batal rilis..."
                embed.colour = 0xB51E1E
            embed.add_field(name=nn_embed, value=embed_update, inline=False)
            embed.set_footer(text=f"Pada: {get_current_time()}")
            await self.bot.showcogs.announce_embed(self.bot, update.announcer, embed)

    @commands.group(name="rilis", aliases=["release"])
    @commands.guild_only()
    async def _showstaff_rilis(self, ctx: naoTimesContext):
        """Showtimes staff release command"""
        if ctx.invoked_subcommand is None:
            pesan: disnake.Message = ctx.message
            split_content = pesan.clean_content.split(" ")
            the_real_title = None
            for pos, konten in enumerate(split_content):
                if "rilis" in konten.lower() or "release" in konten.lower():
                    the_real_title = get_indexed(split_content, pos + 1)
                    if isinstance(the_real_title, str) and not the_real_title.strip():
                        the_real_title = None

            srv_data = await self.queue.fetch_database(ctx.guild.id)
            if srv_data is None:
                return
            self.logger.info(f"{ctx.guild.id}: showtimes data found!")
            if not the_real_title:
                return await self.base.send_all_projects(ctx, srv_data)

            await self._do_release(ctx, srv_data, the_real_title, ReleaseEnum.SINGLE)

    @_showstaff_rilis.command(name="batch")
    async def _showstaff_rilis_batch(self, ctx: naoTimesContext, episode: int, *, judul: str = None):
        """Batch release command"""
        srv_data = await self.queue.fetch_database(ctx.guild.id)
        if srv_data is None:
            return
        self.logger.info(f"{ctx.guild.id}: showtimes data found!")
        if episode < 1:
            return await ctx.send("Mohon tulis episode lebih dari angka 0!")
        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        await self._do_release(ctx, srv_data, judul, ReleaseEnum.BATCH, episode)

    @_showstaff_rilis.command(name="semua")
    async def _showstaff_rilis_semua(self, ctx: naoTimesContext, *, judul: str = None):
        """Full episode release command"""
        srv_data = await self.queue.fetch_database(ctx.guild.id)
        if srv_data is None:
            return
        self.logger.info(f"{ctx.guild.id}: showtimes data found!")
        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        await self._do_release(ctx, srv_data, judul, ReleaseEnum.ALL)

    @commands.group(name="batalrilis", aliases=["undorelease", "revertrelease"])
    @commands.guild_only()
    async def _showstaff_batalrilis(self, ctx: naoTimesContext):
        """Showtimes staff release command"""
        if ctx.invoked_subcommand is None:
            pesan: disnake.Message = ctx.message
            split_content = pesan.clean_content.split(" ")
            the_real_title = None
            for pos, konten in enumerate(split_content):
                if "rilis" in konten.lower() or "release" in konten.lower():
                    the_real_title = get_indexed(split_content, pos + 1)
                    if isinstance(the_real_title, str) and not the_real_title.strip():
                        the_real_title = None

            srv_data = await self.queue.fetch_database(ctx.guild.id)
            if srv_data is None:
                return
            self.logger.info(f"{ctx.guild.id}: showtimes data found!")
            if not the_real_title:
                return await self.base.send_all_projects(ctx, srv_data)

            await self._do_release(
                ctx, srv_data, the_real_title, ReleaseEnum.SINGLE, progress=ProgressEnum.UNDONE
            )

    @_showstaff_batalrilis.command(name="batch")
    async def _showstaff_batalrilis_batch(self, ctx: naoTimesContext, episode: int, *, judul: str = None):
        """Batch release command"""
        srv_data = await self.queue.fetch_database(ctx.guild.id)
        if srv_data is None:
            return
        self.logger.info(f"{ctx.guild.id}: showtimes data found!")
        if episode < 1:
            return await ctx.send("Mohon tulis episode lebih dari angka 0!")
        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        await self._do_release(ctx, srv_data, judul, ReleaseEnum.BATCH, episode, ProgressEnum.UNDONE)

    @_showstaff_batalrilis.command(name="semua")
    async def _showstaff_batalrilis_semua(self, ctx: naoTimesContext, *, judul: str = None):
        """Full episode release command"""
        srv_data = await self.queue.fetch_database(ctx.guild.id)
        if srv_data is None:
            return
        self.logger.info(f"{ctx.guild.id}: showtimes data found!")
        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        await self._do_release(ctx, srv_data, judul, ReleaseEnum.ALL, progress=ProgressEnum.UNDONE)

    @staticmethod
    def _create_progress_embed(project_info: ShowtimesProject, episode_info: ShowtimesEpisodeStatus):
        status_lists = []
        for work, c_stat in episode_info.progress:
            wrap = "~~" if c_stat else "**"
            status_lists.append(f"{wrap}{work}{wrap}")
        statuses = " ".join(status_lists)

        poster_image, poster_color = project_info.poster.url, project_info.poster.color
        embed = disnake.Embed(title=f"{project_info.title} - #{episode_info.episode}", color=poster_color)
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name="Status", value=statuses, inline=False)
        embed.add_field(name="Update Terakhir", value="Baru saja", inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™", icon_url="https://naoti.me/assets/img/nt192.png")
        return embed

    async def _do_beres_batal(
        self,
        ctx: naoTimesContext,
        server: Showtimes,
        mode: ProgressEnum,
        posisi: str,
        judul=None,
        episode: int = None,
    ):
        """A function to be used for !beres and !gakjadi"""
        server_id: int = ctx.guild.id
        self.logger.info(f"{server_id}: getting close matches...")
        all_matches = server.find_projects(judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.info(f"{server_id}: found multiple matches!")
            selected_anime = await ctx.select_simple(all_matches, lambda x: x.title)
            if selected_anime is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [selected_anime]

        if mode == ProgressEnum.TOGGLE and episode is None:
            return await ctx.send("Episode kosong tetapi meminta perintah tandakan...?")

        matched_anime = all_matches[0]
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        if not matched_anime.assignment.can_toggle(posisi, ctx.author) and not server.is_admin(ctx.author):
            return

        active_episode = matched_anime.get_current()
        log_pre = f"{server_id}-{matched_anime.title}"
        if active_episode is None:
            self.logger.warning(f"{log_pre}: no active episode left")
            return await ctx.send("**Sudah selesai digarap!**")

        if mode == ProgressEnum.TOGGLE:
            active_episode = matched_anime.get_episode(episode)
            if active_episode is None:
                self.logger.warning(f"{log_pre}: episode out of range")
                return await ctx.send("Episode tersebut tidak ada di database.")

        is_done = mode == ProgressEnum.DONE
        posisi = posisi.upper()
        self.logger.info(f"{log_pre}: setting {posisi} for episode {active_episode.episode} to {is_done}")
        if mode == ProgressEnum.TOGGLE:
            active_episode.progress.toggle(posisi, not active_episode.progress.get(posisi))
        else:
            if is_done and active_episode.progress.get(posisi):
                return await ctx.send('Role tersebut sudah ditandakan sebagai "Beres".')
            elif not is_done and not active_episode.progress.get(posisi):
                return await ctx.send('Role tersebut sudah ditandakan sebagai "Gak Jadi".')
            active_episode.progress.toggle(posisi, is_done)
        matched_anime.status = active_episode
        server.update_project(matched_anime)

        update_queue: List[Showtimes] = []
        update_queue.append(server)
        for osrv in matched_anime.kolaborasi:
            if osrv == server_id:
                continue
            osrv_srv = await self.queue.fetch_database(osrv)
            if osrv_srv is None:
                continue
            osrv_project = osrv_srv.get_project(matched_anime)
            if osrv_project is None:
                continue
            osrv_project.status = active_episode
            osrv_srv.update_project(osrv_project)
            update_queue.append(osrv_srv)

        for peladen in update_queue:
            await self.queue.add_job(peladen)
        self.logger.info(f"{log_pre}: sending progress info to staff...")
        if mode == ProgressEnum.TOGGLE:
            toggle_to = "beres" if active_episode.progress.get(posisi) else "belum beres"
            await ctx.send(
                f"Berhasil mengubah status `{posisi}` **{matched_anime.title}** episode "
                f"**#{active_episode.episode}** ke **{toggle_to}**"
            )
        else:
            await ctx.send(
                f"Berhasil mengubah status garapan {matched_anime.title} - #{active_episode.episode}"
            )

        for peladen in update_queue:
            self.logger.info(f"{peladen.id}: Updating database...")
            success, msg = await self.ntdb.update_server(peladen)
            if not success:
                if peladen.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(peladen.id)
                self.logger.warning(f"{peladen.id}: Failed to update database: {msg}")

        if mode == ProgressEnum.TOGGLE:
            # Dont sent announce message
            return

        color_pog = disnake.Color.from_rgb(120, 222, 118)
        if mode == ProgressEnum.UNDONE:
            color_pog = disnake.Color.from_rgb(218, 97, 97)

        self.logger.info(f"{log_pre}: Sending progress to all servers...")
        for update in update_queue:
            embed = disnake.Embed(title=f"{matched_anime.title} - #{active_episode.episode}", color=color_pog)
            embed.add_field(
                name="Status", value=self.base.parse_status(active_episode.progress), inline=False
            )
            embed.set_thumbnail(url=EmptyEmbed)
            pre_tar = "✅"
            if not is_done:
                pre_tar = "❌"
            embed.description = f"{pre_tar} {self.base.normalize_role_name(posisi)}"
            embed.set_footer(text=f"Pada: {get_current_time()}")
            await self.bot.showcogs.announce_embed(self.bot, update.announcer, embed)

        self.logger.info(f"{log_pre}: Sending final information to staff...")
        await ctx.send(embed=self._create_progress_embed(matched_anime, active_episode))

    @commands.command(name="beres", aliases=["done"])
    async def _showstaff_beres(self, ctx: naoTimesContext, posisi: str, *, judul: str = None):
        """Showtimes staff done command"""
        server_id = ctx.guild.id
        self.logger.info(f"Requested beres at: {server_id}")
        posisi, posisi_asli = self.base.get_roles(posisi)
        if posisi is None:
            self.logger.warning("Unknown position")
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        await self._do_beres_batal(ctx, srv_data, ProgressEnum.DONE, posisi, judul)

    @commands.command(name="gakjadi", aliases=["undone", "cancel"])
    async def _showstaff_gakjadi(self, ctx: naoTimesContext, posisi: str, *, judul: str = None):
        """Showtimes staff undone command"""
        server_id = ctx.guild.id
        self.logger.info(f"Requested gakjadi at: {server_id}")
        posisi, posisi_asli = self.base.get_roles(posisi)
        if posisi is None:
            self.logger.warning("Unknown position")
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        await self._do_beres_batal(ctx, srv_data, ProgressEnum.UNDONE, posisi, judul)

    @commands.command(name="tandakan", aliases=["mark"])
    async def _showstaff_tandakan(
        self, ctx: naoTimesContext, posisi: str, episode: int, *, judul: str = None
    ):
        """Showtimes toggle position command"""
        server_id = ctx.guild.id
        self.logger.info(f"Requested tandakan at: {server_id}")
        posisi, posisi_asli = self.base.get_roles(posisi)
        if posisi is None:
            self.logger.warning("Unknown position")
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        await self._do_beres_batal(ctx, srv_data, ProgressEnum.TOGGLE, posisi, judul, episode)


def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    bot.add_cog(ShowtimesStaff(bot))
