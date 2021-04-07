# -*- coding: utf-8 -*-

import logging

import discord
from discord.ext import commands, tasks
from discord.embeds import EmptyEmbed

from nthelper.bot import naoTimesBot
from nthelper.showtimes_helper import ShowtimesQueueData
from nthelper.utils import get_current_time

from .base import ShowtimesBase


class ShowtimesStaff(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesStaff, self).__init__()
        self.bot = bot
        self.showqueue = bot.showqueue
        self.ntdb = bot.ntdb
        self.fsdb = bot.fsdb
        # pylint: disable=E1101
        self.resync_failed_server.start()
        self.logger = logging.getLogger("cogs.showtimes_module.staff.ShowtimesStaff")
        # pylint: enable=E1101
        # self.task = asyncio.Task(self.resync_failure())

    def __str__(self):
        return "Showtimes Staff"

    def cog_unload(self):
        self.logger.info("Cancelling all tasks...")
        self.resync_failed_server.cancel()

    @tasks.loop(minutes=1.0)
    async def resync_failed_server(self):
        if not self.bot.showtimes_resync:
            return
        self.logger.info("trying to resynchronizing...")
        for srv in self.bot.showtimes_resync:
            self.logger.info(f"updating: {srv}")
            srv_data = await self.showqueue.fetch_database(srv)
            res, msg = await self.ntdb.update_data_server(srv, srv_data)
            if not res:
                self.logger.error(f"\tFailed to update, reason: {msg}")
                continue
            self.logger.info(f"{srv}: updated!")
            self.bot.showtimes_resync.remove(srv)
        lefts = len(self.bot.showtimes_resync)
        self.logger.info(f"done! leftover to resync are {lefts} server")

    @commands.command(aliases=["release"])
    @commands.guild_only()
    async def rilis(self, ctx, *, data):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        data = data.split()

        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
        propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])

        if len(propagated_anilist) < 1:
            self.logger.warning(f"{server_message}: no registered data on database.")
            return await ctx.send("**Tidak ada anime yang terdaftar di database**")

        if not data:
            return await self.send_all_projects(ctx, srv_data["anime"], server_message)

        koleb_list = []
        osrv_dumped = {}

        should_update_fsdb = False
        fsdb_update_to = "Tentatif"
        if data[0] not in ["batch", "semua"]:
            self.logger.info(f"{server_message}: using normal mode.")

            judul = " ".join(data)

            if judul == " " or judul == "" or judul == "   " or not judul:
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
            ani_title = (
                matched_anime["name"] if matched_anime["type"] == "real" else matched_anime["real_name"]
            )

            self.logger.info(f"{server_message}: matched {matched_anime}")
            program_info = srv_data["anime"][indx]
            status_list = program_info["status"]

            if "kolaborasi" in program_info:
                koleb_data = program_info["kolaborasi"]
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            current = self.get_current_ep(status_list)
            episode_set = status_list[0]
            if not current:
                self.logger.warning(f"{ani_title}: no episode left to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if current["episode"] == episode_set["episode"]:
                should_update_fsdb = True
                fsdb_update_to = "Jalan"

            if (
                str(ctx.message.author.id) != program_info["assignments"]["QC"]["id"]
                and str(ctx.message.author.id) not in srv_owner
            ):
                self.logger.warning(f"{ani_title}: user not allowed.")
                return await ctx.send("**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**")

            if koleb_list:
                self.logger.info(f"{ani_title}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.showqueue.fetch_database(other_srv)
                    if srv_o_data is None:
                        continue
                    self.logger.debug(f"{server_message}: {other_srv} processing...")
                    indx_other = self._search_data_index(srv_o_data["anime"], "id", program_info["id"])
                    progoinfo = srv_o_data["anime"][indx_other]
                    indxo_ep = self._search_data_index(progoinfo["status"], "episode", current["episode"])
                    srv_o_data["anime"][indx_other]["status"][indxo_ep]["is_done"] = True
                    srv_o_data["anime"][indx_other]["last_update"] = self.get_unix()
                    await self.showqueue.add_job(ShowtimesQueueData(srv_o_data, other_srv))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{ani_title}: setting status...")
            current["is_done"] = True
            program_info["last_update"] = self.get_unix()

            text_data = "**{} - #{}** telah dirilis".format(ani_title, current["episode"])
            embed_text_data = "{} #{} telah dirilis!".format(ani_title, current["episode"])
        elif data[0] == "batch":
            self.logger.info(f"{server_message}: using batch mode.")
            if not data[1].isdigit():
                await self.send_all_projects(ctx, srv_data["anime"], server_message)
                return await ctx.send("Lalu tulis jumlah terlebih dahulu baru judul")
            if len(data) < 3:
                return await self.send_all_projects(ctx, srv_data["anime"], server_message)

            jumlah = data[1]
            judul = " ".join(data[2:])

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
            ani_title = (
                matched_anime["name"] if matched_anime["type"] == "real" else matched_anime["real_name"]
            )
            self.logger.info(f"{server_message}: matched {matched_anime}")

            program_info = srv_data["anime"][indx]
            status_list = program_info["status"]

            if "kolaborasi" in program_info:
                koleb_data = program_info["kolaborasi"]
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            current = self.get_current_ep(status_list)
            if not current:
                self.logger.warning(f"{ani_title}: no episode left to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")
            indx_ep = self._search_data_index(status_list, "episode", current["episode"])

            if (
                str(ctx.message.author.id) != program_info["assignments"]["QC"]["id"]
                and str(ctx.message.author.id) not in srv_owner
            ):
                self.logger.warning(f"{ani_title}: user not allowed.")
                return await ctx.send("**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**")

            if koleb_list:
                self.logger.info(f"{ani_title}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.showqueue.fetch_database(other_srv)
                    if srv_o_data is None:
                        continue
                    self.logger.debug(f"{server_message}: {other_srv} processing...")
                    indx_other = self._search_data_index(srv_o_data["anime"], "id", program_info["id"])
                    progoinfo = srv_o_data["anime"][indx_other]
                    indxo_ep = self._search_data_index(progoinfo["status"], "episode", current["episode"])
                    for x in range(indxo_ep, indxo_ep + int(jumlah)):  # range(int(c), int(c)+int(x))
                        try:
                            srv_o_data["anime"][indx_other]["status"][x]["is_done"] = True
                        except IndexError:
                            break
                    srv_o_data["anime"][indx_other]["last_update"] = self.get_unix()
                    await self.showqueue.add_job(ShowtimesQueueData(srv_o_data, other_srv))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{ani_title}: setting status...")
            last_ep_tick = current["episode"]
            for x in range(indx_ep, indx_ep + int(jumlah)):  # range(int(c), int(c)+int(x))
                try:
                    program_info["status"][x]["is_done"] = True
                    last_ep_tick = program_info["status"][x]["episode"]
                except IndexError:
                    break

            should_update_fsdb = True
            fsdb_update_to = "Jalan"
            last_ep = len(status_list) - 1
            if indx_ep + int(jumlah) >= last_ep:
                fsdb_update_to = "Tamat"

            program_info["last_update"] = self.get_unix()

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(
                ani_title, current["episode"], last_ep_tick
            )
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(
                ani_title, current["episode"], last_ep_tick
            )
        elif data[0] == "semua":
            should_update_fsdb = True
            fsdb_update_to = "Tamat"
            self.logger.info(f"{server_message}: using all mode.")
            judul = " ".join(data[1:])

            if judul == " " or judul == "" or judul == "   " or not judul:
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
            ani_title = (
                matched_anime["name"] if matched_anime["type"] == "real" else matched_anime["real_name"]
            )

            self.logger.info(f"{server_message}: matched {matched_anime}")
            program_info = srv_data["anime"][indx]
            status_list = program_info["status"]

            if "kolaborasi" in program_info:
                koleb_data = program_info["kolaborasi"]
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            all_status = self.get_not_released_ep(status_list)
            if not all_status:
                self.logger.warning(f"{ani_title}: no episode left to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if (
                str(ctx.message.author.id) != program_info["assignments"]["QC"]["id"]
                and str(ctx.message.author.id) not in srv_owner
            ):
                self.logger.warning(f"{ani_title}: user not allowed.")
                return await ctx.send("**Tidak secepat itu ferguso, yang bisa rilis cuma admin atau QCer**")

            if koleb_list:
                self.logger.info(f"{ani_title}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.showqueue.fetch_database(other_srv)
                    if srv_o_data is None:
                        continue
                    self.logger.debug(f"{server_message}: {other_srv} processing...")
                    indx_other = self._search_data_index(srv_o_data["anime"], "id", program_info["id"])
                    progoinfo = srv_o_data["anime"][indx_other]
                    alls_other = self.get_not_released_ep(status_list)
                    for ep_other in alls_other:
                        ep_other["is_done"] = True
                    progoinfo["last_update"] = self.get_unix()
                    await self.showqueue.add_job(ShowtimesQueueData(srv_o_data, other_srv))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{ani_title}: setting status...")
            for ep_stat in all_status:
                ep_stat["is_done"] = True

            program_info["last_update"] = self.get_unix()

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(
                ani_title, all_status[0]["episode"], all_status[-1]["episode"]
            )
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(
                ani_title, all_status[0]["episode"], all_status[-1]["episode"]
            )

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{server_message}: sending message")
        await ctx.send(text_data)

        if "fsdb_data" in program_info and should_update_fsdb and self.fsdb is not None:
            self.logger.info("Re-Updating back FSDB project to Not done.")
            fsdb_data = program_info["fsdb_data"]
            if "id" in fsdb_data and fsdb_data["id"] is not None:
                await self.fsdb.update_project(fsdb_data["id"], "status", fsdb_update_to)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            self.logger.info(f"{osrv}: updating collab server...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            if "announce_channel" in osrv_data and osrv_data["announce_channel"]:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                try:
                    announce_chan = int(announce_chan)
                except (AttributeError, ValueError, TypeError):
                    self.logger.warning(f"{osrv}: failed to convert announce channel to integer, ignoring...")
                    continue
                target_chan = self.bot.get_channel(announce_chan)
                if not target_chan:
                    self.logger.warning(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title=ani_title, color=0x1EB5A6)
                embed.add_field(name="Rilis!", value=embed_text_data, inline=False)
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        if "announce_channel" in srv_data and srv_data["announce_channel"]:
            self.logger.info(f"{server_message}: sending progress to everyone...")
            announce_chan = srv_data["announce_channel"]
            try:
                announce_chan = int(announce_chan)
            except (AttributeError, ValueError, TypeError):
                self.logger.warning(
                    f"{server_message}: failed to convert announce channel to integer, ignoring..."
                )
                return
            target_chan = self.bot.get_channel(announce_chan)
            embed = discord.Embed(title=ani_title, color=0x1EB5A6)
            embed.add_field(name="Rilis!", value=embed_text_data, inline=False)
            embed.set_footer(text=f"Pada: {get_current_time()}")
            if target_chan:
                await target_chan.send(embed=embed)

    @commands.command(aliases=["done"])
    async def beres(self, ctx, posisi: str, *, judul: str):
        """
        Menyilang salah satu tugas pendelay
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        posisi, posisi_asli = await self.get_roles(posisi)
        if posisi is None:
            self.logger.warning("unknown position.")
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
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
        status_list = program_info["status"]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        try:
            if (
                not self.check_role(program_info["role_id"], ctx.message.author.roles)
                and str(ctx.message.author.id) not in srv_owner
            ):
                return
        except ValueError:
            return await ctx.send(
                f"Gagal memeriksa role, mohon ubah dengan {self.bot.prefix}ubahdata {ani_title}"
            )

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warning(f"{ani_title}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        current_stat = current["progress"][posisi]
        if current_stat:
            self.logger.warning(f"{ani_title}: position already set to done.")
            return await ctx.send(f"**{posisi_asli}** sudah ditandakan sebagai beres.")

        poster_data = program_info["poster_data"]
        poster_image = poster_data["url"]

        if (
            str(ctx.message.author.id) != str(program_info["assignments"][posisi]["id"])
            and str(ctx.message.author.id) not in srv_owner
        ):
            self.logger.warning(f"{ani_title}: no access to set to done.")
            return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        self.logger.info(f"{ani_title}: setting episode {current} to done.")
        current["progress"][posisi] = True
        program_info["last_update"] = self.get_unix()
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                progoinfo = osrv_data["anime"][indx_other]
                indxo_ep = self._search_data_index(progoinfo["status"], "episode", current["episode"])
                osrv_data["anime"][indx_other]["status"][indxo_ep]["progress"][posisi] = True
                osrv_data["anime"][indx_other]["last_update"] = self.get_unix()
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        current_ep_status = current["progress"]

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{ani_title}: sending progress info to staff...")
        await ctx.send("Berhasil mengubah status garapan {} - #{}".format(ani_title, current["episode"]))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
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

        if osrv_dumped:
            for osrv, osrv_data in osrv_dumped.items():
                if osrv == server_message:
                    continue
                if "announce_channel" in osrv_data and osrv_data["announce_channel"]:
                    self.logger.info(f"{osrv}: sending progress to everyone...")
                    announce_chan = osrv_data["announce_channel"]
                    try:
                        announce_chan = int(announce_chan)
                    except (AttributeError, ValueError, TypeError):
                        self.logger.warning(
                            f"{osrv}: failed to convert announce channel to integer, ignoring..."
                        )
                        continue
                    target_chan = self.bot.get_channel(announce_chan)
                    if not target_chan:
                        self.logger.warning(f"{announce_chan}: unknown channel.")
                        continue
                    embed = discord.Embed(
                        title="{} - #{}".format(ani_title, current["episode"]), color=0x1EB5A6
                    )
                    embed.description = f"✅ {self.normalize_role_to_name(posisi)}"
                    embed.add_field(
                        name="Status", value=self.parse_status(current_ep_status), inline=False,
                    )
                    embed.set_footer(text=f"Pada: {get_current_time()}")
                    await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(ani_title, current["episode"]), color=0x1EB5A6)
        embed.add_field(
            name="Status", value=self.parse_status(current_ep_status), inline=False,
        )
        if "announce_channel" in srv_data and srv_data["announce_channel"]:
            announce_chan = srv_data["announce_channel"]
            try:
                announce_chan = int(announce_chan)
            except (AttributeError, ValueError, TypeError):
                self.logger.warning(
                    f"{server_message}: failed to convert announce channel to integer, ignoring..."
                )
                announce_chan = -1
            target_chan = self.bot.get_channel(announce_chan)
            embed.description = f"✅ {self.normalize_role_to_name(posisi)}"
            embed.set_footer(text=f"Pada: {get_current_time()}")
            self.logger.info(f"{server_message}: sending progress to everyone...")
            if target_chan:
                await target_chan.send(embed=embed)
        embed.description = EmptyEmbed
        embed.add_field(name="Update Terakhir", value="Baru saja", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        embed.set_thumbnail(url=poster_image)
        return await ctx.send(embed=embed)

    @commands.command(aliases=["gakjadirilis", "revert"])
    @commands.guild_only()
    async def batalrilis(self, ctx, *, judul=None):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

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
        status_list = program_info["status"]
        srv_owner = srv_data["serverowner"]

        if (
            str(ctx.message.author.id) != program_info["assignments"]["QC"]["id"]
            and str(ctx.message.author.id) not in srv_owner
        ):
            return await ctx.send(
                "**Tidak secepat itu ferguso, yang bisa membatalkan rilisan cuma admin atau QCer**"
            )

        current = self.get_current_ep(status_list)
        reset_fsdb = False
        if not current:
            current = status_list[-1]
            reset_fsdb = True
        else:
            indx_ep = self._search_data_index(status_list, "episode", current["episode"])
            try:
                current = status_list[indx_ep - 1]
            except IndexError:
                return await ctx.send("Tidak dapat membatalkan rilis jika episode pertama belum di rilis!")

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        self.logger.info(f"{ani_title}: unreleasing episode {current['episode']}")
        current["is_done"] = False
        program_info["last_update"] = self.get_unix()
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                progoinfo = osrv_data["anime"][indx_other]
                indxo_ep = self._search_data_index(progoinfo["status"], "episode", current["episode"])
                osrv_data["anime"][indx_other]["status"][indxo_ep]["is_done"] = False
                osrv_data["anime"][indx_other]["last_update"] = self.get_unix()
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{ani_title}: sending progress info to staff...")
        await ctx.send("Berhasil membatalkan rilisan **{}** episode {}".format(ani_title, current["episode"]))

        if "fsdb_data" in program_info and reset_fsdb and self.fsdb is not None:
            self.logger.info("Re-Updating back FSDB project to Not done.")
            fsdb_data = program_info["fsdb_data"]
            if "id" in fsdb_data and fsdb_data["id"] is not None:
                await self.fsdb.update_project(fsdb_data["id"], "status", "Jalan")

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update" f", reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            if "announce_channel" in osrv_data and osrv_data["announce_channel"]:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                try:
                    target_chan = self.bot.get_channel(int(announce_chan))
                except (AttributeError, ValueError, TypeError):
                    continue
                if not target_chan:
                    self.logger.warning(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title=ani_title, color=0xB51E1E)
                embed.add_field(
                    name="Batal rilis...",
                    value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(  # noqa: E501
                        current["episode"]
                    ),
                    inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        if "announce_channel" in srv_data and srv_data["announce_channel"]:
            announce_chan = srv_data["announce_channel"]
            try:
                announce_chan = int(announce_chan)
            except (AttributeError, ValueError, TypeError):
                self.logger.warning(
                    f"{server_message}: failed to convert announce channel to integer, ignoring..."
                )
                return
            target_chan = self.bot.get_channel(announce_chan)
            embed = discord.Embed(title=ani_title, color=0xB51E1E)
            embed.add_field(
                name="Batal rilis...",
                value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(  # noqa: E501
                    current["episode"]
                ),
                inline=False,
            )
            self.logger.info(f"{server_message}: sending progress to everyone...")
            embed.set_footer(text=f"Pada: {get_current_time()}")
            if target_chan:
                await target_chan.send(embed=embed)

    @commands.command(aliases=["undone", "cancel"])
    @commands.guild_only()
    async def gakjadi(self, ctx, posisi, *, judul):
        """
        Menghilangkan tanda karena ada kesalahan
        ---
        posisi: tl, tlc, enc, ed, ts, atau qc
        judul: Judul anime yang terdaftar
        """
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        posisi, posisi_asli = await self.get_roles(posisi)
        if posisi is None:
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
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
        status_list = program_info["status"]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        try:
            if (
                not self.check_role(program_info["role_id"], ctx.message.author.roles)
                and str(ctx.message.author.id) not in srv_owner
            ):
                return
        except ValueError:
            return await ctx.send(
                f"Gagal memeriksa role, mohon ubah dengan {self.bot.prefix}ubahdata {ani_title}"
            )

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warning(f"{ani_title}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        current_stat = current["progress"][posisi]
        if not current_stat:
            self.logger.warning(f"{ani_title}: position already set to undone.")
            return await ctx.send(f"**{posisi_asli}** sudah ditandakan sebagai tidak beres.")

        poster_data = program_info["poster_data"]
        poster_image = poster_data["url"]

        if (
            str(ctx.message.author.id) != str(program_info["assignments"][posisi]["id"])
            and str(ctx.message.author.id) not in srv_owner
        ):
            self.logger.warning(f"{ani_title}: no access to set to undone.")
            return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        self.logger.info(f"{ani_title}: setting episode {current} to undone.")
        current["progress"][posisi] = False
        program_info["last_update"] = self.get_unix()
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                progoinfo = osrv_data["anime"][indx_other]
                indxo_ep = self._search_data_index(progoinfo["status"], "episode", current["episode"])
                osrv_data["anime"][indx_other]["status"][indxo_ep]["progress"][posisi] = False
                osrv_data["anime"][indx_other]["last_update"] = self.get_unix()
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        current_ep_status = current["progress"]

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{ani_title}: sending progress info to staff...")
        await ctx.send("Berhasil mengubah status garapan {} - #{}".format(ani_title, current["episode"]))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
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

        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
                continue
            if "announce_channel" in osrv_data and osrv_data["announce_channel"]:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                try:
                    announce_chan = int(announce_chan)
                except (AttributeError, ValueError, TypeError):
                    self.logger.warning(f"{osrv}: failed to convert announce channel to integer, ignoring...")
                    continue
                try:
                    target_chan = self.bot.get_channel(announce_chan)
                except ValueError:
                    continue
                if not target_chan:
                    self.logger.warning(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title="{} - #{}".format(ani_title, current["episode"]), color=0xB51E1E,)
                embed.description = f"❌ {self.normalize_role_to_name(posisi)}"
                embed.add_field(
                    name="Status", value=self.parse_status(current_ep_status), inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(ani_title, current["episode"]), color=0xB51E1E)
        embed.add_field(
            name="Status", value=self.parse_status(current_ep_status), inline=False,
        )
        if "announce_channel" in srv_data and srv_data["announce_channel"]:
            announce_chan = srv_data["announce_channel"]
            try:
                announce_chan = int(announce_chan)
            except (AttributeError, ValueError, TypeError):
                self.logger.warning(
                    f"{server_message}: failed to convert announce channel to integer, ignoring..."
                )
                announce_chan = -1
            target_chan = self.bot.get_channel(announce_chan)
            embed.description = f"❌ {self.normalize_role_to_name(posisi)}"
            embed.set_footer(text=f"Pada: {get_current_time()}")
            self.logger.info(f"{server_message}: sending progress to everyone...")
            if target_chan:
                await target_chan.send(embed=embed)
        embed.description = EmptyEmbed
        embed.add_field(name="Update Terakhir", value="Baru saja", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        embed.set_thumbnail(url=poster_image)
        await ctx.send(embed=embed)

    @commands.command(aliases=["mark"])
    @commands.guild_only()
    async def tandakan(self, ctx, posisi: str, episode_n: str, *, judul):
        """
        Mark something as done or undone for
        other episode without announcing it
        """
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        posisi, posisi_asli = await self.get_roles(posisi)
        if posisi is None:
            self.logger.warning("unknown position.")
            return await ctx.send(
                f"Tidak ada posisi **{posisi_asli}**\n"
                "Yang tersedia: `tl`, `tlc`, `enc`, `ed`, `tm`, `ts`, dan `qc`"
            )
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
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
        status_list = program_info["status"]

        ep_index = self._search_data_index(status_list, "episode", episode_n)

        if ep_index is None:
            self.logger.warning(f"{ani_title}: episode out of range.")
            return await ctx.send("Episode tersebut tidak ada di database.")

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warning(f"{ani_title}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        # Toggle status section
        if (
            str(ctx.message.author.id) != str(program_info["assignments"][posisi]["id"])
            and str(ctx.message.author.id) not in srv_owner
        ):
            self.logger.warning(f"{ani_title}: no access to set to mark it.")
            return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        pos_status = status_list[ep_index]["progress"]
        reverse_stat = not pos_status[posisi]

        osrv_dumped = {}
        self.logger.info(f"{ani_title}: marking episode {current}...")
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
                progoinfo = osrv_data["anime"][indx_other]
                indxo_ep = self._search_data_index(progoinfo["status"], "episode", current["episode"])
                if indxo_ep is None:
                    continue
                osrv_data["anime"][indx_other]["status"][indxo_ep]["progress"][posisi] = reverse_stat
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        pos_status[posisi] = reverse_stat
        txt_msg = "Berhasil mengubah status **{st}** **{an}** episode **#{ep}** ke **{x}**"

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        await ctx.send(
            txt_msg.format(
                st=posisi,
                an=ani_title,
                ep=status_list[ep_index]["episode"],
                x="beres" if reverse_stat else "belum beres",
            )
        )

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv, osrv_data in osrv_dumped.items():
            if osrv == server_message:
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
