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

from typing import TYPE_CHECKING

import discord
from discord.ui import View

if TYPE_CHECKING:
    from naotimes.context import naoTimesContext

__all__ = ("ConfirmView",)


class ConfirmView(View):
    def __init__(self, ctx: naoTimesContext, *, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return self.ctx.author.id == interaction.user.id

    async def _disable(self, inter: discord.Interaction):
        # Disable other button
        for button in self.children:
            if isinstance(button, discord.ui.Button):
                button.disabled = True
        await inter.response.edit_message(view=self)

    @discord.ui.button(label="Ya", style=discord.ButtonStyle.green)
    async def confirm(self, button: discord.Button, interaction: discord.MessageInteraction):
        self.value = True
        await self._disable(interaction)
        self.stop()

    @discord.ui.button(label="Tidak", style=discord.ButtonStyle.grey)
    async def cancel(self, button: discord.ui.Button, interaction: discord.MessageInteraction):
        self.value = False
        await self._disable(interaction)
        self.stop()
