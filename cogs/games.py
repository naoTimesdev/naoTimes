import logging
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands

from nthelper.cmd_args import Arguments, CommandArgParse
from nthelper.utils import DiscordPaginator
from nthelper.utils import __version__ as bot_version

logger = logging.getLogger("cogs.games")

steamdb_args = Arguments("steam dbcari")
steamdb_args.add_args("kueri", help="game/app/dlc yang ingin dicari.")
steamdb_args.add_args(
    "--dengan-dlc",
    "-dlc",
    required=False,
    dest="add_dlc",
    action="store_true",
    help="Tambahkan DLC ke kueri pencarian",
)
steamdb_args.add_args(
    "--dengan-app",
    "-app",
    required=False,
    dest="add_app",
    action="store_true",
    help="Tambahkan Applications ke kueri pencarian",
)
steamdb_args.add_args(
    "--dengan-musik",
    "-musik",
    required=False,
    dest="add_music",
    action="store_true",
    help="Tambahkan Music ke kueri pencarian",
)
steamdb_converter = CommandArgParse(steamdb_args)


async def requests(methods, url, **kwargs):
    async with aiohttp.ClientSession(
        headers={"User-Agent": f"naoTimes/{bot_version} (https://github.com/noaione/naoTimes)"}
    ) as sesi:
        methods_set = {
            "GET": sesi.get,
            "POST": sesi.post,
            "PUT": sesi.put,
            "PATCH": sesi.patch,
            "DELETE": sesi.delete,
        }
        request = methods_set.get(methods.upper())
        if request is None:
            return None, "Unknown request methods"
        async with request(url, **kwargs) as resp:
            res = await resp.json()
            if resp.status != 200:
                err_msg = res["error"]
                return None, err_msg
            if "error" in res:
                return None, res["error"]
            return res, "Success"


async def fetch_steam_status():
    logger.info("fetching steam status...")
    async with aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",  # noqa: E501
            "Origin": "https://steamstat.us",
            "Referer": "https://steamstat.us/",
        }
    ) as sesi:
        async with sesi.get("https://crowbar.steamstat.us/gravity.json") as resp:
            if resp.status != 200:
                logger.error(f"Cannot contact SteamStat.us, got error code: {resp.status}")
                return "Tidak dapat menghubungi SteamStat.us"
            try:
                res = await resp.json()
            except ValueError:
                logger.error("Failed to decode JSON data from SteamStat.us")
                return "Gagal mendapatkan status dari SteamStat.us"

    logger.info("remapping results...")
    csgo_server_mapping = {
        "csgo_eu_east": "Vienna, AT",
        "csgo_eu_north": "Stockholm, SWE",
        "csgo_poland": "Warsaw, PL",
        "csgo_spain": "Madrid, SPA",
        "csgo_eu_west": "Frankfurt, DE",
        "csgo_us_northeast": "Sterling, DC, USA",
        "csgo_us_southwest": "Los Angeles, CA, USA",
        "csgo_us_northcentral": "Chicago, USA",
        "csgo_us_northwest": "Moses Lake, WA, USA",
        "csgo_us_southeast": "Atlanta, GA, USA",
        "csgo_australia": "Syndey, AUS",
        "csgo_brazil": "Sao Paulo, BRA",
        "csgo_argentina": "Buenos Aires, ARG",
        "csgo_chile": "Santiago, CHI",
        "csgo_emirates": "Dubai, UAE",
        "csgo_india": "Mumbai, IND",
        "csgo_india_east": "Chennai, IND",
        "csgo_peru": "Lima, Peru",
        "csgo_japan": "Tokyo, JP",
        "csgo_hong_kong": "Hong Kong",
        "csgo_singapore": "Singapore",
        "csgo_south_africa": "Johannesburg, SA",
        "csgo_china_shanghai": "Shanghai, CN",
        "csgo_china_guangzhou": "Guangzhou, CN",
        "csgo_china_tianjin": "Tianjin, CN",
    }

    steam_cms_mappings = {
        "ams": "Amsterdam, NL",
        "vie": "Vienna, AT",
        "sto": "Stockholm, SWE",
        "waw": "Warsaw, PL",
        "mad": "Madrid, SPA",
        "fra": "Frankfurt, DE",
        "par": "Paris, FRA",
        "lhr": "London, UK",
        "iad": "Sterling, DC, USA",
        "lax": "Los Angeles, CA, USA",
        "ord": "Chicago, USA",
        "dfw": "Dallas, TX, USA",
        "sea": "Seattle, SF, USA",
        "syd": "Syndey, AUS",
        "gru": "Sao Paulo, BRA",
        "eze": "Buenos Aires, ARG",
        "scl": "Santiago, CHI",
        "lim": "Lima, Peru",
        "tyo": "Tokyo, JP",
        "hkg": "Hong Kong",
        "sgp": "Singapore",
        "jnb": "Johannesburg, SA",
        "sha": "Shanghai, CN",
    }

    main_mappings = {
        "artifact": "Artifact Game Coordinator",
        "csgo": "CS:GO Game Coordinator",
        "cms": "Steam Connection Managers",
        "dota2": "Dota 2 Game Coordinator",
        "ingame": "In-Game",
        "online": "Online",
        "store": "Steam Store",
        "tf2": "TF2 Game Coordinator",
        "underlords": "Underlords Game Coordinator",
        "webapi": "Steam Web API",
        "community": "Steam Community",
        "csgo_mm_scheduler": "CS:GO Matchmaker",
        "csgo_sessions": "CS:GO Sessions Logon",
        "csgo_community": "CS:GO Player Inventories",
    }

    online_status = res["online"]
    last_updated = datetime.fromtimestamp(res["time"], timezone.utc)
    last_updated_wib = last_updated.strftime("%a, %d %b %Y %H:%M:%S WIB")

    main_keys = list(main_mappings.keys())
    csgo_keys = list(csgo_server_mapping.keys())
    cms_keys = list(steam_cms_mappings.keys())

    remapped_shits = {
        "online": online_status,
        "services": {},
        "csgo_servers": {},
        "steam_cms": {},
        "last_update": last_updated_wib,
        "last_update_timestamp": last_updated,
    }

    for service, _, text_status in res["services"]:
        if service in main_keys:
            key_name = main_mappings[service]
            remapped_shits["services"][key_name] = text_status
        elif service in csgo_keys:
            key_name = csgo_server_mapping[service]
            remapped_shits["csgo_servers"][key_name] = text_status
        elif service in cms_keys:
            key_name = steam_cms_mappings[service]
            remapped_shits["steam_cms"][key_name] = text_status
    return remapped_shits


class GamesAPI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BASE_URL = "https://api.ihateani.me/v1/games/"
        self.logger = logging.getLogger("cogs.games.GamesAPI")

    @commands.command(aliases=["howlong", "howlongtobeat"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def hltb(self, ctx, *, game_name):
        self.logger.info(f"searching: {game_name}")
        request_param = {"q": game_name}
        results, msg = await requests("get", self.BASE_URL + "hltb", params=request_param)
        if results is None:
            self.logger.warning(f"{game_name}: no results.")
            return await ctx.send(msg)

        hltb_results = results["results"]

        async def _construct_embed(hltb_data: dict):
            embed = discord.Embed(
                title=hltb_data["title"], url=hltb_data["url"], color=hltb_data.get("color", 0x858585)
            )
            embed.set_thumbnail(url=hltb_data["image"])
            hltbs = hltb_data["hltb"]
            hltb_text = ""
            if hltbs["main"] is not None:
                hltb_text += "**Bagian Utama**: {}\n".format(hltbs["main"])
            if hltbs["main_extra"] is not None:
                hltb_text += "**Bagian Utama + Ekstra**: {}\n".format(hltbs["main_extra"])
            if hltbs["complete"] is not None:
                hltb_text += "**Perfeksionis**: {}\n".format(hltbs["complete"])
            hltb_text = hltb_text.rstrip("\n")
            hltb_text += f"\n\n*(Info lebih lanjut? [Klik Di sini]({hltb_data['url']}))*"  # noqa: E501

            embed.add_field(
                name="Seberapa lama untuk diselesaikan?", value=hltb_text, inline=False,
            )
            stats_data = []
            if hltb_data["stats"]:
                for st_name, st_stats in hltb_data["stats"].items():
                    txt = f"**{st_name.capitalize()}**: {st_stats}"
                    stats_data.append(txt)
            if stats_data != []:
                embed.add_field(name="Statistik", value="\n".join(stats_data), inline=False)
            embed.set_footer(
                text="Diprakasi oleh HowLongToBeat.com",
                icon_url="https://howlongtobeat.com/img/hltb_brand.png",
            )
            return embed

        self.logger.info(f"{game_name}: formatting results...")

        main_gen = DiscordPaginator(self.bot, ctx)
        main_gen.checker()
        main_gen.set_generator(_construct_embed)
        await main_gen.start(hltb_results, 30.0)

    @commands.group()
    @commands.guild_only()
    async def steam(self, ctx):
        if not ctx.invoked_subcommand:
            perintah = "**Perintah yang tersedia**\n\n"
            perintah += "- `!steam cari [kueri]` (cari game di steam)\n"
            perintah += "- `!steam info appID` (lihat info game/app)\n"
            perintah += "- `!steam user userID` (lihat info user)\n"
            perintah += "- `!steam status` (lihat status server steam)`"
            perintah += "- `!steam dbcari -h` (cari game di steam via steamdb)"
            await ctx.send(perintah)

    @staticmethod
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

    @steam.command(name="cari", aliases=["search"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def steam_cari(self, ctx, *, pencarian):
        self.logger.info(f"searching: {pencarian}")
        request_param = {"q": pencarian}
        sapp_fmt = "https://store.steampowered.com/app/{}/"
        results, msg = await requests("get", self.BASE_URL + "steamsearch", params=request_param)
        if results is None:
            self.logger.warning(f"{pencarian}: error: {msg}.")
            return await ctx.send(msg)

        ss_results = results["results"]
        if not ss_results:
            self.logger.warning(f"{pencarian}: no results.")
            return await ctx.send("Tidak ada hasil.")

        async def _construct_embed(sdb_data):
            embed = discord.Embed(title=sdb_data["title"], url=sapp_fmt.format(sdb_data["id"]))
            description = []
            platform = sdb_data["platforms"]
            platforms = []
            if platform["windows"]:
                platforms.append("Windows")
            if platform["mac"]:
                platforms.append("macOS")
            if platform["linux"]:
                platforms.append("Linux")
            description.append(" | ".join(platforms))
            if sdb_data["is_free"]:
                price_data = "**Harga**: Gratis!"
            else:
                price_data = "**Harga**: {}".format(sdb_data["price"])
            description.append(price_data)
            description.append("🎮 **Support**: {}".format(sdb_data["controller_support"]))
            embed.set_thumbnail(url=sdb_data["thumbnail"])
            embed.description = "\n".join(description)
            embed.set_footer(
                text="{} | Diprakasai oleh Steam Store API".format(sdb_data["id"]),
                icon_url="https://steamstore-a.akamaihd.net/public/shared/images/responsive/share_steam_logo.png",  # noqa: E501
            )
            return embed

        self.logger.info(f"{pencarian}: formatting...")
        main_gen = DiscordPaginator(self.bot, ctx)
        main_gen.checker()
        main_gen.set_generator(_construct_embed)
        await main_gen.start(ss_results, 30.0)

    @steam.command(name="info")
    async def steam_info(self, ctx, app_ids):
        self.logger.info(f"{app_ids}: searching to API.")
        sapp_fmt = "https://store.steampowered.com/app/{}/"
        if isinstance(app_ids, str):
            try:
                app_ids = int(app_ids)
            except ValueError:
                return await ctx.send("Bukan appID yang valid.")
        sdb_data, msg = await requests("get", self.BASE_URL + "steam/" + str(app_ids))
        if sdb_data is None:
            self.logger.warning(f"{app_ids}: error\n{msg}")
            return await ctx.send(msg)
        if sdb_data == {}:
            self.logger.warning(f"{app_ids}: no result.")
            return await ctx.send("Tidak dapat menemukan appID tersebut.")

        genres_list = [genre["description"] for genre in sdb_data["genres"]]
        category_list = [genre["description"] for genre in sdb_data["category"]]

        self.logger.info(f"{app_ids}: formatting results...")
        embed = discord.Embed(title=sdb_data["title"], url=sapp_fmt.format(sdb_data["id"]))
        description = []
        description.append(self.clean_description(sdb_data["description"]) + "\n")
        if sdb_data["is_free"]:
            price_data = "**Harga**: Gratis!"
        else:
            if "price_data" in sdb_data:
                price_info = sdb_data["price_data"]
                price_data = "**Harga**: {}".format(price_info["price"])
                if price_info["discount"]:
                    price_data += f" ({price_info['discounted']} discount)"  # noqa: E501
                    price_data += "\n**Harga Asli**: {}".format(price_info["original_price"])
            else:
                price_data = "**Harga**: TBD"
        description.append(price_data)
        platform = sdb_data["platforms"]
        platforms = []
        if platform["windows"]:
            platforms.append("Windows")
        if platform["mac"]:
            platforms.append("macOS")
        if platform["linux"]:
            platforms.append("Linux")
        description.append(" | ".join(platforms))
        if "total_achivements" in sdb_data:
            description.append("**Total Achivements**: {}".format(sdb_data["total_achivements"]))
        embed.set_thumbnail(url=sdb_data["thumbnail"])
        embed.description = "\n".join(description)
        embed.add_field(
            name="Developer",
            value="**Developer**: {}\n**Publisher**: {}".format(
                ", ".join(sdb_data["developer"]), ", ".join(sdb_data["publisher"]),
            ),
            inline=False,
        )
        if category_list:
            embed.add_field(name="Kategori", value=", ".join(category_list), inline=False)
        if genres_list:
            embed.add_field(name="Genre", value=", ".join(genres_list), inline=False)
        rls_ = sdb_data["released"]
        if rls_ is None:
            rls_ = "Segera!"
        embed.set_footer(
            text="Rilis: {} | Diprakasai oleh Steam Store API".format(rls_),
            icon_url="https://steamdb.info/static/logos/512px.png",
        )
        await ctx.send(embed=embed)

    @steam.command(name="user", aliases=["ui"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def steam_user(self, ctx, user_id):  # skipcq: PYL-W0613
        return await ctx.send("Soon™")

    @steam.command(name="status", aliases=["stat"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def steam_status(self, ctx: commands.Context):
        steam_statuses = await fetch_steam_status()
        if isinstance(steam_statuses, str):
            return await ctx.send(steam_statuses)

        emote_list = ["1️⃣", "2️⃣"]

        def _generator_csgo_servers(_d):
            embed = discord.Embed(
                title="CS:GO Servers", color=0x19212D, timestamp=steam_statuses["last_update_timestamp"],
            )
            embed.set_author(
                name="SteamStat.us",
                url="https://steamstat.us/",
                icon_url="https://p.ihateani.me/tjnjoeio.png",
            )
            embed.set_thumbnail(url="https://p.ihateani.me/tjnjoeio.png")
            descriptions = []
            for server_name, server_status in steam_statuses["csgo_servers"].items():
                descriptions.append(f"- **{server_name}**: {server_status}")
            if descriptions:
                embed.description = "\n".join(descriptions)
            else:
                embed.description = "No status for the CS:GO Servers"
            embed.set_footer(text="Powered by SteamStat.us")
            return embed

        def _generate_cms_servers(_d):
            embed = discord.Embed(
                title="CMS Servers", color=0x19212D, timestamp=steam_statuses["last_update_timestamp"],
            )
            embed.set_author(
                name="SteamStat.us",
                url="https://steamstat.us/",
                icon_url="https://p.ihateani.me/tjnjoeio.png",
            )
            embed.set_thumbnail(url="https://p.ihateani.me/tjnjoeio.png")
            descriptions = []
            for server_name, server_status in steam_statuses["steam_cms"].items():
                descriptions.append(f"- **{server_name}**: {server_status}")
            if descriptions:
                embed.description = "\n".join(descriptions)
            else:
                embed.description = "No status for the CMS"
            embed.set_footer(text="Powered by SteamStat.us")
            return embed

        def _generate_main_embed(_d):
            embed = discord.Embed(
                title="Services", color=0x19212D, timestamp=steam_statuses["last_update_timestamp"],
            )
            embed.set_author(
                name="SteamStat.us",
                url="https://steamstat.us/",
                icon_url="https://p.ihateani.me/tjnjoeio.png",
            )
            embed.set_thumbnail(url="https://p.ihateani.me/tjnjoeio.png")
            descriptions = []
            game_coords = [
                "TF2 Game Coordinator",
                "Dota 2 Game Coordinator",
                "Underlords Game Coordinator",
                "Artifact Game Coordinator",
                "CS:GO Game Coordinator",
            ]
            main_services = ["Steam Store", "Steam Community", "Steam Web API", "Steam Connection Managers"]
            csgo_helpers = ["CS:GO Sessions Logon", "CS:GO Player Inventories", "CS:GO Matchmaker"]
            steam_services = steam_statuses["services"]
            if "Online" in steam_services:
                descriptions.append(f"**Online**: {steam_services['Online']}")
            if "In-Game" in steam_services:
                descriptions.append(f"**In-Game** {steam_services['In-Game']}")
            services_collect = []
            for service in main_services:
                if service in steam_services:
                    services_collect.append(f"**{service}**: {steam_services[service]}")
            if services_collect:
                descriptions.extend(services_collect)
            services_collect = []
            for service in game_coords:
                if service in steam_services:
                    services_collect.append(f"**{service}**: {steam_services[service]}")
            if services_collect:
                descriptions.extend(services_collect)
            services_collect = []
            for service in csgo_helpers:
                if service in steam_services:
                    services_collect.append(f"**{service}**: {steam_services[service]}")
            if services_collect:
                descriptions.extend(services_collect)
            embed.add_field(name="More Info", value="1️⃣ CS:GO Servers\n2️⃣ Steam CMS")
            embed.description = "\n".join(descriptions).rstrip()
            embed.set_footer(text="Powered by SteamStat.us")
            return embed

        async def generator_child(datasets, position, message: discord.Message, emote: str):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return None, message
            if emote_pos == 0:
                generator_embed = _generator_csgo_servers
            elif emote_pos == 1:
                generator_embed = _generate_cms_servers
            await message.clear_reactions()
            custom_gen = DiscordPaginator(self.bot, ctx, [], True)
            custom_gen.set_generator(generator_embed)
            custom_gen.checker()
            await custom_gen.start([datasets[position]], 30.0, message)
            return None, message

        self.logger.info("starting embed generator")
        main_gen = DiscordPaginator(self.bot, ctx, emote_list, True)
        main_gen.checker()
        main_gen.set_generator(_generate_main_embed)
        main_gen.set_handler(0, lambda x, y: True, generator_child)
        main_gen.set_handler(1, lambda x, y: True, generator_child)
        await main_gen.start([steam_statuses], 30.0, None, True)
        await ctx.message.delete()

    @steam.command(name="dbcari", aliases=["searchdb"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def steam_steamdbcari(
        self, ctx, *, args: steamdb_converter = steamdb_converter.show_help()  # type: ignore
    ):
        thumbbase = "https://cdn.cloudflare.steamstatic.com/steam/apps/{}/header.jpg"  # noqa: E501
        sapp_fmt = "https://store.steampowered.com/app/{}/"
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        def true_false(bools):
            if bools:
                return 1
            return 0

        params = {
            "q": args.kueri,
            "dlc": true_false(args.add_dlc),
            "app": true_false(args.add_app),
            "music": true_false(args.add_music),
        }
        self.logger.info(f"searching: {args.kueri}")
        self.logger.info(
            f"{args.kueri}: with opts:\n"
            f">> DLC: {args.add_dlc}\n>> App: {args.add_app}"
            f"\n>> Musik: {args.add_music}"
        )
        results, msg = await requests("get", self.BASE_URL + "steamdbsearch", params=params)
        if results is None:
            self.logger.warning(f"{args.kueri}: error\n{msg}")
            return await ctx.send(msg)
        sdb_results = results["results"]
        if not sdb_results:
            self.logger.warning(f"{args.kueri}: no results.")
            return await ctx.send("Tidak ada hasil.")

        async def _construct_embed(sdb_data):
            embed = discord.Embed(title=sdb_data["title"], url=sapp_fmt.format(sdb_data["id"]))
            description = []
            if "price" in sdb_data:
                description.append("Harga: {}".format(sdb_data["price"]))
            if "user_score" in sdb_data:
                description.append("Skor: {}".format(sdb_data["user_score"]))
            platform = sdb_data["platforms"]
            platforms = []
            if platform["windows"]:
                platforms.append("Windows")
            if platform["mac"]:
                platforms.append("macOS")
            if platform["linux"]:
                platforms.append("Linux")
            description.append(" | ".join(platforms))
            embed.set_thumbnail(url=thumbbase.format(sdb_data["id"]))
            embed.description = "\n".join(description)
            embed.add_field(
                name="Developer",
                value="**Developer**: {}\n**Publisher**: {}".format(
                    sdb_data["developer"], sdb_data["publisher"]
                ),
                inline=False,
            )
            embed.add_field(
                name="Kategori", value=", ".join(sdb_data["categories"]), inline=False,
            )
            embed.add_field(name="Label", value=", ".join(sdb_data["tags"]), inline=False)
            embed.set_footer(
                text="Rilis: {} | {}-{} | Diprakasai oleh SteamDB".format(
                    sdb_data["released"], sdb_data["type"].capitalize(), sdb_data["id"],
                ),
                icon_url="https://steamdb.info/static/logos/512px.png",
            )
            return embed

        self.logger.info(f"{args.kueri}: formatting results...")
        main_gen = DiscordPaginator(self.bot, ctx)
        main_gen.checker()
        main_gen.set_generator(_construct_embed)
        await main_gen.start(sdb_results, 30.0)

    @hltb.error
    @steam_steamdbcari.error
    @steam_cari.error
    @steam_status.error
    async def games_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            perms = ["Manage Messages", "Embed Links", "Read Message History", "Add Reactions"]
            await ctx.send("Bot tidak memiliki salah satu dari perms ini:\n" + "\n".join(perms))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Perintah ini hanya bisa dijalankan di server.")


def setup(bot: commands.Bot):
    logger.debug("adding cogs...")
    bot.add_cog(GamesAPI(bot))
