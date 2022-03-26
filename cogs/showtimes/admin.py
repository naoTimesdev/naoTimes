import logging
from typing import Dict, List, Tuple, TypeVar, Union

import disnake
from disnake.ext import commands

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
from naotimes.utils import get_current_time

Fallback = TypeVar("Fallback")

ADD_EPISODE = """Jumlah yang dimaksud adalah jumlah yang ingin ditambahkan dari jumlah episode sekarang
Misal ketik `4` dan total jumlah episode sekarang adalah `12`
Maka total akan berubah menjadi `16` `(13, 14, 15, 16)`"""  # noqa: E501
REMOVE_EPISODE = """Ranged number, bisa satu digit untuk 1 episode saja atau range dari episode x sampai y
Contoh: `4` untuk episode 4 saja || `4-6` untuk episode 4 sampai 6"""  # noqa: E501


class ShowtimesAdmin(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.queue = bot.showqueue
        self.base = bot.showcogs
        self.logger = logging.getLogger("Showtimes.Admin")

    @commands.command(name="tambahutang")
    @commands.guild_only()
    async def _showadmin_tambahutang(self, ctx: naoTimesContext):
        guild: disnake.Guild = ctx.guild
        server_id = str(guild.id)
        self.logger.info(f"Requested !tambahutang at {server_id}")

        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

        if not srv_data.is_admin(ctx.author):
            self.logger.error(f"{server_id}: not the server owner...")
            return await ctx.send("Hanya admin yang bisa menambah utang baru!")

        self.logger.info(f"{server_id}: creating initial data...")
        embed = disnake.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        base_message = await ctx.send(embed=embed)
        server_pre = self.bot.prefixes(guild)
        anilist_cmd = f"{server_pre}anime"
        project_data = ShowtimesProject.factory()

        def check_if_author(m: disnake.Message):
            return m.author.id == ctx.author.id

        async def _process_anilist_episode(ani_id: str):
            self.logger.info(f"{server_id}: processing total episodes...")
            prompt_msg: disnake.Message = None
            real_msg: str = None
            real_episode: int = None
            while True:
                [real_msg, prompt_msg, _] = await ctx.wait_content(
                    "Mohon masukan perkiraan jumlah episode!",
                    delete_answer=True,
                    pass_message=prompt_msg,
                    allow_cancel=False,
                    return_all=True,
                )
                if real_msg.isdigit():
                    real_episode = int(real_msg)
                    break
                else:
                    await ctx.send_timed("Mohon masukan angka!", 2)

            if prompt_msg:
                await prompt_msg.delete()

            anilist_data = await self.base.fetch_anilist(ani_id, 1, real_episode)
            time_data = anilist_data["time_data"]
            all_episodes = []
            for episode, time_info in enumerate(time_data, 1):
                episode_info = ShowtimesEpisodeStatus.from_dict(
                    {
                        "episode": episode,
                        "airtime": time_info,
                    }
                )
                all_episodes.append(episode_info)
            project_data.status = all_episodes
            return True

        async def _process_anilist():
            self.logger.info(f"{server_id}: processing anime data...")
            embed = disnake.Embed(title="Menambah utang", color=0x96DF6A)
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
            await base_message.edit(embed=embed)

            prompt_msg: disnake.Message = None
            answered: disnake.Message = None
            real_content: str = None
            while True:
                [real_content, prompt_msg, answered] = await ctx.wait_content(
                    "Masukan ID Anilist", timeout=None, pass_message=prompt_msg, return_all=True
                )
                if not real_content.startswith(anilist_cmd):
                    await answered.delete(no_log=True)
                    if real_content == "cancel":
                        return None, "Dibatalkan oleh user"
                    if real_content.isdigit():
                        if srv_data.get_project(real_content):
                            await ctx.send_timed("Proyek tersebut sudah terdaftar!", 2)
                        else:
                            break
                    else:
                        await ctx.send_timed("Mohon masukan angka!", 2)

            if prompt_msg:
                await prompt_msg.delete()
            if not real_content:
                return None, "Tidak diberikan ID anilist!"

            try:
                anilist_data = await self.base.fetch_anilist(
                    real_content,
                    1,
                    1,
                )
            except Exception:
                self.logger.warning(f"{server_id}: failed to fetch air start, please try again later.")
                return (
                    None,
                    "Gagal mendapatkan waktu mulai tayang, silakan coba lagi ketika sudah "
                    "ada kepastian kapan animenya mulai.",
                )

            if isinstance(anilist_data, str):
                self.logger.warning(f"{server_id}: failed to get data, unknown ID?")
                return None, "Tidak dapat menemukan hasil untuk ID tersebut, mohon coba lagi"

            poster_data, title = anilist_data["poster_data"], anilist_data["title"]
            time_data, episodes_total = anilist_data["time_data"], anilist_data["total_episodes"]
            poster_image, poster_color = poster_data["image"], poster_data["color"]
            anilist_id, mal_id = anilist_data["id"], anilist_data["idMal"]
            air_start = anilist_data["airing_start"]

            embed = disnake.Embed(title="Menambah utang", color=0x96DF6A)
            embed.set_thumbnail(url=poster_image)
            embed.add_field(name="Apakah benar?", value=f"Judul: **{title}**", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)
            is_confirmed = await ctx.confirm(base_message, True)
            if not is_confirmed:
                return False, "Dibatalkan oleh user"

            self.logger.info(f"{server_id}: processing time data...")
            poster_info = ShowtimesPoster(poster_image, poster_color)
            project_data.id = anilist_id
            project_data.title = title
            project_data.mal_id = mal_id
            project_data.start_time = air_start
            project_data.poster = poster_info
            if episodes_total == 1:
                success = await _process_anilist_episode(anilist_id)
                return success, None if success else "Terjadi kesalahan ketika menanyakan jumlah episode!"
            else:
                all_episodes = []
                for episode, time_info in enumerate(time_data, 1):
                    episode_info = ShowtimesEpisodeStatus.from_dict(
                        {
                            "episode": episode,
                            "airtime": time_info,
                        }
                    )
                    all_episodes.append(episode_info)

                project_data.status = all_episodes
                return True, None

        async def _process_role():
            self.logger.info(f"{server_id}: processing roles")
            embed = disnake.Embed(title="Menambah utang", color=0x96DF6A)
            embed.set_thumbnail(url=project_data.poster.url)
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\nAtau ketik `auto` untuk membuatnya otomatis",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            awaited: disnake.Message
            while True:
                awaited = await self.bot.wait_for("message", check=check_if_author)
                mentions = awaited.role_mentions
                if not mentions:
                    if awaited.content.isdigit():
                        project_data.role = int(awaited.content)
                        await awaited.delete(no_log=True)
                    elif awaited.content.startswith("auto"):
                        self.logger.info(f"{server_id}: auto-generating role...")
                        await awaited.delete(no_log=True)
                        try:
                            gen_role = await guild.create_role(
                                name=project_data.title,
                                colour=disnake.Colour.random(),
                            )
                            project_data.role = gen_role
                            break
                        except disnake.Forbidden:
                            await ctx.send_timed(
                                "Tidak dapat membuat role karena bot tidak ada akses `Manage Roles`", 3
                            )
                        except disnake.HTTPException:
                            await ctx.send_timed(
                                "Terjadi kesalahan ketika menghubungi Discord, mohon coba lagi!", 3
                            )
                else:
                    project_data.role = mentions[0]
                    await awaited.delete(no_log=True)
                    break
            return True

        def _get_user_from_id(id: int, fallback: Fallback = "[Rahasia]") -> Union[str, Fallback]:
            if not isinstance(id, int):
                return fallback
            user_data = self.bot.get_user(id)
            if not user_data:
                return fallback
            return str(user_data)

        async def _process_staff(staff_role: str):
            pretty_name = self.base.normalize_role_name(staff_role, True)
            embed = disnake.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=project_data.poster.url)
            embed.add_field(
                name=f"{pretty_name} (ID)",
                value=f"Ketik ID Discord {pretty_name} atau mention orangnya",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            while True:
                await_msg: disnake.Message = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                await await_msg.delete(no_log=True)
                if not mentions:
                    if await_msg.content.isdigit():
                        staff_id = int(await_msg.content)
                        staff_name = _get_user_from_id(staff_id, None)
                        if staff_name is not None:
                            staff_name_split = staff_name.rsplit("#", 1)
                            staff_name = staff_name_split[0]
                        project_data.update_assignment(
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
                    project_data.update_assignment(
                        staff_role,
                        ShowtimesAssignee.from_dict(
                            {
                                "id": mentions[0].id,
                                "name": mentions[0].name,
                            }
                        ),
                    )
                    break

            return True

        is_valid, err_msg = await _process_anilist()
        if not is_valid:
            self.logger.warning(f"{server_id}: process cancelled")
            return await ctx.send(err_msg)

        if srv_data.get_project(project_data.id) is not None:
            self.logger.warning(f"{server_id}: anime already registered on database.")
            return await ctx.send("Proyek sudah didaftarkan di database.")

        await _process_role()
        await _process_staff("tl")
        await _process_staff("tlc")
        await _process_staff("enc")
        await _process_staff("ed")
        await _process_staff("tm")
        await _process_staff("ts")
        await _process_staff("qc")

        def _get_role_name(id: int):
            if not isinstance(id, int):
                return "[Tidak diketahui]"
            role_data = guild.get_role(id)
            if not role_data:
                return "[Tidak diketahui]"
            return role_data.name

        self.logger.info(f"{server_id}: Checkpoint before comitting!")
        first_time = True
        is_cancelled = False
        while True:
            TL_NAME = _get_user_from_id(project_data.assignment.tlor.id)
            TLC_NAME = _get_user_from_id(project_data.assignment.tlcer.id)
            ENC_NAME = _get_user_from_id(project_data.assignment.encoder.id)
            ED_NAME = _get_user_from_id(project_data.assignment.editor.id)
            TM_NAME = _get_user_from_id(project_data.assignment.timer.id)
            TS_NAME = _get_user_from_id(project_data.assignment.tser.id)
            QC_NAME = _get_user_from_id(project_data.assignment.qcer.id)

            embed = disnake.Embed(
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
            embed.add_field(
                name="Lain-Lain",
                value="✅ Tambahkan!\n❌ Batalkan!",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                await base_message.delete()
                base_message = await ctx.send(embed=embed)
                first_time = False
            else:
                await base_message.edit(embed=embed)

            REACT_ANDYS = [
                "1⃣",
                "2⃣",
                "3⃣",
                "4⃣",
                "5⃣",
                "6⃣",
                "7⃣",
                "8⃣",
                "9⃣",
                "0⃣",
                "✅",
                "❌",
            ]
            for reaction in REACT_ANDYS:
                await base_message.add_reaction(reaction)

            def reaction_check(reaction: disnake.Reaction, user: disnake.Member):
                return (
                    reaction.message.id == base_message.id
                    and user.id != self.bot.user.id
                    and reaction.emoji in REACT_ANDYS
                )

            res: disnake.Reaction
            user: disnake.Member
            res, user = await self.bot.wait_for("reaction_add", check=reaction_check)
            if user != ctx.author:
                continue
            await base_message.clear_reactions()
            if res.emoji == REACT_ANDYS[0]:
                await _process_anilist()
            elif res.emoji == REACT_ANDYS[1]:
                await _process_anilist_episode(project_data.id)
            elif res.emoji == REACT_ANDYS[2]:
                await _process_role()
            elif res.emoji == REACT_ANDYS[3]:
                await _process_staff("tl")
            elif res.emoji == REACT_ANDYS[4]:
                await _process_staff("tlc")
            elif res.emoji == REACT_ANDYS[5]:
                await _process_staff("enc")
            elif res.emoji == REACT_ANDYS[6]:
                await _process_staff("ed")
            elif res.emoji == REACT_ANDYS[7]:
                await _process_staff("tm")
            elif res.emoji == REACT_ANDYS[8]:
                await _process_staff("ts")
            elif res.emoji == REACT_ANDYS[9]:
                await _process_staff("qc")
            elif res.emoji == "✅":
                break
            elif res.emoji == "❌":
                is_cancelled = True
                break

        if is_cancelled:
            return await ctx.send("Dibatalkan!")

        self.logger.info(f"{server_id}: commiting data to database...")
        embed = disnake.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await base_message.edit(embed=embed)

        self.logger.info(f"{server_id}: Checking valid member...")
        all_members: List[Tuple[str, disnake.Member]] = []
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

        self.logger.info(f"{server_id}: giving the member roles...")
        role_given_success = True
        role_id = project_data.role
        if isinstance(role_id, int):
            role_info = guild.get_role(role_id)
            if role_info is not None:
                for member in all_members:
                    member_role = member[1].get_role(role_info.id)
                    if member_role is None:
                        self.logger.info(f"{server_id}: giving {member[1]} the {role_info} role!")
                        try:
                            await member[1].add_roles(role_info)
                        except (disnake.Forbidden, disnake.HTTPException):
                            role_given_success = False
                            self.logger.error(f"Gagal menambah role ke user {member[1]}")

        mal_id = project_data.mal_id
        if srv_data.fsdb_id is not None and self.bot.fsdb is not None and mal_id is not None:
            self.logger.info(f"{server_id}: updating FansubDB data...")
            embed = disnake.Embed(title="Menambah Utang", color=0x56ACF3)
            embed.add_field(name="Memproses!", value="Membuat data fansubdb...", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)
            fansubs_projects, _ = await self.bot.fsdb.fetch_fansub_projects(srv_data.fsdb_id)
            existing_projects = {str(data.anime.mal_id): data.id for data in fansubs_projects}

            fsani_data = await self.bot.fsdb.fetch_anime_by_mal(mal_id)
            if fsani_data is None:
                _, fsani_id = await self.bot.fsdb.import_mal(int(mal_id))
                _, fsproject_id = await self.bot.fsdb.add_new_project(fsani_id, srv_data.fsdb_id)
                project_data.fsdb = ShowtimesFSDB(fsproject_id, fsani_id)
            else:
                fsani_id = fsani_data.id
                if str(mal_id) in existing_projects:
                    project_data.fsdb = ShowtimesFSDB(existing_projects[str(mal_id)], fsani_id)
                else:
                    _, fsproject_id = await self.bot.fsdb.add_new_project(fsani_id, srv_data.fsdb_id)
                    project_data.fsdb = ShowtimesFSDB(fsproject_id, fsani_id)

        self.logger.info(f"{server_id}: updating database...")
        srv_data += project_data
        embed = disnake.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await base_message.edit(embed=embed)

        await self.bot.showqueue.add_job(srv_data)

        self.logger.info(f"{server_id}: Updating main database...")
        success, msg = await self.bot.ntdb.update_server(srv_data)
        await base_message.delete()

        if not success:
            self.logger.error(f"{server_id}: failed to update, reason: {msg}")
            if server_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_id)

        self.logger.info(f"{server_id}: done processing!")
        await ctx.send(f"Berhasil menambahkan `{project_data.title}` ke database utama naoTimes!")
        if role_given_success:
            await ctx.send("Bot telah otomatis menambah role ke member garapan, mohon cek!")

    @commands.command(name="ubahdata")
    @commands.guild_only()
    async def _showadmin_ubahdata(self, ctx: naoTimesContext, *, judul: str = None):
        guild: disnake.Guild = ctx.guild
        server_id = str(guild.id)
        self.logger.info(f"Requested !ubahdata at {server_id}")

        srv_data = await self.queue.fetch_database(server_id)
        if srv_data is None:
            return
        self.logger.info(f"{server_id}: server found proceeding...")

        if not srv_data.is_admin(ctx.author):
            self.logger.error(f"{server_id}: not the server owner...")
            return await ctx.send("Hanya admin yang bisa menambah utang baru!")

        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)

        self.logger.info(f"{server_id}: getting close matches...")
        all_matches = srv_data.find_projects(judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.info(f"{server_id}: found multiple matches!")
            selected_anime = await ctx.select_simple(all_matches, lambda x: x.title)
            if selected_anime is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [selected_anime]

        matched_anime = all_matches[0]
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        all_stupid_role_used = map(
            lambda x: x.role, filter(lambda x: x.id != matched_anime.id, srv_data.projects)
        )
        all_stupid_role_used = list(filter(lambda x: isinstance(x, int), all_stupid_role_used))
        embed = disnake.Embed(title="Mengubah data", color=0xEB79B9)
        embed.description = "Mempersiapkan proses..."
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        base_message = await ctx.send(embed=embed)

        def _is_original_author(m: disnake.Message):
            return m.author.id == ctx.author.id

        def _get_user_name(user: int, fallback: str = "[Tidak diketahui]"):
            if not user:
                return fallback
            user_data = self.bot.get_user(user)
            if user_data is None:
                return fallback
            return str(user_data)

        async def _internal_change_staff(role: str):
            self.logger.info(f"{matched_anime.title}: changing staff {role}")
            embed = disnake.Embed(title="Mengubah Staff", color=0xEB79B9)
            norm_role = self.base.normalize_role_name(role, True)
            embed.add_field(
                name=f"{norm_role} (ID)",
                value=f"Ketik ID {norm_role} atau mention orangnya!",
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            await_msg: disnake.Message
            while True:
                await_msg = await self.bot.wait_for("message", check=_is_original_author)
                mentions = await_msg.mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        user_name = _get_user_name(int(await_msg.content), None)
                        if user_name is not None:
                            user_split = user_name.split("#")
                            user_name = "#".join(user_split[:-1])
                        matched_anime.update_assignment(
                            role,
                            ShowtimesAssignee.from_dict(
                                {
                                    "id": str(await_msg.content),
                                    "name": user_name,
                                }
                            ),
                        )
                        await await_msg.delete(no_log=True)
                        break
                else:
                    first_user = mentions[0]
                    matched_anime.update_assignment(
                        role,
                        first_user,
                    )
                    await await_msg.delete(no_log=True)
                    break
            return True

        async def _change_staff():
            self.logger.info(f"{matched_anime.title}: Processing staff...")
            REACT_ANYDS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
            while True:
                STAFF_LIST: Dict[str, str] = {}
                staff_list = matched_anime.assignment.copy()
                STAFF_KEYS = list(staff_list.serialize().keys())

                for role, staffers in staff_list:
                    user_name = _get_user_name(staffers.id)
                    STAFF_LIST[role] = user_name

                embed = disnake.Embed(
                    title="Mengubah Staff", description=f"Anime: {matched_anime.title}", color=0xEBA279
                )
                for n, (role, user_name) in enumerate(STAFF_LIST.items()):
                    embed.add_field(
                        name=f"{REACT_ANYDS[n]} {self.base.normalize_role_name(role, True)}",
                        value=user_name,
                        inline=False,
                    )
                embed.add_field(name="Lain-Lain", value="✅ Selesai!", inline=False)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™",
                    icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await base_message.edit(embed=embed)

                EXTENDED_ANDYS = REACT_ANYDS[:]
                EXTENDED_ANDYS.append("✅")

                for REACT in EXTENDED_ANDYS:
                    await base_message.add_reaction(REACT)

                def _check_reaction(reaction: disnake.Reaction, user: disnake.Member):
                    return (
                        reaction.message.id == base_message.id
                        and user.id == ctx.author.id
                        and str(reaction.emoji) in EXTENDED_ANDYS
                    )

                res: disnake.Reaction
                user: disnake.Member
                res, user = await self.bot.wait_for("reaction_add", check=_check_reaction)
                if user != ctx.author:
                    continue
                await base_message.clear_reactions()
                if res.emoji == "✅":
                    break
                else:
                    react_pos = REACT_ANYDS.index(str(res.emoji))
                    await _internal_change_staff(STAFF_KEYS[react_pos].lower())

        async def _change_role():
            self.logger.info(f"{matched_anime.title}: Processing role...")
            embed = disnake.Embed(title="Mengubah Role", color=0xEBA279)
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\nAtau ketik `auto` untuk membuatnya otomatis",
            )
            embed.set_footer(
                text="Dibawahkan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            await_msg: disnake.Message
            while True:
                await_msg = await self.bot.wait_for("message", check=_is_original_author)
                mentions = await_msg.role_mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        matched_anime.role = int(await_msg.content)
                        await await_msg.delete(no_log=True)
                        break
                    elif await_msg.content.startswith("auto"):
                        try:
                            content_role = await guild.create_role(
                                name=matched_anime.title, colour=disnake.Colour.random(), mentionable=True
                            )
                            await await_msg.delete(no_log=True)
                            matched_anime.role = content_role
                        except (disnake.Forbidden, disnake.HTTPException):
                            await ctx.send_timed("Gagal membuat role baru, mohon periksa permission!")
                            await await_msg.delete(no_log=True)
                else:
                    matched_anime.role = mentions[0]
                    await await_msg.delete(no_log=True)
                    break
            return True

        async def _tambah_episode():
            self.logger.info(f"{matched_anime.title}: Processing to add new episode...")
            last_episode = matched_anime.status[-1]
            anilist_data = await self.base.fetch_anilist(matched_anime.id, 1, last_episode.episode)
            time_data = anilist_data["time_data"]

            embed = disnake.Embed(
                title="Menambah Episode",
                description=f"Jumlah Episode Sekarang: {last_episode.episode}",
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan jumlah episode yang diinginkan.",
                value=ADD_EPISODE,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            jumlah_tambahan = None
            await_msg: disnake.Message
            while True:
                await_msg = await self.bot.wait_for("message", check=_is_original_author)
                if await_msg.content.isdigit():
                    jumlah_tambahan = int(await_msg.content)
                    await await_msg.delete(no_log=True)
                    break
                else:
                    await ctx.send_timed("Mohon masukan jumlah episode yang benar!")
                    await await_msg.delete(no_log=True)

            fsdb_anime = matched_anime.fsdb
            if last_episode.finished and fsdb_anime is not None and self.bot.fsdb is not None:
                self.logger.info("Updating FSDB Project to on progress again.")
                if fsdb_anime.id:
                    await self.bot.fsdb.update_project(fsdb_anime.id, "status", "Jalan")

            for episode in range(last_episode.episode + 1, last_episode.episode + jumlah_tambahan + 1):
                ep_child = ShowtimesEpisodeStatus.from_dict(
                    {"episode": episode, "airtime": time_data[episode - 1]}
                )
                matched_anime.add_episode(ep_child)
            await ctx.send_timed(f"Berhasil menambah {jumlah_tambahan} episode baru", 2)
            matched_anime.update_time()
            return True

        async def _hapus_episode():
            self.logger.info(f"{matched_anime.title}: Processing to remove episode...")
            last_episode = matched_anime.status[-1].episode
            embed = disnake.Embed(
                title="Menambah Episode",
                description=f"Jumlah Episode Sekarang: {last_episode}",
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan range episode yang ingin dihapus.",
                value=REMOVE_EPISODE,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            hapus_range = None
            prompt_msg: disnake.Message = None
            while True:
                [hapus_range, prompt_msg, _] = await ctx.wait_content(
                    "Mohon masukan range episode!",
                    delete_answer=True,
                    return_all=True,
                    timeout=None,
                    pass_message=prompt_msg,
                    allow_cancel=False,
                )

                confirmation = await ctx.confirm(
                    f"Apakah anda yakin untuk range episode ini **{hapus_range}**?"
                )
                if confirmation:
                    await prompt_msg.delete()
                    break

            total_episode = hapus_range.split("-")
            if len(total_episode) < 2:
                current = total_episode[0]
                total = total_episode[0]
            else:
                current = total_episode[0]
                total = total_episode[1]

            if current.isdigit() and total.isdigit():
                current = int(current)
                total = int(total)
                if current > last_episode:
                    await ctx.send_timed(
                        f"Angka tidak bisa lebih dari episode maksimum ({current} > {last_episode})", 2
                    )
                    return True
                if total > last_episode:
                    await ctx.send_timed(
                        f"Angka akhir tidak bisa lebih dari episode maksimum ({current} > {last_episode})", 2
                    )
                    return True
                if current > total:
                    await ctx.send_timed(
                        f"Angka awal tidak bisa lebih dari angka akhir ({current} > {total})", 2
                    )
                    return True
                self.logger.info(f"{matched_anime.title}: removing a total of {total} episodes...")
                for ep in range(current, total + 1):
                    matched_anime.remove_episode(ep)

                new_maximum_episode = matched_anime.status[-1]
                fsdb_anime = matched_anime.fsdb
                if new_maximum_episode.finished and fsdb_anime is not None and self.bot.fsdb is not None:
                    self.logger.info("Updating FSDB Project to finished.")
                    if fsdb_anime.id:
                        await self.bot.fsdb.update_project(fsdb_anime.id, "status", "Tamat")
                await ctx.send_timed(f"Berhasil menghapus episode {current} ke {total}", 2)
                matched_anime.update_time()
            else:
                await ctx.send_timed("Mohon masukan angka!")

        async def _hapus_utang_confirmation():
            self.logger.info(f"{matched_anime.title}: preparing to nuke project...")
            embed = disnake.Embed(
                title="Menghapus Utang",
                description=f"Anime: {matched_anime.title}",
                color=0xCC1C20,
            )
            embed.add_field(
                name="Peringatan!",
                value="Utang akan dihapus selama-lamanya dan tidak bisa " "dikembalikan!\nLanjutkan proses?",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)
            do_delete = await ctx.confirm(base_message, True)
            return do_delete

        hapus_utang = False
        exit_command = False
        while True:
            total_episode = matched_anime.total_episodes
            real_role = "*Tidak diketahui*"
            if matched_anime.role is not None:
                role_check = guild.get_role(matched_anime.role)
                if role_check is not None:
                    real_role = role_check.name
            embed = disnake.Embed(
                title="Mengubah Data",
                description=f"Anime: {matched_anime.title}",
                color=0xE7E363,
            )
            embed.add_field(
                name="1️⃣ Ubah Staff",
                value="Ubah staff yang mengerjakan anime ini.",
                inline=False,
            )
            embed.add_field(
                name="2️⃣ Ubah Role",
                value="Ubah role discord yang digunakan:\n" f"Role sekarang: {real_role}",
                inline=False,
            )
            embed.add_field(
                name="3️⃣ Tambah Episode",
                value=f"Tambah jumlah episode\nTotal Episode sekarang: {total_episode}",
                inline=False,
            )
            embed.add_field(
                name="4️⃣ Hapus Episode",
                value="Hapus episode dengan range tertentu.",
                inline=False,
            )
            embed.add_field(
                name="5️⃣ Drop Garapan",
                value="Menghapus garapan ini dari daftar utang untuk selama-lamanya...",
                inline=False,
            )
            embed.add_field(name="Lain-Lain", value="✅ Selesai!\n❌ Batalkan!", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            REACT_ANDYS = [
                "1️⃣",
                "2️⃣",
                "3️⃣",
                "4️⃣",
                "5️⃣",
                "✅",
                "❌",
            ]

            for REACT in REACT_ANDYS:
                await base_message.add_reaction(REACT)

            def _check_reaction(reaction: disnake.Reaction, user: disnake.Member):
                return (
                    reaction.message.id == base_message.id
                    and user.id == ctx.author.id
                    and reaction.emoji in REACT_ANDYS
                )

            res: disnake.Reaction
            user: disnake.Member
            res, user = await self.bot.wait_for("reaction_add", check=_check_reaction)
            if user != ctx.author:
                continue
            await base_message.clear_reactions()
            if res.emoji == "1️⃣":
                await _change_staff()
            elif res.emoji == "2️⃣":
                await _change_role()
            elif res.emoji == "3️⃣":
                await _tambah_episode()
            elif res.emoji == "4️⃣":
                await _hapus_episode()
            elif res.emoji == "5️⃣":
                result = await _hapus_utang_confirmation()
                if result:
                    hapus_utang = result
                    break
            elif res.emoji == "✅":
                break
            elif res.emoji == "❌":
                exit_command = True
                break

        await base_message.delete()
        if exit_command:
            self.logger.warning(f"{matched_anime.title}: cancelling...")
            return await ctx.send("**Dibatalkan!**")
        if hapus_utang:
            self.logger.warning(f"{matched_anime.title}: nuking project...")
            fsdb_data = matched_anime.fsdb
            if fsdb_data is not None and self.bot.fsdb is not None:
                self.logger.warning("Updating FSDB Project to dropped.")
                if fsdb_data.id:
                    await self.bot.fsdb.update_project(fsdb_data.id, "status", "Drop")

            current = matched_anime.get_current()
            announce_it = False
            if current is not None and current.finished:
                announce_it = True

            role_id = matched_anime.role
            # Delete role, but dont delete it if it being used by another project.
            if isinstance(role_id, int) and role_id not in all_stupid_role_used:
                self.logger.info(f"{matched_anime.title}: Trying to remove role ID {role_id}")
                role_real = guild.get_role(role_id)
                if role_real is not None:
                    try:
                        await role_real.delete()
                        self.logger.warning(f"{matched_anime.title}:{role_id}: role removed!")
                    except (disnake.Forbidden, disnake.HTTPException):
                        self.logger.error(f"{matched_anime.title}:{role_id}: failed to remove role!")

            srv_data -= matched_anime
            update_cache: List[Showtimes] = []
            update_cache.append(srv_data)
            for osrv in matched_anime.kolaborasi:
                osrv_data = await self.queue.fetch_database(osrv)
                if osrv_data is None:
                    continue
                osrv_anime = osrv_data.get_project(matched_anime)
                if osrv_anime is None:
                    continue
                removed = osrv_anime.remove_kolaborator(guild.id)
                if removed is not None:
                    osrv_data.update_project(osrv_anime)
                    update_cache.append(osrv_data)

            for update in update_cache:
                await self.queue.add_job(update)
            await ctx.send(f"Berhasil menghapus **{matched_anime.title}** dari daftar utang!")

            self.logger.info(f"{server_id}: Updating main database...")
            for update in update_cache:
                ures, umsg = await self.bot.ntdb.update_server(update)
                if not ures:
                    if update.id not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(update.id)
                    self.logger.error(
                        f"{server_id}: Failed to update showtimes data for {update.id}, reason: {umsg}"
                    )

            if announce_it and srv_data.announcer is not None:
                embed = disnake.Embed(title=matched_anime.title, color=0xB51E1E)
                embed.add_field(
                    name="Dropped...",
                    value=f"{matched_anime.title} telah di drop dari fansub ini :(",
                    inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await self.base.announce_embed(self.bot, srv_data.announcer, embed)
            return

        self.logger.warning(f"{matched_anime.title}: saving new data...")
        update_cache: List[Showtimes] = []
        update_cache.append(srv_data)
        for osrv in matched_anime.kolaborasi:
            osrv_data = await self.queue.fetch_database(osrv)
            if osrv_data is None:
                continue
            osrv_anime = osrv_data.get_project(matched_anime)
            if osrv_anime is None:
                continue
            osrv_data.update_project(matched_anime, False)
            update_cache.append(osrv_data)

        for update in update_cache:
            await self.queue.add_job(update)

        self.logger.info(f"{server_id}: Updating main database...")
        for update in update_cache:
            ures, umsg = await self.bot.ntdb.update_server(update)
            if not ures:
                if update.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(update.id)
                self.logger.error(
                    f"{server_id}: Failed to update showtimes data for {update.id}, reason: {umsg}"
                )

        await ctx.send(f"Berhasil menyimpan data baru untuk garapan **{matched_anime.title}**")


def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    bot.add_cog(ShowtimesAdmin(bot))
