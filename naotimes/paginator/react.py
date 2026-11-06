"""
A reaction based paginator for naoTimes.
Scuffed edition!

---

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
from collections.abc import Callable, Coroutine
from functools import partial
from inspect import signature
from typing import TYPE_CHECKING, Generic, Protocol, TypedDict, TypeVar, cast

import discord

from .common import (
    IT,
    PaginationFailure,
    PaginatorGenerator,
    PaginatorValidator,
)

if TYPE_CHECKING:
    from ..bot import naoTimesBot
    from ..context import naoTimesContext

__all__ = ("DiscordPaginator", "PaginationHandler")

FIRST_EMOTE = "⏮"
PREV_EMOTE = "◀"
NEXT_EMOTE = "▶"
LAST_EMOTE = "⏭"
DELETE_EMOTE = "✅"
PAGINATION_EMOTE = (FIRST_EMOTE, PREV_EMOTE, NEXT_EMOTE, LAST_EMOTE)
ResultT = TypeVar("ResultT")


class _MessageKwargs(TypedDict, total=False):
    content: str
    embed: discord.Embed


class _MessageWithNoLogDelete(Protocol):
    async def delete(self, *, delay: float | None = None, no_log: bool = False) -> None: ...


class PaginationHandler(Generic[IT]):
    validator: PaginatorValidator[IT] | None
    generator: PaginatorGenerator | None
    is_paginator: bool = False

    def __init__(
        self,
        validator: PaginatorValidator[IT] | None,
        generator: PaginatorGenerator | None,
        is_paginator: bool = False,
    ):
        self.validator = validator
        self.generator = generator
        self.is_paginator = is_paginator


class DiscordPaginator(Generic[IT]):
    """
    A scuffed helper class to generate an automatic paginating
    tools for Discord.

    This is a bad idea.
    """

    def __init__(self, bot: naoTimesBot, ctx: naoTimesContext, datasets: list[IT]):
        self.bot: naoTimesBot = bot
        self.ctx: naoTimesContext = ctx
        self.datasets: list[IT] = datasets

        self._handler: dict[str, PaginationHandler[IT] | None] = {
            FIRST_EMOTE: None,
            PREV_EMOTE: None,
            NEXT_EMOTE: None,
            LAST_EMOTE: None,
        }
        self._default_gen: PaginatorGenerator | None = None

        self._stop_on_no_result = False
        self._remove_at_trashed = True
        self._paginate = True
        self.logger = logging.getLogger("Paginator.Reaction")

    @property
    def stop_on_no_result(self):
        return self._stop_on_no_result

    @stop_on_no_result.setter
    def stop_on_no_result(self, value: bool):
        self._stop_on_no_result = value

    @property
    def remove_at_trashed(self):
        return self._remove_at_trashed

    @remove_at_trashed.setter
    def remove_at_trashed(self, value: bool):
        self._remove_at_trashed = value

    @property
    def paginateable(self):
        return self._paginate

    @paginateable.setter
    def paginateable(self, data: bool):
        self._paginate = data

    async def _maybe_asyncute(
        self, cb: Callable[..., ResultT | Coroutine[object, object, ResultT]], *args: object, **kwargs: object
    ) -> ResultT:
        real_func = cb.func if isinstance(cb, partial) else cb
        if asyncio.iscoroutinefunction(real_func):
            return await cast(Coroutine[object, object, ResultT], cb(*args, **kwargs))
        return cast(ResultT, cb(*args, **kwargs))

    def add_handler(self, emote: str, validate: PaginatorValidator[IT], generator: PaginatorGenerator | None = None):
        if emote in self._handler:
            raise ValueError("Emote already exist")

        if not callable(validate):
            raise ValueError("callback is not a function")

        if generator is not None and not callable(generator):
            raise ValueError("Generator is not a function")

        self._handler[emote] = PaginationHandler(validate, generator)

    def remove_handler(self, emote: str):
        if emote not in self._handler:
            raise ValueError("Emote not found")
        del self._handler[emote]

    def set_generator(self, generator: PaginatorGenerator):
        if not callable(generator):
            raise ValueError("Generator is not a function")
        for emote in PAGINATION_EMOTE:
            self._handler[emote] = PaginationHandler(None, generator, True)
        self._default_gen = generator

    def _check_function(self, func: PaginatorGenerator):
        available_args = []
        sigmaballs = signature(func)
        for param in sigmaballs.parameters.values():
            if param.default != param.empty:
                continue
            available_args.append(param)
        pass_data = pass_position = pass_msg = False
        pass_emote = False
        if len(available_args) == 1:
            pass_data = True
        if len(available_args) == 2:
            pass_data = pass_position = True
        if len(available_args) == 3:
            pass_data = pass_position = pass_msg = True
        if len(available_args) == 4:
            pass_data = pass_position = pass_msg = pass_emote = True
        return pass_data, pass_position, pass_msg, pass_emote

    async def __try_to_generate(
        self, data: IT, position: int, message: discord.Message | None = None, emote: str | None = None
    ):
        callback = self._default_gen
        if emote is not None:
            handler = self._handler.get(emote)
            if handler is not None and handler.generator is not None:
                callback = handler.generator
        if callback is None:
            return data
        can_data, can_pos, can_msg, can_emote = self._check_function(callback)
        full_argument = []
        if can_data:
            full_argument.append(data)
        if can_pos:
            full_argument.append(position)
        if can_msg:
            full_argument.append(message)
        if can_emote:
            full_argument.append(emote)
        generator = await self._maybe_asyncute(callback, *full_argument)
        return generator

    @staticmethod
    def __generate_message(generated: object) -> _MessageKwargs | None:
        raw_msg: str | None = None
        embed: discord.Embed | None = None
        if isinstance(generated, (list, tuple)):
            for data in generated:
                if isinstance(data, discord.Embed):
                    embed = data
                elif isinstance(data, str):
                    raw_msg = data
        elif isinstance(generated, discord.Embed):
            embed = generated
        elif isinstance(generated, (str, int)):
            if isinstance(generated, int):
                generated = str(generated)
            raw_msg = generated
        if not raw_msg and not embed:
            return None
        final_kwargs: _MessageKwargs = {}
        if isinstance(raw_msg, str):
            final_kwargs["content"] = raw_msg
        if isinstance(embed, discord.Embed):
            final_kwargs["embed"] = embed
        return final_kwargs

    async def __wrap_generator_stuff(
        self, content: IT, position: int, message: discord.Message | None, emote: str | None
    ) -> _MessageKwargs | None:
        if not callable(self._default_gen):
            return self.__generate_message(content)
        generated = await self.__try_to_generate(content, position, message, emote)
        final_kwargs = self.__generate_message(generated)
        return final_kwargs

    def has_generator(self):
        return callable(self._default_gen)

    async def paginate(
        self,
        timeout: float | None = None,  # ruff: ignore[async-function-with-timeout]
        message: discord.Message | None = None,
    ):
        contents = self.datasets

        if len(contents) < 1:
            return

        position = 1
        maximum = len(contents)
        is_timeout = False
        dont_reset = False
        current_emote = None
        while True:
            content = contents[position - 1]
            final_kwargs = await self.__wrap_generator_stuff(content, position - 1, message, current_emote)
            if not final_kwargs:
                raise PaginationFailure(content, position - 1, self)
            if message is None:
                message = await self.ctx.send(**final_kwargs)
                if message is None:
                    raise RuntimeError("Pagination message was not created")
            else:
                if not dont_reset:
                    await message.edit(**final_kwargs)

            react_andy = []
            if maximum == 1 and position == 1:
                if self._stop_on_no_result:
                    break
            elif position == 1 and self._paginate:
                react_andy.extend([NEXT_EMOTE, LAST_EMOTE])
            elif position == maximum and self._paginate:
                react_andy.extend([FIRST_EMOTE, PREV_EMOTE])
            elif position > 1 and position < maximum and self._paginate:
                react_andy.extend(PAGINATION_EMOTE)

            if self.has_generator():
                for emote, handler in self._handler.items():
                    if emote in PAGINATION_EMOTE:
                        continue
                    if handler is None or handler.validator is None:
                        continue
                    is_success = await self._maybe_asyncute(handler.validator, content)
                    if is_success:
                        react_andy.append(emote)
            react_andy.append(DELETE_EMOTE)

            if not dont_reset:
                for react in react_andy:
                    await message.add_reaction(react)
            else:
                dont_reset = False

            if message is None:
                raise RuntimeError("Pagination message is unavailable")
            current_message = message

            def check_reaction(reaction: discord.Reaction, user: discord.User):
                if reaction.message.id != current_message.id:
                    return False
                if user.id != self.ctx.author.id:
                    return False
                if str(reaction.emoji) not in react_andy:
                    return False
                return True

            res: discord.Reaction
            user: discord.User
            try:
                res, user = await self.bot.wait_for("reaction_add", timeout=timeout, check=check_reaction)
            except TimeoutError:
                is_timeout = True
                self.logger.warning("Timeout, removing reaction...")
                await message.clear_reactions()
                break
            if user.id != self.ctx.author.id:
                dont_reset = True
                continue
            await message.clear_reactions()
            if res.emoji == FIRST_EMOTE:
                position = 1
                current_emote = FIRST_EMOTE
            elif res.emoji == LAST_EMOTE:
                position = maximum
                current_emote = LAST_EMOTE
            elif res.emoji == NEXT_EMOTE:
                position += 1
                current_emote = NEXT_EMOTE
            elif res.emoji == PREV_EMOTE:
                position -= 1
                current_emote = PREV_EMOTE
            elif res.emoji == DELETE_EMOTE:
                if self._remove_at_trashed:
                    await cast(_MessageWithNoLogDelete, message).delete(no_log=True)
                break
            else:
                current_emote = None
                handler = self._handler.get(str(res.emoji))
                generator = handler.generator if handler is not None else None
                if generator is None:
                    generator = self._default_gen
                if generator is None:
                    continue
                can_data, can_pos, can_msg, can_emote = self._check_function(generator)
                generator_args: list[object] = []
                if can_data:
                    generator_args.append(content)
                if can_pos:
                    generator_args.append(position)
                if can_msg:
                    generator_args.append(message)
                if can_emote:
                    generator_args.append(str(res.emoji))
                executed_child = await self._maybe_asyncute(generator, *generator_args)
                generated: object = executed_child
                timeout_error = False
                if isinstance(executed_child, tuple) and len(executed_child) == 3:
                    result, result_message, result_timeout = executed_child
                    if isinstance(result_message, discord.Message) and isinstance(result_timeout, bool):
                        generated = result
                        message = result_message
                        timeout_error = result_timeout
                elif isinstance(executed_child, tuple) and len(executed_child) == 2:
                    result, result_message = executed_child
                    if isinstance(result_message, discord.Message):
                        generated = result
                        message = result_message
                if timeout_error:
                    is_timeout = True
                    break
                if generated is None:
                    generated = await self.__try_to_generate(content, position - 1, message, current_emote)
                if generated:
                    final_kwargs = self.__generate_message(generated)
                    if final_kwargs is not None:
                        await message.edit(**final_kwargs)
        return is_timeout

    start = paginate
