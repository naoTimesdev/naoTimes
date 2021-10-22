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

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Union

from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import AIOEngine
from odmantic.exceptions import DocumentNotFoundError
from pymongo.errors import PyMongoError

from ..models import ShowAdminSchema, ShowtimesSchema, ShowtimesUISchema, ShowUIPrivilege
from ..utils import generate_custom_code
from .models import Showtimes, ShowtimesAdmin, ShowtimesLock

if TYPE_CHECKING:
    from motor.core import AgnosticClient, AgnosticDatabase

__all__ = ("naoTimesDB",)


class naoTimesDB:
    """
    "Pembungkus" modul Motor (PyMongo) untuk database naoTimes.
    Digunakan untuk komunikasi dengan fungsi khusus dan sebagainya!
    """

    _EmptySet = set()

    def __init__(
        self,
        ip_hostname: str,
        port: int,
        dbname: str = "naotimesdb",
        auth_string: str = None,
        tls: bool = False,
        developer_mode: bool = False,
    ):
        self.logger = logging.getLogger("naoTimes.ShowtimesDB")
        self._ip_hostname = ip_hostname
        self._port = port
        self._auth_string = auth_string
        self._tls = tls
        if developer_mode:
            dbname += "_dev"
        self._dbname = dbname
        self.dev_mode = developer_mode

        self._url = ""
        self.generate_url()

        self._client: AgnosticClient = AsyncIOMotorClient(self._url)
        self._db: AgnosticDatabase = self._client[self._dbname]
        self._engine = AIOEngine(self._client, self._dbname)

        self.srv_re = {"name": {"$regex": r"^srv"}}
        self._lock_collection: Dict[str, ShowtimesLock] = {}

    def generate_url(self):
        self._url = "mongodb"
        if self._tls:
            self._url += "+srv"
        self._url += "://"
        if self._auth_string:
            self._url += self._auth_string + "@"
        self._url += f"{self._ip_hostname}"
        if not self._tls:
            self._url += f":{self._port}"
        self._url += "/"
        if self._tls:
            self._url += "?retryWrites=true&w=majority"

    @property
    def dbname(self):
        return self._dbname

    @property
    def url(self):
        _url = "mongodb"
        if self._tls:
            _url += "+srv"
        _url += "://"
        if self._auth_string:
            try:
                user, pass_ = self._auth_string.split(":")
                pass_ = "*" * len(pass_)
                secured_auth = f"{user}:{pass_}"
            except ValueError:
                secured_auth = self._auth_string
            _url += secured_auth + "@"
        _url += f"{self._ip_hostname}"
        if not self._tls:
            _url += f":{self._port}"
        _url += "/"
        return _url

    @property
    def ip_hostname(self) -> str:
        is_v4 = "." in self._ip_hostname
        if is_v4:
            ip_split = self._ip_hostname.split(".")
        else:
            ip_split = self._ip_hostname.split(":")

        ip_masked = ["*" * len(ip) for ip in ip_split[: len(ip_split) - 1]]
        ip_masked.append(ip_split[-1])
        return ".".join(ip_masked) if is_v4 else ":".join(ip_masked)

    @property
    def port(self) -> int:
        return self._port

    def _get_lock(self, server_id: str) -> ShowtimesLock:
        server_id = str(server_id)
        if server_id not in self._lock_collection:
            self._lock_collection[server_id] = ShowtimesLock(server_id)
        return self._lock_collection[server_id]

    async def validate_connection(self):
        await self._db.command({"ping": 1})

    async def ping_server(self):
        t1_ping = time.perf_counter()
        self.logger.info("pinging server...")
        try:
            res = await self._db.command({"ping": 1})
            t2_ping = time.perf_counter()
            if "ok" in res and int(res["ok"]) == 1:
                return True, (t2_ping - t1_ping) * 1000
            return False, 99999
        except (ValueError, PyMongoError):
            return False, 99999

    async def fetch_available_servers(self) -> List[str]:
        """Fetch available servers from database"""
        self.logger.info("Fetching available keys...")
        cursor = self._db["showtimesdatas"].find({}, {"id": 1})
        results_keys = await cursor.to_list(length=250)
        finalized_data = []
        for key in results_keys:
            finalized_data.append(key["id"])
        return finalized_data

    async def fetch_data(self, server_id: Union[str, int]):
        """Fetch showtimes data from database"""
        self.logger.info(f"Fetching server {server_id} data...")
        server_id = str(server_id)
        async with self._get_lock(server_id):
            database_result = await self._engine.find_one(ShowtimesSchema, ShowtimesSchema.id == server_id)
            return database_result, server_id

    async def update_data(self, data: dict):
        parsed = ShowtimesSchema.parse_doc(data)
        self.logger.info(f"Updating server {parsed.id} data...")
        async with self._get_lock(parsed.id):
            try:
                await self._engine.save(parsed)
            except PyMongoError as e:
                return (
                    False,
                    f"Terjadi kesalahan ketika ingin mengupdate database, pesan dari MongoDB: {e._message}",
                )
            return True, "Sukses"

    async def insert_new(self, data: dict):
        return await self.update_data(data)

    async def get_top_admin(self) -> List[dict]:
        self.logger.info("Fetching top administrator...")
        all_admins = await self._engine.find(ShowAdminSchema)
        return [a.dict() for a in all_admins]

    async def fetch_all_as_json(self) -> List[dict]:
        self.logger.info("Fetching all showtimes...")
        all_data = await self._engine.find(ShowtimesSchema)
        json_data = {}
        as_json = []
        for data in all_data:
            as_json.append(data.dict())
        json_data["servers"] = as_json
        json_data["supermod"] = await self.get_top_admin()
        self.logger.info("dumping data...")
        return json_data

    async def get_server(self, server: str):
        server = str(server)
        real_data, _ = await self.fetch_data(server)
        return Showtimes.from_dict(real_data.dict())

    async def update_server(self, data: Showtimes):
        show_dict = data.serialize()
        return await self.update_data(show_dict)

    async def get_admin(self, user_id: str):
        user_id = str(user_id)
        async with self._get_lock("admin_" + user_id):
            database_result = await self._engine.find_one(ShowAdminSchema, ShowAdminSchema.id == user_id)
            return ShowtimesAdmin.from_dict(database_result.dict())

    update_data_server = update_server

    async def remove_server(self, data: Showtimes):
        server = str(data.id)
        self.logger.info(f"yeeting {server} from database...")
        srv_list = await self.fetch_available_servers()
        if server not in srv_list:
            self.logger.warning(f"cant find {server} on database.")
            return True

        show_dict = data.serialize()
        parsed_model = ShowtimesSchema.parse_doc(show_dict)

        try:
            await self._engine.delete(parsed_model)
            self.logger.info(f"{server} deleted from database.")
            return True
        except DocumentNotFoundError:
            self.logger.warning(f"cant find {server} on database.")
            return False

    async def generate_login_info(self, server_id: str, is_owner: bool = False):
        secret_gen = generate_custom_code(16, True, True)
        self.logger.info("Checking existing login information!")
        server_id = str(server_id)
        old_data = await self._engine.find_one(ShowtimesUISchema, ShowtimesUISchema.id == server_id)
        if old_data is not None:
            self.logger.info("Existing login info exist, returning!")
            return False, f"Login sudah ada, passwordnya adalah: `{old_data.secret}`"
        self.logger.info("Generating new login info!")
        privilege = "owner" if is_owner else "server"
        new_data = ShowtimesUISchema(
            id=server_id,
            secret=secret_gen,
            privilege=ShowUIPrivilege(privilege),
        )
        result = await self._engine.save(new_data)
        if not result:
            return False, "Gagal membuat informasi login, mohon coba lagi nanti."
        return True, f"Silakan gunakan password/secret berikut untuk login: `{secret_gen}`"
