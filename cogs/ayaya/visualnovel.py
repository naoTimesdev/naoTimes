import asyncio
import logging
import random
import re
from functools import partial
from typing import List, Literal, Optional

import disnake
import orjson
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.paginator import DiscordPaginator
from naotimes.utils import complex_walk


class VNDBModel:
    def __init__(
        self,
        id: str,
        title: str,
        aliases: List[str] = None,
        image: str = None,
        description: str = "-",
        platforms: List[str] = [],
        languages: List[str] = [],
        relations: List[str] = [],
        screenshots: List[str] = [],
        duration: Optional[Literal[1, 2, 3, 4, 5]] = None,
        score: float = 0.0,
        release_date: str = "Tidak diketahui",
        has_anime: bool = False,
    ):
        self._id = id
        self._title = title
        self._aliases = aliases
        self._image = image
        self._description = description
        self._platforms = platforms
        self._languages = languages
        self._duration = duration
        self._relasi = relations
        self._screenies = screenshots
        self._score = score
        self._is_released = release_date
        self._has_anime = has_anime

        if self._image is None:
            if len(self._screenies) > 0:
                self._image = self._screenies[0]
            else:
                self._image = "https://s.vndb.org/linkimg/vndb1.gif"

    @property
    def id(self) -> str:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def url(self) -> str:
        return f"https://vndb.org/v{self._id}"

    @property
    def footer(self) -> str:
        return f"ID: {self._id}"

    @property
    def aliases(self) -> str:
        if isinstance(self._aliases, str):
            return self._aliases or "Tidak diketahui"
        elif isinstance(self._aliases, list):
            if not self._aliases:
                return "Tidak diketahui"
            return ", ".join(self._aliases)
        return "Tidak diketahui"

    @property
    def rating(self) -> str:
        return str(self._score) if self._score else "Tidak diketahui"

    @property
    def poster(self) -> Optional[str]:
        return self._image

    @property
    def description(self) -> str:
        return self._description if self._description else "Tidak diketahui"

    @property
    def platform(self) -> str:
        if len(self._platforms) < 1:
            return "Tidak diketahui"
        platforms_map = {
            "win": "Windows",
            "ios": "iOS",
            "and": "Android",
            "psv": "PSVita",
            "swi": "Switch",
            "xb3": "XB360",
            "xbo": "XB1",
            "n3d": "3DS",
            "mac": "MacOS/OSX",
        }
        return ", ".join(map(lambda x: platforms_map.get(x, x.upper()), self._platforms))

    @property
    def language(self) -> str:
        if len(self._languages) < 1:
            return "Tidak diketahui"
        return ", ".join(self._languages)

    @property
    def relation(self) -> str:
        if len(self._relasi) < 1:
            return "Tidak ada"
        return "\n".join(self._relasi)

    @property
    def screenies(self) -> List[str]:
        return self._screenies

    @property
    def duration(self) -> str:
        duration_map = {
            1: "Sangat Pendek (< 2 Jam)",
            2: "Pendek (2 - 10 Jam)",
            3: "Menengah (10 - 30 Jam)",
            4: "Panjang (30 - 50 Jam)",
            5: "Sangat Panjang (> 50 Jam)",
        }
        return duration_map.get(self._duration, "Tidak diketahui")

    @property
    def released(self) -> str:
        return self._is_released if self._is_released else "Tidak diketahui"

    @property
    def has_anime(self) -> str:
        return "Ada" if self._has_anime else "Tidak Ada"


def bbcode_markdown(string: str) -> str:
    if not string:
        return "-"
    regex_lists = {
        r"\[b\](.*)\[\\b\]": "**\\1**",
        r"\[i\](.*)\[\\i\]": "*\\1*",
        r"\[u\](.*)\[\\u\]": "__\\1__",
        r"\[s\](.*)\[\\s\]": "~~\\1~~",
        r"\[code\](.*)\[\\code\]": "`\\1`",
        r"\[quote\](.*)\[\\quote\]": "```\\1```",
        r"\[quote\=.+?\](.*)\[\\quote\]": "```\\1```",
        r"\[center\](.*)\[\\center\]": "\\1",
        r"\[color\=.+?\](.*)\[\\color\]": "\\1",
        r"\[img\](.*)\[\\img\]": "![\\1](\\1)",
        r"\[img=(.+?)\](.*)\[\\img\]": "![\\2](\\1)",
        r"\[url=(.+?)\]((?:.|\n)+?)\[\/url\]": "[\\2](\\1)",
        r"\[url\]((?:.|\n)+?)\[\/url\]": "[\\1](\\1)",
    }
    for pattern, repl in regex_lists.items():
        string = re.sub(pattern, repl, string, flags=re.MULTILINE | re.I)
    return string


class AyayaVisualNovel(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Ayaya.VisualNovel")
        self.vnconn = bot.vndb_socket

    async def _try_login(self):
        if not self.vnconn.loggedin:
            self.logger.info("Trying to authenticate connection...")
            try:
                await asyncio.wait_for(self.vnconn.async_login(), 15.0)
            except asyncio.TimeoutError:
                return "Koneksi timeout, tidak dapat terhubung dengan VNDB!"
        return None

    async def _fetch_database(self, search: str):
        login_success = await self._try_login()
        if login_success is not None:
            return login_success
        mode = "title"
        delim = "~"
        if search.strip().isdigit():
            mode = "id"
            delim = "="
            search = int(search)

        command = "vn basic,relations,anime,details,tags,stats,screens ("
        command += f'{mode}{delim}"{search}")'

        self.logger.info(f"Executing: {command}")
        try:
            result = await asyncio.wait_for(self.vnconn.send_command_async("get", command), timeout=15.0)
        except asyncio.TimeoutError:
            return "Koneksi timeout, tidak dapat terhubung dengan VNDB!"

        if isinstance(result, str) and result.startswith("results "):
            result = result[len("results ") :]
            parsed_result = orjson.loads(result)
        else:
            return "VNDB tidak menemukan hasil dimaksud"

        err_msg = complex_walk(parsed_result, "message")
        if err_msg is not None:
            self.logger.error(f"{search}: an error occured: {err_msg}")
            return "Terjadi kesalahan ketika mencari hal yang anda inginkan!"

        total_data = parsed_result["num"]
        if total_data < 1:
            self.logger.warning(f"{search}: no result found")
            return "Tidak dapat menemukan VN dengan judul/ID yang diberikan!"

        self.logger.info(f"{search}: parsing result...")
        full_query_request: List[VNDBModel] = []
        for item in parsed_result["items"]:
            title = item["title"]
            other_title = item["aliases"]
            aliases = []
            if isinstance(other_title, str):
                aliases = other_title.split("\n")
            vn_id = item["id"]

            durasi = item["length"]
            platforms = item["platforms"]

            rating = item["rating"]
            description = bbcode_markdown(item["description"])
            poster = item["image"]

            languages = []
            if item["languages"]:
                for lang in item["languages"]:
                    languages.append(lang.upper())

            has_anime = False
            if item["anime"]:
                has_anime = True

            screenies = complex_walk(item, "screens.*.image")
            relations = []
            if item["relations"]:
                for relasi in item["relations"]:
                    relasi_t = f"{relasi['title']} ({relasi['id']})"
                    relations.append(relasi_t)

            released = item["released"]

            dataset = VNDBModel(
                vn_id,
                title,
                aliases,
                poster,
                description,
                platforms,
                languages,
                relations,
                screenies,
                durasi,
                rating,
                released,
                has_anime,
            )

            full_query_request.append(dataset)
        return full_query_request

    async def _random_search(self):
        log_result = await self._try_login()
        if log_result is not None:
            return log_result

        self.logger.info("Fetching VNDB statistics...")
        try:
            res = await asyncio.wait_for(self.vnconn.send_command_async("dbstats"), 15.0)
        except asyncio.TimeoutError:
            return "Koneksi timeout, tidak dapat terhubung dengan VNDB."
        if isinstance(res, str) and res.startswith("dbstats "):
            res = res.replace("dbstats ", "")
            res = orjson.loads(res)
        elif not isinstance(res, dict):
            return "Terjadi kesalahan ketika memproses hasil dari VNDB"

        total_vn = res["vn"]
        random_get = random.randint(1, total_vn)  # nosec
        self.logger.info(f"Fetching VN {random_get} from randomizer...")
        return await self._fetch_database(str(random_get))

    @staticmethod
    def _design_embed(data: VNDBModel) -> disnake.Embed:
        embed = disnake.Embed(color=0x225588)
        embed.set_thumbnail(url=data.poster)
        embed.set_author(
            name=data.title,
            url=data.url,
            icon_url="https://ihateani.me/o/vndbico.png",
        )
        embed.set_footer(text=data.footer)

        embed.add_field(name="Nama Lain", value=data.aliases, inline=True)
        embed.add_field(name="Durasi", value=data.duration, inline=True)
        embed.add_field(name="Bahasa", value=data.language, inline=True)
        embed.add_field(name="Platform", value=data.platform, inline=True)
        embed.add_field(name="Rilis", value=data.released, inline=True)
        embed.add_field(name="Skor", value=data.rating, inline=True)
        embed.add_field(name="Relasi (VNID)", value=data.relation, inline=True)
        embed.add_field(name="Adaptasi Anime?", value=data.has_anime, inline=True)
        embed.add_field(name="Sinopsis", value=data.description, inline=False)
        return embed

    @staticmethod
    def _design_screenies(image: str, position: int, data: VNDBModel) -> List[str]:
        total_screenies = len(data.screenies)
        embed = disnake.Embed(color=0x225588)
        embed.description = image
        embed.set_author(
            name=f"{data.title} ({position + 1}/{total_screenies})",
            url=data.url,
            icon_url="https://ihateani.me/o/vndbico.png",
        )
        embed.set_image(url=image)
        return embed

    @commands.command(name="vn", aliases=["visualnovel", "eroge", "vndb"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True,
        embed_links=True,
        read_message_history=True,
        add_reactions=True,
    )
    async def _ayaya_vnmain(self, ctx: naoTimesContext, *, judul: str):
        vnqres = await self._fetch_database(judul)
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        async def _screenies_handler(data: VNDBModel, _, message: disnake.Message):
            screen_gen = DiscordPaginator(self.bot, ctx, data.screenies)
            screen_gen.remove_at_trashed = False
            img_embed_gen = partial(self._design_screenies, data=data)
            screen_gen.set_generator(img_embed_gen)
            timeout = await screen_gen.paginate(30.0, message)
            return None, message, timeout

        main_gen = DiscordPaginator(self.bot, ctx, vnqres)
        main_gen.set_generator(self._design_embed)
        main_gen.remove_at_trashed = False
        main_gen.add_handler("📸", lambda data: len(data.screenies) > 0, _screenies_handler)
        await main_gen.paginate(30.0)

    @commands.command(name="randomvn", aliases=["randomvisualnovel", "randomeroge", "vnrandom"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True,
        embed_links=True,
        read_message_history=True,
        add_reactions=True,
    )
    async def _ayaya_vnrandom(self, ctx: naoTimesContext):
        vnqres = await self._random_search()
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        async def _screenies_handler(data: VNDBModel, _, message: disnake.Message):
            screen_gen = DiscordPaginator(self.bot, ctx, data.screenies)
            screen_gen.remove_at_trashed = False
            img_embed_gen = partial(self._design_screenies, data=data)
            screen_gen.set_generator(img_embed_gen)
            timeout = await screen_gen.paginate(30.0, message)
            return None, message, timeout

        first_r = vnqres[0]
        if len(first_r.screenies) > 0:
            main_gen = DiscordPaginator(self.bot, ctx, vnqres)
            main_gen.set_generator(self._design_embed)
            main_gen.remove_at_trashed = False
            main_gen.add_handler("📸", lambda data: len(data.screenies) > 0, _screenies_handler)
            await main_gen.paginate(30.0)
        else:
            embed_data = self._design_embed(first_r)
            await ctx.send(embed=embed_data)


def setup(bot: naoTimesBot):
    bot.add_cog(AyayaVisualNovel(bot))
