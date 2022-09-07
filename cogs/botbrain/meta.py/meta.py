import logging
import platform
from os import getpid
from typing import List

import discord
import psutil
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


class BotbrainMeta(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Meta")

    @commands.command(name="ping")
    async def _bbmeta_ping(self, ctx: naoTimesContext):
        """Ping connection for the bot!"""
        irnd = lambda t: int(round(t))  # noqa: E731

        self.logger.info("Checking Discord WS...")
        ws_ping = self.bot.latency
        self.logger.info("Checking Database...")
        db_res, db_ping = await self.bot.ntdb.ping_server()

        self.logger.info("Checking api.ihateani.me...")
        ihapi_res, ihaapi_ping = await self.bot.ping_website("https://api.ihateani.me/")

        self.logger.info("Checking anilist.co")
        ani_res, ani_ping = await self.bot.ping_website("https://graphql.anilist.co")

        def _gen_text(ping_res: bool, ping_pong: float, name: str):
            intern_res = ":x: "
            if ping_res:
                intern_res = f"{ping_emote(ping_pong)} "
            intern_res += "{}: `{}`".format(name, "{}ms".format(ping_pong) if ping_res else "nan")
            return intern_res

        ihaapi_ping = irnd(ihaapi_ping)
        ani_ping = irnd(ani_ping)
        db_ping = irnd(db_ping)

        text_res = ":satellite: Ping Results :satellite:"
        self.logger.info("Checking Discord itself...")
        t1_dis = self.bot.now().timestamp()
        async with ctx.typing():
            t2_dis = self.bot.now().timestamp()
            dis_ping = irnd((t2_dis - t1_dis) * 1000)
            self.logger.info("Generating results...")
            text_res += f"\n{ping_emote(dis_ping)} Discord: `{dis_ping}ms`"

            if ws_ping != float("nan"):
                ws_time = irnd(ws_ping * 1000)
                ws_res = f"{ping_emote(ws_time)} Websocket `{ws_time}ms`"
            else:
                ws_res = ":x: Websocket: `nan`"

            text_res += f"\n{ws_res}"
            text_res += f"\n{_gen_text(db_res, db_ping, 'Database')}"
            text_res += f"\n{_gen_text(ihapi_res, ihaapi_ping, 'naoTimes API')}"
            text_res += f"\n{_gen_text(ani_res, ani_ping, 'Anilist.co')}"
            self.logger.info("Sending results")
            await ctx.send(content=text_res)

    async def _quick_bot_statistics(self):
        server_lists: List[discord.Guild] = self.bot.guilds
        showtimes_servers = await self.bot.redisdb.keys("showtimes_*")
        return len(server_lists), len(showtimes_servers)

    def _get_bot_creator(self, ctx: naoTimesContext):
        if not self.bot._is_team_bot:
            return self.bot.is_mentionable(ctx, self.bot._owner)

        res = f"{self.bot._team_name} | "
        members_data = []
        members_data.append(self.bot.is_mentionable(ctx, self.bot._owner))
        if self.bot._team_members:
            for member in self.bot._team_members:
                if member.id == self.bot._owner.id:
                    continue
                members_data.append(self.bot.is_mentionable(ctx, member))
        res += " ".join(members_data)
        return res

    @commands.command("info")
    async def _bbmeta_info(self, ctx: naoTimesContext):
        """Get info about the bot!"""
        infog = discord.Embed(
            description="Sebuah bot multifungsi untuk membantu tracking garapan Fansub!",
            color=0xDE8730,
        )
        infog.set_author(
            name=self.bot.user.name, icon_url=self.bot.user.avatar, url="https://naoti.me"  # noqa: E501
        )
        semver = self.bot.semver
        infog.set_thumbnail(url=self.bot.user.avatar)
        server_count, showtimes_count = await self._quick_bot_statistics()
        stats_text = f"🏬 **{server_count}** Peladen\n"
        stats_text += f"📺 **{showtimes_count}** Peladen dengan Showtimes\n"
        infog.add_field(name="📈 Statistik", value=stats_text)
        memory, cpu = await self.bot.loop.run_in_executor(None, get_usage)
        peladen_info = f"📊 **{memory}** MiB\n"
        peladen_info += f"🔥 CPU: {cpu}%\n"
        peladen_info += f"💻 {get_os_info()}\n"
        infog.add_field(name="💪 Host", value=peladen_info)
        py_ver = platform.python_version()
        bahasa_info = f"🐍 Python {py_ver}\n"
        bahasa_info += f"📚 discord.py {discord.__version__}"
        infog.add_field(name="🧾 Kerangka", value=bahasa_info)
        infog.add_field(name="🧠 Pembuat", value=f"🤖 naoTimes v{semver}\n👼 {self._get_bot_creator(ctx)}")
        uptime = self.bot.get_uptime()
        simple_ping = self.bot.latency
        if simple_ping != float("nan"):
            ws_time = int(round(simple_ping * 1000))
            ws_res = f"**{ws_time}** ms"
        else:
            ws_res = "??? ms"
        infog.add_field(name="⌚ Uptime", value=f"⌚ {uptime}\n🏓 {ws_res}", inline=False)
        infog.set_footer(text="👾 @kreator N4O#8868", icon_url="https://p.n4o.xyz/i/nao250px.png")
        await ctx.send(embed=infog)

    @commands.command("uptime")
    async def _bbmeta_uptime(self, ctx: naoTimesContext):
        """Get bot uptime"""
        uptime = self.bot.get_uptime(detailed=True)
        await ctx.send(f":alarm_clock: {uptime}")

    @commands.command("status")
    @commands.is_owner()
    async def _bbmeta_status(self, ctx: naoTimesContext):
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
        is_vndb_loaded = self.bot.vndb_socket is not None
        is_db_loaded = self.bot.ntdb is not None

        def yn_stat(stat: bool) -> str:
            return "Connected" if stat else "Not connected"

        # Get location etc.

        self.logger.info("Generating status...")
        embed = discord.Embed(title="Bot statuses", description=f"Global Prefix: {self.bot.prefix}")
        if len(loaded_extensions) > 0:
            embed.add_field(name="Loaded Cogs", value=quote("\n".join(loaded_extensions)), inline=False)
        if len(unloaded_extensions) > 0:
            embed.add_field(name="Unloaded Cogs", value=quote("\n".join(unloaded_extensions)), inline=False)
        all_stat_test = []
        all_stat_test.append(f"**KBBI**: {'Terautentikasi' if is_kbbi_auth else 'Tidak terautentikasi'}")
        all_stat_test.append(f"**VNDB**: {yn_stat(is_vndb_loaded)}")
        if is_db_loaded:
            ntdb_text = f"**naoTimesDB**: Connected [`{self.bot.ntdb.ip_hostname}:{self.bot.ntdb.port}`]"
            all_stat_test.append(ntdb_text)
        else:
            all_stat_test.append("**naoTimesDB**: Not connected")
        all_stat_test.append(f"**FansubDB**: {yn_stat(is_fsdb_loaded)}")
        embed.add_field(name="Connection Status", value="\n".join(all_stat_test))
        embed.set_footer(text=f"naoTimes versi {self.bot.semver}")
        await ctx.send(embed=embed)

    @commands.command(name="undang", aliases=["invite"])
    async def _bb_meta_invite(self, ctx: naoTimesContext):
        embed = discord.Embed(
            title="Ingin invite Bot ini? Klik link di bawah ini!",
            description="[Invite](https://ihateani.me/andfansub)"
            "\n[Support Server](https://discord.gg/7KyYecn) atau ketik "
            f"`{self.bot.prefixes(ctx)}tiket` di DM Bot."
            "\n[Dukung Dev-nya](https://trakteer.id/noaione)"
            "\n\n[Syarat dan Ketentuan](https://naoti.me/terms) | "
            "[Kebijakan Privasi](https://naoti.me/privasi)",
        )
        embed.set_thumbnail(url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)

    @commands.command(name="donasi", aliases=["donate"])
    async def _bb_meta_donasi(self, ctx: naoTimesContext):
        embed = discord.Embed(
            title="Donasi ke developer Bot!",
            description="Bantu biar developer botnya masih mau tetap"
            " maintenance bot naoTimes!"
            "\n[Trakteer](https://trakteer.id/noaione)"
            "\n[KaryaKarsa](https://karyakarsa.com/noaione)",
            color=0x1,
        )
        embed.set_thumbnail(url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)

    @commands.command(name="support")
    async def _bb_meta_support(self, ctx: naoTimesContext):
        embed = discord.Embed(
            title="Support!",
            description="Silakan Join [Support Server](https://discord.gg/7KyYecn)"
            "\ndan kunjungi #bantuan."
            f"\nATAU ketik `{self.bot.prefixes(ctx)}tiket` di DM Bot.",
            color=0x1,
        )
        embed.set_thumbnail(url="https://naoti.me/assets/img/nt192.png")
        await ctx.send(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotbrainMeta(bot))
