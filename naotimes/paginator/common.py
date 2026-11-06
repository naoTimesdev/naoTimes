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

from collections.abc import Callable, Coroutine
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypedDict,
    TypeVar,
    Union,
)

from discord import Embed, Message
from discord.ui import View

if TYPE_CHECKING:
    from .react import DiscordPaginator
    from .uiv2 import DiscordPaginatorUI


T = TypeVar("T")
IT = TypeVar("IT")
GeneratorOutput = Union[
    tuple[Embed, str],
    tuple[str, Embed],
    tuple[Any, ...],
    list[Any],
    Embed,
    str,
    int,
    float,
    View,
]
PaginatorT = TypeVar("PaginatorT", bound="DiscordPaginator | DiscordPaginatorUI")

PaginatorGenerator = Callable[..., GeneratorOutput | Coroutine[Any, Any, GeneratorOutput]]

__all__ = ("PaginationFailure",)


class GeneratedKwargs(TypedDict, total=False):
    view: View
    message: Message
    embed: Embed


class PaginationFailure(Exception, Generic[IT, PaginatorT]):
    """Raised when pagination fails"""

    def __init__(self, content: IT, position: int, paginator: PaginatorT):
        self.content = content
        self.position = position
        self.paginator = paginator

        paginator_name = self.paginator.__class__.__name__
        super().__init__(f"Failed to paginate page {self.position} in paginator {paginator_name}")


PaginatorValidator = Callable[[IT], bool]
