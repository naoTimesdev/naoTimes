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

from typing import TYPE_CHECKING, Any

import orjson
from aiohttp.web import Response, json_response

if TYPE_CHECKING:
    from aiohttp.typedefs import LooseHeaders

__all__ = (
    "empty_response",
    "orjson_response",
)


def orjson_response(
    data: Any,
    *,
    text: str | None = None,
    body: bytes | None = None,
    status: int = 200,
    reason: str | None = None,
    headers: LooseHeaders | None = None,
    content_type: str = "application/json",
    orjson_option: int = orjson.OPT_INDENT_2,
) -> Response:
    """
    A helper function to return a JSON response.
    This is a wrapper around aiohttp's json_response function.

    This uses orjson to serialize the data.
    """
    return json_response(
        data,
        text=text,
        body=body,
        status=status,
        reason=reason,
        headers=headers,
        content_type=content_type,
        dumps=lambda x: orjson.dumps(x, option=orjson_option).decode("utf-8"),
    )


def empty_response(code: int = 204):
    """Send an empty response/no body.

    You can try to use the following code:
    - `201` Created
    - `204` No Content
    """
    return Response(status=code)
