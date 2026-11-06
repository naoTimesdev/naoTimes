import logging
import math
import platform
from os import getpid

import discord
import psutil
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.utils import quote


def ping_emote(delta: float) -> str:
    if delta < 50:
        return ":race_car:"
    elif delta >= 50 and delta < 200:
        return ":blue_car:"
    elif delta >= 200 and delta < 500:
        return ":racehorse:"
    elif delta >= 200 and delta < 500:
        return ":runner:"
    elif delta >= 500 and delta < 3500:
        return ":walking:"
    return ":snail:"


def get_usage():
    process = psutil.Process(getpid())
    mem_info = process.memory_info()
    cpu_percent = process.cpu_percent(None)
    mb_used = round(mem_info.rss / 1024**2, 2)
    return mb_used, cpu_percent


def get_os_info() -> str:
    return f"{platform.system()} {platform.release()}"


def _format_count(value: int, locale: str) -> str:
    """Format a count with the locale's thousands separator."""
    formatted = f"{value:,}"
    if locale == "id":
        return formatted.replace(",", ".")
    return formatted


MAX_FIELD_VALUE = 1000


def add_chunked_field(embed: discord.Embed, name: str, lines: list[str], *, inline: bool = False) -> None:
    """Add a field, splitting long line lists across fields Discord accepts."""
    if not lines:
        return

    chunks: list[list[str]] = []
    current: list[str] = []
    current_length = 0
    for line in lines:
        addition = len(line) + (1 if current else 0)
        if current and current_length + addition > MAX_FIELD_VALUE:
            chunks.append(current)
            current = []
            current_length = 0
            addition = len(line)
        current.append(line)
        current_length += addition
    if current:
        chunks.append(current)

    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        label = name if total == 1 else f"{name} ({index}/{total})"
        embed.add_field(name=label, value=quote("\n".join(chunk)), inline=inline)


class BotbrainMeta(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Meta")

    @app_commands.command(
        name="ping",
        description=app_commands.locale_str("Cek koneksi bot", key="botbrain.ping.description"),
    )
    async def _bbmeta_ping(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        """Ping connection for the bot!"""

        def irnd(t):
            return round(t)

        self.logger.info("Checking Discord WS...")
        ws_ping = self.bot.latency
        self.logger.info("Checking Database...")
        if self.bot.ntdb is None:
            return await ctx.send(ctx.t("ping.db_unavailable"))
        db_res, db_ping = await self.bot.ntdb.ping_server()

        self.logger.info("Checking api.ihateani.me...")
        ihapi_res, ihaapi_ping = await self.bot.ping_website("https://api.ihateani.me/")

        self.logger.info("Checking anilist.co")
        ani_res, ani_ping = await self.bot.ping_website("https://graphql.anilist.co")

        def _gen_text(ping_res: bool, ping_pong: float, name: str):
            intern_res = ":x: "
            if ping_res:
                intern_res = f"{ping_emote(ping_pong)} "
            intern_res += ctx.t("ping.entry", name=name, value=f"{ping_pong}ms" if ping_res else "nan")
            return intern_res

        ihaapi_ping = irnd(ihaapi_ping)
        ani_ping = irnd(ani_ping)
        db_ping = irnd(db_ping)

        text_res = ctx.t("ping.header")
        self.logger.info("Checking Discord itself...")
        t1_dis = self.bot.now().timestamp()
        async with ctx.typing():
            t2_dis = self.bot.now().timestamp()
            dis_ping = irnd((t2_dis - t1_dis) * 1000)
            self.logger.info("Generating results...")
            text_res += "\n" + ctx.t("ping.discord", emote=ping_emote(dis_ping), ms=dis_ping)

            if not math.isnan(ws_ping):
                ws_time = irnd(ws_ping * 1000)
                ws_res = ctx.t("ping.websocket", emote=ping_emote(ws_time), ms=ws_time)
            else:
                ws_res = ctx.t("ping.websocket_nan")

            text_res += f"\n{ws_res}"
            text_res += f"\n{_gen_text(db_res, db_ping, 'Database')}"
            text_res += f"\n{_gen_text(ihapi_res, ihaapi_ping, 'naoTimes API')}"
            text_res += f"\n{_gen_text(ani_res, ani_ping, 'Anilist.co')}"
            self.logger.info("Sending results")
            await ctx.send(content=text_res)

    async def _quick_bot_statistics(self):
        server_lists = self.bot.guilds
        user_count = sum(guild.member_count or 0 for guild in server_lists)
        if self.bot.redisdb is None:
            return len(server_lists), user_count, 0
        showtimes_servers = await self.bot.redisdb.keys("showtimes_*")
        return len(server_lists), user_count, len(showtimes_servers)

    def _get_bot_creator(self, ctx: naoTimesContext):
        owner = self.bot._owner
        if owner is None:
            return ctx.t("info.unknown")
        excluded_owners = set(self.bot.config.owner_exclude)
        if not self.bot._is_team_bot:
            if owner.id in excluded_owners:
                return ctx.t("info.unknown")
            return self.bot.is_mentionable(ctx.guild, owner)

        team_name = self.bot._team_name or ctx.t("info.unknown")
        members_data = []
        if owner.id not in excluded_owners:
            members_data.append(self.bot.is_mentionable(ctx.guild, owner))
        if self.bot._team_members:
            for member in self.bot._team_members:
                if member.id == owner.id or member.id in excluded_owners:
                    continue
                resolved_member = self.bot.teams_to_user(member) if isinstance(member, discord.TeamMember) else member
                if isinstance(resolved_member, discord.User):
                    members_data.append(self.bot.is_mentionable(ctx.guild, resolved_member))
                else:
                    members_data.append(str(resolved_member))
        if not members_data:
            return team_name
        return f"{team_name} | {' '.join(members_data)}"

    @app_commands.command(
        name="info",
        description=app_commands.locale_str("Informasi tentang bot", key="botbrain.info.description"),
    )
    async def _bbmeta_info(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        """Get info about the bot!"""
        current_user = self.bot.user
        if current_user is None:
            return await ctx.send(ctx.t("info.user_unavailable"))
        infog = discord.Embed(
            description=ctx.t("info.embed_description"),
            color=0xDE8730,
        )
        infog.set_author(name=current_user.name, icon_url=current_user.avatar, url="https://naoti.me")
        semver = self.bot.semver
        infog.set_thumbnail(url=current_user.avatar)
        server_count, user_count, showtimes_count = await self._quick_bot_statistics()
        stats_text = ctx.t(
            "info.stats",
            servers=_format_count(server_count, ctx.locale),
            users=_format_count(user_count, ctx.locale),
            showtimes=_format_count(showtimes_count, ctx.locale),
        )
        infog.add_field(name=ctx.t("info.field_stats"), value=stats_text)
        memory, cpu = await self.bot.loop.run_in_executor(None, get_usage)
        peladen_info = ctx.t("info.host", memory=memory, cpu=cpu, os=get_os_info())
        infog.add_field(name=ctx.t("info.field_host"), value=peladen_info)
        py_ver = platform.python_version()
        bahasa_info = ctx.t("info.framework", python=py_ver, discord=discord.__version__)
        infog.add_field(name=ctx.t("info.field_framework"), value=bahasa_info)
        infog.add_field(
            name=ctx.t("info.field_creator"),
            value=ctx.t("info.creator", semver=semver, creator=self._get_bot_creator(ctx)),
        )
        uptime = self.bot.get_uptime(locale=ctx.locale)
        simple_ping = self.bot.latency
        if not math.isnan(simple_ping):
            ws_time = round(simple_ping * 1000)
            ws_res = ctx.t("info.ping_ms", ms=ws_time)
        else:
            ws_res = ctx.t("info.ping_unknown")
        infog.add_field(
            name=ctx.t("info.field_uptime"),
            value=ctx.t("info.uptime", uptime=uptime, ping=ws_res),
            inline=False,
        )
        infog.set_footer(text="👾 @kreator @noaione", icon_url="https://p.n4o.xyz/i/nao250px.png")
        await ctx.send(embed=infog)

    @app_commands.command(
        name="uptime",
        description=app_commands.locale_str("Lihat sudah berapa lama bot menyala", key="botbrain.uptime.description"),
    )
    async def _bbmeta_uptime(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        """Get bot uptime"""
        uptime = self.bot.get_uptime(detailed=True, locale=ctx.locale)
        await ctx.send(ctx.t("uptime.message", uptime=uptime))

    @app_commands.command(
        name="status",
        description=app_commands.locale_str("Cek status bot (owner)", key="botbrain.status.description"),
    )
    @app_commands.default_permissions(administrator=True)
    async def _bbmeta_status(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        """Check bot status.
        This would check loaded cogs, unloaded cogs.
        status of kbbi/vndb/fsdb connection.

        Parameters
        ----------
        ctx : naoTimesContext
            Bot context that are passed

        Returns
        -------
        None
        """

        all_extensions = await self.bot.available_extensions()
        self.logger.info("Checking loaded extensions...")
        loaded_extensions = list(dict(self.bot.extensions).keys())
        self.logger.info("Checking unloaded extensions...")
        unloaded_extensions = list(filter(lambda x: x not in loaded_extensions, all_extensions))

        loaded_extensions = list(map(lambda x: f"- {x}", loaded_extensions))
        unloaded_extensions = list(map(lambda x: f"- {x}", unloaded_extensions))

        self.logger.info("Checking KBBI/FSDB/VNDB/NTDB connection...")
        is_kbbi_auth = False
        if self.bot.kbbi:
            is_kbbi_auth = self.bot.kbbi.terautentikasi
        is_fsdb_loaded = self.bot.fsdb is not None
        is_vndb_ready = self.bot.vndb_client is not None
        ntdb = self.bot.ntdb

        def yn_stat(stat: bool) -> str:
            return ctx.t("status.connected") if stat else ctx.t("status.not_connected")

        # Get location etc.

        self.logger.info("Generating status...")
        embed = discord.Embed(title=ctx.t("status.embed_title"), description=ctx.t("status.embed_description"))
        if loaded_extensions:
            add_chunked_field(embed, ctx.t("status.field_loaded"), loaded_extensions)
        if unloaded_extensions:
            add_chunked_field(embed, ctx.t("status.field_unloaded"), unloaded_extensions)
        all_stat_test = []
        all_stat_test.append(ctx.t("status.kbbi_authed") if is_kbbi_auth else ctx.t("status.kbbi_not_authed"))
        all_stat_test.append(ctx.t("status.vndb_ready") if is_vndb_ready else ctx.t("status.vndb_unavailable"))
        if ntdb is not None:
            ntdb_text = ctx.t("status.ntdb_connected", host=ntdb.ip_hostname, port=ntdb.port)
            all_stat_test.append(ntdb_text)
        else:
            all_stat_test.append(ctx.t("status.ntdb_not_connected"))
        all_stat_test.append(ctx.t("status.fsdb", status=yn_stat(is_fsdb_loaded)))
        embed.add_field(name=ctx.t("status.field_connection"), value="\n".join(all_stat_test))
        embed.set_footer(text=ctx.t("status.footer", version=self.bot.semver))
        await ctx.send(embed=embed)

    @app_commands.command(
        name="undang",
        description=app_commands.locale_str("Link invite bot", key="botbrain.undang.description"),
    )
    async def _bb_meta_invite(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        embed = discord.Embed(
            title=ctx.t("undang.title"),
            description=ctx.t("undang.description_text"),
        )
        embed.set_thumbnail(url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)

    @app_commands.command(
        name="donasi",
        description=app_commands.locale_str("Dukung developer bot", key="botbrain.donasi.description"),
    )
    async def _bb_meta_donasi(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        embed = discord.Embed(
            title=ctx.t("donasi.title"),
            description=ctx.t("donasi.description_text"),
            color=0x1,
        )
        embed.set_thumbnail(url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)

    @app_commands.command(
        name="support",
        description=app_commands.locale_str("Bantuan dan support server", key="botbrain.support.description"),
    )
    async def _bb_meta_support(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        embed = discord.Embed(
            title=ctx.t("support.title"),
            description=ctx.t("support.description_text"),
            color=0x1,
        )
        embed.set_thumbnail(url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotbrainMeta(bot))
