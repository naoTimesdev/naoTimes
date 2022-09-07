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
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Type, TypeVar, Union

import discord.app_commands.commands
import discord.ext.tasks
import discord.message
import discord.state
from arrow.locales import Locale, _locale_map
from discord.enums import MessageType
from discord.utils import MISSING

if TYPE_CHECKING:
    from discord.app_commands.commands import AppCommandType, ContextMenuCallback
    from discord.ext.commands.cog import Cog

__all__ = (
    "monkeypatch_message_delete",
    "monkeypatch_arrow_id_locale",
    "monkeypatch_discord_tasks_loop",
    "monkeypatch_discord_context_menu",
)

_log = logging.getLogger("naoTimes.Monke")
T = TypeVar("T")


class MessageTypeNew(MessageType):
    deleted_message_no_log = 9999


def monkeypatch_message_delete():
    ORIGINAL_DELETE = discord.message.Message.delete

    async def delete_strategy(
        self: discord.message.Message, *, delay: Optional[float] = None, no_log: bool = False
    ):
        if no_log:
            self.type = MessageTypeNew.deleted_message_no_log

        await ORIGINAL_DELETE(self, delay=delay)

    _log.info("Monkeypatching discord.message.Message.delete with new function")
    discord.message.Message.delete = delete_strategy


def monkeypatch_arrow_id_locale():
    try:
        _log.info("Trying to monkeypatch ID locale...")
        del _locale_map["id"]
        del _locale_map["id-id"]
    except Exception as e:
        _log.error("Failed to monkeypatch ID extended locale", exc_info=e)
        return

    class IndonesianExtendedLocale(Locale):

        names = ["id", "id-id"]

        past = "{0} yang lalu"
        future = "dalam {0}"
        and_word = "dan"

        timeframes = {
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
        }

        meridians = {"am": "", "pm": "", "AM": "", "PM": ""}

        month_names = [
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

        month_abbreviations = [
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

        day_names = ["", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

        day_abbreviations = [
            "",
            "Senin",
            "Selasa",
            "Rabu",
            "Kamis",
            "Jumat",
            "Sabtu",
            "Minggu",
        ]

    _log.info(f"Monkeypatched ID locale with {IndonesianExtendedLocale.__name__}")


def monkeypatch_discord_tasks_loop():
    LF = discord.ext.tasks.LF
    LoopTask = discord.ext.tasks.Loop

    class BetterTasks(LoopTask[LF]):
        def __init__(
            self,
            coro: LF,
            seconds: float,
            hours: float,
            minutes: float,
            time: Union[datetime.time, Sequence[datetime.time]],
            count: Optional[int],
            reconnect: bool,
            name: Optional[str],
        ) -> None:
            super().__init__(coro, seconds, hours, minutes, time, count, reconnect)
            if name is MISSING:
                name = self.coro.__name__
            self._task_name: str = name

        def __get__(self, obj: T, objtype: Type[T]) -> BetterTasks[LF]:
            if obj is None:
                return self

            copy: BetterTasks[LF] = BetterTasks(
                self.coro,
                seconds=self._seconds,
                hours=self._hours,
                minutes=self._minutes,
                time=self._time,
                count=self.count,
                reconnect=self.reconnect,
                name=self._task_name,
            )
            copy._injected = obj
            copy._before_loop = self._before_loop
            copy._after_loop = self._after_loop
            copy._error = self._error
            setattr(obj, self.coro.__name__, copy)
            return copy

        @property
        def name(self) -> str:
            return self._task_name

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
        time: Union[datetime.time, Sequence[datetime.time]] = MISSING,
        count: Optional[int] = None,
        reconnect: bool = True,
        name: str = MISSING,
    ) -> Callable[[LF], BetterTasks[LF]]:
        def decorator(func: LF) -> BetterTasks[LF]:
            return BetterTasks[LF](
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
    discord.ext.tasks.loop = _patched_loop


def monkeypatch_discord_context_menu():
    class BetterContextMenu(discord.app_commands.commands.ContextMenu):
        def __init__(
            self,
            *,
            name: str,
            callback: ContextMenuCallback,
            type: AppCommandType = MISSING,
            nsfw: bool = False,
            guild_ids: Optional[List[int]] = None,
            extras: Dict[Any, Any] = MISSING,
        ):
            super().__init__(
                name=name, callback=callback, type=type, nsfw=nsfw, guild_ids=guild_ids, extras=extras
            )
            self.__cog: Cog = None

        @property
        def cog(self) -> Optional[Cog]:
            return self.__cog

        @cog.setter
        def cog(self, cog: Cog) -> None:
            self.__cog = cog

    _log.info("Monkeypatching discord.app_commands.commands.ContextMenu with new class")
    discord.app_commands.commands.ContextMenu = BetterContextMenu
