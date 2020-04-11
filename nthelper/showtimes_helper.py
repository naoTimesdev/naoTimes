from copy import deepcopy

import motor.motor_asyncio
import pymongo


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
        for collection in server_collection:
            print('[ntDB] INFO2: Fetching server: {}'.format(collection))
            srv = self.db[collection]
            srv_cur = srv.find({})
            srv = list(await srv_cur.to_list(length=100))
            srv = srv[0]
            del srv['_id']
            json_data[collection[4:]] = srv
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
                upd_data = {
                    "$set": dataset[ksrv[4:]]
                }
                while True:
                    print('\t[ntDB] Updating collection: {}'.format(ksrv))
                    srv = self.db[ksrv]
                    res = await srv.update_one({}, upd_data)
                    if res:
                        print('\t[ntDB] INFO: Updated.')
                        break
            else:
                while True:
                    srv = self.dbsync[ksrv]
                    print('\t[ntDB] INFO: Adding new data: {}'.format(ksrv))
                    res = srv.insert(dataset[ksrv[4:]], check_keys=False)
                    if res:
                        break

        upd_adm = {
            "$set": {
                "server_admin": dataset['supermod']
            }
        }
        print('[ntDB] INFO: Updating top admin...')
        while True:
            admin = self.db['server_admin']
            res = await admin.update_one({}, upd_adm)
            if res.acknowledged:
                print('[ntDB] INFO: Updated.')
                break
        print('[ntDB] IFNO: Succes patching database')
        return True

    async def get_top_admin(self):
        print('[ntDB] INFO: Fetching top admin/server admin.')
        admin = self.db['server_admin']
        admin = admin.find({})
        admin = list(await admin.to_list(length=100))
        admin = admin[0]['server_admin']
        return admin

    async def add_top_admin(self, adm_id):
        print('[ntDB] INFO: Adding new top admin/server admin.')
        adm_list = await self.get_top_admin()
        adm_id = str(adm_id)
        if adm_id in adm_list:
            return True, "Sudah ada"
        upd = {
            "$set": {
                "server_admin": adm_list
            }
        }
        admin = self.db['server_admin']
        res = await admin.update_one({}, upd)
        if res.acknowledged:
            print('[ntDB] INFO: Top admin data updated.')
            return True, 'Updated'
        print('[ntDB] ERROR: Failed to update top admin data.')
        return False, 'Gagal menambah top admin baru.'

    async def remove_top_admin(self, adm_id):
        print('[ntDB] INFO: Removing `{}` from top admin/server admin.'.format(adm_id))
        adm_list = await self.get_top_admin()
        adm_id = str(adm_id)
        if adm_id in adm_list:
            adm_list.remove(adm_id)
        upd = {
            "$set": {
                "server_admin": adm_list
            }
        }
        admin = self.db['server_admin']
        res = await admin.update_one({}, upd)
        if res.acknowledged:
            print('[ntDB] INFO: Top admin data updated.')
            return True, 'Updated'
        print('[ntDB] ERROR: Failed to update top admin data.')
        return False, 'Gagal menambah top admin baru.'

    async def get_server_list(self):
        print('[ntDB] INFO: Fetching server list')
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        srv_list = [s[s.find('_')+1:] for s in srv_list]
        return srv_list

    async def get_server(self, server):
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Fetching server set: {}'.format(server))
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        if server not in srv_list:
            print('[ntDB] WARN: cannot found server in database.')
            return {}

        srv = self.db[server]
        srv_cur = srv.find({})
        srv = list(await srv_cur.to_list(length=100))
        srv = srv[0]
        del srv['_id']
        return srv

    async def update_data(self, server, dataset):
        dataset = {
            "$set": dataset
        }
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Updating data for server: {}'.format(server))
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        if server not in srv_list:
            print('[ntDB] WARN: cannot found server in database.')
            return False, 'Server tidak terdaftar di database, gunakan metode `new_server`'

        srv = self.db[server]
        res = await srv.update_one({}, dataset)
        if res.acknowledged:
            print('[ntDB] INFO: Server data updated.')
            return True, 'Updated'
        print('[ntDB] ERROR: Failed to update server data.')
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

        res, msg = await self.update_data(server, srv_data)
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

        res, msg = await self.update_data(server, srv_data)
        return res, msg

    async def new_server(self, server, admin_id, announce_channel = None):
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Adding data for a new server: {}'.format(server))
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        if server in srv_list:
            print('[ntDB] WARN: found server in database, please use `update_data` method')
            return False, 'Server terdaftar di database, gunakan metode `update_data`'

        dataset = {
            "serverowner": [str(admin_id)],
            "announce_channel": "",
            "anime": {},
            "alias": {},
            "konfirmasi": {}
        }

        if announce_channel:
            dataset['announce_channel'] = announce_channel

        srv = self.dbsync[server]
        res = srv.insert(dataset, check_keys=False)
        if res:
            res, msg = await self.add_top_admin(str(admin_id))
            print('[ntDB] INFO: Server data updated.')
            return res, msg if not res else "Updated."
        print('[ntDB] ERROR: Failed to add new server data.')
        return False, 'Gagal mengupdate server data.'

    async def remove_server(self, server, admin_id):
        server = await self._precheck_server_name(server)
        print('[ntDB] INFO: Expunging data for a server: {}'.format(server))
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
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

        res, msg = await self.update_data(target_server, srv_data)
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

        res, msg = await self.update_data(source_server, srv1_data)
        print('[ntDB] INFO: Acknowledged? {}'.format(res))
        print('[ntDB] Message: {}'.format(msg))
        res, msg = await self.update_data(target_server, srv2_data)
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
        res, msg = await self.update_data(server, srv_data)
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
            res, msg = await self.update_data(osrv, osrvd)
            print('[ntDB] INFO: Acknowledged? {}'.format(res))
            print('[ntDB] Message: {}'.format(msg))

        del srv_data['anime'][anime]['kolaborasi']

        res, msg = await self.update_data(server, srv_data)
        return res, msg


if __name__ == "__main__":
    ntdb = naoTimesDB("localhost", 13307, "naotimesdb")
    import asyncio
    loop = asyncio.get_event_loop()
    x = loop.run_until_complete(ntdb.fetch_all_as_json())
    print(x.keys())
    loop.close()

    #ntdb.get_server("")
