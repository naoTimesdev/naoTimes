import logging
from collections.abc import Callable, Mapping
from functools import partial

import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.paginator import DiscordPaginatorUI
from naotimes.showtimes import ShowtimesPoster
from naotimes.showtimes.cogbase import rgbhex_to_rgbint
from naotimes.utils import WalkValue, complex_walk, cutoff_text

ANILIST_QUERY = """
query ($page: Int, $perPage: Int, $search: String, $type: MediaType, $format: MediaFormat) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            total
            currentPage
            lastPage
            hasNextPage
            perPage
        }
        media(search: $search, type: $type, format: $format) {
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
            status(version:2)
            source(version:3)
            season
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
"""


def create_time_format(secs: float, t: Callable[..., str]) -> str:
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
        return_text += t("animanga.time.months", months=months) + " "

    return return_text + t("animanga.time.remaining", days=days, hours=hours, minutes=minutes, seconds=secs)


class EpisodeInfo:
    def __init__(
        self,
        episode: int | None = None,
        time_remain: str | None = None,
        airdate: str | None = None,
        *,
        sort_seconds: float | None = None,
        t: Callable[..., str],
    ):
        self._episode = episode
        self.time_remain = time_remain
        self.airdate = airdate
        self.sort_seconds = sort_seconds
        self._t = t

        self._id = None
        self._title = None
        self._color = 0x19212D

    @property
    def episode(self) -> str:
        if isinstance(self._episode, int):
            return str(self._episode).zfill(2)
        return self._t("animanga.episode.unknown")

    @property
    def raw_episode(self) -> int | None:
        return self._episode

    def bind(self, id: str, title: str, color: int = 0x19212D):
        self._id = id
        self._title = title
        if isinstance(color, int):
            self._color = color


class EpisodeInfoWrap:
    def __init__(self, dataset: list[EpisodeInfo], season: str, time: str):
        self.dataset = dataset
        self.season = season
        self.time = time


class ChapterInfo:
    def __init__(self, chapter: int | None = None, volume: int | None = None, *, t: Callable[..., str]):
        self._chapter = chapter
        self._volume = volume
        self._t = t

    @property
    def chapter(self):
        if isinstance(self._chapter, int):
            return self._t("animanga.chapter.label", chapter=self._chapter)
        return self._t("animanga.chapter.unknown")

    @property
    def volume(self):
        if isinstance(self._volume, int):
            return self._t("animanga.volume.label", volume=self._volume)
        return self._t("animanga.volume.unknown")

    def __str__(self):
        return f"{self.chapter}/{self.volume}"


class AnilistResult:
    def __init__(
        self,
        id: str,
        title: str,
        other_title: list[str] | None = None,
        description: str | None = None,
        start: str | None = None,
        end: str | None = None,
        poster: ShowtimesPoster | None = None,
        format: str | None = None,
        source: str | None = None,
        status: str | None = None,
        season: str | None = None,
        genres: list[str] | None = None,
        rating: int | None = None,
        *,
        t: Callable[..., str],
    ):
        self.id = id
        self.title = title
        self._other = other_title if other_title is not None else []
        self.description = description
        self._start = start
        self._end = end
        self._poster = poster
        self._format = format
        self._source = source
        self._status = status
        self._rating = rating
        self._genres = genres if genres is not None else []
        self._season = season
        self._t = t

        self._extra_data: EpisodeInfo | ChapterInfo | None = None
        self._is_anime = False

    @property
    def other_title(self) -> str:
        if len(self._other) < 1:
            return self._t("animanga.common.none")
        return "\n".join(self._other)

    @property
    def start(self) -> str:
        if not self._start:
            return self._t("animanga.common.not_released")
        return self._start

    @property
    def end(self) -> str:
        if not self._end:
            return self._t("animanga.common.not_ended")
        return self._end

    @property
    def poster_url(self) -> str | None:
        if self._poster is None:
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
            "TV": "tv",
            "TV_SHORT": "tv_short",
            "MOVIE": "movie",
            "SPECIAL": "special",
            "OVA": "ova",
            "ONA": "ona",
            "MUSIC": "music",
            "NOVEL": "novel",
            "MANGA": "manga",
            "ONE_SHOT": "one_shot",
        }
        return self._t(f"animanga.format.{format_tl.get(self._format or '', 'other')}")

    @property
    def source(self) -> str:
        source_tl = {
            "ORIGINAL": "original",
            "MANGA": "manga",
            "VISUAL_NOVEL": "visual_novel",
            "LIGHT_NOVEL": "light_novel",
            "VIDEO_GAME": "video_game",
            "OTHER": "other",
            "NOVEL": "novel",
            "DOUJINSHI": "doujinshi",
            "ANIME": "anime",
            "WEB_NOVEL": "web_novel",
            "LIVE_ACTION": "live_action",
            "GAME": "game",
            "COMIC": "comic",
            "MULTIMEDIA_PROJECT": "multimedia_project",
            "PICTURE_BOOK": "picture_book",
        }
        return self._t(f"animanga.source.{source_tl.get(self._source or '', 'other')}")

    @property
    def status(self) -> str:
        status_tl = {
            "FINISHED": "finished",
            "RELEASING": "releasing",
            "NOT_YET_RELEASED": "not_yet_released",
            "CANCELLED": "cancelled",
            "HIATUS": "hiatus",
        }
        return self._t(f"animanga.status.{status_tl.get(self._status or '', 'other')}")

    @property
    def season(self) -> str | None:
        season_tl = {
            "WINTER": "winter",
            "SPRING": "spring",
            "SUMMER": "summer",
            "FALL": "fall",
        }
        key = season_tl.get(self._season or "")
        if key is None:
            return None
        return self._t(f"animanga.season.{key}")

    @property
    def rating(self) -> str:
        if self._rating is None:
            return self._t("animanga.common.none")
        return f"{self._rating / 10}/10.0"

    @property
    def genre(self) -> str:
        if isinstance(self._genres, list):
            if len(self._genres) > 0:
                return ", ".join(self._genres)
        return self._t("animanga.common.unknown")

    @property
    def url(self) -> str:
        method = "anime" if self._is_anime else "manga"
        return f"https://anilist.co/{method}/{self.id}"

    def bind(self, extra_data: EpisodeInfo | ChapterInfo) -> None:
        if isinstance(extra_data, EpisodeInfo):
            extra_data.bind(self.id, self.title, self.color)
            self._is_anime = True
            self._extra_data = extra_data
        elif isinstance(extra_data, ChapterInfo):
            self._extra_data = extra_data

    @property
    def extras(self) -> EpisodeInfo | ChapterInfo | None:
        return self._extra_data

    @property
    def has_next(self) -> bool:
        if self._extra_data is None:
            return False
        if isinstance(self._extra_data, EpisodeInfo):
            if isinstance(self._extra_data.airdate, str):
                return True
        return False


def _as_mapping(value: WalkValue | None) -> Mapping[str | int, WalkValue] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _optional_string(value: WalkValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: WalkValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _optional_number(value: WalkValue | None) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def create_nicer_anilist_date(date: WalkValue | None, locale: str | None = None) -> str | None:
    date_data = _as_mapping(date)
    if date_data is None:
        return None
    year = _optional_int(date_data.get("year"))
    month = _optional_int(date_data.get("month"))
    day = _optional_int(date_data.get("day"))
    if year is None:
        return None

    # Use arrow to format the date
    if day and month:
        return f"{arrow.get(year, month, day).format('DD MMM YYYY', locale=locale or 'id')}"
    elif month:
        return f"{arrow.get(year, month, 1).format('MMM YYYY', locale=locale or 'id')}"
    return str(year)


def html2markdown(text: str) -> str:
    replace_list = {
        "<br>": "\n",
        "</br>": "\n",
        "<br />": "\n",
        "<br/>": "\n",
        "<i>": "*",
        "</i>": "*",
        "<i/>": "*",
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
    def __select_cover(media: Mapping[str | int, WalkValue]) -> str | None:
        cover = _as_mapping(media.get("coverImage"))
        if cover is None:
            return None
        return (
            _optional_string(cover.get("extraLarge"))
            or _optional_string(cover.get("large"))
            or _optional_string(cover.get("medium"))
        )

    async def __parse_anilist(
        self,
        raw_data: Mapping[str | int, WalkValue],
        is_anime: bool = True,
        force_manga_only: bool = False,
        *,
        t: Callable[..., str],
        locale: str | None = None,
    ) -> list[AnilistResult]:
        media_info = complex_walk(raw_data, "Page.media")
        if not isinstance(media_info, list):
            return []
        self.logger.info(f"Got {len(media_info)} raw results...")
        if len(media_info) == 0:
            return []

        parsed_result: list[AnilistResult] = []
        self.logger.info("Parsing search result...")
        for raw_media in media_info:
            media = _as_mapping(raw_media)
            if media is None:
                continue
            media_id = media.get("id")
            if not isinstance(media_id, (str, int)) or isinstance(media_id, bool):
                continue
            anilist_id = str(media_id)
            title_data = _as_mapping(media.get("title"))
            titles = [
                _optional_string(title_data.get(key)) if title_data is not None else None
                for key in ("romaji", "english", "native")
            ]
            main_title = next((title for title in titles if title), None)
            if main_title is None:
                continue
            other_title: list[str] = []
            for title in titles:
                if not title:
                    continue
                if title == main_title:
                    continue
                other_title.append(title)

            rating = _optional_int(media.get("averageScore"))
            description = _optional_string(media.get("description"))
            if description:
                description = html2markdown(description)
            raw_genres = media.get("genres", [])
            genres = [genre for genre in raw_genres if isinstance(genre, str)] if isinstance(raw_genres, list) else []
            status = _optional_string(media.get("status"))
            format = _optional_string(media.get("format"))
            source = _optional_string(media.get("source"))
            season = _optional_string(media.get("season"))
            if force_manga_only and format == "NOVEL":
                continue

            cover_color_value = complex_walk(media, "coverImage.color")
            cover_color = rgbhex_to_rgbint(_optional_string(cover_color_value) or "")
            cover_image = self.__select_cover(media)
            poster = ShowtimesPoster(cover_image, cover_color) if cover_image is not None else None
            started = create_nicer_anilist_date(complex_walk(media, "startDate"), locale)
            ended = create_nicer_anilist_date(complex_walk(media, "endDate"), locale)

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
                season,
                genres,
                rating,
                t=t,
            )
            if is_anime:
                episode = _optional_int(media.get("episodes"))
                ep_info = EpisodeInfo(episode, t=t)
                next_airing = _as_mapping(media.get("nextAiringEpisode"))
                if next_airing is not None:
                    airdate = next_airing.get("airingAt")
                    if isinstance(airdate, (str, int, float)) and not isinstance(airdate, bool):
                        try:
                            ep_info.airdate = arrow.get(airdate).format("DD MMMM YYYY", locale=locale or "id")
                        except (TypeError, ValueError):
                            pass
                    time_until_air = _optional_number(next_airing.get("timeUntilAiring"))
                    if time_until_air is not None:
                        ep_info.time_remain = create_time_format(float(time_until_air), t)
                result.bind(ep_info)
            else:
                chapter = _optional_int(media.get("chapters"))
                volumes = _optional_int(media.get("volumes"))
                result.bind(ChapterInfo(chapter, volumes, t=t))
            parsed_result.append(result)

        return parsed_result

    async def _fetch_anichart_data(self, t: Callable[..., str], locale: str | None = None):
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

        def _format_time(time_secs: float):
            time_days = int(time_secs // 86400)
            time_secs -= time_days * 86400
            time_hours = int(time_secs // 3600)
            time_secs -= time_hours * 3600
            time_minutes = int(time_secs // 60)
            time_secs -= time_minutes * 60

            if time_days > 0:
                if time_hours > 0:
                    return t("animanga.time.days_hours", days=time_days, hours=time_hours)
                return t("animanga.time.days_minutes", days=time_days, minutes=time_minutes)

            if time_hours > 0:
                if time_minutes > 0:
                    return t("animanga.time.hours_minutes", hours=time_hours, minutes=time_minutes)
                return t("animanga.time.hours", hours=time_hours)

            if time_minutes > 0:
                return t("animanga.time.minutes", minutes=time_minutes)

            return t("animanga.time.seconds", seconds=time_secs)

        current_season = seasonal.get(current_month, "winter").upper()
        season_info = f"{t(f'animanga.season.{current_season.lower()}')} {current_year}"
        anibucket = self.bot.anibucket
        if anibucket is None:
            return t("animanga.anilist_unavailable"), season_info
        all_query_results: list[WalkValue] = []
        base_vars = {
            "season": current_season,
            "year": current_year,
            "page": 1,
            "perPage": 50,
            "statuses": ["RELEASING", "NOT_YET_RELEASED"],
            "format": ["TV", "TV_SHORT", "MOVIE", "ONA"],
        }
        current_page = 1
        async for api_res in anibucket.paginate(ANICHART_QUERY, base_vars):
            if api_res.data is None:
                current_page += 1
                continue
            collected_media = complex_walk(api_res.data, "Page.media")
            if isinstance(collected_media, list):
                self.logger.info(f"Merging page: {current_page}")
                all_query_results.extend(collected_media)
            current_page += 1

        formatted_query: list[EpisodeInfo] = []
        for raw_media in all_query_results:
            media = _as_mapping(raw_media)
            if media is None:
                continue
            media_id = media.get("id")
            if not isinstance(media_id, (str, int)) or isinstance(media_id, bool):
                continue
            anilist_id = str(media_id)
            title_data = _as_mapping(media.get("title"))
            titles = [
                _optional_string(title_data.get(key)) if title_data is not None else None
                for key in ("romaji", "english", "native")
            ]
            main_title = next((title for title in titles if title), None)
            if main_title is None:
                continue
            next_airs = _as_mapping(media.get("nextAiringEpisode"))

            next_episode = _optional_int(next_airs.get("episode")) if next_airs is not None else None
            if next_airs:
                time_secs = _optional_number(next_airs.get("timeUntilAiring"))
                if time_secs is None:
                    sort_seconds = None
                    time_until_air = t("animanga.embed.schedule_value_placeholder")
                else:
                    sort_seconds = float(time_secs)
                    time_until_air = _format_time(sort_seconds)
            else:
                sort_seconds = 100.0
                time_until_air = create_nicer_anilist_date(media.get("startDate"), locale) or t(
                    "animanga.embed.unknown_date"
                )

            episode_info = EpisodeInfo(
                next_episode,
                time_until_air,
                time_until_air,
                sort_seconds=sort_seconds,
                t=t,
            )
            episode_info.bind(anilist_id, main_title)
            formatted_query.append(episode_info)

        if len(formatted_query) < 1:
            return t("animanga.no_season_results"), season_info

        # Sort by airtime
        formatted_query.sort(key=lambda x: x.sort_seconds if x.sort_seconds is not None else float("inf"))

        mapped_airing: dict[str, EpisodeInfoWrap] = {}
        others_label = t("animanga.schedule.others")
        for data in formatted_query:
            if data.raw_episode is None or data.sort_seconds is None:
                if others_label not in mapped_airing:
                    mapped_airing[others_label] = EpisodeInfoWrap([], season_info, others_label)
                mapped_airing[others_label].dataset.append(data)
            else:
                day = str(int(data.sort_seconds // 86400)).zfill(2)

                if day not in mapped_airing:
                    mapped_airing[day] = EpisodeInfoWrap([], season_info, day)
                mapped_airing[day].dataset.append(data)

        sorted_mapped_airing: dict[str, EpisodeInfoWrap] = {}
        for the_day in sorted(mapped_airing.keys()):
            original_key = str(the_day)
            day_label = the_day.removeprefix("0")
            if the_day == others_label:
                display_day = others_label
            elif day_label == "0":
                display_day = t("animanga.schedule.less_than_day")
            else:
                display_day = t("animanga.schedule.days_left", days=day_label)
            fixed_data = mapped_airing[original_key]
            fixed_data.time = display_day
            sorted_mapped_airing[display_day] = fixed_data

        return sorted_mapped_airing, season_info

    @staticmethod
    def _generate_anime_embed(data: AnilistResult, t: Callable[..., str]) -> discord.Embed:
        embed = discord.Embed(color=data.color)
        if data.poster_url:
            embed.set_thumbnail(url=data.poster_url)
        embed.set_author(
            name=data.title,
            url=data.url,
            icon_url="https://p.ihateani.me/hxlsxvpo.png",
        )
        embed.description = cutoff_text(data.description or t("animanga.embed.synopsis_placeholder"), 2000)
        embed.set_footer(text=t("animanga.embed.footer_id", id=data.id))

        embed.add_field(name=t("animanga.embed.other_title"), value=data.other_title)
        extras = data.extras
        episode = extras.episode if isinstance(extras, EpisodeInfo) else t("animanga.episode.unknown")
        embed.add_field(name=t("animanga.embed.episode"), value=episode)
        embed.add_field(name=t("animanga.embed.status"), value=data.status)
        embed.add_field(name=t("animanga.embed.score"), value=data.rating)
        start_fmt = data.start
        season_fmt = data.season
        if season_fmt:
            start_fmt += f"\n({season_fmt})"
        embed.add_field(name=t("animanga.embed.release"), value=start_fmt)
        embed.add_field(name=t("animanga.embed.end"), value=data.end)
        embed.add_field(name=t("animanga.embed.format"), value=data.format)
        embed.add_field(name=t("animanga.embed.source"), value=data.source)
        return embed

    @staticmethod
    def _generate_manga_embed(data: AnilistResult, t: Callable[..., str]) -> discord.Embed:
        embed = discord.Embed(color=data.color)
        if data.poster_url:
            embed.set_thumbnail(url=data.poster_url)
        embed.set_author(
            name=data.title,
            url=data.url,
            icon_url="https://p.ihateani.me/hxlsxvpo.png",
        )
        embed.description = cutoff_text(data.description or t("animanga.embed.synopsis_placeholder"), 2000)
        embed.set_footer(text=t("animanga.embed.footer_id", id=data.id))

        embed.add_field(name=t("animanga.embed.other_title"), value=data.other_title)
        extras = data.extras
        chapter_volume = str(extras) if isinstance(extras, ChapterInfo) else t("animanga.chapter_volume.unknown")
        embed.add_field(name=t("animanga.embed.chapter_volume"), value=chapter_volume)
        embed.add_field(name=t("animanga.embed.status"), value=data.status)
        embed.add_field(name=t("animanga.embed.score"), value=data.rating)
        embed.add_field(name=t("animanga.embed.release"), value=data.start)
        embed.add_field(name=t("animanga.embed.end"), value=data.end)
        embed.add_field(name=t("animanga.embed.format"), value=data.format)
        embed.add_field(name=t("animanga.embed.source"), value=data.source)
        return embed

    @staticmethod
    def _next_episode_embed(data: AnilistResult, t: Callable[..., str]) -> discord.Embed:
        embed = discord.Embed(color=data.color)
        embed.set_author(name=data.title, url=data.url, icon_url="https://p.ihateani.me/hxlsxvpo.png")
        extras = data.extras
        if isinstance(extras, EpisodeInfo):
            embed.set_footer(
                text=t(
                    "animanga.embed.airing_on",
                    date=extras.airdate or t("animanga.embed.unknown_date"),
                )
            )
            embed.add_field(
                name=t("animanga.embed.episode_label", episode=extras.episode),
                value=extras.time_remain or t("animanga.embed.schedule_value_placeholder"),
                inline=False,
            )
        else:
            embed.add_field(
                name=t("animanga.embed.schedule_field"),
                value=t("animanga.embed.schedule_unavailable"),
                inline=False,
            )
        return embed

    def _check_bot_perms(self, ctx: naoTimesContext):
        guild = ctx.guild
        if guild is None:
            # DMs: embeds are always allowed.
            return False, True
        bot_member = guild.me
        if bot_member is None or ctx.channel is None:
            return True, False
        has_embed_perms = ctx.channel.permissions_for(bot_member).embed_links
        return True, has_embed_perms

    @app_commands.command(
        name="anime",
        description=app_commands.locale_str("Cari anime di Anilist", key="ayaya.animanga.description_anime"),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul yang ingin dicari", key="ayaya.animanga.option_judul"),
    )
    async def _ayaya_anime(self, inter: discord.Interaction, judul: str):
        """Cari anime di Anilist"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        self.logger.info(f"Searching for {judul}")
        variables = {"search": judul, "page": 1, "perPage": 25, "type": "ANIME"}
        anibucket = self.bot.anibucket
        if anibucket is None:
            await ctx.send(ctx.t("animanga.anilist_unavailable"))
            return
        requested = await anibucket.handle(ANILIST_QUERY, variables)
        if requested.errors:
            await ctx.send(ctx.t("animanga.anilist_unavailable"))
            return
        if requested.data is None:
            await ctx.send(ctx.t("animanga.anilist_no_data"))
            return

        _, has_embed_perms = self._check_bot_perms(ctx)
        if not has_embed_perms:
            return await ctx.send(ctx.t("animanga.embed_permission"))

        parsed_result = await self.__parse_anilist(requested.data, True, t=ctx.t, locale=ctx.locale)
        if len(parsed_result) < 1:
            return await ctx.send(ctx.t("animanga.no_results"))
        self.logger.info(f"Got {len(parsed_result)} hits")

        def handle_episode_table(dataset: EpisodeInfo, _: int, __: discord.Message, view: DiscordPaginatorUI):
            nextep_gen = DiscordPaginatorUI(view.ctx, [dataset], paginateable=False)
            nextep_gen.attach(partial(self._next_episode_embed, t=ctx.t))
            nextep_gen.parent = view
            nextep_gen.timeout = 30.0
            return nextep_gen

        main_gen = DiscordPaginatorUI(ctx, parsed_result)
        main_gen.attach(partial(self._generate_anime_embed, t=ctx.t))
        main_gen.add_handler(
            ctx.t("animanga.schedule.handler"),
            lambda data: data.has_next,
            handle_episode_table,
            emoji="⌛",
        )
        await main_gen.interact(30.0)

    @app_commands.command(
        name="manga",
        description=app_commands.locale_str("Cari manga di Anilist", key="ayaya.animanga.description_manga"),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul yang ingin dicari", key="ayaya.animanga.option_judul"),
    )
    async def _ayaya_manga(self, inter: discord.Interaction, judul: str):
        """Cari manga di Anilist"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        _, has_embed_perms = self._check_bot_perms(ctx)
        if not has_embed_perms:
            return await ctx.send(ctx.t("animanga.embed_permission"))
        self.logger.info(f"Searching for {judul}")
        variables = {"search": judul, "page": 1, "perPage": 25, "type": "MANGA"}
        anibucket = self.bot.anibucket
        if anibucket is None:
            await ctx.send(ctx.t("animanga.anilist_unavailable"))
            return
        requested = await anibucket.handle(ANILIST_QUERY, variables)
        if requested.errors:
            await ctx.send(ctx.t("animanga.anilist_unavailable"))
            return
        if requested.data is None:
            await ctx.send(ctx.t("animanga.anilist_no_data"))
            return

        parsed_result = await self.__parse_anilist(requested.data, False, True, t=ctx.t, locale=ctx.locale)
        if len(parsed_result) < 1:
            return await ctx.send(ctx.t("animanga.no_results"))
        self.logger.info(f"Got {len(parsed_result)} hits")

        if ctx.guild is not None:
            main_gen = DiscordPaginatorUI(ctx, parsed_result)
            main_gen.attach(partial(self._generate_manga_embed, t=ctx.t))
            await main_gen.interact(30.0)
        else:
            generate_embed = self._generate_manga_embed(parsed_result[0], t=ctx.t)
            await ctx.send(embed=generate_embed)

    @app_commands.command(
        name="novel",
        description=app_commands.locale_str("Cari light novel di Anilist", key="ayaya.animanga.description_novel"),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul yang ingin dicari", key="ayaya.animanga.option_judul"),
    )
    async def _ayaya_novel(self, inter: discord.Interaction, judul: str):
        """Cari light novel di Anilist"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        _, has_embed_perms = self._check_bot_perms(ctx)
        if not has_embed_perms:
            return await ctx.send(ctx.t("animanga.embed_permission"))
        self.logger.info(f"Searching for {judul}")
        variables = {"search": judul, "page": 1, "perPage": 25, "type": "MANGA", "format": "NOVEL"}
        anibucket = self.bot.anibucket
        if anibucket is None:
            await ctx.send(ctx.t("animanga.anilist_unavailable"))
            return
        requested = await anibucket.handle(ANILIST_QUERY, variables)
        if requested.errors:
            await ctx.send(ctx.t("animanga.anilist_unavailable"))
            return
        if requested.data is None:
            await ctx.send(ctx.t("animanga.anilist_no_data"))
            return

        parsed_result = await self.__parse_anilist(requested.data, False, t=ctx.t, locale=ctx.locale)
        if len(parsed_result) < 1:
            return await ctx.send(ctx.t("animanga.no_results"))
        self.logger.info(f"Got {len(parsed_result)} hits")

        if ctx.guild is not None:
            main_gen = DiscordPaginatorUI(ctx, parsed_result)
            main_gen.attach(partial(self._generate_manga_embed, t=ctx.t))
            await main_gen.interact(30.0)
        else:
            generate_embed = self._generate_manga_embed(parsed_result[0], t=ctx.t)
            await ctx.send(embed=generate_embed)

    @app_commands.command(
        name="tayang",
        description=app_commands.locale_str(
            "Lihat jadwal tayang anime musim ini",
            key="ayaya.animanga.description_tayang",
        ),
    )
    async def _ayaya_anime_tayang(self, inter: discord.Interaction):
        """Lihat jadwal tayang anime musim ini"""
        ctx = await self.bot.get_context(inter)
        await ctx.defer()
        self.logger.info("Requesting anime airing time...")
        _, has_embed_perms = self._check_bot_perms(ctx)
        if not has_embed_perms:
            return await ctx.send(ctx.t("animanga.embed_permission"))

        fetched_result, season = await self._fetch_anichart_data(ctx.t, ctx.locale)
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
            embed = discord.Embed(color=0x19212D)
            embed.set_author(
                name="Anichart",
                url="https://anichart.net/",
                icon_url="https://anichart.net/favicon.ico",
            )
            final_value = []
            for data in dataset.dataset:
                final_value.append(f"- **{data._title}**\n{data.airdate}")
            embed.description = f"**{dataset.time}**\n" + "\n\n".join(final_value)
            embed.set_footer(text=f"{dataset.season}")
            return embed

        def generate_embed_wrapper(dataset: dict[str, EpisodeInfoWrap]):
            embed = discord.Embed(title=ctx.t("animanga.schedule.title", season=season), color=0x19212D)
            embed.set_author(
                name="Anichart",
                url="https://anichart.net/",
                icon_url="https://p.ihateani.me/hxlsxvpo.png",
            )
            real_value = []
            data_kk = list(dataset.keys())[: len(emote_list)]
            for n, date in enumerate(data_kk):
                real_value.append(f"{emote_list[n]} **{date}**")
            embed.description = "\n".join(real_value)
            return embed

        def _generator_jadwal(
            dataset: dict[str, EpisodeInfoWrap], _, __: discord.Message, view: DiscordPaginatorUI, emote: str
        ):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return ""

            all_keys = list(dataset.keys())
            proper_list = dataset.get(all_keys[emote_pos])
            if proper_list is None:
                return ""
            child_gen = DiscordPaginatorUI(ctx, [proper_list], paginateable=False)
            child_gen.attach(generate_embed_for_real)
            child_gen.parent = view
            child_gen.timeout = 30.0
            return child_gen

        main_gen = DiscordPaginatorUI(ctx, [fetched_result])
        main_gen.attach(generate_embed_wrapper)
        all_fetch_keys = list(fetched_result.keys())[: len(emote_list)]
        for idx, namae in enumerate(all_fetch_keys):
            emote = emote_list[idx]
            partial_gen = partial(_generator_jadwal, emote=emote)
            main_gen.add_handler(namae, lambda x: True, partial_gen, emoji=emote)
        await main_gen.interact(30.0)
        # all_fetch_keys = list(fetched_result.keys())[: len(emote_list)]
        # for n, _ in enumerate(all_fetch_keys):
        #     main_gen.add_handler(emote_list[n], lambda x: True, _generator_jadwal)
        # await main_gen.paginate(30.0)


async def setup(bot: naoTimesBot):
    await bot.add_cog(AyayaAnimeManga(bot))
