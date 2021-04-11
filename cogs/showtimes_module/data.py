# -*- coding: utf-8 -*-

import logging
from copy import deepcopy
from functools import partial

import discord
from discord.ext import commands

from nthelper.bot import naoTimesBot
from nthelper.showtimes_helper import ShowtimesQueueData
from nthelper.utils import confirmation_dialog, get_current_time, send_timed_msg

from .base import ShowtimesBase, fetch_anilist

add_eps_instruct = """Jumlah yang dimaksud adalah jumlah yang ingin ditambahkan dari jumlah episode sekarang
Misal ketik `4` dan total jumlah episode sekarang adalah `12`
Maka total akan berubah menjadi `16` `(13, 14, 15, 16)`"""  # noqa: E501

del_eps_instruct = """Ranged number, bisa satu digit untuk 1 episode saja atau range dari episode x sampai y
Contoh: `4` untuk episode 4 saja || `4-6` untuk episode 4 sampai 6"""  # noqa: E501


class ShowtimesData(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesData, self).__init__()
        self.bot = bot
        self.ntdb = bot.ntdb
        self.showqueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, redisdb=bot.redisdb)
        self.srv_dumps = partial(self.dumps_showtimes, redisdb=bot.redisdb)
        self.logger = logging.getLogger("cogs.showtimes_module.data.ShowtimesData")
        self.fsdb_conn = bot.fsdb

    def __str__(self):
        return "Showtimes Data"

    @commands.command()
    @commands.guild_only()
    async def ubahdata(self, ctx, *, judul):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa mengubah data garapan.")

        propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])
        if not judul:
            return await self.send_all_projects(ctx, srv_data["anime"], server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = self.find_any_matches(judul, propagated_anilist)
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        matched_anime = matches[0]
        indx = matched_anime["index"]
        ani_title = matched_anime["name"] if matched_anime["type"] == "real" else matched_anime["real_name"]

        self.logger.info(f"{server_message}: matched {matched_anime}")
        program_info = srv_data["anime"][indx]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        def check_if_author(m):
            return m.author == ctx.message.author

        async def get_user_name(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return "{}#{}".format(user_data.name, user_data.discriminator)
            except (AttributeError, ValueError, TypeError):
                return "[Rahasia]"

        async def internal_change_staff(role, staff_list, emb_msg):
            better_names = {
                "TL": "Translator",
                "TLC": "TLCer",
                "ENC": "Encoder",
                "ED": "Editor",
                "TM": "Timer",
                "TS": "Typesetter",
                "QC": "Quality Checker",
            }
            self.logger.info(f"{ani_title}: changing {role}")
            embed = discord.Embed(title="Mengubah Staff", color=0xEB79B9)
            embed.add_field(
                name="{} ID".format(better_names[role]),
                value="Ketik ID {} atau mention orangnya".format(better_names[role]),
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        staff_list[role]["id"] = str(await_msg.content)
                        usr_ = await get_user_name(await_msg.content)
                        if usr_ == "[Rahasia]":
                            usr_ = None
                        else:
                            usr_split = usr_.split("#")
                            # Remove denominator
                            usr_ = "#".join(usr_split[:-1])
                        staff_list[role]["name"] = usr_
                        await await_msg.delete()
                        break
                else:
                    staff_list[role]["id"] = str(mentions[0].id)
                    usr_ = await get_user_name(str(mentions[0].id))
                    if usr_ == "[Rahasia]":
                        usr_ = None
                    staff_list[role]["name"] = usr_
                    await await_msg.delete()
                    break
            return staff_list, emb_msg

        async def ubah_staff(emb_msg):
            first_run = True
            self.logger.info(f"{ani_title}: processing staff.")
            while True:
                if first_run:
                    staff_list = deepcopy(program_info["assignments"])
                    staff_list_key = list(staff_list.keys())
                    first_run = False

                staff_list_name = {}
                for k, v in staff_list.items():
                    usr_ = await get_user_name(v["id"])
                    if usr_ == "[Rahasia]":
                        usr_ = None
                    else:
                        split_name = usr_.split("#")
                        if len(split_name) > 2:
                            usr_ = "#".join(split_name[:-1])
                    staff_list_name[k] = usr_

                embed = discord.Embed(
                    title="Mengubah Staff", description="Anime: {}".format(ani_title), color=0xEBA279,
                )
                embed.add_field(name="1⃣ TLor", value=staff_list_name["TL"], inline=False)
                embed.add_field(name="2⃣ TLCer", value=staff_list_name["TLC"], inline=False)
                embed.add_field(
                    name="3⃣ Encoder", value=staff_list_name["ENC"], inline=False,
                )
                embed.add_field(name="4⃣ Editor", value=staff_list_name["ED"], inline=True)
                embed.add_field(name="5⃣ Timer", value=staff_list_name["TM"], inline=True)
                embed.add_field(
                    name="6⃣ Typeseter", value=staff_list_name["TS"], inline=True,
                )
                embed.add_field(name="7⃣ QCer", value=staff_list_name["QC"], inline=True)
                embed.add_field(name="Lain-Lain", value="✅ Selesai!", inline=False)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "✅"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                else:
                    await emb_msg.clear_reactions()
                    reaction_pos = reactmoji.index(str(res.emoji))
                    staff_list, emb_msg = await internal_change_staff(
                        staff_list_key[reaction_pos], staff_list, emb_msg
                    )

            self.logger.info(f"{ani_title}: setting new staff.")
            program_info["assignments"] = staff_list
            if koleb_list:
                for other_srv in koleb_list:
                    osrv_data = await self.showqueue.fetch_database(other_srv)
                    if osrv_data is None:
                        continue
                    indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                    osrv_data["anime"][indx_other]["assignments"] = staff_list
                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))

            return emb_msg

        async def ubah_role(emb_msg):
            self.logger.info(f"{ani_title}: processing role.")
            embed = discord.Embed(title="Mengubah Role", color=0xEBA279)
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\n" "Atau ketik `auto` untuk membuatnya otomatis",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        program_info["role_id"] = str(await_msg.content)
                        await await_msg.delete()
                        break
                    if await_msg.content.startswith("auto"):
                        c_role = await ctx.message.guild.create_role(
                            name=ani_title, colour=discord.Colour.random(), mentionable=True,
                        )
                        program_info["role_id"] = str(c_role.id)
                        await await_msg.delete()
                        break
                else:
                    program_info["role_id"] = str(mentions[0].id)
                    await await_msg.delete()
                    break

            self.logger.info(f"{ani_title}: setting role...")
            role_ids = program_info["role_id"]
            await send_timed_msg(ctx, f"Berhasil menambah role ID ke {role_ids}", 2)

            return emb_msg

        async def tambah_episode(emb_msg):
            self.logger.info(f"{ani_title}: adding new episode...")
            status_list = program_info["status"]
            max_episode = status_list[-1]["episode"]
            anilist_data = await fetch_anilist(program_info["id"], 1, max_episode, True)
            time_data = anilist_data["time_data"]

            embed = discord.Embed(
                title="Menambah Episode",
                description="Jumlah Episode Sekarang: {}".format(max_episode),
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan jumlah episode yang diinginkan.", value=add_eps_instruct, inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if await_msg.content.isdigit():
                    jumlah_tambahan = int(await_msg.content)
                    await await_msg.delete()
                    break

            osrv_dumped = {}
            if koleb_list:
                for osrv in koleb_list:
                    osrv_data = await self.showqueue.fetch_database(osrv)
                    if osrv_data is None:
                        continue
                    osrv_dumped[osrv] = deepcopy(osrv_data)

            if (
                program_info["status"][-1]["is_done"]
                and "fsdb_data" in program_info
                and self.fsdb_conn is not None
            ):
                self.logger.info("Updating FSDB Project to on progress again.")
                if "id" in program_info["fsdb_data"]:
                    await self.fsdb_conn.update_project(program_info["fsdb_data"]["id"], "status", "Jalan")

            self.logger.info(f"{ani_title}: adding a total of {jumlah_tambahan}...")
            for x in range(
                int(max_episode) + 1, int(max_episode) + jumlah_tambahan + 1
            ):  # range(int(c), int(c)+int(x))
                st_data = {}
                staff_status = {}

                staff_status["TL"] = False
                staff_status["TLC"] = False
                staff_status["ENC"] = False
                staff_status["ED"] = False
                staff_status["TM"] = False
                staff_status["TS"] = False
                staff_status["QC"] = False

                st_data["is_done"] = False
                try:
                    st_data["airtime"] = time_data[x - 1]
                except IndexError:
                    pass
                st_data["progress"] = staff_status
                st_data["episode"] = x
                if osrv_dumped:
                    for osrv, osrv_data in osrv_dumped.items():
                        indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                        try:
                            osrv_data["anime"][indx_other]["status"].append(st_data)
                            osrv_dumped[osrv] = {"idx": indx_other, "data": osrv_data}
                        except (KeyError, IndexError):
                            continue
                program_info["status"].append(st_data)

            if osrv_dumped:
                for osrv, osrv_data in osrv_dumped.items():
                    osrv_data["data"]["anime"][osrv_data["idx"]]["last_update"] = self.get_unix()
                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data["data"], osrv))
            program_info["last_update"] = self.get_unix()

            await send_timed_msg(ctx, f"Berhasil menambah {jumlah_tambahan} episode baru", 2)

            return emb_msg

        async def hapus_episode(emb_msg):
            self.logger.info(f"{ani_title}: removing an episodes...")
            status_list = program_info["status"]
            max_episode = status_list[-1]["episode"]

            embed = discord.Embed(
                title="Menghapus Episode",
                description="Jumlah Episode Sekarang: {}".format(max_episode),
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan range episode yang ingin dihapus.", value=del_eps_instruct, inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                jumlah_tambahan = await_msg.content
                embed = discord.Embed(title="Menghapus Episode", color=0xEBA279)
                embed.add_field(
                    name="Apakah Yakin?", value="Range episode: **{}**".format(jumlah_tambahan), inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["✅", "❌"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await await_msg.delete()
                    await emb_msg.clear_reactions()
                    break
                elif "❌" in str(res.emoji):
                    await await_msg.delete()
                    embed = discord.Embed(
                        title="Menghapus Episode",
                        description="Jumlah Episode Sekarang: {}".format(max_episode),
                        color=0xEBA279,
                    )
                    embed.add_field(
                        name="Masukan range episode yang ingin dihapus.",
                        value=del_eps_instruct,
                        inline=False,
                    )
                    embed.set_footer(
                        text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                    )
                    await emb_msg.edit(embed=embed)
                await emb_msg.clear_reactions()

            total_episode = jumlah_tambahan.split("-")
            if len(total_episode) < 2:
                current = int(total_episode[0])
                total = int(total_episode[0])
            else:
                current = int(total_episode[0])
                total = int(total_episode[1])

            if current > max_episode:
                await send_timed_msg(
                    ctx, f"Angka tidak bisa lebih dari episode maksimum ({current} > {max_episode})", 2
                )
                return emb_msg
            if total > max_episode:
                await send_timed_msg(
                    ctx, f"Angka akhir tidak bisa lebih dari episode maksimum ({current} > {max_episode})", 2
                )
                return emb_msg

            if current > total:
                await send_timed_msg(
                    ctx, f"Angka awal tidak bisa lebih dari angka akhir ({current} > {total})", 2
                )
                return emb_msg

            self.logger.info(f"{ani_title}: removing a total of {total} episodes...")
            to_remove = []
            for x in range(current, total + 1):
                to_remove.append(str(x))

            new_statues_sets = []
            for status in status_list:
                if str(status["episode"]) not in to_remove:
                    new_statues_sets.append(status)

            if koleb_list:
                for osrv in koleb_list:
                    osrv_data = await self.showqueue.fetch_database(osrv)
                    if osrv_data is None:
                        continue
                    indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                    osrv_data["anime"][indx_other]["status"] = new_statues_sets
                    osrv_data["anime"][indx_other]["last_update"] = self.get_unix()
                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))

            program_info["status"] = new_statues_sets

            new_max_ep = new_statues_sets[-1]
            if new_max_ep["is_done"] and "fsdb_data" in program_info and self.fsdb_conn is not None:
                self.logger.info("Updating FSDB Project to finished.")
                if "id" in program_info["fsdb_data"]:
                    await self.fsdb_conn.update_project(program_info["fsdb_data"]["id"], "status", "Tamat")
            program_info["last_update"] = self.get_unix()

            await send_timed_msg(ctx, f"Berhasil menghapus episode {current} ke {total}", 2)

            return emb_msg

        async def hapus_utang_tanya(emb_msg):
            delete_ = False
            self.logger.info(f"{ani_title}: preparing to nuke project...")
            while True:
                embed = discord.Embed(
                    title="Menghapus Utang", description="Anime: {}".format(ani_title), color=0xCC1C20,
                )
                embed.add_field(
                    name="Peringatan!",
                    value="Utang akan dihapus selama-lamanya dan tidak bisa "
                    "dikembalikan!\nLanjutkan proses?",
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["✅", "❌"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    delete_ = True
                    break
                elif "❌" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                await emb_msg.clear_reactions()
            return emb_msg, delete_

        first_run = True
        exit_command = False
        hapus_utang = False
        while True:
            guild_roles = ctx.message.guild.roles
            total_episodes = len(program_info["status"])
            role_id = program_info["role_id"]
            embed = discord.Embed(
                title="Mengubah Data", description="Anime: {}".format(ani_title), color=0xE7E363,
            )
            embed.add_field(
                name="1⃣ Ubah Staff", value="Ubah staff yang mengerjakan anime ini.", inline=False,
            )
            embed.add_field(
                name="2⃣ Ubah Role",
                value="Ubah role discord yang digunakan:\n"
                "Role sekarang: {}".format(self.get_role_name(role_id, guild_roles)),
                inline=False,
            )
            embed.add_field(
                name="3⃣ Tambah Episode",
                value="Tambah jumlah episode\n" "Total Episode sekarang: {}".format(total_episodes),
                inline=False,
            )
            embed.add_field(
                name="4⃣ Hapus Episode", value="Hapus episode tertentu.", inline=False,
            )
            embed.add_field(
                name="5⃣ Drop Garapan",
                value="Menghapus garapan ini dari daftar utang untuk selama-lamanya...",
                inline=False,
            )
            embed.add_field(name="Lain-Lain", value="✅ Selesai!\n❌ Batalkan!", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                emb_msg = await ctx.send(embed=embed)
                first_run = False
            else:
                await emb_msg.edit(embed=embed)

            reactmoji = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "✅", "❌"]

            for react in reactmoji:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif reactmoji[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_staff(emb_msg)
            elif reactmoji[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_role(emb_msg)
            elif reactmoji[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await tambah_episode(emb_msg)
            elif reactmoji[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await hapus_episode(emb_msg)
            elif reactmoji[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg, hapus_utang = await hapus_utang_tanya(emb_msg)
                if hapus_utang:
                    await emb_msg.delete()
                    break
            elif reactmoji[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break
            elif reactmoji[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                exit_command = True
                break

        if exit_command:
            self.logger.warning(f"{ani_title}: cancelling...")
            return await ctx.send("**Dibatalkan!**")
        if hapus_utang:
            self.logger.warning(f"{ani_title}: nuking project...")
            if "fsdb_data" in program_info and self.fsdb_conn is not None:
                self.logger.info("Updating FSDB Project to dropped.")
                if "id" in program_info["fsdb_data"]:
                    await self.fsdb_conn.update_project(program_info["fsdb_data"]["id"], "status", "Drop")
            current = self.get_current_ep(program_info["status"])
            try:
                if not program_info["status"][0]["status"]:
                    announce_it = False
                elif not current:
                    announce_it = False
                else:
                    announce_it = True
            except KeyError:
                announce_it = True

            role_anime = program_info["role_id"]
            try:
                role_int_id = int(role_anime)
                self.logger.info(f"{ani_title}: Trying to remove role ID {role_int_id}")
                role_info = ctx.message.guild.get_role(role_int_id)
                if isinstance(role_info, discord.Role):
                    self.logger.info(
                        f"{ani_title}: Found role {role_int_id} with name {role_info.name}, deleting..."
                    )
                    try:
                        await role_info.delete()
                        self.logger.warning(f"{ani_title}:{role_int_id}: role removed!")
                    except (discord.Forbidden, discord.HTTPException):
                        self.logger.warning(
                            f"{ani_title}:{role_int_id}: failed to remove role, exception occured!"
                        )
            except (ValueError, IndexError, KeyError, AttributeError):
                pass

            srv_data["anime"].pop(indx)
            for osrv in koleb_list:
                osrv_data = await self.showqueue.fetch_database(osrv)
                if osrv_data is None:
                    continue
                indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                try:
                    progoinfo = osrv_data["anime"][indx_other]
                except IndexError:
                    continue
                if "kolaborasi" in progoinfo and server_message in progoinfo["kolaborasi"]:
                    try:
                        osrv_data["anime"][indx_other]["kolaborasi"].remove(server_message)
                    except ValueError:
                        pass
                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))

            await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
            self.logger.info(f"{ani_title}: storing final data...")
            await ctx.send("Berhasil menghapus **{}** dari daftar utang".format(ani_title))

            self.logger.info(f"{server_message}: updating database...")
            success, msg = await self.ntdb.update_data_server(server_message, srv_data)
            for osrv in koleb_list:
                if osrv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(osrv)
                if osrv_data is None:  # Skip if the server doesn't exist :pepega:
                    continue
                self.logger.info(f"{osrv}: updating database...")
                res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
                if not res2:
                    if osrv not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(osrv)
                    self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

            if not success:
                self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                if server_message not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(server_message)

            if "announce_channel" in srv_data and srv_data["announce_channel"]:
                announce_chan = srv_data["announce_channel"]
                try:
                    target_chan = self.bot.get_channel(int(announce_chan))
                except (AttributeError, ValueError, TypeError):
                    self.logger.warning(f"{ani_title}: failed to fetch announce channel, ignoring...")
                    return
                embed = discord.Embed(title=ani_title, color=0xB51E1E)
                embed.add_field(
                    name="Dropped...",
                    value="{} telah di drop dari fansub ini :(".format(ani_title),
                    inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                if announce_it:
                    self.logger.info(f"{server_message}: announcing removal of a project...")
                    if target_chan:
                        await target_chan.send(embed=embed)
            return

        self.logger.info(f"{ani_title}: saving new data...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            osrv_data = await self.showqueue.fetch_database(osrv)
            if osrv_data is None:  # Skip if the server doesn't exist :pepega:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send("Berhasil menyimpan data baru untuk garapan **{}**".format(ani_title))

    @commands.command(aliases=["addnew"])
    @commands.guild_only()
    async def tambahutang(self, ctx):
        """
        Membuat utang baru, ambil semua user id dan role id yang diperlukan.
        ----
        Menggunakan embed agar terlihat lebih enak dibanding sebelumnya
        Merupakan versi 2
        """
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa menambah utang")

        propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])
        srv_anilist = []
        srv_anilist_ids = []
        for anime in propagated_anilist:
            if anime["type"] == "real":
                srv_anilist.append(anime["name"])
                srv_anilist_ids.append(anime["id"])

        self.logger.info(f"{server_message}: creating initial data...")
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "ani_title": "",
            "anilist_id": "",
            "mal_id": "",
            "episodes": "",
            "time_data": "",
            "poster_img": "",
            "role_id": "",
            "role_generated": None,
            "tlor_id": "",
            "tlcer_id": "",
            "encoder_id": "",
            "editor_id": "",
            "timer_id": "",
            "tser_id": "",
            "qcer_id": "",
            "start_time": 0,
            "settings": {"time_data_are_the_same": False},
            "old_time_data": [],
        }
        cancel_toggled = False  # Some easy check if it's gonna fucked up
        first_time = True

        def check_if_author(m):
            return m.author == msg_author

        async def process_episode(table, emb_msg):
            self.logger.info(f"{server_message}: processing total episodes...")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name="Jumlah Episode", value="Ketik Jumlah Episode perkiraan", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            episode_content = None
            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if await_msg.content.isdigit():
                    episode_content = await_msg.content
                    try:
                        await await_msg.delete()
                    except discord.NotFound:
                        pass
                    break

                try:
                    await await_msg.delete()
                except discord.NotFound:
                    pass

            anilist_data = await fetch_anilist(table["anilist_id"], 1, int(episode_content), True)
            table["episodes"] = anilist_data["total_episodes"]
            table["time_data"] = anilist_data["time_data"]

            return table, emb_msg

        async def process_anilist(table, emb_msg):
            self.logger.info(f"{server_message}: processing anime data...")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.add_field(
                name="Anilist ID",
                value="Ketik ID Anilist untuk anime yang diinginkan\n\n"
                "Bisa gunakan `!anime <judul>` dan melihat bagian bawah "
                "untuk IDnya\n\nKetik *cancel* untuk membatalkan proses",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(content="", embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if not await_msg.content.startswith("!anime"):
                    if await_msg.content == ("cancel"):
                        return False, "Dibatalkan oleh user."

                    if await_msg.content.isdigit():
                        if await_msg.content in srv_anilist_ids:
                            await send_timed_msg(ctx, "ID Anime tersebut sudah terdaftar!", 2)
                        else:
                            break
                    else:
                        await send_timed_msg(ctx, "Mohon masukan angka!", 2)

            try:
                anilist_data = await fetch_anilist(await_msg.content, 1, 1, True)
            except Exception:  # skipcq: PYL-W0703
                self.logger.warning(f"{server_message}: failed to fetch air start, please try again later.")
                return (
                    False,
                    "Gagal mendapatkan waktu mulai tayang, silakan coba lagi ketika sudah "
                    "ada kepastian kapan animenya mulai.",
                )
            poster_data, title = anilist_data["poster_data"], anilist_data["title"]
            time_data, episodes_total = anilist_data["time_data"], anilist_data["total_episodes"]
            poster_image, poster_color = poster_data["image"], poster_data["color"]

            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=poster_image)
            embed.add_field(
                name="Apakah benar?", value="Judul: **{}**".format(title), inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            to_react = ["✅", "❌"]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                try:
                    ani_air_data = await fetch_anilist(await_msg.content, 1, 1, return_only_time=True)
                    start_time = ani_air_data["airing_start"]
                except Exception:  # skipcq: PYL-W0703
                    self.logger.warning(
                        f"{server_message}: failed to fetch air start, please try again later."
                    )
                    return (
                        False,
                        "Gagal mendapatkan waktu mulai tayang, silakan coba lagi ketika sudah "
                        "ada kepastian kapan animenya mulai.",
                    )
                table["ani_title"] = title
                table["poster_data"] = {
                    "url": poster_image,
                    "color": poster_color,
                }
                table["anilist_id"] = str(await_msg.content)
                table["mal_id"] = str(anilist_data["idMal"])
                table["start_time"] = start_time
                await emb_msg.clear_reactions()
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                return False, "Dibatalkan oleh user."

            if episodes_total == 1:
                self.logger.info(f"{server_message}: asking episode total to user...")
                table, emb_msg = await process_episode(table, emb_msg)
            else:
                self.logger.info(f"{server_message}: using anilist episode total...")
                table["episodes"] = episodes_total
                table["time_data"] = time_data

            return table, emb_msg

        async def process_role(table, emb_msg):
            self.logger.info(f"{server_message}: processing roles")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\n" "Atau ketik `auto` untuk membuatnya otomatis",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                mentions = await_msg.role_mentions

                should_break = False
                if not mentions:
                    if await_msg.content.isdigit():
                        table["role_id"] = await_msg.content
                        await await_msg.delete()
                    elif await_msg.content.startswith("auto"):
                        self.logger.info(f"{server_message}: auto-generating role...")
                        try:
                            c_role = await ctx.message.guild.create_role(
                                name=table["ani_title"], colour=discord.Colour.random(), mentionable=True,
                            )
                            table["role_generated"] = c_role
                            table["role_id"] = str(c_role.id)
                            should_break = True
                        except discord.Forbidden:
                            await send_timed_msg(
                                ctx, "Tidak dapat membuat role karena bot tidak ada akses `Manage Roles`", 3
                            )
                        except discord.HTTPException:
                            await send_timed_msg(
                                ctx, "Terjadi kesalahan ketika menghubungi Discord, mohon coba lagi!", 3
                            )
                        await await_msg.delete()
                else:
                    table["role_id"] = mentions[0].id
                    await await_msg.delete()
                    should_break = True
                if should_break:
                    break

            return table, emb_msg

        async def process_staff(table, emb_msg, staffer):
            staffer_mapping = {
                "tl": {"b": "tlor_id", "n": "Translator"},
                "tlc": {"b": "tlcer_id", "n": "TLCer"},
                "enc": {"b": "encoder_id", "n": "Encoder"},
                "ed": {"b": "editor_id", "n": "Editor"},
                "ts": {"b": "tser_id", "n": "Penata Rias"},
                "tm": {"b": "timer_id", "n": "Penata Waktu"},
                "qc": {"b": "qcer_id", "n": "Pemeriksa Akhir"},
            }
            staff_need = staffer_mapping.get(staffer)
            staff_name, table_map = staff_need["n"], staff_need["b"]
            self.logger.info(f"{server_message}: processing {staff_name}")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name=f"{staff_name} ID",
                value=f"Ketik ID Discord {staff_name} atau mention orangnya",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table[table_map] = await_msg.content
                        await await_msg.delete()
                        break
                else:
                    table[table_map] = mentions[0].id
                    await await_msg.delete()
                    break
                # await await_msg.delete()

            return table, emb_msg

        def check_setting(gear):
            if not gear:
                return "❌"
            return "✅"

        async def process_pengaturan(table, emb_msg):
            # Inner settings
            async def gear_1(table, emb_msg, gear_data):
                self.logger.info("pengaturan: setting all time data to be the same.")
                if not gear_data:
                    table["old_time_data"] = table["time_data"]  # Make sure old time data are not deleted
                    time_table = table["time_data"]
                    new_time_table = []
                    for _ in time_table:
                        new_time_table.append(time_table[0])

                    table["time_data"] = new_time_table
                    table["settings"]["time_data_are_the_same"] = True
                    return table, emb_msg

                new_time_table = []
                for i, _ in enumerate(table["time_data"]):
                    new_time_table.append(table["old_time_data"][i])

                # Remove old time data because it resetted
                table["old_time_data"] = []
                table["settings"]["time_data_are_the_same"] = False
                return table, emb_msg

            self.logger.info("showing settings...")
            while True:
                embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
                embed.set_thumbnail(url=table["poster_img"])
                embed.add_field(
                    name="1⃣ Samakan waktu tayang",
                    value="Status: **{}**\n\nBerguna untuk anime Netflix yang sekali rilis banyak".format(  # noqa: E501
                        check_setting(table["settings"]["time_data_are_the_same"])
                    ),
                    inline=False,
                )
                embed.add_field(name="Lain-Lain", value="⏪ Kembali", inline=False)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                to_react = [
                    "1⃣",
                    "⏪",
                ]
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif to_react[0] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    table, emb_msg = await gear_1(
                        table, emb_msg, table["settings"]["time_data_are_the_same"],
                    )
                elif to_react[-1] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    return table, emb_msg

        json_tables, emb_msg = await process_anilist(json_tables, emb_msg)

        if not json_tables:
            self.logger.warning(f"{server_message}: process cancelled")
            return await ctx.send(emb_msg)

        if json_tables["ani_title"] in srv_anilist:
            self.logger.warning(f"{server_message}: anime already registered on database.")
            return await ctx.send("Anime sudah didaftarkan di database.")

        json_tables, emb_msg = await process_role(json_tables, emb_msg)
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tl")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tlc")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "enc")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ed")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tm")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ts")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "qc")

        async def fetch_username_from_id(_id):
            try:
                user_data = self.bot.get_user(int(_id))
                return "{}#{}".format(user_data.name, user_data.discriminator), True
            except (AttributeError, ValueError, TypeError):
                return "[Rahasia]", False

        self.logger.info(f"{server_message}: checkpoint before commiting")
        valid_users = []
        while True:
            tl_, tl_success = await fetch_username_from_id(json_tables["tlor_id"])
            tlc_, tlc_success = await fetch_username_from_id(json_tables["tlcer_id"])
            enc_, enc_success = await fetch_username_from_id(json_tables["encoder_id"])
            ed_, ed_success = await fetch_username_from_id(json_tables["editor_id"])
            tm_, tm_success = await fetch_username_from_id(json_tables["timer_id"])
            ts_, ts_success = await fetch_username_from_id(json_tables["tser_id"])
            qc_, qc_success = await fetch_username_from_id(json_tables["qcer_id"])

            embed = discord.Embed(
                title="Menambah Utang", description="Periksa data!\nReact jika ingin diubah.", color=0xE7E363,
            )
            embed.set_thumbnail(url=json_tables["poster_img"])
            embed.add_field(
                name="1⃣ Judul",
                value="{} ({})".format(json_tables["ani_title"], json_tables["anilist_id"]),
                inline=False,
            )
            embed.add_field(
                name="2⃣ Episode", value="{}".format(json_tables["episodes"]), inline=False,
            )
            embed.add_field(
                name="3⃣ Role",
                value="{}".format(self.get_role_name(json_tables["role_id"], ctx.message.guild.roles)),
                inline=False,
            )
            embed.add_field(name="4⃣ Translator", value=tl_, inline=True)
            embed.add_field(name="5⃣ TLCer", value=tlc_, inline=True)
            embed.add_field(name="6⃣ Encoder", value=enc_, inline=True)
            embed.add_field(name="7⃣ Editor", value=ed_, inline=True)
            embed.add_field(name="8⃣ Timer", value=tm_, inline=True)
            embed.add_field(name="9⃣ Typesetter", value=ts_, inline=True)
            embed.add_field(name="0⃣ Quality Checker", value=qc_, inline=True)
            embed.add_field(
                name="Lain-Lain", value="🔐 Pengaturan\n✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = [
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
                "🔐",
                "✅",
                "❌",
            ]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_anilist(json_tables, emb_msg)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_episode(json_tables, emb_msg)
            elif to_react[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_role(json_tables, emb_msg)
            elif to_react[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tl")
            elif to_react[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tlc")
            elif to_react[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "enc")
            elif to_react[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ed")
            elif to_react[7] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tm")
            if to_react[8] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ts")
            elif to_react[9] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "qc")
            elif "🔐" in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_pengaturan(json_tables, emb_msg)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                if tl_success and json_tables["tlor_id"] not in valid_users:
                    valid_users.append(json_tables["tlor_id"])
                if tlc_success and json_tables["tlcer_id"] not in valid_users:
                    valid_users.append(json_tables["tlcer_id"])
                if enc_success and json_tables["encoder_id"] not in valid_users:
                    valid_users.append(json_tables["encoder_id"])
                if ed_success and json_tables["editor_id"] not in valid_users:
                    valid_users.append(json_tables["editor_id"])
                if tm_success and json_tables["timer_id"] not in valid_users:
                    valid_users.append(json_tables["timer_id"])
                if ts_success and json_tables["tser_id"] not in valid_users:
                    valid_users.append(json_tables["tser_id"])
                if qc_success and json_tables["qcer_id"] not in valid_users:
                    valid_users.append(json_tables["qcer_id"])
                break
            elif "❌" in str(res.emoji):
                self.logger.warning(f"{server_message}: process cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        # Everything are done and now processing data
        self.logger.info(f"{server_message}: commiting data to database...")
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        gen_all_success = True
        current_guild: discord.Guild = ctx.message.guild
        if isinstance(json_tables["role_generated"], discord.Role):
            gen_roles: discord.Role = json_tables["role_generated"]
            for member in valid_users:
                if current_guild:
                    self.logger.info(f"Auto-adding auto-generated role to {member}")
                    try:
                        member_sel: discord.Member = current_guild.get_member(int(member))
                        if not member_sel:
                            self.logger.warning(f"Cannot add the auto-role to {member}, can't find the user.")
                            continue
                        await member_sel.add_roles(gen_roles, reason="Auto add by Bot for tambahutang!")
                    except (discord.Forbidden, discord.HTTPException):
                        gen_all_success = False
                        self.logger.error(f"Gagal menambah role ke user {member}")
        else:
            if current_guild:
                rr_id = int(json_tables["role_id"])
                real_roles: discord.Role = current_guild.get_role(rr_id)
                if real_roles:
                    for member in valid_users:
                        self.logger.info(f"Auto-adding role to {member}")
                        try:
                            member_sel: discord.Member = current_guild.get_member(int(member))
                            if not member_sel:
                                self.logger.warning(f"Cannot add the role to {member}, can't find the user.")
                                continue
                            rr_exist = False
                            for role in member_sel.roles:
                                if role.id == rr_id:
                                    self.logger.warning(f"Role already exist for member {member}")
                                    rr_exist = True
                                    break
                            if not rr_exist:
                                await member_sel.add_roles(
                                    real_roles, reason="Auto add by Bot for tambahutang!"
                                )
                        except (discord.Forbidden, discord.HTTPException):
                            gen_all_success = False
                            self.logger.error(f"Gagal menambah role ke user {member}")

        new_anime_data = {}
        staff_data = {}
        status = []

        new_anime_data["id"] = str(json_tables["anilist_id"])
        new_anime_data["mal_id"] = str(json_tables["mal_id"])
        new_anime_data["title"] = json_tables["ani_title"]
        new_anime_data["last_update"] = self.get_unix()
        new_anime_data["role_id"] = str(json_tables["role_id"])
        new_anime_data["poster_data"] = json_tables["poster_data"]
        new_anime_data["start_time"] = int(json_tables["start_time"])

        def get_username_of_user(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return user_data.name
            except AttributeError:
                return None

        staff_data["TL"] = {
            "id": str(json_tables["tlor_id"]),
            "name": get_username_of_user(json_tables["tlor_id"]),
        }
        staff_data["TLC"] = {
            "id": str(json_tables["tlcer_id"]),
            "name": get_username_of_user(json_tables["tlcer_id"]),
        }
        staff_data["ENC"] = {
            "id": str(json_tables["encoder_id"]),
            "name": get_username_of_user(json_tables["encoder_id"]),
        }
        staff_data["ED"] = {
            "id": str(json_tables["editor_id"]),
            "name": get_username_of_user(json_tables["editor_id"]),
        }
        staff_data["TM"] = {
            "id": str(json_tables["timer_id"]),
            "name": get_username_of_user(json_tables["timer_id"]),
        }
        staff_data["TS"] = {
            "id": str(json_tables["tser_id"]),
            "name": get_username_of_user(json_tables["tser_id"]),
        }
        staff_data["QC"] = {
            "id": str(json_tables["qcer_id"]),
            "name": get_username_of_user(json_tables["qcer_id"]),
        }
        new_anime_data["assignments"] = staff_data

        self.logger.info(f"{server_message}: generating episode...")
        for x in range(int(json_tables["episodes"])):
            st_data = {}
            staff_status = {}

            staff_status["TL"] = False
            staff_status["TLC"] = False
            staff_status["ENC"] = False
            staff_status["ED"] = False
            staff_status["TM"] = False
            staff_status["TS"] = False
            staff_status["QC"] = False

            st_data["is_done"] = False
            st_data["airtime"] = json_tables["time_data"][x]
            st_data["progress"] = staff_status
            st_data["episode"] = x + 1
            status.append(st_data)

        new_anime_data["status"] = status
        new_anime_data["aliases"] = []
        new_anime_data["kolaborasi"] = []

        if "fsdb_id" in srv_data and self.fsdb_conn is not None:
            embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
            embed.add_field(name="Memproses!", value="Membuat data fansubdb...", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)
            collect_anime_dataset = await self.fsdb_conn.fetch_animes()
            collect_anime_dataset.sort(key=lambda x: x["mal_id"])
            fansubs_projects, _ = await self.fsdb_conn.fetch_fansub_projects(srv_data["fsdb_id"])
            existing_projects = {str(data["anime"]["mal_id"]): data["id"] for data in fansubs_projects}

            mal_id = new_anime_data["mal_id"]
            fsani_data = await self.split_search_id(collect_anime_dataset, "mal_id", int(mal_id))
            if fsani_data is None:
                _, fsani_id = await self.fsdb_conn.import_mal(int(mal_id))
                _, fsproject_id = await self.fsdb_conn.add_new_project(fsani_id, srv_data["fsdb_id"])
                new_anime_data["fsdb_data"] = {"id": fsproject_id, "ani_id": fsani_id}
            else:
                fsani_id = fsani_data["id"]
                if str(new_anime_data["mal_id"]) in existing_projects:
                    new_anime_data["fsdb_data"] = {
                        "id": existing_projects[str(new_anime_data["mal_id"])],
                        "ani_id": fsani_id,
                    }
                else:
                    _, fsproject_id = await self.fsdb_conn.add_new_project(fsani_id, srv_data["fsdb_id"])
                    new_anime_data["fsdb_data"] = {"id": fsproject_id, "ani_id": fsani_id}

        srv_data["anime"].append(new_anime_data)

        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}: saving to local database...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="**{}** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                json_tables["ani_title"]
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        await emb_msg.delete()

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        self.logger.info(f"{server_message}: done processing!")
        await ctx.send(
            "Berhasil menambahkan **{}** ke dalam database utama naoTimes".format(  # noqa: E501
                json_tables["ani_title"]
            )
        )

        if gen_all_success:
            await ctx.send("Bot telah otomatis menambah role ke member garapan, mohon cek!")

    @commands.command(name="showui")
    async def _show_ui_cmd(self, ctx: commands.Context, guild_id: str = None):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return

        server_message = guild_id
        using_guild_id = True
        if server_message is None:
            try:
                server_message = str(ctx.message.guild.id)
                using_guild_id = False
            except AttributeError:
                return await ctx.send(
                    "Mohon jalankan di server, atau berikan ID server!\n"
                    f"Contoh: `{self.bot.prefixes(ctx)}showui xxxxxxxxxxx`"
                )

        self.logger.info(f"requesting {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)
        if srv_data is None:
            self.logger.info("cannot find the server in database")
            if using_guild_id:
                await ctx.send(f"Tidak dapat menemukan ID `{server_message}` di database naoTimes!")
            return

        author = ctx.message.author.id
        srv_owner = srv_data["serverowner"]
        if str(author) not in srv_owner:
            self.logger.warning(f"User {author} are unauthorized to create a new database")
            return await ctx.send("Tidak berhak untuk melihat password, hanya Admin yang terdaftar yang bisa")

        self.logger.info("Making new login info!")
        do_continue = await confirmation_dialog(
            self.bot, ctx, "Perintah ini akan memperlihatkan kode rahasia untuk login di WebUI, lanjutkan?"
        )
        if not do_continue:
            return

        _, return_msg = await self.ntdb.generate_login_info(server_message)
        await ctx.send(return_msg)
