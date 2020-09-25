# -*- coding: utf-8 -*-

import logging
import time

import discord
from discord.ext import commands, tasks

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
        data = data.split()

        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_owner = srv_data["serverowner"]
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if len(srv_anilist) < 1:
            self.logger.warning(f"{server_message}: no registered data on database.")
            return await ctx.send("**Tidak ada anime yang terdaftar di database**")

        if not data or data == []:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        koleb_list = []
        osrv_dumped = {}

        should_update_fsdb = False
        fsdb_update_to = "Tentatif"
        if data[0] not in ["batch", "semua"]:
            self.logger.info(f"{server_message}: using normal mode.")

            judul = " ".join(data)

            if judul == " " or judul == "" or judul == "   " or not judul:
                return await self.send_all_projects(ctx, srv_anilist, server_message)

            self.logger.info(f"{server_message}: getting close matches...")
            matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
            if not matches:
                self.logger.warning(f"{server_message}: no matches.")
                return await ctx.send("Tidak dapat menemukan judul tersebut di database")
            elif len(matches) > 1:
                self.logger.info(f"{server_message}: multiple matches!")
                matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
                if not matches:
                    return await ctx.send("**Dibatalkan!**")

            self.logger.info(f"{server_message}: matched {matches[0]}")
            program_info = srv_data["anime"][matches[0]]
            status_list = program_info["status"]

            if "kolaborasi" in program_info:
                koleb_data = program_info["kolaborasi"]
                if koleb_data:
                    for ko_data in koleb_data:
                        if server_message == ko_data:
                            continue
                        koleb_list.append(ko_data)

            current = self.get_current_ep(status_list)
            episode_set = list(status_list.keys())
            if not current:
                self.logger.warning(f"{matches[0]}: no episode left to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if current == episode_set[0]:
                should_update_fsdb = True
                fsdb_update_to = "Jalan"

            if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
                if str(ctx.message.author.id) not in srv_owner:
                    self.logger.warning(f"{matches[0]}: user not allowed.")
                    return await ctx.send(
                        "**Tidak secepat itu ferguso, " "yang bisa rilis cuma admin atau QCer**"
                    )

            if koleb_list:
                self.logger.info(f"{matches[0]}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.showqueue.fetch_database(other_srv)
                    if srv_o_data is None:
                        continue
                    self.logger.debug(f"{server_message}: {other_srv} processing...")
                    srv_o_data["anime"][matches[0]]["status"][current]["status"] = "released"
                    srv_o_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await self.showqueue.add_job(ShowtimesQueueData(srv_o_data, other_srv))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{matches[0]}: setting status...")
            srv_data["anime"][matches[0]]["status"][current]["status"] = "released"
            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            text_data = "**{} - #{}** telah dirilis".format(matches[0], current)
            embed_text_data = "{} #{} telah dirilis!".format(matches[0], current)
        elif data[0] == "batch":
            self.logger.info(f"{server_message}: using batch mode.")
            if not data[1].isdigit():
                await self.send_all_projects(ctx, srv_anilist, server_message)
                return await ctx.send("Lalu tulis jumlah terlebih dahulu baru judul")
            if len(data) < 3:
                return await self.send_all_projects(ctx, srv_anilist, server_message)

            jumlah = data[1]
            judul = " ".join(data[2:])

            self.logger.info(f"{server_message}: getting close matches...")
            matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
            if not matches:
                self.logger.warning(f"{server_message}: no matches.")
                return await ctx.send("Tidak dapat menemukan judul tersebut di database")
            elif len(matches) > 1:
                self.logger.info(f"{server_message}: multiple matches!")
                matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
                if not matches:
                    return await ctx.send("**Dibatalkan!**")
            self.logger.info(f"{server_message}: matched {matches[0]}")

            program_info = srv_data["anime"][matches[0]]
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
                self.logger.warning(f"{matches[0]}: no episode left to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
                if str(ctx.message.author.id) not in srv_owner:
                    self.logger.warning(f"{matches[0]}: user not allowed.")
                    return await ctx.send(
                        "**Tidak secepat itu ferguso, " "yang bisa rilis cuma admin atau QCer**"
                    )

            if koleb_list:
                self.logger.info(f"{matches[0]}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.showqueue.fetch_database(other_srv)
                    if srv_o_data is None:
                        continue
                    self.logger.debug(f"{server_message}: {other_srv} processing...")
                    for x in range(int(current), int(current) + int(jumlah)):  # range(int(c), int(c)+int(x))
                        srv_o_data["anime"][matches[0]]["status"][str(x)]["status"] = "released"
                    srv_o_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await self.showqueue.add_job(ShowtimesQueueData(srv_o_data, other_srv))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{matches[0]}: setting status...")
            for x in range(int(current), int(current) + int(jumlah)):  # range(int(c), int(c)+int(x))
                srv_data["anime"][matches[0]]["status"][str(x)]["status"] = "released"

            should_update_fsdb = True
            fsdb_update_to = "Jalan"
            last_ep = int(list(status_list.keys())[-1])
            if last_ep == int(current) + int(jumlah):
                fsdb_update_to = "Tamat"

            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(
                matches[0], current, int(current) + int(jumlah) - 1
            )
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(
                matches[0], current, int(current) + int(jumlah) - 1
            )
        elif data[0] == "semua":
            should_update_fsdb = True
            fsdb_update_to = "Tamat"
            self.logger.info(f"{server_message}: using all mode.")
            judul = " ".join(data[1:])

            if judul == " " or judul == "" or judul == "   " or not judul:
                return await self.send_all_projects(ctx, srv_anilist, server_message)

            self.logger.info(f"{server_message}: getting close matches...")
            matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
            if not matches:
                self.logger.warning(f"{server_message}: no matches.")
                return await ctx.send("Tidak dapat menemukan judul tersebut di database")
            elif len(matches) > 1:
                self.logger.info(f"{server_message}: multiple matches!")
                matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
                if not matches:
                    return await ctx.send("**Dibatalkan!**")

            program_info = srv_data["anime"][matches[0]]
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
                self.logger.warning(f"{matches[0]}: no episode left " "to be worked on.")
                return await ctx.send("**Sudah beres digarap!**")

            if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
                if str(ctx.message.author.id) not in srv_owner:
                    self.logger.warning(f"{matches[0]}: user not allowed.")
                    return await ctx.send(
                        "**Tidak secepat itu ferguso, " "yang bisa rilis cuma admin atau QCer**"
                    )

            if koleb_list:
                self.logger.info(f"{matches[0]}: setting collab status...")
                for other_srv in koleb_list:
                    if other_srv == server_message:
                        continue
                    srv_o_data = await self.showqueue.fetch_database(other_srv)
                    if srv_o_data is None:
                        continue
                    for x in all_status:
                        srv_o_data["anime"][matches[0]]["status"][x]["status"] = "released"
                    srv_o_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await self.showqueue.add_job(ShowtimesQueueData(srv_o_data, other_srv))
                    osrv_dumped[other_srv] = srv_o_data
            self.logger.info(f"{matches[0]}: setting status...")
            for x in all_status:
                srv_data["anime"][matches[0]]["status"][x]["status"] = "released"

            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            text_data = "**{} - #{} sampai #{}** telah dirilis".format(
                matches[0], all_status[0], all_status[-1]
            )
            embed_text_data = "{} #{} sampai #{} telah dirilis!".format(
                matches[0], all_status[0], all_status[-1]
            )

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{server_message}: sending message")
        await ctx.send(text_data)

        if "fsdb_data" in program_info and should_update_fsdb:
            self.logger.info("Re-Updating back FSDB project to Not done.")
            fsdb_data = program_info["fsdb_data"]
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
            if "announce_channel" in osrv_data:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                if not target_chan:
                    self.logger.warning(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title="{}".format(matches[0]), color=0x1EB5A6)
                embed.add_field(name="Rilis!", value=embed_text_data, inline=False)
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        if "announce_channel" in srv_data:
            self.logger.info(f"{server_message}: sending progress to everyone...")
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed = discord.Embed(title="{}".format(matches[0]), color=0x1EB5A6)
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
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )
        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        if not self.check_role(program_info["role_id"], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warning(f"{matches[0]}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        current_stat = status_list[current]["staff_status"][posisi]
        if current_stat == "y":
            self.logger.warning(f"{matches[0]}: position already set to done.")
            return await ctx.send(f"**{posisi_asli}** sudah ditandakan " "sebagai beres.")

        poster_data = program_info["poster_data"]
        poster_image = poster_data["url"]

        if str(ctx.message.author.id) != program_info["staff_assignment"][posisi]:
            if str(ctx.message.author.id) not in srv_owner:
                self.logger.warning(f"{matches[0]}: no access to set to done.")
                return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        self.logger.info(f"{matches[0]}: setting episode {current} to done.")
        srv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "y"
        srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                osrv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "y"
                osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        current_ep_status = status_list[current]["staff_status"]

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{matches[0]}: sending progress info to staff...")
        await ctx.send("Berhasil mengubah status garapan {} - #{}".format(matches[0], current))

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
                if "announce_channel" in osrv_data:
                    self.logger.info(f"{osrv}: sending progress to everyone...")
                    announce_chan = osrv_data["announce_channel"]
                    target_chan = self.bot.get_channel(int(announce_chan))
                    if not target_chan:
                        self.logger.warning(f"{announce_chan}: unknown channel.")
                        continue
                    embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0x1EB5A6,)
                    embed.add_field(
                        name="Status", value=self.parse_status(current_ep_status), inline=False,
                    )
                    embed.set_footer(text=f"Pada: {get_current_time()}")
                    await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0x1EB5A6)
        embed.add_field(
            name="Status", value=self.parse_status(current_ep_status), inline=False,
        )
        if "announce_channel" in srv_data:
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed.set_footer(text=f"Pada: {get_current_time()}")
            self.logger.info(f"{server_message}: sending progress to everyone...")
            if target_chan:
                await target_chan.send(embed=embed)
        embed.add_field(name="Update Terakhir", value="Baru saja", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        embed.set_thumbnail(url=poster_image)
        return await ctx.send(embed=embed)

    @commands.command(aliases=["gakjadirilis", "revert"])
    @commands.guild_only()
    async def batalrilis(self, ctx, *, judul=None):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]
        srv_owner = srv_data["serverowner"]

        if str(ctx.message.author.id) != program_info["staff_assignment"]["QC"]:
            if str(ctx.message.author.id) not in srv_owner:
                return await ctx.send(
                    "**Tidak secepat itu ferguso, yang bisa " "membatalkan rilisan cuma admin atau QCer**"
                )

        current = self.get_current_ep(status_list)
        reset_fsdb = False
        if not current:
            current = int(list(status_list.keys())[-1])
            reset_fsdb = True
        else:
            current = int(current) - 1

        if current < 1:
            self.logger.info(f"{matches[0]}: no episode have been released.")
            return await ctx.send("Tidak ada episode yang dirilis untuk judul ini.")

        current = str(current)

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        self.logger.info(f"{matches[0]}: unreleasing episode {current}")
        srv_data["anime"][matches[0]]["status"][current]["status"] = "not_released"
        srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                osrv_data["anime"][matches[0]]["status"][current]["status"] = "not_released"
                osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{matches[0]}: sending progress info to staff...")
        await ctx.send("Berhasil membatalkan rilisan **{}** episode {}".format(matches[0], current))

        if "fsdb_data" in program_info and reset_fsdb:
            self.logger.info("Re-Updating back FSDB project to Not done.")
            await self.fsdb.update_project(program_info["fsdb_data"]["id"], "status", "Jalan")

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
            if "announce_channel" in osrv_data:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                if not target_chan:
                    self.logger.warning(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title="{}".format(matches[0]), color=0xB51E1E)
                embed.add_field(
                    name="Batal rilis...",
                    value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(  # noqa: E501
                        current
                    ),
                    inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        if "announce_channel" in srv_data:
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed = discord.Embed(title="{}".format(matches[0]), color=0xB51E1E)
            embed.add_field(
                name="Batal rilis...",
                value="Rilisan **episode #{}** dibatalkan dan sedang dikerjakan kembali".format(  # noqa: E501
                    current
                ),
                inline=False,
            )
            self.logger.info(f"{server_message}: sending " "progress to everyone...")
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
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        if not self.check_role(program_info["role_id"], ctx.message.author.roles):
            if str(ctx.message.author.id) not in srv_owner:
                return
            else:
                pass

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warning(f"{matches[0]}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        current_stat = status_list[current]["staff_status"][posisi]
        if current_stat == "x":
            self.logger.warning(f"{matches[0]}: position already set to undone.")
            return await ctx.send(f"**{posisi_asli}** sudah ditandakan " "sebagai tidak beres.")

        poster_data = program_info["poster_data"]
        poster_image = poster_data["url"]

        if str(ctx.message.author.id) != program_info["staff_assignment"][posisi]:
            if str(ctx.message.author.id) not in srv_owner:
                self.logger.warning(f"{matches[0]}: no access to set to undone.")
                return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        self.logger.info(f"{matches[0]}: setting episode {current} to undone.")
        srv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "x"
        srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
        osrv_dumped = {}
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                osrv_data["anime"][matches[0]]["status"][current]["staff_status"][posisi] = "x"
                osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        current_ep_status = status_list[current]["staff_status"]

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        self.logger.info(f"{matches[0]}: sending progress info to staff...")
        await ctx.send("Berhasil mengubah status garapan {} - #{}".format(matches[0], current))

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
            if "announce_channel" in osrv_data:
                self.logger.info(f"{osrv}: sending progress to everyone...")
                announce_chan = osrv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                if not target_chan:
                    self.logger.warning(f"{announce_chan}: unknown channel.")
                    continue
                embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0xB51E1E,)
                embed.add_field(
                    name="Status", value=self.parse_status(current_ep_status), inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                await target_chan.send(embed=embed)
        embed = discord.Embed(title="{} - #{}".format(matches[0], current), color=0xB51E1E)
        embed.add_field(
            name="Status", value=self.parse_status(current_ep_status), inline=False,
        )
        if "announce_channel" in srv_data:
            announce_chan = srv_data["announce_channel"]
            target_chan = self.bot.get_channel(int(announce_chan))
            embed.set_footer(text=f"Pada: {get_current_time()}")
            self.logger.info(f"{server_message}: sending progress to everyone...")
            if target_chan:
                await target_chan.send(embed=embed)
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
        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]
        status_list = program_info["status"]

        if episode_n not in status_list:
            self.logger.warning(f"{matches[0]}: episode out of range.")
            return await ctx.send("Episode tersebut tidak ada di database.")

        current = self.get_current_ep(status_list)
        if not current:
            self.logger.warning(f"{matches[0]}: no episode left to be worked on.")
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
        if str(ctx.message.author.id) != program_info["staff_assignment"][posisi]:
            if str(ctx.message.author.id) not in srv_owner:
                self.logger.warning(f"{matches[0]}: no access to set to mark it.")
                return await ctx.send("**Bukan posisi situ untuk mengubahnya!**")

        pos_status = status_list[str(episode_n)]["staff_status"]

        osrv_dumped = {}
        self.logger.info(f"{matches[0]}: marking episode {current}...")
        if koleb_list:
            for other_srv in koleb_list:
                if other_srv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(other_srv)
                if osrv_data is None:
                    continue
                if pos_status[posisi] == "x":
                    osrv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][posisi] = "y"
                elif pos_status[posisi] == "y":
                    osrv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][posisi] = "x"
                await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))
                osrv_dumped[other_srv] = osrv_data

        if pos_status[posisi] == "x":
            srv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][posisi] = "y"
            txt_msg = (
                "Berhasil mengubah status **{st}** **{an}** episode **#{ep}** ke **beres**"  # noqa: E501
            )
        elif pos_status[posisi] == "y":
            srv_data["anime"][matches[0]]["status"][episode_n]["staff_status"][posisi] = "x"
            txt_msg = "Berhasil mengubah status **{st}** **{an}** episode **#{ep}** ke **belum beres**"  # noqa: E501

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        await ctx.send(txt_msg.format(st=posisi, an=matches[0], ep=episode_n))

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
