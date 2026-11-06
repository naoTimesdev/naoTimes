import logging
from enum import Enum

import discord
from discord import app_commands
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.showtimes import Showtimes, ShowtimesEpisodeStatus, ShowtimesProject
from naotimes.showtimes.slash import load_server, project_autocomplete, resolve_project
from naotimes.utils import get_current_time


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
        queue = bot.showqueue
        base = bot.showcogs
        ntdb = bot.ntdb
        if queue is None or base is None or ntdb is None:
            raise RuntimeError("Showtimes services must be initialized before loading this cog")
        self.queue = queue
        self.base = base
        self.ntdb = ntdb
        self.logger = logging.getLogger("Showtimes.Staff")

        self.resync_failed_server.start()

    async def cog_unload(self):
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
        project: ShowtimesProject,
        mode: ReleaseEnum = ReleaseEnum.SINGLE,
        episode: int | None = None,
        progress: ProgressEnum = ProgressEnum.DONE,
    ):
        self.logger.info(f"Requested release {project.title} at {server.id} with mode {mode}")

        matched_anime = project
        self.logger.info(f"{server.id}: matched {matched_anime.title}")
        current_episode = matched_anime.get_current()
        if progress == ProgressEnum.UNDONE:
            current_episode = matched_anime.get_previous_episode()
            if current_episode is None:
                return await ctx.send(ctx.t("rilis.no_previous"))
        else:
            if current_episode is None:
                return await ctx.send(ctx.t("errors.anime_finished"))
        if current_episode is None:
            return await ctx.send(ctx.t("errors.no_active_episode"))
        first_episode = matched_anime.status[0]
        final_episode = matched_anime.status[-1]
        should_update_fsdb = False
        fsdb_update_to = "Tentatif"

        if not matched_anime.assignment.can_release(ctx.author) and not server.is_admin(ctx.author):
            return await ctx.send(ctx.t("rilis.not_allowed"))

        if episode is None and mode == ReleaseEnum.BATCH:
            return await ctx.send(ctx.t("rilis.batch_count"))
        if mode == ReleaseEnum.BATCH and episode is None:
            return await ctx.send(ctx.t("rilis.batch_count"))
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

        joined_koleb: list[Showtimes] = []
        for kolaborasi in matched_anime.kolaborasi:
            if kolaborasi == server.id:
                continue
            osrv_info = await self.queue.fetch_database(str(kolaborasi))
            if osrv_info is not None:
                joined_koleb.append(osrv_info)

        updated_episode: list[int] = []
        text_update = ctx.t("rilis.single_done", title=matched_anime.title, episode=current_episode.episode)
        embed_update = ctx.t("rilis.single_done_embed", title=matched_anime.title, episode=current_episode.episode)
        if progress == ProgressEnum.UNDONE:
            text_update = ctx.t("rilis.single_undone", title=matched_anime.title, episode=current_episode.episode)
            embed_update = ctx.t("rilis.single_undone_embed", episode=current_episode.episode)
        if mode == ReleaseEnum.SINGLE:
            updated_episode.append(current_episode.episode)
        elif mode == ReleaseEnum.BATCH:
            if episode is None:
                return await ctx.send(ctx.t("rilis.batch_count"))
            # start episode
            start_ep = current_episode.episode
            hop_step = 1
            end_ep = start_ep
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
            text_update = ctx.t("rilis.range_done", title=matched_anime.title, start=start_ep, end=end_ep)
            embed_update = ctx.t("rilis.range_done_embed", title=matched_anime.title, start=start_ep, end=end_ep)
            updated_episode.extend(range(start_ep, end_ep + hop_step, hop_step))
            if progress == ProgressEnum.UNDONE:
                text_update = ctx.t("rilis.range_undone", title=matched_anime.title, end=end_ep, start=start_ep)
                embed_update = ctx.t("rilis.range_undone_embed", end=end_ep, start=start_ep)
        elif mode == ReleaseEnum.ALL:
            # start episode
            start_ep = current_episode.episode
            hop_step = 1
            end_ep = start_ep
            if progress == ProgressEnum.DONE:
                end_ep = final_episode.episode
            elif progress == ProgressEnum.UNDONE:
                end_ep = first_episode.episode
                hop_step = -1
            updated_episode.extend(range(start_ep, end_ep + hop_step, hop_step))
            text_update = ctx.t("rilis.range_done", title=matched_anime.title, start=start_ep, end=end_ep)
            embed_update = ctx.t("rilis.range_done_embed", title=matched_anime.title, start=start_ep, end=end_ep)
            if progress == ProgressEnum.UNDONE:
                text_update = ctx.t("rilis.range_undone", title=matched_anime.title, end=end_ep, start=start_ep)
                embed_update = ctx.t("rilis.range_undone_embed", end=end_ep, start=start_ep)

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

        save_queue: list[Showtimes] = []
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
            self.logger.info(f"{matched_anime.id}: Updating FSDB status data for project to {fsdb_update_to}...")
            if matched_anime.fsdb.id is not None:
                await self.bot.fsdb.update_project(matched_anime.fsdb.id, "status", fsdb_update_to)
        for all_srv in save_queue:
            self.logger.info(f"{all_srv.id}: updating server...")
            res, msg = await self.ntdb.update_server(all_srv)
            if not res:
                if all_srv.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(str(all_srv.id))
                self.logger.error(f"{all_srv.id}: failed to update, reason: {msg}")

        for update in save_queue:
            embed = discord.Embed(title=matched_anime.title, color=0x1EB5A6)
            nn_embed = ctx.t("rilis.embed_done")
            if progress == ProgressEnum.UNDONE:
                nn_embed = ctx.t("rilis.embed_undone")
                embed.colour = 0xB51E1E
            embed.add_field(name=nn_embed, value=embed_update, inline=False)
            embed.set_footer(text=ctx.t("footer.at", time=get_current_time(ctx.locale)))
            await self.base.announce_embed(self.bot, update.announcer, embed)

    # ------------------------------------------------------------------ slash helpers
    async def _project_auto(self, inter: discord.Interaction, current: str):
        return await project_autocomplete(self.bot, inter, current)

    async def _posisi_auto(self, inter: discord.Interaction, current: str):
        judul = getattr(inter.namespace, "judul", None)
        server = await self.queue.fetch_database(str(inter.guild.id)) if inter.guild else None
        if server is None or not judul:
            return []
        project = server.get_project(judul) or server.exact_match(judul)
        if project is None:
            return []
        choices = [
            app_commands.Choice(
                name=project.assignment.get_custom_name(role) or self.base.normalize_role_name(role, True),
                value=role,
            )
            for role, _ in project.assignment
        ]
        return [c for c in choices if current.lower() in c.name.lower() or current.lower() in c.value.lower()][:25]

    async def _release_entry(
        self,
        inter: discord.Interaction,
        judul: str,
        mode: ReleaseEnum,
        jumlah: int | None,
        progress: ProgressEnum,
    ):
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        if mode == ReleaseEnum.BATCH and (jumlah is None or jumlah < 1):
            return await inter.response.send_message(ctx.t("rilis.batch_option"), ephemeral=True)
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)
        await inter.response.defer()
        await self._do_release(ctx, srv_data, project, mode, jumlah, progress)

    @app_commands.command(
        name="rilis",
        description=app_commands.locale_str("Rilis episode yang sedang digarap", key="showtimes.rilis.description"),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        mode=app_commands.locale_str(
            "Satu episode (bawaan), batch beberapa episode, atau semua episode", key="showtimes.options.mode"
        ),
        jumlah=app_commands.locale_str("Jumlah episode (khusus mode batch)", key="showtimes.options.jumlah"),
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name=app_commands.locale_str("Satu episode", key="showtimes.choices.single"), value=0),
            app_commands.Choice(name=app_commands.locale_str("Batch", key="showtimes.choices.batch"), value=1),
            app_commands.Choice(name=app_commands.locale_str("Semua", key="showtimes.choices.all"), value=2),
        ]
    )
    async def _showstaff_rilis(
        self,
        inter: discord.Interaction,
        judul: str,
        mode: app_commands.Choice[int] | None = None,
        jumlah: app_commands.Range[int, 1, 100] | None = None,
    ):
        release_mode = ReleaseEnum(mode.value if mode is not None else 0)
        await self._release_entry(inter, judul, release_mode, jumlah, ProgressEnum.DONE)

    @app_commands.command(
        name="batalrilis",
        description=app_commands.locale_str("Batalkan rilisan episode", key="showtimes.batalrilis.description"),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        mode=app_commands.locale_str(
            "Satu episode (bawaan), batch beberapa episode, atau semua episode", key="showtimes.options.mode"
        ),
        jumlah=app_commands.locale_str("Jumlah episode (khusus mode batch)", key="showtimes.options.jumlah"),
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name=app_commands.locale_str("Satu episode", key="showtimes.choices.single"), value=0),
            app_commands.Choice(name=app_commands.locale_str("Batch", key="showtimes.choices.batch"), value=1),
            app_commands.Choice(name=app_commands.locale_str("Semua", key="showtimes.choices.all"), value=2),
        ]
    )
    async def _showstaff_batalrilis(
        self,
        inter: discord.Interaction,
        judul: str,
        mode: app_commands.Choice[int] | None = None,
        jumlah: app_commands.Range[int, 1, 100] | None = None,
    ):
        release_mode = ReleaseEnum(mode.value if mode is not None else 0)
        await self._release_entry(inter, judul, release_mode, jumlah, ProgressEnum.UNDONE)

    def _create_progress_embed(
        self, ctx: naoTimesContext, project_info: ShowtimesProject, episode_info: ShowtimesEpisodeStatus
    ):
        statuses = self.base.parse_status(episode_info.progress)

        poster_image, poster_color = project_info.poster.url, project_info.poster.color
        embed = discord.Embed(
            title=ctx.t("tagih.embed_title", title=project_info.title, episode=episode_info.episode),
            color=poster_color,
        )
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name=ctx.t("embed.status"), value=statuses, inline=False)
        embed.add_field(name=ctx.t("embed.last_update"), value=ctx.t("embed.recent"), inline=False)
        embed.set_footer(text=ctx.t("footer.credit"), icon_url="https://naoti.me/assets/img/nt192.png")
        return embed

    async def _do_beres_batal(
        self,
        ctx: naoTimesContext,
        server: Showtimes,
        mode: ProgressEnum,
        posisi: str | None,
        posisi_asli: str,
        project: ShowtimesProject,
        episode: int | None = None,
    ):
        """A function to be used for !beres and !gakjadi"""
        server_id = server.id

        if mode == ProgressEnum.TOGGLE and episode is None:
            return await ctx.send(ctx.t("progress.empty_episode"))

        matched_anime = project
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        is_custom = False
        if posisi is None:
            valid_position = ["tl", "tlc", "enc", "ed", "tm", "ts"]
            for custom in matched_anime.assignment.custom:
                valid_position.append(custom.key.lower())
            valid_position.append("qc")
            if posisi_asli.lower() not in valid_position:
                return await ctx.send(
                    ctx.t(
                        "progress.unknown_position",
                        position=posisi_asli,
                        available="`, `".join(valid_position),
                    )
                )
            posisi = posisi_asli.lower()
            is_custom = True

        if not matched_anime.assignment.can_toggle(posisi, ctx.author) and not server.is_admin(ctx.author):
            return

        active_episode = matched_anime.get_current()
        log_pre = f"{server_id}-{matched_anime.title}"
        if active_episode is None:
            self.logger.warning(f"{log_pre}: no active episode left")
            return await ctx.send(ctx.t("errors.already_finished"))

        if mode == ProgressEnum.TOGGLE:
            if episode is None:
                return await ctx.send(ctx.t("progress.episode_required"))
            active_episode = matched_anime.get_episode(episode)
            if active_episode is None:
                self.logger.warning(f"{log_pre}: episode out of range")
                return await ctx.send(ctx.t("progress.episode_not_found"))

        is_done = mode == ProgressEnum.DONE
        posisi = posisi.upper()
        self.logger.info(f"{log_pre}: setting {posisi} for episode {active_episode.episode} to {is_done}")
        if mode == ProgressEnum.TOGGLE:
            active_episode.progress.toggle(posisi, not active_episode.progress.get(posisi))
        else:
            if is_done and active_episode.progress.get(posisi):
                return await ctx.send(ctx.t("progress.already_done"))
            elif not is_done and not active_episode.progress.get(posisi):
                return await ctx.send(ctx.t("progress.already_undone"))
            active_episode.progress.toggle(posisi, is_done)
        matched_anime.status = active_episode
        server.update_project(matched_anime)

        update_queue: list[Showtimes] = []
        update_queue.append(server)
        for osrv in matched_anime.kolaborasi:
            if osrv == server_id:
                continue
            osrv_srv = await self.queue.fetch_database(str(osrv))
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
            toggle_to = (
                ctx.t("progress.toggled_done")
                if active_episode.progress.get(posisi)
                else ctx.t("progress.toggled_undone")
            )
            await ctx.send(
                ctx.t(
                    "progress.toggle_success",
                    position=posisi,
                    title=matched_anime.title,
                    episode=active_episode.episode,
                    state=toggle_to,
                )
            )
        else:
            await ctx.send(ctx.t("progress.change_success", title=matched_anime.title, episode=active_episode.episode))

        for peladen in update_queue:
            self.logger.info(f"{peladen.id}: Updating database...")
            success, msg = await self.ntdb.update_server(peladen)
            if not success:
                if peladen.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(str(peladen.id))
                self.logger.warning(f"{peladen.id}: Failed to update database: {msg}")

        if mode == ProgressEnum.TOGGLE:
            # Dont sent announce message
            return

        color_pog = discord.Color.from_rgb(120, 222, 118)
        if mode == ProgressEnum.UNDONE:
            color_pog = discord.Color.from_rgb(218, 97, 97)

        self.logger.info(f"{log_pre}: Sending progress to all servers...")
        for update in update_queue:
            embed = discord.Embed(
                title=ctx.t("tagih.embed_title", title=matched_anime.title, episode=active_episode.episode),
                color=color_pog,
            )
            embed.add_field(
                name=ctx.t("embed.status"),
                value=self.base.parse_status(active_episode.progress),
                inline=False,
            )
            embed.set_thumbnail(url=None)
            pre_tar = "✅"
            if not is_done:
                pre_tar = "❌"
            posisi_as_name = self.base.normalize_role_name(posisi)
            if is_custom:
                self.logger.info(f"{log_pre}: {posisi} is custom role")
                posisi_as_name = active_episode.progress.get_custom_name(posisi) or posisi_as_name
            embed.description = f"{pre_tar} {posisi_as_name}"
            embed.set_footer(text=ctx.t("footer.at", time=get_current_time(ctx.locale)))
            await self.base.announce_embed(self.bot, update.announcer, embed)

        self.logger.info(f"{log_pre}: Sending final information to staff...")
        await ctx.send(embed=self._create_progress_embed(ctx, matched_anime, active_episode))

    async def _progress_entry(
        self,
        inter: discord.Interaction,
        judul: str,
        posisi: str,
        mode: ProgressEnum,
        episode: int | None = None,
    ):
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)
        posisi_r, posisi_asli = self.base.get_roles(posisi)
        await inter.response.defer()
        ctx = await self.bot.get_context(inter)
        await self._do_beres_batal(ctx, srv_data, mode, posisi_r, posisi_asli, project, episode)

    @app_commands.command(
        name="beres",
        description=app_commands.locale_str(
            "Tandai posisi sudah selesai dikerjakan", key="showtimes.beres.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        posisi=app_commands.locale_str("Posisi yang sudah beres", key="showtimes.beres.option_posisi"),
    )
    async def _showstaff_beres(self, inter: discord.Interaction, judul: str, posisi: str):
        await self._progress_entry(inter, judul, posisi, ProgressEnum.DONE)

    @app_commands.command(
        name="gakjadi",
        description=app_commands.locale_str("Batalkan tanda beres sebuah posisi", key="showtimes.gakjadi.description"),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        posisi=app_commands.locale_str("Posisi yang dibatalkan", key="showtimes.gakjadi.option_posisi"),
    )
    async def _showstaff_gakjadi(self, inter: discord.Interaction, judul: str, posisi: str):
        await self._progress_entry(inter, judul, posisi, ProgressEnum.UNDONE)

    @app_commands.command(
        name="tandakan",
        description=app_commands.locale_str(
            "Ubah (toggle) status posisi di episode tertentu", key="showtimes.tandakan.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        posisi=app_commands.locale_str("Posisi yang diubah", key="showtimes.tandakan.option_posisi"),
        episode=app_commands.locale_str("Nomor episode", key="showtimes.tandakan.option_episode"),
    )
    async def _showstaff_tandakan(
        self, inter: discord.Interaction, judul: str, posisi: str, episode: app_commands.Range[int, 1, 10000]
    ):
        await self._progress_entry(inter, judul, posisi, ProgressEnum.TOGGLE, episode)

    for _cmd in (_showstaff_rilis, _showstaff_batalrilis, _showstaff_beres, _showstaff_gakjadi, _showstaff_tandakan):
        _cmd.autocomplete("judul")(_project_auto)
    for _cmd in (_showstaff_beres, _showstaff_gakjadi, _showstaff_tandakan):
        _cmd.autocomplete("posisi")(_posisi_auto)
    del _cmd


async def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesStaff(bot))
