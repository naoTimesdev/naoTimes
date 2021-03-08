import asyncio
import functools
import logging
import time
import traceback
from copy import deepcopy
from typing import Union

import aioredis
import motor.motor_asyncio
import pymongo
import pymongo.errors

from nthelper.redis import RedisBridge

showtimes_log = logging.getLogger("showtimes_helper")


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
            showtimes_log.error("traceback\n{}".format("".join(tb)))
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

        self.clientsync = pymongo.MongoClient(self._url)
        self.dbsync = self.clientsync[dbname]
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
    async def fetch_data(self, collection: str, **kwargs) -> tuple:
        self.logger.info(f"Fetching {collection} data...")
        coll = self.db[collection]
        coll_cur = coll.find({})
        res = list(await coll_cur.to_list(length=100))
        res = res[0]
        del res["_id"]  # type: ignore
        return res, collection

    @safe_asynclock
    async def update_data(self, coll_key: str, data: dict, **kwargs) -> bool:
        upd = {"$set": data}
        self.logger.info(f"{coll_key}: Updating collection...")
        coll = self.db[coll_key]
        res = await coll.update_one({}, upd)
        if res.acknowledged:
            self.logger.info(f"{coll_key}: data updated.")
            return True
        self.logger.error(f"{coll_key}: Failed to update.")
        return False

    @safe_asynclock
    async def insert_new(self, coll_key: str, data: dict, **kwargs) -> bool:
        coll = self.db[coll_key]
        self.logger.info(f"{coll_key}: adding new data...")
        result = await coll.insert_one(data)
        if result.acknowledged:
            ids_res = result.inserted_id
            self.logger.info(f"{coll_key}: inserted with IDs {ids_res}")
            return True
        self.logger.error(f"{coll_key}: Failed to insert new data.")
        return False

    @safe_asynclock
    async def insert_new_sync(self, coll_key: str, data: dict, **kwargs) -> bool:
        srv = self.dbsync[coll_key]
        self.logger.info(f"{coll_key}: adding new data...")
        res = srv.insert(data, check_keys=False)
        if res:
            self.logger.info(f"{coll_key}: data inserted.")
            return True
        self.logger.error(f"{coll_key}: Failed to insert new data.")
        return False

    async def _precheck_server_name(self, namae):
        if not isinstance(namae, str):
            namae = str(namae)
        if not namae.startswith("srv_"):
            namae = "srv_" + namae
        return namae

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
        server_collection = await self.db.list_collection_names(filter=self.srv_re)
        self.logger.info("Creating tasks...")
        server_tasks = [self.fetch_data(coll) for coll in server_collection]
        for srv_task in asyncio.as_completed(server_tasks):
            srv, name = await srv_task
            self.logger.info("Fetching server: {}".format(name))
            json_data[name[4:]] = srv
        self.logger.info("dumping data...")
        return json_data

    async def patch_all_from_json(self, dataset: dict):
        self.logger.info("patching database with current local save.")
        kunci = list(dataset.keys())
        kunci.remove("supermod")

        server_collection = await self.db.list_collection_names(filter=self.srv_re)
        for ksrv in kunci:
            self.logger.info(f"patching collection: {ksrv}")
            ksrv = await self._precheck_server_name(ksrv)
            if ksrv in server_collection:
                while True:
                    self.logger.info(f"{ksrv}: Updating collection...")
                    res = await self.update_data(ksrv, dataset[ksrv[4:]])
                    if res:
                        self.logger.info(f"{ksrv}: Updated.")
                        break
            else:
                while True:
                    self.logger.info(f"{ksrv}: adding as new data...")
                    res = await self.insert_new_sync(ksrv, dataset[ksrv[4:]])
                    if res:
                        break

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
        admin, _ = await self.fetch_data("server_admin")
        admin = admin["server_admin"]
        return admin

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

    @safe_asynclock
    async def get_server_list(self, clean_result=False):
        self.logger.info("fetching...")
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        if clean_result:
            self.logger.info("cleaning results...")
            srv_list = [s[s.find("_") + 1 :] for s in srv_list]
        return srv_list

    async def get_server(self, server):
        server = await self._precheck_server_name(server)
        self.logger.info(f"fetching server set: {server}")
        srv_list = await self.get_server_list()
        if server not in srv_list:
            self.logger.warning(f"cant find {server} on database.")
            return {}

        srv, _ = await self.fetch_data(server)
        return srv

    async def update_data_server(self, server, dataset):
        server = await self._precheck_server_name(server)
        self.logger.info(f"updating data for {server}")
        srv_list = await self.get_server_list()
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
        server = await self._precheck_server_name(server)
        adm_id = str(adm_id)
        self.logger.info(f"trying to add {adm_id} to {server}...")
        srv_data = await self.get_server(server)
        if not srv_data:
            self.logger.warning(f"cant find {server} on database.")
            return False, "Server tidak terdaftar di naoTimes."

        if adm_id not in srv_data["serverowner"]:
            srv_data["serverowner"].append(adm_id)

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def remove_admin(self, server, adm_id):
        server = await self._precheck_server_name(server)
        adm_id = str(adm_id)
        self.logger.info(f"trying to remove {adm_id} from {server}...")
        srv_data = await self.get_server(server)
        if not srv_data:
            self.logger.warning(f"cant find {server} on database.")
            return False, "Server tidak terdaftar di naoTimes."

        if adm_id in srv_data["serverowner"]:
            srv_data["serverowner"].remove(adm_id)

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def new_server(self, server, admin_id, announce_channel=None):
        server = await self._precheck_server_name(server)
        self.logger.info(f"trying to add {server} to database...")
        srv_list = await self.get_server_list()
        if server in srv_list:
            self.logger.warning(f"{server} already exists on database.")
            return (
                False,
                "Server terdaftar di database, gunakan metode `update_data_server`",
            )

        dataset = {
            "serverowner": [str(admin_id)],
            "announce_channel": "",
            "anime": {},
            "alias": {},
            "konfirmasi": {},
        }

        if announce_channel:
            dataset["announce_channel"] = announce_channel

        res = await self.insert_new_sync(server, dataset)
        if res:
            res, msg = await self.add_top_admin(str(admin_id))
            self.logger.info(f"{server} added to database.")
            return res, msg if not res else "Updated."
        self.logger.error(f"failed adding {server} to database.")
        return False, "Gagal mengupdate server data."

    async def remove_server(self, server, admin_id):
        server = await self._precheck_server_name(server)
        self.logger.info(f"yeeting {server} from database...")
        srv_list = await self.get_server_list()
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

    async def kolaborasi_dengan(self, target_server, confirm_id, target_data):
        self.logger.info(f"new collaboration with {target_server}")
        target_server = await self._precheck_server_name(target_server)
        srv_data = await self.get_server(target_server)
        if not srv_data:
            self.logger.warning(f"server {target_server} doesn't exist.")
            return False, "Server tidak terdaftar di naoTimes."
        srv_data["konfirmasi"][confirm_id] = target_data

        res, msg = await self.update_data_server(target_server, srv_data)
        self.logger.info(f"{target_server}: collaboration initiated")
        return res, msg

    async def kolaborasi_konfirmasi(self, source_server, target_server, srv1_data, srv2_data):
        self.logger.info(f"confirming between {source_server}" f" and {target_server}")
        target_server = await self._precheck_server_name(target_server)
        source_server = await self._precheck_server_name(source_server)
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
        self.logger.info(f"{source_server}: message> {msg}")
        res, msg = await self.update_data_server(target_server, srv2_data)
        self.logger.info(f"{target_server}: is acknowledged? {res}")
        self.logger.info(f"{target_server}: message> {msg}")
        return res, msg

    async def kolaborasi_batalkan(self, server, confirm_id):
        self.logger.info("cancelling " f"collaboration with {server}")
        server = await self._precheck_server_name(server)
        srv_data = await self.get_server(server)
        if not srv_data:
            self.logger.warning(f"{server} doesn't exist.")
            return False, "Server tidak terdaftar di naoTimes."

        if confirm_id in srv_data["kolaborasi"]:
            del srv_data["kolaborasi"][confirm_id]
        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def kolaborasi_putuskan(self, server, anime):
        self.logger.info("aborting " f"collaboration with {server}")
        server = await self._precheck_server_name(server)
        srv_data = await self.get_server(server)
        if not srv_data:
            return False, "Server tidak terdaftar di naoTimes."

        if anime not in srv_data["anime"]:
            return False, "Anime tidak dapat ditemukan."

        if "kolaborasi" not in srv_data["anime"][anime]:
            return False, "Tidak ada kolaborasi yang terdaftar"

        for osrv in srv_data["anime"][anime]["kolaborasi"]:
            self.logger.info(f"removing {server} " f"from {osrv} data")
            osrv = await self._precheck_server_name(osrv)
            osrvd = await self.get_server(osrv)
            klosrv = deepcopy(osrvd["anime"][anime]["kolaborasi"])
            klosrv.remove(server[4:])

            remove_all = False
            if len(klosrv) == 1 and klosrv[0] == osrv[4:]:
                remove_all = True

            if remove_all:
                del osrvd["anime"][anime]["kolaborasi"]
            else:
                osrvd["anime"][anime]["kolaborasi"] = klosrv
            res, msg = await self.update_data_server(osrv, osrvd)
            self.logger.info(f"{osrv}: is acknowledged? {res}")
            self.logger.info(f"{osrv}: message> {msg}")

        del srv_data["anime"][anime]["kolaborasi"]

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg


class ShowtimesQueueData:
    """A queue data of save state
    used mainly for queue-ing when there's shit ton of stuff
    to save to the local database.
    """

    def __init__(self, dataset: Union[list, dict], server_id: str):
        self.dataset = dataset
        self.server_id = server_id

        self._type = "dumps"

    def job_type(self):
        return self._type


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

        self._lock = False

    async def shutdown(self):
        """
        Teardown everything
        """
        self._logger.info("Cancelling all tasks...")
        self._showtasks.cancel()
        self._logger.info("finished awaiting cancelled tasks, stopping...")

    # async def get_data(self, server_id: str, retry_time: int = 5):
    #     if retry_time <= 0:
    #         retry_time = 1
    #     dataset = {}
    #     is_success = False
    #     while retry_time > 0:
    #         _temp_data = self._showdata.get(server_id, "no data in showdata")
    #         if not isinstance(_temp_data, str):
    #             dataset = self._showdata.pop(server_id)
    #             is_success = True
    #             break
    #         retry_time -= 1
    #         await asyncio.sleep(0.2)
    #     return dataset, is_success

    async def _dumps_data(self, dataset: Union[list, dict], server_id: str):
        self._logger.info(f"dumping db {server_id}")
        await self._lock_job()
        try:
            await self._db.set(f"showtimes_{server_id}", dataset)
        except aioredis.RedisError as e:
            self._logger.error("Failed to dumps database...")
            self._logger.error(e)
            pass
        await self._job_done()

    async def fetch_database(self, server_id: str):
        self._logger.info(f"opening db {server_id}")
        await self._lock_job()
        try:
            json_data = await self._db.get(f"showtimes_{server_id}")
        except aioredis.RedisError as e:
            self._logger.error("Failed to read database...")
            self._logger.error(e)
            json_data = None
        # self._logger.info("Adding to data part...")
        # self._showdata[server_id] = json_data
        await self._job_done()
        return json_data

    async def _lock_job(self):
        while self._lock:
            await asyncio.sleep(0.2)
        self._lock = True

    async def _job_done(self):
        self._lock = False

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
