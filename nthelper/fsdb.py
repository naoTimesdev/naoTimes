import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import AnyStr, Tuple, Union
from urllib.parse import quote_plus

import aiohttp
from bs4 import BeautifulSoup

import ujson

__CHROME_UA__ = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.105 Safari/537.36"  # noqa: E501


class FansubDBBridge:
    def __init__(self):
        self.logger = logging.getLogger("nthelper.fsdb.FansubDBBridge")
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": __CHROME_UA__,
                "x-requested-by": "naoTimes-FSDB-Bridge",
                "x-requested-with": "XMLHttpRequest",
            }
        )
        self.BASE_URL = "https://db.silveryasha.web.id"
        self.AJAX_API = f"{self.BASE_URL}/ajax"
        self.CRUD_API = f"{self.BASE_URL}/crud"
        self._method_map = {
            "get": self.session.get,
            "post": self.session.post,
            "put": self.session.put,
        }
        self._wib_tz = timezone(timedelta(hours=7))

    async def close(self):
        """Close all session connection."""
        await self.session.close()

    async def request_db(self, method: str, url: str, **kwargs) -> AnyStr:
        """Request a webpage to the FansubDB website.
        Might be the API or just normal page.

        :param method: HTTP Method to use (GET, POST, PUT)
        :type method: str
        :param url: URL to fetch
        :type url: str
        :return: String or bytes from the webpage
        :rtype: AnyStr
        """
        methods = self._method_map.get(method.lower())
        async with methods(url, **kwargs) as resp:
            res = await resp.text()
        return res

    async def request_ajax(self, method: str, endpoint: str, **kwargs):
        """Request to AJAX API.

        :param method: HTTP method to use (GET, POST, PUT)
        :type method: str
        :param endpoint: Endpoint to use
        :type endpoint: str
        :return: json parsed format (dict or list)
        :rtype: Union[dict, list]
        """
        url = f"{self.AJAX_API}/{endpoint}"
        res = await self.request_db(method, url, **kwargs)
        data = ujson.loads(res)
        return data

    async def request_crud(self, method: str, endpoint: str, **kwargs):
        """Request to Crud API.

        :param method: HTTP method to use (GET, POST, PUT)
        :type method: str
        :param endpoint: Endpoint to use
        :type endpoint: str
        :return: json parsed format (dict or list)
        :rtype: Union[dict, list]
        """
        url = f"{self.CRUD_API}/{endpoint}"
        res = await self.request_db(method, url, **kwargs)
        data = ujson.loads(res)
        return res

    async def _request_csrf_token(self, anime_id=None, is_anime=True) -> str:
        """Request a CSRF Token

        :param anime_id: anime_id to use, defaults to None
        :type anime_id: int, optional
        :param is_anime: Is the CSRF needed for anime page, defaults to True
        :type is_anime: bool, optional
        :return: CSRF Token
        :rtype: str
        """
        self.logger.info(f"fetching csrf token for {anime_id}")
        fetch_page = f"{self.BASE_URL}"
        if is_anime:
            fetch_page += "/anime"
        if anime_id is not None:
            fetch_page += f"/{anime_id}"
        res = await self.request_db("get", fetch_page)
        soup = BeautifulSoup(res, "html.parser")
        csrf_token = soup.find("meta", {"name": "csrf-token"})
        return csrf_token["content"]

    async def fetch_id_garapan(self, id_garapan: str) -> Union[dict, str]:
        self.logger.info(f"fetching {id_garapan}...")
        endpoint = f"project/anime/get?id={id_garapan}"
        response: dict = await self.request_ajax("get", endpoint)
        if "message" in response:
            return response["message"]
        project = response["projek"]
        proper_data_map = {
            "id": id_garapan,
            "anime_id": project["anime_id"],
            "flag": project["flag"] if project["flag"] is not None else "",
            "status": project["status"],
            "type": project["type"],
            "status": project["status"],
            "url": project["url"] if project["url"] is not None else "",
            "misc": project["misc"] if project["misc"] is not None else "",
            "fansub": response["fansub"]
        }
        return proper_data_map

    async def tambah_garapan(self, anime_id, fansub_id, is_movie=False) -> Tuple[bool, str]:
        if not isinstance(anime_id, int):
            try:
                anime_id = int(anime_id)
            except Exception:
                return False, "anime_id bukanlah angka."
        if not isinstance(fansub_id, int):
            try:
                fansub_id = int(fansub_id)
            except Exception:
                return False, "fansub_id bukanlah angka."
        data_baru = {
            "_method": "post",
            "_id": "",
            "anime_id": anime_id,
            "fansub[]": [fansub_id],
            "flag": "",
            "type": "BD" if is_movie else "TV",
            "status": "Tentatif",
            "url": "",
            "misc": "",
        }
        data_baru["_token"] = await self._request_csrf_token(data_baru["anime_id"])
        accept_head = {
            "accept": "application/json, text/javascript, */*; q=0.01"
        }
        self.logger.info(f"fs{fansub_id}: menambah garapan untuk anime id {anime_id}...")
        res = await self.request_crud("post", "project_anime", data=data_baru, headers=accept_head)
        if "type" not in res:
            self.logger.error(f"fs{fansub_id}: terjadi kesalahan: {res['message']}")
            return False, res["message"]
        self.logger.info(f"fs{fansub_id}: sukses!")
        return True, "Success."

    async def ubah_data(self, data_baru: dict) -> Tuple[bool, str]:
        data_baru["_token"] = await self._request_csrf_token(data_baru["anime_id"])
        if "_id" not in data_baru:
            data_baru["_id"] = int(data_baru["id"])
            del data_baru["id"]
        if "fansub[]" not in data_baru:
            data_baru["fansub[]"] = data_baru["fansub"]
            del data_baru["fansub"]
        data_baru["_method"] = "PUT"
        accept_head = {
            "accept": "application/json, text/javascript, */*; q=0.01"
        }
        self.logger.info(f"{data_baru['_id']}: mengubah data...")
        res = await self.request_crud("post", "project_anime", data=data_baru, headers=accept_head)
        if "type" not in res:
            self.logger.error(f"{data_baru['_id']}: terjadi kesalahan: {res['message']}")
            return False, res["message"]
        self.logger.info(f"{data_baru['_id']}: sukses!")
        return True, "Success."

    async def ubah_status(self, id_garapan: str, status: str) -> Tuple[bool, str]:
        status_allow = ["jalan", "tamat", "tentatif", "drop"]
        status = status.lower()
        if status not in status_allow:
            self.logger.error(f"{id_garapan}: jenis status tidak diketahui...")
            return False, "Jenis status tidak diketahui."
        self.logger.info(f"{id_garapan}: mengambil data...")
        garapan = await self.fetch_id_garapan(id_garapan)
        if isinstance(garapan, str):
            self.logger.error(f"{id_garapan}: terjadi kesalahan: {garapan}")
            return False, garapan
        self.logger.info(f"{id_garapan}: mengubah status ke `{status}`...")
        garapan["status"] = status.capitalize()
        res, msg = await self.ubah_data(garapan)
        return True, "Sukses."

    async def ubah_bendera(self, id_garapan: str, bendera: str) -> Tuple[bool, str]:
        self.logger.info(f"{id_garapan}: mengambil data...")
        garapan = await self.fetch_id_garapan(id_garapan)
        if isinstance(garapan, str):
            self.logger.error(f"{id_garapan}: terjadi kesalahan: {garapan}")
            return False, garapan
        self.logger.info(f"{id_garapan}: mengubah bendera ke `{bendera}`...")
        garapan["flag"] = bendera
        res, msg = await self.ubah_data(garapan)
        return True, "Sukses."

    async def tambah_anime(self, mal_id):
        self.logger.info(f"{mal_id}: adding to fansub db")
        csrf_token = await self._request_csrf_token()
        mal_data = {
            "_token": csrf_token,
            "mal_url": f"https://myanimelist.net/anime/{mal_id}/",
        }
        accept_head = {
            "accept": "application/json, text/javascript, */*; q=0.01"
        }
        res = await self.request_crud("post", "import_mal", data=mal_data, headers=accept_head)
        if "type" not in res:
            self.logger.error(f"{mal_id}: terjadi kesalahan: {res['message']}")
            return False, res["message"]
        self.logger.info(f"{mal_id}: sukses!")
        return True, "Success."

    def _dict_to_params(self, dictmap: dict) -> str:
        params = []
        for key, val in dictmap.items():
            if val is None:
                val = ""
            if not isinstance(val, str):
                val = str(val)
            params.append(f"{quote_plus(key)}={quote_plus(val)}")
        return "&".join(params)

    async def fetch_fansubs(self, filter_fs=None) -> Tuple[bool, Union[list, str]]:
        parameters = {
            "draw": 1,
            "columns[0][data]": "name",
            "columns[0][name]": "",
            "columns[0][searchable]": "true",
            "columns[0][orderable]": "true",
            "columns[0][search][value]": "",
            "columns[0][search][regex]": "false",
            "columns[1][data]": "garapan",
            "columns[1][name]": "",
            "columns[1][searchable]": "true",
            "columns[1][orderable]": "true",
            "columns[1][search][value]": "",
            "columns[1][search][regex]": "false",
            "columns[2][data]": "garapan_now",
            "columns[2][name]": "",
            "columns[2][searchable]": "true",
            "columns[2][orderable]": "true",
            "columns[2][search][value]": "",
            "columns[2][search][regex]": "false",
            "columns[3][data]": "status",
            "columns[3][name]": "",
            "columns[3][searchable]": "true",
            "columns[3][orderable]": "true",
            "columns[3][search][value]": "",
            "columns[3][search][regex]": "false",
            "columns[4][data]": "tautan",
            "columns[4][name]": "",
            "columns[4][searchable]": "true",
            "columns[4][orderable]": "true",
            "columns[4][search][value]": "",
            "columns[4][search][regex]": "false",
            "order[0][column]": 0,
            "order[0][dir]": "asc",
            "start": 0,
            "length": 200,
            "search[value]": filter_fs if filter_fs is not None else "",
            "search[regex]": "false",
            "type": "anime",
            "status": "",
        }
        log_txt = "requesting all fansubs data..."
        if filter_fs is not None:
            log_txt = f"requesting `{filter_fs}`..."
        self.logger.info(log_txt)
        csrf_token = await self._request_csrf_token(is_anime=False)
        parameters["_token"] = csrf_token
        ctime = int(round(datetime.now(self._wib_tz).timestamp() * 1000))
        parameters["_"] = ctime
        parsed_param = self._dict_to_params(parameters)
        self.logger.debug(f"parsed parameters to send: {parsed_param}")
        resp = await self.request_ajax("get", f"fansub/search?{parsed_param}")
        if "data" not in resp:
            self.logger.error(f"error occured: {resp['message']}")
            return False, resp["message"]
        dataset: list = resp["data"]
        if dataset:
            dataset.sort(key=lambda x: x["id"])
        return True, dataset

    async def fetch_anime(self, filter_ani=None) -> Tuple[bool, Union[list, str]]:
        parameters = {
            "draw": 1,
            "columns[0][data]": "type",
            "columns[0][name]": "type",
            "columns[0][searchable]": "true",
            "columns[0][orderable]": "true",
            "columns[0][search][value]": "",
            "columns[0][search][regex]": "false",
            "columns[1][data]": "title_url",
            "columns[1][name]": "title",
            "columns[1][searchable]": "true",
            "columns[1][orderable]": "true",
            "columns[1][search][value]": "",
            "columns[1][search][regex]": "false",
            "columns[2][data]": "season_id",
            "columns[2][name]": "season_id",
            "columns[2][searchable]": "true",
            "columns[2][orderable]": "true",
            "columns[2][search][value]": "",
            "columns[2][search][regex]": "false",
            "columns[3][data]": "garapan",
            "columns[3][name]": "garapan",
            "columns[3][searchable]": "true",
            "columns[3][orderable]": "true",
            "columns[3][search][value]": "",
            "columns[3][search][regex]": "false",
            "order[0][column]": 1,
            "order[0][dir]": "asc",
            "start": 0,
            "length": 2000,
            "search[value]": filter_ani if filter_ani is not None else "",
            "search[regex]": "false",
        }
        log_txt = "requesting all anime data..."
        if filter_ani is not None:
            log_txt = f"requesting `{filter_ani}`..."
        self.logger.info(log_txt)
        ctime = int(round(datetime.now(self._wib_tz).timestamp() * 1000))
        parameters["_"] = ctime
        parsed_param = self._dict_to_params(parameters)
        self.logger.debug(f"parsed parameters to send: {parsed_param}")
        resp = await self.request_ajax("get", f"anime/dtanime?{parsed_param}")
        if "data" not in resp:
            self.logger.error(f"error occured: {resp['message']}")
            return False, resp["message"]
        dataset: list = resp["data"]
        if dataset:
            dataset.sort(key=lambda x: x["id"])
        return True, dataset
