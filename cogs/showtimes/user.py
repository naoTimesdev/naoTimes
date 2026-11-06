import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.showtimes import ShowtimesEpisodeStatus, ShowtimesProject
from naotimes.showtimes.cogbase import utctime_to_timeleft
from naotimes.showtimes.slash import load_server, project_autocomplete, resolve_project


class ShowtimesUser(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.queue = bot.showqueue
        self.base = bot.showcogs

        self.logger = logging.getLogger("Showtimes.User")

    async def _showtimes_render_tagih(self, ctx: naoTimesContext, matched_anime: ShowtimesProject):
        if ctx.guild is None:
            return await ctx.send(ctx.t("errors.guild_only"))
        if ctx.is_interaction():
            self.logger.info("Deferring result...")
            await ctx.defer()
        server_id = str(ctx.guild.id)
        self.logger.info(f"{server_id}: matched {matched_anime.title}")

        active_episode = matched_anime.get_current()
        log_pre = f"{server_id}-{matched_anime.title}"
        if active_episode is None:
            self.logger.warning(f"{log_pre}: no active episode left")
            return await ctx.send(ctx.t("errors.already_finished"))

        poster_image, poster_color = matched_anime.poster.url, matched_anime.poster.color
        last_episode = matched_anime.status[-1]
        if not bool(active_episode.progress):
            if self.base is None:
                return await ctx.send(ctx.t("errors.service_unavailable"))
            schedules_data = await self.base.anilist_get_schedules(matched_anime.id, last_episode.episode)
            if not isinstance(schedules_data, list):
                last_status = ctx.t("tagih.unknown")
            else:
                selected_ep = list(filter(lambda x: x.episode == active_episode.episode, schedules_data))
                if not selected_ep:
                    last_status = ctx.t("tagih.unknown")
                else:
                    last_status = utctime_to_timeleft(selected_ep[0].airing_at, ctx.locale)
            last_text = ctx.t("tagih.status_aired")
        else:
            last_status = matched_anime.format_last_update(ctx.locale)
            last_text = ctx.t("embed.last_update")

        self.logger.info(f"{log_pre}: sending current episode progress...")
        embed = discord.Embed(
            title=ctx.t("tagih.embed_title", title=matched_anime.title, episode=active_episode.episode),
            color=poster_color,
        )
        embed.set_thumbnail(url=poster_image)
        if self.base is None:
            return await ctx.send(ctx.t("errors.service_unavailable"))
        embed.add_field(name=ctx.t("embed.status"), value=self.base.parse_status(active_episode.progress), inline=False)
        embed.add_field(name=last_text, value=last_status, inline=False)
        if active_episode.delay_reason is not None:
            embed.add_field(name=ctx.t("tagih.delay_reason"), value=active_episode.delay_reason, inline=False)
        if len(active_episode.progress.Custom) > 0:
            custom_notes = []
            for custom in active_episode.progress.Custom:
                custom_notes.append(ctx.t("tagih.custom_note", key=custom.key, name=custom.name))
            embed.add_field(name=ctx.t("tagih.notes"), value="\n".join(custom_notes), inline=False)
        embed.set_footer(text=ctx.t("footer.credit"), icon_url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)

    @app_commands.command(
        name="tagih",
        description=app_commands.locale_str(
            "Melihat status progres sebuah proyek garapan", key="showtimes.tagih.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        judul=app_commands.locale_str("Judul yang ingin dilihat informasinya", key="showtimes.tagih.option_judul")
    )
    async def _showuser_tagih_slash(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        if inter.guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only"), ephemeral=True)
        self.logger.info(f"Requested at: {inter.guild.id}")
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)
        await self._showtimes_render_tagih(ctx, project)

    @_showuser_tagih_slash.autocomplete("judul")
    async def _showuser_tagih_slash_judul_auto(self, inter: discord.Interaction, current: str):
        return await project_autocomplete(self.bot, inter, current, only_unfinished=True)

    @app_commands.command(
        name="staff",
        description=app_commands.locale_str(
            "Melihat siapa saja yang mengerjakan sebuah proyek", key="showtimes.staff.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _showuser_staff(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        if inter.guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only"), ephemeral=True)
        server_id = str(inter.guild.id)
        self.logger.info(f"Requested at: {server_id}")
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        matched_anime, error = await resolve_project(self.bot, srv_data, judul)
        if matched_anime is None:
            return await inter.response.send_message(error, ephemeral=True)
        self.logger.info(f"{server_id}: matched {matched_anime.title}")
        if ctx.guild is None:
            return await ctx.send(ctx.t("errors.guild_only"))

        rtext = ctx.t("staff.header", title=matched_anime.title) + "\n"
        rtext += ctx.t("staff.admin_label")

        def get_user_info(user_id: int | None):
            if user_id is None:
                return ctx.t("staff.secret")
            user = self.bot.get_user(user_id)
            if user is None:
                return ctx.t("staff.secret")
            return str(user)

        rtext += ", ".join(map(get_user_info, srv_data.admins))

        guild = ctx.guild
        role_name = ctx.t("staff.unknown_role")
        if matched_anime.role is not None:
            role_info = guild.get_role(matched_anime.role)
            if role_info is not None:
                role_name = role_info.name
        rtext += ctx.t("staff.role_line", role=role_name)

        if len(matched_anime.kolaborasi) > 0:
            only_non_server = list(filter(lambda x: x != guild.id, matched_anime.kolaborasi))
            koleb_list = []
            for koleb in only_non_server:
                server_koleb = self.bot.get_guild(koleb)
                if server_koleb is not None:
                    koleb_list.append(server_koleb.name)
            if len(koleb_list) > 0:
                rtext += ctx.t("staff.collaboration", servers=", ".join(koleb_list))
        rtext += "\n\n"

        for role, staff in matched_anime.assignment:
            rtext += ctx.t("staff.staff_line", role=role, user=get_user_info(staff.id))

        if len(matched_anime.assignment.custom) > 0:
            rtext += ctx.t("staff.info_header")
            custom_lines = [ctx.t("staff.custom_line", key=x.key, name=x.name) for x in matched_anime.assignment.custom]
            rtext += "\n".join(custom_lines)

        rtext += ctx.t("staff.footer_note")
        self.logger.info(f"{server_id}-{matched_anime.id}: Sending staff information...")
        await ctx.send(rtext)

    @_showuser_staff.autocomplete("judul")
    async def _showuser_staff_judul_auto(self, inter: discord.Interaction, current: str):
        return await project_autocomplete(self.bot, inter, current)

    @app_commands.command(
        name="jadwal",
        description=app_commands.locale_str(
            "Melihat jadwal tayang garapan yang sedang berlangsung", key="showtimes.jadwal.description"
        ),
    )
    @app_commands.guild_only()
    async def _showuser_jadwal(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        if inter.guild is None:
            return await inter.response.send_message(ctx.t("errors.guild_only"), ephemeral=True)
        if self.base is None:
            return await inter.response.send_message(ctx.t("errors.service_unavailable"), ephemeral=True)
        server_id = str(inter.guild.id)
        self.logger.info(f"Requested at: {server_id}")
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        await ctx.defer()
        self.logger.info(f"{server_id}: found a showtimes match")

        time_data_list = {}

        def calculate_needed(status_list: list[ShowtimesEpisodeStatus]):
            final_episode = status_list[-1]
            return 7 * final_episode.episode * 24 * 60 * 60

        simple_queue = asyncio.Queue[dict[str, Any]]()
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
            appendtxt += ctx.t("jadwal.entry", title=animay, episode=episode)
            appendtxt += time_data + "\n\n"

        self.logger.info(f"{server_id}: sending result...")
        if appendtxt != "":
            return await ctx.send(appendtxt.strip())
        await ctx.send(ctx.t("jadwal.empty"))
        if is_error:
            await ctx.send(ctx.t("jadwal.anilist_error"))


async def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesUser(bot))
