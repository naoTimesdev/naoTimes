import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import OwnerGroup
from naotimes.i18n.translator import (
    resolve_command_description,
    resolve_parameter_description,
)

MAX_FIELD = 1024


def _flatten(command, i18n, locale):
    """Yield ``(qualified_name, description)`` for every runnable command below ``command``."""
    if isinstance(command, app_commands.Group):
        for child in command.commands:
            yield from _flatten(child, i18n, locale)
    else:
        yield command.qualified_name, resolve_command_description(i18n, command, locale)


class BotBrainHelp(commands.Cog):
    """A /help command generated from the live slash command tree."""

    module = "common"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Help")

    def _t(self, inter: discord.Interaction, key: str, **kwargs: Any) -> str:
        """Resolve a shared ``common`` string for the interaction's guild."""
        return self.bot.i18n_for(inter.guild).resolve_key(f"common.{key}", **kwargs)

    async def _visible(self, inter: discord.Interaction):
        is_owner = await self.bot.is_owner(inter.user)
        commands_list = []
        for cmd in self.bot.tree.get_commands():
            # Context menus live in the same tree but are not slash commands.
            if isinstance(cmd, app_commands.ContextMenu):
                continue
            if isinstance(cmd, OwnerGroup) and not is_owner:
                continue
            if getattr(cmd, "guild_only", False) and inter.guild is None:
                continue
            commands_list.append(cmd)
        return sorted(commands_list, key=lambda c: c.name)

    @app_commands.command(
        name="help",
        description=app_commands.locale_str(
            "Lihat daftar perintah naoTimes",
            key="common.help.command_description",
        ),
    )
    @app_commands.describe(
        perintah=app_commands.locale_str(
            "Nama perintah atau grup (misal: alias, fansubrss)",
            key="common.help.option",
        )
    )
    async def _help(self, inter: discord.Interaction, perintah: str | None = None):
        visible = await self._visible(inter)
        i18n = self.bot.i18n_bot
        if perintah:
            name = perintah.lower().lstrip("/")
            target = next((c for c in visible if c.name == name), None)
            if target is None:
                return await inter.response.send_message(self._t(inter, "help.not_found", name=name), ephemeral=True)
            embed = discord.Embed(
                title=f"/{target.name}",
                description=resolve_command_description(i18n, target, inter.locale),
                color=0x56ACF3,
            )
            if isinstance(target, app_commands.Group):
                lines = [f"`/{n}` — {d}" for n, d in _flatten(target, i18n, inter.locale)]
                embed.add_field(
                    name=self._t(inter, "help.subcommands"),
                    value="\n".join(lines)[:MAX_FIELD] or "-",
                    inline=False,
                )
            else:
                params = [
                    self._t(
                        inter,
                        "help.parameter",
                        name=p.name,
                        optional="" if p.required else self._t(inter, "help.optional_suffix"),
                        description=resolve_parameter_description(i18n, p, inter.locale),
                    )
                    for p in target.parameters
                ]
                if params:
                    embed.add_field(
                        name=self._t(inter, "help.options"),
                        value="\n".join(params)[:MAX_FIELD],
                        inline=False,
                    )
            return await inter.response.send_message(embed=embed, ephemeral=True)

        lines: list[str] = []
        for cmd in visible:
            if isinstance(cmd, app_commands.Group):
                subs = ", ".join(f"`{c.name}`" for c in cmd.commands)
                lines.append(f"`/{cmd.name}` — {resolve_command_description(i18n, cmd, inter.locale)}\n⠀↳ {subs}")
            else:
                lines.append(f"`/{cmd.name}` — {resolve_command_description(i18n, cmd, inter.locale)}")

        embed = discord.Embed(
            title=self._t(inter, "help.title"),
            description=self._t(inter, "help.description"),
            color=0x56ACF3,
        )
        chunk: list[str] = []
        size = 0
        part = 1
        for line in lines:
            if size + len(line) + 1 > MAX_FIELD:
                embed.add_field(
                    name=self._t(inter, "help.commands_page", part=part),
                    value="\n".join(chunk),
                    inline=False,
                )
                part += 1
                chunk, size = [], 0
            chunk.append(line)
            size += len(line) + 1
        if chunk:
            label = self._t(inter, "help.commands")
            if part > 1:
                label = self._t(inter, "help.commands_page", part=part)
            embed.add_field(name=label, value="\n".join(chunk), inline=False)
        embed.set_footer(text=self._t(inter, "help.footer", version=self.bot.semver))
        await inter.response.send_message(embed=embed, ephemeral=True)

    @_help.autocomplete("perintah")
    async def _help_auto(self, inter: discord.Interaction, current: str):
        visible = await self._visible(inter)
        current = current.lower()
        return [app_commands.Choice(name=c.name, value=c.name) for c in visible if current in c.name][:25]


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainHelp(bot))
