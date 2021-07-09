# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any, List, Union

import aiohttp
import discord
import discord.ext.commands as commands

from nthelper.bot import naoTimesBot
from nthelper.utils import DiscordPaginator, HelpGenerator


def setup(bot: naoTimesBot):
    bot.add_cog(nHController(bot))


async def nsfw_channel(ctx):
    if ctx.guild:
        return ctx.channel.is_nsfw()
    raise commands.NoPrivateMessage("Perintah tidak bisa dipakai di private message.")


TRANSLASI_BAHASA = {
    "English": "Inggris",
    "Chinese": "Cina",
    "Korean": "Korea",
    "Japanese": "Jepang",
}

TAG_TRANSLATION = {
    "parodies": ":nut_and_bolt: Parodi",
    "characters": ":nut_and_bolt: Karakter",
    "tags": ":nut_and_bolt: Label",
    "artists": ":nut_and_bolt: Seniman",
    "groups": ":nut_and_bolt: Circle/Grup",
    "languages": ":nut_and_bolt: Bahasa",
    "categories": ":nut_and_bolt: Kategori",
}

GQL_INFO_SCHEMAS = """query nhInfo($id:ID!) {
    nhentai {
        info(doujin_id:$id) {
            id
            media_id
            title {
                simple
                english
                japanese
            }
            cover_art {
                type
                url
                original_url
                sizes
            }
            tags {
                artists {
                    name
                    amount
                }
                categories {
                    name
                    amount
                }
                groups {
                    name
                    amount
                }
                languages {
                    name
                    amount
                }
                tags {
                    name
                    amount
                }
                parodies {
                    name
                    amount
                }
                characters {
                    name
                    amount
                }
            }
            images {
                type
                url
                original_url
                sizes
            }
            url
            publishedAt
            favorites
            total_pages
        }
    }
}"""

GQL_SEARCH_SCHEMAS = """query nhSearch($query:String!,$page:Int) {
    nhentai {
        search(query:$query,page:$page) {
            results {
                id
                media_id
                title {
                    simple
                    english
                    japanese
                }
                cover_art {
                    type
                    url
                    original_url
                    sizes
                }
                tags {
                    artists {
                        name
                        amount
                    }
                    categories {
                        name
                        amount
                    }
                    groups {
                        name
                        amount
                    }
                    languages {
                        name
                        amount
                    }
                    tags {
                        name
                        amount
                    }
                    parodies {
                        name
                        amount
                    }
                    characters {
                        name
                        amount
                    }
                }
                images {
                    type
                    url
                    original_url
                    sizes
                }
                url
                publishedAt
                favorites
                total_pages
            }
            pageInfo {
                total
            }
        }
    }
}"""

GQL_LATEST_SCHEMAS = """query nhLatest($page:Int) {
    nhentai {
        latest(page:$page) {
            results {
                id
                media_id
                title {
                    simple
                    english
                    japanese
                }
                cover_art {
                    type
                    url
                    original_url
                    sizes
                }
                tags {
                    artists {
                        name
                        amount
                    }
                    categories {
                        name
                        amount
                    }
                    groups {
                        name
                        amount
                    }
                    languages {
                        name
                        amount
                    }
                    tags {
                        name
                        amount
                    }
                    parodies {
                        name
                        amount
                    }
                    characters {
                        name
                        amount
                    }
                }
                images {
                    type
                    url
                    original_url
                    sizes
                }
                url
                publishedAt
                favorites
                total_pages
            }
            pageInfo {
                total
            }
        }
    }
}"""


def truncate(text: str, m: str) -> str:
    mamount = {"title": 256, "field": 1024, "desc": 2048, "footer": 2048}
    max_len = mamount.get(m, 1024)
    if len(text) > max_len:
        text = text[0 : max_len - 5] + " ..."
    return text


def walk(data: Any, notations: str) -> Union[Any, None]:
    split_not = notations.split(".")
    for nota in split_not:
        if nota.isdigit():
            nota = int(nota)
        try:
            data = data[nota]
        except (TypeError, ValueError, KeyError, AttributeError):
            return None
    return data


class NotNSFWChannel(Exception):
    pass


class nHController(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.nh.nHController")

    @staticmethod
    def is_msg_empty(msg: str, thr: int = 3) -> bool:
        split_msg: List[str] = msg.split(" ")
        split_msg = [m for m in split_msg if m != ""]
        if len(split_msg) < thr:
            return True
        return False

    @commands.group(aliases=["nh"])
    @commands.check(nsfw_channel)
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def nhi(self, ctx):
        msg = ctx.message.content
        if not ctx.invoked_subcommand:
            if not self.is_msg_empty(msg, 2):
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            helpcmd = HelpGenerator(
                self.bot,
                ctx,
                "nh",
                desc="Sebuah modul untuk membaca, melihat info, mencari doujin via nhentai",
            )
            await helpcmd.generate_field("nh", desc="Memunculkan bantuan perintah ini.")
            await helpcmd.generate_field(
                "nh cari",
                opts=[{"type": "r", "name": "query", "desc": "Kata kunci pencarian"}],
                desc="Mencari doujin di nhentai",
            )
            await helpcmd.generate_field(
                "nh info",
                opts=[{"type": "r", "name": "kode", "desc": "Kode nuklir digit di nHentai"}],
                desc='Melihat informasi sebuah doujin melalui "kode nuklir"',
            )
            await helpcmd.generate_field(
                "nh info",
                opts=[{"type": "r", "name": "kode", "desc": "Kode nuklir digit di nHentai"}],
                desc="Membaca langsung doujin di Discord menggunakan sistem proxy agar gambar tetap ke load",
            )
            await helpcmd.generate_field(
                "nh unduh",
                opts=[{"type": "r", "name": "kode", "desc": "Kode nuklir digit di nHentai"}],
                desc="Mendownload doujin dan dijadikan zip file, akan dibuat URL untuk lokasi mengunduhnya",
            )
            await helpcmd.generate_aliases()
            await ctx.send(embed=helpcmd.get())

    @staticmethod
    def cek_translasi(tags: List[dict]) -> str:
        lang: List[str] = [i["name"].capitalize() for i in tags["languages"]]  # type: ignore
        if "Translated" in lang:
            lang.remove("Translated")
            lang = [TRANSLASI_BAHASA.get(la, la) for la in lang]
            return "Terjemahan: " + ", ".join(lang)
        return "RAW ({})".format(TRANSLASI_BAHASA.get(lang[0], lang[0]))

    async def format_embed_search(self, data: dict, query: str) -> discord.Embed:
        embed = discord.Embed(title="Pencarian: {}".format(query), color=0x1F1F1F, url=data["url"])
        embed.set_footer(text="Kode: {} | Diprakasai oleh api.ihateani.me".format(data["id"]))
        embed.description = "**{}**\n{}".format(data["title"]["english"], self.cek_translasi(data["tags"]))
        embed.set_image(url=data["cover_art"]["url"])
        return embed

    async def format_embed_info(self, data: dict) -> discord.Embed:
        lang = [i["name"].capitalize() for i in data["tags"]["languages"]]
        if "Translated" in lang:
            lang.remove("Translated")
            lang_ = "Translasi " + TRANSLASI_BAHASA.get(lang[0], lang[0])
        lang_ = "RAW {}".format(TRANSLASI_BAHASA.get(lang[0], lang[0]))
        format_title = "{} [{}]".format(data["title"]["english"], lang_)
        embed = discord.Embed(
            title=format_title,
            color=0x1F1F1F,
            url=data["url"],
            timestamp=datetime.strptime(data["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ),
        )
        embed.description = "{}\n{}".format(data["title"]["japanese"], data["title"]["simple"],)
        for tag in data["tags"].keys():
            if data["tags"][tag]:
                tag_parsed = [aaa["name"].capitalize() for aaa in data["tags"][tag]]
                embed.add_field(
                    name=TAG_TRANSLATION[tag], value=", ".join(tag_parsed),
                )
        embed.add_field(
            name=":nut_and_bolt: Total Halaman", value="{} halaman".format(data["total_pages"]),
        )
        embed.set_footer(text="Favorit: {} | Diprakasai oleh api.ihateani.me".format(data["favorites"]))
        embed.set_image(url=data["cover_art"]["url"])
        return embed

    async def format_embed_image(
        self, data: dict, pos: Union[str, int], real_data: dict, data_total: Union[str, int]
    ) -> discord.Embed:
        embed = discord.Embed(
            title=real_data["title"]["english"],
            color=0x1F1F1F,
            url=real_data["url"],
            timestamp=datetime.strptime(real_data["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ),
        )
        embed.description = "{}/{}\n<{}>".format(pos + 1, data_total, data["url"])
        embed.set_image(url=data["url"])
        embed.set_footer(text="Diprakasai oleh api.ihateani.me")
        return embed

    async def format_embed_download(self, data: dict) -> discord.Embed:
        embed = discord.Embed(
            title=data["title"]["english"],
            color=0x1F1F1F,
            url=data["url"],
            timestamp=datetime.strptime(data["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ),
        )
        description = "Klik link dibawah ini untuk mulai mengunduh Doujin\n"
        description += f"https://nh.ihateani.me/read/{data['id']}/download\n\n"
        description += "It will start fetching a list of image to download that you can use\n"
        description += "If there is a lot of pages or images, it might take a while."
        embed.description = description
        embed.set_footer(text="Diprakasai oleh api.ihateani.me")
        embed.set_thumbnail(url=data["cover_art"]["url"])
        return embed

    @nhi.command(aliases=["search", "latest", "terbaru"])
    async def cari(self, ctx, *, query=None):
        msg_content = ctx.message.clean_content
        do_mode = msg_content.split()[1]

        schemas = GQL_LATEST_SCHEMAS
        variables = {"page": 1}
        nh_mode = "latest"
        if "search" in do_mode or "cari" in do_mode:
            if query:
                schemas = GQL_SEARCH_SCHEMAS
                variables["query"] = query
                nh_mode = "search"
            else:
                query = "Doujin terbaru"
        else:
            query = "Doujin terbaru"
        message = await ctx.send("Memulai proses pencarian, mohon tunggu.")
        self.logger.info(f"searching {query}")
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{self.bot.semver} (https://naoti.me/)"}
        ) as sesi:
            async with sesi.post(
                "https://api.ihateani.me/v2/graphql", json={"query": schemas, "variables": variables}
            ) as resp:
                try:
                    gql_raw = await resp.json()
                    response = walk(gql_raw, f"data.nhentai.{nh_mode}")
                    if response is None:
                        error_msg = walk(gql_raw, "errors.0.message")
                        if error_msg is None:
                            return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
                        if "404" in error_msg:
                            return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")
                        return await ctx.send(
                            f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`"
                        )
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        self.logger.info(f"{query}: parsing results...")
        resdata = response["results"]
        if len(resdata) < 1:
            return await ctx.send("Tidak dapat hasil.")

        await message.edit(content="Pencarian didapatkan.")

        async def wrap_start_image(datasets, position, message):
            await message.clear_reactions()
            dataset = datasets[position]
            total_img = len(dataset["images"])
            img_embed_gen = partial(self.format_embed_image, data_total=total_img, real_data=dataset)
            reader_gen = DiscordPaginator(self.bot, ctx)
            reader_gen.checker()
            reader_gen.set_generator(img_embed_gen, True)
            await reader_gen.start(datasets[position]["images"], None, message)
            return None, message

        async def wrap_start_dl(datasets, position, message):
            await message.clear_reactions()
            dl_gen = DiscordPaginator(self.bot, ctx, [], True)
            dl_gen.checker()
            dl_gen.set_generator(self.format_embed_download)
            await dl_gen.start([datasets[position]], None, message)
            return None, message

        async def wrap_start_info(datasets, position, message: discord.Message):
            await message.clear_reactions()
            info_gen = DiscordPaginator(self.bot, ctx, ["\N{INBOX TRAY}", "\N{OPEN BOOK}"], True)
            info_gen.checker()
            info_gen.set_handler(0, lambda x, y: True, wrap_start_dl)
            info_gen.set_handler(1, lambda x, y: True, wrap_start_image)
            info_gen.set_generator(self.format_embed_info)
            await info_gen.start([datasets[position]], None, message)
            return None, message

        main_gen = DiscordPaginator(self.bot, ctx, extra_emotes=["📜"])
        fmt_search = partial(self.format_embed_search, query=query)
        main_gen.set_generator(fmt_search)
        main_gen.add_handler(lambda x, y: True, wrap_start_info)
        await main_gen.start(resdata)

        await message.delete()
        await ctx.message.delete()

    @nhi.command(aliases=["informasi"])
    async def info(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Masukan kode nuklir yang benar.")

        message = await ctx.send("Memulai proses pengumpulan informasi, mohon tunggu.")
        self.logger.info(f"querying {kode_nuklir}")
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{self.bot.semver} (https://naoti.me/)"}
        ) as sesi:
            async with sesi.post(
                "https://api.ihateani.me/v2/graphql",
                json={"query": GQL_INFO_SCHEMAS, "variables": {"id": kode_nuklir}},
            ) as resp:
                try:
                    gql_raw = await resp.json()
                    data2 = walk(gql_raw, "data.nhentai.info")
                    if data2 is None:
                        error_msg = walk(gql_raw, "errors.0.message")
                        if error_msg is None:
                            return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
                        if "404" in error_msg:
                            return await ctx.send("Tidak dapat menemukan doujin tersebut!")
                        return await ctx.send(
                            f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`"
                        )
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        async def wrap_start_image(datasets, position, message):
            await message.clear_reactions()
            dataset = datasets[position]
            total_img = len(dataset["images"])
            img_embed_gen = partial(self.format_embed_image, data_total=total_img, real_data=dataset)
            reader_gen = DiscordPaginator(self.bot, ctx)
            reader_gen.checker()
            reader_gen.set_generator(img_embed_gen, True)
            await reader_gen.start(datasets[position]["images"], None, message)
            return None, message

        async def wrap_start_dl(datasets, position, message):
            await message.clear_reactions()
            dl_gen = DiscordPaginator(self.bot, ctx, [], True)
            dl_gen.checker()
            dl_gen.set_generator(self.format_embed_download)
            await dl_gen.start([datasets[position]], None, message)
            return None, message

        await message.delete()

        info_gen = DiscordPaginator(self.bot, ctx, ["\N{INBOX TRAY}", "\N{OPEN BOOK}"], True)
        info_gen.set_handler(0, lambda x, y: True, wrap_start_dl)
        info_gen.set_handler(1, lambda x, y: True, wrap_start_image)
        info_gen.set_generator(self.format_embed_info)
        await info_gen.start([data2], None)
        await ctx.message.delete()

    @nhi.command(aliases=["down", "dl", "download"])
    async def unduh(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Masukan kode nuklir yang benar.")

        message = await ctx.send("Memulai proses pengumpulan informasi, mohon tunggu.")
        self.logger.info(f"querying {kode_nuklir}")
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{self.bot.semver} (https://naoti.me/)"}
        ) as sesi:
            async with sesi.post(
                "https://api.ihateani.me/v2/graphql",
                json={"query": GQL_INFO_SCHEMAS, "variables": {"id": kode_nuklir}},
            ) as resp:
                try:
                    gql_raw = await resp.json()
                    data2 = walk(gql_raw, "data.nhentai.info")
                    if data2 is None:
                        error_msg = walk(gql_raw, "errors.0.message")
                        if error_msg is None:
                            return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
                        if "404" in error_msg:
                            return await ctx.send("Tidak dapat menemukan doujin tersebut!")
                        return await ctx.send(
                            f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`"
                        )
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        await message.delete()
        data2["url"] = "https://nhentai.net/g/" + kode_nuklir

        embed = discord.Embed(
            title=data2["title"]["english"],
            color=0x1F1F1F,
            url=data2["url"],
            timestamp=datetime.strptime(data2["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            ),
        )
        description = "Klik link dibawah ini untuk mulai mengunduh Doujin\n"
        description += f"https://nh.ihateani.me/read/{kode_nuklir}/download\n\n"
        description += "It will start fetching a list of image to download that you can use\n"
        description += "If there is a lot of pages or images, it might take a while."
        embed.description = description
        embed.set_footer(text="Diprakasai oleh api.ihateani.me")
        embed.set_thumbnail(url=data2["cover_art"]["url"])

        self.logger.info(f"{kode_nuklir}: sending download link...")
        msg = await ctx.send(embed=embed)

        while True:
            reactmoji = ["✅"]
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

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await msg.clear_reactions()
                await ctx.message.delete()
                return await msg.delete()

    @nhi.command(aliases=["read"])
    async def baca(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Masukan kode nuklir yang benar.")

        message = await ctx.send("Memulai proses pengumpulan informasi, mohon tunggu.")
        self.logger.info(f"querying {kode_nuklir}")
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{self.bot.semver} (https://naoti.me/)"}
        ) as sesi:
            async with sesi.post(
                "https://api.ihateani.me/v2/graphql",
                json={"query": GQL_INFO_SCHEMAS, "variables": {"id": kode_nuklir}},
            ) as resp:
                try:
                    gql_raw = await resp.json()
                    data2 = walk(gql_raw, "data.nhentai.info")
                    if data2 is None:
                        error_msg = walk(gql_raw, "errors.0.message")
                        if error_msg is None:
                            return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
                        if "404" in error_msg:
                            return await ctx.send("Tidak dapat menemukan doujin tersebut!")
                        return await ctx.send(
                            f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`"
                        )
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        await message.delete()
        total_img = len(data2["images"])
        img_embed_gen = partial(self.format_embed_image, data_total=total_img, real_data=data2)
        reader_gen = DiscordPaginator(self.bot, ctx)
        reader_gen.set_generator(img_embed_gen, True)
        await reader_gen.start(data2["images"], None)

    @nhi.error
    async def nhi_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            perms = ["Manage Messages", "Embed Links", "Read Message History", "Add Reactions"]
            await ctx.send("Bot tidak memiliki salah satu dari perms ini:\n" + "\n".join(perms))
        if isinstance(error, commands.CheckFailure):
            self.logger.error("need NSFW channel.")
            await ctx.send(
                "Untuk menggunakan perintah ini, dibutuhkan channel yang sudah diaktifkan mode NSFW-nya."
            )
