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

from typing import Optional

from discord.ext.commands import Context

__all__ = ("PlaceHolderCommand",)


class PlaceHolderCommand:
    """
    A placeholder command for disabled, it replaced with a simple text

    Usage:
    ```py
    # Initialize first the class, then pass the send_placeholder command

    plch_cmd = PlaceHolderCommand(name="kbbi", reason="Website sangat tidak stabil untuk digunakan.")
    bot.add_command(commands.Command(plch_cmd.send_placeholder, name="kbbi"))
    ```
    """

    def __init__(self, name: str, reason: Optional[str] = None):
        """Initialize the PlaceHolderCommand class

        :param name: command name
        :type name: str
        :param reason: reason why that command is being disabled, or replaced by placeholder, defaults to None
        :type reason: Optional[str], optional
        """
        self.name = name
        self.reason = reason

        self._custom_text = None
        self._original_function = None

    def set_custom(self, custom: str):
        self._custom_text = custom

    def clear_custom(self):
        self._custom_text = None

    def bind(self, callback: callable):
        self._original_function = callback
        setattr(self.send_placeholder, "__nt_placeholder__", callback)

    @property
    def original(self):
        return self._original_function

    async def send_placeholder(self, ctx: Context):
        """Send a placeholder message to the user"""
        if self._custom_text is not None:
            return await ctx.send(self._custom_text)
        send_msg = f"Perintah **`{self.name}`** dinon-aktifkan oleh owner bot ini."
        if self.reason is not None and self.reason != "":
            send_msg += f"\n**Alasan**: {self.reason}"
        await ctx.send(send_msg)
