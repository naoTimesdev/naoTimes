# -*- coding: utf-8 -*-

import argparse
import asyncio
import shlex

import aiohttp
import discord
import discord.ext.commands as commands
from bs4 import BeautifulSoup

import ujson

with open("config.json", "r") as fp:
    bot_config = ujson.load(fp)


class ArgumentParserError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class HelpException(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class BotArgumentParser(argparse.ArgumentParser):
    def print_help(self, file=None):
        raise HelpException(self.format_help())

    def exit(self, status=0, message=None):
        raise HelpException(message)

    def error(self, message=None):
        raise ArgumentParserError(message)


def humanbytes(B: int) -> str:
    """Return the given bytes as a human friendly KB, MB, GB, or TB string"""
    B = float(B)  # type: ignore
    KB = float(1024)
    MB = float(KB ** 2)  # 1,048,576
    GB = float(KB ** 3)  # 1,073,741,824
    TB = float(KB ** 4)  # 1,099,511,627,776
    PB = float(KB ** 5)

    if B < KB:
        return "{0} {1}".format(B, "Bytes" if 0 == B > 1 else "Byte")
    elif KB <= B < MB:
        return "{0:.2f} KiB".format(B / KB)
    elif MB <= B < GB:
        return "{0:.2f} MiB".format(B / MB)
    elif GB <= B < TB:
        return "{0:.2f} GiB".format(B / GB)
    elif TB <= B:
        return "{0:.2f} TiB".format(B / TB)
    elif PB <= B:
        return "{0:.2f} PiB".format(B / PB)


def parse_error(err_str):
    if err_str.startswith("unrecognized arguments"):
        err_str = err_str.replace("unrecognized arguments", "Argumen tidak diketahui")
    elif err_str.startswith("the following arguments are required"):
        err_str = err_str.replace("the following arguments are required", "Argumen berikut wajib diberikan",)
    if "usage" in err_str:
        err_str = (
            err_str.replace("usage", "Gunakan")
            .replace("positional arguments", "Argumen yang diwajibkan")
            .replace("optional arguments", "Argumen opsional")
            .replace("show this help message and exit", "Perlihatkan bantuan perintah",)
        )
    return err_str


def parse_args(str_txt: str, s: str, search_mode=True):
    """parse an argument that passed"""
    parser = BotArgumentParser(
        prog="!nyaa " + s, usage="!nyaa " + s, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    if search_mode:
        parser.add_argument("input", help="Apa yang mau dicari")
    parser.add_argument(
        "--category",
        "-C",
        required=False,
        default="all",
        dest="kategori",
        action="store",
        help="Kategori pencarian - cek dengan !nyaa kategori",
    )
    parser.add_argument(
        "--user",
        "-u",
        required=False,
        default=None,
        dest="user",
        action="store",
        help="Cari torrent hanya pada user yang diberikan",
    )
    parser.add_argument(
        "--sukebei", "-nsfw", required=False, dest="sukebei", action="store_true", help="Mode Sukebei",
    )
    parser.add_argument(
        "--trusted",
        required=False,
        dest="trust_only",
        action="store_true",
        help="Filter untuk torrent trusted saja",
    )
    parser.add_argument(
        "--no-remake",
        "-nr",
        required=False,
        dest="no_remake",
        action="store_true",
        help="Filter untuk torrent yang bukan remake/merah",
    )
    try:
        return parser.parse_args(shlex.split(str_txt))
    except ArgumentParserError as argserror:
        return str(argserror)
    except HelpException as help_:
        return "```\n" + str(help_) + "\n```"


def get_kategori(sukebei=False):
    if not sukebei:
        category_type = {
            "all": "0_0",
            "anime": "1_0",
            "amv": "1_1",
            "anime_eng": "1_2",
            "anime_non-eng": "1_3",
            "anime_raw": "1_4",
            "audio": "2_0",
            "audio_lossless": "2_1",
            "audio_lossy": "2_2",
            "books": "3_0",
            "books_eng": "3_1",
            "books_non-eng": "3_2",
            "books_raw": "3_3",
            "live_action": "4_0",
            "la_eng": "4_1",
            "la_idolpv": "4_2",
            "la_non-eng": "4_3",
            "la_raw": "4_4",
            "pictures": "5_0",
            "pics_graphics": "5_1",
            "pics_photos": "5_2",
            "software": "6_0",
            "sw_apps": "6_1",
            "sw_games": "6_2",
        }
    if sukebei:
        category_type = {
            "all": "0_0",
            "art": "1_0",
            "art_anime": "1_1",
            "art_doujinshi": "1_2",
            "art_games": "1_3",
            "art_manga": "1_4",
            "art_pics": "1_5",
            "real_life": "2_0",
            "real_pics": "2_1",
            "real_videos": "2_2",
        }
    return category_type


def api_url(sukebei=False):
    if sukebei:
        return "https://sukebei.nyaa.si/", "https://sukebei.nyaa.si/api/"
    return "https://nyaa.si/", "https://nyaa.si/api/"


async def parse_querylist(querylist):
    """
    querylist: <table tr> from SearchTorrent

    #Stolen from NyaaPy
    """
    maximum = len(querylist)
    torrentslist = []

    for query in querylist[:maximum]:
        temp = []

        for td in query.find_all("td"):
            if td.find_all("a"):
                for link in td.find_all("a"):
                    if link.get("href")[-9:] != "#comments":
                        temp.append(link.get("href"))
                        if link.text.rstrip():
                            temp.append(link.text)
            if td.text.rstrip():
                temp.append(td.text.strip())

        try:
            tordata = {
                "id": temp[1].replace("/view/", ""),
                "download_link": temp[4],
            }
            torrentslist.append(tordata)
        except IndexError:
            pass

    return torrentslist


async def check_user(user, sukebei=False):
    _NYAA_URL, _NYAA_API_URL = api_url(sukebei)
    url_search = "{base}user/{user_}".format(base=_NYAA_URL, user_=user,)
    async with aiohttp.ClientSession() as sesi:
        async with sesi.get(url_search) as r:
            await r.text()
            if r.status != 200:
                return False
    return True


async def fetch_nyaa(
    keyword=None, category="all", trusted=False, nr=False, user=None, sukebei=False,
):
    """
    Search and parse info from Nyaa.si
    """
    kategori_list = get_kategori(sukebei)
    if category not in kategori_list:
        return "Kategori tidak diketahui. cek lagi dengan `!nyaa kategori`"

    if trusted and nr:
        return "Pilih antara `--trusted` atau `--no-remake` (Hanya bisa salah satu)"  # noqa: E501

    filter_n = 0
    if nr:
        filter_n = 1
    if trusted:
        filter_n = 2

    _NYAA_URL, _NYAA_API_URL = api_url(sukebei)

    url_search = "{base}{user_}?f={fc}&c={cc}&q={q_}".format(
        base=_NYAA_URL,
        user_="user/" + user if user is not None else "",
        fc=filter_n,
        cc=kategori_list[category],
        q_=keyword if keyword is not None else "",
    )

    if user:
        user_exist = await check_user(user, sukebei)
        if not user_exist:
            return "Tidak dapat menemukan user tersebut."

    async with aiohttp.ClientSession() as sesi:
        try:
            async with sesi.get(url_search) as r:
                data = await r.text()
                if r.status != 200:
                    if r.status == 404:
                        return "Tidak ada hasil"
                    elif r.status == 500:
                        return "Terjadi kesalahan Internal dari server"
        except aiohttp.ClientError:
            return "Koneksi error"

    parsed = BeautifulSoup(data, "html.parser")
    queried = parsed.select("table tr")

    full_queries = await parse_querylist(queried)
    if not keyword:  # assume !nyaa terbaru
        full_queries = full_queries[:10]  # Limit to 10 results
    if len(full_queries) > 15:
        full_queries = full_queries[:15]

    torrents = []

    NYAA_EMAIL, NYAA_PASS = (
        bot_config["nyaasi"]["username"],
        bot_config["nyaasi"]["password"],
    )
    if not NYAA_EMAIL or not NYAA_PASS:
        return "Perintah Nyaa.si tidak bisa digunakan karena bot tidak diberikan informasi login untuk Nyaa.si\nCek `config.json` untuk memastikannya."  # noqa: E501

    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(NYAA_EMAIL, NYAA_PASS)) as sesi:
        for query in full_queries:
            tor_id = query["id"]
            dl_link = query["download_link"]

            async with sesi.get("{base}info/{id}".format(base=_NYAA_API_URL, id=tor_id)) as r:
                try:
                    r2j = await r.json()
                except IndexError:
                    return "ERROR: Terjadi kesalahan internal"

            name = r2j["name"]
            create_date = r2j["creation_date"]
            description = r2j["description"]
            information = r2j["information"]
            submitter = r2j["submitter"]
            url = r2j["url"]
            magnet = r2j["magnet"]

            filesize = humanbytes(r2j["filesize"])
            torhash = r2j["hash_hex"]
            is_trusted = r2j["is_trusted"]
            is_remake = r2j["is_remake"]

            categoryN = "{} - {}".format(r2j["main_category"], r2j["sub_category"])
            categoryID = "{}_{}".format(r2j["main_category_id"], r2j["sub_category_id"])

            seeds = r2j["stats"]["seeders"]
            leechs = r2j["stats"]["leechers"]
            downs = r2j["stats"]["downloads"]

            dataset = {
                "id": tor_id,
                "name": name,
                "information": information,
                "description": description,
                "submitter": submitter,
                "creation": create_date,
                "filesize": filesize,
                "hash": torhash,
                "category": categoryN,
                "category_id": categoryID,
                "seeders": seeds,
                "leechers": leechs,
                "completed": downs,
                "download_link": _NYAA_URL[:-1] + dl_link,
                "magnet_link": magnet,
                "url": url,
                "is_trusted": is_trusted,
                "is_remake": is_remake,
            }
            torrents.append(dataset)

    return {"result": torrents, "data_total": len(torrents)}


def color_bar(t_=False, r_=False):
    if t_:
        return 0xA7D195
    elif r_:
        return 0xD88787
    return 0x337AB7


class NyaaTorrentsV2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    @commands.guild_only()
    async def nyaa(self, ctx):
        if not ctx.invoked_subcommand:
            helpmain = discord.Embed(
                title="Bantuan Perintah (!nyaa)", description="versi 2.0.0", color=0x00AAAA,
            )
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(
                name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png",
            )
            helpmain.add_field(
                name="!nyaa", value="```Memunculkan bantuan perintah```", inline=False,
            )
            helpmain.add_field(
                name="!nyaa cari <argumen>",
                value="```Mencari torrent di nyaa.si " "(gunakan argumen -h untuk melihat bantuan)```",
                inline=False,
            )
            helpmain.add_field(
                name="!nyaa terbaru <argumen>",
                value="```Melihat 10 torrents terbaru " "(gunakan argumen -h untuk melihat bantuan)```",
                inline=False,
            )
            helpmain.add_field(
                name="!nyaa kategori <tipe>",
                value="```Melihat kategori apa aja yang bisa dipakai"
                "\n<tipe> ada 2 yaitu, normal dan sukebei```",
                inline=False,
            )
            helpmain.add_field(name="Aliases", value="Tidak ada", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes " "|| Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)

    @nyaa.command(aliases=["category"])
    async def kategori(self, ctx, d_="normal"):
        if "sukebei" in d_ or "nsfw" in d_:
            dataset = {
                "all": "Semua Kategori",
                "art": 'Semua Kategori - "Art"',
                "art_anime": "Art - Anime",
                "art_doujinshi": "Art - Doujinshi",
                "art_games": "Art - Games",
                "art_manga": "Art - Manga",
                "art_pics": "Art - Gambar/Photobook",
                "real_life": "Semua Kategori - Real Life",
                "real_pics": "RL - Photobook",
                "real_videos": "RL - Video",
            }
        elif "normal" in d_:
            dataset = {
                "all": "Semua Kategori",
                "anime": "Semua Kategori - Anime",
                "amv": "AMV",
                "anime_eng": "Anime - Eng TL",
                "anime_non-eng": "Anime - Non Eng TL",
                "anime_raw": "Anime - Raw",
                "audio": "Semua Kategori - Musik",
                "audio_lossless": "Musik - Lossless",
                "audio_lossy": "Musik - Lossy (MP3)",
                "books": "Semua Kategori - Buku/Manga",
                "books_eng": "Buku - Eng TL",
                "books_non-eng": "Buku - Non Eng TL",
                "books_raw": "Buku - Raw",
                "live_action": "Semua Kategori - Live Action",
                "la_eng": "Live Action - Eng TL",
                "la_idolpv": "Idol/PV",
                "la_non-eng": "Live Action - Non Eng TL",
                "la_raw": "Live Action - Raw",
                "pictures": "Semua Kategori - Gambar",
                "pics_graphics": "Gambar - Digital",
                "pics_photos": "Gambar - Foto",
                "software": "Aplikasi & Games",
                "sw_apps": "Aplikasi",
                "sw_games": "Games",
            }
        else:
            return await ctx.send("Tipe hanya ada `normal` dan `sukebei`")

        text = "**Berikut adalah kategori untuk hal yang berbau *{}***\n**Format Penulisan**: *Kode* - *Nama*\n".format(  # noqa: E501
            d_.upper()
        )
        for k, v in dataset.items():
            if v.startswith("Semua"):
                text += "\n"
            text += "**`{}`** - **{}**\n".format(k, v)

        msg = await ctx.send(text)
        reactmoji = ["✅"]
        for react in reactmoji:
            await msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in reactmoji:
                return False
            return True

        res, user = await self.bot.wait_for("reaction_add", check=check_react)
        if user != ctx.message.author:
            pass
        elif "✅" in str(res.emoji):
            await msg.clear_reactions()
            await ctx.message.delete()
            return await msg.delete()

    @nyaa.command(aliases=["search"])
    async def cari(self, ctx, *, args_="-h"):
        args = parse_args(args_, "cari")
        if isinstance(args, str):
            return await ctx.send(parse_error(args))
        nqres = await fetch_nyaa(
            args.input, args.kategori, args.trust_only, args.no_remake, args.user, args.sukebei,
        )
        if isinstance(nqres, str):
            return await ctx.send(nqres)

        max_page = nqres["data_total"]
        resdata = nqres["result"]

        first_run = True
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                embed = discord.Embed(color=color_bar(data["is_trusted"], data["is_remake"]))
                embed.set_author(
                    name=data["name"],
                    url=data["url"],
                    icon_url="https://nyaa.si/static/img/avatar/default.png",
                )
                embed.set_footer(text="{} | Dibuat: {}".format(data["id"], data["creation"]))

                se, le, co = (
                    data["seeders"],
                    data["leechers"],
                    data["completed"],
                )
                dl_link_fmt = "📥 \|| **[Torrent]({t})**".format(t=data["download_link"])  # noqa: W605

                embed.add_field(name="Uploader", value=data["submitter"], inline=True)
                embed.add_field(
                    name="Kategori (ID)",
                    value=data["category"] + " ({})".format(data["category_id"]),
                    inline=True,
                )
                embed.add_field(
                    name="Stats",
                    value="**Seeders**: {}\n**Leechers**: {}\n**Completed**: {}".format(  # noqa: E501
                        se, le, co
                    ),
                    inline=False,
                )
                embed.add_field(name="Ukuran", value=data["filesize"], inline=True)
                embed.add_field(name="Download", value=dl_link_fmt, inline=False)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                break
            elif num == 1:
                reactmoji.append("⏩")
            elif num == max_page:
                reactmoji.append("⏪")
            elif num > 1 and num < max_page:
                reactmoji.extend(["⏪", "⏩"])
            for reaction in reactmoji:
                await msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                num = num - 1
                data = resdata[num - 1]

                embed = discord.Embed(color=color_bar(data["is_trusted"], data["is_remake"]))
                embed.set_author(
                    name=data["name"],
                    url=data["url"],
                    icon_url="https://nyaa.si/static/img/avatar/default.png",
                )
                embed.set_footer(text="{} | Dibuat: {}".format(data["id"], data["creation"]))

                se, le, co = (
                    data["seeders"],
                    data["leechers"],
                    data["completed"],
                )
                dl_link_fmt = "📥 \|| **[Torrent]({t})**".format(t=data["download_link"])  # noqa: W605

                embed.add_field(name="Uploader", value=data["submitter"], inline=True)
                embed.add_field(
                    name="Kategori (ID)",
                    value=data["category"] + " ({})".format(data["category_id"]),
                    inline=True,
                )
                embed.add_field(
                    name="Stats",
                    value="**Seeders**: {}\n**Leechers**: {}\n**Completed**: {}".format(  # noqa: E501
                        se, le, co
                    ),
                    inline=False,
                )
                embed.add_field(name="Ukuran", value=data["filesize"], inline=True)
                embed.add_field(name="Download", value=dl_link_fmt, inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                num = num + 1
                data = resdata[num - 1]

                embed = discord.Embed(color=color_bar(data["is_trusted"], data["is_remake"]))
                embed.set_author(
                    name=data["name"],
                    url=data["url"],
                    icon_url="https://nyaa.si/static/img/avatar/default.png",
                )
                embed.set_footer(text="{} | Dibuat: {}".format(data["id"], data["creation"]))

                se, le, co = (
                    data["seeders"],
                    data["leechers"],
                    data["completed"],
                )
                dl_link_fmt = "📥 \|| **[Torrent]({t})**".format(t=data["download_link"])  # noqa: W605

                embed.add_field(name="Uploader", value=data["submitter"], inline=True)
                embed.add_field(
                    name="Kategori (ID)",
                    value=data["category"] + " ({})".format(data["category_id"]),
                    inline=True,
                )
                embed.add_field(
                    name="Stats",
                    value="**Seeders**: {}\n**Leechers**: {}\n**Completed**: {}".format(  # noqa: E501
                        se, le, co
                    ),
                    inline=False,
                )
                embed.add_field(name="Ukuran", value=data["filesize"], inline=True)
                embed.add_field(name="Download", value=dl_link_fmt, inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)

    @nyaa.command(aliases=["latest"])
    async def terbaru(self, ctx, *, args_="-h"):
        args = parse_args(args_, "terbaru", False)
        if isinstance(args, str):
            return await ctx.send(parse_error(args))
        nqres = await fetch_nyaa(
            None, args.kategori, args.trust_only, args.no_remake, args.user, args.sukebei,
        )
        if isinstance(nqres, str):
            return await ctx.send(nqres)

        max_page = nqres["data_total"]
        resdata = nqres["result"]

        first_run = True
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                embed = discord.Embed(color=color_bar(data["is_trusted"], data["is_remake"]))
                embed.set_author(
                    name=data["name"],
                    url=data["url"],
                    icon_url="https://nyaa.si/static/img/avatar/default.png",
                )
                embed.set_footer(text="{} | Dibuat: {}".format(data["id"], data["creation"]))

                se, le, co = (
                    data["seeders"],
                    data["leechers"],
                    data["completed"],
                )
                dl_link_fmt = "📥 \|| **[Torrent]({t})**".format(t=data["download_link"])  # noqa: w605

                embed.add_field(name="Uploader", value=data["submitter"], inline=True)
                embed.add_field(
                    name="Kategori (ID)",
                    value=data["category"] + " ({})".format(data["category_id"]),
                    inline=True,
                )
                embed.add_field(
                    name="Stats",
                    value="**Seeders**: {}\n**Leechers**: {}\n**Completed**: {}".format(  # noqa: E501
                        se, le, co
                    ),
                    inline=False,
                )
                embed.add_field(name="Ukuran", value=data["filesize"], inline=True)
                embed.add_field(name="Download", value=dl_link_fmt, inline=False)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                break
            elif num == 1:
                reactmoji.append("⏩")
            elif num == max_page:
                reactmoji.append("⏪")
            elif num > 1 and num < max_page:
                reactmoji.extend(["⏪", "⏩"])
            for reaction in reactmoji:
                await msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                num = num - 1
                data = resdata[num - 1]

                embed = discord.Embed(color=color_bar(data["is_trusted"], data["is_remake"]))
                embed.set_author(
                    name=data["name"],
                    url=data["url"],
                    icon_url="https://nyaa.si/static/img/avatar/default.png",
                )
                embed.set_footer(text="{} | Dibuat: {}".format(data["id"], data["creation"]))

                se, le, co = (
                    data["seeders"],
                    data["leechers"],
                    data["completed"],
                )
                dl_link_fmt = "📥 \|| **[Torrent]({t})**".format(t=data["download_link"])  # noqa: W605

                embed.add_field(name="Uploader", value=data["submitter"], inline=True)
                embed.add_field(
                    name="Kategori (ID)",
                    value=data["category"] + " ({})".format(data["category_id"]),
                    inline=True,
                )
                embed.add_field(
                    name="Stats",
                    value="**Seeders**: {}\n**Leechers**: {}\n**Completed**: {}".format(  # noqa: E501
                        se, le, co
                    ),
                    inline=False,
                )
                embed.add_field(name="Ukuran", value=data["filesize"], inline=True)
                embed.add_field(name="Download", value=dl_link_fmt, inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                num = num + 1
                data = resdata[num - 1]

                embed = discord.Embed(color=color_bar(data["is_trusted"], data["is_remake"]))
                embed.set_author(
                    name=data["name"],
                    url=data["url"],
                    icon_url="https://nyaa.si/static/img/avatar/default.png",
                )
                embed.set_footer(text="{} | Dibuat: {}".format(data["id"], data["creation"]))

                se, le, co = (
                    data["seeders"],
                    data["leechers"],
                    data["completed"],
                )
                dl_link_fmt = "📥 \|| **[Torrent]({t})**".format(t=data["download_link"])  # noqa: W605

                embed.add_field(name="Uploader", value=data["submitter"], inline=True)
                embed.add_field(
                    name="Kategori (ID)",
                    value=data["category"] + " ({})".format(data["category_id"]),
                    inline=True,
                )
                embed.add_field(
                    name="Stats",
                    value="**Seeders**: {}\n**Leechers**: {}\n**Completed**: {}".format(  # noqa: E501
                        se, le, co
                    ),
                    inline=False,
                )
                embed.add_field(name="Ukuran", value=data["filesize"], inline=True)
                embed.add_field(name="Download", value=dl_link_fmt, inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)


def setup(bot):
    if True:
        # Skip
        return
    bot.add_cog(NyaaTorrentsV2(bot))
