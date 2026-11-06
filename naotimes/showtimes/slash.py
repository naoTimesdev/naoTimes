"""
naotimes.showtimes.slash
~~~~~~~~~~~~~~~~~~~~~~~~
Shared helpers for the Showtimes slash commands: project autocomplete and lookup,
so commands no longer need to ask "which one did you mean?" with typed prompts.

:copyright: (c) 2019-2022 naoTimesdev
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .models import Showtimes, ShowtimesProject

if TYPE_CHECKING:
    from ..bot import naoTimesBot

__all__ = (
    "NOT_REGISTERED",
    "load_server",
    "project_autocomplete",
    "require_admin",
    "resolve_project",
)

NOT_REGISTERED = "Peladen ini belum terdaftar di Showtimes!"
# Discord limits an autocomplete / choice to 25 entries, names and values to 100 characters.
_MAX_CHOICES = 25
_MAX_LEN = 100


def _choice(project: ShowtimesProject) -> app_commands.Choice[str]:
    title = project.title if len(project.title) <= _MAX_LEN else project.title[: _MAX_LEN - 1] + "…"
    return app_commands.Choice(name=title, value=str(project.id))


async def project_autocomplete(
    bot: naoTimesBot,
    inter: discord.Interaction,
    current: str,
    *,
    only_unfinished: bool = False,
    predicate: Callable[[ShowtimesProject], bool] | None = None,
) -> list[app_commands.Choice[str]]:
    """Autocomplete project titles for the server the command is used in.

    ``value`` is the project ID, so :func:`resolve_project` can look it up exactly.
    """
    if inter.guild is None:
        return []
    if bot.showqueue is None:
        return []
    server = await bot.showqueue.fetch_database(str(inter.guild.id))
    if server is None:
        return []

    if current:
        projects = await bot.loop.run_in_executor(None, server.find_projects, current)
    else:
        projects = list(server.projects)
    if only_unfinished:
        projects = [p for p in projects if p.get_current() is not None]
    if predicate is not None:
        projects = [p for p in projects if predicate(p)]
    projects.sort(key=lambda p: p.title.lower())
    return [_choice(p) for p in projects[:_MAX_CHOICES]]


async def load_server(bot: naoTimesBot, inter: discord.Interaction) -> Showtimes | None:
    """Fetch the Showtimes data for the current guild, or reply that it isn't registered."""
    if inter.guild is None:
        return None
    if bot.showqueue is None:
        return None
    server = await bot.showqueue.fetch_database(str(inter.guild.id))
    if server is None:
        message = NOT_REGISTERED
        if inter.response.is_done():
            await inter.followup.send(message, ephemeral=True)
        else:
            await inter.response.send_message(message, ephemeral=True)
    return server


async def resolve_project(
    bot: naoTimesBot, server: Showtimes, query: str
) -> tuple[ShowtimesProject | None, str | None]:
    """Find a project from an autocomplete value (an ID) or free-typed text.

    Returns ``(project, None)`` on success, ``(None, error_message)`` otherwise.
    Free text that matches several projects is rejected with the candidates listed,
    the user then picks one from the autocomplete list.
    """
    project = server.get_project(query)
    if project is not None:
        return project, None
    exact = server.exact_match(query)
    if exact is not None:
        return exact, None

    matches = await bot.loop.run_in_executor(None, server.find_projects, query)
    if not matches:
        return None, "Tidak dapat menemukan judul tersebut di database."
    if len(matches) == 1:
        return matches[0], None
    names = ", ".join(f"`{m.title}`" for m in matches[:8])
    more = f" dan {len(matches) - 8} lainnya" if len(matches) > 8 else ""
    return None, f"Ada beberapa judul yang cocok: {names}{more}.\nPilih salah satu dari daftar autocomplete."


def require_admin(server: Showtimes, user: discord.abc.User) -> bool:
    """Whether the user is an administrator of this Showtimes server."""
    return server.is_admin(user.id)
