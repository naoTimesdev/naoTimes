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
from collections.abc import Callable, Coroutine
from enum import Enum
from functools import partial
from inspect import signature
from time import time
from typing import TYPE_CHECKING, Generic, TypedDict, TypeVar, Unpack, cast

import discord
from discord.ui import Button, View

from naotimes.utils import generate_custom_code

from .common import (
    PaginatorGenerator,
    PaginatorValidator,
)

if TYPE_CHECKING:
    from naotimes.context import naoTimesContext


def _translate_view_label(ctx: object, key: str, fallback: str, **kwargs: object) -> str:
    """Resolve a shared view label, keeping the Indonesian default without i18n."""
    translate = getattr(ctx, "t", None)
    if not callable(translate):
        return fallback
    try:
        translated = translate(key, **kwargs)
    except Exception:
        return fallback
    if not isinstance(translated, str):
        return fallback
    return fallback if translated == key else translated


__all__ = ("DiscordPaginatorUI",)
IT = TypeVar("IT")
ViewT = TypeVar("ViewT", bound="DiscordPaginatorUI")
ResultT = TypeVar("ResultT")


class _CustomButtonKwargs(TypedDict, total=False):
    style: discord.ButtonStyle
    disabled: bool
    url: str | None
    emoji: str | discord.Emoji | discord.PartialEmoji | None
    row: int | None


class _MessageKwargs(TypedDict, total=False):
    content: str
    embed: discord.Embed
    view: View


def _require_view(view: ViewT | None) -> ViewT:
    if view is None:
        raise RuntimeError("Paginator button is not attached to a view")
    return view


class IncrType(Enum):
    """
    Enum for the different types of incrementing.
    """

    INCREMENT = 1
    DECREMENT = 2
    FIRST = 3
    LAST = 4
    IGNORE = 5


class NavButton(Button[ViewT]):
    def __init__(
        self,
        incr_type: IncrType = IncrType.INCREMENT,
        *,
        label: str | None = None,
        emoji: str | None = None,
        disabled: bool = False,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        row: int = 0,
    ):
        super().__init__(style=style, label=label, disabled=disabled, emoji=emoji, row=row)

        self._incr = incr_type

    async def callback(self, interaction: discord.Interaction):
        view = _require_view(self.view)
        if self._incr == IncrType.FIRST:
            view.page = 0
        elif self._incr == IncrType.LAST:
            view.page = view.max_page
        elif self._incr == IncrType.INCREMENT:
            view.page = view.page + 1
            view.page = min(view.page, view.max_page)
        elif self._incr == IncrType.DECREMENT:
            view.page = view.page - 1
            view.page = max(view.page, 0)
        await view.call_handler(interaction)


class FinishButton(Button[ViewT]):
    def __init__(self, *, row: int = 1, label: str | None = None):
        super().__init__(label=label or "Beres", emoji="✅", style=discord.ButtonStyle.danger, row=row)
        self._is_finish_btn = True

    async def callback(self, interaction: discord.Interaction):
        view = _require_view(self.view)
        if view.parent is not None:
            return await view.reset_to_parent(interaction)

        view.is_stopping = True
        await view.update_view()
        await interaction.response.edit_message(view=view)
        await view.stop_all()


class CustomButton(Button[ViewT]):
    def __init__(
        self,
        label: str,
        *,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        disabled: bool = False,
        url: str | None = None,
        emoji: str | discord.Emoji | discord.PartialEmoji | None = None,
        row: int | None = None,
    ):
        custom_id = f"{label}_{int(time())}_{generate_custom_code(4)}"
        super().__init__(
            style=style, label=label, disabled=disabled, custom_id=custom_id, url=url, emoji=emoji, row=row
        )

    async def callback(self, interaction: discord.Interaction):
        view = _require_view(self.view)
        await view.call_handler(interaction, self.custom_id)


class PaginateHandler(Generic[IT]):
    validator: PaginatorValidator[IT]
    generator: PaginatorGenerator | None

    def __init__(
        self,
        label: str,
        validator: PaginatorValidator[IT],
        generator: PaginatorGenerator | None,
        button_kwargs: _CustomButtonKwargs,
    ):
        self.label: str = label
        self.validator = validator
        self.generator = generator
        self.btn_kwargs = button_kwargs


class DiscordPaginatorUI(View, Generic[IT]):
    def __init__(
        self,
        ctx: naoTimesContext,
        items: list[IT],
        timeout: float | None = None,
        paginateable: bool = True,
    ):
        super().__init__(timeout=timeout)
        self.logger = logging.getLogger("Paginator.UIv2")

        self.ctx: naoTimesContext = ctx

        self._items: list[IT] = items
        self.__actual_timeout: float | None = timeout
        self._page: int = 0

        self._parent_view: DiscordPaginatorUI | None = None
        self._message: discord.Message | None = None
        self._paginateable = paginateable
        self._is_stopping: bool = False

        # Row 2, 3, 4, 5
        self.__available_row = [5, 5, 5, 4]
        self._is_nav_attached = False

        self._default_gen: PaginatorGenerator | None = None
        self._handlers: dict[str, PaginateHandler[IT]] = {}

        if paginateable:
            self._attach_navigator()
        self.add_item(FinishButton(row=4, label=_translate_view_label(self.ctx, "common.views.finish", "Beres")))

    @property
    def page(self):
        return self._page

    @page.setter
    def page(self, _page: int):
        if not isinstance(_page, int):
            return
        self._page = _page

    @property
    def max_page(self):
        return len(self._items) - 1

    @property
    def total_pages(self):
        return len(self._items)

    @property
    def parent(self):
        return self._parent_view

    @parent.setter
    def parent(self, value: DiscordPaginatorUI | None):
        self._parent_view = value

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, _msg: discord.Message | None):
        self._message = _msg

    @property
    def is_stopping(self):
        return self._is_stopping

    @is_stopping.setter
    def is_stopping(self, value: bool):
        self._is_stopping = bool(value)

    @property
    def actual_timeout(self):
        return self.__actual_timeout

    def _find_btn_by_id(self, btn_id: str) -> CustomButton | None:
        for btn in self.children:
            if isinstance(btn, CustomButton):
                if btn.custom_id == btn_id:
                    return btn
        return None

    def __get_button_row(self, wanted_row: int | None = None):
        # Find empty row
        if wanted_row is not None and wanted_row >= 1 and wanted_row <= 4:
            row_cap = self.__available_row[wanted_row]
            if row_cap > 0:
                self.__available_row[wanted_row] -= 1
                return wanted_row
        found_idx: int | None = None
        for row_idx, row_capacity in enumerate(self.__available_row, 1):
            if row_capacity < 1:
                continue
            found_idx = row_idx
            break
        if found_idx is None:
            raise ValueError("Cannot add more button since it's full!")

        self.__available_row[found_idx - 1] -= 1
        return found_idx

    def attach(self, generator: PaginatorGenerator):
        if not callable(generator):
            raise ValueError("Generator is not a function")
        self._default_gen = generator

    def add_handler(
        self,
        label: str,
        validator: PaginatorValidator[IT],
        generator: PaginatorGenerator | None = None,
        **button_kwargs: Unpack[_CustomButtonKwargs],
    ):
        if not callable(validator):
            raise ValueError("validate is not a function!")
        if generator is not None and not callable(generator):
            raise ValueError("generator is not a function!")
        button_kwargs.pop("disabled", None)
        want_row = button_kwargs.pop("row", None)
        actual_row = self.__get_button_row(want_row)
        unknown_kwarg = next((name for name in button_kwargs if name not in {"style", "url", "emoji"}), None)
        if unknown_kwarg is not None:
            raise TypeError(f"CustomButton.__init__() got an unexpected keyword argument {unknown_kwarg!r}")
        button = CustomButton(
            label,
            style=button_kwargs.get("style", discord.ButtonStyle.secondary),
            url=button_kwargs.get("url"),
            emoji=button_kwargs.get("emoji"),
            row=actual_row,
        )
        custom_id = button.custom_id
        if custom_id is None:
            raise RuntimeError("Custom button did not receive an ID")
        self._handlers[custom_id] = PaginateHandler(label, validator, generator, button_kwargs)
        self.add_item(button)

    async def _maybe_asyncute(
        self, cb: Callable[..., ResultT | Coroutine[object, object, ResultT]], *args: object, **kwargs: object
    ) -> ResultT:
        real_func = cb.func if isinstance(cb, partial) else cb
        if asyncio.iscoroutinefunction(real_func):
            return await cast(Coroutine[object, object, ResultT], cb(*args, **kwargs))
        return cast(ResultT, cb(*args, **kwargs))

    def _check_function(self, func: PaginatorGenerator):
        available_args = []
        sigmaballs = signature(func)
        for param in sigmaballs.parameters.values():
            if param.default != param.empty:
                continue
            available_args.append(param)
        pass_data = pass_position = pass_msg = pass_view = False
        if len(available_args) == 1:
            pass_data = True
        if len(available_args) == 2:
            pass_data = pass_position = True
        if len(available_args) == 3:
            pass_data = pass_position = pass_msg = True
        if len(available_args) == 4:
            pass_data = pass_position = pass_msg = pass_view = True
        return pass_data, pass_position, pass_msg, pass_view

    async def __try_to_generate(
        self, data: IT, position: int, message: discord.Message | None = None, btn_id: str | None = None
    ) -> object:
        callback = self._default_gen
        if not callable(callback):
            return data
        if btn_id is not None:
            handler = self._handlers.get(btn_id)
            if handler is not None and handler.generator is not None:
                callback = handler.generator
        can_data, can_pos, can_msg, can_view = self._check_function(callback)
        full_argument = []
        if can_data:
            full_argument.append(data)
        if can_pos:
            full_argument.append(position)
        if can_msg:
            full_argument.append(message)
        if can_view:
            full_argument.append(self)
        generated = await self._maybe_asyncute(callback, *full_argument)
        return generated

    async def __generate_message(self, generated: object) -> _MessageKwargs | None:
        raw_msg: str | None = None
        embed: discord.Embed | None = None
        raw_view: View | None = None
        if isinstance(generated, (list, tuple)):
            for data in generated:
                if isinstance(data, discord.Embed):
                    embed = data
                elif isinstance(data, str):
                    raw_msg = data
                elif isinstance(data, View):
                    raw_view = data
        elif isinstance(generated, View):
            raw_view = generated
        elif isinstance(generated, discord.Embed):
            embed = generated
        elif isinstance(generated, (str, int, float)):
            if isinstance(generated, (int, float)):
                generated = str(generated)
            raw_msg = generated
        if not raw_msg and not embed and not raw_view:
            return None
        final_kwargs: _MessageKwargs = {}
        if isinstance(raw_msg, str):
            final_kwargs["content"] = raw_msg
        if isinstance(embed, discord.Embed):
            final_kwargs["embed"] = embed
        if raw_view is not None:
            if isinstance(raw_view, DiscordPaginatorUI):
                # Attach nested paginator and its parent.
                raw_view.message = self._message
                raw_view._parent_view = self
                kwargument = await raw_view.generate_quick_kwargs()
                if kwargument is not None:
                    if "content" in kwargument:
                        final_kwargs["content"] = kwargument["content"]
                    if "embed" in kwargument:
                        final_kwargs["embed"] = kwargument["embed"]
                self.timeout = None
            final_kwargs["view"] = raw_view
        else:
            final_kwargs["view"] = self
        return final_kwargs

    async def call_handler(self, interaction: discord.Interaction, button_id: str | None = None):
        final_kwargs = await self.generate_quick_kwargs(button_id)
        if final_kwargs is None:
            await interaction.response.edit_message()
        else:
            await interaction.response.edit_message(**final_kwargs)

    async def generate_quick_kwargs(self, button_id: str | None = None):
        data = self._items[self._page]
        await self.update_view()
        generated = await self.__try_to_generate(data, self._page, self._message, button_id)
        final_kwargs = await self.__generate_message(generated)
        return final_kwargs

    async def reset_to_parent(self, interaction: discord.Interaction):
        parent = self._parent_view
        if parent is None:
            return
        parent.timeout = parent.actual_timeout
        await parent.call_handler(interaction)
        self.stop()

    async def update_view(self):
        curr = self._page + 1
        content = self._items[self._page]
        total = self.total_pages
        for item in self.children:
            if isinstance(item, NavButton):
                item.disabled = False
                if self._page == 0:
                    if item._incr in (IncrType.DECREMENT, IncrType.FIRST):
                        item.disabled = True
                if self._page == self.max_page:
                    if item._incr in (IncrType.INCREMENT, IncrType.LAST):
                        item.disabled = True
                if self.is_stopping or self.total_pages == 1:
                    item.disabled = True
                if item._incr == IncrType.IGNORE:
                    item.disabled = True
                    item.label = _translate_view_label(
                        self.ctx,
                        "common.views.page",
                        f"Halaman {curr}/{total}",
                        current=curr,
                        total=total,
                    )
            elif isinstance(item, FinishButton):
                item.disabled = self.is_stopping
            elif isinstance(item, CustomButton) and self.is_stopping:
                item.disabled = True

        if not self.is_stopping:
            for key_id, gen_data in self._handlers.items():
                btn = self._find_btn_by_id(key_id)
                if btn is None:
                    continue
                is_valid = await self._maybe_asyncute(gen_data.validator, content)
                btn.disabled = not is_valid

    def _attach_navigator(self):
        if self._is_nav_attached:
            return
        first_btn = NavButton(IncrType.FIRST, emoji="⏮")
        prev_btn = NavButton(IncrType.DECREMENT, emoji="◀")
        cur_page = NavButton(IncrType.IGNORE, label="1/1", style=discord.ButtonStyle.primary, disabled=True)
        next_btn = NavButton(IncrType.INCREMENT, emoji="▶")
        last_btn = NavButton(IncrType.LAST, emoji="⏭")

        self.add_item(first_btn)
        self.add_item(prev_btn)
        self.add_item(cur_page)
        self.add_item(next_btn)
        self.add_item(last_btn)
        self._is_nav_attached = True

    def _remove_navigator(self):
        if not self._is_nav_attached:
            return
        to_be_removed: list[NavButton] = []
        for item in self.children:
            if isinstance(item, NavButton):
                to_be_removed.append(item)

        self._paginateable

        for item in to_be_removed:
            self.remove_item(item)
        self._is_nav_attached = False

    @property
    def paginateable(self) -> bool:
        return self._paginateable

    @paginateable.setter
    def paginateable(self, value: bool):
        self._paginateable = bool(value)
        if self._paginateable:
            self._attach_navigator()
        else:
            self._remove_navigator()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return self.ctx.author.id == interaction.user.id

    async def on_timeout(self) -> None:
        # Shut down all parent
        await self.stop_all()
        self.is_stopping = True
        self.logger.info("Timeout occured, updating view...")
        await self.update_view()
        message = self.message
        if message is not None:
            self.logger.info("Message detected, editing...")
            await message.edit(view=self)

    async def stop_all(self):
        if self._parent_view is not None:
            await self._parent_view.stop_all()
        self.stop()

    async def __verify_contents_no_gen(self):
        for data in self._items:
            gen_kwargs = await self.__generate_message(data)
            if gen_kwargs is None:
                raise ValueError("Default generator is empty, and one of the item is not generatable!")
        return True

    async def interact(
        self,
        timeout: float | None = None,  # ruff: ignore[async-function-with-timeout]
    ):
        """Start interaction with the custom view

        Will generate message if it's none.
        Using internal ctx that are passed by user!
        """

        if timeout is not None:
            self.timeout = timeout
            self.__actual_timeout = timeout
        if self._default_gen is None:
            # Check if all data is able to be created by __generate_message
            await self.__verify_contents_no_gen()

        self.logger.info("Starting interaction...")
        parent = self.parent
        if parent is not None:
            parent_message = parent.message
            self.message = parent_message
            if parent_message is not None:
                await parent_message.edit(view=self)
            return

        if self.message is None:
            self.logger.warning("Will generate starting message first...")
            data = self._items[self._page]
            generated = await self.__try_to_generate(data, self._page, self._message)
            gen_kwargs = await self.__generate_message(generated)
            real_kwargs: _MessageKwargs = {}
            if gen_kwargs is not None:
                if "content" in gen_kwargs:
                    real_kwargs["content"] = gen_kwargs["content"]
                if "embed" in gen_kwargs:
                    real_kwargs["embed"] = gen_kwargs["embed"]
            self.message = await self.ctx.send(**real_kwargs)

        if self.total_pages == 1:
            if not self._handlers:
                self.logger.warning("There's only a single page, will not attach view")
                return
            self._remove_navigator()
            for item in self.children:
                row = item.row
                if row is None:
                    continue
                new_row = row - 1
                if new_row < 0:
                    continue
                item.row = new_row

        self.logger.info("Attaching UI View!")
        await self.update_view()
        message = self.message
        if message is not None:
            await message.edit(view=self)
