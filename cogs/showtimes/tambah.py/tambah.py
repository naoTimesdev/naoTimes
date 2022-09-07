import logging
from functools import partial
from typing import Any, Callable, Coroutine, List, Optional, Tuple, cast

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.showtimes import (
    Showtimes,
    ShowtimesAssignee,
    ShowtimesEpisodeStatus,
    ShowtimesFSDB,
    ShowtimesPoster,
    ShowtimesProject,
)
from naotimes.showtimes.cogbase import AnilistFailure
from naotimes.views import ConfirmView


class ShowAddConfirm(discord.ui.Button):
    _view: ConfirmView

    def __init__(
        self,
        label: str,
        emoji: str,
        callback: Callable[[], Coroutine[Any, Any, Tuple[bool, ShowtimesProject]]],
    ):
        self._actual_callback: Callable[[], Coroutine[Any, Any, Tuple[bool, ShowtimesProject]]] = callback
        super().__init__(label=label, emoji=emoji)

    async def callback(self, interaction: discord.Interaction, /):
        _, project = await self._actual_callback()
        self.value = project
        await self._view._disable(interaction)
        self._view.stop()


class ShowtimesAdminTambah(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.TambahUtang")

    async def _process_anilist_episode(
        self, ctx: naoTimesContext, project: ShowtimesProject, message: discord.Message
    ):
        guild_id = ctx.guild.id
        self.logger.info(f"{guild_id}: Processing anilist episode")

        prompt_msg: discord.Message = None
        actual_msg: str = None
        while True:
            actual_msg, prompt_msg, _ = await ctx.wait_content(
                "Mohon masukan perkiraan jumlah episode!",
                delete_answer=True,
                pass_message=prompt_msg,
                allow_cancel=False,
                return_all=True,
            )
            if actual_msg is None:
                await ctx.send("**Timeout!**")
                return False, project
            if actual_msg is False:
                await ctx.send("**Dibatalkan!**")
                return False, project
            if actual_msg.isdigit():
                break
            await ctx.send_timed("Mohon masukan angka!", 2)

        if isinstance(prompt_msg, discord.Message):
            await prompt_msg.delete()

        schedules_data = await self.bot.showcogs.anilist_get_schedules(project.id, int(actual_msg))
        if not isinstance(schedules_data, list):
            await ctx.send(schedules_data.error)
            return False, project

        parsed_episodes: List[ShowtimesEpisodeStatus] = []
        for schedule in schedules_data:
            parsed_episodes.append(
                ShowtimesEpisodeStatus.from_dict({"episode": schedule.episode, "airtime": schedule.airing_at})
            )
        project.status = parsed_episodes
        return True, project

    async def _process_anilist(
        self,
        ctx: naoTimesContext,
        server_data: Showtimes,
        project: ShowtimesProject,
        message: discord.Message,
    ):
        guild_id = ctx.guild.id
        self.logger.info(f"{guild_id}: Processing anilist data...")

        embed = discord.Embed(title="Menambah utang", color=0x96DF6A)
        embed.add_field(
            name="Anilist ID",
            value="Ketik ID Anilist untuk anime yang diinginkan\n\n"
            "Bisa gunakan `!anime <judul>` dan melihat bagian footer "
            "untuk IDnya\n\nKetik *cancel* untuk membatalkan!",
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await message.edit(embed=embed)

        server_pre = self.bot.prefixes(ctx.guild)
        anilist_cmd = [f"{server_pre}anime", f"{server_pre}kartun", f"{server_pre}ani", f"{server_pre}animu"]

        prompt_msg: discord.Message = None
        answered: discord.Message = None
        real_content: str = None
        while True:
            real_content, prompt_msg, answered = await ctx.wait_content(
                "Masukan ID Anilist", timeout=None, pass_message=prompt_msg, return_all=True
            )
            if real_content is False:
                await ctx.send("**Dibatalkan!**")
                return False, project
            if real_content is None:
                await ctx.send("**Timeout!**")
                return False, project

            any_match = False
            for cmd in anilist_cmd:
                if real_content.startswith(cmd):
                    any_match = True
                    break

            if not any_match:
                try:
                    await answered.delete(no_log=True)
                except Exception:
                    pass
                if real_content.isdigit():
                    if server_data.get_project(real_content):
                        await ctx.send_timed("Proyek tersebut sudah ada!", 2)
                    else:
                        break
                else:
                    await ctx.send_timed("Mohon masukan ID Anilist!", 2)

        if prompt_msg is not None:
            try:
                await prompt_msg.delete(no_log=True)
            except Exception:
                pass

        if not real_content:
            await ctx.send("**Dibatalkan!**")
            return False, project

        anime_info = await self.bot.showcogs.anilist_get_information(real_content)
        if isinstance(anime_info, AnilistFailure):
            await ctx.send(anime_info.error)
            return False, project

        poster_info = ShowtimesPoster(anime_info.cover_image, anime_info.cover_color)
        project.id = anime_info.id
        project.title = anime_info.title
        project.mal_id = anime_info.mal_id
        project.start_time = anime_info.start_time
        project.poster = poster_info
        parsed_schedules: List[ShowtimesEpisodeStatus] = []
        for schedule in anime_info.schedules:
            parsed_schedules.append(
                ShowtimesEpisodeStatus.from_dict({"episode": schedule.episode, "airtime": schedule.airing_at})
            )

        if len(parsed_schedules) < 1:
            # Process episode
            success, project = await self._process_anilist_episode(ctx, project, message)
            return success, project
        else:
            project.status = parsed_schedules
        return True, project

    def _get_user_from_id(self, user_id: int, fallback: Optional[str] = "[Rahasia]") -> Optional[str]:
        if not isinstance(user_id, int):
            return fallback
        user = self.bot.get_user(user_id)
        if user is None:
            return fallback
        return str(user)

    async def _process_role(self, ctx: naoTimesContext, project: ShowtimesProject, message: discord.Message):
        embed = discord.Embed(title="Menambah utang", color=0x96DF6A)
        embed.set_thumbnail(url=project.poster.url)
        embed.add_field(
            name="Role ID",
            value="Ketik ID Role atau mention rolenya\nAtau ketik `auto` untuk membuatnya otomatis",
            inline=False,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await message.edit(embed=embed)

        def check_wait_valid(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel

        while True:
            awaited: discord.Message = await self.bot.wait_for("message", check=check_wait_valid)
            mentions = awaited.role_mentions
            if not mentions:
                if awaited.content.isdigit():
                    # Check if it's a valid role
                    role = ctx.guild.get_role(int(awaited.content))
                    await awaited.delete(no_log=True)
                    if role is None:
                        await ctx.send_timed("Tidak dapat menemukan role tersebut!", 2)
                        continue
                    project.role = role
                elif awaited.content.lower().startswith("auto"):
                    self.logger.info(f"{ctx.guild.id}: auto-generating role...")
                    await awaited.delete(no_log=True)
                    try:
                        gen_role = await ctx.guild.create_role(
                            name=project.title,
                            colour=discord.Colour.random(),
                        )
                        project.role = gen_role
                        break
                    except discord.Forbidden:
                        await ctx.send_timed(
                            "Tidak dapat membuat role karena bot tidak ada akses `Manage Roles`", 3
                        )
                    except discord.HTTPException:
                        await ctx.send_timed(
                            "Terjadi kesalahan ketika menghubungi Discord, mohon coba lagi!", 3
                        )
            else:
                project.role = mentions[0]
                await awaited.delete(no_log=True)
                break
        return True, project

    async def _process_staff(
        self, ctx: naoTimesContext, project: ShowtimesProject, message: discord.Message, staff_role: str
    ):
        pretty_name = self.bot.showcogs.normalize_role_name(staff_role, True)
        embed = discord.Embed(title="Menambah utang", color=0x96DF6A)
        embed.set_thumbnail(url=project.poster.url)
        embed.add_field(
            name=f"{pretty_name} (ID)",
            value=f"Ketik ID Discord {pretty_name} atau mention orangnya",
            inline=False,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await message.edit(embed=embed)

        def check_wait_valid(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel

        while True:
            await_msg: discord.Message = await self.bot.wait_for("message", check=check_wait_valid)
            mentions = await_msg.mentions
            await await_msg.delete(no_log=True)
            if not mentions:
                if await_msg.content.isdigit():
                    staff_id = int(await_msg.content)
                    staff_name = self._get_user_from_id(staff_id, None)
                    if staff_name is not None:
                        staff_name_split = staff_name.rsplit("#", 1)
                        staff_name = staff_name_split[0]
                    project.update_assignment(
                        staff_role,
                        ShowtimesAssignee.from_dict(
                            {
                                "id": staff_id,
                                "name": staff_name,
                            }
                        ),
                    )
                    break
                else:
                    await ctx.send_timed("Mohon masukan angka atau mention orangnya!")
            else:
                project.update_assignment(
                    staff_role,
                    ShowtimesAssignee.from_dict(
                        {
                            "id": mentions[0].id,
                            "name": mentions[0].name,
                        }
                    ),
                )
                break

        return True, project

    @commands.command(name="tambahutang")
    @commands.guild_only()
    async def _showadmin_tambahutang(self, ctx: naoTimesContext):
        guild = ctx.guild
        self.logger.info(f"Requested !tambahutang at {guild.id}")

        server_data = await self.bot.showqueue.fetch_database(guild.id)
        if server_data is None:
            self.logger.error(f"No server data found for {guild.id}")
            return

        self.logger.info(f"{guild.id}: Found server data")

        if not server_data.is_admin(ctx.author):
            self.logger.error(f"{guild.id}: {ctx.author.id} is not an admin")
            return await ctx.send("Hanya admin yang bisa menambah utang baru!")

        self.logger.info(f"{guild.id}: creating initial data...")
        embed = discord.Embed(title="Menamabah utang", color=0x56ACF3)
        embed.add_field(name="Memulai proses!", value="Mempersiapkan...")
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        request_message = await ctx.send(embed=embed)

        project_data = ShowtimesProject.factory()
        is_success, project_data = await self._process_anilist(
            ctx, server_data, project_data, request_message
        )
        if not is_success:
            self.logger.warning(f"{guild.id}: failed to process anilist data")
            try:
                await request_message.delete()
            except Exception:
                pass
            return

        if server_data.get_project(project_data.id):
            self.logger.warning(f"{guild.id}: anime already registered on database.")
            return await ctx.send("Proyek sudah didaftarkan di database.")

        _, project_data = await self._process_role(ctx, project_data, request_message)
        _, project_data = await self._process_staff(ctx, project_data, request_message, "tl")
        _, project_data = await self._process_staff(ctx, project_data, request_message, "tlc")
        _, project_data = await self._process_staff(ctx, project_data, request_message, "enc")
        _, project_data = await self._process_staff(ctx, project_data, request_message, "ed")
        _, project_data = await self._process_staff(ctx, project_data, request_message, "tm")
        _, project_data = await self._process_staff(ctx, project_data, request_message, "ts")
        _, project_data = await self._process_staff(ctx, project_data, request_message, "qc")

        def _get_role_name(id: int):
            if not isinstance(id, int):
                return "[Tidak diketahui]"
            role_data = guild.get_role(id)
            if not role_data:
                return "[Tidak diketahui]"
            return role_data.name

        self.logger.info(f"{guild.id}: adding project to database...")
        first_time = True
        is_cancelled = False
        while True:
            TL_NAME = self._get_user_from_id(project_data.assignment.tlor.id)
            TLC_NAME = self._get_user_from_id(project_data.assignment.tlcer.id)
            ENC_NAME = self._get_user_from_id(project_data.assignment.encoder.id)
            ED_NAME = self._get_user_from_id(project_data.assignment.editor.id)
            TM_NAME = self._get_user_from_id(project_data.assignment.timer.id)
            TS_NAME = self._get_user_from_id(project_data.assignment.tser.id)
            QC_NAME = self._get_user_from_id(project_data.assignment.qcer.id)

            embed = discord.Embed(
                title="Menambah Utang",
                description="Periksa data!\nReact jika ingin diubah.",
                color=0xE7E363,
            )
            embed.set_thumbnail(url=project_data.poster.url)
            embed.add_field(
                name="1⃣ Judul",
                value=f"{project_data.title} ({project_data.id})",
                inline=False,
            )
            embed.add_field(
                name="2⃣ Episode",
                value=f"{project_data.total_episodes} episodes",
                inline=False,
            )
            embed.add_field(
                name="3⃣ Role",
                value=_get_role_name(project_data.role),
                inline=False,
            )
            embed.add_field(name="4⃣ Translator", value=TL_NAME, inline=True)
            embed.add_field(name="5⃣ TLCer", value=TLC_NAME, inline=True)
            embed.add_field(name="6⃣ Encoder", value=ENC_NAME, inline=True)
            embed.add_field(name="7⃣ Editor", value=ED_NAME, inline=True)
            embed.add_field(name="8⃣ Timer", value=TM_NAME, inline=True)
            embed.add_field(name="9⃣ Typesetter", value=TS_NAME, inline=True)
            embed.add_field(name="0⃣ Quality Checker", value=QC_NAME, inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            confirm_view = ConfirmView(ctx, timeout=None)
            confirm_view.cancel.label = "Batalkan"
            confirm_view.cancel.row = 4
            confirm_view.confirm.label = "Tambahkan"
            confirm_view.confirm.row = 4
            # Attach the edit
            confirm_view.add_item(
                ShowAddConfirm(
                    "Judul",
                    "1⃣",
                    partial(self._process_anilist, ctx, server_data, project_data, request_message),
                )
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "Episode",
                    "2⃣",
                    partial(self._process_anilist_episode, ctx, project_data, request_message),
                )
            )
            confirm_view.add_item(
                ShowAddConfirm("Role", "3⃣", partial(self._process_role, ctx, project_data, request_message))
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "Translator", "4⃣", partial(self._process_staff, ctx, project_data, request_message, "tl")
                )
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "TLCer", "5⃣", partial(self._process_staff, ctx, project_data, request_message, "tlc")
                )
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "Encoder", "6⃣", partial(self._process_staff, ctx, project_data, request_message, "enc")
                )
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "Editor", "7⃣", partial(self._process_staff, ctx, project_data, request_message, "ed")
                )
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "Timer", "8⃣", partial(self._process_staff, ctx, project_data, request_message, "tm")
                )
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "Typesetter", "9⃣", partial(self._process_staff, ctx, project_data, request_message, "ts")
                )
            )
            confirm_view.add_item(
                ShowAddConfirm(
                    "Quality Checker",
                    "0⃣",
                    partial(self._process_staff, ctx, project_data, request_message, "qc"),
                )
            )

            if first_time:
                await request_message.delete()
                request_message = await ctx.send(embed=embed, view=confirm_view)
                first_time = False
            else:
                await request_message.edit(embed=embed, view=confirm_view)
            await confirm_view.wait()

            if confirm_view is True:
                break
            if confirm_view is False:
                is_cancelled = True
                break
            project_data = cast(ShowtimesProject, confirm_view.value)

        if is_cancelled:
            self.logger.warning(f"{guild.id}: user cancelled adding project")
            return await ctx.send("Proyek batal ditambah!")

        self.logger.info(f"{guild.id}: commiting data to database...")
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await request_message.edit(embed=embed, view=None)

        self.logger.info(f"{guild.id}: Checking valid member...")
        all_members: List[Tuple[str, discord.Member]] = []
        for role, role_staff in project_data.assignment:
            if not role_staff.id:
                continue
            if isinstance(role_staff.id, int):
                user_info = guild.get_member(role_staff.id)
                if user_info is not None:
                    all_members.append((role, user_info))
            elif isinstance(role_staff.id, str):
                id_quick = role_staff.id
                if id_quick.isdigit():
                    id_quick = int(id_quick)
                    user_info = guild.get_member(id_quick)
                    if user_info is not None:
                        all_members.append((role, user_info))

        for member in all_members:
            project_data.update_assignment(member[0], member[1])

        self.logger.info(f"{guild.id}: giving the member roles...")
        role_given_success = True
        role_id = project_data.role
        if isinstance(role_id, int):
            role_info = guild.get_role(role_id)
            if role_info is not None:
                for member in all_members:
                    member_role = member[1].get_role(role_info.id)
                    if member_role is None:
                        self.logger.info(f"{guild.id}: giving {member[1]} the {role_info} role!")
                        try:
                            await member[1].add_roles(role_info)
                        except (discord.Forbidden, discord.HTTPException):
                            role_given_success = False
                            self.logger.error(f"Gagal menambah role ke user {member[1]}")

        mal_id = project_data.mal_id
        if server_data.fsdb_id is not None and self.bot.fsdb is not None and mal_id is not None:
            self.logger.info(f"{guild.id}: updating FansubDB data...")
            embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
            embed.add_field(name="Memproses!", value="Membuat data fansubdb...", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await request_message.edit(embed=embed)
            fansubs_projects, _ = await self.bot.fsdb.fetch_fansub_projects(server_data.fsdb_id)
            existing_projects = {str(data.anime.mal_id): data.id for data in fansubs_projects}

            fsani_data = await self.bot.fsdb.fetch_anime_by_mal(mal_id)
            if fsani_data is None:
                _, fsani_id = await self.bot.fsdb.import_mal(int(mal_id))
                _, fsproject_id = await self.bot.fsdb.add_new_project(fsani_id, server_data.fsdb_id)
                project_data.fsdb = ShowtimesFSDB(fsproject_id, fsani_id)
            else:
                fsani_id = fsani_data.id
                if str(mal_id) in existing_projects:
                    project_data.fsdb = ShowtimesFSDB(existing_projects[str(mal_id)], fsani_id)
                else:
                    _, fsproject_id = await self.bot.fsdb.add_new_project(fsani_id, server_data.fsdb_id)
                    project_data.fsdb = ShowtimesFSDB(fsproject_id, fsani_id)

        self.logger.info(f"{guild.id}: committing data to database...")
        server_data += project_data
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await request_message.edit(embed=embed)

        await self.bot.showqueue.add_job(server_data)

        self.logger.info(f"{guild.id}: Updating main database...")
        success, msg = await self.bot.ntdb.update_server(server_data)
        await request_message.delete()

        if not success:
            self.logger.error(f"{guild.id}: failed to update, reason: {msg}")
            if str(guild.id) not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(guild.id))

        self.logger.info(f"{guild.id}: done processing!")
        await ctx.send(f"Berhasil menambahkan `{project_data.title}` ke database utama naoTimes!")
        if role_given_success:
            await ctx.send("Bot telah otomatis menambah role ke member garapan, mohon cek!")


async def setup(bot: naoTimesBot):
    ntdb = bot.ntdb
    if ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesAdminTambah(bot))
