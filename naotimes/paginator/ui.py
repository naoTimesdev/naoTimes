"""
A UI based paginator for naoTimes.
Scuffed edition!

---

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

import logging
from inspect import iscoroutinefunction, signature
from typing import Generic, List, Optional, TypeVar

import discord
import discord.ui as DisUI
from discord import Interaction
from discord.ext.commands import Context

from .common import IT, GeneratedKwargs, GeneratorOutput, PaginationFailure, PaginatorGenerator

__all__ = ("DiscordPaginatorUI",)

Number = TypeVar("Number", int, float)


class DiscordPaginatorUI(DisUI.View, Generic[IT]):
    """
    A UI based paginator helper class.
    This utilize the new UI kit feature.
    """

    def __init__(self, ctx: Context, items: List[IT], timeout: Optional[Number] = None):
        super().__init__(timeout=timeout)
        self.logger = logging.getLogger("Paginator.UI")
        self.message: Optional[discord.Message] = None

        self.ctx: Context = ctx
        self._author = ctx.author
        self._default_gen: Optional[PaginatorGenerator[IT]] = None
        self._pages: List[IT] = items
        self._page = 0
        self._is_stopped = False
        self.update_view()

    @property
    def max_page(self):
        return len(self._pages) - 1

    @property
    def total_pages(self):
        return len(self._pages)

    def update_view(self):
        self.current_page.label = f"Halaman {self._page + 1}/{self.total_pages}"
        self.first_page.disabled = False
        self.prev_page.disabled = False
        self.next_page.disabled = False
        self.last_page.disabled = False
        if self._page == 0:
            self.prev_page.disabled = True
            self.first_page.disabled = True
        if self._page == self.max_page:
            self.next_page.disabled = True
            self.last_page.disabled = True
        if self._is_stopped or self.total_pages == 1:
            self.current_page.disabled = True
            self.first_page.disabled = True
            self.prev_page.disabled = True
            self.next_page.disabled = True
            self.last_page.disabled = True
            self.close_button.disabled = True

    async def _maybe_asyncute(self, cb: callable, *args, **kwargs):
        real_func = cb
        if hasattr(real_func, "func"):
            # Partial function
            real_func = cb.func
        if iscoroutinefunction(real_func):
            return await cb(*args, **kwargs)
        return cb(*args, **kwargs)

    def attach(self, generator: PaginatorGenerator[IT]):
        if not callable(generator):
            raise ValueError("Generator is not a function")
        self._default_gen = generator

    async def interact(self, timeout: Optional[Number] = None):
        """Start interaction with the custom view

        Will generate message if it's none.
        Using internal ctx that are passed by user!
        """
        if timeout is not None:
            self.timeout = timeout
        self.logger.info("Starting interaction...")
        if self.message is None:
            self.logger.warning("Will generate starting message first!")
            kwargs = await self.__generate_view(self.message, None)
            real_kwargs = {}
            if "content" in kwargs:
                real_kwargs["content"] = kwargs["content"]
            if "embed" in kwargs:
                real_kwargs["embed"] = kwargs["embed"]
            self.message = await self.ctx.send(**real_kwargs)
        if self.total_pages == 1:
            self.logger.warning("There's only 1 pages, will not attach view")
        else:
            self.logger.info("Attaching UI View!")
            await self.message.edit(view=self)

    @property
    def current(self):
        return self._pages[self._page]

    def _check_function(self, func: PaginatorGenerator[IT]):
        available_args = []
        sigmaballs = signature(func)
        for param in sigmaballs.parameters.values():
            if param.default != param.empty:
                continue
            available_args.append(param)
        pass_data = pass_position = pass_msg = False
        if len(available_args) == 1:
            pass_data = True
        if len(available_args) == 2:
            pass_data = pass_position = True
        if len(available_args) == 3:
            pass_data = pass_position = pass_msg = True
        return pass_data, pass_position, pass_msg

    @staticmethod
    def __generate_message(generated: GeneratorOutput) -> GeneratedKwargs:
        raw_msg: str = None
        embed: discord.Embed = None
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
        final_kwargs = {}
        if isinstance(raw_msg, str):
            final_kwargs["content"] = raw_msg
        if isinstance(embed, discord.Embed):
            final_kwargs["embed"] = embed
        return final_kwargs

    async def __generate_view(
        self, message: discord.Message, user: Optional[discord.User]
    ) -> GeneratedKwargs:
        if user is not None:
            if user.id != self._author.id:
                self.logger.warning("User is not the same as author, will return current view")
                return {"view": self}
        callback = self._default_gen
        if not callable(callback):
            data = self._pages[self._page]
            kwargs_data = self.__generate_message(data)
            if kwargs_data is None:
                raise PaginationFailure(data, self._page, self)
            kwargs_data["view"] = self
            return kwargs_data
        can_data, can_pos, can_msg = self._check_function(callback)
        full_argument = []
        data = self._pages[self._page]
        if can_data:
            full_argument.append(data)
        if can_pos:
            full_argument.append(self._page)
        if can_msg:
            full_argument.append(message)
        generator = await self._maybe_asyncute(callback, *full_argument)
        final_kwargs = self.__generate_message(generator)
        if final_kwargs is None:
            return {"view": self}
        final_kwargs["view"] = self
        return final_kwargs

    async def interaction_check(self, interaction: Interaction) -> bool:
        return self.ctx.author.id == interaction.user.id

    async def on_timeout(self) -> None:
        self._is_stopped = True
        self.logger.info("Timeout occured, updating view...")
        self.update_view()
        if self.message is not None:
            self.logger.info("Message detected, editing...")
            await self.message.edit(view=self)

    @DisUI.button(label="Awal", emoji="⏮")
    async def first_page(self, button: DisUI.Button, interaction: Interaction):
        self._page = 0
        self.update_view()
        generated = await self.__generate_view(interaction.message, interaction.user)
        await interaction.response.edit_message(**generated)

    @DisUI.button(label="Sebelumnya", emoji="◀")
    async def prev_page(self, button: DisUI.Button, interaction: Interaction):
        self._page -= 1
        if self._page < 0:
            self._page = 0
        self.update_view()
        generated = await self.__generate_view(interaction.message, interaction.user)
        await interaction.response.edit_message(**generated)

    @DisUI.button(label="Halaman 1/1", style=discord.ButtonStyle.primary, disabled=True)
    async def current_page(self, button: DisUI.Button, interaction: Interaction):
        self.update_view()
        generated = await self.__generate_view(interaction.message, interaction.user)
        await interaction.response.edit_message(**generated)

    @DisUI.button(label="Selanjutnya", emoji="▶")
    async def next_page(self, button: DisUI.Button, interaction: Interaction):
        self._page += 1
        if self._page > len(self._pages) - 1:
            self._page = len(self._pages) - 1
        self.update_view()
        generated = await self.__generate_view(interaction.message, interaction.user)
        await interaction.response.edit_message(**generated)

    @DisUI.button(label="Akhir", emoji="⏭")
    async def last_page(self, button: DisUI.Button, interaction: Interaction):
        self._page = len(self._pages) - 1
        self.update_view()
        generated = await self.__generate_view(interaction.message, interaction.user)
        await interaction.response.edit_message(**generated)

    @DisUI.button(label="Tutup", emoji="✅", style=discord.ButtonStyle.danger)
    async def close_button(self, button: DisUI.Button, interaction: Interaction):
        self._is_stopped = True
        self.update_view()
        await interaction.response.edit_message(view=self)
        self.stop()
