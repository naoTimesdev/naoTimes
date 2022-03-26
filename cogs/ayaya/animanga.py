import logging
from typing import Dict, List, Union

import arrow
import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.paginator import DiscordPaginator, DiscordPaginatorUI
from naotimes.showtimes import ShowtimesPoster
from naotimes.showtimes.cogbase import rgbhex_to_rgbint
from naotimes.t import T
from naotimes.utils import complex_walk, cutoff_text

ANILIST_QUERY = """
query ($page: Int, $perPage: Int, $search: String, $type: MediaType) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            total
            currentPage
            lastPage
            hasNextPage
            perPage
        }
        media(search: $search, type: $type) {
            id
            idMal
            title {
                romaji
                english
                native
            }
            coverImage {
                color
                extraLarge
                large
                medium
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

ANICHART_QUERY = """
query ($season: MediaSeason, $year: Int, $page: Int, $perPage: Int, $statuses: [MediaStatus], $format: [MediaFormat]) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
            total
            currentPage
            perPage
        }
        media(season: $season, seasonYear: $year, status_in: $statuses, type: ANIME, format_in: $format) {
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


def create_time_format(secs: Union[int, float]):
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
        return_text += f"{months} bulan "

    return return_text + f"{days} hari {hours} jam {minutes} menit {secs} detik lagi"


class EpisodeInfo:
    def __init__(self, episode: int = None, time_remain: str = None, airdate: str = None):
        self._episode = episode
        self.time_remain = time_remain
        self.airdate = airdate

        self._id = None
        self._title = None
        self._color = 0x19212D

    @property
    def episode(self):
        if isinstance(self._episode, int):
            return str(self._episode).zfill(2)
        return "??"

    @property
    def raw_episode(self):
        return self._episode

    def bind(self, id: str, title: str, color: int = 0x19212D):
        self._id = id
        self._title = title
        if isinstance(color, int):
            self._color = color


class EpisodeInfoWrap:
    def __init__(self, dataset: List[EpisodeInfo], season: str, time: str):
        self.dataset = dataset
        self.season = season
        self.time = time


class ChapterInfo:
    def __init__(self, chapter: int = None, volume: int = None):
        self._chapter = chapter
        self._volume = volume

    @property
    def chapter(self):
        if isinstance(self._chapter, int):
            add_s = ""
            if self._chapter > 1:
                add_s = "s"
            return f"{self._chapter} chapter{add_s}"
        return "?? chapter"

    @property
    def volume(self):
        if isinstance(self._volume, int):
            add_s = ""
            if self._volume > 1:
                add_s = "s"
            return f"{self._volume} volume{add_s}"
        return "?? volume"

    def __str__(self):
        return f"{self.chapter}/{self.volume}"


class AnilistResult:
    def __init__(
        self,
        id: str,
        title: str,
        other_title: List[str] = [],
        description: str = None,
        start: str = None,
        end: str = None,
        poster: ShowtimesPoster = None,
        format: str = None,
        source: str = None,
        status: str = None,
        genres: List[str] = [],
        rating: int = None,
    ):
        self.id = id
        self.title = title
        self._other = other_title
        self.description = description
        self._start = start
        self._end = end
        self._poster = poster
        self._format = format
        self._source = source
        self._status = status
        self._rating = rating
        self._genres = genres

        self._extra_data: Union[EpisodeInfo, ChapterInfo] = None
        self._is_anime = False

    @property
    def other_title(self) -> str:
        if len(self._other) < 1:
            return "*Tidak ada*"
        return "\n".join(self._other)

    @property
    def start(self) -> str:
        if not self._start:
            return "Belum Rilis"
        return self._start

    @property
    def end(self) -> str:
        if not self._end:
            return "Belum Berakhir"
        return self._end

    @property
    def poster_url(self) -> str:
        if self._poster is None:
            return None
        if self._poster.url is None:
            return None
        return self._poster.url

    @property
    def color(self) -> int:
        if self._poster is None:
            return 0
        if self._poster.color is None:
            return 0
        return self._poster.color

    @property
    def format(self) -> str:
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
        }
        return format_tl.get(fallback_str(self._format, ""), "Lainnya")

    @property
    def source(self) -> str:
        source_tl = {
            "ORIGINAL": "Orisinil",
            "MANGA": "Manga",
            "VISUAL_NOVEL": "Visual Novel",
            "LIGHT_NOVEL": "Novel Ringan",
            "VIDEO_GAME": "Gim",
            "OTHER": "Lainnya",
        }
        return source_tl.get(fallback_str(self._source, ""), "Lainnya")

    @property
    def status(self) -> str:
        status_tl = {
            "FINISHED": "Tamat",
            "RELEASING": "Sedang Berlangsung",
            "NOT_YET_RELEASED": "Belum Rilis",
            "CANCELLED": "Batal Tayang",
        }
        return status_tl.get(fallback_str(self._status, ""), "Lainnya")

    @property
    def rating(self) -> str:
        if self._rating is None:
            return "*Tidak ada*"
        return f"{self._rating / 10}/10.0"

    @property
    def genre(self) -> str:
        if isinstance(self._genres, list):
            if len(self._genres) > 0:
                return ", ".join(self._genres)
        return "Tidak diketahui"

    @property
    def url(self) -> str:
        method = "anime" if self._is_anime else "manga"
        return f"https://anilist.co/{method}/{self.id}"

    def bind(self, extra_data: Union[EpisodeInfo, ChapterInfo]):
        if isinstance(extra_data, EpisodeInfo):
            extra_data.bind(self.id, self.title, self.color)
            self._is_anime = True
            self._extra_data = extra_data
        elif isinstance(extra_data, ChapterInfo):
            self._extra_data = extra_data

    @property
    def extras(self):
        return self._extra_data

    @property
    def has_next(self):
        if self._extra_data is None:
            return False
        if isinstance(self._extra_data, EpisodeInfo):
            if isinstance(self._extra_data.airdate, str):
                return True
        return False


def create_nicer_anilist_date(date: dict):
    if not isinstance(date, dict):
        return None
    extended = [date.get("year"), date.get("month"), date.get("day")]
    extended = filter(lambda x: x is not None, extended)
    if len(list(extended)) < 1:
        return None
    return "/".join(map(str, extended))


def fallback_str(content: T, fallback: str) -> Union[T, str]:
    if content is None:
        return fallback
    return content


def html2markdown(text: str) -> str:
    replace_list = {
        "<br>": "\n",
        "</br>": "\n",
        "<br />": "\n",
        "<br/>": "\n",
        "<i>": "*",
        "</i>": "*",
        "<b>": "**",
        "</b>": "**",
        "<u>": "__",
        "</u>": "__",
        "\n\n": "\n",
    }
    for orig, target in replace_list.items():
        text = text.replace(orig, target)
    return text


class AyayaAnimeManga(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Ayaya.AnimeManga")

    @staticmethod
    def __select_cover(media: dict) -> str:
        large = media.get("coverImage", {}).get("large")
        medium = media.get("coverImage", {}).get("medium")
        extra_large = media.get("coverImage", {}).get("extraLarge")
        extended = list(filter(lambda x: x is not None, [extra_large, large, medium]))
        if len(extended) < 1:
            return None
        return extended[0]

    async def __parse_anilist(self, raw_data: dict, is_anime: bool = True):
        media_info: list = complex_walk(raw_data, "Page.media")
        self.logger.info(f"Got {len(media_info)} raw results...")
        if len(media_info) == 0:
            return []

        parsed_result: List[AnilistResult] = []
        self.logger.info("Parsing search result...")
        for media in media_info:
            started = create_nicer_anilist_date(complex_walk(media, "startDate"))
            ended = create_nicer_anilist_date(complex_walk(media, "endDate"))

            anilist_id = str(media["id"])
            roman = complex_walk(media, "title.romaji")
            english = complex_walk(media, "title.english")
            native = complex_walk(media, "title.native")
            main_title = fallback_str(roman, fallback_str(english, native))
            other_title = []
            for title in (roman, english, native):
                if not title:
                    continue
                if title == main_title:
                    continue
                other_title.append(title)

            rating = complex_walk(media, "averageScore")

            description = complex_walk(media, "description")
            if isinstance(description, str) and description:
                description = html2markdown(description)
            genres = media.get("genres", [])
            status = media.get("status", None)
            format = media.get("format", None)
            source = media.get("source", None)

            cover_color = rgbhex_to_rgbint(complex_walk(media, "coverImage.color"))
            cover_image = self.__select_cover(media)

            poster = ShowtimesPoster(cover_image, cover_color)

            result = AnilistResult(
                anilist_id,
                main_title,
                other_title,
                description,
                started,
                ended,
                poster,
                format,
                source,
                status,
                genres,
                rating,
            )
            if is_anime:
                episode = media.get("episodes")
                ep_info = EpisodeInfo(episode)
                airdate = complex_walk(media, "nextAiringEpisode.airingAt")
                if airdate is not None:
                    airdate_arrow: arrow.Arrow = arrow.get(airdate)

                    ep_info.airdate = airdate_arrow.format("DD MMMM YYYY")
                    ep_info.time_remain = create_time_format(
                        complex_walk(media, "nextAiringEpisode.timeUntilAiring")
                    )
                result.bind(ep_info)
            else:
                chapter = media.get("chapters", None)
                volumes = media.get("volumes", None)
                result.bind(ChapterInfo(chapter, volumes))
            parsed_result.append(result)

        return parsed_result

    async def _fetch_anichart_data(self):
        self.logger.info("Querying anichart...")
        current_time = self.bot.now().datetime
        current_month = current_time.month
        current_year = current_time.year

        seasonal = {
            1: "winter",
            2: "winter",
            3: "winter",
            4: "spring",
            5: "spring",
            6: "spring",
            7: "summer",
            8: "summer",
            9: "summer",
            10: "fall",
            11: "fall",
            12: "fall",
        }

        def _format_time(time_secs: Union[int, float]):
            time_days = int(time_secs // 86400)
            time_secs -= time_days * 86400
            time_hours = int(time_secs // 3600)
            time_secs -= time_hours * 3600
            time_minutes = int(time_secs // 60)
            time_secs -= time_minutes * 60

            if time_days > 0:
                if time_hours > 0:
                    return f"{time_days} hari, {time_hours} jam"
                return f"{time_days} hari, {time_minutes} menit"

            if time_hours > 0:
                if time_minutes > 0:
                    return f"{time_hours} jam, {time_minutes} menit"
                return f"{time_hours} jam"

            if time_minutes > 0:
                return f"{time_minutes} menit"

            return f"{time_secs} detik"

        current_season = seasonal.get(current_month, "winter").upper()
        all_query_results = []
        base_vars = {
            "season": current_season,
            "year": current_year,
            "page": 1,
            "perPage": 50,
            "statuses": ["RELEASING", "NOT_YET_RELEASED"],
            "format": ["TV", "TV_SHORT", "MOVIE", "ONA"],
        }
        current_page = 1
        async for api_res in self.bot.anibucket.paginate(ANICHART_QUERY, base_vars):
            collected_media = complex_walk(api_res.data, "Page.media")
            if isinstance(collected_media, list):
                self.logger.info(f"Merging page: {current_page}")
                all_query_results.extend(collected_media)
            current_page += 1

        season_info = f"{current_season.lower().capitalize()} {current_year}"

        formatted_query: List[EpisodeInfo] = []
        for media in all_query_results:
            anilist_id = str(media["id"])
            roman = complex_walk(media, "title.romaji")
            english = complex_walk(media, "title.english")
            native = complex_walk(media, "title.native")
            main_title = fallback_str(roman, fallback_str(english, native))
            start_date = complex_walk(media, "startDate")
            next_airs = complex_walk(media, "nextAiringEpisode")

            next_episode = complex_walk(next_airs, "episode")
            if next_airs:
                time_secs = next_airs.get("timeUntilAiring")
                time_until_air = _format_time(time_secs)
            else:
                time_secs = 100
                time_until_air = str(start_date["year"])
                st_month = complex_walk(start_date, "month")
                st_day = complex_walk(start_date, "day")
                if st_month:
                    time_until_air = f"{str(st_month).zfill(2)}/{time_until_air}"
                if st_day:
                    time_until_air = f"{str(st_day).zfill(2)}/{time_until_air}"

            episode_info = EpisodeInfo(
                next_episode,
                time_secs,
                time_until_air,
            )
            episode_info.bind(anilist_id, main_title)
            formatted_query.append(episode_info)

        if len(formatted_query) < 1:
            return "Tidak ada hasil untuk musim ini", season_info

        # Sort by airtime
        formatted_query.sort(key=lambda x: x.time_remain)

        mapped_airing: Dict[str, EpisodeInfoWrap] = {}
        for data in formatted_query:
            if data.raw_episode is None:
                if "Lain-Lain" not in mapped_airing:
                    mapped_airing["Lain-Lain"] = EpisodeInfoWrap([], season_info, "Lain-Lain")
                mapped_airing["Lain-Lain"].dataset.append(data)
            else:
                day = str(data.time_remain // 86400).zfill(2)

                if day not in mapped_airing:
                    mapped_airing[day] = EpisodeInfoWrap([], season_info, day)
                mapped_airing[day].dataset.append(data)

        sorted_mapped_airing: Dict[str, EpisodeInfoWrap] = {}
        for the_day in sorted(mapped_airing.keys()):
            original_key = str(the_day)
            if the_day.startswith("0"):
                the_day = the_day[1:]

            if the_day != "Lain-Lain":
                the_day += " hari lagi"
            if the_day == "0 hari lagi":
                the_day = "<24 jam lagi"
            fixed_data = mapped_airing[original_key]
            fixed_data.time = the_day
            sorted_mapped_airing[the_day] = fixed_data

        return sorted_mapped_airing, season_info

    @staticmethod
    def _generate_anime_embed(data: AnilistResult) -> disnake.Embed:
        embed = disnake.Embed(color=data.color)
        if data.poster_url:
            embed.set_thumbnail(url=data.poster_url)
        embed.set_author(
            name=data.title,
            url=data.url,
            icon_url="https://p.ihateani.me/wtelbjmn.png",
        )
        embed.description = cutoff_text(fallback_str(data.description, "*Tidak ada sinopsis*"), 2000)
        embed.set_footer(text=f"ID: {data.id}")

        embed.add_field(name="Nama lain", value=data.other_title)
        embed.add_field(name="Episode", value=data.extras.episode)
        embed.add_field(name="Status", value=data.status)
        embed.add_field(name="Skor", value=data.rating)
        embed.add_field(name="Rilis", value=data.start)
        embed.add_field(name="Berakhir", value=data.end)
        embed.add_field(name="Format", value=data.format)
        embed.add_field(name="Adaptasi", value=data.source)
        return embed

    @staticmethod
    def _generate_manga_embed(data: AnilistResult) -> disnake.Embed:
        embed = disnake.Embed(color=data.color)
        if data.poster_url:
            embed.set_thumbnail(url=data.poster_url)
        embed.set_author(
            name=data.title,
            url=data.url,
            icon_url="https://p.ihateani.me/wtelbjmn.png",
        )
        embed.description = cutoff_text(fallback_str(data.description, "*Tidak ada sinopsis*"), 2000)
        embed.set_footer(text=f"ID: {data.id}")

        embed.add_field(name="Nama lain", value=data.other_title)
        embed.add_field(name="Chapter/Volume", value=str(data.extras))
        embed.add_field(name="Status", value=data.status)
        embed.add_field(name="Skor", value=data.rating)
        embed.add_field(name="Rilis", value=data.start)
        embed.add_field(name="Berakhir", value=data.end)
        embed.add_field(name="Format", value=data.format)
        embed.add_field(name="Adaptasi", value=data.source)
        return embed

    @staticmethod
    def _next_episode_embed(data: AnilistResult) -> disnake.Embed:
        embed = disnake.Embed(color=data.color)
        embed.set_author(name=data.title, url=data.url, icon_url="https://p.ihateani.me/wtelbjmn.png")
        embed.set_footer(text=f"Akan tayang pada {data.extras.airdate}")
        embed.add_field(name=f"Episode {data.extras.episode}", value=data.extras.time_remain, inline=False)
        return embed

    def _check_bot_perms(self, ctx: naoTimesContext):
        the_guild: disnake.Guild = ctx.guild
        is_guild = the_guild is not None
        the_channel: disnake.TextChannel = ctx.channel
        bot_member = the_guild.get_member(self.bot.user.id)
        bbperms = the_channel.permissions_for(bot_member)

        is_valid_perm = True
        has_embed_perms = bbperms.embed_links
        for perm in (
            bbperms.manage_messages,
            bbperms.embed_links,
            bbperms.read_message_history,
            bbperms.add_reactions,
        ):
            if not perm:
                is_valid_perm = False
                break
        return is_guild, is_valid_perm, has_embed_perms

    @commands.command(name="anime", aliases=["animu", "kartun", "ani"])
    async def _ayaya_anime(self, ctx: naoTimesContext, *, judul: str) -> None:
        self.logger.info(f"Searching for {judul}")
        variables = {"search": judul, "page": 1, "perPage": 25, "type": "ANIME"}
        requested = await self.bot.anibucket.handle(ANILIST_QUERY, variables)
        if len(requested.errors) > 0:
            await ctx.send("Gagal menghubungi Anilist, mohon coba sesaat lagi!")
            return

        is_guild, can_paginate, has_embed_perms = self._check_bot_perms(ctx)

        parsed_result = await self.__parse_anilist(requested.data, True)
        if len(parsed_result) < 1:
            return await ctx.send("Tidak ada hasil!")
        self.logger.info(f"Got {len(parsed_result)} hits")

        async def handle_episode_table(dataset: EpisodeInfo, _, message: disnake.Message):
            nextep_gen = DiscordPaginator(self.bot, ctx, [dataset])
            nextep_gen.remove_at_trashed = False
            nextep_gen.paginateable = False
            nextep_gen.stop_on_no_result = False
            nextep_gen.set_generator(self._next_episode_embed)
            timeout = await nextep_gen.paginate(30.0, message)
            return None, message, timeout

        if is_guild:
            if can_paginate:
                main_gen = DiscordPaginator(self.bot, ctx, parsed_result)
                main_gen.set_generator(self._generate_anime_embed)
                main_gen.add_handler("⌛", lambda data: data.has_next, handle_episode_table)
                main_gen.remove_at_trashed = False
                await main_gen.paginate(30.0)
            else:
                if has_embed_perms:
                    generate_embed = self._generate_anime_embed(parsed_result[0])
                    await ctx.send(embed=generate_embed)
                    perms_need = ["Manage Messages", "Read Message History", "Add Reactions"]
                    err_msg = "Bot tidak dapat melakukan paginating karena kekurangan "
                    err_msg += "salah satu permission berikut:\n"
                    err_msg += "\n".join(perms_need)
                    await ctx.send(err_msg)
                else:
                    perms_need = ["Manage Messages", "Read Message History", "Add Reactions", "Embed Links"]
                    err_msg = "Bot tidak dapat memberikan hasil karena kekurangan "
                    err_msg += "salah satu permission berikut:\n"
                    err_msg += "\n".join(perms_need)
                    await ctx.send(err_msg)
        else:
            generate_embed = self._generate_anime_embed(parsed_result[0])
            await ctx.send(embed=generate_embed)

    @commands.command(name="manga", aliases=["komik", "mango"])
    async def _ayaya_manga(self, ctx: naoTimesContext, *, judul: str):
        self.logger.info(f"Searching for {judul}")
        variables = {"search": judul, "page": 1, "perPage": 25, "type": "MANGA"}
        requested = await self.bot.anibucket.handle(ANILIST_QUERY, variables)
        if len(requested.errors) > 0:
            await ctx.send("Gagal menghubungi Anilist, mohon coba sesaat lagi!")
            return

        parsed_result = await self.__parse_anilist(requested.data, False)
        if len(parsed_result) < 1:
            return await ctx.send("Tidak ada hasil!")
        self.logger.info(f"Got {len(parsed_result)} hits")

        if ctx.guild is not None:
            main_gen = DiscordPaginatorUI(ctx, parsed_result)
            main_gen.attach(self._generate_manga_embed)
            await main_gen.interact(30.0)
        else:
            generate_embed = self._generate_manga_embed(parsed_result[0])
            await ctx.send(embed=generate_embed)

    @commands.command(name="tayang")
    async def _ayaya_anime_tayang(self, ctx: naoTimesContext):
        self.logger.info("Requesting anime airing time...")
        is_guild, can_paginate, _ = self._check_bot_perms(ctx)
        if not is_guild:
            return await ctx.send("Hanya bisa dilakukan di peladen!")
        if not can_paginate:
            perms_need = ["Manage Messages", "Read Message History", "Add Reactions", "Embed Links"]
            err_msg = "Bot tidak dapat memberikan hasil karena kekurangan "
            err_msg += "salah satu permission berikut:\n"
            err_msg += "\n".join(perms_need)
            return await ctx.send(err_msg)

        fetched_result, season = await self._fetch_anichart_data()
        if isinstance(fetched_result, str):
            return await ctx.send(fetched_result)

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
        ]

        def generate_embed_for_real(dataset: EpisodeInfoWrap):
            embed = disnake.Embed(color=0x19212D)
            embed.set_author(
                name="Anichart",
                url="https://anichart.net/",
                icon_url="https://anichart.net/favicon.ico",
            )
            final_value = []
            for data in dataset.dataset:
                final_value.append(f"- **{data._title}**\n{data.airdate}")
            embed.description = f"**{dataset.time}**" + "\n\n".join(final_value)
            embed.set_footer(text=f"{dataset.season}")
            return embed

        def generate_embed_wrapper(dataset: Dict[str, EpisodeInfoWrap]):
            embed = disnake.Embed(title="Listing Jadwal Tayang - " + season, color=0x19212D)
            embed.set_author(
                name="Anichart",
                url="https://anichart.net/",
                icon_url="https://p.ihateani.me/wtelbjmn.png",
            )
            real_value = []
            data_kk = list(dataset.keys())[: len(emote_list)]
            for n, date in enumerate(data_kk):
                real_value.append(f"{emote_list[n]} **{date}**")
            embed.description = "\n".join(real_value)
            return embed

        async def _generator_jadwal(
            dataset: Dict[str, EpisodeInfoWrap], _, message: disnake.Message, emote: str
        ):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return None, message

            all_keys = list(dataset.keys())
            proper_list = dataset.get(all_keys[emote_pos])
            if proper_list is None:
                return None, message
            child_gen = DiscordPaginator(self.bot, ctx, [proper_list])
            child_gen.set_generator(generate_embed_for_real)
            child_gen.remove_at_trashed = False
            child_gen.paginateable = False
            await child_gen.paginate(None, message)
            return None, message

        main_gen = DiscordPaginator(self.bot, ctx, [fetched_result])
        main_gen.set_generator(generate_embed_wrapper)
        all_fetch_keys = list(fetched_result.keys())[: len(emote_list)]
        for n, _ in enumerate(all_fetch_keys):
            main_gen.add_handler(emote_list[n], lambda x: True, _generator_jadwal)
        await main_gen.paginate(30.0)


def setup(bot: naoTimesBot):
    bot.add_cog(AyayaAnimeManga(bot))
