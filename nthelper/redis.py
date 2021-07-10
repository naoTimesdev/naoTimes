import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import aioredis
from bson import ObjectId


class BSONEncoderExtended(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, ObjectId):
            return str(o)
        return super().default(o)


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
        kwargs = {"address": address, "loop": self._loop}
        if self._pass is not None:
            kwargs["password"] = self._pass
        self._conn = aioredis.create_redis_pool(**kwargs)
        self.logger = logging.getLogger("nthelper.redis.RedisBridge")
        self._is_connected = False

        self._need_execution = []
        self._is_stopping = False

    @staticmethod
    def _clean_bson_objectid(objects: dict) -> dict:
        readjusted_data = {}
        for key, value in objects.items():
            if isinstance(value, ObjectId):
                continue
            readjusted_data[key] = value
        return readjusted_data

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
            if isinstance(data, dict):
                data = self._clean_bson_objectid(data)
            elif isinstance(data, list):
                _data = []
                for d in data:
                    if isinstance(d, dict):
                        _data.append(self._clean_bson_objectid(d))
                    else:
                        _data.append(d)
                data = _data
            data = json.dumps(data, ensure_ascii=False, cls=BSONEncoderExtended)
        return data

    @staticmethod
    def to_original(data: Optional[str]) -> Any:
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
        if data.isnumeric():
            return int(data, 10)
        if data.startswith("b2dntcode_"):
            data = data[10:]
            return data.encode("utf-8")
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            pass
        return data

    @property
    def is_stopping(self) -> bool:
        """Is the connection is being stopped or not?"""
        return self._is_stopping

    async def connect(self):
        """Initialize the connection to the RedisDB

        Please execute this function after creating the `claas`
        """
        self._conn = await self._conn
        self._is_connected = True

    async def close(self):
        """Close the underlying connection

        This function will wait until all of remaining process has been executed
        and then set it to stopping mode, halting any new function call.
        """
        self.logger.info(f"Closing connection, waiting for {len(self._need_execution)} tasks...")
        timeout_delta = 10
        current_timeout = 0
        while len(self._need_execution) > 0:
            await asyncio.sleep(0.2)
            if len(self._need_execution) < 1:
                break
            if timeout_delta > current_timeout:
                self.logger.info("Timeout after waiting for 10 seconds, shutting down anyway...")
                break
            current_timeout += 0.2
        self._is_stopping = True
        self.logger.info("All tasks executed, closing connection!")
        self._conn.close()
        await self._conn.wait_closed()

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
        self._need_execution.append("get_" + uniq_id)
        try:
            res = await self._conn.get(key, encoding="utf-8")
            if res is None:
                return fallback
            res = self.to_original(res)
        except aioredis.errors.RedisError:
            res = None
        self._need_execution.remove("get_" + uniq_id)
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
        self._need_execution.append("keys_" + uniq_id)
        try:
            all_keys = await self._conn.keys(pattern)
        except aioredis.errors.RedisError:
            all_keys = []
        self._need_execution.remove("keys_" + uniq_id)
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
        self._need_execution.append("getall_" + uniq_id)
        try:
            all_keys = await self._conn.keys(pattern)
        except aioredis.errors.RedisError:
            all_keys = []
        self._need_execution.remove("getall_" + uniq_id)
        if not isinstance(all_keys, list):
            return []
        all_values = []
        for key in all_keys:
            r_val = await self.get(key)
            all_values.append(r_val)
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
        self._need_execution.append("getalldict_" + uniq_id)
        try:
            all_keys = await self._conn.keys(pattern)
        except aioredis.RedisError:
            all_keys = []
        self._need_execution.remove("getalldict_" + uniq_id)
        if not isinstance(all_keys, list):
            return {}
        key_val = {}
        for key in all_keys:
            r_val = await self.get(key)
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            key_val[key] = r_val
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
        self._need_execution.append("set_" + uniq_id)
        try:
            res = await self._conn.set(key, self.stringify(data))
        except aioredis.RedisError:
            res = False
        self._need_execution.remove("set_" + uniq_id)
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
        self._need_execution.append("setex_" + uniq_id)
        try:
            res = await self._conn.setex(key, expires, self.stringify(data))
        except aioredis.RedisError:
            res = False
        self._need_execution.remove("setex_" + uniq_id)
        return res

    async def exist(self, key: str) -> bool:
        """Check if a key exist or not on the DB

        :param key: Key to check
        :type key: str
        :return: Is the key exist or not?
        :rtype: bool
        """
        if self._is_stopping:
            return False
        uniq_id = str(uuid.uuid4())
        self._need_execution.append("exists_" + uniq_id)
        try:
            res = await self._conn.exists(key)
        except aioredis.RedisError:
            res = 0
        self._need_execution.remove("exists_" + uniq_id)
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
        self._need_execution.append("delete_" + uniq_id)
        try:
            res = await self._conn.delete(key)
        except aioredis.RedisError:
            res = 0
        self._need_execution.remove("delete_" + uniq_id)
        if res > 0:
            return True
        return False

    # Aliases
    delete = rm
