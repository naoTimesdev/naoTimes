import asyncio
import functools
import logging
import time
import traceback
from typing import Dict, List, Union

import aioredis
import motor.motor_asyncio
import pymongo
import pymongo.errors
import schema as sc

from nthelper.redis import RedisBridge
from nthelper.utils import generate_custom_code

showtimes_log = logging.getLogger("showtimes_helper")

NoneStr = sc.Or(str, None)
NoneInt = sc.Or(int, None)

ShowtimesSchemas = sc.Schema(
    {
        "id": str,
        "serverowner": [str],
        sc.Optional("announce_channel"): NoneStr,
        sc.Optional("fsdb_id"): sc.Or(int, str),
        "anime": [
            {
                sc.Optional("aliases"): [sc.Optional(str)],
                sc.Optional("kolaborasi"): [sc.Optional(str)],
                "id": str,
                "mal_id": str,
                "title": str,
                "role_id": NoneStr,
                "start_time": NoneInt,
                "assignments": {
                    "TL": {"id": NoneStr, "name": NoneStr},
                    "TLC": {"id": NoneStr, "name": NoneStr},
                    "ENC": {"id": NoneStr, "name": NoneStr},
                    "ED": {"id": NoneStr, "name": NoneStr},
                    "TM": {"id": NoneStr, "name": NoneStr},
                    "TS": {"id": NoneStr, "name": NoneStr},
                    "QC": {"id": NoneStr, "name": NoneStr},
                },
                "status": [
                    {
                        "episode": int,
                        "is_done": bool,
                        "progress": {
                            "TL": bool,
                            "TLC": bool,
                            "ENC": bool,
                            "ED": bool,
                            "TM": bool,
                            "TS": bool,
                            "QC": bool,
                        },
                        sc.Optional("airtime"): int,
                    }
                ],
                "poster_data": {"url": str, "color": int},
                "last_update": int,
                sc.Optional("fsdb_data"): {"id": int, "ani_id": int},
            }
        ],
        sc.Optional("konfirmasi"): [{"id": str, "anime_id": int, "server_id": str}],
    },
    name="ShowtimesData",
    description="A schema for server Showtimes data.",
)


def safe_asynclock(func):
    """A thread-safe/async-safe decorator lock mechanism to fight race-condition
    Should be safe enough™

    :param func: Function to wraps
    :type func: Callable
    :return: A async wrapped function with lock mechanism on try/catch block.
             Function put into try/catch block just in case the function
             fail horribly
    :rtype: Callable
    """

    @functools.wraps(func)
    async def safelock(self, *args, **kwargs):
        try:
            showtimes_log.info("Acquiring lock...")
            await self._acquire_lock()  # skipcq: PYL-W0212
            showtimes_log.info("Running function...")
            ret = await func(self, *args, **kwargs)
            showtimes_log.info("Releasing lock...")
            await self._release_lock()  # skipcq: PYL-W0212
            return ret
        except Exception as error:  # skipcq: PYL-W0703
            showtimes_log.error("Exception occured, releasing lock...")
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            showtimes_log.error("{}".format("".join(tb)))
            await self._release_lock()  # skipcq: PYL-W0212
            ret = None
            if args and len(args) == 1:
                ret = None, None
            if kwargs and kwargs.get("collection"):
                ret = None, None
            return ret

    return safelock


class naoTimesDB:
    """
    "Pembungkus" modul Motor (PyMongo) untuk database naoTimes
    Modul ini dibuat untuk kebutuhan khusus naoTimes dan sebagainya.
    """

    def __init__(self, ip_hostname, port, dbname="naotimesdb", auth_string=None, tls=False):
        self.logger = logging.getLogger("naotimesdb")
        self._ip_hostname = ip_hostname
        self._port = port
        self._auth_string = auth_string
        self._tls = tls
        self._dbname = dbname

        self._url = ""
        self.generate_url()

        self.client = motor.motor_asyncio.AsyncIOMotorClient(self._url)
        self.db = self.client[dbname]

        self.srv_re = {"name": {"$regex": r"^srv"}}
        self.__locked = False

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
    def is_locked(self):
        return self.__locked

    async def _acquire_lock(self):
        while True:
            if not self.__locked:
                break
            await asyncio.sleep(0.5)
        self.__locked = True

    async def _release_lock(self):
        self.__locked = False

    async def validate_connection(self):
        await self.db.command({"ping": 1})

    @safe_asynclock
    async def fetch_data(self, server_id: Union[str, int], remove_id=True, **kwargs) -> tuple:
        self.logger.info(f"Fetching server {server_id} data...")
        result = await self.db["showtimesdatas"].find_one({"id": str(server_id)})
        if result is None:
            return {}, server_id
        if remove_id:
            try:
                del result["_id"]
            except KeyError:
                pass
        return result, server_id

    @safe_asynclock
    async def update_data(self, server_id: str, data: dict, **kwargs) -> bool:
        upd = {"$set": data}
        self.logger.info(f"{server_id}: validating schematics...")
        try:
            ShowtimesSchemas.validate(data)
        except sc.SchemaError as error:
            self.logger.error(f"{server_id}: failed to validate the server schemas")
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            self.logger.error("Exception occured\n" + "".join(tb))
        self.logger.info(f"{server_id}: Updating collection...")
        coll = self.db["showtimesdatas"]
        res = await coll.update_one({"id": str(server_id)}, upd)
        if res.acknowledged:
            self.logger.info(f"{server_id}: data updated.")
            return True
        self.logger.error(f"{server_id}: Failed to update.")
        return False

    @safe_asynclock
    async def insert_new(self, server_id: str, data: dict, **kwargs) -> bool:
        coll = self.db["showtimesdatas"]
        self.logger.info(f"{server_id}: validating schematics...")
        try:
            ShowtimesSchemas.validate(data)
        except sc.SchemaError as error:
            self.logger.error(f"{server_id}: failed to validate the server schemas")
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            self.logger.error("Exception occured\n" + "".join(tb))
        self.logger.info(f"{server_id}: adding new data...")
        result = await coll.insert_one(data)
        if result.acknowledged:
            ids_res = result.inserted_id
            self.logger.info(f"{server_id}: inserted with IDs {ids_res}")
            return True
        self.logger.error(f"{server_id}: Failed to insert new data.")
        return False

    @safe_asynclock
    async def fetch_available_servers(self) -> List[str]:
        self.logger.info("Fetching available keys...")
        cursor = self.db["showtimesdatas"].find({}, {"id": 1})
        results_keys = await cursor.to_list(length=250)
        finalized_data = []
        for key in results_keys:
            finalized_data.append(key["id"])
        return finalized_data

    async def ping_server(self):
        t1_ping = time.perf_counter()
        self.logger.info("pinging server...")
        try:
            res = await self.db.command({"ping": 1})
            t2_ping = time.perf_counter()
            if "ok" in res and int(res["ok"]) == 1:
                return True, (t2_ping - t1_ping) * 1000
            return False, 99999
        except (ValueError, pymongo.errors.PyMongoError):
            return False, 99999

    async def fetch_all_as_json(self):
        self.logger.info("Fetching all collection...")
        json_data = {}
        admin_list = await self.get_top_admin()
        json_data["supermod"] = admin_list
        showtimes_coll = self.db["showtimesdatas"]
        showtimes_cur = showtimes_coll.find({})
        self.logger.info("Fetching all showtimes servers!")
        server_collection = await showtimes_cur.to_list(length=100)
        json_data["servers"] = server_collection
        self.logger.info("dumping data...")
        return json_data

    async def patch_all_from_json(self, dataset: dict):
        self.logger.info("patching database with current local save.")
        server_collection = await self.fetch_available_servers()
        for server in dataset["servers"]:
            if server["id"] in server_collection:
                res = await self.update_data(server["id"], server)
                if res:
                    self.logger.info(f"updated {server['id']}")
            else:
                res = await self.insert_new(server["id"], server)
                if res:
                    self.logger.info(f"inserted {server['id']}")

        self.logger.info("updating top admin...")
        while True:
            res = await self.update_data("server_admin", {"server_admin": dataset["supermod"]})
            if res:
                self.logger.info("admin: Updated.")
                break
        self.logger.info("Success patching database")
        return True

    async def get_top_admin(self):
        self.logger.info("fetching...")
        curr = self.db["showtimesadmin"].find({})
        admin_coll = await curr.to_list(length=100)
        removed_ids_contents = []
        for res in admin_coll:
            removed_ids_contents.append({"id": res["id"], "servers": res["servers"]})
        return removed_ids_contents

    async def add_top_admin(self, adm_id):
        self.logger.info(f"trying to add {adm_id}...")
        adm_list = await self.get_top_admin()
        adm_id = str(adm_id)
        if adm_id in adm_list:
            self.logger.warning("admin already on top admin.")
            return True, "Sudah ada"
        res = await self.update_data("server_admin", {"server_admin": adm_list})
        if res:
            self.logger.info("admin added.")
            return True, "Updated"
        self.logger.error("failed to add new top admin.")
        return False, "Gagal menambah top admin baru."

    async def remove_top_admin(self, adm_id):
        self.logger.info(f"trying to remove {adm_id}...")
        adm_list = await self.get_top_admin()
        adm_id = str(adm_id)
        if adm_id in adm_list:
            self.logger.warning("admin is not on top admin.")
            adm_list.remove(adm_id)
        res = await self.update_data("server_admin", {"server_admin": adm_list})
        if res:
            self.logger.info("admin removed.")
            return True, "Updated"
        self.logger.error("failed to remove top admin.")
        return False, "Gagal menghapus top admin."

    async def get_server(self, server):
        server = str(server)
        self.logger.info(f"fetching server set: {server}")
        srv_list = await self.fetch_available_servers()
        if server not in srv_list:
            self.logger.warning(f"cant find {server} on database.")
            return {}

        srv, _ = await self.fetch_data(server)
        return srv

    async def update_data_server(self, server, dataset):
        server = str(server)
        self.logger.info(f"updating data for {server}")
        srv_list = await self.fetch_available_servers()
        if server not in srv_list:
            self.logger.warning(f"cant find {server} on database.")
            return (
                False,
                "Server tidak terdaftar di database, gunakan metode `new_server`",
            )

        res = await self.update_data(server, dataset)
        if res:
            return True, "Updated"
        return False, "Gagal mengupdate server data."

    async def add_admin(self, server, adm_id):
        server = str(server)
        adm_id = str(adm_id)
        self.logger.info(f"trying to add {adm_id} to {server}...")
        srv_data = await self.get_server(server)
        if not srv_data:
            self.logger.warning(f"cant find {server} on database.")
            return False, "Server tidak terdaftar di naoTimes."

        if adm_id not in srv_data["serverowner"]:
            srv_data["serverowner"].append(int(adm_id))

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def remove_admin(self, server, adm_id):
        server = str(server)
        adm_id = str(adm_id)
        self.logger.info(f"trying to remove {adm_id} from {server}...")
        srv_data = await self.get_server(server)
        if not srv_data:
            self.logger.warning(f"cant find {server} on database.")
            return False, "Server tidak terdaftar di naoTimes."

        if adm_id in srv_data["serverowner"]:
            srv_data["serverowner"].remove(int(adm_id))

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def new_server(self, server, admin_id, announce_channel=None):
        server = str(server)
        self.logger.info(f"trying to add {server} to database...")
        srv_list = await self.fetch_available_servers()
        if server in srv_list:
            self.logger.warning(f"{server} already exists on database.")
            return (
                False,
                "Server terdaftar di database, gunakan metode `update_data_server`",
            )

        dataset = {
            "id": str(server),
            "serverowner": [admin_id],
            "announce_channel": announce_channel,
            "anime": [],
            "konfirmasi": [],
        }

        res = await self.insert_new(server, dataset)
        if res:
            res, msg = await self.add_top_admin(str(admin_id))
            self.logger.info(f"{server} added to database.")
            return res, msg if not res else "Updated."
        self.logger.error(f"failed adding {server} to database.")
        return False, "Gagal mengupdate server data."

    async def remove_server(self, server, admin_id):
        server = str(server)
        self.logger.info(f"yeeting {server} from database...")
        srv_list = await self.fetch_available_servers()
        if server not in srv_list:
            self.logger.warning(f"cant find {server} on database.")
            return True

        res = await self.db.drop_collection(server)
        if res:
            res, msg = await self.remove_top_admin(admin_id)
            self.logger.info(f"{server} yeeted from database.")
            return res, msg if not res else "Success."
        self.logger.warning("server doesn't exist on database when dropping, ignoring...")
        return True, "Success anyway"

    async def kolaborasi_dengan(self, target_server, target_data):
        self.logger.info(f"new collaboration with {target_server}")
        target_server = str(target_server)
        srv_data = await self.get_server(target_server)
        if not srv_data:
            self.logger.warning(f"server {target_server} doesn't exist.")
            return False, "Server tidak terdaftar di naoTimes."
        if "konfirmasi" not in srv_data:
            srv_data["konfirmasi"] = []
        srv_data["konfirmasi"].append(target_data)

        res, msg = await self.update_data_server(target_server, srv_data)
        self.logger.info(f"{target_server}: collaboration initiated")
        return res, msg

    async def kolaborasi_konfirmasi(self, source_server, target_server, srv1_data, srv2_data):
        self.logger.info(f"confirming between {source_server}" f" and {target_server}")
        target_server = str(target_server)
        source_server = str(source_server)
        target_srv_data = await self.get_server(target_server)
        source_srv_data = await self.get_server(source_server)
        if not target_srv_data:
            self.logger.warning("target server doesn't exist.")
            return False, "Server target tidak terdaftar di naoTimes."
        if not source_srv_data:
            self.logger.warning("init server doesn't exist.")
            return False, "Server awal tidak terdaftar di naoTimes."

        res, msg = await self.update_data_server(source_server, srv1_data)
        self.logger.info(f"{source_server}: is acknowledged? {res}")
        self.logger.info(f"{source_server}: message? {msg}")
        res, msg = await self.update_data_server(target_server, srv2_data)
        self.logger.info(f"{target_server}: is acknowledged? {res}")
        self.logger.info(f"{target_server}: message? {msg}")
        return res, msg

    @staticmethod
    def _find_confirm_id(konfirm_id, kolaborasi_data):
        index = None
        for n, koleb in enumerate(kolaborasi_data):
            if konfirm_id == koleb["id"]:
                index = n
                break
        return index

    async def kolaborasi_batalkan(self, server, confirm_id):
        self.logger.info("cancelling " f"collaboration with {server}")
        server = str(server)
        srv_data = await self.get_server(server)
        if not srv_data:
            self.logger.warning(f"{server} doesn't exist.")
            return False, "Server tidak terdaftar di naoTimes."

        del_index = self._find_confirm_id(confirm_id, srv_data["kolaborasi"])
        if del_index is None:
            return True, "IDs tidak dapat ditemukan"
        srv_data["kolaborasi"].pop(del_index)

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    # WebUI Mechanism
    async def generate_login_info(self, server_id: str, is_owner=False) -> str:
        randomized_password = generate_custom_code(16, True, True)
        self.logger.info("Checking existing login information!")
        collection = self.db["showtimesuilogin"]
        server_id = str(server_id)
        old_data = await collection.find_one({"id": server_id})
        if old_data is not None:
            self.logger.info("Existing login info exist, returning!")
            return False, f"Login sudah ada, passwordnya adalah: `{old_data['secret']}`"
        self.logger.info(f"Generating new secret for {server_id}")
        login_type = "server" if not is_owner else "owner"
        result = await collection.insert_one(
            {"id": server_id, "secret": randomized_password, "privilege": login_type}
        )
        if result.acknowledged:
            return True, f"Silakan gunakan password/secret berikut untuk login: `{randomized_password}`"
        return False, "Gagal membuat informasi login, mohon coba lagi nanti."


class ShowtimesQueueData:
    """A queue data of save state
    used mainly for queue-ing when there's shit ton of stuff
    to save to the local database.
    """

    def __init__(self, dataset: Union[list, dict], server_id: str):
        self.dataset = dataset
        self.server_id = server_id

        self._type = "dumps"

    @property
    def info(self):
        return f"Server: {self.server_id}"

    def job_type(self):
        return self._type


class ShowtimesLock:
    def __init__(self, server_id: Union[str, int]):
        self._log = logging.getLogger(f"ShowtimesLock[{server_id}]")
        self._id = str(server_id)
        self._lock = False

    @property
    def id(self):
        return self._id

    async def __aenter__(self, *args, **kwargs):
        await self.hold()
        return self._id

    async def __aexit__(self, *args, **kwargs):
        await self.release()

    async def hold(self):
        timeout_max = 10  # In seconds
        current_time = 0
        increment = 0.2
        while self._lock:
            if not self._lock:
                break
            if current_time > timeout_max:
                self._log.warning("Waiting timeout occured, relocking!")
                break
            await asyncio.sleep(increment)
            current_time += increment
        self._log.info("Holding access to lock!")
        self._lock = True

    async def release(self):
        self._log.info("Releasing lock...")
        self._lock = False


class ShowtimesQueue:
    """A helper to queue save local showtimes database.

    Use asyncio.Queue and asyncio.Task
    """

    def __init__(self, redis_client: RedisBridge, loop=None):
        self._db: RedisBridge = redis_client

        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop() if loop is None else loop
        self._logger = logging.getLogger("nthelper.showtimes_helper.ShowtimesQueue")

        self._showqueue: asyncio.Queue = asyncio.Queue()
        self._showtasks: asyncio.Task = asyncio.Task(self.background_jobs(), loop=self._loop)
        # self._showdata: dict = {}

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

    async def _dumps_data(self, dataset: Union[list, dict], server_id: str):
        self._logger.info(f"dumping db {server_id}")
        async with self._get_lock(server_id) as locked_id:
            try:
                await self._db.set(f"showtimes_{locked_id}", dataset)
            except aioredis.RedisError as e:
                self._logger.error("Failed to dumps database...")
                self._logger.error(e)

    async def fetch_database(self, server_id: str):
        self._logger.info(f"opening db {server_id}")
        async with self._get_lock(server_id) as locked_id:
            try:
                json_data = await self._db.get(f"showtimes_{locked_id}")
            except aioredis.RedisError as e:
                self._logger.error("Failed to read database...")
                self._logger.error(e)
                json_data = None
        return json_data

    async def background_jobs(self):
        self._logger.info("Starting ShowtimesQueue Task...")
        while True:
            try:
                sq_data: ShowtimesQueueData = await self._showqueue.get()
                self._logger.info(f"job get, running: {sq_data.server_id}")
                self._logger.info(f"job data type: {sq_data.job_type()}")
                await self._dumps_data(sq_data.dataset, sq_data.server_id)
                self._showqueue.task_done()
            except asyncio.CancelledError:
                return

    async def add_job(self, save_data: ShowtimesQueueData):
        await self._showqueue.put(save_data)
