import logging
from functools import partial
from typing import List

import arrow
import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption
from naotimes.models import nh as nhmodel
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import complex_walk

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

NH_INFO_BASE = """
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
"""

GQL_SCHEMAS = r"""
query nhInfo($id:ID!) {
    nhentai {
        info(doujin_id:$id) {
            {{INFO}}
        }
    }
}

query nhSearch($query:String!,$page:Int) {
    nhentai {
        search(query:$query,page:$page) {
            results {
                {{INFO}}
            }
            pageInfo {
                total
            }
        }
    }
}

query nhLatest($page:Int) {
    nhentai {
        latest(page:$page) {
            results {
                {{INFO}}
            }
            pageInfo {
                total
            }
        }
    }
}
"""

GQL_SCHEMAS = GQL_SCHEMAS.replace(r"{{INFO}}", NH_INFO_BASE)


class NSFWCogNH(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("NSFW.nH")

    @commands.group(name="nh", aliases=["nhi"])
    @commands.guild_only()
    @commands.is_nsfw()
    @commands.bot_has_guild_permissions(embed_links=True)
    async def _nsfw_nh(self, ctx: naoTimesContext):
        if not ctx.invoked_subcommand:
            if not ctx.empty_subcommand(2):
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")

            helpcmd = ctx.create_help(
                "nh", desc="Sebuah modul untuk membaca, melihat info, mencari doujin via nhentai"
            )
            helpcmd.add_fields(
                [
                    HelpField("nh", "Memunculkan bantuan perintah ini"),
                    HelpField(
                        "nh cari",
                        "Mencari doujin di nhentai",
                        [
                            HelpOption(
                                "query",
                                "Kata kunci pencarian",
                                True,
                            )
                        ],
                    ),
                    HelpField("nh latest", "Melihat doujin terbaru di nhentai"),
                    HelpField(
                        "nh baca",
                        "Membaca langsung doujin yang diinginkan (anti blokir!)",
                        [
                            HelpOption(
                                "kode",
                                "Kode nuklir yang ingin dibaca",
                                True,
                            )
                        ],
                    ),
                    HelpField(
                        "nh unduh",
                        "Mendownload doujin yang diinginkan",
                        [
                            HelpOption(
                                "kode",
                                "Kode nuklir yang ingin diunduh",
                                True,
                            )
                        ],
                    ),
                ]
            )
            helpcmd.add_aliases(["nhi"])
            await ctx.send(embed=helpcmd.get())

    @staticmethod
    def _cek_translasi(tags: List[dict]) -> str:
        lang: List[str] = list(map(lambda x: x["name"].capitalize(), tags["languages"]))
        if "Translated" in lang:
            lang.remove("Translated")
            lang = list(map(lambda x: TRANSLASI_BAHASA.get(x, x), lang))
            return "Terjemahan: " + ", ".join(lang)
        first_lang = TRANSLASI_BAHASA.get(lang[0], lang[0])
        return f"RAW ({first_lang})"

    @staticmethod
    def _get_base_title(titles: nhmodel._NHDoujinTitleInfo) -> str:
        english: str = titles.get("english")
        japanese: str = titles.get("japanese")
        simple: str = titles.get("simple")
        return simple or english or japanese

    @staticmethod
    def _highlight_title(titles: nhmodel._NHDoujinTitleInfo) -> str:
        english: str = titles.get("english")
        japanese: str = titles.get("japanese")
        simple: str = titles.get("simple") or ""
        eng_or_jp = japanese or english or ""
        return eng_or_jp.replace(simple, f"**{simple}**")

    def _fmt_search_embed(self, data: nhmodel.NHDoujinInfo, query: str) -> discord.Embed:
        embed = discord.Embed(title=f"Pencarian: {query}", color=0x1F1F1F, url=data["url"])
        embed.set_author(
            name="nh", url=data["url"], icon_url="https://nh.ihateani.me/android-icon-192x192.png"
        )
        embed.description = f"**{self._get_base_title(data['title'])}**\n{self._cek_translasi(data['tags'])}"
        embed.set_image(url=data["cover_art"]["url"])
        embed.set_footer(text=f"Kode: {data['id']} | Diprakasai oleh api.ihateani.me")
        return embed

    def _fmt_info_embed(self, data: nhmodel.NHDoujinInfo) -> discord.Embed:
        embed = discord.Embed(
            color=0x1F1F1F,
            timestamp=arrow.get(data.publishedAt).datetime,
        )
        embed.set_author(
            name="nh", url=data["url"], icon_url="https://nh.ihateani.me/android-icon-192x192.png"
        )
        embed.description = self._highlight_title(data.title)
        embed.description += f"\nURL: {data.url}"
        tagar: str
        isi_tagar: nhmodel._NHDoujinTagBase
        for tagar, isi_tagar in data.tags.items():
            if isi_tagar:
                tag_parsed = list(map(lambda x: x.name.capitalize(), isi_tagar))
                embed.add_field(
                    name=TAG_TRANSLATION.get(tagar, tagar.capitalize()), value=", ".join(tag_parsed)
                )
        embed.add_field(name=":nut_and_bolt: Total Halaman", value=f"{data['total_pages']} halaman")
        embed.set_footer(text=f"Favorit: {data['favorites']} | Diprakasai oleh api.ihateani.me")
        embed.set_image(url=data["cover_art"]["url"])
        return embed

    def _fmt_read_embed(
        self, image: nhmodel._NHDoujinImageInfo, pos: int, data: nhmodel.NHDoujinInfo, image_total: int
    ):
        embed = discord.Embed(
            color=0x1F1F1F,
            timestamp=arrow.get(data["publishedAt"]).datetime,
        )
        embed.set_author(
            name="nh", url=data["url"], icon_url="https://nh.ihateani.me/android-icon-192x192.png"
        )
        description = [self._highlight_title(data.title)]
        description.append(f"{pos + 1}/{image_total}")
        description.append(f"<{data.url}>")
        embed.description = "\n".join(description)
        embed.set_image(url=image["url"])
        embed.set_footer(text=f"Kode: {data['id']} | Diprakasai oleh api.ihateani.me")
        return embed

    def _fmt_download_embed(self, data: nhmodel.NHDoujinInfo) -> discord.Embed:
        embed = discord.Embed(
            color=0x1F1F1F,
            timestamp=arrow.get(data["publishedAt"]).datetime,
        )
        embed.set_author(name="nh", url=data.url, icon_url="https://nh.ihateani.me/android-icon-192x192.png")
        description = self._highlight_title(data.title) + "\n\n"
        description += "Klik link dibawah ini untuk mulai mengunduh Doujin!\n"
        description += f"https://nh.ihateani.me/read/{data.id}/download"
        embed.description = description
        embed.set_footer(text=f"Kode: {data.id} | Diprakasai oleh api.ihateani.me")
        embed.set_thumbnail(url=data["cover_art"]["url"])
        return embed

    async def wrap_start_image(self, dataset: dict, _, __, view: DiscordPaginatorUI, ctx: naoTimesContext):
        total_img = len(dataset["images"])
        img_embed_gen = partial(
            self._fmt_read_embed,
            data=dataset,
            image_total=total_img,
        )
        reader_gen = DiscordPaginatorUI(ctx, dataset["images"])
        reader_gen.attach(img_embed_gen)
        reader_gen.parent = view
        return reader_gen

    async def wrap_start_dl(self, dataset: dict, _, __, view: DiscordPaginatorUI, ctx: naoTimesContext):
        dl_gen = DiscordPaginatorUI(ctx, [dataset], paginateable=False)
        dl_gen.attach(self._fmt_download_embed)
        dl_gen.parent = view
        return dl_gen

    async def wrap_start_info(self, dataset: dict, _, __, view: DiscordPaginatorUI, ctx: naoTimesContext):
        info_gen = DiscordPaginatorUI(ctx, [dataset], paginateable=False)
        dl_wrap_ctx = partial(self.wrap_start_dl, ctx=ctx)
        img_wrap_ctx = partial(self.wrap_start_image, ctx=ctx)
        info_gen.add_handler("Unduh", lambda x: True, dl_wrap_ctx, emoji="📥")
        info_gen.add_handler("Baca", lambda x: True, img_wrap_ctx, emoji="📖")
        info_gen.attach(self._fmt_info_embed)
        info_gen.parent = view
        return info_gen

    @_nsfw_nh.command(name="cari", aliases=["search", "latest", "terbaru"])
    async def _nh_nsfw_cari(self, ctx: naoTimesContext, *, query: str = None):
        msg_content: str = ctx.message.clean_content
        do_mode = msg_content.split()[1]

        nh_operation = "nhLatest"
        nh_mode = "latest"
        variables = {"page": 1}
        if "search" in do_mode or "cari" in do_mode:
            if query:
                nh_operation = "nhSearch"
                nh_mode = "search"
                variables["query"] = query
            else:
                query = "Doujin terbaru"
        else:
            query = "Doujin terbaru"

        message = await ctx.send("Memulai pencarian, mohon tunggu...")
        self.logger.info(f"Searching for: {query}")
        response = await self.bot.ihaapi.query(GQL_SCHEMAS, variables, nh_operation)
        if response.errors:
            error_msg = response.errors[0].message
            if error_msg is None:
                return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
            if "404" in error_msg:
                return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")
            return await ctx.send(f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`")

        self.logger.info(f"{query}: parsing results...")
        results = complex_walk(response.data, f"nhentai.{nh_mode}.results")
        if not results:
            return await ctx.send("Tidak dapat hasil!")

        await message.edit(content="Pencarian didapatkan...")

        await message.delete(no_log=True)
        main_gen = DiscordPaginatorUI(ctx, results)
        info_wrap_ctx = partial(self.wrap_start_info, ctx=ctx)
        main_gen.add_handler("Info", lambda x: True, info_wrap_ctx, emoji="📜")
        search_gen = partial(self._fmt_search_embed, query=query)
        main_gen.attach(search_gen)
        await main_gen.interact()
        await ctx.message.delete(no_log=True)

    @_nsfw_nh.command(name="info", aliases=["informasi"])
    async def _nsfw_nh_info(self, ctx: naoTimesContext, kode_nuklir: str):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Kode nuklir tidak valid!")

        message = await ctx.send("Memulai pencarian, mohon tunggu...")
        self.logger.info(f"Searching for: {kode_nuklir}")
        variables = {"id": kode_nuklir}
        response = await self.bot.ihaapi.query(GQL_SCHEMAS, variables, "nhInfo")
        if response.errors:
            error_msg = response.errors[0].message
            if error_msg is None:
                return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
            if "404" in error_msg:
                return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")
            return await ctx.send(f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`")

        self.logger.info(f"{kode_nuklir}: parsing results...")
        result = complex_walk(response.data, "nhentai.info")
        if not result:
            return await ctx.send("Tidak dapat kode yang sesuai!")

        await message.delete()
        await self.wrap_start_info(result, 0, None, ctx, True)
        await ctx.message.delete(no_log=True)

    @_nsfw_nh.command(name="unduh", aliases=["down", "dl", "download"])
    async def _nsfw_nh_unduh(self, ctx: naoTimesContext, kode_nuklir: str):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Kode nuklir tidak valid!")

        message = await ctx.send("Memulai pencarian, mohon tunggu...")
        self.logger.info(f"Searching for: {kode_nuklir}")
        variables = {"id": kode_nuklir}
        response = await self.bot.ihaapi.query(GQL_SCHEMAS, variables, "nhInfo")
        if response.errors:
            error_msg = response.errors[0].message
            if error_msg is None:
                return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
            if "404" in error_msg:
                return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")
            return await ctx.send(f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`")

        self.logger.info(f"{kode_nuklir}: parsing results...")
        result = complex_walk(response.data, "nhentai.info")
        if not result:
            return await ctx.send("Tidak dapat kode yang sesuai!")
        await message.delete()
        await self.wrap_start_dl(result, 0, None, ctx, True)
        await ctx.message.delete(no_log=True)

    @_nsfw_nh.command(name="baca", aliases=["read"])
    async def _nsfw_nh_baca(self, ctx: naoTimesContext, kode_nuklir: str):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Kode nuklir tidak valid!")

        message = await ctx.send("Memulai pencarian, mohon tunggu...")
        self.logger.info(f"Searching for: {kode_nuklir}")
        variables = {"id": kode_nuklir}
        response = await self.bot.ihaapi.query(GQL_SCHEMAS, variables, "nhInfo")
        if response.errors:
            error_msg = response.errors[0].message
            if error_msg is None:
                return await ctx.send("Terjadi kesalahan ketika ingin menghubungi API")
            if "404" in error_msg:
                return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")
            return await ctx.send(f"Terjadi kesalahan ketika memproses data dari API\n`{error_msg}`")

        self.logger.info(f"{kode_nuklir}: parsing results...")
        result = complex_walk(response.data, "nhentai.info")
        if not result:
            return await ctx.send("Tidak dapat kode yang sesuai!")
        await message.delete()
        await self.wrap_start_image(result, 0, None, ctx, True)
        await ctx.message.delete(no_log=True)

    @_nsfw_nh.error
    async def _nsfw_nh_error(self, ctx: naoTimesContext, error: Exception):
        if isinstance(error, commands.NSFWChannelRequired):
            await ctx.send(
                "Untuk menggunakan perintah ini, dibutuhkan channel yang sudah diaktifkan mode NSFW-nya."
            )
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Hanya bisa dijalankan disebuah peladen Discord!")
        elif isinstance(error, commands.BotMissingPermissions):
            perms = ["Manage Messages", "Embed Links", "Read Message History", "Add Reactions"]
            await ctx.send("Bot tidak memiliki salah satu dari perms ini:\n" + "\n".join(perms))


async def setup(bot: naoTimesBot):
    await bot.add_cog(NSFWCogNH(bot))
