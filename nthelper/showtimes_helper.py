import asyncio
import functools
from copy import deepcopy

import motor.motor_asyncio
import pymongo


def safe_asynclock(func):
    """A thread-safe/async-safe decorator lock mechanism to fight race-condition
    Should be safe enough™

    :param func: Function to wraps
    :type func: Callable
    :return: A async wrapped function with lock mechanism on try/catch block.
             Function put into try/catch block just in case the function fail horribly
    :rtype: Callable
    """
    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        try:
            print("[SAFELOCK] Acquiring lock...")
            await self._acquire_lock()
            print("[SAFELOCK] Running function...")
            ret = await func(self, *args, **kwargs)
            print("[SAFELOCK] Releasing lock...")
            await self._release_lock()
            return ret
        except:
            print("[SAFELOCK] Exception occured, releasing lock...")
            await self._release_lock()
            ret = None
            if args:
                if len(args) == 1:
                    ret = None, None
            if kwargs:
                if kwargs.get("collection"):
                    ret = None, None
            return ret
    return async_wrapper



class naoTimesDB:
    """
    "Pembungkus" modul Motor (PyMongo) untuk database naoTimes
    Modul ini dibuat untuk kebutuhan khusus naoTimes dan sebagainya.
    """
    def __init__(self, ip_hostname, port, dbname="naotimesdb"):
        self.client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://{}:{}".format(ip_hostname, port))
        self.db = self.client[dbname]

        self.clientsync = pymongo.MongoClient("mongodb://{}:{}".format(ip_hostname, port))
        self.dbsync = self.clientsync[dbname]
        self.srv_re = {"name": {"$regex": r"^srv"}}
        self.__locked = False

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

    @safe_asynclock
    async def fetch_data(self, collection: str) -> tuple:
        coll = self.db[collection]
        coll_cur = coll.find({})
        res = list(await coll_cur.to_list(length=100))
        res = res[0]
        del res['_id']
        return res, collection

    @safe_asynclock
    async def update_data(self, coll_key: str, data: dict) -> bool:
        upd = {"$set": data}
        print('\t[ntDB] Updating collection: {}'.format(coll_key))
        coll = self.db[coll_key]
        res = await coll.update_one({}, upd)
        if res.acknowledged:
            print('\t[ntDB] INFO: {} data updated.'.format(coll_key))
            return True
        print('\t[ntDB] ERROR: Failed to update {} data.'.format(coll_key))
        return False

    @safe_asynclock
    async def insert_new(self, coll_key: str, data: dict) -> bool:
        coll = self.db[coll_key]
        print('\t[ntDB] INFO: Adding new data: {}'.format(coll_key))
        result = await coll.insert_one(data)
        if result.acknowledged:
            self.logger.info(f"\tInserted with IDs: {result.inserted_id}")
            return True
        self.logger.error("\tFailed to insert new data.")
        return False

    @safe_asynclock
    async def insert_new_sync(self, coll_key: str, data: dict) -> bool:
        srv = self.dbsync[coll_key]
        print('\t[ntDB] INFO: Adding new data: {}'.format(coll_key))
        res = srv.insert(data, check_keys=False)
        if res:
            print('\t[ntDB] INFO: {} data inserted.'.format(coll_key))
            return True
        print('\t[ntDB] ERROR: Failed to insert {} data.'.format(coll_key))
        return False

    async def _precheck_server_name(self, namae):
        if not isinstance(namae, str):
            namae = str(namae)
        if not namae.startswith("srv_"):
            namae = "srv_" + namae
        return namae

    async def ping_server(self):
        try:
            res = await self.db.command({'ping': 1})
            if "ok" in res:
                if int(res['ok']) == 1:
                    return True
            return False
        except Exception:
            return True

    async def fetch_all_as_json(self):
        print('[ntDB] INFO: Fetching all collection as json...')
        json_data = {}
        admin_list = await self.get_top_admin()
        json_data['supermod'] = admin_list
        server_collection = await self.db.list_collection_names(filter=self.srv_re)
        print("[ntDB] INFO: Creating tasks...")
        server_tasks = [self.fetch_data(coll) for coll in server_collection]
        for srv_task in asyncio.as_completed(server_tasks):
            srv, name = await srv_task
            print('[ntDB] INFO2: Fetching server: {}'.format(name))
            json_data[name[4:]] = srv
        print('[ntDB] INFO: Dumping data...')
        return json_data

    async def patch_all_from_json(self, dataset: dict):
        print('[ntDB] INFO: Patching database with current local save.')
        kunci = list(dataset.keys())
        kunci.remove('supermod')

        server_collection = await self.db.list_collection_names(filter=self.srv_re)
        for ksrv in kunci:
            print('[ntDB] Redoing collection: {}'.format(ksrv))
            ksrv = await self._precheck_server_name(ksrv)
            if ksrv in server_collection:
                while True:
                    print('\t[ntDB] Updating collection: {}'.format(ksrv))
                    res = await self.update_data(ksrv, dataset[ksrv[4:]])
                    if res:
                        print('\t[ntDB] INFO: Updated.')
                        break
            else:
                while True:
                    print('\t[ntDB] INFO: Adding new data: {}'.format(ksrv))
                    res = await self.insert_new_sync(ksrv, dataset[ksrv[4:]])
                    if res:
                        break

        print('[ntDB] INFO: Updating top admin...')
        while True:
            res = await self.update_data("server_admin", {"server_admin": dataset["supermod"]})
            if res:
                print('[ntDB] INFO: Updated.')
                break
        print('[ntDB] INFO: Success patching database')
        return True

    async def get_top_admin(self):
        print('[ntDB] INFO: Fetching top admin/server admin.')
        admin, _ = await self.fetch_data("server_admin")
        admin = admin['server_admin']
        return admin

    async def add_top_admin(self, adm_id):
        print('[ntDB] INFO: Adding new top admin/server admin.')
        adm_list = await self.get_top_admin()
        adm_id = str(adm_id)
        if adm_id in adm_list:
            return True, "Sudah ada"
        res = await self.update_data("server_admin", {"server_admin": adm_list})
        if res:
            return True, 'Updated'
        return False, 'Gagal menambah top admin baru.'

    async def remove_top_admin(self, adm_id):
        print('[ntDB] INFO: Removing `{}` from top admin/server admin.'.format(adm_id))
        adm_list = await self.get_top_admin()
        adm_id = str(adm_id)
        if adm_id in adm_list:
            adm_list.remove(adm_id)
        res = await self.update_data("server_admin", {"server_admin": adm_list})
        if res:
            return True, 'Updated'
        return False, 'Gagal menghapus top admin.'

    @safe_asynclock
    async def get_server_list(self):
        print('[ntDB] INFO: Fetching server list')
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        srv_list = [s[s.find('_')+1:] for s in srv_list]
        return srv_list

    async def get_server(self, server):
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Fetching server set: {}'.format(server))
        srv_list = await self.get_server_list()
        if server not in srv_list:
            print('[ntDB] WARN: cannot found server in database.')
            return {}

        srv, _ = await self.fetch_data(server)
        return srv

    async def update_data_server(self, server, dataset):
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Updating data for server: {}'.format(server))
        srv_list = await self.get_server_list()
        if server not in srv_list:
            print('[ntDB] WARN: cannot found server in database.')
            return False, 'Server tidak terdaftar di database, gunakan metode `new_server`'

        srv = self.db[server]
        res = await self.update_data(server, dataset)
        if res:
            return True, 'Updated'
        return False, 'Gagal mengupdate server data.'

    async def add_admin(self, server, adm_id):
        server = await self._precheck_server_name(server)
        adm_id = str(adm_id)
        print('[ntDB] INFO: Adding new admin `{}` to server: {}'.format(adm_id, server))
        srv_data = await self.get_server(server)
        if not srv_data:
            return False, 'Server tidak terdaftar di naoTimes.'

        if adm_id not in srv_data['serverowner']:
            srv_data['serverowner'].append(adm_id)

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def remove_admin(self, server, adm_id):
        server = await self._precheck_server_name(server)
        adm_id = str(adm_id)
        print('[ntDB] INFO: Removing admin `{}` from server: {}'.format(adm_id, server))
        srv_data = await self.get_server(server)
        if not srv_data:
            return False, 'Server tidak terdaftar di naoTimes.'

        if adm_id in srv_data['serverowner']:
            srv_data['serverowner'].remove(adm_id)

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def new_server(self, server, admin_id, announce_channel = None):
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Adding data for a new server: {}'.format(server))
        srv_list = await self.get_server_list()
        if server in srv_list:
            print('[ntDB] WARN: found server in database, please use `update_data_server` method')
            return False, 'Server terdaftar di database, gunakan metode `update_data_server`'

        dataset = {
            "serverowner": [str(admin_id)],
            "announce_channel": "",
            "anime": {},
            "alias": {},
            "konfirmasi": {}
        }

        if announce_channel:
            dataset['announce_channel'] = announce_channel

        res = await self.insert_new_sync(server, dataset)
        if res:
            res, msg = await self.add_top_admin(str(admin_id))
            print('[ntDB] INFO: Server data updated.')
            return res, msg if not res else "Updated."
        print('[ntDB] ERROR: Failed to add new server data.')
        return False, 'Gagal mengupdate server data.'

    async def remove_server(self, server, admin_id):
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Expunging data for a server: {}'.format(server))
        srv_list = await self.get_server_list()
        if server not in srv_list:
            print('[ntDB] WARN: Cannot find server in database, ignoring...')
            return True

        res = await self.db.drop_collection(server)
        if res:
            res, msg = await self.remove_top_admin(admin_id)
            print('[ntDB] INFO: Success deleting server from database')
            return res, msg if not res else "Success."
        print('[ntDB] WARN: Server doesn\'t exist on database when dropping, ignoring...')
        return True, 'Success anyway'

    """
    Kolaborasi command
    """
    async def kolaborasi_dengan(self, target_server, confirm_id, target_data):
        print('[ntDB] INFO: Collaborating with: {}'.format(target_server))
        target_server = await self._precheck_server_name(target_server)
        srv_data = await self.get_server(target_server)
        if not srv_data:
            return False, 'Server tidak terdaftar di naoTimes.'
        srv_data['konfirmasi'][confirm_id] = target_data

        res, msg = await self.update_data_server(target_server, srv_data)
        return res, msg

    async def kolaborasi_konfirmasi(self, source_server, target_server, srv1_data, srv2_data):
        print(
            '[ntDB] INFO: Confirming collaborating between {} and {}'.format(
            source_server, target_server)
        )
        target_server = await self._precheck_server_name(target_server)
        source_server = await self._precheck_server_name(source_server)
        target_srv_data = await self.get_server(target_server)
        source_srv_data = await self.get_server(source_server)
        if not target_srv_data:
            return False, 'Server target tidak terdaftar di naoTimes.'
        if not source_srv_data:
            return False, 'Server awal tidak terdaftar di naoTimes.'

        res, msg = await self.update_data_server(source_server, srv1_data)
        print('[ntDB] INFO: Acknowledged? {}'.format(res))
        print('[ntDB] Message: {}'.format(msg))
        res, msg = await self.update_data_server(target_server, srv2_data)
        print('[ntDB] INFO: Acknowledged? {}'.format(res))
        print('[ntDB] Message: {}'.format(msg))
        return res, msg

    async def kolaborasi_batalkan(self, server, confirm_id):
        print('[ntDB] INFO: Cancelling collaboration with: {}'.format(server))
        server = await self._precheck_server_name(server)
        srv_data = await self.get_server(server)
        if not srv_data:
            return False, 'Server tidak terdaftar di naoTimes.'

        if confirm_id in srv_data['kolaborasi']:
            del srv_data['kolaborasi'][confirm_id]
        res, msg = await self.update_data_server(server, srv_data)
        return res, msg

    async def kolaborasi_putuskan(self, server, anime):
        print('[ntDB] INFO: Aborting collaboration from server: {}'.format(server))
        server = await self._precheck_server_name(server)
        srv_data = await self.get_server(server)
        if not srv_data:
            return False, 'Server tidak terdaftar di naoTimes.'

        if anime not in srv_data['anime']:
            return False, 'Anime tidak dapat ditemukan.'

        if 'kolaborasi' not in srv_data['anime'][anime]:
            return False, 'Tidak ada kolaborasi yang terdaftar'

        for osrv in srv_data['anime'][anime]['kolaborasi']:
            print('[ntDB] Removing {} from: {}'.format(server, osrv))
            osrv = await self._precheck_server_name(osrv)
            osrvd = await self.get_server(osrv)
            klosrv = deepcopy(osrvd['anime'][anime]['kolaborasi'])
            klosrv.remove(server[4:])

            remove_all = False
            if len(klosrv) == 1:
                if klosrv[0] == osrv[4:]:
                    remove_all = True

            if remove_all:
                del osrvd['anime'][anime]['kolaborasi']
            else:
                osrvd['anime'][anime]['kolaborasi'] = klosrv
            res, msg = await self.update_data_server(osrv, osrvd)
            print('[ntDB] INFO: Acknowledged? {}'.format(res))
            print('[ntDB] Message: {}'.format(msg))

        del srv_data['anime'][anime]['kolaborasi']

        res, msg = await self.update_data_server(server, srv_data)
        return res, msg


if __name__ == "__main__":
    ntdb = naoTimesDB("localhost", 13307, "naotimesdb")
    import asyncio
    loop = asyncio.get_event_loop()
    x = loop.run_until_complete(ntdb.fetch_all_as_json())
    print(x.keys())
    loop.close()

    #ntdb.get_server("")
