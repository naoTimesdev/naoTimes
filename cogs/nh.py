# -*- coding: utf-8 -*-

import logging
from typing import List, Union

import aiohttp
import discord
import discord.ext.commands as commands
from urllib.parse import quote_plus
from datetime import datetime


def setup(bot):
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


def truncate(text: str, m: str) -> str:
    mamount = {"title": 256, "field": 1024, "desc": 2048, "footer": 2048}
    max_len = mamount.get(m, 1024)
    if len(text) > max_len:
        text = text[0 : max_len - 5] + " ..."
    return text


class NotNSFWChannel(Exception):
    pass


class nHController(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.nh.nHController")

    @commands.group(aliases=["nh"])
    @commands.check(nsfw_channel)
    async def nhi(self, ctx):
        if not ctx.invoked_subcommand:
            helpmain = discord.Embed(
                title="Bantuan Perintah (!nh)", description="versi 2.0.0", color=0x00AAAA,
            )
            helpmain.set_thumbnail(url="https://image.ibb.co/darSzH/question_mark_1750942_640.png")
            helpmain.set_author(
                name="naoTimes", icon_url="https://p.n4o.xyz/i/naotimes_ava.png",
            )
            helpmain.add_field(
                name="!nh", value="```Memunculkan bantuan perintah```", inline=False,
            )
            helpmain.add_field(
                name="!nh cari <query>", value="```Mencari kode nuklir.```", inline=False,
            )
            helpmain.add_field(
                name="!nh info <kode>", value="```Melihat informasi kode nuklir.```", inline=False,
            )
            helpmain.add_field(
                name="!nh baca <kode>", value="```Membaca langsung kode nuklir.```", inline=False,
            )
            helpmain.add_field(
                name="!nh unduh <kode>",
                value="```Mendownload kode nuklir dan dijadikan .zip file"
                " (limit file adalah 3 hari sebelum dihapus dari server).```",
                inline=False,
            )
            helpmain.add_field(name="Aliases", value="Tidak ada", inline=False)
            helpmain.set_footer(text="Dibawakan oleh naoTimes " "|| Dibuat oleh N4O#8868 versi 2.0.0")
            await ctx.send(embed=helpmain)

    @staticmethod
    def cek_translasi(tags: List[dict]) -> str:
        lang: List[str] = [i[0].capitalize() for i in tags["languages"]]  # type: ignore
        if "Translated" in lang:
            lang.remove("Translated")
            lang = [TRANSLASI_BAHASA.get(l, l) for l in lang]
            return "Terjemahan: " + ", ".join(lang)
        return "RAW ({})".format(TRANSLASI_BAHASA.get(lang[0], lang[0]))

    async def format_embed_search(self, data: dict, query: str) -> discord.Embed:
        embed = discord.Embed(title="Pencarian: {}".format(query), color=0x1F1F1F, url=data["url"],)
        embed.set_footer(text="Kode: {} | Diprakasai oleh api.ihateani.me".format(data["id"]))
        embed.description = "**{}**\n{}".format(data["title"], self.cek_translasi(data["tags"]))
        embed.set_image(url=data["cover"])
        return embed

    async def format_embed_info(self, data: dict) -> discord.Embed:
        lang = [i[0].capitalize() for i in data["tags"]["languages"]]
        if "Translated" in lang:
            lang.remove("Translated")
            lang_ = "Translasi " + TRANSLASI_BAHASA.get(lang[0], lang[0])
        lang_ = "RAW {}".format(TRANSLASI_BAHASA.get(lang[0], lang[0]))
        format_title = "{} [{}]".format(data["title"], lang_)
        embed = discord.Embed(
            title=format_title,
            color=0x1F1F1F,
            url=data["url"],
            timestamp=datetime.fromtimestamp(data["posted_time"]),
        )
        embed.description = "{}\n{}".format(
            data["original_title"]["japanese"], data["original_title"]["other"],
        )
        for tag in data["tags"].keys():
            if data["tags"][tag]:
                tag_parsed = [aaa[0].capitalize() for aaa in data["tags"][tag]]
                embed.add_field(
                    name=TAG_TRANSLATION[tag], value=", ".join(tag_parsed),
                )
        embed.add_field(
            name=":nut_and_bolt: Total Halaman", value="{} halaman".format(data["total_pages"]),
        )
        embed.set_footer(text="Favorit: {} | Diprakasai oleh api.ihateani.me".format(data["favorites"]))
        embed.set_image(url=data["cover"])
        return embed

    async def format_embed_image(
        self, data: dict, pos: Union[str, int], data_total: Union[str, int], img_link: str
    ) -> discord.Embed:
        embed = discord.Embed(
            title=data["title"],
            color=0x1F1F1F,
            url=data["url"],
            timestamp=datetime.fromtimestamp(data["posted_time"]),
        )
        embed.description = "{}/{}\n<{}>".format(pos, data_total, img_link)
        embed.set_image(url=img_link)
        embed.set_footer(text="Diprakasai oleh api.ihateani.me")
        return embed

    @nhi.command(aliases=["search", "latest", "terbaru"])
    async def cari(self, ctx, *, query=None):
        msg_content = ctx.message.clean_content
        do_mode = msg_content.split()[1]
        url_to_use = "https://api.ihateani.me/nh/latest"
        if "search" in do_mode or "cari" in do_mode:
            if query:
                url_to_use = "https://api.ihateani.me/nh/search?q={}".format(quote_plus(query))
            else:
                query = "Doujin terbaru"
        else:
            query = "Doujin terbaru"
        message = await ctx.send("Memulai proses pencarian, mohon tunggu.")
        self.logger.info(f"searching {query}")
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(url_to_use) as resp:
                try:
                    response = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        await message.edit(content="Pencarian didapatkan.")

        self.logger.info(f"{query}: parsing results...")
        resdata = response["results"]
        total_data = response["total_data"]

        first_run = True
        num = 1
        while True:
            if first_run:
                data = resdata[num - 1]
                embed = await self.format_embed_search(data, query)

                first_run = False
                self.logger.info(f"{query}: sending results...")
                msg = await ctx.send(embed=embed)
                await message.delete()

            reactmoji = []
            if total_data == 1 and num == 1:
                pass
            elif num == 1:
                reactmoji.append("⏩")
            elif num == total_data:
                reactmoji.append("⏪")
            elif num > 1 and num < total_data:
                reactmoji.extend(["⏪", "⏩"])
            reactmoji.append("📜")
            reactmoji.append("✅")
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
                self.logger.warn(f"{query}: done, nuking embed!")
                await msg.clear_reactions()
                await ctx.message.delete()
                return await msg.delete()
            elif "⏪" in str(res.emoji):
                self.logger.debug(f"{query}: previous result.")
                num = num - 1
                data = resdata[num - 1]

                embed = await self.format_embed_search(data, query)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                self.logger.debug(f"{query}: next result.")
                num = num + 1
                data = resdata[num - 1]

                embed = await self.format_embed_search(data, query)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "📜" in str(res.emoji):
                self.logger.info(f"{data['id']}: checking info...")
                await msg.clear_reactions()
                first_run_2 = True
                download_text_open = False
                while True:
                    reactmoji2 = []
                    if not download_text_open:
                        reactmoji2.append("\N{OPEN BOOK}")  # Read
                        reactmoji2.append("\N{INBOX TRAY}")  # Down
                    reactmoji2.append("✅")  # Back

                    if first_run_2:
                        embed = await self.format_embed_info(data)
                        first_run_2 = False
                        await msg.edit(embed=embed)

                    for reaction in reactmoji2:
                        await msg.add_reaction(reaction)

                    def check_react2(reaction, user):
                        if reaction.message.id != msg.id:
                            return False
                        if user != ctx.message.author:
                            return False
                        if str(reaction.emoji) not in reactmoji2:
                            return False
                        return True

                    res2, user2 = await self.bot.wait_for("reaction_add", check=check_react2)
                    if user2 != ctx.message.author:
                        pass
                    elif "✅" in str(res2.emoji):
                        await msg.clear_reactions()
                        if not download_text_open:
                            self.logger.warn(f"{data['id']}: going back to" " search results...")
                            embed = await self.format_embed_search(data, query)

                            await msg.edit(embed=embed)
                            break
                        self.logger.debug(f"{data['id']}: going back to info")
                        embed = await self.format_embed_info(data)
                        await msg.edit(embed=embed)
                        download_text_open = False
                    elif "\N{INBOX TRAY}" in str(res2.emoji):  # Download
                        self.logger.info(f"{data['id']}: showing download link...")
                        embed = discord.Embed(
                            title=data["title"],
                            color=0x1F1F1F,
                            url=data["url"],
                            timestamp=datetime.fromtimestamp(data["posted_time"]),
                        )
                        embed.description = "Klik link dibawah ini untuk mendownload\n<https://api.ihateani.me/nh/unduh?id={}>\n\nJika gambar banyak, akan memakan waktu lebih lama ketika proses sebelum download.".format(  # noqa: E501
                            data["id"]
                        )
                        embed.set_footer(text="Diprakasai oleh api.ihateani.me")
                        embed.set_thumbnail(url=data["cover"])

                        download_text_open = True
                        await msg.clear_reactions()
                        await msg.edit(embed=embed)
                    elif "\N{OPEN BOOK}" in str(res2.emoji):  # Read
                        self.logger.info(f"{data['id']}: showing reader...")
                        await msg.clear_reactions()

                        dataset_img = data["images"]
                        dataset_total = len(dataset_img)
                        first_run_3 = True
                        pospos = 1
                        while True:
                            if first_run_3:
                                img_link = dataset_img[pospos - 1]
                                embed = await self.format_embed_image(data, pospos, dataset_total, img_link)

                                first_run_3 = False
                                await msg.edit(embed=embed)

                            reactmoji3 = []
                            if dataset_total < 2:
                                break
                            if pospos == 1:
                                reactmoji3 = ["⏩"]
                            elif dataset_total == pospos:
                                reactmoji3 = ["⏪"]
                            elif pospos > 1 and pospos < dataset_total:
                                reactmoji3 = ["⏪", "⏩"]
                            reactmoji3.append("✅")
                            for reaction in reactmoji3:
                                await msg.add_reaction(reaction)

                            def check_react3(reaction, user):
                                if reaction.message.id != msg.id:
                                    return False
                                if user != ctx.message.author:
                                    return False
                                if str(reaction.emoji) not in reactmoji3:
                                    return False
                                return True

                            res3, user3 = await self.bot.wait_for("reaction_add", check=check_react3)
                            if user3 != ctx.message.author:
                                pass
                            if "✅" in str(res3.emoji):
                                self.logger.warn(f"{data['id']}: going back to info")
                                embed = await self.format_embed_info(data)
                                await msg.clear_reactions()
                                await msg.edit(embed=embed)
                                break
                            if "⏪" in str(res3.emoji):
                                self.logger.debug(f"{data['id']}: reader: " "previous image...")
                                pospos = pospos - 1
                                img_link = dataset_img[pospos - 1]

                                embed = await self.format_embed_image(data, pospos, dataset_total, img_link)
                                await msg.clear_reactions()
                                await msg.edit(embed=embed)
                            elif "⏩" in str(res3.emoji):
                                self.logger.debug(f"{data['id']}: reader: " "next image...")
                                pospos = pospos + 1
                                img_link = dataset_img[pospos - 1]

                                embed = await self.format_embed_image(data, pospos, dataset_total, img_link)
                                await msg.clear_reactions()
                                await msg.edit(embed=embed)

    @nhi.command(aliases=["informasi"])
    async def info(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Masukan kode nuklir yang benar.")

        message = await ctx.send("Memulai proses pengumpulan informasi, mohon tunggu.")
        self.logger.info(f"querying {kode_nuklir}")
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get("https://api.ihateani.me/nh/info/{}".format(kode_nuklir)) as resp:
                try:
                    data2 = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        await message.delete()
        first_run_2 = True
        data2["url"] = "https://nhentai.net/g/" + kode_nuklir
        download_text_open = False
        while True:
            reactmoji2 = []
            if not download_text_open:
                reactmoji2.append("\N{OPEN BOOK}")  # Read
                reactmoji2.append("\N{INBOX TRAY}")  # Down
            reactmoji2.append("✅")  # Back

            if first_run_2:
                self.logger.info(f"{kode_nuklir}: sending result.")
                embed = await self.format_embed_info(data2)
                first_run_2 = False
                msg = await ctx.send(embed=embed)

            for reaction in reactmoji2:
                await msg.add_reaction(reaction)

            def check_react2(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji2:
                    return False
                return True

            res2, user2 = await self.bot.wait_for("reaction_add", check=check_react2)
            if user2 != ctx.message.author:
                pass
            elif "✅" in str(res2.emoji):
                await msg.clear_reactions()
                if not download_text_open:
                    self.logger.warn(f"{kode_nuklir}: done, nuking embed!")
                    await ctx.message.delete()
                    return await msg.delete()
                else:
                    self.logger.debug(f"{kode_nuklir}: going back to info.")
                    embed = await self.format_embed_info(data2)
                    await msg.edit(embed=embed)
                    download_text_open = False
            elif "\N{INBOX TRAY}" in str(res2.emoji):  # Download
                self.logger.info(f"{kode_nuklir}: showing download...")
                embed = discord.Embed(
                    title=data2["title"],
                    color=0x1F1F1F,
                    url=data2["url"],
                    timestamp=datetime.fromtimestamp(data2["posted_time"]),
                )
                embed.description = "Klik link dibawah ini untuk mendownload\n<https://api.ihateani.me/nh/unduh?id={}>\n\nJika gambar banyak, akan memakan waktu lebih lama ketika proses sebelum download.".format(  # noqa: E501
                    kode_nuklir
                )
                embed.set_footer(text="Diprakasai oleh api.ihateani.me")
                embed.set_thumbnail(url=data2["cover"])

                download_text_open = True
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "\N{OPEN BOOK}" in str(res2.emoji):  # Read
                self.logger.info(f"{kode_nuklir}: showing reader...")
                await msg.clear_reactions()

                dataset_img = data2["images"]
                dataset_total = len(dataset_img)
                first_run_3 = True
                pospos = 1
                while True:
                    if first_run_3:
                        img_link = dataset_img[pospos - 1]

                        embed = await self.format_embed_image(data2, pospos, dataset_total, img_link)
                        first_run_3 = False
                        await msg.edit(embed=embed)

                    reactmoji3 = []
                    if dataset_total < 2:
                        break
                    if pospos == 1:
                        reactmoji3 = ["⏩"]
                    elif dataset_total == pospos:
                        reactmoji3 = ["⏪"]
                    elif pospos > 1 and pospos < dataset_total:
                        reactmoji3 = ["⏪", "⏩"]
                    reactmoji3.append("✅")
                    for reaction in reactmoji3:
                        await msg.add_reaction(reaction)

                    def check_react3(reaction, user):
                        if reaction.message.id != msg.id:
                            return False
                        if user != ctx.message.author:
                            return False
                        if str(reaction.emoji) not in reactmoji3:
                            return False
                        return True

                    res3, user3 = await self.bot.wait_for("reaction_add", check=check_react3)
                    if user3 != ctx.message.author:
                        pass
                    elif "✅" in str(res3.emoji):
                        self.logger.warn(f"{kode_nuklir}: going back to info")
                        embed = await self.format_embed_info(data2)
                        await msg.clear_reactions()
                        await msg.edit(embed=embed)
                        break
                    elif "⏪" in str(res3.emoji):
                        self.logger.debug(f"{kode_nuklir}: reader: previous image...")
                        pospos = pospos - 1
                        img_link = dataset_img[pospos - 1]

                        embed = await self.format_embed_image(data2, pospos, dataset_total, img_link)
                        await msg.clear_reactions()
                        await msg.edit(embed=embed)
                    elif "⏩" in str(res3.emoji):
                        self.logger.debug(f"{kode_nuklir}: reader: next image...")
                        pospos = pospos + 1
                        img_link = dataset_img[pospos - 1]

                        embed = await self.format_embed_image(data2, pospos, dataset_total, img_link)
                        await msg.clear_reactions()
                        await msg.edit(embed=embed)

    @nhi.command(aliases=["down", "dl", "download"])
    async def unduh(self, ctx, kode_nuklir):
        kode_nuklir = kode_nuklir.strip()
        if not kode_nuklir.isdigit():
            return await ctx.send("Masukan kode nuklir yang benar.")

        message = await ctx.send("Memulai proses pengumpulan informasi, mohon tunggu.")
        self.logger.info(f"querying {kode_nuklir}")
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get("https://api.ihateani.me/nh/info/{}".format(kode_nuklir)) as resp:
                try:
                    data2 = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        await message.delete()
        data2["url"] = "https://nhentai.net/g/" + kode_nuklir

        embed = discord.Embed(
            title=data2["title"],
            color=0x1F1F1F,
            url=data2["url"],
            timestamp=datetime.fromtimestamp(data2["posted_time"]),
        )
        embed.description = "Klik link dibawah ini untuk mendownload\n<https://api.ihateani.me/nh/unduh?id={}>\n\nJika gambar banyak, akan memakan waktu lebih lama ketika proses sebelum download.".format(  # noqa: E501
            kode_nuklir
        )
        embed.set_footer(text="Diprakasai oleh api.ihateani.me")
        embed.set_thumbnail(url=data2["cover"])

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
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get("https://api.ihateani.me/nh/info/{}".format(kode_nuklir)) as resp:
                try:
                    data2 = await resp.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    return await ctx.send("Terjadi kesalahan ketika menghubungi server.")
                if resp.status != 200:
                    return await ctx.send("Tidak dapat menemukan apa-apa dengan kata tersebut.")

        await message.delete()
        data2["url"] = "https://nhentai.net/g/" + kode_nuklir

        dataset_img = data2["images"]
        dataset_total = len(dataset_img)
        first_run_3 = True
        pospos = 1
        while True:
            if first_run_3:
                img_link = dataset_img[pospos - 1]

                self.logger.info(f"{kode_nuklir}: start reading...")
                embed = await self.format_embed_image(data2, pospos, dataset_total, img_link)
                first_run_3 = False
                msg = await ctx.send(embed=embed)

            reactmoji3 = []
            if dataset_total < 2:
                break
            if pospos == 1:
                reactmoji3 = ["⏩"]
            elif dataset_total == pospos:
                reactmoji3 = ["⏪"]
            elif pospos > 1 and pospos < dataset_total:
                reactmoji3 = ["⏪", "⏩"]
            reactmoji3.append("✅")
            for reaction in reactmoji3:
                await msg.add_reaction(reaction)

            def check_react3(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji3:
                    return False
                return True

            res3, user3 = await self.bot.wait_for("reaction_add", check=check_react3)
            if user3 != ctx.message.author:
                pass
            elif "✅" in str(res3.emoji):
                self.logger.info(f"{kode_nuklir}: done, nuking embed!")
                await msg.clear_reactions()
                await ctx.message.delete()
                return await msg.delete()
            elif "⏪" in str(res3.emoji):
                self.logger.debug(f"{kode_nuklir}: previous image...")
                pospos = pospos - 1
                img_link = dataset_img[pospos - 1]

                embed = await self.format_embed_image(data2, pospos, dataset_total, img_link)
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res3.emoji):
                self.logger.debug(f"{kode_nuklir}: next image...")
                pospos = pospos + 1
                img_link = dataset_img[pospos - 1]

                embed = await self.format_embed_image(data2, pospos, dataset_total, img_link)
                await msg.clear_reactions()
                await msg.edit(embed=embed)

    @nhi.error
    async def nhi_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            self.logger.error("need NSFW channel.")
            await ctx.send(
                "Untuk menggunakan perintah ini, dibutuhkan channel" " yang sudah diaktifkan mode NSFW-nya."
            )

