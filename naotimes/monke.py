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

from typing import Optional

import discord.message
from discord.enums import MessageType

__all__ = ("monkeypatch_message_delete",)


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

    discord.message.Message.delete = delete_strategy
