import asyncio
import logging

import aiohttp
import discord
from discord.ext import commands
from nthelper import Arguments, CommandArgParse

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
        headers={"User-Agent": "naoTimes/2.0b"}
    ) as sesi:
        methods_set = {
            "GET": sesi.get,
            "POST": sesi.post,
            "PUT": sesi.put,
            "PATCH": sesi.patch,
            "DELETE": sesi.delete,
        }
        request = methods_set.get(methods.upper(), None)
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
    res, msg = await requests(
        "get", "https://crowbar.steamstat.us/gravity.json"
    )
    if res is None:
        return res, None


class GamesAPI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BASE_URL = "https://api.ihateani.me/games/"
        self.logger = logging.getLogger("cogs.games.GamesAPI")

    @commands.command(aliases=["howlong", "howlongtobeat"])
    @commands.guild_only()
    async def hltb(self, ctx, *, game_name):
        self.logger.info(f"searching: {game_name}")
        request_param = {"q": game_name}
        results, msg = await requests(
            "get", self.BASE_URL + "hltb", params=request_param
        )
        if results is None:
            self.logger.warn(f"{game_name}: no results.")
            return await ctx.send(msg)

        hltb_results = results["results"]

        async def _construct_embed(hltb_data: dict):
            embed = discord.Embed(
                title=hltb_data["title"],
                url=hltb_data["url"],
                color=hltb_data["color"],
            )
            embed.set_thumbnail(url=hltb_data["image"])
            hltbs = hltb_data["hltb"]
            hltb_text = ""
            if hltbs["main"] is not None:
                hltb_text += "**Bagian Utama**: {}\n".format(hltbs["main"])
            if hltbs["main_extra"] is not None:
                hltb_text += "**Bagian Utama + Ekstra**: {}\n".format(
                    hltbs["main_extra"]
                )
            if hltbs["complete"] is not None:
                hltb_text += "**Perfeksionis**: {}\n".format(hltbs["complete"])
            hltb_text = hltb_text.rstrip("\n")
            hltb_text += f"\n\n*(Info lebih lanjut? [Klik Di sini]({hltb_data['url']}))*"  # noqa: E501

            embed.add_field(
                name="Seberapa lama untuk diselesaikan?",
                value=hltb_text,
                inline=False,
            )
            stats_data = []
            if hltb_data["stats"]:
                for st_name, st_stats in hltb_data["stats"].items():
                    txt = f"**{st_name.capitalize()}**: {st_stats}"
                    stats_data.append(txt)
            if stats_data != []:
                embed.add_field(
                    name="Statistik", value="\n".join(stats_data), inline=False
                )
            embed.set_footer(
                text="Diprakasi oleh HowLongToBeat.com",
                icon_url="https://howlongtobeat.com/img/hltb_brand.png",
            )
            return embed

        self.logger.info(f"{game_name}: formatting results...")
        hltb_formatted = [
            await _construct_embed(data) for data in hltb_results
        ]

        first_run = True
        dataset_total = len(hltb_formatted)
        pos = 1
        self.logger.info(f"{game_name}: total {dataset_total} results")
        while True:
            if first_run:
                self.logger.info(f"{game_name}: sending results...")
                entri = hltb_formatted[pos - 1]
                msg = await ctx.send(embed=entri)
                first_run = False

            if dataset_total < 2:
                self.logger.info(f"{game_name}: only 1 results, exiting...")
                break
            elif pos == 1:
                to_react = ["⏩", "✅"]
            elif dataset_total == pos:
                to_react = ["⏪", "✅"]
            elif pos > 1 and pos < dataset_total:
                to_react = ["⏪", "⏩", "✅"]

            for react in to_react:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for(
                    "reaction_add", timeout=30.0, check=check_react
                )
            except asyncio.TimeoutError:
                self.logger.warn(f"{game_name}: timeout, clearing...")
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                self.logger.warn(f"{game_name}: clearing reaction...")
                return await msg.clear_reactions()
            elif "⏪" in str(res.emoji):
                self.logger.debug(f"{game_name}: going backward")
                await msg.clear_reactions()
                pos -= 1
                entri = hltb_formatted[pos - 1]
                await msg.edit(embed=entri)
            elif "⏩" in str(res.emoji):
                self.logger.debug(f"{game_name}: going forward")
                await msg.clear_reactions()
                pos += 1
                entri = hltb_formatted[pos - 1]
                await msg.edit(embed=entri)

    @commands.group()
    @commands.guild_only()
    async def steam(self, ctx):
        if not ctx.invoked_subcommand:
            perintah = "**Perintah yang tersedia**\n\n"
            perintah += "- `!steam cari [kueri]` (cari game di steam)\n"
            perintah += "- `!steam info appID` (lihat info game/app)\n"
            perintah += "- `!steam user userID` (lihat info user)\n"
            perintah += "- `!steam dbcari -h` (cari game di steam via steamdb)"
            await ctx.send(perintah)

    def clean_description(self, desc: str) -> str:
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
    async def steam_cari(self, ctx, *, pencarian):
        self.logger.info(f"searching: {pencarian}")
        request_param = {"q": pencarian}
        sapp_fmt = "https://store.steampowered.com/app/{}/"
        results, msg = await requests(
            "get", self.BASE_URL + "steamsearch", params=request_param
        )
        if results is None:
            self.logger.warn(f"{pencarian}: error: {msg}.")
            return await ctx.send(msg)

        ss_results = results["results"]
        if not ss_results:
            self.logger.warn(f"{pencarian}: no results.")
            return await ctx.send("Tidak ada hasil.")

        async def _construct_embed(sdb_data):
            embed = discord.Embed(
                title=sdb_data["title"], url=sapp_fmt.format(sdb_data["id"])
            )
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
            description.append(
                "🎮 **Support**: {}".format(sdb_data["controller_support"])
            )
            embed.set_thumbnail(url=sdb_data["thumbnail"])
            embed.description = "\n".join(description)
            embed.set_footer(
                text="{} | Diprakasai oleh Steam Store API".format(
                    sdb_data["id"]
                ),
                icon_url="https://steamstore-a.akamaihd.net/public/shared/images/responsive/share_steam_logo.png",  # noqa: E501
            )
            return embed

        self.logger.info(f"{pencarian}: formatting...")
        formatted_embed = [await _construct_embed(res) for res in ss_results]

        first_run = True
        dataset_total = len(formatted_embed)
        pos = 1
        self.logger.info(f"{pencarian}: total {dataset_total} results.")
        while True:
            if first_run:
                self.logger.info(f"{pencarian}: sending results")
                entri = formatted_embed[pos - 1]
                msg = await ctx.send(embed=entri)
                first_run = False

            if dataset_total < 2:
                self.logger.info(f"{pencarian}: no other results, exiting...")
                break
            elif pos == 1:
                to_react = ["⏩", "✅"]
            elif dataset_total == pos:
                to_react = ["⏪", "✅"]
            elif pos > 1 and pos < dataset_total:
                to_react = ["⏪", "⏩", "✅"]

            for react in to_react:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for(
                    "reaction_add", timeout=30.0, check=check_react
                )
            except asyncio.TimeoutError:
                self.logger.warn(f"{pencarian}: timeout!")
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                self.logger.warn(f"{pencarian}: clearing reactions...")
                return await msg.clear_reactions()
            elif "⏪" in str(res.emoji):
                self.logger.debug(f"{pencarian}: going backward")
                await msg.clear_reactions()
                pos -= 1
                entri = formatted_embed[pos - 1]
                await msg.edit(embed=entri)
            elif "⏩" in str(res.emoji):
                self.logger.debug(f"{pencarian}: going forward")
                await msg.clear_reactions()
                pos += 1
                entri = formatted_embed[pos - 1]
                await msg.edit(embed=entri)

    @steam.command(name="info")
    async def steam_info(self, ctx, app_ids):
        self.logger.info(f"{app_ids}: searching to API.")
        sapp_fmt = "https://store.steampowered.com/app/{}/"
        if isinstance(app_ids, str):
            try:
                app_ids = int(app_ids)
            except ValueError:
                return await ctx.send("Bukan appID yang valid.")
        sdb_data, msg = await requests(
            "get", self.BASE_URL + "steam/" + str(app_ids)
        )
        if sdb_data is None:
            self.logger.warn(f"{app_ids}: error\n{msg}")
            return await ctx.send(msg)
        if sdb_data == {}:
            self.logger.warn(f"{app_ids}: no result.")
            return await ctx.send("Tidak dapat menemukan appID tersebut.")

        genres_list = [genre["description"] for genre in sdb_data["genres"]]
        category_list = [
            genre["description"] for genre in sdb_data["category"]
        ]

        self.logger.info(f"{app_ids}: formatting results...")
        embed = discord.Embed(
            title=sdb_data["title"], url=sapp_fmt.format(sdb_data["id"])
        )
        description = []
        description.append(
            self.clean_description(sdb_data["description"]) + "\n"
        )
        if sdb_data["is_free"]:
            price_data = "**Harga**: Gratis!"
        else:
            if "price_data" in sdb_data:
                price_info = sdb_data["price_data"]
                price_data = "**Harga**: {}".format(price_info["price"])
                if price_info["discount"]:
                    price_data += (
                        f" ({price_info['discounted']} discount)"  # noqa: E501
                    )
                    price_data += "\n**Harga Asli**: {}".format(
                        price_info["original_price"]
                    )
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
            description.append(
                "**Total Achivements**: {}".format(
                    sdb_data["total_achivements"]
                )
            )
        embed.set_thumbnail(url=sdb_data["thumbnail"])
        embed.description = "\n".join(description)
        embed.add_field(
            name="Developer",
            value="**Developer**: {}\n**Publisher**: {}".format(
                ", ".join(sdb_data["developer"]),
                ", ".join(sdb_data["publisher"]),
            ),
            inline=False,
        )
        if category_list:
            embed.add_field(
                name="Kategori", value=", ".join(category_list), inline=False
            )
        if genres_list:
            embed.add_field(
                name="Genre", value=", ".join(genres_list), inline=False
            )
        rls_ = sdb_data["released"]
        if rls_ is None:
            rls_ = "Segera!"
        embed.set_footer(
            text="Rilis: {} | Diprakasai oleh Steam Store API".format(rls_),
            icon_url="https://steamdb.info/static/logos/512px.png",
        )
        await ctx.send(embed=embed)

    @steam.command(name="user", aliases=["ui"])
    async def steam_user(self, ctx, user_id):
        if True:
            return await ctx.send("Soon™")

    @steam.command(name="dbcari", aliases=["searchdb"])
    async def steam_steamdbcari(
        self, ctx, *, args: steamdb_converter = steamdb_converter.show_help()
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
        results, msg = await requests(
            "get", self.BASE_URL + "steamdbsearch", params=params
        )
        if results is None:
            self.logger.warn(f"{args.kueri}: error\n{msg}")
            return await ctx.send(msg)
        sdb_results = results["results"]
        if not sdb_results:
            self.logger.warn(f"{args.kueri}: no results.")
            return await ctx.send("Tidak ada hasil.")

        async def _construct_embed(sdb_data):
            embed = discord.Embed(
                title=sdb_data["title"], url=sapp_fmt.format(sdb_data["id"])
            )
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
                name="Kategori",
                value=", ".join(sdb_data["categories"]),
                inline=False,
            )
            embed.add_field(
                name="Label", value=", ".join(sdb_data["tags"]), inline=False
            )
            embed.set_footer(
                text="Rilis: {} | {}-{} | Diprakasai oleh SteamDB".format(
                    sdb_data["released"],
                    sdb_data["type"].capitalize(),
                    sdb_data["id"],
                ),
                icon_url="https://steamdb.info/static/logos/512px.png",
            )
            return embed

        self.logger.info(f"{args.kueri}: formatting results...")
        formatted_embed = [await _construct_embed(res) for res in sdb_results]

        first_run = True
        dataset_total = len(formatted_embed)
        pos = 1
        self.logger.info(f"{args.kueri}: total {dataset_total} results")
        while True:
            if first_run:
                self.logger.info(f"{args.kueri}: sending results...")
                entri = formatted_embed[pos - 1]
                msg = await ctx.send(embed=entri)
                first_run = False

            if dataset_total < 2:
                self.logger.warn(f"{args.kueri}: no other results, exiting...")
                break
            elif pos == 1:
                to_react = ["⏩", "✅"]
            elif dataset_total == pos:
                to_react = ["⏪", "✅"]
            elif pos > 1 and pos < dataset_total:
                to_react = ["⏪", "⏩", "✅"]

            for react in to_react:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for(
                    "reaction_add", timeout=30.0, check=check_react
                )
            except asyncio.TimeoutError:
                self.logger.warn(f"{args.kueri}: timeout, exiting...")
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                self.logger.warn(f"{args.kueri}: clearing, exiting...")
                return await msg.clear_reactions()
            elif "⏪" in str(res.emoji):
                self.logger.debug(f"{args.kueri}: going backward")
                await msg.clear_reactions()
                pos -= 1
                entri = formatted_embed[pos - 1]
                await msg.edit(embed=entri)
            elif "⏩" in str(res.emoji):
                self.logger.debug(f"{args.kueri}: going forward")
                await msg.clear_reactions()
                pos += 1
                entri = formatted_embed[pos - 1]
                await msg.edit(embed=entri)


def setup(bot: commands.Bot):
    logger.debug("adding cogs...")
    bot.add_cog(GamesAPI(bot))
