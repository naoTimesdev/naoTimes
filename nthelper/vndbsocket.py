import asyncio
import logging
import socket
import ssl

import ujson


class VNDBSockIOManager:
    """
    Asynchronous VNDB Socket Connection manager.
    This was made since everything needs async connection, help me.

    Code inspiration taken from:
    https://github.com/ccubed/PyMoe/blob/master/Pymoe/VNDB/connection.py

    The changes are now using asyncio Streams instead normal SSL Sock.
    """

    def __init__(self, username, password, loop=None):
        self.sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        self.sslcontext.verify_mode = ssl.CERT_REQUIRED
        self.sslcontext.check_hostname = True
        self.sslcontext.load_default_certs()

        self.clientvars = {"protocol": 1, "clientver": 2.0, "client": "naoTimes"}
        self._username = username
        self._password = password
        self.logger = logging.getLogger("nthelper.vndbsocket.VNDBSocket")

        self.loggedin = False
        self.data_buffer = bytes(1024)

        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop

        self._sock_reader = None
        self._sock_writer = None

    async def initialize(self):
        self.logger.info("initiating new connection...")
        reader, writer = await asyncio.open_connection(
            "api.vndb.org", 19535, family=socket.AF_INET, ssl=self.sslcontext, loop=self.loop
        )

        self._sock_reader: asyncio.StreamReader = reader
        self._sock_writer: asyncio.StreamWriter = writer

    async def close(self):
        self.logger.warning("emptying reader...")
        await self._sock_reader.read()
        self._sock_writer.close()

    async def login(self):
        finvars = self.clientvars
        if self._username and self._password:
            finvars["username"] = self._username
            finvars["password"] = self._password
            self.logger.info(f"trying to login with username {self._username}")
            ret = await self.send_command("login", ujson.dumps(finvars))
            if not isinstance(ret, str):  # should just be 'Ok'
                if self.loggedin:
                    self.loggedin = False
            self.loggedin = True

    async_login = login

    async def send_command(self, command, args=None):
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
                # We just let ujson propogate the error here
                # if it can't parse the arguments
                final_command = command + " " + ujson.dumps(args) + "\x04"
        else:
            final_command = command + "\x04"
        self.logger.debug(f"sending: {command} command")
        self._sock_writer.write(final_command.encode("utf-8"))
        await self._sock_writer.drain()
        return await self._read_data()

    send_command_async = send_command

    async def _read_data(self):
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
        return ujson.loads(temp.split(" ", 1)[1])
