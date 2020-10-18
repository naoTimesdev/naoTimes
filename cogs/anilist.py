# -*- coding: utf-8 -*-

import asyncio
import logging
import time
from copy import deepcopy
from datetime import datetime, timedelta
from math import ceil

import aiohttp
import discord
import discord.ext.commands as commands
from bs4 import BeautifulSoup

from nthelper.bot import naoTimesBot

anilog = logging.getLogger("cogs.anilist")


def setup(bot: commands.Cog):
    anilog.debug("adding cogs...")
    bot.add_cog(Anilist(bot))


anichart_query = """
query ($season: MediaSeason, $year: Int, $format: MediaFormat, $excludeFormat: MediaFormat, $status: MediaStatus, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
            total
            currentPage
            perPage
        }
        media(season: $season, seasonYear: $year, format: $format, format_not: $excludeFormat, status: $status, type: ANIME) {
            id
            title {
                romaji
                native
                english
            }
            startDate {
                year
                month
                day
            }
            endDate {
                year
                month
                day
            }
            status
            season
            format
            episodes
            siteUrl
            nextAiringEpisode {
                airingAt
                timeUntilAiring
                episode
            }
        }
    }
}
"""  # noqa: E501

anilist_query = """
query ($page: Int, $perPage: Int, $search: String) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            total
            currentPage
            lastPage
            hasNextPage
            perPage
        }
        media(search: $search, type: %s) {
            id
            idMal
            title {
                romaji
                english
                native
            }
            coverImage {
                large
            }
            averageScore
            chapters
            volumes
            episodes
            format
            status
            source
            genres
            description(asHtml:false)
            startDate {
                year
                month
                day
            }
            endDate {
                year
                month
                day
            }
            nextAiringEpisode {
                airingAt
                timeUntilAiring
                episode
            }
        }
    }
}
"""


def monthintext(number):
    idn = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]
    if number is None:
        return "Unknown"
    x = number - 1
    if x < 0:
        return "Unknown"
    return idn[number - 1]


def create_time_format(secs):
    months = int(secs // 2592000)  # 30 days format
    secs -= months * 2592000
    days = int(secs // 86400)
    secs -= days * 86400
    hours = int(secs // 3600)
    secs -= hours * 3600
    minutes = int(secs // 60)
    secs -= minutes * 60

    return_text = ""
    if months != 0:
        return_text += "{} bulan ".format(months)

    return return_text + "{} hari {} jam {} menit {} detik lagi".format(days, hours, minutes, secs)


def html2markdown(text):
    re_list = {
        "<br>": "\n",
        "</br>": "\n",
        "<br />": "\n",
        "<br/>": "\n",
        "<i>": "*",
        "</i>": "*",
        "<b>": "**",
        "</b>": "**",
        "\n\n": "\n",
    }
    for k, v in re_list.items():
        text = text.replace(k, v)
    return text


async def current_season_streams():
    current_time = datetime.today()
    month = current_time.month
    year = current_time.year

    seasonal = {
        "1": "winter",
        "2": "winter",
        "3": "winter",
        "4": "spring",
        "5": "spring",
        "6": "spring",
        "7": "summer",
        "8": "summer",
        "9": "summer",
        "10": "fall",
        "11": "fall",
        "12": "fall",
    }

    url_fetch = "https://www.livechart.me/streams?all_regions=true&season={season}-{year}&titles=romaji"
    url_to_fetch = url_fetch.format(season=seasonal.get(str(month), "winter"), year=year)

    anilog.info("fetching: {} {}".format(seasonal.get(str(month), "winter"), year))

    async with aiohttp.ClientSession() as sesi:
        try:
            async with sesi.get(url_to_fetch) as r:
                data = await r.text()
                if r.status != 200:
                    if r.status == 404:
                        return "Tidak ada hasil."
                    if r.status == 500:
                        return "Internal Error :/"
                    return "Terjadi kesalahan ketika komunikasi dengan server"
        except aiohttp.ClientError:
            return "Koneksi terputus"

    sup = BeautifulSoup(data, "html.parser")

    streams_lists = sup.find_all("div", {"class": "column column-block", "data-controller": "stream-list"},)

    full_query_result = []
    for streams in streams_lists:
        dataset = {}
        stream = streams.find("div")

        stream_head = stream.find("li", {"class": "grouped-list-heading"})
        stream_name = stream_head.find("div", class_="grouped-list-heading-title").text

        stream_icon = stream_head.find("div", class_="grouped-list-heading-icon").find("img")
        stream_icon = stream_icon["src"].replace("style=small", "style=large").replace("&amp;", "")

        anime_list = []
        for anime in stream.find_all("li", class_="anime-item"):
            title_animu = anime["data-title"]
            extra = anime.find("div", {"class": "info text-italic"})
            if extra:
                extra_text = extra.text.replace("※ ", "")
                if "via" not in extra_text:
                    title_animu += " ({})".format(extra_text)
            anime_list.append(title_animu)

        dataset["name"] = stream_name
        dataset["icon"] = stream_icon
        dataset["anime"] = anime_list
        full_query_result.append(dataset)

    return {"result": full_query_result, "data_total": len(full_query_result)}


class LegalStreaming:
    def __init__(self, json_data):
        self.json_data = json_data
        self.logger = logging.getLogger("cogs.anilist.LegalStreaming")

    async def find_by_id(self, id_):
        ids_ani = []
        self.logger.debug(f"finding {id_}")
        for k in self.json_data:
            if "anilist" in k["related"]:
                ids_ani.append(k["related"]["anilist"])
            else:
                ids_ani.append("")
        try:
            if str(id_) not in ids_ani:
                return []
            index_data = self.json_data[ids_ani.index(str(id_))]
        except IndexError:
            return []

        return index_data["streams"]


async def parse_anilist_results(results, method, streams_list={}):
    anilog.info("parsing API results...")
    query = results["Page"]["media"]

    # Koleksi translasi dan perubahan teks
    status_tl = {
        "finished": "Tamat",
        "releasing": "Sedang Berlangsung",
        "not_yet_released": "Belum Rilis",
        "cancelled": "Batal Tayang",
    }
    format_tl = {
        "TV": "Anime",
        "TV_SHORT": "Anime Pendek",
        "MOVIE": "Film",
        "SPECIAL": "Spesial",
        "OVA": "OVA",
        "ONA": "ONA",
        "MUSIC": "MV",
        "NOVEL": "Novel",
        "MANGA": "Manga",
        "ONE_SHOT": "One-Shot",
        None: "Lainnya",
    }
    source_tl = {
        "ORIGINAL": "Original",
        "MANGA": "Manga",
        "VISUAL_NOVEL": "Visual Novel",
        "LIGHT_NOVEL": "Novel Ringan",
        "VIDEO_GAME": "Gim",
        "OTHER": "Lainnya",
        None: "Lainnya",
    }

    if not query:
        return "Tidak ada hasil."

    if method == "anime":
        legalstreams_data = LegalStreaming(streams_list)
    full_query_result = []
    anilog.info("parsing results...")
    for entry in query:
        start_y = entry["startDate"]["year"]
        end_y = entry["endDate"]["year"]
        if not start_y:
            start = "Belum Rilis"
        else:
            start = "{}".format(start_y)
            start_m = entry["startDate"]["month"]
            if start_m:
                start = "{}/{}".format(start, start_m)
                start_d = entry["startDate"]["day"]
                if start_d:
                    start = "{}/{}".format(start, start_d)

        if not end_y:
            end = "Belum Berakhir"
        else:
            end = "{}".format(end_y)
            end_m = entry["endDate"]["month"]
            if end_m:
                end = "{}/{}".format(end, end_m)
                end_d = entry["endDate"]["day"]
                if end_d:
                    end = "{}/{}".format(end, end_d)

        title = entry["title"]["romaji"]
        ani_id = str(entry["id"])

        # Judul lain
        other_title = entry["title"]["native"]
        english_title = entry["title"]["english"]
        if english_title:
            if other_title:
                other_title += "\n" + english_title
            else:
                other_title = english_title

        score_rate = None
        score_rate_anilist = entry["averageScore"]
        if score_rate:
            score_rate = "{}/10".format(score_rate_anilist / 10)

        description = entry["description"]
        if description is not None:
            description = html2markdown(description)
            if len(description) > 1023:
                description = description[:1020] + "..."

        genres = ", ".join(entry["genres"]).lower()
        status = entry["status"].lower()
        img = entry["coverImage"]["large"]
        ani_link = "https://anilist.co/{m}/{id}".format(m=method, id=ani_id)

        dataset = {
            "title": title,
            "title_other": other_title,
            "start_date": start,
            "end_date": end,
            "poster_img": img,
            "synopsis": description,
            "status": status_tl[status],
            "format": format_tl[entry["format"]],
            "source_fmt": source_tl[entry["source"]],
            "link": ani_link,
            "score": score_rate,
            "footer": "ID: {} | {}".format(ani_id, genres),
        }

        if method == "manga":
            vol = entry["volumes"]
            ch = entry["chapters"]
            ch_vol = "{c} chapterXXC/{v} volumeXXV".format(c=ch, v=vol).replace("None", "??")
            if ch:
                if ch > 1:
                    ch_vol = ch_vol.replace("XXC", "s")
            ch_vol = ch_vol.replace("XXC", "")
            if vol:
                if vol > 1:
                    ch_vol = ch_vol.replace("XXV", "s")
            ch_vol = ch_vol.replace("XXV", "")
            dataset["ch_vol"] = ch_vol
        if method == "anime":
            anilog.info("Fetching stream for: {}".format(title))
            streams_list = await legalstreams_data.find_by_id(ani_id)
            if streams_list:
                dataset["streams"] = streams_list
            dataset["episodes"] = entry["episodes"]
            if status in ["releasing", "not_yet_released"]:
                ne_data = entry["nextAiringEpisode"]
                if ne_data:
                    airing_time = ne_data["airingAt"]
                    d_airing_time = timedelta(seconds=abs(airing_time))
                    time_tuple = datetime(1, 1, 1) + d_airing_time

                    dataset["airing_date"] = "{d} {m} {y}".format(
                        d=time_tuple.day, m=monthintext(time_tuple.month), y=time.strftime("%Y"),
                    )
                    dataset["next_episode"] = ne_data["episode"]
                    dataset["time_remain"] = create_time_format(ne_data["timeUntilAiring"])

        for k, v in dataset.items():
            if not v:
                dataset[k] = "Tidak ada"

        full_query_result.append(dataset)
    # del LegalStreams
    return {"result": full_query_result, "data_total": len(full_query_result)}


async def fetch_anichart():
    anilog.info("querying anichart...")
    current_time = datetime.today()
    month = current_time.month
    current_year = current_time.year

    seasonal = {
        "1": "winter",
        "2": "winter",
        "3": "winter",
        "4": "spring",
        "5": "spring",
        "6": "spring",
        "7": "summer",
        "8": "summer",
        "9": "summer",
        "10": "fall",
        "11": "fall",
        "12": "fall",
    }

    current_season = seasonal.get(str(month), "winter").upper()

    async def internal_fetch(season, year, page=1):
        anilog.info("Fetching page {} ({} {})".format(page, season, year))
        variables = {
            "season": season,
            "year": year,
            "page": page,
            "perPage": 50,
        }
        async with aiohttp.ClientSession() as sesi:
            try:
                async with sesi.post(
                    "https://graphql.anilist.co", json={"query": anichart_query, "variables": variables},
                ) as r:
                    try:
                        data = await r.json()
                    except IndexError:
                        return "ERROR: Terjadi kesalahan internal"
                    if r.status != 200:
                        if r.status == 404:
                            return "Tidak ada hasil."
                        if r.status == 500:
                            return "ERROR: Internal Error :/"
                    try:
                        return data["data"]["Page"]
                    except IndexError:
                        return "Tidak ada hasil."
            except aiohttp.ClientError:
                return "ERROR: Koneksi terputus"

    def _format_time(time_secs):
        time_days = int(time_secs // 86400)
        time_secs -= time_days * 86400
        time_hours = int(time_secs // 3600)
        time_secs -= time_hours * 3600
        time_minutes = int(time_secs // 60)
        time_secs -= time_minutes * 60

        if time_days > 0:
            if time_hours > 0:
                return "{} hari, {} jam".format(time_days, time_hours)
            return "{} hari, {} menit".format(time_days, time_minutes)

        if time_hours > 0:
            if time_minutes > 0:
                return "{} jam, {} menit".format(time_hours, time_minutes)
            return "{} jam".format(time_hours)

        if time_minutes > 0:
            return "{} menit".format(time_minutes)

        return "{} detik".format(time_secs)

    def is_valid_airing(status):
        ng = {"RELEASING": True, "NOT_YET_RELEASED": True}

        return ng.get(status, False)

    def is_valid_format(aniformat):
        ng = {"TV": True, "TV_SHORT": True, "MOVIE": True, "ONA": True}

        return ng.get(aniformat, False)

    dataset = await internal_fetch(current_season, current_year)
    if isinstance(dataset, str):
        return dataset

    full_fetched_query = []

    anilog.info("Parsing results...")
    for d in dataset["media"]:
        title = d["title"]["romaji"]
        nar = d["nextAiringEpisode"]
        start_date = d["startDate"]

        if not is_valid_format(d["format"]):
            continue

        if not is_valid_airing(d["status"]):
            continue

        if nar:
            next_ep = d["nextAiringEpisode"]["episode"]
            time_secs = d["nextAiringEpisode"]["timeUntilAiring"]
            title = "**{t}** - #{e}".format(t=title, e=str(next_ep).zfill(2))
            time_until_air = _format_time(time_secs)
        else:
            title = "**{t}**".format(t=title)
            time_secs = 100
            time_until_air = str(start_date["year"])
            if start_date["month"]:
                time_until_air = "{s}/{e}".format(s=str(start_date["month"]).zfill(2), e=time_until_air)
            if start_date["day"]:
                time_until_air = "{s}/{e}".format(s=str(start_date["day"]).zfill(2), e=time_until_air)

        discord_fill = {
            "title": title,
            "remain_txt": time_until_air,
            "remain": time_secs,
            "unknown": not nar,
        }

        full_fetched_query.append(discord_fill)

    next_page = dataset["pageInfo"]["hasNextPage"]
    if next_page:
        anilog.info("Parsing additional results...")
        count_total = dataset["pageInfo"]["total"]
        per_page = 50

        total_pages = ceil(count_total / per_page)

        for page in range(2, total_pages + 1):
            dataset = await internal_fetch(current_season, current_year, page)
            if isinstance(dataset, str):
                continue

            anilog.info("Parsing results...")
            for d in dataset["media"]:
                title = d["title"]["romaji"]
                nar = d["nextAiringEpisode"]
                start_date = d["startDate"]

                if not is_valid_format(d["format"]):
                    continue

                if not is_valid_airing(d["status"]):
                    continue

                if nar:
                    next_ep = d["nextAiringEpisode"]["episode"]
                    time_secs = d["nextAiringEpisode"]["timeUntilAiring"]
                    title = "**{t}** - #{e}".format(t=title, e=str(next_ep).zfill(2))
                    time_until_air = _format_time(time_secs)
                else:
                    title = "**{t}**".format(t=title)
                    time_secs = 100
                    time_until_air = str(start_date["year"])
                    if start_date["month"]:
                        time_until_air = "{s}/{e}".format(
                            s=str(start_date["month"]).zfill(2), e=time_until_air,
                        )
                    if start_date["day"]:
                        time_until_air = "{s}/{e}".format(s=str(start_date["day"]).zfill(2), e=time_until_air)

                discord_fill = {
                    "title": title,
                    "remain_txt": time_until_air,
                    "remain": time_secs,
                    "unknown": not nar,
                }

                full_fetched_query.append(discord_fill)

    # Sort
    anilog.info("Sorting results...")
    filtered_full_fetched_query = {}
    for q in full_fetched_query:
        if q["unknown"]:
            if "Lain-Lain" not in filtered_full_fetched_query:
                unknown_dataset = []
            else:
                unknown_dataset = filtered_full_fetched_query["Lain-Lain"]
            unknown_dataset.append(q)
            filtered_full_fetched_query["Lain-Lain"] = unknown_dataset
        else:
            td = timedelta(seconds=q["remain"])
            day = str(td.days).zfill(2)

            if day not in filtered_full_fetched_query:
                day_dataset = []
            else:
                day_dataset = filtered_full_fetched_query[day]

            day_dataset.append(q)
            filtered_full_fetched_query[day] = day_dataset

    del full_fetched_query

    sorted_full_fetched_query = {}
    for sss in sorted(list(filtered_full_fetched_query.keys())):
        if sss.startswith("0"):
            na = sss[1:] + " hari lagi"
        else:
            na = sss
            if sss != "Lain-Lain":
                na += " hari lagi"
        if na == "0 hari lagi":
            na = "<24 jam lagi"
        sorted_full_fetched_query[na] = filtered_full_fetched_query[sss]

    del filtered_full_fetched_query

    sorted_time_full_fetched_query = {}
    for sss in list(sorted_full_fetched_query.keys()):
        dk = sorted_full_fetched_query[sss]
        if sss != "Lain-Lain":
            dk.sort(key=lambda x: x["remain"])
        sorted_time_full_fetched_query[sss] = dk

    del sorted_full_fetched_query

    anilog.info("Done!")
    return {
        "dataset": sorted_time_full_fetched_query,
        "season": f"{current_season.lower().capitalize()} {current_year}",
    }


class Anilist(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.streams_list = bot.jsdb_streams["data"]
        self.logger = logging.getLogger("cogs.anilist.Anilist")

        self.anibucket = bot.anibucket

    @commands.command(aliases=["animu", "kartun", "ani"])
    @commands.guild_only()
    async def anime(self, ctx, *, judul):
        """Mencari informasi anime lewat API anilist.co"""
        self.logger.info(f"searching {judul}")
        variables = {"search": judul, "page": 1, "perPage": 50}
        req_res = await self.anibucket.handle(anilist_query % "ANIME", variables)
        if isinstance(req_res, str):
            return await ctx.send(req_res)
        aqres = await parse_anilist_results(req_res, "anime", self.streams_list)
        if isinstance(aqres, str):
            return await ctx.send(aqres)

        max_page = aqres["data_total"]
        resdata = aqres["result"]
        self.logger.info(f"total results {len(resdata)}")

        first_run = True
        time_table = False
        stream_list = False
        num = 1
        while True:
            if first_run:
                self.logger.info("showing results...")
                data = resdata[num - 1]
                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=data["footer"])

                embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
                embed.add_field(name="Episode", value=data["episodes"], inline=True)
                embed.add_field(name="Status", value=data["status"], inline=True)
                embed.add_field(name="Skor", value=data["score"], inline=True)
                embed.add_field(name="Rilis", value=data["start_date"], inline=True)
                embed.add_field(name="Berakhir", value=data["end_date"], inline=True)
                embed.add_field(name="Format", value=data["format"], inline=True)
                embed.add_field(name="Adaptasi", value=data["source_fmt"], inline=True)
                embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if time_table or stream_list:
                reactmoji.append("👍")
            elif max_page == 1 and num == 1:
                pass
            elif num == 1:
                reactmoji.append("⏩")
            elif num == max_page:
                reactmoji.append("⏪")
            elif num > 1 and num < max_page:
                reactmoji.extend(["⏪", "⏩"])
            if "next_episode" in data and not time_table and not stream_list:
                reactmoji.append("⏳")
            if "streams" in data and not time_table and not stream_list:
                reactmoji.append("📺")
            reactmoji.append("✅")

            self.logger.debug("reacting message...")
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

            try:
                self.logger.debug("now waiting for reaction...")
                res, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check_react)
            except asyncio.TimeoutError:
                self.logger.warn("timeout, removing reactions...")
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                self.logger.debug("going backward...")
                num = num - 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=data["footer"])

                embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
                embed.add_field(name="Episode", value=data["episodes"], inline=True)
                embed.add_field(name="Status", value=data["status"], inline=True)
                embed.add_field(name="Skor", value=data["score"], inline=True)
                embed.add_field(name="Rilis", value=data["start_date"], inline=True)
                embed.add_field(name="Berakhir", value=data["end_date"], inline=True)
                embed.add_field(name="Format", value=data["format"], inline=True)
                embed.add_field(name="Adaptasi", value=data["source_fmt"], inline=True)
                embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                self.logger.debug("going forward...")
                num = num + 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=data["footer"])

                embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
                embed.add_field(name="Episode", value=data["episodes"], inline=True)
                embed.add_field(name="Status", value=data["status"], inline=True)
                embed.add_field(name="Skor", value=data["score"], inline=True)
                embed.add_field(name="Rilis", value=data["start_date"], inline=True)
                embed.add_field(name="Berakhir", value=data["end_date"], inline=True)
                embed.add_field(name="Format", value=data["format"], inline=True)
                embed.add_field(name="Adaptasi", value=data["source_fmt"], inline=True)
                embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "👍" in str(res.emoji):
                self.logger.debug("reshowing anime info...")
                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=data["footer"])

                embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
                embed.add_field(name="Episode", value=data["episodes"], inline=True)
                embed.add_field(name="Status", value=data["status"], inline=True)
                embed.add_field(name="Skor", value=data["score"], inline=True)
                embed.add_field(name="Rilis", value=data["start_date"], inline=True)
                embed.add_field(name="Berakhir", value=data["end_date"], inline=True)
                embed.add_field(name="Format", value=data["format"], inline=True)
                embed.add_field(name="Adaptasi", value=data["source_fmt"], inline=True)
                embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)

                if time_table:
                    time_table = False
                if stream_list:
                    stream_list = False
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏳" in str(res.emoji):
                self.logger.debug("showing next episode air time...")
                ep_txt = "Episode " + str(data["next_episode"])
                embed = discord.Embed(color=0x19212D)
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=f"Akan tayang pada {data['airing_date']}")

                embed.add_field(name=ep_txt, value=data["time_remain"], inline=False)

                time_table = True
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "📺" in str(res.emoji):
                self.logger.debug("showing streams list...")
                text_data = "**Legal Streams**:\n"
                for k, v in data["streams"].items():
                    if not isinstance(v, str):
                        temp = []
                        for k2, v2 in v.items():
                            if v2:
                                temp.append("[{}]({})".format(k2, v2))
                            else:
                                temp.append("*{s}*".format(s=k2))
                        text_data += "- **{s}**\n".format(s=k)
                        text_data += "  " + " \| ".join(temp)  # noqa: W605
                        text_data += "\n"
                    else:
                        if v:
                            text_data += "- [{}]({})\n".format(k, v)
                        else:
                            text_data += "- **{s}**\n".format(s=k)

                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.description = text_data
                embed.set_footer(text=data["footer"])

                stream_list = True
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
                self.logger.warn("deleting embed...")
                await ctx.message.delete()
                return await msg.delete()

    @commands.command(aliases=["komik", "mango"])
    @commands.guild_only()
    async def manga(self, ctx, *, judul):
        """Mencari informasi manga lewat API anilist.co"""
        self.logger.info(f"searching {judul}")
        variables = {"search": judul, "page": 1, "perPage": 50}
        req_res = await self.anibucket.handle(anilist_query % "MANGA", variables)
        if isinstance(req_res, str):
            return await ctx.send(req_res)
        aqres = await parse_anilist_results(req_res, "manga", self.streams_list)
        if isinstance(aqres, str):
            return await ctx.send(aqres)

        max_page = aqres["data_total"]
        resdata = aqres["result"]
        self.logger.info(f"total result {max_page}")

        first_run = True
        num = 1
        while True:
            if first_run:
                self.logger.info("showing results...")
                data = resdata[num - 1]
                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=data["footer"])

                embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
                embed.add_field(name="Chapter/Volume", value=data["ch_vol"], inline=True)
                embed.add_field(name="Status", value=data["status"], inline=True)
                embed.add_field(name="Skor", value=data["score"], inline=True)
                embed.add_field(name="Rilis", value=data["start_date"], inline=True)
                embed.add_field(name="Berakhir", value=data["end_date"], inline=True)
                embed.add_field(name="Format", value=data["format"], inline=True)
                embed.add_field(name="Adaptasi", value=data["source_fmt"], inline=True)
                embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                pass
            elif num == 1:
                reactmoji.append("⏩")
            elif num == max_page:
                reactmoji.append("⏪")
            elif num > 1 and num < max_page:
                reactmoji.extend(["⏪", "⏩"])
            reactmoji.append("✅")

            self.logger.debug("reacting message...")
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

            try:
                self.logger.debug("now waiting for reaction...")
                res, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check_react)
            except asyncio.TimeoutError:
                self.logger.warn("timeout, removing reactions...")
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                self.logger.debug("going backward...")
                num = num - 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=data["footer"])

                embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
                embed.add_field(name="Chapter/Volume", value=data["ch_vol"], inline=True)
                embed.add_field(name="Status", value=data["status"], inline=True)
                embed.add_field(name="Skor", value=data["score"], inline=True)
                embed.add_field(name="Rilis", value=data["start_date"], inline=True)
                embed.add_field(name="Berakhir", value=data["end_date"], inline=True)
                embed.add_field(name="Format", value=data["format"], inline=True)
                embed.add_field(name="Adaptasi", value=data["source_fmt"], inline=True)
                embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                self.logger.debug("going forward...")
                num = num + 1
                data = resdata[num - 1]

                embed = discord.Embed(color=0x19212D)

                embed.set_thumbnail(url=data["poster_img"])
                embed.set_author(
                    name=data["title"],
                    url=data["link"],
                    icon_url="https://anilist.co/img/icons/apple-touch-icon-152x152.png",
                )
                embed.set_footer(text=data["footer"])

                embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
                embed.add_field(name="Chapter/Volume", value=data["ch_vol"], inline=True)
                embed.add_field(name="Status", value=data["status"], inline=True)
                embed.add_field(name="Skor", value=data["score"], inline=True)
                embed.add_field(name="Rilis", value=data["start_date"], inline=True)
                embed.add_field(name="Berakhir", value=data["end_date"], inline=True)
                embed.add_field(name="Format", value=data["format"], inline=True)
                embed.add_field(name="Adaptasi", value=data["source_fmt"], inline=True)
                embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
                self.logger.warn("deleting embed...")
                await ctx.message.delete()
                return await msg.delete()

    @commands.command()
    @commands.guild_only()
    async def tayang(self, ctx):
        """Mencari informasi season lewat API anilist.co"""
        self.logger.info("requesting...")
        aqres = await fetch_anichart()
        if isinstance(aqres, str):
            return await ctx.send(aqres)

        resdata = aqres["dataset"]
        self.logger.info("filtering results...")
        if len(resdata) > 18:
            keysss = list(resdata.keys())
            merge_keys = keysss[18:]
            last_data = deepcopy(resdata[keysss[18]])
            for ki in merge_keys:
                last_data.extend(resdata[ki])
                del resdata[ki]
            new_name = ">" + keysss[18]
            del resdata[keysss[18]]
            resdata[new_name] = last_data

        sisen = aqres["season"]
        amount_final = len(resdata)

        async def generate_embed(dataset, day_left):
            embed = discord.Embed(color=0x19212D)
            embed.set_author(
                name="Anichart", url="https://anichart.net/", icon_url="https://anichart.net/favicon.ico",
            )
            val = ""
            for data in dataset:
                val += "- {}\n{}\n".format(data["title"], data["remain_txt"])
            embed.add_field(name=day_left, value=val, inline=False)
            return embed

        emote_list = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
            "8️⃣",
            "9️⃣",
            "0️⃣",
            "🇦",
            "🇧",
            "🇨",
            "🇩",
            "🇪",
            "🇫",
            "🇬",
            "🇭",
        ]

        resdata_keys = list(resdata.keys())

        first_run = True
        melihat_listing = False
        num = 1
        while True:
            if first_run:
                self.logger.info("showing results...")
                embed = discord.Embed(title="Listing Jadwal Tayang - " + sisen, color=0x19212D)
                embed.set_author(
                    name="Anichart", url="https://anichart.net/", icon_url="https://anichart.net/favicon.ico",
                )
                val = ""
                for n, data in enumerate(resdata.keys()):
                    val += "{em} **{fmt}**\n".format(em=emote_list[n], fmt=data)
                embed.add_field(name="List Hari", value=val)

                first_run = False
                msg = await ctx.send(embed=embed)

            if melihat_listing:
                amount_to_use = 0
            else:
                amount_to_use = amount_final

            emotes = emote_list[:amount_to_use]
            emotes.extend("✅")

            for react in emotes:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in emotes:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await msg.clear_reactions()
                if melihat_listing:
                    embed = discord.Embed(title="Listing Jadwal Tayang - " + sisen, color=0x19212D,)
                    embed.set_author(
                        name="Anichart",
                        url="https://anichart.net/",
                        icon_url="https://anichart.net/favicon.ico",
                    )
                    val = ""
                    for n, data in enumerate(resdata.keys()):
                        val += "{em} **{fmt}**\n".format(em=emote_list[n], fmt=data)
                    embed.add_field(name="List Hari", value=val)

                    melihat_listing = False
                    await msg.edit(embed=embed)
                else:
                    self.logger.warn("deleting embed...")
                    await msg.delete()
                    return await ctx.message.delete()
            elif emote_list[0] in str(res.emoji):
                await msg.clear_reactions()
                num = 0
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[1] in str(res.emoji):
                await msg.clear_reactions()
                num = 1
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[2] in str(res.emoji):
                await msg.clear_reactions()
                num = 2
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[3] in str(res.emoji):
                await msg.clear_reactions()
                num = 3
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[4] in str(res.emoji):
                await msg.clear_reactions()
                num = 4
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[5] in str(res.emoji):
                await msg.clear_reactions()
                num = 5
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[6] in str(res.emoji):
                await msg.clear_reactions()
                num = 6
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[7] in str(res.emoji):
                await msg.clear_reactions()
                num = 7
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[8] in str(res.emoji):
                await msg.clear_reactions()
                num = 8
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[9] in str(res.emoji):
                await msg.clear_reactions()
                num = 9
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[10] in str(res.emoji):
                await msg.clear_reactions()
                num = 10
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[11] in str(res.emoji):
                await msg.clear_reactions()
                num = 11
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[12] in str(res.emoji):
                await msg.clear_reactions()
                num = 12
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[13] in str(res.emoji):
                await msg.clear_reactions()
                num = 13
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[14] in str(res.emoji):
                await msg.clear_reactions()
                num = 14
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[15] in str(res.emoji):
                await msg.clear_reactions()
                num = 15
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[16] in str(res.emoji):
                await msg.clear_reactions()
                num = 16
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            elif emote_list[17] in str(res.emoji):
                await msg.clear_reactions()
                num = 17
                self.logger.debug(f"picking no. {num}...")
                melihat_listing = True
                embed = await generate_embed(resdata[resdata_keys[num]], resdata_keys[num])
                await msg.edit(embed=embed)
            else:
                self.logger.warn("clearing reactions...")
                await msg.clear_reactions()
