import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.paginator import DiscordPaginatorUI
from naotimes.showtimes import Showtimes
from naotimes.showtimes.models import ShowtimesFSDB
from naotimes.showtimes.slash import load_server, project_autocomplete, resolve_project
from naotimes.utils import split_search_id

FOOTER_ICON = "https://p.n4o.xyz/i/nao250px.png"


class ShowtimesFansubDB(commands.Cog):
    fsdb_group = app_commands.Group(
        name="fsdb",
        description=app_commands.locale_str("Integrasi Showtimes dengan FansubDB", key="showtimes.fsdb.description"),
        guild_only=True,
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.FansubDB")

        queue = bot.showqueue
        base = bot.showcogs
        ntdb = bot.ntdb
        if queue is None or base is None or ntdb is None:
            raise RuntimeError("Showtimes services must be initialized before loading this cog")
        self.queue = queue
        self.base = base
        self.ntdb = ntdb
        self.fsdb = bot.fsdb

    @property
    def fsdb_client(self):
        if self.fsdb is None:
            raise RuntimeError("FansubDB is not initialized")
        return self.fsdb

    async def _project_auto(self, inter: discord.Interaction, current: str):
        return await project_autocomplete(self.bot, inter, current)

    async def _fsdb_ready(self, inter: discord.Interaction) -> bool:
        if self.fsdb is None:
            ctx = await self.bot.get_context(inter)
            await inter.response.send_message(ctx.t("fsdb.not_initialized"), ephemeral=True)
            return False
        return True

    @staticmethod
    def _embed(ctx: naoTimesContext, color: int = 0x56ACF3) -> discord.Embed:
        embed = discord.Embed(title=ctx.t("fsdb.embed_title"), color=color)
        embed.set_footer(text=ctx.t("footer.credit"), icon_url=FOOTER_ICON)
        return embed

    # ------------------------------------------------------------------ integrasi
    @fsdb_group.command(
        name="integrasi",
        description=app_commands.locale_str(
            "Integrasikan Showtimes server ini dengan FansubDB (admin)", key="showtimes.fsdb.integrasi"
        ),
    )
    @app_commands.describe(
        fansub_id=app_commands.locale_str(
            "ID Fansub di FansubDB (cari dengan /fsdb fansub)", key="showtimes.fsdb.option_fansub_id"
        )
    )
    async def _showfsdb_integrasi(self, inter: discord.Interaction, fansub_id: app_commands.Range[int, 1]):
        if not await self._fsdb_ready(inter):
            return
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        if inter.guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only"), ephemeral=True)
        server_id = inter.guild.id
        if not srv_data.is_admin(inter.user):
            return await inter.response.send_message(ctx.t("fsdb.admin_integrate"), ephemeral=True)
        if srv_data.fsdb_id is not None:
            return await inter.response.send_message(ctx.t("fsdb.already_integrated"), ephemeral=True)

        await inter.response.defer()
        fsdb_id = fansub_id

        fsdb = self.fsdb_client
        all_fansubs = await fsdb.fetch_fansubs()
        fsd_data = split_search_id(all_fansubs, "id", fsdb_id)
        if not fsd_data:
            return await ctx.send(ctx.t("fsdb.fansub_not_found"))

        embed = self._embed(ctx, 0xE7E363)
        embed.description = ctx.t("fsdb.check_integration")
        embed.add_field(name=ctx.t("fsdb.field_fansub"), value=f"{fsd_data['name']} ({fsdb_id})", inline=False)
        if not await ctx.confirm(ctx.t("fsdb.confirm_integration"), embed=embed):
            return await ctx.send(ctx.t("errors.cancelled"))

        progress = await ctx.send(
            embed=self._embed(ctx).add_field(
                name=ctx.t("fsdb.processing_title"),
                value=ctx.t("fsdb.processing_connection"),
                inline=True,
            )
        )

        update_queue: list[Showtimes] = []
        collect_all_animes = await fsdb.fetch_animes()
        if collect_all_animes:
            collect_all_animes.sort(key=lambda x: x["mal_id"])
            for project in srv_data.projects:
                mal_id = project.mal_id
                if mal_id is None:
                    continue
                fsani_data = split_search_id(collect_all_animes, "mal_id", mal_id)
                if fsani_data is None:
                    res, import_id = await fsdb.import_mal(int(mal_id))
                    if not res or not isinstance(import_id, int):
                        self.logger.warning("Failed to import an anime into FansubDB")
                        continue
                    fsani_id = import_id
                else:
                    fsani_id = fsani_data["id"]
                project.fsdb = ShowtimesFSDB(None, fsani_id)
                srv_data.update_project(project, False)

            fansubs_projects, _ = await fsdb.fetch_fansub_projects(fsdb_id)
            existing_projects = {str(data["anime"]["id"]): data["id"] for data in fansubs_projects}
            for project in srv_data.projects:
                kolaborasi_data = [k for k in project.kolaborasi if str(k) != str(server_id)]
                if project.fsdb is None:
                    continue
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
                    proj_add_success, project_id = await fsdb.add_new_project(fsani_id, fsdb_id, status_type)
                    if proj_add_success:
                        self.logger.info(f"fsdb_ani{fsani_id}: appending proj{project_id} to database...")
                        try:
                            project.fsdb.id = int(project_id)
                        except (TypeError, ValueError):
                            self.logger.warning(f"FansubDB returned an invalid project ID: {project_id!r}")
                srv_data.update_project(project, False)
                for osrv in kolaborasi_data:
                    osrv_data = await self.queue.fetch_database(str(osrv))
                    if osrv_data is None:
                        continue
                    osrv_anime = osrv_data.get_project(project)
                    if osrv_anime is None:
                        continue
                    osrv_anime.fsdb = project.fsdb
                    osrv_data.update_project(osrv_anime, False)
                    update_queue.append(osrv_data)

        srv_data.fsdb_id = int(fsdb_id)
        update_queue.append(srv_data)

        for data in update_queue:
            await self.queue.add_job(data)

        await progress.delete()
        await ctx.send(
            embed=self._embed(ctx, 0x96DF6A).add_field(name=ctx.t("fsdb.success_title"), value=ctx.t("fsdb.integrated"))
        )
        for data in update_queue:
            res, msg = await self.ntdb.update_server(data)
            if not res:
                self.logger.error(f"{data.id}: failed to update main database: {msg}")
                if data.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(str(data.id))
        self.logger.info(f"{server_id}: integration completed!")

    # ------------------------------------------------------------------ bind
    @fsdb_group.command(
        name="bind",
        description=app_commands.locale_str(
            "Hubungkan sebuah garapan dengan FansubDB (admin)", key="showtimes.fsdb.bind"
        ),
    )
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _showfsdb_bind(self, inter: discord.Interaction, judul: str):
        if not await self._fsdb_ready(inter):
            return
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        if inter.guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only"), ephemeral=True)
        server_id = inter.guild.id
        if not srv_data.is_admin(inter.user):
            return await inter.response.send_message(ctx.t("fsdb.admin_bind"), ephemeral=True)
        if srv_data.fsdb_id is None:
            return await inter.response.send_message(ctx.t("fsdb.not_integrated"), ephemeral=True)
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)

        await inter.response.defer()
        if not await ctx.confirm(ctx.t("fsdb.bind_confirm", title=project.title)):
            return await ctx.send(ctx.t("errors.cancelled"))

        msg = await ctx.send(ctx.t("fsdb.checking_old"))
        fsdb = self.fsdb_client
        fansubs_projects, _ = await fsdb.fetch_fansub_projects(srv_data.fsdb_id)
        existing_projects = {str(data["anime"]["mal_id"]): data["id"] for data in fansubs_projects}
        fansubs_projects.sort(key=lambda x: x["id"])
        if str(project.mal_id) in existing_projects:
            fansub_data = split_search_id(fansubs_projects, "id", existing_projects[str(project.mal_id)])
            if fansub_data is not None:
                self.logger.info(f"{server_id}-{project.id}: found old fansub data at FansubDB")
                if not await ctx.confirm(ctx.t("fsdb.overwrite_confirm")):
                    return await ctx.send(ctx.t("errors.cancelled"))
                await msg.edit(content=ctx.t("fsdb.removing_old"))
                if len(fansub_data["fansub"]) == 1:
                    res, _ = await fsdb.delete_project(fansub_data["id"])
                    if not res:
                        return await ctx.send(ctx.t("fsdb.delete_old_failed"))
                else:
                    all_fs_id = [x["id"] for x in fansub_data["fansub"]]
                    try:
                        all_fs_id.remove(fansub_data["id"])
                    except ValueError:
                        return await ctx.send(ctx.t("fsdb.delete_old_failed"))
                    res, _ = await fsdb.update_project(fansub_data["id"], "fansub", all_fs_id, task_mode=False)
                    if not res:
                        return await ctx.send(ctx.t("fsdb.delete_old_failed"))

        await msg.edit(content=ctx.t("fsdb.adding_new"))
        mal_id = project.mal_id
        if mal_id is None:
            return await ctx.send(ctx.t("fsdb.no_mal_id"))
        anime_lists = await fsdb.fetch_animes()
        anifs_id = await fsdb.find_id_from_mal(mal_id, anime_lists)
        if anifs_id == 0:
            self.logger.warning(f"{server_id}-{project.id}: anime not found, importing...")
            imported, imported_id = await fsdb.import_mal(mal_id)
            if not imported or not isinstance(imported_id, int):
                return await ctx.send(ctx.t("fsdb.import_failed"))
            anifs_id = imported_id

        status_type = "Tentatif"
        if project.get_current() is None:
            status_type = "Tamat"
        elif project.status[0].finished:
            status_type = "Jalan"
            if len(project.status) == 1:
                status_type = "Tamat"

        res, project_id = await fsdb.add_new_project(anifs_id, srv_data.fsdb_id, status_type)
        if not res:
            self.logger.warning(f"{server_id}: failed to add project to database")
            return await ctx.send(ctx.t("fsdb.add_project_failed"))
        if not isinstance(project_id, int):
            try:
                project_id = int(project_id)
            except ValueError:
                return await ctx.send(ctx.t("fsdb.invalid_project_id"))
        project.fsdb = ShowtimesFSDB(project_id, anifs_id)
        srv_data.update_project(project, False)
        await self.queue.add_job(srv_data)

        success, err = await self.ntdb.update_server(srv_data)
        if not success:
            self.logger.warning(f"{server_id}: failed to update main database: {err}")
            if str(server_id) not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(server_id))

        await ctx.send(ctx.t("fsdb.bound", title=project.title))

    # ------------------------------------------------------------------ fansub
    @fsdb_group.command(
        name="fansub",
        description=app_commands.locale_str("Cari informasi fansub di FansubDB", key="showtimes.fsdb.fansub"),
    )
    @app_commands.describe(pencarian=app_commands.locale_str("Nama fansub", key="showtimes.fsdb.option_pencarian"))
    async def _showfsdb_fansub(self, inter: discord.Interaction, pencarian: str):
        if not await self._fsdb_ready(inter):
            return
        await inter.response.defer()
        ctx = await self.bot.get_context(inter)
        results = await self.fsdb_client.fetch_fansubs(pencarian)
        if not results:
            return await ctx.send(ctx.t("fsdb.no_fansub_match"))

        def _create_fsdb_embed(data: dict):
            embed = discord.Embed(color=0x19212D)
            embed.set_footer(text=ctx.t("fsdb.fansubdb_credit"))
            embed.title = data["name"]
            desc = ctx.t("fsdb.fansub_id", id=data["id"])
            if data["description"]:
                desc += f"\n{data['description']}"
            embed.description = desc

            url_link_info = []
            if data["website"]:
                url_link_info.append(ctx.t("fsdb.link_website", url=data["website"]))
            if data["facebook"]:
                url_link_info.append(ctx.t("fsdb.link_facebook", url=data["facebook"]))
            if data["discord"]:
                url_link_info.append(ctx.t("fsdb.link_discord", url=data["discord"]))
            if url_link_info:
                embed.add_field(name=ctx.t("fsdb.field_url"), value="\n".join(url_link_info))
            return embed

        ui_paginate = DiscordPaginatorUI(ctx, results, 30.0)
        ui_paginate.attach(_create_fsdb_embed)
        await ui_paginate.interact()

    _showfsdb_bind.autocomplete("judul")(_project_auto)


async def setup(bot: naoTimesBot):
    if bot.ntdb is None or bot.showqueue is None or bot.showcogs is None:
        bot.logger.warning("Showtimes services are unavailable; not loading the FansubDB cog")
        return
    await bot.add_cog(ShowtimesFansubDB(bot))
