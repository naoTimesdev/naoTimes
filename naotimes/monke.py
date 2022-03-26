"""
MIT License

Copyright (c) 2019-2021 naoTimesdev

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
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence, Type, TypeVar, Union

import disnake.ext.tasks
import disnake.message
import disnake.state
from arrow.locales import Locale, _locale_map
from disnake import ComponentType, MessageInteraction, ModalInteraction, Thread
from disnake.enums import MessageType
from disnake.utils import MISSING

from .context import naoTimesAppContext

if TYPE_CHECKING:
    from datetime import datetime, time

    from disnake.guild import Guild
    from disnake.types.interactions import (
        ApplicationCommandInteraction as ApplicationCommandInteractionPayload,
    )

__all__ = (
    "monkeypatch_message_delete",
    "monkeypatch_arrow_id_locale",
    "monkeypatch_interaction_create",
    "monkeypatch_thread_create",
    "monkeypatch_disnake_tasks_loop",
)

_log = logging.getLogger("naoTimes.Monke")
T = TypeVar("T")


class MessageTypeNew(MessageType):
    deleted_message_no_log = 9999


def monkeypatch_message_delete():
    ORIGINAL_DELETE = disnake.message.Message.delete

    async def delete_strategy(
        self: disnake.message.Message, *, delay: Optional[float] = None, no_log: bool = False
    ):
        if no_log:
            self.type = MessageTypeNew.deleted_message_no_log

        await ORIGINAL_DELETE(self, delay=delay)

    _log.info("Monkeypatching discord.message.Message.delete with new function")
    disnake.message.Message.delete = delete_strategy


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


def monkeypatch_interaction_create():
    def _parse_interaction_create(
        self: disnake.state.ConnectionState, data: ApplicationCommandInteractionPayload
    ) -> None:
        # A modified version of interaction create to use
        # naoTimesAppContext to dispatch the slash_command!
        interaction_type = data["type"]
        if interaction_type == 1:
            # PING interaction should never be received
            return
        elif interaction_type == 2:
            interaction = naoTimesAppContext(data=data, state=self)
            self.dispatch("application_command", interaction)
        elif interaction_type == 3:
            interaction = MessageInteraction(data=data, state=self)
            self._view_store.dispatch(interaction)
            self.dispatch("message_interaction", interaction)
            if interaction.data.component_type is ComponentType.button:
                self.dispatch("button_click", interaction)
            elif interaction.data.component_type is ComponentType.select:
                self.dispatch("dropdown", interaction)
        elif interaction_type == 4:
            interaction = naoTimesAppContext(data=data, state=self)
            self.dispatch("application_command_autocomplete", interaction)

        elif interaction_type == 5:
            interaction = ModalInteraction(data=data, state=self)
            self._modal_store.dispatch(interaction)
            self.dispatch("modal_submit", interaction)
        else:
            return

        self.dispatch("interaction", interaction)

    _log.info("Monkeypatching discord.state.ConnectionState.parse_integration_create with new function")
    disnake.state.ConnectionState.parse_interaction_create = _parse_interaction_create


def monkeypatch_thread_create():
    def _parse_thread_create(self: disnake.state.ConnectionState, data):
        guild_id = int(data["guild_id"])
        guild: Optional[Guild] = self._get_guild(guild_id)
        if guild is None:
            _log.debug("THREAD_CREATE referencing an unknown guild ID: %s. Discarding", guild_id)
            return
        new_thread = data.get("newly_created", False)

        thread = Thread(guild=guild, state=guild._state, data=data)
        has_thread = guild.get_thread(thread.id)
        guild._add_thread(thread)
        if new_thread:
            self.dispatch("thread_create", thread)
            return
        if not has_thread:
            self.dispatch("thread_join", thread)

    _log.info("Monkeypatching discord.state.ConnectionState.parse_thread_create with new function")
    disnake.state.ConnectionState.parse_thread_create = _parse_thread_create


def monkeypatch_disnake_tasks_loop():
    LF = disnake.ext.tasks.LF
    LoopTask = disnake.ext.tasks.Loop

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
            name: str,
            loop: asyncio.AbstractEventLoop,
        ) -> None:
            super().__init__(coro, seconds, hours, minutes, time, count, reconnect, loop)
            if name is MISSING:
                name = self.coro.__name__
            self._task_name: str = name

        def __get__(self, obj: T, objtype: Type[T]) -> LoopTask[LF]:
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
                loop=self.loop,
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
            if self._task is not MISSING and not self._task.done():
                raise RuntimeError("Task is already launched and is not completed.")

            if self._injected is not None:
                args = (self._injected, *args)

            if self.loop is MISSING:
                self.loop = asyncio.get_event_loop()

            task_name = f"disnake.tasks-{self._task_name}-loop_n-{self._current_loop}"
            self._task = self.loop.create_task(self._loop(*args, **kwargs), name=task_name)
            return self._task

    def _patched_loop(
        *,
        seconds: float = MISSING,
        minutes: float = MISSING,
        hours: float = MISSING,
        time: Union[time, Sequence[time]] = MISSING,
        count: Optional[int] = None,
        reconnect: bool = True,
        name: str = MISSING,
        loop: asyncio.AbstractEventLoop = MISSING,
    ) -> Callable[[LF], BetterTasks[LF]]:
        def decorator(func: LF) -> BetterTasks[LF]:
            return BetterTasks[LF](
                coro=func,
                seconds=seconds,
                minutes=minutes,
                hours=hours,
                time=time,
                count=count,
                reconnect=reconnect,
                name=name,
                loop=loop,
            )

        return decorator

    _log.info("Monkeypatching discord.ext.tasks.loop with new function")
    disnake.ext.tasks.loop = _patched_loop
