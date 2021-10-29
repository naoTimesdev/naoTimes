"""
A custom Redis client for naoTimes.
Using aioredis as it's main connector

The main class wraps multiple command with some stuff that I use.
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

import asyncio
import logging
import uuid
from typing import Any, Dict, List, NoReturn, Optional, Union

import aioredis
import orjson
from bson import ObjectId

__all__ = ("RedisBridge",)


def ShowtimesEncoderDefault(obj: Any):
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError


class RedisBridge:
    """A custom Redis connection handler.
    Using aioredis as it's main connector

    This `class` is wrapping some of the main function of the aioredis module,
    with extras like automatic data conversion, a `getall` and `getalldict` function
    that wraps fetching all values of many `keys` on a provided pattern

    All function in this class is asynchronous!

    Usage:
    -------
    ```py
    import asyncio

    loop = asyncio.get_event_loop()
    client = RedisBridge(host="127.0.0.1", port=6379, loop=loop)
    # You need to specifically init the connection for now
    loop.run_until_complete(client.connect())

    # Set key
    loop.run_until_complete(client.set("data1", {"key": "val"}))

    # Get key
    res = loop.run_until_complete(client.get("data1"))
    print(res)  # --> {"key": "val"}

    # Close the connection
    loop.run_until_complete(client.close())
    loop.close()
    ```
    """

    def __init__(self, host: str, port: int, password: str = None, loop: asyncio.AbstractEventLoop = None):
        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._host = host
        self._port = port
        self._pass = password

        address = f"redis://{self._host}:{self._port}"
        kwargs = {"url": address}
        if self._pass is not None:
            kwargs["password"] = self._pass
        self._pool = aioredis.ConnectionPool.from_url(**kwargs)
        self._conn = aioredis.Redis(connection_pool=self._pool)
        self.logger = logging.getLogger("naoTimes.Redis")
        self._is_connected = False

        self._need_execution = []
        self._is_stopping = False

    def lock(self, key: str):
        """Lock/add a process to execution task"""
        self._need_execution.append(key)

    def unlock(self, key: str):
        """Remove a process from execution task"""
        try:
            self._need_execution.remove(key)
        except ValueError:
            pass

    @property
    def client(self):
        """:class:`aioredis.Redis`: The internal redis client."""
        return self._conn

    @property
    def connection(self):
        """:class:`aioredis.ConnectionPool`: Returns the connection pool."""
        return self._pool

    def stringify(self, data: Any) -> str:
        """Stringify `data`

        :param data: data to be turn into a string
        :type data: Any
        :return: A stringified `data`
        :rtype: str
        """
        if isinstance(data, bytes):
            data = data.decode("utf-8")
            # Prepend magic code
            data = "b2dntcode_" + data
        elif isinstance(data, int):
            data = str(data)
        elif isinstance(data, (list, tuple, dict)):
            data = orjson.dumps(data, default=ShowtimesEncoderDefault).decode("utf-8")
        return data

    @staticmethod
    def _try_float(data: str) -> Union[str, float]:
        """Try to convert the data to float

        :param data: data to convert
        :type data: str
        :return: float or the original data
        :rtype: Union[str, float]
        """
        try:
            return float(data)
        except ValueError:
            return data

    def to_original(self, data: Optional[bytes]) -> Optional[Any]:
        """Convert back data to the possible original data types

        For bytes, you need to prepend with `b2dntcode_`
        since there's no reliable way to detect it.

        :param data: data to convert to original type
        :type data: Optional[str]
        :return: Converted data
        :rtype: Any
        """
        if data is None:
            return None
        parsed = data.decode("utf-8")
        _float_parse = self._try_float(parsed)
        if isinstance(_float_parse, (float, int)):
            return _float_parse
        if parsed.isdigit():
            return int(parsed, 10)
        if parsed.startswith("b2dntcode_"):
            parsed = parsed[10:]
            return parsed.encode("utf-8")
        try:
            parsed = orjson.loads(parsed)
        except ValueError:
            pass
        return parsed

    @property
    def is_stopping(self) -> bool:
        """Is the connection is being stopped or not?"""
        return self._is_stopping

    async def connect(self):
        """Initialize the connection to the RedisDB

        Please execute this function after creating the `class`
        """
        self._conn = await self._conn.initialize()
        self._is_connected = True

    async def close(self):
        """Close the underlying connection

        This function will wait until all of remaining process has been executed
        and then set it to stopping mode, halting any new function call.
        """
        self.logger.info(f"Closing connection, waiting for {len(self._need_execution)} tasks...")
        timeout_delta = 10.0
        current_timeout = 0.0
        while len(self._need_execution) > 0:
            await asyncio.sleep(0.2)
            if len(self._need_execution) < 1:
                break
            if current_timeout > timeout_delta:
                self.logger.info("Timeout after waiting for 10 seconds, shutting down anyway...")
                break
            current_timeout += 0.2
        self._is_stopping = True
        self.logger.info("All tasks executed, closing connection!")
        await self._conn.close()
        self.logger.info("Closing all pool connection...")
        await self._pool.disconnect()
        self.logger.info("All connection closed")

    async def get(self, key: str, fallback: Any = None) -> Any:
        """Get a key from the database

        :param key: The key of the object
        :type key: str
        :return: The value of a key, might be `NoneType`
        :rtype: Any
        """
        if self._is_stopping:
            return None
        uniq_id = str(uuid.uuid4())
        self.lock("get_" + uniq_id)
        try:
            res = await self._conn.get(key)
            res = self.to_original(res)
            if res is None:
                res = fallback
        except aioredis.RedisError:
            res = fallback
        self.unlock("get_" + uniq_id)
        return res

    async def keys(self, pattern: str) -> List[str]:
        """Get a list of keys from the database

        :param pattern: The pattern of the key to find, using the glob-style patterns
                        Refer more here: https://redis.io/commands/KEYS
        :type pattern: str
        :return: The matching keys of the pattern
        :rtype: List[str]
        """
        if self._is_stopping:
            return []
        uniq_id = str(uuid.uuid4())
        self.lock("keys_" + uniq_id)
        try:
            all_keys = await self._conn.keys(pattern)
        except aioredis.RedisError:
            all_keys = []
        self.unlock("keys_" + uniq_id)
        if not isinstance(all_keys, list):
            return []
        all_keys = [key.decode("utf-8") for key in all_keys]
        return all_keys

    async def getall(self, pattern: str) -> List[Any]:
        """Get all values that match the key pattern

        Example return format: `["value_of_it", "another_value"]`

        :param pattern: The pattern of the keys to find, using the glob-style patterns
                        Refer more here: https://redis.io/commands/KEYS
        :type pattern: str
        :return: All values of the matches keys
        :rtype: List[Any]
        """
        if self._is_stopping:
            return []
        uniq_id = str(uuid.uuid4())
        all_keys = await self.keys(pattern)
        if not isinstance(all_keys, list):
            return []
        self.lock("getall_" + uniq_id)
        all_values = []
        for key in all_keys:
            r_val = await self.get(key)
            all_values.append(r_val)
        self.unlock("getall_" + uniq_id)
        return all_values

    async def getalldict(self, pattern: str) -> Dict[str, Any]:
        """Get all values (with the key of it) that match the key pattern

        This is the same as `getall()` but with dict format.

        Example: `{"the_key_name": "value_of_it", "the_key_name2", "another_value"}`

        :param pattern: The pattern of the keys to find, using the glob-style patterns
                        Refer more here: https://redis.io/commands/KEYS
        :type pattern: str
        :return: A key-value dict, key is the key name, value is the data
        :rtype: Dict[str, Any]
        """
        if self._is_stopping:
            return {}
        uniq_id = str(uuid.uuid4())
        all_keys = await self.keys(pattern)
        if not isinstance(all_keys, list):
            return {}
        self.lock("getalldict_" + uniq_id)
        key_val = {}
        for key in all_keys:
            r_val = await self.get(key)
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            key_val[key] = r_val
        self.unlock("getalldict_" + uniq_id)
        return key_val

    async def set(self, key: str, data: Any) -> bool:
        """Set a new key with provided data

        :param key: key name to hold the data
        :type key: str
        :param data: the data itself
        :type data: Any
        :return: is the execution success or no?
        :rtype: bool
        """
        if self._is_stopping:
            return False
        uniq_id = str(uuid.uuid4())
        self.lock("set_" + uniq_id)
        try:
            res = await self._conn.set(key, self.stringify(data))
        except aioredis.RedisError as e:
            self.logger.debug(f"Failed to set {key}", exc_info=e)
            res = False
        self.unlock("set_" + uniq_id)
        return res

    async def setex(self, key: str, data: Any, expires: int) -> bool:
        """Set a new key with provided data BUT with additional expiration time

        :param key: key name to hold the data
        :type key: str
        :param data: the data itself
        :type data: Any
        :param expires: TTL of the key, in seconds
        :type expires: int
        :return: is the execution success or no?
        :rtype: bool
        """
        if self._is_stopping:
            return False
        uniq_id = str(uuid.uuid4())
        self.lock("setex_" + uniq_id)
        try:
            res = await self._conn.setex(key, expires, self.stringify(data))
        except aioredis.RedisError:
            res = False
        self.unlock("setex_" + uniq_id)
        return res

    async def exists(self, key: str) -> bool:
        """Check if a key exist or not on the DB

        :param key: Key to check
        :type key: str
        :return: Is the key exist or not?
        :rtype: bool
        """
        if self._is_stopping:
            return False
        uniq_id = str(uuid.uuid4())
        self.lock("exists_" + uniq_id)
        try:
            res = await self._conn.exists(key)
        except aioredis.RedisError:
            res = 0
        self.unlock("exists_" + uniq_id)
        if res > 0:
            return True
        return False

    async def rm(self, key: str) -> bool:
        """Remove a key from the database

        :param key: key to remove
        :type key: str
        :return: is the deletion success or not?
        :rtype: bool
        """
        if self._is_stopping:
            return False
        uniq_id = str(uuid.uuid4())
        self.lock("rm_" + uniq_id)
        try:
            res = await self._conn.delete(key)
        except aioredis.RedisError:
            res = 0
        self.unlock("rm_" + uniq_id)
        if res > 0:
            return True
        return False

    # Aliases
    exist = exists
    delete = rm

    async def bulkrm(self, keys: str) -> NoReturn:
        if self._is_stopping:
            return False
        collection = await self.keys(keys)
        for key in collection:
            await self.rm(key)

    bulkdelete = bulkrm
