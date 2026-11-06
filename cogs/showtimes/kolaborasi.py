import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.showtimes import Showtimes, ShowtimesKonfirmasi
from naotimes.showtimes.slash import load_server, project_autocomplete, resolve_project
from naotimes.utils import generate_custom_code

FOOTER_ICON = "https://p.n4o.xyz/i/nao250px.png"


class ShowtimesKolaborasi(commands.Cog):
    kolaborasi = app_commands.Group(
        name="kolaborasi",
        description=app_commands.locale_str(
            "Kolaborasi garapan dengan fansub lain", key="showtimes.kolaborasi.description"
        ),
        guild_only=True,
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.Kolaborasi")
        ntdb = bot.ntdb
        queue = bot.showqueue
        if ntdb is None or queue is None:
            raise RuntimeError("Showtimes services must be initialized before loading this cog")
        self.ntdb = ntdb
        self.queue = queue

    # ------------------------------------------------------------------ helpers
    async def _project_auto(self, inter: discord.Interaction, current: str):
        return await project_autocomplete(self.bot, inter, current)

    async def _server_auto(self, inter: discord.Interaction, current: str):
        """Servers the bot shares with the user (excluding the current one)."""
        current = current.lower()
        choices: list[app_commands.Choice[str]] = []
        for guild in self.bot.guilds:
            if inter.guild is not None and guild.id == inter.guild.id:
                continue
            if guild.get_member(inter.user.id) is None:
                continue
            if current and current not in guild.name.lower() and current not in str(guild.id):
                continue
            choices.append(app_commands.Choice(name=f"{guild.name}"[:100], value=str(guild.id)))
            if len(choices) >= 25:
                break
        return choices

    async def _commit(self, servers: list[Showtimes]):
        for server in servers:
            await self.queue.add_job(server)
        for server in servers:
            success, msg = await self.ntdb.update_server(server)
            if not success:
                self.logger.warning(f"{server.id}: failed to update, reason: {msg}")
                if server.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(str(server.id))

    @staticmethod
    def _embed(ctx: naoTimesContext, title: str, color: int) -> discord.Embed:
        embed = discord.Embed(title=title, color=color)
        embed.set_footer(text=ctx.t("footer.credit"), icon_url=FOOTER_ICON)
        return embed

    async def _require_admin(self, inter: discord.Interaction, key: str) -> Showtimes | None:
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return None
        if not srv_data.is_admin(inter.user.id):
            await inter.response.send_message(ctx.t(key), ephemeral=True)
            return None
        return srv_data

    # ------------------------------------------------------------------ dengan
    @kolaborasi.command(
        name="dengan",
        description=app_commands.locale_str(
            "Ajak fansub lain berkolaborasi pada sebuah garapan", key="showtimes.kolaborasi.dengan"
        ),
    )
    @app_commands.describe(
        server=app_commands.locale_str(
            "Peladen fansub yang diajak (pilih dari daftar atau ketik ID)",
            key="showtimes.kolaborasi.option_server",
        ),
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
    )
    async def _showkoleb_dengan(self, inter: discord.Interaction, server: str, judul: str):
        ctx = await self.bot.get_context(inter)
        srv_data = await self._require_admin(inter, "kolaborasi.admin_start")
        if srv_data is None:
            return
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only_bang"), ephemeral=True)
        server_id = guild.id

        target_guild = self.bot.get_guild(int(server)) if server.isdigit() else None
        if target_guild is None:
            return await inter.response.send_message(ctx.t("kolaborasi.server_not_found"), ephemeral=True)
        if target_guild.id == server_id:
            return await inter.response.send_message(ctx.t("kolaborasi.same_server"), ephemeral=True)
        target_data = await self.queue.fetch_database(str(target_guild.id))
        if target_data is None:
            return await inter.response.send_message(
                ctx.t("kolaborasi.server_not_in_db", server=target_guild), ephemeral=True
            )

        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)
        if target_guild.id in project.kolaborasi or str(target_guild.id) in [str(k) for k in project.kolaborasi]:
            return await inter.response.send_message(ctx.t("kolaborasi.already_collab"), ephemeral=True)

        embed = self._embed(ctx, ctx.t("kolaborasi.embed_title"), 0xE7E363)
        embed.description = ctx.t("kolaborasi.check_invite")
        embed.add_field(name=ctx.t("kolaborasi.field_anime"), value=project.title, inline=False)
        embed.add_field(name=ctx.t("kolaborasi.field_server"), value=target_guild.name, inline=False)

        await inter.response.defer()
        ctx = await self.bot.get_context(inter)
        if not await ctx.confirm(ctx.t("kolaborasi.confirm_invite"), embed=embed):
            return await ctx.send(ctx.t("errors.cancelled"))

        random_confirm = generate_custom_code(16)
        target_data.add_konfirm(ShowtimesKonfirmasi(random_confirm, server_id, project.id))
        self.logger.info(f"{server_id}-{project.id}: storing data...")
        await self.queue.add_job(target_data)

        embed = self._embed(ctx, ctx.t("kolaborasi.embed_title"), 0x96DF6A)
        embed.add_field(
            name=ctx.t("kolaborasi.success_title"),
            value=ctx.t("kolaborasi.invite_success_value", code=random_confirm),
            inline=True,
        )
        await ctx.send(embed=embed)
        await ctx.send(ctx.t("kolaborasi.invite_message", code=random_confirm))
        await self._commit([target_data])

    # ------------------------------------------------------------------ konfirmasi
    @kolaborasi.command(
        name="konfirmasi",
        description=app_commands.locale_str(
            "Konfirmasi ajakan kolaborasi dari fansub lain", key="showtimes.kolaborasi.konfirmasi"
        ),
    )
    @app_commands.describe(
        kode=app_commands.locale_str(
            "Kode konfirmasi dari fansub yang mengajak", key="showtimes.kolaborasi.option_kode"
        )
    )
    async def _showkoleb_konfirmasi(self, inter: discord.Interaction, kode: str):
        ctx = await self.bot.get_context(inter)
        srv_data = await self._require_admin(inter, "kolaborasi.admin_confirm")
        if srv_data is None:
            return
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only_bang"), ephemeral=True)
        server_id = guild.id
        if len(srv_data.konfirmasi) < 1:
            return await inter.response.send_message(ctx.t("kolaborasi.nothing_to_confirm"), ephemeral=True)
        get_confirm = srv_data.get_konfirm(kode)
        if get_confirm is None:
            return await inter.response.send_message(ctx.t("kolaborasi.code_not_found"), ephemeral=True)

        server_ident = self.bot.get_guild(int(get_confirm.server))
        source_name = server_ident.name if server_ident is not None else get_confirm.server
        source_srv = await self.queue.fetch_database(str(get_confirm.server))
        if source_srv is None:
            return await inter.response.send_message(ctx.t("kolaborasi.source_missing"), ephemeral=True)
        project_info = source_srv.get_project(get_confirm.anime)
        if project_info is None:
            return await inter.response.send_message(ctx.t("kolaborasi.anime_missing"), ephemeral=True)

        embed = self._embed(ctx, ctx.t("kolaborasi.confirm_embed_title"), 0xE7E363)
        embed.add_field(name=ctx.t("kolaborasi.field_anime"), value=project_info.title, inline=False)
        embed.add_field(name=ctx.t("kolaborasi.field_server"), value=str(source_name), inline=False)

        await inter.response.defer()
        ctx = await self.bot.get_context(inter)
        if not await ctx.confirm(ctx.t("kolaborasi.confirm_accept"), embed=embed):
            srv_data.remove_konfirm(get_confirm)
            await self.queue.add_job(srv_data)
            await ctx.send(ctx.t("kolaborasi.invite_rejected"))
            return await self._commit([srv_data])

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
            try:
                c_role = await guild.create_role(
                    name=project_info.title, colour=discord.Colour.random(), mentionable=True
                )
            except (discord.Forbidden, discord.HTTPException):
                return await ctx.send(ctx.t("kolaborasi.role_create_failed"))
            old_role = c_role.id

        clone_data = project_info.copy()
        clone_data.role = old_role
        if old_fsdb_info is not None:
            clone_data.fsdb = old_fsdb_info

        joint_koleb = [get_confirm.server, server_id]
        joint_koleb.extend(other_collab_data)
        joint_koleb.extend(project_info.kolaborasi)
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
            joint_srv = await self.queue.fetch_database(str(joint))
            if joint_srv is None:
                continue
            joint_project = joint_srv.get_project(project_info)
            if joint_project is None:
                continue
            joint_project.kolaborasi = joint_koleb
            joint_srv.update_project(joint_project)
            update_queue.append(joint_srv)

        for srv in update_queue:
            await self.queue.add_job(srv)

        embed = self._embed(ctx, ctx.t("kolaborasi.embed_title"), 0x96DF6A)
        embed.add_field(
            name=ctx.t("kolaborasi.success_title"),
            value=ctx.t("kolaborasi.confirm_success_value", server=source_name),
            inline=True,
        )
        await ctx.send(embed=embed)
        await self._commit(update_queue)
        await ctx.send(
            ctx.t("kolaborasi.confirm_success_message", server=source_name, role=old_role),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ------------------------------------------------------------------ batalkan
    @kolaborasi.command(
        name="batalkan",
        description=app_commands.locale_str(
            "Batalkan ajakan kolaborasi yang sudah dikirim", key="showtimes.kolaborasi.batalkan"
        ),
    )
    @app_commands.describe(
        server=app_commands.locale_str("Peladen yang diajak", key="showtimes.kolaborasi.option_server_batal"),
        kode=app_commands.locale_str("Kode konfirmasi yang dibatalkan", key="showtimes.kolaborasi.option_kode_batal"),
    )
    async def _showkoleb_batalkan(self, inter: discord.Interaction, server: str, kode: str):
        ctx = await self.bot.get_context(inter)
        srv_data = await self._require_admin(inter, "kolaborasi.admin_cancel")
        if srv_data is None:
            return
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only_bang"), ephemeral=True)
        server_id = guild.id
        if not server.isdigit():
            return await inter.response.send_message(ctx.t("kolaborasi.server_invalid"), ephemeral=True)
        target_srv = await self.queue.fetch_database(server)
        if target_srv is None:
            return await inter.response.send_message(ctx.t("kolaborasi.target_server_missing"), ephemeral=True)
        get_confirm = target_srv.get_konfirm(kode)
        if get_confirm is None:
            return await inter.response.send_message(ctx.t("kolaborasi.code_not_found"), ephemeral=True)
        if str(get_confirm.server) != str(server_id):
            return await inter.response.send_message(ctx.t("kolaborasi.not_authorized"), ephemeral=True)

        target_srv.remove_konfirm(kode)
        await self.queue.add_job(target_srv)
        embed = self._embed(ctx, ctx.t("kolaborasi.embed_title"), 0x96DF6A)
        embed.add_field(
            name=ctx.t("kolaborasi.success_title"),
            value=ctx.t("kolaborasi.cancel_success_value", code=kode),
        )
        await inter.response.send_message(embed=embed)
        await self._commit([target_srv])

    # ------------------------------------------------------------------ putus
    @kolaborasi.command(
        name="putus",
        description=app_commands.locale_str("Putuskan kolaborasi sebuah garapan", key="showtimes.kolaborasi.putus"),
    )
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _showkoleb_putus(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        srv_data = await self._require_admin(inter, "kolaborasi.admin_disconnect")
        if srv_data is None:
            return
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only_bang"), ephemeral=True)
        server_id = guild.id
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)
        if len(project.kolaborasi) < 1:
            return await inter.response.send_message(ctx.t("kolaborasi.no_active_collab"), ephemeral=True)

        await inter.response.defer()
        ctx = await self.bot.get_context(inter)
        if not await ctx.confirm(ctx.t("kolaborasi.disconnect_confirm", title=project.title)):
            return await ctx.send(ctx.t("errors.cancelled_plain"))

        update_queue: list[Showtimes] = []
        for osrv in project.kolaborasi:
            if str(osrv) == str(server_id):
                continue
            osrv_data = await self.queue.fetch_database(str(osrv))
            if osrv_data is None:
                continue
            osrv_anime = osrv_data.get_project(project)
            if osrv_anime is None:
                continue
            osrv_anime.remove_kolaborator(server_id)
            if len(osrv_anime.kolaborasi) < 2:
                first_person = osrv_anime.kolaborasi[0] if osrv_anime.kolaborasi else None
                if first_person is None or str(first_person) == str(osrv):
                    osrv_anime.kolaborasi = []
            osrv_data.update_project(osrv_anime)
            update_queue.append(osrv_data)

        is_fsdb_binded = project.fsdb is not None
        project.fsdb = None
        project.kolaborasi = []
        srv_data.update_project(project)
        update_queue.append(srv_data)

        for server in update_queue:
            await self.queue.add_job(server)

        embed = self._embed(ctx, ctx.t("kolaborasi.embed_title"), 0x96DF6A)
        embed.add_field(
            name=ctx.t("kolaborasi.success_title"),
            value=ctx.t("kolaborasi.disconnect_success_value", title=project.title),
            inline=True,
        )
        await ctx.send(embed=embed)
        await self._commit(update_queue)
        await ctx.send(ctx.t("kolaborasi.disconnect_success_message", title=project.title))
        if is_fsdb_binded:
            await ctx.send(ctx.t("kolaborasi.fsdb_unbound", title=project.title))

    _showkoleb_dengan.autocomplete("server")(_server_auto)
    _showkoleb_batalkan.autocomplete("server")(_server_auto)
    _showkoleb_dengan.autocomplete("judul")(_project_auto)
    _showkoleb_putus.autocomplete("judul")(_project_auto)


async def setup(bot: naoTimesBot):
    if bot.ntdb is None or bot.showqueue is None:
        bot.logger.warning("Showtimes services are unavailable; not loading the collaboration cog")
        return
    await bot.add_cog(ShowtimesKolaborasi(bot))
