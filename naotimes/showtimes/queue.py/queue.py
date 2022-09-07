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

import asyncio
import logging
from typing import Dict

from redis import asyncio as aioredis

from ..redis import RedisBridge
from .models import Showtimes, ShowtimesLock

__all__ = ("ShowtimesQueue",)


class ShowtimesQueue:
    """A helper to queue save local showtimes database.

    Use asyncio.Queue and asyncio.Task
    """

    _PREFIX = "showtimes_"

    def __init__(self, redis_client: RedisBridge, loop=None):
        self._db: RedisBridge = redis_client

        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop() if loop is None else loop
        self._logger = logging.getLogger("naoTimes.Showtimes.Queue")

        self._showqueue = asyncio.Queue[Showtimes]()
        self._showtasks: asyncio.Task = asyncio.Task(self.background_jobs(), loop=self._loop)

        self._lock_collection: Dict[str, ShowtimesLock] = {}

    async def shutdown(self):
        """
        Teardown everything
        """
        self._logger.info("Cancelling all tasks...")
        self._showtasks.cancel()
        for _, locked in self._lock_collection.items():
            await locked.release()
        self._logger.info("finished awaiting cancelled tasks, stopping...")

    def _get_lock(self, server_id: str) -> ShowtimesLock:
        server_id = str(server_id)
        if server_id not in self._lock_collection:
            self._lock_collection[server_id] = ShowtimesLock(server_id)
        return self._lock_collection[server_id]

    async def _dumps_data(self, data: Showtimes):
        self._logger.info(f"dumping db {data.id}")
        async with self._get_lock(data.id) as locked_id:
            try:
                await self._db.set(f"{self._PREFIX}{locked_id}", data.serialize())
            except aioredis.RedisError as e:
                self._logger.error("Failed to dumps database...")
                self._logger.error(e)

    async def fetch_database(self, server_id: str):
        async with self._get_lock(server_id) as locked_id:
            try:
                self._logger.info(f"opening db {server_id}")
                json_data = await self._db.get(f"{self._PREFIX}{locked_id}")
                if json_data is None:
                    return None
                json_data = Showtimes.from_dict(json_data)
            except aioredis.RedisError as e:
                self._logger.error("Failed to read database...")
                self._logger.error(e)
                json_data = None
        return json_data

    async def background_jobs(self):
        self._logger.info("Starting ShowtimesQueue Task...")
        while True:
            try:
                sq_data: Showtimes = await self._showqueue.get()
                self._logger.info(f"job get, running: {sq_data.id}")
                await self._dumps_data(sq_data)
                self._showqueue.task_done()
            except asyncio.CancelledError:
                return

    async def add_job(self, save_data: Showtimes):
        await self._showqueue.put(save_data)
