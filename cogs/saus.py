import asyncio

import aiohttp
import discord
from discord.ext import commands

import magic


def truncate(x: str, n: int):
    if len(x) < n:
        return x
    return x[0:n - 4] + "..."


def setup(bot):
    bot.add_cog(SausTomat(bot))


class SausTomat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def request_api(self, ctx):
        pass

    @commands.command(aliases=["sauce", "sausnao", "saucenao"])
    async def saus(self, ctx, *, url=""):
        print("[#] Invoked saus command\n[#] Checking attachments")

        attachments = ctx.message.attachments
        if not attachments:
            print("[!] No attachment found, checking url")
            if not url:
                print("[!] No url, found returning message")
                return await ctx.send(
                    "Mohon cantumkan attachment gambar atau ketik urlnya"
                )
            # Remove Discord URL Escape if exists
            if url.startswith("<"):
                if url.endswith(">"):
                    url = url[1:-1]
                else:
                    url = url[1:]
            if url.endswith(">"):
                url = url[:-1]
        else:
            url = attachments[0].url

        print("[$] Sending POST request to N4O SauceNAO API")
        temp_msg = await ctx.send("Memproses, mohon tunggu...")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.ihateani.me/sauce/saucenao", data={"url": url}
            ) as r:
                try:
                    r_data = await r.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    await temp_msg.edit(content="Gagal memproses gambar...")
                    return await ctx.send(
                        "Tidak dapat menghubungi endpoint API naoTimes."
                    )
                if r.status != 200:
                    await temp_msg.edit(content="Gagal memproses gambar...")
                    msggg = "Terjadi kesalahan dengan request ke API."
                    if "message" in r_data:
                        msggg += "\nResponse API: `{}`".format(
                            r_data["message"]
                        )
                    return await ctx.send(content=msggg)
                if "results" not in r_data:
                    await temp_msg.edit(content="Gagal memproses gambar...")
                    msggg = "Terjadi kesalahan dengan request ke API."
                    if "message" in r_data:
                        msggg += "\nResponse API: `{}`".format(
                            r_data["message"]
                        )
                    return await ctx.send(content=msggg)
                if not r_data["results"]:
                    await temp_msg.edit(
                        content="Gagal memproses gambar (1/2)..."
                        "\nMengontak API IQDB."
                    )
                    async with session.post(
                        "https://api.ihateani.me/sauce/iqdb",
                        data={"url": url},
                    ) as r2:
                        try:
                            r_data = await r2.json()
                        except aiohttp.client_exceptions.ContentTypeError:
                            await temp_msg.edit(
                                content="Gagal memproses gambar..."
                            )
                            return await ctx.send(
                                "Tidak dapat menghubungi "
                                "endpoint API naoTimes."
                            )
                        if r2.status != 200:
                            await temp_msg.edit(
                                content="Gagal memproses gambar..."
                            )
                            msggg = "Terjadi kesalahan dengan request ke API."
                            if "message" in r_data:
                                msggg += "\nResponse API: `{}`".format(
                                    r_data["message"]
                                )
                            return await ctx.send(content=msggg)
                        if "results" not in r_data:
                            await temp_msg.edit(
                                content="Gagal memproses gambar..."
                            )
                            msggg = "Terjadi kesalahan dengan request ke API."
                            if "message" in r_data:
                                msggg += "\nResponse API: `{}`".format(
                                    r_data["message"]
                                )
                            return await ctx.send(content=msggg)
                        if not r_data["results"]:
                            await temp_msg.edit(
                                content="Gagal memproses gambar (2/2)..."
                            )
                            return await ctx.send(
                                "Tidak dapat menemukan hasil yang "
                                "cukup yakin untuk gambar anda."
                            )

        resdata = r_data["results"]
        max_page = len(resdata)
        print("\t>> Total result: {}".format(max_page))

        first_run = True
        num = 1
        while True:
            if first_run:
                print("\t>> Showing result")
                data = resdata[num - 1]
                embed = discord.Embed(
                    title=truncate(data["title"], 256), color=0x19212D
                )
                desc = ""
                if data["extra_info"]:
                    for k, v in data["extra_info"].items():
                        desc += "**{0}**: {1}\n".format(k.capitalize(), v)
                if data["source"]:
                    desc += "[Source]({})".format(data["source"])
                else:
                    desc += "Unknown Source"
                embed.description = desc

                embed.set_image(url=data["thumbnail"])
                embed.set_footer(
                    text="Confidence: {}% | {}".format(
                        data["confidence"], data["indexer"]
                    )
                )

                first_run = False
                await temp_msg.delete()
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                return
            elif num == 1:
                reactmoji.append("⏩")
            elif num == max_page:
                reactmoji.append("⏪")
            elif num > 1 and num < max_page:
                reactmoji.extend(["⏪", "⏩"])
            reactmoji.append("✅")

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
                res, user = await self.bot.wait_for(
                    "reaction_add", timeout=30.0, check=check_react
                )
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                print("<< Going backward")
                num = num - 1
                data = resdata[num - 1]
                embed = discord.Embed(
                    title=truncate(data["title"], 256), color=0x19212D
                )
                desc = ""
                if data["extra_info"]:
                    for k, v in data["extra_info"].items():
                        desc += "**{0}**: {1}\n".format(k.capitalize(), v)
                if data["source"]:
                    desc += "[Source]({})".format(data["source"])
                else:
                    desc += "Unknown Source"
                embed.description = desc

                embed.set_image(url=data["thumbnail"])
                embed.set_footer(
                    text="Confidence: {}% | {}".format(
                        data["confidence"], data["indexer"]
                    )
                )

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                print("\t>> Going forward")
                num = num + 1
                data = resdata[num - 1]
                embed = discord.Embed(
                    title=truncate(data["title"], 256), color=0x19212D
                )
                desc = ""
                if data["extra_info"]:
                    for k, v in data["extra_info"].items():
                        desc += "**{0}**: {1}\n".format(k.capitalize(), v)
                if data["source"]:
                    desc += "[Source]({})".format(data["source"])
                else:
                    desc += "Unknown Source"
                embed.description = desc

                embed.set_image(url=data["thumbnail"])
                embed.set_footer(
                    text="Confidence: {}% | {}".format(
                        data["confidence"], data["indexer"]
                    )
                )

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
                await ctx.message.delete()
                return await msg.delete()

    @commands.command(aliases=["saucel", "saucenaol", "sausnaol"])
    async def sausl(self, ctx, use_img_num="1"):
        print("Initiated saucenao last 20 message mechanism")
        if isinstance(use_img_num, str):
            if not use_img_num.isdigit():
                use_img_num = 1
            else:
                use_img_num = int(use_img_num)
        if use_img_num > 50:
            use_img_num = 1
        channel = ctx.channel
        print("[@] Searching the last 50 messages for image")
        final_img_url = None
        message_url = None
        magic_mime = magic.Magic(mime=True)
        found_count = 0
        async for msg in channel.history(limit=50, oldest_first=False):
            if msg.attachments:
                use_first_one = msg.attachments[0]
                mime_res = magic_mime.from_buffer(await use_first_one.read())
                if mime_res.startswith("image"):
                    found_count += 1
                    if found_count >= use_img_num:
                        final_img_url = use_first_one.url
                        message_url = msg.jump_url
                        break

        if not final_img_url:
            return await ctx.send(
                "Tidak dapat menemukan gambar di 50 pesan terakhir."
            )

        print("[$] Sending POST request to N4O SauceNAO API")
        temp_msg = await ctx.send(
            "Memproses gambar dari pesan: <{}>\nMohon tunggu...".format(
                message_url
            )
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.ihateani.me/sauce/saucenao",
                data={"url": final_img_url},
            ) as r:
                try:
                    r_data = await r.json()
                except aiohttp.client_exceptions.ContentTypeError:
                    await temp_msg.edit(content="Gagal memproses gambar...")
                    return await ctx.send(
                        "Tidak dapat menghubungi endpoint API naoTimes."
                    )
                if r.status != 200:
                    await temp_msg.edit(content="Gagal memproses gambar...")
                    msggg = "Terjadi kesalahan dengan request ke API."
                    if "message" in r_data:
                        msggg += "\nResponse API: `{}`".format(
                            r_data["message"]
                        )
                    return await ctx.send(content=msggg)
                if "results" not in r_data:
                    await temp_msg.edit(content="Gagal memproses gambar...")
                    msggg = "Terjadi kesalahan dengan request ke API."
                    if "message" in r_data:
                        msggg += "\nResponse API: `{}`".format(
                            r_data["message"]
                        )
                    return await ctx.send(content=msggg)
                if not r_data["results"]:
                    await temp_msg.edit(
                        content="Gagal memproses gambar (1/2)..."
                        "\nMengontak API IQDB."
                    )
                    async with session.post(
                        "https://api.ihateani.me/sauce/iqdb",
                        data={"url": final_img_url},
                    ) as r2:
                        try:
                            r_data = await r2.json()
                        except aiohttp.client_exceptions.ContentTypeError:
                            await temp_msg.edit(
                                content="Gagal memproses gambar..."
                            )
                            return await ctx.send(
                                "Tidak dapat menghubungi "
                                "endpoint API naoTimes."
                            )
                        if r2.status != 200:
                            await temp_msg.edit(
                                content="Gagal memproses gambar..."
                            )
                            msggg = "Terjadi kesalahan dengan request ke API."
                            if "message" in r_data:
                                msggg += "\nResponse API: `{}`".format(
                                    r_data["message"]
                                )
                            return await ctx.send(content=msggg)
                        if "results" not in r_data:
                            await temp_msg.edit(
                                content="Gagal memproses gambar..."
                            )
                            msggg = "Terjadi kesalahan dengan request ke API."
                            if "message" in r_data:
                                msggg += "\nResponse API: `{}`".format(
                                    r_data["message"]
                                )
                            return await ctx.send(content=msggg)
                        if not r_data["results"]:
                            await temp_msg.edit(
                                content="Gagal memproses gambar (2/2)..."
                            )
                            return await ctx.send(
                                "Tidak dapat menemukan hasil yang "
                                "cukup yakin untuk gambar anda."
                            )

        resdata = r_data["results"]
        max_page = len(resdata)
        print("\t>> Total result: {}".format(max_page))

        first_run = True
        num = 1
        while True:
            if first_run:
                print("\t>> Showing result")
                data = resdata[num - 1]
                embed = discord.Embed(
                    title=truncate(data["title"], 256), color=0x19212D
                )
                desc = ""
                if data["extra_info"]:
                    for k, v in data["extra_info"].items():
                        desc += "**{0}**: {1}\n".format(k.capitalize(), v)
                if data["source"]:
                    desc += "[Source]({})".format(data["source"])
                else:
                    desc += "Unknown Source"
                embed.description = desc

                embed.set_image(url=data["thumbnail"])
                embed.set_footer(
                    text="Confidence: {}% | {}".format(
                        data["confidence"], data["indexer"]
                    )
                )

                first_run = False
                await temp_msg.delete()
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                return
            elif num == 1:
                reactmoji.append("⏩")
            elif num == max_page:
                reactmoji.append("⏪")
            elif num > 1 and num < max_page:
                reactmoji.extend(["⏪", "⏩"])
            reactmoji.append("✅")

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
                res, user = await self.bot.wait_for(
                    "reaction_add", timeout=30.0, check=check_react
                )
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                print("<< Going backward")
                num = num - 1
                data = resdata[num - 1]
                embed = discord.Embed(
                    title=truncate(data["title"], 256), color=0x19212D
                )
                desc = ""
                if data["extra_info"]:
                    for k, v in data["extra_info"].items():
                        desc += "**{0}**: {1}\n".format(k.capitalize(), v)
                if data["source"]:
                    desc += "[Source]({})".format(data["source"])
                else:
                    desc += "Unknown Source"
                embed.description = desc

                embed.set_image(url=data["thumbnail"])
                embed.set_footer(
                    text="Confidence: {}% | {}".format(
                        data["confidence"], data["indexer"]
                    )
                )

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                print("\t>> Going forward")
                num = num + 1
                data = resdata[num - 1]
                embed = discord.Embed(
                    title=truncate(data["title"], 256), color=0x19212D
                )
                desc = ""
                if data["extra_info"]:
                    for k, v in data["extra_info"].items():
                        desc += "**{0}**: {1}\n".format(k.capitalize(), v)
                if data["source"]:
                    desc += "[Source]({})".format(data["source"])
                else:
                    desc += "Unknown Source"
                embed.description = desc

                embed.set_image(url=data["thumbnail"])
                embed.set_footer(
                    text="Confidence: {}% | {}".format(
                        data["confidence"], data["indexer"]
                    )
                )

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
                await ctx.message.delete()
                return await msg.delete()
