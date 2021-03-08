import asyncio
import logging

import aiohttp
import discord
import magic
from discord.ext import commands

from nthelper.bot import naoTimesBot

SAUCE_QUERY_PARAMS = r"""query ($url:String!) {
    sauce {
        saucenao(url:$url,minsim:57.5) {
            _total
            items {
                title
                source
                thumbnail
                indexer
                confidence
                extra_info
            }
        }
        iqdb(url:$url,minsim:52.5) {
            _total
            items {
                title
                source
                thumbnail
                indexer
                confidence
                extra_info
            }
        }
    }
}
"""


def truncate(x: str, n: int):
    if len(x) < n:
        return x
    return x[0 : n - 4] + "..."


def setup(bot: naoTimesBot):
    bot.add_cog(SausTomat(bot))


class SausTomat(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.saus.SausTomat")

    async def request_gql(self, url_target):
        query_param = {"query": SAUCE_QUERY_PARAMS, "variables": {"url": url_target}}
        self.logger.info(f"invoking request to API for image: {url_target}")
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{self.bot.semver} (https://github.com/noaione/naoTimes)"}
        ) as sesi:
            async with sesi.post("https://api.ihateani.me/v2/graphql", json=query_param) as resp:
                try:
                    if "application/json" not in resp.headers["content-type"]:
                        return [], "Menerima respon yang tidak diinginkan dari API, mohon coba lagi."
                    res = await resp.json()
                    if "error" in res or "errors" in res:
                        return [], "Menerima error dari API, mohon coba lagi."
                except aiohttp.ClientError:
                    return [], "Tidak dapat mengontak API (kemungkinan down)."
        sauce_results = res["data"]["sauce"]
        merged_results = []
        merged_results.extend(sauce_results["saucenao"]["items"])
        merged_results.extend(sauce_results["iqdb"]["items"])
        if len(merged_results) < 1:
            return [], "Tidak dapat menemukan hasil yang yakin untuk gambar tersebut."
        return merged_results, "Sukses"

    async def generate_embed(self, data: dict) -> discord.Embed:
        embed = discord.Embed(title=truncate(data["title"], 256), color=0x19212D)
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
        embed.set_footer(text="Confidence: {}% | {}".format(data["confidence"], data["indexer"]))
        return embed

    @commands.command(aliases=["sauce", "sausnao", "saucenao"])
    async def saus(self, ctx, *, url=""):
        self.logger.info("Invoking saus command, checking attachments...")
        attachments = ctx.message.attachments
        if not attachments:
            self.logger.info("No attachments found, checking message")
            if not url:
                self.logger.info("No URL found in message too, returning")
                return await ctx.send("Mohon cantumkan attachment gambar atau ketik urlnya")
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

        temp_msg = await ctx.send("Memproses, mohon tunggu...")
        resdata, msg = await self.request_gql(url)
        if not resdata:
            self.logger.info(f"Received error when contacting API, message: {msg}")
            await temp_msg.delete()
            return await ctx.send(f"Tidak dapat mencari saus untuk gambar tersebut\n`{msg}`")

        if resdata:
            resdata.sort(key=lambda x: x["confidence"], reverse=True)
        max_page = len(resdata)
        self.logger.info(f"Total results: {max_page}")

        first_run = True
        num = 1
        while True:
            if first_run:
                self.logger.info(">> Showing results...")
                data = resdata[num - 1]
                embed = await self.generate_embed(data)

                first_run = False
                await temp_msg.delete()
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                return
            if num == 1:
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
                res, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                self.logger.info("<< Going backward...")
                num = num - 1
                data = resdata[num - 1]
                embed = await self.generate_embed(data)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                self.logger.info(">> Going forward...")
                num = num + 1
                data = resdata[num - 1]
                embed = await self.generate_embed(data)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
                self.logger.info("Exiting...")
                await ctx.message.delete()
                return await msg.delete()

    @commands.command(aliases=["saucel", "saucenaol", "sausnaol"])
    async def sausl(self, ctx, use_img_num="1"):
        self.logger.info("Initiated saucenao last 50 message mechanism")
        if isinstance(use_img_num, str):
            if not use_img_num.isdigit():
                use_img_num = 1
            else:
                use_img_num = int(use_img_num)
        if use_img_num > 50:
            use_img_num = 1
        channel = ctx.channel
        self.logger.info("Searching the last 50 messages for image")
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
            return await ctx.send("Tidak dapat menemukan gambar di 50 pesan terakhir.")

        temp_msg = await ctx.send(f"Memproses gambar dari pesan: <{message_url}>\nMohon tunggu...")
        resdata, msg = await self.request_gql(final_img_url)
        if not resdata:
            self.logger.info(f"Received error when contacting API, message: {msg}")
            await temp_msg.delete()
            return await ctx.send(f"Tidak dapat mencari saus untuk gambar tersebut\n`{msg}`")

        if resdata:
            resdata.sort(key=lambda x: x["confidence"], reverse=True)
        max_page = len(resdata)
        self.logger.info(f"Total results: {max_page}")

        first_run = True
        num = 1
        while True:
            if first_run:
                self.logger.info(">> Showing results...")
                data = resdata[num - 1]
                embed = discord.Embed(title=truncate(data["title"], 256), color=0x19212D)
                embed = await self.generate_embed(data)

                first_run = False
                await temp_msg.delete()
                msg = await ctx.send(embed=embed)

            reactmoji = []
            if max_page == 1 and num == 1:
                return
            if num == 1:
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
                res, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                self.logger.info("<< Going backward...")
                num = num - 1
                data = resdata[num - 1]
                embed = await self.generate_embed(data)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                self.logger.info(">> Going forward...")
                num = num + 1
                data = resdata[num - 1]
                embed = await self.generate_embed(data)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
                await ctx.message.delete()
                return await msg.delete()
