import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.showtimes import (
    Showtimes,
    ShowtimesAssigneeCustom,
    ShowtimesEpisodeStatus,
    ShowtimesEpisodeStatusChild,
    ShowtimesProject,
)
from naotimes.showtimes.slash import load_server, project_autocomplete, resolve_project
from naotimes.utils import get_current_time

BASE_ROLE_KEYS = ("TL", "TLC", "ENC", "ED", "TM", "TS", "QC")
MAX_CUSTOM_ROLES = 5


class ShowtimesAdmin(commands.Cog):
    ubahdata = app_commands.Group(
        name="ubahdata",
        description=app_commands.locale_str("Ubah data garapan fansub (admin)", key="showtimes.ubahdata.description"),
        guild_only=True,
    )
    ubah_staff = app_commands.Group(
        name="staff",
        description=app_commands.locale_str("Ubah staff garapan", key="showtimes.ubahdata.group_staff"),
        parent=ubahdata,
    )
    ubah_episode = app_commands.Group(
        name="episode",
        description=app_commands.locale_str("Ubah jumlah episode", key="showtimes.ubahdata.group_episode"),
        parent=ubahdata,
    )
    ubah_role = app_commands.Group(
        name="role",
        description=app_commands.locale_str("Atur role custom garapan", key="showtimes.ubahdata.group_role"),
        parent=ubahdata,
    )

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
        self.logger = logging.getLogger("Showtimes.Admin")

    # ------------------------------------------------------------------ helpers
    async def _commit(self, server_id: str, servers: list[Showtimes]) -> None:
        """Queue the new data for saving, then sync the main database (retry later on failure)."""
        for server in servers:
            await self.queue.add_job(server)
        for server in servers:
            self.logger.info(f"{server_id}: updating main database for {server.id}...")
            success, msg = await self.ntdb.update_server(server)
            if not success:
                if server.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(str(server.id))
                self.logger.error(f"{server_id}: failed to update {server.id}, reason: {msg}")

    async def _collaborators(self, project: ShowtimesProject, current_server_id) -> list[Showtimes]:
        servers: list[Showtimes] = []
        for osrv in project.kolaborasi:
            if str(osrv) == str(current_server_id):
                continue
            osrv_srv = await self.queue.fetch_database(str(osrv))
            if osrv_srv is not None:
                servers.append(osrv_srv)
        return servers

    async def _admin_project(self, inter: discord.Interaction, judul: str, *, admin_only: bool = True):
        """Load server + project, replying with the error if anything fails.

        Returns ``(server, project)`` or ``(None, None)`` when a reply was already sent.
        """
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return None, None
        if admin_only and not srv_data.is_admin(inter.user):
            await inter.response.send_message(ctx.t("ubahdata.admin_only"), ephemeral=True)
            return None, None
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            await inter.response.send_message(error, ephemeral=True)
            return None, None
        return srv_data, project

    async def _project_auto(self, inter: discord.Interaction, current: str):
        return await project_autocomplete(self.bot, inter, current)

    # ------------------------------------------------------------------ delay
    async def _set_delay(self, inter: discord.Interaction, judul: str, reason: str | None):
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        server_id = str(srv_data.id)
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)

        current_episode = project.get_current()
        if current_episode is None:
            return await inter.response.send_message(ctx.t("errors.anime_finished"), ephemeral=True)
        if not project.assignment.can_release(inter.user) and not srv_data.is_admin(inter.user):
            return await inter.response.send_message(ctx.t("delay.admin_only"), ephemeral=True)

        reason_text = ctx.t("delay.reason_set", reason=reason) if reason else ctx.t("delay.reason_removed")
        check = ctx.t("delay.confirm", title=project.title, episode=current_episode.episode, reason=reason_text)
        if not await ctx.confirm(check):
            return await ctx.send(ctx.t("errors.cancelled"))

        current_episode.delay_reason = reason
        project.status = current_episode
        srv_data.update_project(project)

        update_queue: list[Showtimes] = [srv_data]
        for osrv_srv in await self._collaborators(project, server_id):
            osrv_project = osrv_srv.get_project(project)
            if osrv_project is None:
                continue
            osrv_project.status = current_episode
            osrv_srv.update_project(osrv_project)
            update_queue.append(osrv_srv)

        await ctx.send(ctx.t("delay.updated") if reason else ctx.t("delay.removed"))
        await self._commit(server_id, update_queue)

    @app_commands.command(
        name="delay",
        description=app_commands.locale_str(
            "Tambah alasan delay untuk episode yang sedang digarap", key="showtimes.delay.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        alasan=app_commands.locale_str("Alasan delay", key="showtimes.delay.option_alasan"),
    )
    async def _showadmin_alasandelay(self, inter: discord.Interaction, judul: str, alasan: str):
        await self._set_delay(inter, judul, alasan)

    @app_commands.command(
        name="hapusdelay",
        description=app_commands.locale_str(
            "Hapus alasan delay episode yang sedang digarap", key="showtimes.hapusdelay.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _showadmin_hapusalasandelay(self, inter: discord.Interaction, judul: str):
        await self._set_delay(inter, judul, None)

    _showadmin_alasandelay.autocomplete("judul")(_project_auto)
    _showadmin_hapusalasandelay.autocomplete("judul")(_project_auto)

    # ------------------------------------------------------------------ ubahdata: staff
    @ubah_staff.command(
        name="set",
        description=app_commands.locale_str(
            "Ganti orang yang mengerjakan sebuah posisi", key="showtimes.ubahdata.staff_set"
        ),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        posisi=app_commands.locale_str("Posisi staff", key="showtimes.ubahdata.option_posisi"),
        orang=app_commands.locale_str("Orang yang menggantikan", key="showtimes.ubahdata.option_orang"),
    )
    async def _ubah_staff_set(self, inter: discord.Interaction, judul: str, posisi: str, orang: discord.Member):
        ctx = await self.bot.get_context(inter)
        srv_data, project = await self._admin_project(inter, judul)
        if srv_data is None or project is None:
            return
        keys = {k for k, _ in project.assignment}
        if posisi not in keys:
            return await inter.response.send_message(ctx.t("ubahdata.unknown_position"), ephemeral=True)

        project.update_assignment(posisi, orang)
        srv_data.update_project(project)
        await inter.response.send_message(
            ctx.t(
                "ubahdata.staff_replaced",
                role=self._role_name(project, posisi),
                title=project.title,
                mention=orang.mention,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self._save_with_collaborators(inter, srv_data, project)

    @ubah_staff.command(
        name="list",
        description=app_commands.locale_str("Lihat staff saat ini", key="showtimes.ubahdata.staff_list"),
    )
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _ubah_staff_list(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        _, project = await self._admin_project(inter, judul)
        if project is None:
            return
        embed = discord.Embed(
            title=ctx.t("ubahdata.staff_embed_title"),
            description=ctx.t("ubahdata.staff_embed_description", title=project.title),
            color=0xEBA279,
        )
        for role, staffer in project.assignment:
            name = self._user_name(staffer.id, ctx.t("ubahdata.unknown_user"))
            embed.add_field(name=self._role_name(project, role), value=name, inline=False)
        await inter.response.send_message(embed=embed, ephemeral=True)

    @_ubah_staff_set.autocomplete("posisi")
    async def _ubah_staff_set_posisi_auto(self, inter: discord.Interaction, current: str):
        judul = getattr(inter.namespace, "judul", None)
        server = await self.queue.fetch_database(str(inter.guild.id)) if inter.guild else None
        if server is None or not judul:
            return []
        project = server.get_project(judul) or server.exact_match(judul)
        if project is None:
            return []
        choices = [
            app_commands.Choice(name=self._role_name(project, role), value=role) for role, _ in project.assignment
        ]
        return [c for c in choices if current.lower() in c.name.lower()][:25]

    def _role_name(self, project: ShowtimesProject, role: str) -> str:
        return project.assignment.get_custom_name(role) or self.base.normalize_role_name(role, True)

    def _user_name(self, user_id, fallback: str) -> str:
        if not user_id:
            return fallback
        try:
            user = self.bot.get_user(int(user_id))
        except (TypeError, ValueError):
            return fallback
        return str(user) if user is not None else fallback

    async def _save_with_collaborators(
        self, inter: discord.Interaction, srv_data: Showtimes, project: ShowtimesProject
    ):
        update_cache: list[Showtimes] = [srv_data]
        for osrv_data in await self._collaborators(project, srv_data.id):
            if osrv_data.get_project(project) is None:
                continue
            osrv_data.update_project(project, False)
            update_cache.append(osrv_data)
        await self._commit(str(srv_data.id), update_cache)

    # ------------------------------------------------------------------ ubahdata: role
    @ubahdata.command(
        name="rolediscord",
        description=app_commands.locale_str(
            "Ganti role Discord yang dipakai garapan", key="showtimes.ubahdata.rolediscord"
        ),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        role=app_commands.locale_str("Role Discord yang dipakai", key="showtimes.ubahdata.option_role"),
        buat_otomatis=app_commands.locale_str(
            "Buat role baru otomatis (abaikan pilihan role)", key="showtimes.ubahdata.option_buat_otomatis"
        ),
    )
    async def _ubah_role_discord(
        self,
        inter: discord.Interaction,
        judul: str,
        role: discord.Role | None = None,
        buat_otomatis: bool = False,
    ):
        ctx = await self.bot.get_context(inter)
        srv_data, project = await self._admin_project(inter, judul)
        if srv_data is None or project is None:
            return
        if role is None and not buat_otomatis:
            return await inter.response.send_message(ctx.t("ubahdata.role_required"), ephemeral=True)
        await inter.response.defer()
        guild = inter.guild
        if guild is None:
            return await inter.followup.send(ctx.t("errors.guild_only_bang"))
        if buat_otomatis:
            try:
                role = await guild.create_role(name=project.title, colour=discord.Colour.random(), mentionable=True)
            except (discord.Forbidden, discord.HTTPException):
                return await inter.followup.send(ctx.t("ubahdata.role_create_failed"))
        if role is None:
            return await inter.followup.send(ctx.t("ubahdata.role_not_found"))
        project.role = role
        srv_data.update_project(project)
        await inter.followup.send(
            ctx.t("ubahdata.role_updated", title=project.title, mention=role.mention),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self._save_with_collaborators(inter, srv_data, project)

    # ------------------------------------------------------------------ ubahdata: episode
    @ubah_episode.command(
        name="tambah",
        description=app_commands.locale_str("Tambah jumlah episode", key="showtimes.ubahdata.episode_tambah"),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        jumlah=app_commands.locale_str("Jumlah episode yang ditambahkan", key="showtimes.ubahdata.option_jumlah"),
    )
    async def _ubah_episode_tambah(
        self, inter: discord.Interaction, judul: str, jumlah: app_commands.Range[int, 1, 100]
    ):
        ctx = await self.bot.get_context(inter)
        srv_data, project = await self._admin_project(inter, judul)
        if srv_data is None or project is None:
            return
        await inter.response.defer()
        last_episode = project.status[-1]
        anilist_data = await self.base.fetch_anilist(project.id, 1, last_episode.episode)
        if isinstance(anilist_data, str):
            return await inter.followup.send(ctx.t("ubahdata.anilist_error", error=anilist_data))
        time_data = anilist_data["time_data"]

        fsdb_anime = project.fsdb
        fsdb = self.bot.fsdb
        if last_episode.finished and fsdb_anime is not None and fsdb is not None and fsdb_anime.id:
            self.logger.info("Updating FSDB Project to on progress again.")
            await fsdb.update_project(fsdb_anime.id, "status", "Jalan")

        for episode in range(last_episode.episode + 1, last_episode.episode + jumlah + 1):
            airtime_value = time_data[episode - 1] if episode - 1 < len(time_data) else None
            airtime = (
                airtime_value
                if isinstance(airtime_value, (int, float)) and not isinstance(airtime_value, bool)
                else None
            )
            ep_child = ShowtimesEpisodeStatus(
                episode,
                ShowtimesEpisodeStatusChild.factory_from_other(last_episode.progress),
                airtime,
            )
            project.add_episode(ep_child)
        project.update_time()
        srv_data.update_project(project)
        await inter.followup.send(
            ctx.t("ubahdata.episodes_added", amount=jumlah, title=project.title, total=project.total_episodes)
        )
        await self._save_with_collaborators(inter, srv_data, project)

    @ubah_episode.command(
        name="hapus",
        description=app_commands.locale_str(
            "Hapus episode dengan range tertentu", key="showtimes.ubahdata.episode_hapus"
        ),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        rentang=app_commands.locale_str("Satu episode (4) atau rentang (4-6)", key="showtimes.ubahdata.option_rentang"),
    )
    async def _ubah_episode_hapus(self, inter: discord.Interaction, judul: str, rentang: str):
        ctx = await self.bot.get_context(inter)
        srv_data, project = await self._admin_project(inter, judul)
        if srv_data is None or project is None:
            return
        last_episode = project.status[-1].episode
        parts = [p.strip() for p in rentang.split("-")]
        if len(parts) > 2 or not all(p.isdigit() for p in parts):
            return await inter.response.send_message(
                ctx.t("ubahdata.invalid_number") + "\n" + ctx.t("ubahdata.remove_episode_hint"), ephemeral=True
            )
        first = int(parts[0])
        last = int(parts[-1])
        if first < 1 or first > last_episode or last > last_episode:
            return await inter.response.send_message(
                ctx.t("ubahdata.number_exceeds_max", maximum=last_episode), ephemeral=True
            )
        if first > last:
            return await inter.response.send_message(
                ctx.t("ubahdata.start_after_end", first=first, last=last), ephemeral=True
            )

        label = str(first) if first == last else f"{first}-{last}"
        if not await ctx.confirm(ctx.t("ubahdata.episode_delete_confirm", label=label, title=project.title)):
            return await ctx.send(ctx.t("errors.cancelled"))

        for ep in range(first, last + 1):
            project.remove_episode(ep)
        if project.status:
            new_maximum_episode = project.status[-1]
            fsdb_anime = project.fsdb
            fsdb = self.bot.fsdb
            if new_maximum_episode.finished and fsdb_anime is not None and fsdb is not None and fsdb_anime.id:
                self.logger.info("Updating FSDB Project to finished.")
                await fsdb.update_project(fsdb_anime.id, "status", "Tamat")
        project.update_time()
        srv_data.update_project(project)
        await ctx.send(ctx.t("ubahdata.episodes_deleted", label=label, title=project.title))
        await self._save_with_collaborators(inter, srv_data, project)

    # ------------------------------------------------------------------ ubahdata: drop
    @ubahdata.command(
        name="drop",
        description=app_commands.locale_str(
            "Hapus garapan ini dari daftar utang selamanya", key="showtimes.ubahdata.drop"
        ),
    )
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _ubah_drop(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        srv_data, project = await self._admin_project(inter, judul)
        if srv_data is None or project is None:
            return
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only_bang"), ephemeral=True)
        server_id = str(guild.id)
        if not await ctx.confirm(ctx.t("ubahdata.drop_confirm", title=project.title)):
            return await ctx.send(ctx.t("errors.cancelled"))

        self.logger.warning(f"{project.title}: nuking project...")
        other_roles = {p.role for p in srv_data.projects if p.id != project.id and isinstance(p.role, int)}
        fsdb_data = project.fsdb
        fsdb = self.bot.fsdb
        if fsdb_data is not None and fsdb is not None and fsdb_data.id:
            self.logger.warning("Updating FSDB Project to dropped.")
            await fsdb.update_project(fsdb_data.id, "status", "Drop")

        current = project.get_current()
        announce_it = current is not None and current.finished

        role_id = project.role
        # Delete the role, but not if another project is still using it.
        if isinstance(role_id, int) and role_id not in other_roles:
            role_real = guild.get_role(role_id)
            if role_real is not None:
                try:
                    await role_real.delete()
                    self.logger.warning(f"{project.title}:{role_id}: role removed!")
                except (discord.Forbidden, discord.HTTPException):
                    self.logger.error(f"{project.title}:{role_id}: failed to remove role!")

        srv_data -= project
        update_cache: list[Showtimes] = [srv_data]
        for osrv_data in await self._collaborators(project, server_id):
            osrv_anime = osrv_data.get_project(project)
            if osrv_anime is None:
                continue
            if osrv_anime.remove_kolaborator(guild.id) is not None:
                osrv_data.update_project(osrv_anime)
                update_cache.append(osrv_data)

        await ctx.send(ctx.t("ubahdata.dropped", title=project.title))
        await self._commit(server_id, update_cache)

        if announce_it and srv_data.announcer is not None:
            embed = discord.Embed(title=project.title, color=0xB51E1E)
            embed.add_field(
                name=ctx.t("ubahdata.drop_embed_title"),
                value=ctx.t("ubahdata.drop_embed_value", title=project.title),
                inline=False,
            )
            embed.set_footer(text=ctx.t("footer.at", time=get_current_time(ctx.locale)))
            await self.base.announce_embed(self.bot, srv_data.announcer, embed)

    # ------------------------------------------------------------------ custom roles
    @ubah_role.command(
        name="tambah",
        description=app_commands.locale_str(
            "Tambah posisi/role custom (maksimal 5)", key="showtimes.ubahdata.role_tambah"
        ),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        kode=app_commands.locale_str("Kode role, contoh: TS (tanpa spasi)", key="showtimes.ubahdata.option_kode"),
        nama=app_commands.locale_str("Nama lengkap role", key="showtimes.ubahdata.option_nama"),
    )
    async def _ubah_customrole_tambah(
        self,
        inter: discord.Interaction,
        judul: str,
        kode: app_commands.Range[str, 1, 10],
        nama: app_commands.Range[str, 1, 50],
    ):
        ctx = await self.bot.get_context(inter)
        srv_data, project = await self._admin_project(inter, judul)
        if srv_data is None or project is None:
            return
        key = kode.upper()
        if " " in key:
            return await inter.response.send_message(ctx.t("ubahdata.no_spaces"), ephemeral=True)
        if key in BASE_ROLE_KEYS:
            return await inter.response.send_message(ctx.t("ubahdata.reserved_code"), ephemeral=True)
        existing = project.assignment.custom
        if any(r.key == key for r in existing):
            return await inter.response.send_message(ctx.t("ubahdata.code_taken"), ephemeral=True)
        if len(existing) >= MAX_CUSTOM_ROLES:
            return await inter.response.send_message(ctx.t("ubahdata.max_custom_roles"), ephemeral=True)

        new_role = ShowtimesAssigneeCustom(key, nama)
        await self._apply_custom_roles(inter, srv_data, project, [new_role], [])

    @ubah_role.command(
        name="hapus",
        description=app_commands.locale_str("Hapus posisi/role custom", key="showtimes.ubahdata.role_hapus"),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        kode=app_commands.locale_str("Kode role yang dihapus", key="showtimes.ubahdata.option_kode_hapus"),
    )
    async def _ubah_customrole_hapus(self, inter: discord.Interaction, judul: str, kode: str):
        ctx = await self.bot.get_context(inter)
        srv_data, project = await self._admin_project(inter, judul)
        if srv_data is None or project is None:
            return
        key = kode.upper()
        if not any(r.key == key for r in project.assignment.custom):
            return await inter.response.send_message(ctx.t("ubahdata.custom_code_not_found"), ephemeral=True)
        await self._apply_custom_roles(inter, srv_data, project, [], [key])

    @ubah_role.command(
        name="list",
        description=app_commands.locale_str("Lihat posisi/role custom", key="showtimes.ubahdata.role_list"),
    )
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _ubah_customrole_list(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        _, project = await self._admin_project(inter, judul)
        if project is None:
            return
        custom_roles = project.assignment.custom
        value = ctx.t("ubahdata.none")
        if custom_roles:
            value = "- " + "\n- ".join(f"**{x.key}** - {x.name}" for x in custom_roles)
        embed = discord.Embed(title=project.title, color=0x1E1EB5)
        embed.add_field(name=ctx.t("ubahdata.custom_role_embed"), value=value, inline=False)
        await inter.response.send_message(embed=embed, ephemeral=True)

    @_ubah_customrole_hapus.autocomplete("kode")
    async def _ubah_customrole_hapus_kode_auto(self, inter: discord.Interaction, current: str):
        judul = getattr(inter.namespace, "judul", None)
        server = await self.queue.fetch_database(str(inter.guild.id)) if inter.guild else None
        if server is None or not judul:
            return []
        project = server.get_project(judul) or server.exact_match(judul)
        if project is None:
            return []
        choices = [
            app_commands.Choice(name=f"{r.key} — {r.name}"[:100], value=r.key) for r in project.assignment.custom
        ]
        return [c for c in choices if current.lower() in c.name.lower()]

    async def _apply_custom_roles(
        self,
        inter: discord.Interaction,
        srv_data: Showtimes,
        project: ShowtimesProject,
        to_add: list[ShowtimesAssigneeCustom],
        to_delete: list[str],
    ):
        server_id = str(srv_data.id)
        ctx = await self.bot.get_context(inter)
        await inter.response.defer()

        def _apply(target: ShowtimesProject):
            for role in to_add:
                target.assignment.create_custom(role.key, role.name, role.person)
                for status in target.status:
                    status.progress.create_custom(role.key, role.name, False)
            for key in to_delete:
                target.assignment.remove_custom(key)
                for status in target.status:
                    status.progress.remove_custom(key)

        _apply(project)
        srv_data.update_project(project)
        save_queue: list[Showtimes] = [srv_data]
        for osrv in await self._collaborators(project, server_id):
            osrv_project = osrv.get_project(project)
            if osrv_project is None:
                continue
            _apply(osrv_project)
            osrv.update_project(osrv_project)
            save_queue.append(osrv)

        await inter.followup.send(ctx.t("ubahdata.saved"))
        await self._commit(server_id, save_queue)

    # ------------------------------------------------------------------ autocomplete wiring
    for _cmd in (
        _ubah_staff_set,
        _ubah_staff_list,
        _ubah_role_discord,
        _ubah_episode_tambah,
        _ubah_episode_hapus,
        _ubah_drop,
        _ubah_customrole_tambah,
        _ubah_customrole_hapus,
        _ubah_customrole_list,
    ):
        _cmd.autocomplete("judul")(_project_auto)
    del _cmd


async def setup(bot: naoTimesBot):
    ntdb = bot.ntdb
    if ntdb is None or bot.showqueue is None or bot.showcogs is None:
        bot.logger.warning("Showtimes services are unavailable; not loading this admin cog")
        return
    await bot.add_cog(ShowtimesAdmin(bot))
