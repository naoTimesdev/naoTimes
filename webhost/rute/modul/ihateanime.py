import json
import math
from typing import Optional, TypeVar, Union

import diskcache


class ihateanimeCache:
    def __init__(self):
        print('[!#!] Starting cache server.')
        self.cachedb = diskcache.Cache('cache_data/')
        self.ping()

    def get(self, key: str) -> Union[None, str, bytes]:
        """Get a value from a key, return None if there's KeyError

        :param key: cache key
        :type key: str
        :return: value of a key.
        :rtype: Union[None, str, bytes]
        """
        print('[#] Getting key: {}'.format(key))
        try:
            val = self.cachedb.get(key=key, default=None, retry=True)
        except KeyError:
            val = None
        except TimeoutError:
            val = None
        return val

    def set(self, key: str, val: Union[str, bytes, dict, list]) -> bool:
        """Set a value to a key

        :param key: cache key
        :type key: str
        :param val: cache value
        :type val: Union[str, bytes, dict, list]
        :return: see result
        :rtype: bool
        """
        print('[#] Setting key: {}'.format(key))
        if isinstance(val, dict):
            val = json.dumps(val)
        elif isinstance(val, (list, tuple)):
            val = str(val)
        res = self.cachedb.set(key, val, retry=True)
        return res

    def setex(self, key: str, expired: Union[int, float], val: Union[str, bytes, dict, list]) -> bool:
        """Set a value to a key with expiration time

        :param key: cache key
        :type key: str
        :param expired: expiring time since current epoch time
        :type expired: Union[int, float]
        :param val: cache value
        :type val: Union[str, bytes, dict, list]
        :return: see result
        :rtype: bool
        """
        print('[#] Setting key: {}\n[#] Expiring on: {}'.format(key, expired))
        if isinstance(val, dict):
            val = json.dumps(val)
        elif isinstance(val, (list, tuple)):
            val = str(val)
        if isinstance(expired, float):
            expired = math.ceil(expired)
        res = self.cachedb.set(key, val, expire=expired)
        return res

    def expire(self):
        print('[#] Expiring keys...')
        self.cachedb.expire()

    def delete(self, key: str):
        """
        Delete key

        :param key: str: key to delete
        """
        print('[#] Deleting key: {}'.format(key))
        try:
            self.cachedb.delete(key, True)
        except TimeoutError:
            pass
        except Exception:
            pass

    def drop_info(self):
        for i in self.cachedb.iterkeys():
            if i.isdigit():
                self.cachedb.delete(i)
                print(f'Deleted: {i}')

    def drop_thumbs(self):
        amount = 0
        for i in self.cachedb.iterkeys():
            if 't.nhentai' in i:
                self.cachedb.delete(i)
                amount += 1
        print(f'Dropped a total of {amount} nh thumbnail cache')

    def drop_images(self):
        amount = 0
        for i in self.cachedb.iterkeys():
            if 'i.nhentai' in i:
                self.cachedb.delete(i)
                amount += 1
        print(f'Dropped a total of {amount} nh image cache')

    def ping(self):
        """
        Test cache client connection
        """
        print('[!] PINGING CacheServer')
        ping = self.get('ping')
        if not ping:
            res = self.set('ping', 'pong')
            if not res:
                print('[!!] Failed setting up CacheServer, exiting...')
                exit(1)
            ping = self.get('ping')

        if ping != 'pong':
            print('[!!] Failed setting up CacheServer, exiting...')
            exit(1)

        print('[!] PONG!')
