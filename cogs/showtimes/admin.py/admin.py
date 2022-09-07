import logging
from typing import Dict, List, TypeVar

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.showtimes import Showtimes, ShowtimesAssignee, ShowtimesEpisodeStatus
from naotimes.utils import get_current_time
from naotimes.views import Selection

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

    @commands.command(name="delay", aliases=["alasandelay"])
    @commands.guild_only()
    async def _showadmin_alasandelay(self, ctx: naoTimesContext, alasan_delay: str, *, judul: str = None):
        server_id = ctx.guild.id
        self.logger.info(f"Requested delay reason at: {server_id}")
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)
        all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.info(f"{server_id}: found multiple matches!")
            selected_anime = await ctx.select_single(
                all_matches, lambda x: Selection(x.title, x.id), content="Pilih judul yang anda maksud!"
            )
            if selected_anime is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [selected_anime]

        matched_anime = all_matches[0]
        self.logger.info(f"{srv_data.id}: matched {matched_anime.title}")
        current_episode = matched_anime.get_current()
        if current_episode is None:
            return await ctx.send("Anime telah selesai digarap!")
        if not matched_anime.assignment.can_release(ctx.author) and not srv_data.is_admin(ctx.author):
            return await ctx.send("**Hanya administrator yang bisa menambah alasan delay episode ini**")

        message_check = (
            f"**{matched_anime.title}** #{current_episode.episode}\nAlasan delay: `{alasan_delay}`"
        )
        message_check += "\nApakah anda yakin?"
        do_commit = await ctx.confirm(message_check)
        if not do_commit:
            return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_id}-{matched_anime.title}: confirmed delay reason: {alasan_delay}")
        current_episode.delay_reason = alasan_delay
        matched_anime.status = current_episode
        srv_data.update_project(matched_anime)

        update_queue: List[Showtimes] = []
        update_queue.append(srv_data)
        for osrv in matched_anime.kolaborasi:
            if osrv == server_id:
                continue
            osrv_srv = await self.queue.fetch_database(osrv)
            if osrv_srv is None:
                continue
            osrv_project = osrv_srv.get_project(matched_anime)
            if osrv_project is None:
                continue
            osrv_project.status = current_episode
            osrv_srv.update_project(osrv_project)
            update_queue.append(osrv_srv)

        for peladen in update_queue:
            await self.queue.add_job(peladen)
        await ctx.send("Berhasil menambah alasan delay!", reference=ctx.message)

        for peladen in update_queue:
            self.logger.info(f"{peladen.id}: Updating database...")
            success, msg = await self.bot.ntdb.update_server(peladen)
            if not success:
                if peladen.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(peladen.id)
                self.logger.warning(f"{peladen.id}: Failed to update database: {msg}")
        self.logger.info(f"{server_id}: Finished updating database")

    @commands.command(name="hapusdelay", aliases=["hapusalasandelay"])
    @commands.guild_only()
    async def _showadmin_hapusalasandelay(self, ctx: naoTimesContext, *, judul: str = None):
        server_id = ctx.guild.id
        self.logger.info(f"Requested hapus delay reason at: {server_id}")
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

        if not judul:
            return await self.base.send_all_projects(ctx, srv_data)
        all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.info(f"{server_id}: found multiple matches!")
            selected_anime = await ctx.select_single(
                all_matches, lambda x: Selection(x.title, x.id), content="Pilih judul yang anda maksud!"
            )
            if selected_anime is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [selected_anime]

        matched_anime = all_matches[0]
        self.logger.info(f"{srv_data.id}: matched {matched_anime.title}")
        current_episode = matched_anime.get_current()
        if current_episode is None:
            return await ctx.send("Anime telah selesai digarap!")
        if not matched_anime.assignment.can_release(ctx.author) and not srv_data.is_admin(ctx.author):
            return await ctx.send("**Hanya administrator yang bisa menambah alasan delay episode ini**")

        message_check = f"**{matched_anime.title}** #{current_episode.episode}\nAlasan delay: *dihapus*"
        message_check += "\nApakah anda yakin?"
        do_commit = await ctx.confirm(message_check)
        if not do_commit:
            return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_id}-{matched_anime.title}: removed delay reason")
        current_episode.delay_reason = None
        matched_anime.status = current_episode
        srv_data.update_project(matched_anime)

        update_queue: List[Showtimes] = []
        update_queue.append(srv_data)
        for osrv in matched_anime.kolaborasi:
            if osrv == server_id:
                continue
            osrv_srv = await self.queue.fetch_database(osrv)
            if osrv_srv is None:
                continue
            osrv_project = osrv_srv.get_project(matched_anime)
            if osrv_project is None:
                continue
            osrv_project.status = current_episode
            osrv_srv.update_project(osrv_project)
            update_queue.append(osrv_srv)

        for peladen in update_queue:
            await self.queue.add_job(peladen)
        await ctx.send("Berhasil menambah alasan delay!", reference=ctx.message)

        for peladen in update_queue:
            self.logger.info(f"{peladen.id}: Updating database...")
            success, msg = await self.bot.ntdb.update_server(peladen)
            if not success:
                if peladen.id not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(peladen.id)
                self.logger.warning(f"{peladen.id}: Failed to update database: {msg}")
        self.logger.info(f"{server_id}: Finished updating database")

    @commands.command(name="ubahdata")
    @commands.guild_only()
    async def _showadmin_ubahdata(self, ctx: naoTimesContext, *, judul: str = None):
        guild: discord.Guild = ctx.guild
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
        all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, judul)
        if len(all_matches) < 1:
            self.logger.warning(f"{server_id}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(all_matches) > 1:
            self.logger.info(f"{server_id}: found multiple matches!")
            selected_anime = await ctx.select_single(
                all_matches, lambda x: Selection(x.title, x.id), content="Pilih judul yang anda maksud!"
            )
            if selected_anime is None:
                return await ctx.send("**Dibatalkan!**")
            all_matches = [selected_anime]

        matched_anime = all_matches[0]
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        all_stupid_role_used = map(
            lambda x: x.role, filter(lambda x: x.id != matched_anime.id, srv_data.projects)
        )
        all_stupid_role_used = list(filter(lambda x: isinstance(x, int), all_stupid_role_used))
        embed = discord.Embed(title="Mengubah data", color=0xEB79B9)
        embed.description = "Mempersiapkan proses..."
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®",
            icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        base_message = await ctx.send(embed=embed)

        def _is_original_author(m: discord.Message):
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
            embed = discord.Embed(title="Mengubah Staff", color=0xEB79B9)
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

            await_msg: discord.Message
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

                embed = discord.Embed(
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

                def _check_reaction(reaction: discord.Reaction, user: discord.Member):
                    return (
                        reaction.message.id == base_message.id
                        and user.id == ctx.author.id
                        and str(reaction.emoji) in EXTENDED_ANDYS
                    )

                res: discord.Reaction
                user: discord.Member
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
            embed = discord.Embed(title="Mengubah Role", color=0xEBA279)
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\nAtau ketik `auto` untuk membuatnya otomatis",
            )
            embed.set_footer(
                text="Dibawahkan oleh naoTimes™",
                icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await base_message.edit(embed=embed)

            await_msg: discord.Message
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
                                name=matched_anime.title, colour=discord.Colour.random(), mentionable=True
                            )
                            await await_msg.delete(no_log=True)
                            matched_anime.role = content_role
                        except (discord.Forbidden, discord.HTTPException):
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

            embed = discord.Embed(
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
            await_msg: discord.Message
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
            embed = discord.Embed(
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
            prompt_msg: discord.Message = None
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
            embed = discord.Embed(
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
            do_delete = await ctx.confirm(base_message, dont_remove=True)
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
            embed = discord.Embed(
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

            def _check_reaction(reaction: discord.Reaction, user: discord.Member):
                return (
                    reaction.message.id == base_message.id
                    and user.id == ctx.author.id
                    and reaction.emoji in REACT_ANDYS
                )

            res: discord.Reaction
            user: discord.Member
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
                    except (discord.Forbidden, discord.HTTPException):
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
                embed = discord.Embed(title=matched_anime.title, color=0xB51E1E)
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


async def setup(bot: naoTimesBot):
    ntdb = bot.ntdb
    if ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesAdmin(bot))
