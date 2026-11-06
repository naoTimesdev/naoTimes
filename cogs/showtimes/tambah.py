import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.showtimes import (
    ShowtimesEpisodeStatus,
    ShowtimesEpisodeStatusChild,
    ShowtimesFSDB,
    ShowtimesPoster,
    ShowtimesProject,
)
from naotimes.showtimes.cogbase import AnilistFailure
from naotimes.showtimes.slash import NOT_REGISTERED
from naotimes.utils import get_current_time

STAFF_KEYS = ("tl", "tlc", "enc", "ed", "tm", "ts", "qc")


class ShowtimesAdminTambah(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.TambahUtang")

    @app_commands.command(
        name="tambahutang",
        description=app_commands.locale_str(
            "Tambah garapan baru ke daftar utang (admin)", key="showtimes.tambahutang.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        anilist_id=app_commands.locale_str(
            "ID Anilist anime (lihat dengan /anime anime)", key="showtimes.tambahutang.option_anilist_id"
        ),
        jumlah_episode=app_commands.locale_str(
            "Perkiraan jumlah episode (hanya jika Anilist belum punya jadwal)",
            key="showtimes.tambahutang.option_jumlah_episode",
        ),
        role=app_commands.locale_str("Role Discord untuk garapan ini", key="showtimes.tambahutang.option_role"),
        buat_role_otomatis=app_commands.locale_str(
            "Buat role baru otomatis (abaikan pilihan role)",
            key="showtimes.tambahutang.option_buat_role_otomatis",
        ),
        tl=app_commands.locale_str("Translator", key="showtimes.tambahutang.option_tl"),
        tlc=app_commands.locale_str("Translation checker", key="showtimes.tambahutang.option_tlc"),
        enc=app_commands.locale_str("Encoder", key="showtimes.tambahutang.option_enc"),
        ed=app_commands.locale_str("Editor", key="showtimes.tambahutang.option_ed"),
        tm=app_commands.locale_str("Timer", key="showtimes.tambahutang.option_tm"),
        ts=app_commands.locale_str("Typesetter", key="showtimes.tambahutang.option_ts"),
        qc=app_commands.locale_str("Quality checker", key="showtimes.tambahutang.option_qc"),
    )
    async def _showadmin_tambahutang(
        self,
        inter: discord.Interaction,
        anilist_id: app_commands.Range[int, 1],
        jumlah_episode: app_commands.Range[int, 1, 1000] | None = None,
        role: discord.Role | None = None,
        buat_role_otomatis: bool = False,
        tl: discord.Member | None = None,
        tlc: discord.Member | None = None,
        enc: discord.Member | None = None,
        ed: discord.Member | None = None,
        tm: discord.Member | None = None,
        ts: discord.Member | None = None,
        qc: discord.Member | None = None,
    ):
        ctx = await self.bot.get_context(inter)
        guild = inter.guild
        if guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only_bang"), ephemeral=True)
        queue = self.bot.showqueue
        base = self.bot.showcogs
        ntdb = self.bot.ntdb
        if queue is None or base is None or ntdb is None:
            return await inter.response.send_message(ctx.t("tambahutang.not_initialized"), ephemeral=True)
        self.logger.info(f"Requested /tambahutang at {guild.id}")

        server_data = await queue.fetch_database(str(guild.id))
        if server_data is None:
            return await inter.response.send_message(NOT_REGISTERED, ephemeral=True)
        if not server_data.is_admin(inter.user):
            return await inter.response.send_message(ctx.t("tambahutang.admin_only"), ephemeral=True)
        if server_data.get_project(str(anilist_id)):
            return await inter.response.send_message(ctx.t("tambahutang.project_exists"), ephemeral=True)

        await inter.response.defer()

        anime_info = await base.anilist_get_information(anilist_id)
        if isinstance(anime_info, AnilistFailure):
            return await inter.followup.send(anime_info.error or ctx.t("tambahutang.anilist_info_failed"))

        project_data = ShowtimesProject.factory()
        project_data.id = str(anime_info.id)
        project_data.title = anime_info.title
        project_data.mal_id = anime_info.mal_id
        project_data.start_time = anime_info.start_time
        project_data.poster = ShowtimesPoster(anime_info.cover_image, anime_info.cover_color)
        parsed: list[ShowtimesEpisodeStatus] = [
            ShowtimesEpisodeStatus(
                s.episode,
                ShowtimesEpisodeStatusChild.factory(),
                s.airing_at,
            )
            for s in anime_info.schedules
        ]
        if not parsed:
            if jumlah_episode is None:
                return await inter.followup.send(ctx.t("tambahutang.no_schedule"))
            schedules = await base.anilist_get_schedules(project_data.id, jumlah_episode)
            if not isinstance(schedules, list):
                return await inter.followup.send(schedules.error or ctx.t("tambahutang.schedule_failed"))
            parsed = [
                ShowtimesEpisodeStatus(
                    s.episode,
                    ShowtimesEpisodeStatusChild.factory(),
                    s.airing_at,
                )
                for s in schedules
            ]
        project_data.status = parsed

        if buat_role_otomatis:
            try:
                role = await guild.create_role(name=project_data.title, colour=discord.Colour.random())
            except discord.Forbidden:
                return await inter.followup.send(ctx.t("tambahutang.role_forbidden"))
            except discord.HTTPException:
                return await inter.followup.send(ctx.t("tambahutang.discord_error"))
        if buat_role_otomatis and role is None:
            return await inter.followup.send(ctx.t("tambahutang.role_missing"))
        if role is not None:
            project_data.role = role

        staffers = dict(zip(STAFF_KEYS, (tl, tlc, enc, ed, tm, ts, qc)))
        for key, member in staffers.items():
            if member is not None:
                project_data.update_assignment(key, member)

        embed = discord.Embed(
            title=ctx.t("tambahutang.embed_title"),
            description=ctx.t("tambahutang.embed_description"),
            color=0xE7E363,
        )
        embed.set_thumbnail(url=project_data.poster.url)
        embed.add_field(
            name=ctx.t("tambahutang.field_judul"),
            value=ctx.t("tambahutang.field_judul_value", title=project_data.title, id=project_data.id),
            inline=False,
        )
        embed.add_field(
            name=ctx.t("tambahutang.field_episode"),
            value=ctx.t("tambahutang.field_episode_value", count=project_data.total_episodes),
            inline=False,
        )
        embed.add_field(
            name=ctx.t("tambahutang.field_role"),
            value=role.mention if role else ctx.t("tambahutang.role_none"),
            inline=False,
        )
        for key, member in staffers.items():
            embed.add_field(
                name=base.normalize_role_name(key, True),
                value=member.mention if member else ctx.t("tambahutang.role_empty"),
                inline=True,
            )
        embed.set_footer(text=ctx.t("footer.credit"), icon_url="https://p.n4o.xyz/i/nao250px.png")

        if not await ctx.confirm(ctx.t("tambahutang.confirm"), embed=embed):
            if buat_role_otomatis and role is not None:
                try:
                    await role.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass
            return await ctx.send(ctx.t("tambahutang.cancelled"))

        members: list[tuple[str, discord.Member]] = [(k, m) for k, m in staffers.items() if m is not None]

        role_given_success = True
        if role is not None:
            for _, member in members:
                if member.get_role(role.id) is None:
                    try:
                        await member.add_roles(role)
                    except (discord.Forbidden, discord.HTTPException):
                        role_given_success = False
                        self.logger.error(f"Gagal menambah role ke user {member}")

        mal_id = project_data.mal_id
        fsdb = self.bot.fsdb
        if server_data.fsdb_id is not None and fsdb is not None and mal_id is not None:
            self.logger.info(f"{guild.id}: updating FansubDB data...")
            fansubs_projects, _ = await fsdb.fetch_fansub_projects(server_data.fsdb_id)
            existing_projects = {
                str(data.anime.mal_id): data.id
                for data in fansubs_projects
                if data.anime is not None and data.anime.mal_id is not None
            }
            fsani_data = await fsdb.fetch_anime_by_mal(mal_id)
            if fsani_data is None:
                imported, imported_id = await fsdb.import_mal(int(mal_id))
                if not imported or not isinstance(imported_id, int):
                    return await ctx.send(ctx.t("tambahutang.fsdb_import_failed"))
                fsani_id = imported_id
                _, fsproject_id = await fsdb.add_new_project(fsani_id, server_data.fsdb_id)
                if not isinstance(fsproject_id, int):
                    try:
                        fsproject_id = int(fsproject_id)
                    except ValueError:
                        return await ctx.send(ctx.t("fsdb.invalid_project_id"))
                project_data.fsdb = ShowtimesFSDB(fsproject_id, fsani_id)
            else:
                fsani_id = fsani_data.id
                if str(mal_id) in existing_projects:
                    project_data.fsdb = ShowtimesFSDB(int(existing_projects[str(mal_id)]), fsani_id)
                else:
                    _, fsproject_id = await fsdb.add_new_project(fsani_id, server_data.fsdb_id)
                    if not isinstance(fsproject_id, int):
                        try:
                            fsproject_id = int(fsproject_id)
                        except ValueError:
                            return await ctx.send(ctx.t("fsdb.invalid_project_id"))
                    project_data.fsdb = ShowtimesFSDB(fsproject_id, fsani_id)

        self.logger.info(f"{guild.id}: committing data to database...")
        server_data += project_data
        await queue.add_job(server_data)
        success, msg = await ntdb.update_server(server_data)
        if not success:
            self.logger.error(f"{guild.id}: failed to update, reason: {msg}")
            if str(guild.id) not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(guild.id))

        self.logger.info(f"{guild.id}: done processing at {get_current_time()}!")
        await ctx.send(ctx.t("tambahutang.success", title=project_data.title))
        if role_given_success and role is not None and members:
            await ctx.send(ctx.t("tambahutang.role_added"))


async def setup(bot: naoTimesBot):
    ntdb = bot.ntdb
    if ntdb is None or bot.showqueue is None or bot.showcogs is None:
        bot.logger.warning("Showtimes services are unavailable; not loading this cog")
        return
    await bot.add_cog(ShowtimesAdminTambah(bot))
