"""
MIT License

Copyright (c) 2019-2022 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot

__all__ = ("BotBrainLocale",)

LANGUAGE_NAMES = {
    "id": "Bahasa Indonesia",
    "en": "English",
}


def _display_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


class BotBrainLocale(commands.Cog):
    """Per-guild language settings (``/bahasa``)."""

    bahasa = app_commands.Group(
        name="bahasa",
        description=app_commands.locale_str(
            "Atur bahasa yang dipakai naoTimes di peladen ini",
            key="common.language.command_description",
        ),
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Locale")

    def _available(self) -> list[str]:
        return list(self.bot.i18n_bot.languages)

    def _choices(self, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        choices: list[app_commands.Choice[str]] = []
        for code in self._available():
            name = _display_name(code)
            if current and current not in code and current not in name.lower():
                continue
            choices.append(app_commands.Choice(name=f"{name} ({code})", value=code))
        return choices[:25]

    @bahasa.command(
        name="lihat",
        description=app_commands.locale_str("Lihat bahasa yang sedang dipakai", key="common.language.sub_lihat"),
    )
    async def _bahasa_lihat(self, inter: discord.Interaction):
        mod = self.bot.i18n_for(inter.guild)
        await inter.response.send_message(
            mod.resolve_key("common.language.current", language=_display_name(mod.language)), ephemeral=True
        )

    @bahasa.command(
        name="atur",
        description=app_commands.locale_str("Ubah bahasa peladen", key="common.language.sub_atur"),
    )
    @app_commands.describe(
        bahasa=app_commands.locale_str("Kode bahasa yang ingin dipakai", key="common.language.option")
    )
    async def _bahasa_atur(self, inter: discord.Interaction, bahasa: str):
        code = bahasa.strip().lower()
        if code not in self.bot.i18n_bot:
            mod = self.bot.i18n_for(inter.guild)
            available = ", ".join(f"`{item}`" for item in self._available())
            await inter.response.send_message(
                mod.resolve_key("common.language.unsupported", language=code, available=available), ephemeral=True
            )
            return
        await self.bot.set_i18n(str(inter.guild_id), code)
        mod = self.bot.i18n_bot.get(code)
        await inter.response.send_message(
            mod.resolve_key("common.language.set", language=_display_name(code)), ephemeral=True
        )

    @bahasa.command(
        name="reset",
        description=app_commands.locale_str("Kembalikan ke bahasa bawaan", key="common.language.sub_reset"),
    )
    async def _bahasa_reset(self, inter: discord.Interaction):
        await self.bot.set_i18n(str(inter.guild_id), None)
        default = self.bot.i18n_bot.getdefault()
        await inter.response.send_message(
            default.resolve_key("common.language.reset", language=_display_name(default.language)), ephemeral=True
        )

    @_bahasa_atur.autocomplete("bahasa")
    async def _bahasa_atur_auto(self, inter: discord.Interaction, current: str):
        return self._choices(current)


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainLocale(bot))
