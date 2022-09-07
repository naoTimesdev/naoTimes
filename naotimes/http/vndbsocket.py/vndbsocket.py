"""
A simple wrapper for VNDB socket API.
Based on PyMoe implementation here:
https://github.com/ccubed/PyMoe/blob/master/Pymoe/VNDB/connection.py

This implemenation are mostly focused on asynchronous support.

---

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

import asyncio
import logging
import socket
import ssl
from typing import Any, Dict, Optional, Union

import orjson
from discord.backoff import ExponentialBackoff

__all__ = ("VNDBSockIOManager",)


class VNDBSockIOManager:
    """
    Asynchronous VNDB Socket Connection manager.
    This was made since everything needs async connection, help me.

    Code inspiration taken from:
    https://github.com/ccubed/PyMoe/blob/master/Pymoe/VNDB/connection.py

    The changes are now using asyncio Streams instead normal SSL Sock.
    """

    def __init__(self, username: str, password: str, loop: asyncio.AbstractEventLoop = None):
        self.sslcontext: ssl.SSLContext = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        self.sslcontext.verify_mode = ssl.CERT_REQUIRED
        self.sslcontext.check_hostname = True
        self.sslcontext.load_default_certs()

        self.clientvars: Dict[str, Any] = {"protocol": 1, "clientver": 2.0, "client": "naoTimes"}
        self._username: str = username
        self._password: str = password
        self.logger = logging.getLogger("naoTimes.VNDBSocket")

        self.loggedin: bool = False
        self.data_buffer = bytes(1024)

        self.loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()
        self._reconnection_lock: asyncio.Event = asyncio.Event()
        self._reconnect_backoff: ExponentialBackoff = ExponentialBackoff(integral=True)

        self._closing: bool = False

        self._sock_reader: asyncio.StreamReader = None
        self._sock_writer: asyncio.StreamWriter = None

    async def initialize(self):
        self.logger.info("initiating new connection...")
        if self._closing:
            self.logger.warning("Closing flag is set, not initializing connection.")
            return False
        reader, writer = await asyncio.open_connection(
            "api.vndb.org", 19535, family=socket.AF_INET, ssl=self.sslcontext
        )
        self._sock_reader: asyncio.StreamReader = reader
        self._sock_writer: asyncio.StreamWriter = writer
        return True

    async def _check_connection(self):
        """
        Checks if the connection is still alive.
        """
        if self._sock_writer.is_closing():
            self.logger.warning("Connection is closing, waiting for it to close...")
            if self._reconnection_lock.is_set():
                self.logger.warning("Reconnection lock is set, waiting for it to clear...")
                await self._reconnection_lock.wait()
                self.logger.warning("Reconnection lock cleared, marking connection as alive.")
                return
            # Connection is closing or closed.
            # Reinitialize the connection.
            await self._sock_writer.wait_closed()
            self._reconnection_lock.set()
            # Reconnect indefinitely, retry with backoff.
            self.logger.warning("Connection is closed, reconnecting...")
            while True:
                success = await self.reconnect()
                if success is None:
                    self.logger.warning("Reconnection cancelled, since bot is closing.")
                    break
                if success:
                    self.logger.warning("Reconnection successful, marking connection as alive.")
                    self._reconnection_lock.clear()
                    break
                delay_by = self._reconnect_backoff.delay()
                self.logger.warning(f"Reconnection failed, trying again in {delay_by} seconds.")
                await asyncio.sleep(delay_by)

    async def close(self):
        self.logger.warning("emptying reader...")
        self._closing = True
        self._reconnection_lock.set()
        self._sock_writer.close()

    async def login(self):
        finvars = self.clientvars
        if self._username and self._password:
            finvars["username"] = self._username
            finvars["password"] = self._password
            self.logger.info(f"Trying to login with username {self._username}")
            ret = await self.send_command("login", orjson.dumps(finvars).decode("utf-8"))
            if not isinstance(ret, str) and self.loggedin:  # should just be 'Ok'
                self.loggedin = False
            self.loggedin = True

    async def reconnect(self):
        """
        Reconnects to the VNDB socket.
        """
        # If it's closing, wait until closed fully.
        await self._sock_writer.wait_closed()
        self.loggedin = False
        should_continue = await self.initialize()
        if not should_continue:
            return None
        try:
            await asyncio.wait_for(self.login(), timeout=10.0)
        except asyncio.TimeoutError:
            self.logger.error("Failed to login, connection timeout after 10 seconds.")
            self.loggedin = False
            return False
        return True

    async_login = login

    async def send_command(self, command: str, args: Optional[Union[str, dict]] = None) -> Dict[str, Any]:
        """
        Send a command to VNDB and then get the result.
        :param command: What command are we sending
        :param args: What are the json args for this command
        :return: Servers Response
        :rtype: Dictionary (See D11 docs on VNDB)
        """
        if self._sock_writer is None:
            raise ValueError("VNDBSockIOManager is not yet initalized yet, please use initialize() first.")
        if args:
            if isinstance(args, str):
                final_command = command + " " + args + "\x04"
            else:
                # We just let orjson propogate the error here
                # if it can't parse the arguments
                final_command = command + " " + orjson.dumps(args).decode("utf-8") + "\x04"
        else:
            final_command = command + "\x04"
        await self._check_connection()
        self.logger.debug(f"Sending: {command} command")
        self._sock_writer.write(final_command.encode("utf-8"))
        await self._sock_writer.drain()
        return await self._read_data()

    send_command_async = send_command

    async def _read_data(self) -> Dict[str, Any]:
        """
        Receieves data until we reach the \x04 and then returns it.
        :return: The data received
        """
        temp = ""
        while not self._sock_reader.at_eof():
            if self._sock_reader.at_eof():
                break
            try:
                self.data_buffer = await self._sock_reader.read(1024)
            except asyncio.IncompleteReadError as aio_incomplete:
                self.data_buffer = aio_incomplete.partial
            if "\x04" in self.data_buffer.decode("utf-8", "ignore"):
                temp += self.data_buffer.decode("utf-8", "ignore")
                break
            temp += self.data_buffer.decode("utf-8", "ignore")
            self.data_buffer = bytes(1024)
        temp = temp.replace("\x04", "")
        # self._sock_writer.close()
        if "ok" in temp.lower():  # because login
            return temp
        return orjson.loads(temp.split(" ", 1)[1])
