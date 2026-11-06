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

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from discord import ButtonStyle, SelectOption
from discord.ui import Button, Select, View, button

from naotimes.utils import generate_custom_code

if TYPE_CHECKING:
    from discord import Emoji, Interaction, PartialEmoji

    from naotimes.context import naoTimesContext

__all__ = (
    "MultiButtonView",
    "MultiSelectionView",
    "Selection",
)
MTV = TypeVar("MTV", bound="MultiSelectionView")
MBV = TypeVar("MBV", bound="MultiButtonView")


def _translate_label(ctx: object, key: str, fallback: str) -> str:
    """Resolve one shared label, keeping the Indonesian default without i18n."""
    translate = getattr(ctx, "t", None)
    if not callable(translate):
        return fallback
    try:
        translated = translate(key)
    except Exception:
        return fallback
    if not isinstance(translated, str):
        return fallback
    return fallback if translated == key else translated


@dataclass
class Selection:
    # Displayed in the select menu
    label: str
    # The internal value data
    name: str | None = None
    description: str | None = None
    emoji: Emoji | PartialEmoji | str | None = None
    disable: bool = False

    def __comp_name(self, other: str):
        return self.name == other or self.label == other

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, Selection):
            return self.__comp_name(__o.name or __o.label)
        if isinstance(__o, str):
            return self.__comp_name(__o)
        return False


class Selections(Select[MTV]):
    def __init__(self, selections: list[Selection], *, placeholder: str | None = None):
        as_options: list[SelectOption] = []
        for select in selections:
            as_options.append(
                SelectOption(
                    label=select.label,
                    value=select.name or select.label,
                    description=select.description,
                    emoji=select.emoji,
                )
            )

        self.__raw_options = as_options

        super().__init__(placeholder=placeholder or "Pilih salah satu", options=as_options, row=0)

    async def callback(self, interaction: Interaction):
        try:
            first_item = self.values[0]
        except IndexError:
            return

        for item in self.__raw_options:
            if item.value == first_item:
                view = self.view
                if isinstance(view, MultiSelectionView):
                    view.set_selected_value(item)
                    await view.disable_all(interaction)
                    view.stop()
                return


class MultiSelectionView(View):
    def __init__(self, ctx: naoTimesContext, selections: list[Selection], *, timeout: int = 180):
        super().__init__(timeout=timeout)
        if not isinstance(selections, list):
            raise TypeError("selections must be a list of Selection")
        for idx, select in enumerate(selections):
            if not isinstance(select, Selection):
                raise TypeError(f"selections[{idx}] must be a Selection")
        # Maximum 25 selections
        selections = selections[:25]

        self.add_item(
            Selections(
                selections,
                placeholder=_translate_label(ctx, "common.views.select_placeholder", "Pilih salah satu"),
            )
        )

        self._selected_value: SelectOption | None = None
        self._is_cancelled: bool = False
        self.ctx = ctx

        self.cancel.label = _translate_label(ctx, "common.views.cancel", "Batalkan")

    async def interaction_check(self, interaction: Interaction) -> bool:
        return self.ctx.author.id == interaction.user.id

    def set_selected_value(self, value: SelectOption):
        self._selected_value = value

    async def disable_all(self, inter: Interaction):
        for item in self.children:
            if isinstance(item, (Button, Select)):
                item.disabled = True
        await inter.response.edit_message(view=self)

    @property
    def selected(self):
        return self._selected_value

    @property
    def cancelled(self):
        return self._is_cancelled

    @button(label="Batalkan", style=ButtonStyle.secondary, emoji="❌", row=1)
    async def cancel(self, interaction: Interaction, button: Button):
        self._is_cancelled = True
        self._selected_value = None
        await self.disable_all(interaction)
        self.stop()


class ButtonSelect(Button[MBV]):
    def __init__(self, selection: Selection, *, row: int = 0):
        self._name = selection.name or selection.label or selection.emoji
        self._selection = selection
        super().__init__(label=selection.label, emoji=selection.emoji, row=row, disabled=selection.disable)

    async def callback(self, interaction: Interaction):
        view = self.view
        if isinstance(view, MultiButtonView):
            view.set_selected_value(self._selection)
            await view.disable_all(interaction)
            view.stop()


class MultiButtonView(View):
    def __init__(
        self,
        ctx: naoTimesContext,
        selections: list[Selection],
        *,
        timeout: int = 180,
        no_cancel: bool = False,
    ):
        super().__init__(timeout=timeout)
        if not isinstance(selections, list):
            raise TypeError("selections must be a list of Selection")
        for idx, select in enumerate(selections):
            if not isinstance(select, Selection):
                raise TypeError(f"selections[{idx}] must be a Selection")
        if len(selections) > 24:
            raise ValueError("MutliButtonView only able to get 24 selection!")
        self.__available_row = [5, 5, 5, 5, 4]
        for selection in selections:
            row = self.__get_button_row()
            self.add_item(ButtonSelect(selection, row=row))
        self._batal_code = f"batal-mbv-naotimes-{generate_custom_code()}"
        if not no_cancel:
            self.add_item(
                ButtonSelect(
                    Selection(
                        _translate_label(ctx, "common.views.cancel", "Batalkan"),
                        self._batal_code,
                        emoji="❌",
                    ),
                    row=self.__get_button_row(),
                )
            )

        self._selected_value: Selection | None = None
        self.ctx = ctx

    def __get_button_row(self):
        found_idx: int | None = None
        for row_idx, row_capacity in enumerate(self.__available_row):
            if row_capacity < 1:
                continue
            found_idx = row_idx
            break
        if found_idx is None:
            raise ValueError("Cannot add more button since it's full!")

        self.__available_row[found_idx] -= 1
        return found_idx

    async def interaction_check(self, interaction: Interaction) -> bool:
        return self.ctx.author.id == interaction.user.id

    def set_selected_value(self, value: Selection):
        self._selected_value = value

    async def disable_all(self, inter: Interaction):
        for item in self.children:
            if isinstance(item, (Button, Select)):
                item.disabled = True
        await inter.response.edit_message(view=self)

    @property
    def selected(self):
        return self._selected_value

    @property
    def cancelled(self):
        return self._selected_value is not None and self._selected_value.name == self._batal_code
