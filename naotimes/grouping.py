"""
naotimes.grouping
~~~~~~~~~~~~~~~~~
Moves standalone slash commands into shared command groups (``/kamus kbbi`` instead of ``/kbbi``).

Cogs keep declaring plain top-level ``@app_commands.command`` functions. When a cog is added to the bot,
:meth:`CommandGrouper.apply` moves the listed commands into their group, and :meth:`CommandGrouper.release`
puts everything back when the cog is removed, so loading, unloading and hot-reloading all keep working.

:copyright: (c) 2019-2022 naoTimesdev
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from discord import app_commands
from discord.ext import commands

from .i18n import MissingModule, MissingTranslation

if TYPE_CHECKING:
    from .bot import naoTimesBot

__all__ = ("GROUPS", "CommandGrouper")

# group name -> (description, {current command name: name inside the group})
GROUPS: dict[str, tuple[app_commands.locale_str, dict[str, str]]] = {
    "anime": (
        app_commands.locale_str(
            "Cari anime, manga, novel, visual novel, dan alat bantu fansub",
            key="common.groups.anime",
        ),
        {
            "anime": "anime",
            "manga": "manga",
            "novel": "novel",
            "tayang": "tayang",
            "vn": "vn",
            "randomvn": "randomvn",
            "saus": "saus",
        },
    ),
    "kamus": (
        app_commands.locale_str(
            "Kamus, tesaurus, dan penerjemah",
            key="common.groups.kamus",
        ),
        {
            "kbbi": "kbbi",
            "padanan": "padanan",
            "sinonim": "sinonim",
            "antonim": "antonim",
            "tesaurus": "tesaurus",
            "thesaurus": "thesaurus",
            "define": "define",
            "jisho": "jisho",
            "kanji": "kanji",
            "translasi": "translasi",
        },
    ),
    "game": (
        app_commands.locale_str("Informasi game", key="common.groups.game"),
        {"steam": "steam", "steamdb": "steamdb", "hltb": "hltb"},
    ),
    "vote": (
        app_commands.locale_str("Voting dan giveaway", key="common.groups.vote"),
        {"vote": "buat", "votekick": "kick", "voteban": "ban", "giveaway": "giveaway"},
    ),
    "hiburan": (
        app_commands.locale_str("Perintah hiburan dan iseng", key="common.groups.hiburan"),
        {
            "8ball": "8ball",
            "kerang": "kerang",
            "dadu": "dadu",
            "kocok": "kocok",
            "pilih": "pilih",
            "f": "f",
            "santet": "santet",
            "agama": "agama",
            "ras": "ras",
            "crot": "crot",
            "kontol": "kontol",
            "booru": "booru",
        },
    ),
    "bot": (
        app_commands.locale_str(
            "Informasi bot, peladen, dan pengguna",
            key="common.groups.bot",
        ),
        {
            "status": "status",
            "uptime": "uptime",
            "serverinfo": "serverinfo",
            "userinfo": "userinfo",
            "avatar": "avatar",
            "support": "support",
            "donasi": "donasi",
            "undang": "undang",
        },
    ),
    "alat": (
        app_commands.locale_str(
            "Alat bantu: kalkulator, cuaca, kurs, pengingat, dan emote",
            key="common.groups.alat",
        ),
        {
            "kalkulator": "kalkulator",
            "wolfram": "wolfram",
            "cuaca": "cuaca",
            "kurs": "kurs",
            "ingatkan": "ingatkan",
            "bigemote": "bigemote",
            "emotesteal": "emotesteal",
            "nemote": "nemote",
        },
    ),
}

_LOOKUP: dict[str, tuple[str, str]] = {
    old: (group, new) for group, (_, members) in GROUPS.items() for old, new in members.items()
}


def _guild_only_message(interaction) -> str:
    """Resolve the guild-only notice in the interaction's guild language."""
    fallback = "Perintah ini hanya bisa dipakai di dalam server."
    i18n_for = getattr(interaction.client, "i18n_for", None)
    if i18n_for is None:
        return fallback
    try:
        return i18n_for(interaction.guild).resolve_key("common.errors.guild_only")
    except (MissingModule, MissingTranslation):
        return fallback


async def _guild_only_check(interaction) -> bool:
    # Discord only reads ``guild_only`` from the top-level command, so enforce it per sub-command ourselves.
    if interaction.guild is None:
        await interaction.response.send_message(_guild_only_message(interaction), ephemeral=True)
        return False
    return True


@dataclass
class _Moved:
    group: str
    command: app_commands.Command | app_commands.Group
    original_name: str


class CommandGrouper:
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("naoTimes.Grouping")
        self._moved: dict[str, list[_Moved]] = {}
        self._managed: set[str] = set()

    @property
    def tree(self):
        return self.bot.tree

    @classmethod
    def _set_guild_check(cls, command, enable: bool) -> None:
        """Enforce (or stop enforcing) ``guild_only`` on a command that was moved under another group."""
        if isinstance(command, app_commands.Group):
            if getattr(command, "guild_only", False):
                for child in command.walk_commands():
                    if not isinstance(child, app_commands.Group):
                        cls._toggle_check(child, enable)
            return
        if enable and not getattr(command, "guild_only", False):
            return
        cls._toggle_check(command, enable)

    @staticmethod
    def _toggle_check(command, enable: bool) -> None:
        if enable and _guild_only_check not in command.checks:
            command.checks.append(_guild_only_check)
        elif not enable and _guild_only_check in command.checks:
            command.checks.remove(_guild_only_check)

    def apply(self, cog: commands.Cog) -> None:
        """Move the cog's top-level slash commands into their groups."""
        for command in cog.get_app_commands():
            target = _LOOKUP.get(command.name)
            if target is None:
                continue
            group_name, new_name = target
            original_name = command.name

            self.tree.remove_command(original_name)
            group = self.tree.get_command(group_name)
            if group is None:
                description = GROUPS[group_name][0]
                group = app_commands.Group(name=group_name, description=description)
                self.tree.add_command(group)
                self._managed.add(group_name)
            elif not isinstance(group, app_commands.Group) or group_name not in self._managed:
                self.logger.warning(f"Cannot group /{original_name}: /{group_name} is already used elsewhere")
                self.tree.add_command(command)
                continue

            command.name = new_name
            self._set_guild_check(command, True)
            group.add_command(command, override=True)
            self._moved.setdefault(cog.qualified_name, []).append(_Moved(group_name, command, original_name))
            self.logger.info(f"Grouped /{original_name} -> /{group_name} {new_name}")

    def release(self, cog: commands.Cog) -> None:
        """Undo :meth:`apply` for a cog that is being removed."""
        for moved in self._moved.pop(cog.qualified_name, []):
            group = self.tree.get_command(moved.group)
            if isinstance(group, app_commands.Group):
                group.remove_command(moved.command.name)
                if moved.group in self._managed and not group.commands:
                    self.tree.remove_command(moved.group)
                    self._managed.discard(moved.group)
            moved.command.name = moved.original_name
            self._set_guild_check(moved.command, False)
            moved.command.parent = None
