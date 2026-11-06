import logging
from collections.abc import Callable
from typing import cast

import discord
import magic
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.models import saus as sausmodel
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import complex_walk, cutoff_text, quote
from naotimes.views import ConfirmView

SAUS_QUERY = """
query ($url:String!,$snsim:Float=57.5,$iqsim:Float=52.5) {
    sauce {
        saucenao(url:$url,minsim:$snsim) {
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
        iqdb(url:$url,minsim:$iqsim) {
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

    async def _request_sauce(
        self, t: Callable[..., str], image_url: str, sim_saucenao: float = 57.5, sim_iqdb: float = 52.5
    ) -> list[sausmodel.SausResultItem] | str:
        self.logger.info(f"Invoking GQL API for image: {image_url}")
        if self.bot.ihaapi is None:
            return t("saus.graphql_unavailable")
        result = await self.bot.ihaapi.query(SAUS_QUERY, {"url": image_url, "snsim": sim_saucenao, "iqsim": sim_iqdb})
        if result.errors is not None and len(result.errors) > 0:
            self.logger.warning(f"Error invoking GQL API: {result.errors}")
            joined_error = []
            for error in result.errors:
                joined_error.append(error.message)
            return "\n".join(joined_error)

        data = result.data
        if data is None:
            return t("saus.graphql_no_data")
        saucenao_results = complex_walk(data, "sauce.saucenao.items")
        iqdb_results = complex_walk(data, "sauce.iqdb.items")
        merged_results: list[sausmodel.SausResultItem] = []
        for value in (saucenao_results, iqdb_results):
            if isinstance(value, list):
                merged_results.extend(cast(list[sausmodel.SausResultItem], value))
        if len(merged_results) < 1:
            return []
        return merged_results

    def _generate_embed_result(self, data: sausmodel.SausResultItem, t: Callable[..., str]) -> discord.Embed:
        embed = discord.Embed(title=cutoff_text(data["title"], 256), color=0x19212D)
        description = ""
        if data["extra_info"]:
            for key, value in data["extra_info"].items():
                description += f"**{key.capitalize()}**: {value}\n"
        if data["source"]:
            description += t("saus.source_link", url=data["source"])
        else:
            description += t("saus.unknown_source")
        embed.description = description

        embed.set_image(url=data["thumbnail"])
        confidence = data["confidence"]
        indexer = data["indexer"]
        embed.set_footer(text=t("saus.footer", confidence=confidence, indexer=indexer))
        return embed

    @app_commands.command(
        name="saus",
        description=app_commands.locale_str(
            "Cari sumber (saus) sebuah gambar via SauceNAO + IQDB", key="peninjau.saus.description"
        ),
    )
    @app_commands.describe(
        gambar=app_commands.locale_str("Gambar yang ingin dicari sausnya", key="peninjau.saus.option_image"),
        url=app_commands.locale_str("Atau URL gambar", key="peninjau.saus.option_url"),
    )
    async def _peninjau_saus(
        self,
        inter: discord.Interaction,
        gambar: discord.Attachment | None = None,
        url: str | None = None,
    ):
        """Cari sumber (saus) sebuah gambar via SauceNAO + IQDB"""
        self.logger.info("Invoking saus command...")
        ctx = await self.bot.get_context(inter)
        image_url: str
        if gambar is not None:
            if not (gambar.content_type or "").startswith("image"):
                return await ctx.send(ctx.t("saus.not_image"), ephemeral=True)
            image_url = gambar.url
        elif url:
            image_url = url.strip().lstrip("<").rstrip(">")
        else:
            return await ctx.send(ctx.t("saus.no_input"), ephemeral=True)

        await ctx.defer()
        temp_msg = await ctx.send(ctx.t("saus.processing"))
        result = await self._request_sauce(ctx.t, image_url)
        if isinstance(result, str):
            self.logger.info(f"Received error when contacting API, message: {result}")
            await getattr(temp_msg, "delete")(no_log=True)
            view = ConfirmView(ctx, timeout=None)
            base_msg = ctx.t("saus.search_failed", error=quote(result, True))
            base_msg += ctx.t("saus.retry_offer")
            old_nsg = await ctx.send(base_msg, view=view)
            await view.wait()
            if not view.value:
                return await ctx.send(ctx.t("saus.cancelled"))
            else:
                self.logger.info("Retrying with lower threshold (30.0 for SauceNAO, 28.5 for IQDB)")
                await getattr(old_nsg, "delete")(no_log=True)
                temp_msg = await ctx.send(ctx.t("saus.processing_retry"))
                result = await self._request_sauce(ctx.t, image_url, 30.0, 28.5)
                if isinstance(result, str):
                    self.logger.info(f"Received error (again) when contacting API, message: {result}")
                    await getattr(temp_msg, "delete")(no_log=True)
                    return await ctx.send(ctx.t("saus.search_failed", error=quote(result, True)))

        if not result:
            return await ctx.send(ctx.t("saus.no_results"))
        result.sort(key=lambda x: x.get("confidence", -1), reverse=True)

        self.logger.info(f"Total match: {len(result)}")
        paginator = DiscordPaginatorUI(ctx, result, 30.0)
        paginator.attach(lambda data: self._generate_embed_result(data, ctx.t))
        await paginator.interact()


async def setup(bot: naoTimesBot):
    await bot.add_cog(PeninjauSausGambar(bot))
