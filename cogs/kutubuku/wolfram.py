import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.http import WolframPod
from naotimes.paginator import DiscordPaginatorUI
from naotimes.utils import quote, rgb_to_color


class KutubukuWolfram(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("Kutubuku.WolframAlpha")
        self.wolfram = self.bot.wolfram

    @app_commands.command(
        name="wolfram",
        description=app_commands.locale_str("Tanya WolframAlpha", key="kutubuku.wolfram.description"),
    )
    @app_commands.describe(
        query=app_commands.locale_str(
            "Pertanyaan atau ekspresi untuk WolframAlpha",
            key="kutubuku.wolfram.option_query",
        ),
    )
    async def wolfram_cmd(self, inter: discord.Interaction, query: str):
        """Tanya WolframAlpha"""
        ctx = await self.bot.get_context(inter)
        if self.wolfram is None:
            return await inter.response.send_message(ctx.t("wolfram.disabled"), ephemeral=True)
        await ctx.defer()
        self.logger.info(f"Querying: {query}")
        results = await self.wolfram.query(query)
        if isinstance(results, str):
            self.logger.warning(f"Failed to get results: {results}")
            return await ctx.send(results)
        SEARCH_URL = "https://www.wolframalpha.com/input/?i={}"
        QUERY_STRINGIFY = query.replace(" ", "+")

        def _create_embed(pod: WolframPod):
            embed = discord.Embed(title=pod.title, color=rgb_to_color(202, 103, 89))
            embed.set_author(
                name="WolframAlpha",
                url=SEARCH_URL.format(QUERY_STRINGIFY),
                icon_url="https://p.n4o.xyz/i/wa_icon.png",
            )
            embed.description = ctx.t("wolfram.query", query=query)
            first_image = None
            for n, subpod in enumerate(pod.pods, 1):
                sb_plain = subpod.plaintext.strip()
                if subpod.image and first_image is None:
                    first_image = subpod.image
                if not sb_plain and first_image is not None:
                    sb_plain = ctx.t("wolfram.see_image")
                elif not sb_plain and first_image is None:
                    continue
                embed.add_field(name=(pod.scanner or "WolframAlpha") + f" ({n})", value=quote(subpod.plaintext, True))
            if first_image is not None:
                embed.set_image(url=first_image)
            embed.set_footer(text=ctx.t("wolfram.footer"), icon_url="https://p.n4o.xyz/i/wa_icon.png")
            return embed

        paginator = DiscordPaginatorUI(ctx, results.pods)
        paginator.attach(_create_embed)
        await paginator.interact(30.0)


async def setup(bot: naoTimesBot):
    await bot.add_cog(KutubukuWolfram(bot))
