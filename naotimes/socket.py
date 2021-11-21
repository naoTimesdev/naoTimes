"""
A simple socket server to receive event and answer back.

This contains internal socket and another one exposed to the internet

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

from __future__ import annotations

import asyncio
import inspect
import logging
import platform
import socket
import traceback
from base64 import b64encode
from dataclasses import dataclass
from inspect import signature
from time import struct_time
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict, Union

import arrow
import orjson
from bson import ObjectId

from .t import T
from .utils import get_indexed

__all__ = ("EventManager", "SocketServer", "ntevent", "ntsocket")


class EventDecoParam(TypedDict):
    name: str
    installed: bool


class SocketDecoParam(EventDecoParam):
    locked: bool


class SServerFunc(Callable[[str, Any], Any]):
    __nt_socket__: Union[SocketDecoParam, List[SocketDecoParam]]
    __func__: SServerFunc
    func: SServerFunc


class EventFunc(Callable[..., None]):
    __nt_event__: Union[EventDecoParam, List[EventDecoParam]]
    __func__: EventFunc
    func: EventFunc


async def maybe_asyncute(func: Union[SServerFunc, EventFunc], *args, **kwargs):
    """
    Try to execute function
    """
    result = func(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


@dataclass
class SocketEvent:
    callback: SServerFunc
    is_auth: bool = True


class SocketServer:
    """
    A simple external socket server
    """

    def __init__(
        self,
        port: int,
        password: Optional[str] = None,
        *,
        logger: Optional[logging.Logger] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        """
        A simple external socket server
        """
        self.logger = logging.getLogger("naoTimes.SocketServer")
        self._server = None
        self._server_lock = False
        self._authenticated_sid = []

        self._event_map: Dict[str, SocketEvent] = {}
        self._loop = loop
        if self._loop is None:
            self._loop = asyncio.get_event_loop()

        self._port = port
        self._password = password

        self._access_logger = logger or logging.getLogger("naoTimes.SocketAccess")
        # Remove parent logger
        self._access_logger.parent = None

        self._INTERNAL_EVENT = ["ping", "authenticate"]
        self._event_map["authenticate"] = SocketEvent(self.on_authenticate)
        self._internal_task = asyncio.Task(self._start_server(), loop=self._loop)

    def log(self, uuid: str, event: str, success: int, data: Any, time: float):
        now = arrow.utcnow().shift(seconds=-time).to("local")
        start_time = now.format("DD[/]MMM[/]YYYY[:]HH[:]mm[:]ss[.]SSS Z")
        body_len = len(orjson.dumps(data))
        fmt_str = f'{uuid} [{start_time}] EVENT "{event}" {success} {body_len} (Done in {time}s)'
        if success == 1:
            self.logger.info(fmt_str)
        elif success == 0:
            self.logger.error(fmt_str)
        elif success == -1:
            self.logger.warning(fmt_str)
        else:
            self.logger.debug(fmt_str)

    async def _start_server(self):
        """
        Start the socket server
        """
        if self._server_lock:
            return
        self.logger.info("Starting socket server...")
        server = await asyncio.start_server(self._handle_message, "0.0.0.0", self._port)
        # Set tcpalive
        if platform.system() == "Linux":
            server.sockets[0].setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 1)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 3)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
        elif platform.system() == "Darwin":
            TCP_KEEPALIVE = 0x10
            server.sockets[0].setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            server.sockets[0].setsockopt(socket.IPPROTO_TCP, TCP_KEEPALIVE, 3)
        elif platform.system() == "Windows":
            server.sockets[0].ioctl(socket.SIO_KEEPALIVE_VALS, (1, 10000, 3000))

        # Get sockname
        addr = server.sockets[0].getsockname()
        self._server_lock = True
        self.logger.info(f"Serving socket server at: {addr[0]}:{addr[1]}")
        self._server = server

        try:
            async with server:
                await server.serve_forever()
        except asyncio.CancelledError:
            self.logger.warning("Got asyncio close request, shutting down...")
            self._server.close()
            await server.wait_closed()
        self.logger.info("Socket server closed.")

    def close(self):
        self._internal_task.cancel()

    @staticmethod
    def _hash_ip(addr):
        if addr is None:
            return "UNKNOWN_UUID"
        if isinstance(addr, (tuple, list)):
            addr = addr[0]
        if not isinstance(addr, str):
            if isinstance(addr, int):
                addr = str(addr)
            else:
                addr = orjson.dumps(addr).decode("utf-8")
        return b64encode(addr.encode("utf-8")).decode("utf-8")

    @staticmethod
    def __parse_json(recv_bytes: bytes):
        if b"\x04" == recv_bytes[-len(b"\x04") :]:
            recv_bytes = recv_bytes[: -len(b"\x04")]
        decoded = recv_bytes.decode("utf-8").strip()
        return orjson.loads(decoded)

    @staticmethod
    def _encode_message(any_data: Any) -> bytes:
        def _OrJsonDefault(obj: Any):
            if isinstance(obj, ObjectId):
                return str(obj)
            elif isinstance(obj, struct_time):
                return list(obj)
            raise TypeError

        if isinstance(any_data, tuple):
            any_data = list(any_data)
        if isinstance(any_data, (list, dict)):
            any_data = orjson.dumps(any_data, default=_OrJsonDefault).decode("utf-8")
        elif isinstance(any_data, (int, float)):
            any_data = str(any_data)
        elif isinstance(any_data, bytes):
            if b"\x04" != any_data[-len(b"\x04") :]:
                any_data = any_data + b"\x04"
            return any_data
        return any_data.encode("utf-8") + b"\x04"

    @staticmethod
    def __create_argument(func: Callable[..., T], sid: str, data: str):
        available_args = []
        sigmaballs = signature(func)
        for param in sigmaballs.parameters.values():
            if param.default != param.empty:
                continue
            available_args.append(param)
        if len(available_args) == 0:
            return []
        if len(available_args) == 1:
            return [sid]
        return [sid, data]

    def _check_auth(self, sid: str) -> bool:
        if self._password is None:
            return True
        return sid in self._authenticated_sid

    # Internal event
    async def on_authenticate(self, sid: str, data: str) -> Union[str, dict]:
        """Function to authenticate, you can override this

        :param sid: the uuid
        :type sid: str
        :param data: the password to compare
        :type data: str
        :return: if success, return string else return dict
        :rtype: Union[str, dict]
        """
        self.logger.info(f"trying to authenticating {sid}, comparing s::{data} and t::{self._password}")
        if self._password is None:
            self._authenticated_sid.append(sid)
            return "ok"
        if data == self._password:
            self.logger.info(f"Authenticated {sid}")
            self._authenticated_sid.append(sid)
            return "ok"
        return {"message": "not ok", "success": 0}

    async def _on_message(self, sid: str, recv_data: Any) -> None:
        parsed = self.__parse_json(recv_data)
        if not isinstance(parsed, dict):
            return {"message": "unknown message received", "success": 0, "event": None}
        event: str = parsed.get("event")
        if event is None:
            return {"message": "unknown event", "success": 0, "event": None}
        event = event.lower()
        if event == "ping":
            return {"message": "pong", "success": 1, "event": event}
        content = parsed.get("data")
        callback = self._event_map.get(event)
        if callback is None:
            # Ignore unknown event
            return {"message": "unknown event, ignored", "success": 1, "event": event}

        is_auth = self._check_auth(sid)
        if callback.is_auth and not is_auth and event != "authenticate":
            auth_key = parsed.get("auth")
            if not auth_key:
                return {"message": "not authenticated", "success": -1, "event": event}
            res = await maybe_asyncute(self.on_authenticate, sid, auth_key)
            if isinstance(res, dict):
                # Auth failed
                res["event"] = event
                return res

        # Try to execute callback
        try:
            generated_args = self.__create_argument(callback.callback, sid, content)
            res = await maybe_asyncute(callback.callback, *generated_args)
        except Exception as e:
            self.logger.exception(e)
            err_msg = "An error occured while trying to execute callback"
            tb = traceback.format_exception(type(e), e, e.__traceback__)
            err_msg += "\n" + "".join(tb)
            return {"message": err_msg, "success": 0, "event": event}
        if isinstance(res, dict):
            msg_success = res.get("message")
            cb_code = res.get("success", 1)
            if msg_success is None:
                if cb_code == 1:
                    msg_success = "ok"
                else:
                    msg_success = "not ok"
            return {"message": msg_success, "success": cb_code, "event": event}
        return {"message": res, "success": 1, "event": event}

    async def _handle_message(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.logger.info("Message received, reading message...")
        start = arrow.utcnow().timestamp()
        uuid = "UNKNOWN_UUID"
        answer = {"message": "An unknown error occured", "success": 0}
        try:
            data = await reader.readuntil(b"\x04")
            addr = writer.get_extra_info("peername")
            uuid = self._hash_ip(addr)
            answer = await self._on_message(uuid, data)
        except asyncio.IncompleteReadError:
            self.logger.error("incomplete data acquired")
            answer = {"message": "incomplete data received", "success": 0}
        writer.write(self._encode_message(answer))
        event_name = answer.get("event", "UNKNOWN")
        self.logger.info(f"answering back request to {uuid} on event {event_name}")
        await writer.drain()
        end = arrow.utcnow().timestamp()
        # Log access
        self.log(uuid, event_name, answer["success"], answer, end - start)
        writer.close()

    def _bind_function_attr(
        self, bind_this: SServerFunc, name: str, lock: bool = True, installed: bool = True
    ):
        original_attr = getattr(bind_this, "__nt_socket__", None)
        socket_info = {
            "name": name,
            "installed": installed,
            "locked": lock,
        }
        if original_attr is not None:
            if isinstance(original_attr, list):
                socket_info_temp = []
                for ori in original_attr:
                    if ori["name"] == name:
                        socket_info["name"] = ori["name"]
                        socket_info["locked"] = ori["locked"]
                        socket_info_temp.append(socket_info)
                    else:
                        socket_info_temp.append(ori)
                socket_info = socket_info_temp
            else:
                socket_info["name"] = original_attr["name"]
                socket_info["locked"] = original_attr["locked"]

        if hasattr(bind_this, "__func__"):
            # Bound method
            bind_this.__func__.__nt_socket__ = socket_info
        else:
            # function
            bind_this.__nt_socket__ = socket_info

    # Function to bind
    def on(self, event: str, callback: Union[SServerFunc, Tuple[SServerFunc, bool], SocketEvent]) -> None:
        """Bind an event to a callback"""
        event = event.lower()
        if event in self._INTERNAL_EVENT:
            raise ValueError(f"{event} is a reserved event")
        if event in self._event_map:
            self.logger.warning(f"overriding event {event}")
        if callable(callback):
            self._bind_function_attr(callback, event)
            self._event_map[event] = SocketEvent(callback)
        elif isinstance(callback, (tuple, list)):
            first_data = callback[0]
            second_data = callback[1]
            if isinstance(first_data, bool) and callable(second_data):
                self._bind_function_attr(second_data, event, first_data)
                self._event_map[event] = SocketEvent(second_data, first_data)
            elif isinstance(second_data, bool) and callable(first_data):
                self._bind_function_attr(first_data, event, second_data)
                self._event_map[event] = SocketEvent(first_data, second_data)
        elif isinstance(callback, SocketEvent):
            self._bind_function_attr(callback.callback, event, callback.is_auth)
            self._event_map[event] = callback

    def off(self, event: str) -> None:
        """Unbind event, if it's doesnt exist log and do nothing"""
        event = event.lower()
        if event not in self._event_map:
            self.logger.warning(f"event {event} not found, ignoring...")
            return
        self.logger.warning(f"unbinding event {event}")
        evcb = self._event_map[event].callback
        self._bind_function_attr(evcb, event, installed=False)
        del self._event_map[event]


class EventManager:
    """A simple event manager to dispatch a event to another cogs"""

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """A simple event manager to dispatch a event to another cogs"""
        self.logger = logging.getLogger("naoTimes.EventManager")
        self._event_map: Dict[str, List[EventFunc]] = {}

        self._loop = loop or asyncio.get_event_loop()
        self._blocking = False

    async def _run_wrap_event(self, coro: SServerFunc, *args: Any, **kwargs: Any) -> None:
        try:
            await maybe_asyncute(coro, *args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.exception("An exception occured while trying to execute callback:", exc_info=e)

    def _internal_scheduler(self, event_name: str, coro: SServerFunc, *args, **kwargs):
        wrapped = self._run_wrap_event(coro, *args, **kwargs)
        return asyncio.create_task(wrapped, name=f"naoTimesEvent: {event_name}")

    async def close(self):
        self._blocking = True
        task_retriever = asyncio.all_tasks
        tasks = {
            t
            for t in task_retriever(loop=self._loop)
            if not t.done() and t.get_name().startswith("naoTimesEvent:")
        }
        if not tasks:
            return
        self.logger.info("Trying to cleanup %d event tasks...", len(tasks))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.logger.info("All event tasks is finished...")
        for task in tasks:
            if task.cancelled():
                continue
            if task.exception() is not None:
                self.logger.error(
                    "An exception occured while trying to cancel event task:", exc_info=task.exception()
                )

    def __extract_event(self, event: str):
        event = event.lower()
        extracted = event.split("_")
        if len(extracted) < 2:
            return event, None
        last_one = extracted[-1]
        if last_one.isdigit():
            digit = int(extracted.pop())
            return "_".join(extracted), digit
        return event, None

    def __find_callback(self, event: str, numbering: int = None):
        event_map = []
        is_realfn = False
        if event not in self._event_map:
            if "realfn_" + event not in self._event_map:
                return None
            else:
                event_map = self._event_map["realfn_" + event]
                is_realfn = True
        else:
            event_map = self._event_map[event]

        if is_realfn:
            return event_map[0]

        if numbering is not None:
            callback = get_indexed(event_map, numbering)
            if callback is not None:
                return callback
            return None

        return event_map

    def __create_kwarguments(self, callback: EventFunc, *args, **kwargs):
        valid_kwargs = {}
        missing_kwargs = []
        sigmaballs = signature(callback)
        for idx, param in enumerate(sigmaballs.parameters.values()):
            kw = kwargs.get(param.name)
            if param.default != param.empty:
                if kw is not None:
                    valid_kwargs[param.name] = kw
                else:
                    valid_kwargs[param.name] = param.default
                continue

            args_index = get_indexed(args, idx)
            if args_index is not None:
                valid_kwargs[param.name] = args_index
            else:
                missing_kwargs.append(
                    {
                        "index": idx,
                        "name": param.name,
                    }
                )

        if len(missing_kwargs) > 0:
            return False, None

        return True, valid_kwargs

    def dispatch(self, event: str, *args, **kwargs) -> None:
        """Dispatch an event to all registered callbacks"""
        if self._blocking:
            # The event is shutting down, dont try to add more dispatch
            return
        event, digit = self.__extract_event(event)
        callbacks = self.__find_callback(event, digit)
        if callbacks is None:
            self.logger.warning(f"event {event} not found, ignoring...")
            return

        if isinstance(callbacks, list):
            for callback in callbacks:
                self.logger.info(f"Trying to dispatch event: {event}, callback: {callback}")
                valid, real_kwargs = self.__create_kwarguments(callback, *args, **kwargs)
                if not valid:
                    continue
                self._internal_scheduler(event, callback, *[], **real_kwargs)
        else:
            self.logger.info(f"Trying to dispatch event: {event}, callback: {callbacks}")
            valid, real_kwargs = self.__create_kwarguments(callbacks, *args, **kwargs)
            if valid:
                self._internal_scheduler(event, callbacks, *[], **real_kwargs)

    @staticmethod
    def __extract_fn_name(fn: EventFunc):
        def _naming():
            if hasattr(fn, "func"):
                return fn.func.__name__
            return fn.__name__

        name = _naming()

        if name == "<lambda>":
            return f"lambda_{hash(fn)}"
        return name

    def _bind_function_attr(self, bind_this: EventFunc, name: str, installed: bool = True):
        original_attr = getattr(bind_this, "__nt_event__", None)
        event_info = {
            "name": name,
            "installed": installed,
        }

        if original_attr is not None:
            if isinstance(original_attr, list):
                event_info_temp = []
                for ori in original_attr:
                    if ori["name"] == name:
                        event_info["name"] = ori["name"]
                        event_info_temp.append(event_info)
                    else:
                        event_info_temp.append(ori)
                event_info = event_info_temp
            else:
                event_info["name"] = original_attr["name"]

        if hasattr(bind_this, "__func__"):
            # Bound method
            bind_this.__func__.__nt_event__ = event_info
        else:
            # function
            bind_this.__nt_event__ = event_info

    def on(self, event: str, callback: EventFunc) -> None:
        """Bind an event to a callback"""
        event = event.lower()
        if event.startswith("realfn_"):
            raise ValueError("Cannot use `realfn_` as starting event name because it's reserved!")
        event_map = self._event_map.get(event, [])
        self._bind_function_attr(callback, event)
        event_map.append(callback)
        fn_name = self.__extract_fn_name(callback)
        self._event_map[event] = event_map
        self._event_map["realfn_" + fn_name] = [callback]

    def off(self, event: str) -> None:
        """Unbind event, if it's doesnt exist log and do nothing"""
        event = event.lower()
        if event not in self._event_map:
            self.logger.warning(f"event {event} not found, ignoring...")
            return
        self.logger.warning(f"unbinding event {event}")
        event_list = self._event_map[event]
        for evcb in event_list:
            self._bind_function_attr(evcb, event, False)
        del self._event_map[event]


def _check_for_existing_name(old_event: List[EventDecoParam], name: str):
    for event in old_event:
        if event["name"] == name:
            return True
    return False


def ntevent(name: str = None):
    """Decorator to mark a function as a ntevent function.

    Parameters
    ------------
    name: Optional[:class:`str`]
        The name of the event. If not provided, the function name will be used.
    """

    def event_deco(fn: EventFunc):
        _internal_name = fn.__name__
        if _internal_name.startswith("on_"):
            _internal_name = _internal_name[3:]
        use_name = name or _internal_name
        old_event = getattr(fn, "__nt_event__", None)
        if old_event is not None:
            event_info = []
            if isinstance(old_event, list):
                event_info = old_event
            else:
                event_info.append(old_event)
            if _check_for_existing_name(event_info, name):
                if name is None:
                    raise ValueError("It's required to provide name parameter if you stack multiple @ntevent")
                else:
                    raise ValueError(f"Cannot use the event name {use_name} since it already exist!")
            event_info.append({"name": use_name, "installed": False})
            fn.__nt_event__ = event_info
        else:
            fn.__nt_event__ = {
                "name": use_name,
                "installed": False,
            }
        return fn

    return event_deco


def ntsocket(name: str = None, locked: bool = True):
    """Decorator to mark a function as a ntsocket function.

    Parameters
    ------------
    name: Optional[:class:`str`]
        The name of the event. If not provided, the function name will be used.
    locked: Optional[:class:`bool`]
        If ``True``, the function will be marked as authentication needed.
    """

    def socket_deco(fn: SServerFunc):
        _internal_name = fn.__name__
        if _internal_name.startswith("on_"):
            _internal_name = _internal_name[3:]
        use_name = name or _internal_name
        old_event = getattr(fn, "__nt_socket__", None)
        if old_event is not None:
            event_info = []
            if isinstance(old_event, list):
                event_info = old_event
            else:
                event_info.append(old_event)
            if _check_for_existing_name(event_info, use_name):
                if name is None:
                    raise ValueError(
                        "It's required to provide name parameter if you stack multiple @ntsocket"
                    )
                else:
                    raise ValueError(f"Cannot use the event name {use_name} since it already exist!")
            event_info.append({"name": use_name, "installed": False, "locked": locked})
            fn.__nt_socket__ = event_info
        else:
            fn.__nt_socket__ = {
                "name": use_name,
                "installed": False,
                "locked": locked,
            }
        return fn

    return socket_deco
