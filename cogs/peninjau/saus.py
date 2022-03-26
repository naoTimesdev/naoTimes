import logging
from typing import List

import disnake
import magic
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.models import saus as sausmodel
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import complex_walk, cutoff_text, quote

SAUS_QUERY = """
query ($url:String!) {
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


class PeninjauSausGambar(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.SausGambar")

        self.magic = magic.Magic(mime=True)

    async def _request_sauce(self, image_url: str) -> List[sausmodel.SausResultItem]:
        self.logger.info(f"Invoking GQL API for image: {image_url}")
        result = await self.bot.ihaapi.query(SAUS_QUERY, {"url": image_url})
        if result.errors is not None and len(result.errors) > 0:
            self.logger.warning(f"Error invoking GQL API: {result.errors}")
            joined_error = []
            for error in result.errors:
                joined_error.append(error.message)
            return "\n".join(joined_error)

        data = result.data
        saucenao_results = complex_walk(data, "sauce.saucenao.items")
        iqdb_results = complex_walk(data, "sauce.iqdb.items")
        merged_results = [*saucenao_results, *iqdb_results]
        if len(merged_results) < 1:
            return "Tidak dapat menemukan hasil yang yakin untuk gambar tersebut."
        return merged_results

    def _generate_embed_result(self, data: sausmodel.SausResultItem) -> disnake.Embed:
        embed = disnake.Embed(title=cutoff_text(data["title"], 256), color=0x19212D)
        description = ""
        if data["extra_info"]:
            for key, value in data["extra_info"].items():
                description += f"**{key.capitalize()}**: {value}\n"
        if data["source"]:
            description += f"[Source]({data['source']})"
        else:
            description += "Unknown Source"
        embed.description = description

        embed.set_image(url=data["thumbnail"])
        confidence = data["confidence"]
        indexer = data["indexer"]
        embed.set_footer(text=f"Confidence: {confidence}% | {indexer}")
        return embed

    @commands.command(name="saus", aliases=["sauce", "sausnao", "sauce-nao"])
    async def _peninjau_saus(self, ctx: naoTimesContext, *, image_url: str = ""):
        self.logger.info("Invoking saus command, checking attachments...")
        attachments: List[disnake.Attachment] = ctx.message.attachments
        if len(attachments) > 0:
            first_attach = attachments[0]
            if not first_attach.content_type.startswith("image"):
                return await ctx.send("File yang dicantumkan bukanlah gambar!")
            url = attachments[0].url
        else:
            self.logger.info("No attachment found, checking message")
            if not image_url:
                self.logger.info("No URL found in message too, returning")
                return await ctx.send("Mohon cantumkan attachment gambar atau ketik urlnya")

            if image_url.startswith("<"):
                if image_url.endswith(">"):
                    image_url = image_url[1:-1]
                else:
                    image_url = image_url[1:]
            if image_url.endswith(">"):
                image_url = image_url[:-1]
            url = image_url

        temp_msg = await ctx.send("Memproses, mohon tunggu...")
        result = await self._request_sauce(url)
        if isinstance(result, str):
            self.logger.info(f"Received error when contacting API, message: {result}")
            await temp_msg.delete()
            return await ctx.send(f"Tidak dapat mencari saus untuk gambar tersebut\n{quote(result, True)}")

        if result:
            result.sort(key=lambda x: x.get("confidence", -1), reverse=True)

        self.logger.info(f"Total match: {len(result)}")
        paginator = DiscordPaginatorUI(ctx, result, 30.0)
        paginator.attach(self._generate_embed_result)
        await paginator.interact()

    @commands.command(name="sausl", aliases=["saucel", "saucenaol", "sausnaol"])
    async def _peninjau_saus_last(self, ctx: naoTimesContext, img_pos: int = 1):
        self.logger.info("Initiated saucenao last 75 message mechanism")
        if img_pos > 75:
            img_pos = 1
        channel: disnake.TextChannel = ctx.channel

        match_count = 0
        final_url = None
        reference = None
        async for msg in channel.history(limit=75, oldest_first=False):
            if len(msg.attachments) > 0:
                first_attach = msg.attachments[0]
                if first_attach.content_type.startswith("image/"):
                    match_count += 1
                    if match_count >= img_pos:
                        final_url = first_attach.url
                        reference = msg
                        break

        if not final_url:
            return await ctx.send("Tidak dapat menemukan gambar di 75 pesan terakhir.")

        temp_msg: disnake.Message = await ctx.send("Memproses gambar berikut...", reference=reference)
        result = await self._request_sauce(final_url)
        if isinstance(result, str):
            self.logger.info(f"Received error when contacting API, message: {result}")
            await temp_msg.delete()
            return await ctx.send(
                f"Tidak dapat mencari saus untuk gambar tersebut\n{quote(result, True)}", reference=reference
            )

        if result:
            result.sort(key=lambda x: x.get("confidence", -1), reverse=True)

        self.logger.info(f"Total match: {len(result)}")
        paginator = DiscordPaginatorUI(ctx, result)
        paginator.attach(self._generate_embed_result)
        await paginator.interact(30.0)


def setup(bot: naoTimesBot):
    bot.add_cog(PeninjauSausGambar(bot))
