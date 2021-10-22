import asyncio
import logging
from typing import Any, Dict, List

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.showtimes import ShowtimesEpisodeStatus


class ShowtimesUser(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.queue = bot.showqueue
        self.base = bot.showcogs

        self.logger = logging.getLogger("Showtimes.User")

    @commands.command(name="tagih", aliases=["blame", "mana"])
    @commands.guild_only()
    async def _showuser_tagih(self, ctx: naoTimesContext, *, judul: str = None):
        """Menagih utang fansub tukang diley
        Lihat progress garapan sudah sampai mana
        ---
        judul: Judul anime/garapan
        """
        server_id = str(ctx.guild.id)
        self.logger.info(f"Requested at: {server_id}")
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

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

        active_episode = matched_anime.get_current()
        log_pre = f"{server_id}-{matched_anime.title}"
        if active_episode is None:
            self.logger.warning(f"{log_pre}: no active episode left")
            return await ctx.send("**Sudah selesai digarap!**")

        poster_image, poster_color = matched_anime.poster.url, matched_anime.poster.color
        if not bool(active_episode.progress):
            anilist_data = await self.base.fetch_anilist(matched_anime.id, active_episode.episode)
            if isinstance(anilist_data, str):
                last_status = "Tidak diketahui..."
            else:
                last_status = anilist_data["episode_status"]
            last_text = "Tayang"
        else:
            last_status = matched_anime.formatted_last_update
            last_text = "Update Terakhir"

        self.logger.info(f"{log_pre}: sending current episode progress...")
        embed = discord.Embed(title=f"{matched_anime.title} - #{active_episode.episode}", color=poster_color)
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name="Status", value=self.base.parse_status(active_episode.progress), inline=False)
        embed.add_field(name=last_text, value=last_status, inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™", icon_url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)

    # @app.slash_command(name="tagih")
    # @app.option("judul", str, autocomplete=True)
    # async def _showuser_tagih_slash(self, ctx: app.ApplicationContext, judul: str):
    #     server_id = str(ctx.guild.id)
    #     self.logger.info(f"Requested at: {server_id}")
    #     srv_data = await self.queue.fetch_database(server_id)

    #     if ctx.autocompleting == "judul":
    #         if srv_data is None:
    #             self.logger.warning("Autocompleting without data...")
    #             return await ctx.autocomplete(["Server tidak terdaftar di Showtimes"])
    #         self.logger.info(f"Trying to match autocomplete: {judul}...")
    #         all_matches = srv_data.find_projects(judul)
    #         parsed_objects = list(map(lambda x: app.OptionChoice(x.id, x.title), all_matches))
    #         self.logger.info(f"Autocomplete found: {len(parsed_objects)} matches")
    #         return await ctx.autocomplete(parsed_objects[:20])

    #     if srv_data is None:
    #         return await ctx.send("Peladen tidak terdaftar di Showtimes!")
    #     self.logger.info(f"{server_id}: found a showtimes match with title ID: {judul}")

    #     await ctx.send(f"This should get `{judul}` later")

    @commands.command(name="staff", aliases=["tukangdelay", "pendelay", "staf"])
    @commands.guild_only()
    async def _showuser_staff(self, ctx: naoTimesContext, *, judul: str = None):
        """Melihatkan siapa yang ngebuat sebuah proyek delay"""
        server_id = str(ctx.guild.id)
        self.logger.info(f"Requested at: {server_id}")
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

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

        rtext = f"Staff yang mengerjakan **{matched_anime.title}**\n"
        rtext += "**Admin**: "

        def get_user_info(user_id: int):
            user = self.bot.get_user(user_id)
            if user is None:
                return "[Rahasia]"
            return str(user)

        rtext += ", ".join(map(get_user_info, srv_data.admins))

        guild: discord.Guild = ctx.guild
        role_name = "Tidak diketahui"
        if matched_anime.role is not None:
            role_info = guild.get_role(matched_anime.role)
            if role_info is not None:
                role_name = role_info.name
        rtext += f"\n**Role**: {role_name}"

        if len(matched_anime.kolaborasi) > 0:
            only_non_server = list(filter(lambda x: x != guild.id, matched_anime.kolaborasi))
            koleb_list = []
            for koleb in only_non_server:
                server_koleb: discord.Guild = self.bot.get_guild(koleb)
                if server_koleb is not None:
                    koleb_list.append(server_koleb.name)
            if len(koleb_list) > 0:
                rtext += "\n**Kolaborasi dengan**: " + ", ".join(koleb_list)
        rtext += "\n\n"

        for role, staff in matched_anime.assignment:
            rtext += f"**{role}**: {get_user_info(staff.id)}\n"

        rtext += "\n**Jika ada yang Unknown, admin dapat menggantikannya**"
        self.logger.info(f"{server_id}-{matched_anime.id}: Sending staff information...")
        await ctx.send(rtext)

    @commands.command(name="jadwal", aliases=["airing"])
    @commands.guild_only()
    async def _showuser_jadwal(self, ctx: naoTimesContext):
        """Melihat jadwal untuk garapan yang sedang berlangsung"""
        server_id = str(ctx.guild.id)
        self.logger.info(f"Requested at: {server_id}")
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return
        self.logger.info(f"{server_id}: found a showtimes match")

        time_data_list = {}

        def calculate_needed(status_list: List[ShowtimesEpisodeStatus]):
            final_episode = status_list[-1]
            return 7 * final_episode.episode * 24 * 60 * 60

        simple_queue = asyncio.Queue[Dict[str, Any]]()
        fetch_jobs = []
        current_date = self.bot.now().timestamp()
        for anime in srv_data.projects:
            current = anime.get_current()
            if current is None:
                self.logger.warning(f"{anime.title}: anime already done worked on.")
                continue

            start_time = anime.start_time
            if start_time is None:
                continue
            calculate = calculate_needed(anime.status)
            needed_time = start_time + calculate + (24 * 3600)
            if current_date >= needed_time:
                self.logger.warning(f"{anime.title}: anime already done, skipping...")
                continue
            fetch_jobs.append(self.base.fetch_anilist(anime.id, jadwal_only=True))

        self.logger.info(f"{server_id}: running {len(fetch_jobs)} jobs...")
        is_error = False
        for anime_job in asyncio.as_completed(fetch_jobs):
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

        self.logger.info(f"{server_id}: starting queue...")
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

        sorted_data = sorted(time_data_list)
        appendtxt = ""
        self.logger.info(f"{server_id}: generating result...")
        for s in sorted_data:
            animay, time_data, episode = time_data_list[s]
            appendtxt += f"**{animay}** - #{episode}\n"
            appendtxt += time_data + "\n\n"

        self.logger.info(f"{server_id}: sending result...")
        if appendtxt != "":
            return await ctx.send(appendtxt.strip())
        await ctx.send("**Tidak ada utang pada musim ini yang terdaftar**")
        if is_error:
            await ctx.send("Ada kemungkinan Anilist gagal dihubungi, mohon coba lagi nanti.")


def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    bot.add_cog(ShowtimesUser(bot))
