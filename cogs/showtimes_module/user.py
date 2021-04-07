# -*- coding: utf-8 -*-

import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial
from typing import Union

import discord
from discord.ext import commands

from nthelper.bot import naoTimesBot

from .base import ShowtimesBase, fetch_anilist, get_last_updated


class ShowtimesUser(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesUser, self).__init__()
        self.bot = bot
        self.showqueue = bot.showqueue
        self.ntdb = bot.ntdb
        # pylint: disable=E1101
        self.logger = logging.getLogger("cogs.showtimes_module.user.ShowtimesUser")
        self.srv_fetch = partial(self.fetch_showtimes, redisdb=bot.redisdb)
        self.srv_dumps = partial(self.dumps_showtimes, redisdb=bot.redisdb)
        # pylint: enable=E1101
        # self.task = asyncio.Task(self.resync_failure())

    def __str__(self):
        return "Showtimes User"

    @commands.command(aliases=["blame", "mana"])
    @commands.guild_only()
    async def tagih(self, ctx, *, judul=None):
        """
        Menagih utang fansub tukang diley maupun tidak untuk memberikan
        mereka tekanan
        ---
        judul: Judul anime yang terdaftar
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
        last_update = int(program_info["last_update"])
        status_list = program_info["status"]

        current = self.get_current_ep(status_list)
        if current is None:
            self.logger.info(f"{matches[0]}: no episode left to be worked on.")
            return await ctx.send("**Sudah beres digarap!**")

        poster_data = program_info["poster_data"]
        poster_image, poster_color = poster_data["url"], poster_data["color"]

        if not self.is_progressing(current["progress"]):
            anilist_data = await fetch_anilist(program_info["id"], current["episode"])
            if isinstance(anilist_data, str):
                last_status = "Tidak diketahui..."
            else:
                last_status = anilist_data["episode_status"]
            last_text = "Tayang"
        else:
            last_status = get_last_updated(last_update)
            last_text = "Update Terakhir"

        current_ep_status = self.parse_status(current["progress"])

        self.logger.info(f"{matches[0]} sending current episode progress...")
        embed = discord.Embed(title="{} - #{}".format(ani_title, current["episode"]), color=poster_color)
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name="Status", value=current_ep_status, inline=False)
        embed.add_field(name=last_text, value=last_status, inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["airing"])
    @commands.guild_only()
    async def jadwal(self, ctx):
        """
        Melihat jadwal anime musiman yang di ambil.
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

        time_data_list = {}
        total_anime = len(srv_data["anime"])
        self.logger.info(f"{server_message}: collecting {total_anime} jadwal...")

        def calculate_needed(status_list):
            final_ep = status_list[-1]
            return 7 * final_ep["episode"] * 24 * 60 * 60

        simple_queue = asyncio.Queue()
        fetch_anime_jobs = []
        current_date = datetime.now(tz=timezone.utc).timestamp()
        for ani_data in srv_data["anime"]:
            ani = ani_data["title"]
            current = self.get_current_ep(ani_data["status"])
            if current is None:
                self.logger.warning(f"{ani_data['title']}: anime already done worked on.")
                continue
            try:
                start_time = ani_data["start_time"]
            except KeyError:
                self.logger.error(f"{ani}: failed fetching start_time from database.")
                continue
            calc_need = calculate_needed(ani_data["status"])
            needed_time = start_time + calc_need + (24 * 60 * 60)
            if current_date >= needed_time:
                self.logger.warning(f"{ani}: anime already ended, skipping...")
                continue
            self.logger.info(f"{server_message}: requesting {ani}")
            fetch_anime_jobs.append(fetch_anilist(ani_data["id"], jadwal_only=True))

        self.logger.info(f"{server_message}: running jobs...")
        is_error = False
        for anime_job in asyncio.as_completed(fetch_anime_jobs):
            anilist_data = await anime_job
            if isinstance(anilist_data, str):
                is_error = True
                continue
            time_data = anilist_data["episode_status"]
            if not isinstance(time_data, str):
                continue
            next_air = anilist_data["next_airing"]
            time_until, episode = next_air["time_until"], next_air["episode"]
            await simple_queue.put({"t": time_until, "d": [anilist_data["title"], time_data, episode]})

        self.logger.info(f"{server_message}: starting queue...")
        while not simple_queue.empty():
            data_map = await simple_queue.get()
            time_until, data = data_map["t"], data_map["d"]
            if time_until in time_data_list:  # For anime that air at the same time
                time_until += 1
                while True:
                    if time_until not in time_data_list:
                        break
                    time_until += 1
            time_data_list[time_until] = data
            simple_queue.task_done()

        sorted_time = sorted(deepcopy(time_data_list))
        appendtext = ""
        self.logger.info(f"{server_message}: generating result...")
        for s in sorted_time:
            animay, time_data, episode = time_data_list[s]
            appendtext += "**{}** - #{}\n".format(animay, episode)
            appendtext += time_data + "\n\n"

        self.logger.info(f"{server_message}: sending message...")
        if appendtext != "":
            await ctx.send(appendtext.strip())
        else:
            await ctx.send("**Tidak ada utang pada musim ini yang terdaftar**")
        if is_error:
            await ctx.send("Ada kemungkinan Anilist gagal dihubungi, mohon coba lagi nanti.")

    @commands.command(aliases=["tukangdelay", "pendelay", "staf"])
    @commands.guild_only()
    async def staff(self, ctx: commands.Context, *, judul):
        """
        Menagih utang fansub tukang diley maupun
        tidak untuk memberikan mereka tekanan
        ---
        judul: Judul anime yang terdaftar
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
        staff_assignment = program_info["assignments"]
        self.logger.info(f"{server_message}: parsing staff data...")

        rtext = "Staff yang mengerjakaan **{}**\n**Admin**: ".format(ani_title)
        rtext += ""

        async def get_user_name(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return "{}#{}".format(user_data.name, user_data.discriminator)
            except (AttributeError, ValueError, TypeError):
                return "[Rahasia]"

        new_srv_owner = []
        for adm in srv_owner:
            user = await get_user_name(adm)
            new_srv_owner.append(user)

        rtext += ", ".join(new_srv_owner)

        guild: discord.Guild = ctx.message.guild
        role_name = "Tidak Diketahui"
        try:
            realrole: Union[discord.Role, None] = guild.get_role(int(program_info["role_id"]))
            if realrole is not None:
                role_name = realrole.name
        except ValueError:
            role_name = "Tidak Dikethui"

        rtext += f"\n**Role**: {role_name}"

        if "kolaborasi" in program_info:
            k_list = []
            for other_srv in program_info["kolaborasi"]:
                if server_message == other_srv:
                    continue
                server_data = self.bot.get_guild(int(other_srv))
                if not server_data:
                    self.logger.warning(f"{other_srv}: can't find server on Discord.")
                    self.logger.warning(f"{other_srv}: is the bot on that server.")
                    continue
                k_list.append(server_data.name)
            if k_list:
                rtext += "\n**Kolaborasi dengan**: {}".format(", ".join(k_list))

        rtext += "\n\n"

        for k, v in staff_assignment.items():
            try:
                user = await get_user_name(v["id"])
                rtext += "**{}**: {}\n".format(k, user)
            except discord.errors.NotFound:
                rtext += "**{}**: Unknown\n".format(k)

        rtext += "\n**Jika ada yang Unknown, admin dapat menggantikannya**"

        self.logger.info(f"{server_message}: sending message!")
        await ctx.send(rtext)
