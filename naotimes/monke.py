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

import asyncio
import datetime
import logging
from collections.abc import Callable, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    cast,
)

import discord.app_commands.commands
import discord.ext.tasks
import discord.message
from arrow.locales import Locale, _locale_map
from discord.enums import AppCommandType, MessageType
from discord.utils import MISSING

if TYPE_CHECKING:
    from discord.app_commands.commands import ContextMenuCallback
    from discord.ext.commands.cog import Cog

__all__ = (
    "monkeypatch_arrow_id_locale",
    "monkeypatch_discord_context_menu",
    "monkeypatch_discord_tasks_loop",
    "monkeypatch_message_delete",
)

_log = logging.getLogger("naoTimes.Monke")
DELETED_MESSAGE_NO_LOG = cast(MessageType, 9999)


def monkeypatch_message_delete():
    ORIGINAL_DELETE = discord.message.PartialMessage.delete

    async def delete_strategy(self: discord.message.Message, *, delay: float | None = None, no_log: bool = False):
        if no_log:
            self.type = DELETED_MESSAGE_NO_LOG

        await ORIGINAL_DELETE(self, delay=delay)

    _log.info("Monkeypatching discord.message.PartialMessage.delete with new function")
    setattr(discord.message.PartialMessage, "delete", delete_strategy)

    # Messages sent as a reply to an interaction (slash commands) are InteractionMessage /
    # WebhookMessage objects, their `delete` has its own signature without `no_log`.
    # Accept (and ignore) it so shared helpers can use `delete(no_log=True)` everywhere.
    def _wrap_webhook_delete(original: Any) -> Any:
        async def delete_webhook(self: Any, *, delay: float | None = None, no_log: bool = False) -> Any:
            return await original(self, delay=delay)

        return delete_webhook

    for cls in (discord.WebhookMessage, discord.InteractionMessage):
        if "no_log" not in cls.delete.__code__.co_varnames:
            _log.info(f"Monkeypatching discord.{cls.__name__}.delete to accept no_log")
            setattr(cls, "delete", _wrap_webhook_delete(cls.delete))


def monkeypatch_arrow_id_locale():
    try:
        _log.info("Trying to monkeypatch ID locale...")
        del _locale_map["id"]
        del _locale_map["id-id"]
    except Exception as e:
        _log.error("Failed to monkeypatch ID extended locale", exc_info=e)
        return

    class IndonesianExtendedLocale(Locale):
        names: ClassVar[list[str]] = ["id", "id-id"]

        past = "{0} yang lalu"
        future = "dalam {0}"
        and_word = "dan"

        meridians: ClassVar[dict[str, str]] = {"am": "", "pm": "", "AM": "", "PM": ""}

        month_names: ClassVar[list[str]] = [
            "",
            "Januari",
            "Februari",
            "Maret",
            "April",
            "Mei",
            "Juni",
            "Juli",
            "Agustus",
            "September",
            "Oktober",
            "November",
            "Desember",
        ]

        month_abbreviations: ClassVar[list[str]] = [
            "",
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "Mei",
            "Jun",
            "Jul",
            "Ags",
            "Sept",
            "Okt",
            "Nov",
            "Des",
        ]

        day_names: ClassVar[list[str]] = ["", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

        day_abbreviations: ClassVar[list[str]] = [
            "",
            "Senin",
            "Selasa",
            "Rabu",
            "Kamis",
            "Jumat",
            "Sabtu",
            "Minggu",
        ]

    # Arrow's Locale annotation has stricter key types than this custom mapping.
    # Keep the runtime override while avoiding an incompatible subclass field.
    setattr(
        IndonesianExtendedLocale,
        "timeframes",
        {
            "now": "baru saja",
            "second": "sedetik",
            "seconds": "{0} detik",
            "minute": "1 menit",
            "minutes": "{0} menit",
            "hour": "1 jam",
            "hours": "{0} jam",
            "day": "1 hari",
            "days": "{0} hari",
            "week": "1 minggu",
            "weeks": "{0} minggu",
            "month": "1 bulan",
            "months": "{0} bulan",
            "quarter": "1 kuartal",
            "quarters": "{0} kuartal",
            "year": "1 tahun",
            "years": "{0} tahun",
        },
    )

    _log.info(f"Monkeypatched ID locale with {IndonesianExtendedLocale.__name__}")


def monkeypatch_discord_tasks_loop():
    LoopTask: Any = discord.ext.tasks.Loop

    class BetterTasks(LoopTask):
        def __init__(
            self,
            coro: Any,
            seconds: float,
            hours: float,
            minutes: float,
            time: datetime.time | Sequence[datetime.time],
            count: int | None,
            reconnect: bool,
            name: Any,
        ) -> None:
            super().__init__(coro, seconds, hours, minutes, time, count, reconnect)
            if name is MISSING:
                name = self.coro.__name__
            setattr(self, "_task_name", name)

        def __get__(self, obj: Any, objtype: Any) -> Any:
            if obj is None:
                return self

            copy = BetterTasks(
                self.coro,
                seconds=self._seconds,
                hours=self._hours,
                minutes=self._minutes,
                time=self._time,
                count=self.count,
                reconnect=self.reconnect,
                name=getattr(self, "_task_name"),
            )
            copy._injected = obj
            copy._before_loop = self._before_loop
            copy._after_loop = self._after_loop
            copy._error = self._error
            setattr(obj, self.coro.__name__, copy)
            return copy

        @property
        def name(self) -> str:
            return getattr(self, "_task_name")

        def start(self, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
            if self._task and not self._task.done():
                raise RuntimeError("Task is already launched and is not completed.")

            if self._injected is not None:
                args = (self._injected, *args)

            task_name = f"discord.tasks-{self._task_name}-loop_n-{self._current_loop}"
            self._task = asyncio.create_task(self._loop(*args, **kwargs), name=task_name)
            return self._task

    def _patched_loop(
        *,
        seconds: float = MISSING,
        minutes: float = MISSING,
        hours: float = MISSING,
        time: datetime.time | Sequence[datetime.time] = MISSING,
        count: int | None = None,
        reconnect: bool = True,
        name: Any = MISSING,
    ) -> Callable[[Any], Any]:
        def decorator(func: Any) -> Any:
            return BetterTasks(
                func,
                seconds=seconds,
                minutes=minutes,
                hours=hours,
                count=count,
                time=time,
                reconnect=reconnect,
                name=name,
            )

        return decorator

    _log.info("Monkeypatching discord.ext.tasks.loop with new function")
    setattr(discord.ext.tasks, "loop", _patched_loop)


def monkeypatch_discord_context_menu():
    class BetterContextMenu(discord.app_commands.commands.ContextMenu):
        def __init__(
            self,
            *,
            name: str,
            callback: ContextMenuCallback,
            type: AppCommandType = MISSING,
            nsfw: bool = False,
            guild_ids: list[int] | None = None,
            extras: dict[Any, Any] = MISSING,
        ):
            super().__init__(name=name, callback=callback, type=type, nsfw=nsfw, guild_ids=guild_ids, extras=extras)
            self.__cog: Cog | None = None

        @property
        def cog(self) -> Cog | None:
            return self.__cog

        @cog.setter
        def cog(self, cog: Cog) -> None:
            self.__cog = cog

    _log.info("Monkeypatching discord.app_commands.commands.ContextMenu with new class")
    setattr(discord.app_commands.commands, "ContextMenu", BetterContextMenu)
