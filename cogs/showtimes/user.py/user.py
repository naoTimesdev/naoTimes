import asyncio
import logging
from typing import Any, Dict, List

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.showtimes import ShowtimesEpisodeStatus, ShowtimesProject
from naotimes.showtimes.cogbase import utctime_to_timeleft
from naotimes.views.multi_view import Selection


class ShowtimesUser(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.queue = bot.showqueue
        self.base = bot.showcogs

        self.logger = logging.getLogger("Showtimes.User")

    async def _showtimes_render_tagih(self, ctx: naoTimesContext, matched_anime: ShowtimesProject):
        if ctx.is_interaction():
            self.logger.info("Deferring result...")
            await ctx.defer()
        server_id = str(ctx.guild.id)
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        active_episode = matched_anime.get_current()
        log_pre = f"{server_id}-{matched_anime.title}"
        if active_episode is None:
            self.logger.warning(f"{log_pre}: no active episode left")
            return await ctx.send("**Sudah selesai digarap!**")

        poster_image, poster_color = matched_anime.poster.url, matched_anime.poster.color
        last_episode = matched_anime.status[-1]
        if not bool(active_episode.progress):
            schedules_data = await self.base.anilist_get_schedules(matched_anime.id, last_episode.episode)
            if not isinstance(schedules_data, list):
                last_status = "Tidak diketahui..."
            else:
                selected_ep = list(filter(lambda x: x.episode == last_episode.episode, schedules_data))
                if not selected_ep:
                    last_status = "Tidak diketahui..."
                else:
                    last_status = utctime_to_timeleft(selected_ep[0].airing_at)
            last_text = "Tayang"
        else:
            last_status = matched_anime.formatted_last_update
            last_text = "Update Terakhir"

        self.logger.info(f"{log_pre}: sending current episode progress...")
        embed = discord.Embed(title=f"{matched_anime.title} - #{active_episode.episode}", color=poster_color)
        embed.set_thumbnail(url=poster_image)
        embed.add_field(name="Status", value=self.base.parse_status(active_episode.progress), inline=False)
        embed.add_field(name=last_text, value=last_status, inline=False)
        if active_episode.delay_reason is not None:
            embed.add_field(name="Alasan Delay", value=active_episode.delay_reason, inline=False)
        embed.set_footer(text="Dibawakan oleh naoTimes™", icon_url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)

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
        await self._showtimes_render_tagih(ctx, matched_anime)

    @app_commands.command(name="tagih", description="Melihat status progres sebuah proyek garapan")
    @app_commands.describe(judul="Judul yang ingin dilihat informasinya")
    async def _showuser_tagih_slash(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        # @app.option("judul", str, autocomplete=True, description="Judul anime yang ingin dilihat")
        server_id = str(ctx.guild.id)
        self.logger.info(f"Requested at: {server_id}")
        srv_data = await self.queue.fetch_database(server_id)

        if srv_data is None:
            return await ctx.send("Peladen tidak terdaftar di Showtimes")

        self.logger.info(f"{server_id}: getting close matches, with title/ID: {judul}")
        match_project = await self.bot.loop.run_in_executor(None, srv_data.get_project, judul)
        if match_project is None:
            match_project = srv_data.exact_match(judul)
            if match_project is None:
                self.logger.warning(f"{server_id}: no matches.")
                return await ctx.send("Tidak dapat menemukan judul tersebut di database")

        await self._showtimes_render_tagih(ctx, match_project)

    @_showuser_tagih_slash.autocomplete("judul")
    async def _showuser_tagih_slash_judul_auto(self, inter: discord.Interaction, current: str):
        server_id = str(inter.guild.id)
        self.logger.info(f"Requested at: {server_id}")
        srv_data = await self.queue.fetch_database(server_id)
        if srv_data is None:
            self.logger.info("Autocompleting without showtimes being resgistered...")
            return ["Peladen tidak terdaftar di Showtimes"]

        parsed_choices: List[app_commands.Choice] = []
        if not current:
            self.logger.info(f"{server_id}: autocompleting with all projects...")
            match_unfinished_project: List[ShowtimesProject] = []
            for project in srv_data:
                if project.get_current() is not None:
                    match_unfinished_project.append(project)
            match_unfinished_project.sort(key=lambda x: x.title)
            parsed_choices = [
                app_commands.Choice(name=proj.title, value=str(proj.id)) for proj in match_unfinished_project
            ]
        else:
            self.logger.info(f"{server_id}: Trying to autocomplete with: {current}")
            all_matches = await self.bot.loop.run_in_executor(None, srv_data.find_projects, current)
            all_matches.sort(key=lambda x: x.title)
            parsed_choices = [
                app_commands.Choice(name=proj.title, value=str(proj.id)) for proj in all_matches
            ]

        if parsed_choices:
            parsed_choices.sort(key=lambda x: x.name)
        return parsed_choices

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


async def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesUser(bot))
