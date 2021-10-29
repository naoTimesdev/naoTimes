import logging
from typing import Literal

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.http.crowbar import ServerLoad, ServerStatus
from naotimes.paginator import DiscordPaginatorUI

HTTPMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


def clean_description(desc: str) -> str:
    mappings = {
        "&quot;": '"',
        "&amp;": "&",
        "&lt;": "<",
        "&rt;": ">",
        "&apos;": "'",
    }
    for src, dest in mappings.items():
        desc = desc.replace(src, dest)
    return desc


class PeninjauGameSteam(commands.Cog):
    IHABASE = "https://api.ihateani.me/v1/games/"
    APP_FORMAT = "https://store.steampowered.com/app/{}/"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.Gaming.Steam")

    @commands.group(name="steam")
    @commands.guild_only()
    async def _peninjau_game_steam(self, ctx: naoTimesContext):
        if not ctx.invoked_subcommand:
            perintah = "**Perintah yang tersedia**\n\n"
            perintah += "- `!steam cari [kueri]` (cari game di steam)\n"
            perintah += "- `!steam info appID` (lihat info game/app)\n"
            perintah += "- `!steam user userID` (lihat info user)\n"
            perintah += "- `!steam status` (lihat status server steam)`"
            perintah += "- `!steam dbcari -h` (cari game di steam via steamdb)"
            await ctx.send(perintah)

    async def _requests(self, method: HTTPMethod, url: str, **kwargs: dict):
        METHODS_MAP = {
            "GET": self.bot.aiosession.get,
            "POST": self.bot.aiosession.post,
            "PUT": self.bot.aiosession.put,
            "PATCH": self.bot.aiosession.patch,
            "DELETE": self.bot.aiosession.delete,
        }
        request = METHODS_MAP.get(method.upper())
        if request is None:
            return None, "Unknown request methods!"

        async with request(url, **kwargs) as response:
            res = await response.json()
            if response.status != 200:
                err_msg = res["error"]
                return None, err_msg
            if "error" in res:
                return None, res["error"]
            return res, "Success"

    @_peninjau_game_steam.command(name="cari")
    async def _peninjau_game_steam_cari(self, ctx: naoTimesContext, *, pencarian: str):
        self.logger.info(f"Searching for: {pencarian}")
        request_param = {"q": pencarian}
        results, msg = await self._requests("GET", self.IHABASE + "steam/search", params=request_param)
        if results is None:
            self.logger.warning(f"{pencarian}: error: {msg}.")
            return await ctx.send(msg)

        search_results = results["results"]
        if not search_results:
            self.logger.warning(f"{pencarian}: not found.")
            return await ctx.send("Tidak ada hasil.")

        def _stylize_embed(data: dict):
            embed = discord.Embed(title=data["title"], url=self.APP_FORMAT.format(data["id"]))
            descriptions = []
            platforms_data = data["platforms"]
            platforms = []
            if platforms_data["windows"]:
                platforms.append("Windows")
            if platforms_data["mac"]:
                platforms.append("macOS")
            if platforms_data["linux"]:
                platforms.append("Linux")
            descriptions.append(" | ".join(platforms))
            if "is_free" in data and data["is_free"]:
                price_data = "**Harga**: Gratis!"
            else:
                price_data = f"**Harga**: {data['price']}"

            descriptions.append(price_data)
            descriptions.append(f"🎮 **Support**: {data['controller_support']}")
            embed.description = "\n".join(descriptions)
            embed.set_thumbnail(url=data["thumbnail"])
            embed.set_footer(
                text=f"{data['id']} | Diprakasai oleh Steam Store API",
                icon_url="https://steamstore-a.akamaihd.net/public/shared/images/responsive/share_steam_logo.png",  # noqa: E501
            )
            return embed

        self.logger.info(f"{pencarian}: sending info...")
        ui_gen = DiscordPaginatorUI(ctx, items=search_results, timeout=30.0)
        ui_gen.attach(_stylize_embed)
        await ui_gen.interact()

    @_peninjau_game_steam.command(name="info")
    async def _peninjau_gaming_steam_info(self, ctx: naoTimesContext, app_id: str):
        self.logger.info(f"Getting info for {app_id}")
        if not app_id.isdigit():
            return await ctx.send("Bukan AppID yang valid.")

        result, msg = await self._requests("GET", self.IHABASE + "steam/game/" + app_id)
        if result is None:
            self.logger.warning(f"{app_id}: error: {msg}.")
            return await ctx.send(msg)
        if not result:
            self.logger.warning(f"{app_id}: no result.")
            return await ctx.send("Tidak dapat menemukan appID tersebut.")

        genres_list = list(map(lambda x: x["description"], result.get("genres", [])))
        category_list = list(map(lambda x: x["description"], result.get("category", [])))

        self.logger.info(f"{app_id}: formatting results...")
        embed = discord.Embed(title=result["title"], url=self.APP_FORMAT.format(result["id"]))
        embed_desc = []
        embed_desc.append(clean_description(result["description"]))
        if "is_free" in result and result["is_free"]:
            price_data = "**Harga**: Gratis!"
        else:
            price_info = result.get("price_data")
            if price_info:
                price_data = f"**Harga**: {price_info['price']}"
                if price_data["discount"]:
                    price_data += f" ({price_info['discounted']} discount)"  # noqa: E501
                    price_data += f"\n**Harga Asli**: {price_info['original_price']}"
            else:
                price_info = "**Harga**: TBD"
        embed_desc.append(price_data)
        platforms_data = result["platforms"]
        platforms = []
        if platforms_data["windows"]:
            platforms.append("Windows")
        if platforms_data["mac"]:
            platforms.append("macOS")
        if platforms_data["linux"]:
            platforms.append("Linux")
        embed_desc.append(" | ".join(platforms))
        if "total_achivements" in result:
            embed_desc.append(f"**Total Achievments**: {result['total_achivements']}")
        embed.description = "\n".join(embed_desc)
        embed.set_thumbnail(url=result["thumbnail"])
        developer = ", ".join(result["developer"])
        publisher = ", ".join(result["publisher"])
        embed.add_field(
            name="Developer", value=f"**Developer**: {developer}\n**Publisher**: {publisher}", inline=False
        )
        if category_list:
            embed.add_field(name="Kategori", value=", ".join(category_list), inline=False)
        if genres_list:
            embed.add_field(name="Genre", value=", ".join(genres_list), inline=False)
        rls_date = result["released"]
        if rls_date is None:
            rls_date = "Segera!"
        embed.set_footer(
            text=f"Rilis: {rls_date} | Diprakasai oleh Steam Store API",
            icon_url="https://steamdb.info/static/logos/512px.png",
        )
        await ctx.send(embed=embed)

    @staticmethod
    def _tl_server_load(server_load: ServerLoad):
        if server_load == ServerLoad.IDLE or server_load == ServerLoad.LOW:
            return "Rendah"
        elif server_load == ServerLoad.NORMAL:
            return "Normal"
        elif server_load == ServerLoad.MEDIUM:
            return "Menengah"
        elif server_load == ServerLoad.HIGH:
            return "Ramai"
        elif server_load == ServerLoad.SURGE:
            return "Terjadi lonjakan"
        elif server_load == ServerLoad.CRITICAL:
            return "Kritikal"
        elif server_load == ServerStatus.OFFLINE:
            return "Nonaktif"
        return "*Tidak diketahui*"

    @staticmethod
    def _tl_server_status(server_status: ServerStatus):
        if server_status == ServerStatus.NORMAL:
            return "Normal"
        elif server_status == ServerStatus.SLOW:
            return "Koneksi padat"
        elif server_status == ServerStatus.UNAVAILABLE:
            return "Tidak tersedia"
        elif server_status == ServerStatus.OFFLINE:
            return "Mati"
        return "*Tidak diketahui*"

    @_peninjau_game_steam.command(name="status", aliases=["stat"])
    async def _peninjau_gaming_steam_status(self, ctx: naoTimesContext):
        if self.bot.crowbar is None:
            return
        self.logger.info("Getting status...")
        steam_status = await self.bot.crowbar.get_status()
        HL_LOGO = "https://static.wikia.nocookie.net/half-life/images/d/dc/Lambda_logo.svg/revision/latest/scale-to-width-down/365?cb=20100327174546&path-prefix=en"  # noqa: E501

        embed = discord.Embed(
            title="Layanan Steam", color=0x19212D, timestamp=steam_status.timestamp.datetime
        )
        embed.set_author(
            name="Crowbar Inc.",
            icon_url="https://static.wikia.nocookie.net/half-life/images/c/c8/Lambdaspray_1a.png/revision/latest/scale-to-width-down/256?cb=20120621181914&path-prefix=en",  # noqa: E501
        )
        embed.set_thumbnail(url=HL_LOGO)
        services_collect = []
        if steam_status.online_count > 0:
            services_collect.append(f"**Daring**: {steam_status.online_count:,}")
        if steam_status.ingame_count > 0:
            services_collect.append(f"**Sedang bermain**: {steam_status.ingame_count:,}")
        services_collect.append(f"**Steam Store**: {self._tl_server_status(steam_status.store)}")
        services_collect.append(f"**Komunitas Steam**: {self._tl_server_status(steam_status.community)}")
        services_collect.append(f"**Steam Web API**: {self._tl_server_status(steam_status.webapi)}")

        game_coords = steam_status.coordinator
        game_coords_collect = []
        game_coords_collect.append(f"**CS:GO**: {self._tl_server_status(game_coords.csgo)}")
        game_coords_collect.append(f"**Dota 2**: {self._tl_server_status(game_coords.dota2)}")
        game_coords_collect.append(f"**Team Fortress 2**: {self._tl_server_status(game_coords.tf2)}")
        game_coords_collect.append(f"**Underlords**: {self._tl_server_status(game_coords.underlords)}")
        game_coords_collect.append(f"**Artifact**: {self._tl_server_status(game_coords.artifact)}")

        csgo_collect = []
        csgo_data = steam_status.csgo
        data_center_collect = []
        for datacenter in csgo_data.datacenters:
            data_center_collect.append(f"**{datacenter.name}**: {self._tl_server_load(datacenter.status)}")
        csgo_collect.append(f"**Autentikasi CS:GO**: {self._tl_server_load(csgo_data.sessions)}")
        csgo_collect.append(f"**Inventaris CS:GO**: {self._tl_server_load(csgo_data.inventories)}")
        csgo_collect.append(f"***Matchmaker* CS:GO**: {self._tl_server_load(csgo_data.matchmaking)}")

        embed.description = "\n".join(services_collect)
        embed.add_field(
            name="Koordinator Gim",
            value="\n".join(game_coords_collect),
            inline=True,
        )
        embed.add_field(name="Informasi Peladen CS:GO", value="\n".join(csgo_collect), inline=False)
        embed.add_field(name="CS:GO Datacenter", value="\n".join(data_center_collect), inline=False)
        embed.set_footer(text="🛠️ Crowbar Powered")

        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(PeninjauGameSteam(bot))
