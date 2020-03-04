import pymongo
import motor.motor_asyncio

class naoTimesDB:
    """
    "Pembungkus" modul Motor (PyMongo) untuk database naoTimes
    Modul ini dibuat untuk kebutuhan khusus naoTimes dan sebagainya.
    """
    def __init__(self, ip_hostname, port, dbname="naotimesdb"):
        self.client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://{}:{}".format(ip_hostname, port))
        self.db = self.client[dbname]
        self.srv_re = {"name": {"$regex": r"^srv"}}

    async def _precheck(self, namae):
        if not isinstance(namae, str):
            namae = str(namae)
        if not namae.startswith("srv_"):
            namae = "srv_" + namae
        return namae

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
        if adm_id not in adm_list:
            adm_list.append(str(adm_id))
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
        server = await self._precheck(server)
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
        server = await self._precheck(server)
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        if server not in srv_list:
            print('[ntDB] WARN: cannot found server in database.')
            return False, 'Server tidak terdaftar di database, gunakan metode `new_server`'
        print('[ntDB] INFO: Updating data for server: {}'.format(server))

        srv = self.db[server]
        res = await srv.update_one({}, dataset)
        if res.acknowledged:
            print('[ntDB] INFO: Server data updated.')
            return True, 'Updated'
        print('[ntDB] ERROR: Failed to update server data.')
        return False, 'Gagal mengupdate server data.'

    async def new_server(self, server, dataset):
        server = await self._precheck(server)
        srv_list = await self.db.list_collection_names(filter=self.srv_re)
        if server in srv_list:
            print('[ntDB] WARN: found server in database, please use `update_data` method')
            return False, 'Server terdaftar di database, gunakan metode `update_data`'
        print('[ntDB] INFO: Adding data for a new server: {}'.format(server))

        srv = self.db[server]
        res = await srv.insert_one(dataset, check_keys=False)
        if res.acknowledged:
            print('[ntDB] INFO: Server data updated.')
            return True, 'Updated'
        print('[ntDB] ERROR: Failed to update server data.')
        return False, 'Gagal mengupdate server data.'


if __name__ == "__main__":
    ntdb = naoTimesDB("localhost", 13307, "naotimesdb")
    import asyncio
    loop = asyncio.get_event_loop()
    x = loop.run_until_complete(ntdb.fetch_all_as_json())
    print(x.keys())
    loop.close()

    #ntdb.get_server("")