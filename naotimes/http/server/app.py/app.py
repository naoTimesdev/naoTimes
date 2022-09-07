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
from base64 import b64encode
from functools import partial as ftpartial
from functools import update_wrapper
from typing import Dict, List, Optional

import aiohttp
import arrow
from aiohttp import web
from aiohttp.abc import AbstractAccessLogger, AbstractMatchInfo

from .routes import Route, RouteMethod

__all__ = ("naoTimesHTTPServer",)


class RouteAlreadyRegistered(Exception):
    def __init__(self, route: Route):
        self.route: Route = route
        super().__init__(
            f"Route {route.path} is already registered/exists on the webserver, please choose another path."
        )


def _hash_ip(addr: str):
    if addr is None:
        return "-"
    return b64encode(addr.encode("utf-8")).decode("utf-8")


class naoTimesAccessLogger(AbstractAccessLogger):
    @staticmethod
    def _format_request(request: web.Request, time: float) -> str:
        ip_req = request.remote
        ip = _hash_ip(ip_req)
        now = arrow.utcnow().shift(seconds=-time).to("local")
        start_time = now.format("DD[/]MMM[/]YYYY[:]HH[:]mm[:]ss[.]SSS Z")
        return f'{ip} [{start_time}] "{request.method} {request.path}"'

    @staticmethod
    def _format_response(response: web.Response, time: float) -> str:
        return f"{response.status} {response.body_length} (Done in {time:.2f}s)"

    def log(self, request: web.Request, response: web.StreamResponse, time: float):
        r = self._format_request(request, time)
        rp = self._format_response(response, time)
        http = response.status
        if http >= 400:
            self.logger.error(f"{r} {rp}")
        elif http >= 300 < 400:
            self.logger.warning(f"{r} {rp}")
        elif http >= 200 < 300:
            self.logger.info(f"{r} {rp}")
        else:
            self.logger.debug(f"{r} {rp}")


class naoTimesHTTPServer:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 25671,
        password: Optional[str] = None,
        *,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logging.getLogger("naoTimes.HTTPServer")
        self.host: str = host
        self.port: int = port
        self.password: Optional[str] = password
        self.loop = asyncio.get_event_loop()

        self._request_path: Dict[str, Route] = {}

        self.__internal_task: Optional[asyncio.Task] = None

        # Monkeypatch it
        web.Application._handle = self._handle_request
        self._access_logger = logger or logging.getLogger("naoTimes.HTTPAccess")
        # Remove parent root logger.
        self._access_logger.parent = None

        self.__internal_app: web.Application = web.Application(loop=self.loop)
        self.__internal_runner: Optional[web.AppRunner] = None

    @property
    def app(self):
        return self.__internal_app

    async def _health_ping(self, _: web.Request):
        return web.json_response({"status": "ok"})

    async def internal_start(self):
        self.logger.info("Preparing extra routes...")
        self.__internal_app.add_routes([web.get("/_/health", self._health_ping)])
        self.logger.info("Preparing web app runner...")
        runner = web.AppRunner(
            self.__internal_app,
            access_log=self._access_logger,
            access_log_class=naoTimesAccessLogger,
            handle_signals=False,
        )
        self.logger.info("Creating server for web application!")
        await runner.setup()
        self.logger.info("App runner prepared.")
        self.__internal_runner = runner
        site = web.TCPSite(runner, self.host, self.port)
        self.logger.info(f"Starting HTTP server at {self.host}:{self.port} ...")
        await site.start()

    async def start(self):
        """
        Internally start the server.
        """
        ctime = arrow.utcnow().int_timestamp
        self.__internal_task = asyncio.create_task(
            self.internal_start(), name=f"naotimes-webserver-{self.host}:{self.port}_{ctime}"
        )
        self.__internal_task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task):
        exception = task.exception()
        if exception is not None:
            self.logger.error(f"Task {task.get_name()} failed: {exception}", exc_info=exception)
            return
        self.logger.info(f"Task {task.get_name()} finished.")

    async def close(self):
        """
        Internally close the server.
        """
        if self.__internal_runner:
            await self.__internal_runner.cleanup()
        if self.__internal_task:
            self.__internal_task.cancel()
            await self.__internal_task

    async def _handle_auth_headers(self, request: web.Request):
        if request.version != aiohttp.HttpVersion11:
            return

        auth_header = request.headers.get("Authorization")
        if auth_header is None:
            raise web.HTTPUnauthorized(reason="Missing Authorization header")
        elif auth_header.startswith("Password "):
            password = auth_header.split(" ")[1]
            if password != self.password:
                raise web.HTTPForbidden(reason="Invalid authorization password")
        else:
            raise web.HTTPForbidden(
                reason="Invalid authorization data format, must be prefixed with Password"
            )

        request.transport.write(b"HTTP/1.1 100 Continue\r\n\r\n")

    async def _handle_request(self, app: web.Application, request: web.Request) -> web.StreamResponse:
        """
        Handle a request.
        """

        loop = asyncio.get_event_loop()
        debug = loop.get_debug()
        match_info = await app._router.resolve(request)
        if debug:  # pragma: no cover
            if not isinstance(match_info, AbstractMatchInfo):
                raise TypeError(
                    "match_info should be AbstractMatchInfo instance, not {!r}".format(match_info)
                )
        match_info.add_app(self.__internal_app)
        match_info.freeze()

        resp = None
        request._match_info = match_info
        expect = request.headers.get(aiohttp.hdrs.EXPECT)
        if expect:
            resp = await match_info.expect_handler(request)
            await request.writer.drain()

        if resp is None:
            handler = match_info.handler

            if app._run_middlewares:
                for app in match_info.apps[::-1]:
                    for m, new_style in app._middlewares_handlers:  # type: ignore[union-attr] # noqa
                        if new_style:
                            handler = update_wrapper(ftpartial(m, handler=handler), handler)
                        else:
                            handler = await m(app, handler)  # type: ignore[arg-type]

            canon_route = match_info.route.resource
            if canon_route is not None:
                canon_route = canon_route.canonical
            method_path = self._request_path.get(canon_route)

            request_data = [request]
            if method_path and method_path.cog:
                request_data.insert(0, method_path.cog)

            resp = await handler(*request_data)

        self.logger.info(f"[WEB-LOG] {request.method} {request.path} {resp.status}")
        return resp

    def add_route(self, route: Route):
        """An overly complex method to add/replace route for the webserver.

        Parameters
        -----------
        route: :class:`Route`
            The route to be added or replaced if it's exist.

        Raises
        --------
        RouteAlreadyRegistered
            If the route is already registered.
            This will not be raised if the route you give already marked as injected.

            Please do not manually set it to ``True``.
        """
        idx_resource = -1
        for idx, resource in enumerate(self.__internal_app.router._resources):
            if isinstance(resource, web.PlainResource):
                if resource._path == route.path:
                    idx_resource = idx
                    break
            elif isinstance(resource, web.DynamicResource):
                if resource.canonical == route.path:
                    idx_resource = idx
                    break
        if idx_resource == -1:
            # If no match, add new route
            for method in route.method:
                if self.password is not None and route.with_auth:
                    self.__internal_app.router.add_route(
                        method.value, route.path, route.handler, expect_handler=self._handle_auth_headers
                    )
                else:
                    self.__internal_app.router.add_route(method.value, route.path, route.handler)
            route.has_injected = True
            self._request_path[route.path] = route
            return

        _old_data = self._request_path.get(route.path)
        if _old_data is not None:
            if idx_resource != -1 and _old_data.has_injected:
                # If something matched the route, replace the handler.
                # This is very useful if cog are reloaded.
                resource_route: web.Resource = self.__internal_app.router._resources[idx_resource]
                untouched_method: List[RouteMethod] = []
                for method in route.method:
                    r_mod = -1
                    for i_mod, mod in enumerate(resource_route._routes):
                        if mod.method == method.value:
                            r_mod = i_mod
                            break
                    if r_mod != -1:
                        resource_route._routes[r_mod]._handler = route.handler
                        # Check if we need to inject authentication expect checking.
                        if self.password is not None and route.with_auth:
                            resource_route._routes[r_mod]._expect_handler = self._handle_auth_headers
                        else:
                            resource_route._routes[r_mod]._expect_handler = None
                    else:
                        # Add to method that are missing and need to be added.
                        untouched_method.append(method)
                available_method = [m.value for m in route.method]
                # Check what method need to be removed.
                # Removed from the provided route, and exist in resource
                cleaned_routes: List[web.ResourceRoute] = []
                for route in resource_route._routes:
                    if route.method in available_method:
                        cleaned_routes.append(route)
                # Replace with all route that are actually need to be added.
                resource_route._routes = cleaned_routes
                # Register the current new routes.
                self.__internal_app.router._resources[idx_resource] = resource_route
                # Check what method need to be added, and inject it.
                for untouched in untouched_method:
                    if self.password is not None and route.with_auth:
                        self.__internal_app.router.add_route(
                            untouched.value,
                            route.path,
                            route.handler,
                            expect_handler=self._handle_auth_headers,
                        )
                    else:
                        self.__internal_app.router.add_route(
                            untouched.value,
                            route.path,
                            route.handler,
                        )
                return
        raise RouteAlreadyRegistered(route)
