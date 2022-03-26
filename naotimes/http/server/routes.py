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

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, List, Optional, Protocol, Union

from aiohttp.web import Request as WebRequest
from aiohttp.web import StreamResponse
from disnake.ext.commands.cog import Cog

__all__ = ("Route", "RouteMethod", "get", "post", "put", "patch", "delete", "head", "route")


class RouteMethod(Enum):
    HEAD = "HEAD"
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class WrappedHandlerWithRoute(Protocol):
    __nt_webserver_route__: Route
    __func__: WrappedHandlerWithRoute
    func: WrappedHandlerWithRoute

    def __call__(self, request: WebRequest) -> Awaitable[StreamResponse]:
        ...


@dataclass
class Route:
    """Represent a single route"""

    path: str
    method: List[RouteMethod]
    handler: Callable[[WebRequest], Awaitable[StreamResponse]]
    with_auth: bool = False
    has_injected: bool = False
    cog: Optional[Cog] = None

    def __post_init__(self):
        if not self.path.startswith("/"):
            self.path = "/" + self.path

    def bind_cog(self, cog: Cog):
        self.cog = cog
        # Get route prefix from class
        suffix_attr = "http_route_prefix"
        matching_attr = None
        for attr in dir(cog):
            if attr.casefold().endswith(suffix_attr):
                fetch_attr = getattr(cog, attr, None)
                if isinstance(fetch_attr, str):
                    matching_attr = fetch_attr
                    break

        if matching_attr is not None:
            if not matching_attr.startswith("/"):
                matching_attr = "/" + matching_attr

            # Join route path with prefix path
            if matching_attr.endswith("/") and self.path.startswith("/"):
                self.path = matching_attr + self.path[1:]
            elif matching_attr.endswith("/") and not self.path.startswith("/"):
                self.path = matching_attr + self.path
            elif not matching_attr.endswith("/") and self.path.startswith("/"):
                self.path = matching_attr + self.path


def get(
    path: str, *, with_auth: bool = False
) -> Callable[[WrappedHandlerWithRoute], WrappedHandlerWithRoute]:
    """Decorator for GET routes"""

    def decorator(handler: WrappedHandlerWithRoute):
        handler.__nt_webserver_route__ = Route(path, [RouteMethod.GET], handler, with_auth)
        return handler

    return decorator


def post(
    path: str, *, with_auth: bool = False
) -> Callable[[WrappedHandlerWithRoute], WrappedHandlerWithRoute]:
    """Decorator for POST routes"""

    def decorator(handler: WrappedHandlerWithRoute):
        handler.__nt_webserver_route__ = Route(path, [RouteMethod.POST], handler, with_auth)
        return handler

    return decorator


def put(
    path: str, *, with_auth: bool = False
) -> Callable[[WrappedHandlerWithRoute], WrappedHandlerWithRoute]:
    """Decorator for PUT routes"""

    def decorator(handler: WrappedHandlerWithRoute):
        handler.__nt_webserver_route__ = Route(path, [RouteMethod.PUT], handler, with_auth)
        return handler

    return decorator


def patch(
    path: str, *, with_auth: bool = False
) -> Callable[[WrappedHandlerWithRoute], WrappedHandlerWithRoute]:
    """Decorator for PATCH routes"""

    def decorator(handler: WrappedHandlerWithRoute):
        handler.__nt_webserver_route__ = Route(path, [RouteMethod.PATCH], handler, with_auth)
        return handler

    return decorator


def delete(
    path: str, *, with_auth: bool = False
) -> Callable[[WrappedHandlerWithRoute], WrappedHandlerWithRoute]:
    """Decorator for DELETE routes"""

    def decorator(handler: WrappedHandlerWithRoute):
        handler.__nt_webserver_route__ = Route(path, [RouteMethod.DELETE], handler, with_auth)
        return handler

    return decorator


def head(
    path: str, *, with_auth: bool = False
) -> Callable[[WrappedHandlerWithRoute], WrappedHandlerWithRoute]:
    """Decorator for HEAD routes"""

    def decorator(handler: WrappedHandlerWithRoute):
        handler.__nt_webserver_route__ = Route(path, [RouteMethod.HEAD], handler, with_auth)
        return handler

    return decorator


def route(
    path: str, *, method: Union[RouteMethod, List[RouteMethod], str, List[str]] = [], with_auth: bool = False
) -> Callable[[WrappedHandlerWithRoute], WrappedHandlerWithRoute]:
    """Decorator for any routes"""

    def decorator(handler: WrappedHandlerWithRoute):
        pp_method = []
        if not isinstance(method, list):
            pp_method.append(method)
        else:
            pp_method = method
        actual_method = []
        for meth in pp_method:
            if isinstance(meth, str):
                actual_method.append(RouteMethod(meth.upper()))
            else:
                actual_method.append(meth)
        if not actual_method:
            actual_method = [
                RouteMethod.GET,
                RouteMethod.HEAD,
                RouteMethod.POST,
                RouteMethod.PUT,
                RouteMethod.DELETE,
                RouteMethod.PATCH,
            ]
        handler.__nt_webserver_route__ = Route(path, actual_method, handler, with_auth)
        return handler

    return decorator
