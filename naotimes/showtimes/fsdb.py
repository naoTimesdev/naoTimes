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

import asyncio
import logging
import re
from typing import Any, AnyStr, List, Optional, Tuple, Union

import aiohttp
import arrow
import orjson

from ..models import fsdb as fsdbmodel
from ..utils import AttributeDict
from ..version import __version__ as bot_version

__all__ = ("FansubDBBridge",)


class FSDBAPIError(Exception):
    def __init__(self, code: int, message: AnyStr) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class FansubDBBridge:
    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        loop: asyncio.AbstractEventLoop = None,
    ):
        self.logger = logging.getLogger("naoTimes.FansubDB")
        self._outside_session = False
        if session is not None:
            self.session = session
            self._outside_session = True
        else:
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": f"naoTimes-FSDB/v{bot_version} (+https://github.com/noaione/naoTimes)",
                }
            )

        self._user = username
        self._pass = password
        self._loop: asyncio.AbstractEventLoop = loop
        if loop is None:
            self._loop = asyncio.get_event_loop()
        self.BASE_URL = "https://db.silveryasha.web.id"
        self.BASE_API = f"{self.BASE_URL}/api"
        self._method_map = {
            "get": self.session.get,
            "post": self.session.post,
            "put": self.session.put,
            "delete": self.session.delete,
        }

        self._token = ""  # noqa: E501
        self._expire = None

        # self._loop.run_until_complete(self.authorize())

    @property
    def token_data(self):
        return {"token": self._token, "expires": self._expire}

    def set_token(self, token: str, expires: Optional[Union[int, float]]):
        self._token = token
        self._expire = expires

    @staticmethod
    def get_close_matches(target: str, lists: list) -> list:
        """
        Find close matches from input target
        Sort everything if there's more than 2 results
        """
        target_compiler = re.compile("({})".format(target), re.IGNORECASE)
        return [fres for fres in lists if target_compiler.search(fres["name"])]

    async def close(self):
        """Close all session connection."""
        if not self._outside_session:
            await self.session.close()

    async def request_db(self, method: str, url: str, **kwargs) -> Tuple[AnyStr, int]:
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
        main_headers = kwargs.pop("headers", {})
        all_headers = {"Content-Type": "application/json", "X-Requested-With": "naoTimes-FansubDB"}
        if self._token:
            all_headers["Authorization"] = f"Bearer {self._token}"
        merged_headers = {**main_headers, **all_headers}
        resp: aiohttp.ClientResponse
        async with methods(url, headers=merged_headers, **kwargs) as resp:
            res = await resp.text()
            code = resp.status
        return res, code

    async def request_api(
        self, method: str, endpoint: str, **kwargs
    ) -> Union[List[AttributeDict], AttributeDict, Any]:
        url = f"{self.BASE_API}/{endpoint}"
        json_data = kwargs.get("json", kwargs.get("data", None))
        self.logger.info(f"{method}: request to /api/{endpoint}: {json_data}")
        ret_code = 500
        try:
            res, code = await self.request_db(method, url, **kwargs)
            ret_code = code
            self.logger.debug(f"Response from {url}: {res}")
            data = orjson.loads(res)
        except orjson.JSONEncodeError as e:
            self.logger.error(f"Failed to decode JSON response: {e}")
            raise FSDBAPIError(ret_code, f"Failed to decode JSON response: {str(e)}")
        except aiohttp.ClientResponseError as e:
            self.logger.error(f"Failed to request {url}: {str(e)}")
            raise FSDBAPIError(e.status, f"Failed to request {url}: {str(e)}")
        if isinstance(data, list):
            as_attr_dict = []
            for item in data:
                try:
                    as_attr_dict.append(AttributeDict(item))
                except Exception:
                    as_attr_dict.append(item)
            return as_attr_dict
        try:
            return AttributeDict(data)
        except Exception:
            return data

    async def authorize(self):
        """
        Authorize username and password.
        """
        body = {"username": self._user, "password": self._pass}
        self.logger.info(f"Authenticating FansubDB with user {self._user}")
        res = await self.request_api("post", "pintusorga", json=body)
        if res["type"] == "success":
            self.logger.info("Successfully logged in.")
            self._token = res["token"]
        else:
            self.logger.error("Failed to authenticate account, disabling fansubdb...")
            self._token = None

    async def check_expires(self):
        if self._expire is None:
            return
        if self._token == "":
            await self.authorize()
            return
        ctime = arrow.utcnow().int_timestamp
        if ctime - 300 >= self._expire:
            self.logger.info("Reauthorizing since token expired...")
            await self.authorize()

    async def find_id_from_mal(self, mal_id: int, dataset: list) -> int:
        mid_num = len(dataset) // 2
        mid_data = dataset[mid_num]
        if mid_data["mal_id"] == mal_id:
            return mid_data["id"]
        if mid_data["mal_id"] > mal_id:
            for data in dataset[:mid_num]:
                if data["mal_id"] == mal_id:
                    return data["id"]
        elif mid_data["mal_id"] < mal_id:
            for data in dataset[mid_num:]:
                if data["mal_id"] == mal_id:
                    return data["id"]
        return 0

    async def find_project_id(self, anime_id: int, dataset: list) -> int:
        dataset.sort(key=lambda x: x["anime"]["id"])
        mid_num = len(dataset) // 2
        mid_data = dataset[mid_num]
        if mid_data["anime"]["id"] == anime_id:
            return mid_data["id"]
        if mid_data["anime"]["id"] > anime_id:
            for data in dataset[:mid_num]:
                if data["anime"]["id"] == anime_id:
                    return data["id"]
        elif mid_data["anime"]["id"] < anime_id:
            for data in dataset[mid_num:]:
                if data["anime"]["id"] == anime_id:
                    return data["id"]
        return 0

    async def fetch_animes(self) -> List[fsdbmodel.FSDBAnimeData]:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            anime_list: List[dict] = await self.request_api("get", "anime/list", headers=headers)
            if isinstance(anime_list, list):
                anime_list.sort(key=lambda x: x["id"])
                return anime_list
            else:
                self.logger.error(f"Failed to get Anime list, {anime_list!r}")
                return []
        except FSDBAPIError as e:
            self.logger.error(f"Failed to fetch anime list: {str(e)}")
            return []

    async def fetch_anime(self, anime_id: Union[int, str]) -> Optional[fsdbmodel.FSDBAnimeData]:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            anime_info: dict = await self.request_api("get", f"anime/list/{anime_id}", headers=headers)
            if "type" in anime_info and anime_info["type"] == "error":
                return None
            return anime_info
        except FSDBAPIError as e:
            if e.code == 404:
                return None
            raise

    async def fetch_anime_by_mal(self, mal_id: Union[int, str]) -> Optional[fsdbmodel.FSDBAnimeData]:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            anime_info = await self.request_api("get", f"anime/mal/{mal_id}", headers=headers)
            if "type" in anime_info and anime_info["type"] == "error":
                return None
            return anime_info
        except FSDBAPIError as err:
            # Error, assume that it got 404'd
            if err.code == 404:
                return None
            raise

    async def import_mal(self, mal_id: int) -> Tuple[bool, Union[int, str]]:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        body_json = {"mal_id": mal_id}
        result = await self.request_api("post", "anime/list", json=body_json, headers=headers)
        if result["type"] == "success":
            anime_lists = await self.fetch_animes()
            anime_lists.sort(key=lambda x: x["mal_id"])
            fs_id = await self.find_id_from_mal(mal_id, anime_lists)
            return True, fs_id
        return False, result["message"]

    async def fetch_fansubs(self, search_query: str = "") -> List[fsdbmodel.FSDBFansubData]:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        fansubs_list: list = await self.request_api("get", "fansub/list", headers=headers)
        if search_query.rstrip() != "":
            fansubs_list = self.get_close_matches(search_query, fansubs_list)
        return fansubs_list

    async def fetch_anime_fansubs(
        self, anime_id: Union[int, str]
    ) -> Tuple[List[fsdbmodel.FSDBProjectData], str]:
        if isinstance(anime_id, str):
            try:
                anime_id = int(anime_id)
            except ValueError:
                return [], "Anime ID is not a valid number."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        fansubs_list: list = await self.request_api("get", f"projek/anime/{anime_id}", headers=headers)
        return fansubs_list, "Success"

    async def fetch_fansub_projects(
        self, fansub_id: Union[int, str]
    ) -> Tuple[List[fsdbmodel.FSDBProjectData], str]:
        if isinstance(fansub_id, str):
            try:
                fansub_id = int(fansub_id)
            except ValueError:
                return [], "Fansub ID is not a valid number."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            project_lists: list = await self.request_api("get", f"projek/fansub/{fansub_id}", headers=headers)
            if (
                isinstance(project_lists, dict)
                and "type" in project_lists
                and project_lists["type"] == "error"
            ):
                return [], project_lists["message"]
            return project_lists, "Success"
        except FSDBAPIError as err:
            if err.code == 404:
                return [], "Fansub ini belum ada garapan"
            return [], err.message

    async def add_new_project(
        self, anime_id: Union[int, str], fansub_id: Union[int, str, list], status: str = "Tentatif"
    ) -> Tuple[bool, Union[int, str]]:
        if isinstance(anime_id, str):
            try:
                anime_id = int(anime_id)
            except ValueError:
                return False, "Anime ID is not a valid number."
        if isinstance(fansub_id, str):
            try:
                fansub_id = int(fansub_id)
            except ValueError:
                return False, "Fansub ID is not a valid number."
        if isinstance(fansub_id, list):
            try:
                new_fs_id = []
                for fs_id in fansub_id:
                    if isinstance(fansub_id, str):
                        try:
                            fs_id = int(fs_id)
                        except ValueError:
                            return False, "Fansub ID is not a valid number."
                    new_fs_id.append(fs_id)
                fansub_id = new_fs_id
            except ValueError:
                return False, "Fansub ID is not a valid number."
        if status not in ["Tentatif", "Jalan", "Tamat", "Drop"]:
            return False, "Invalid status."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        json_body = {
            "anime_id": anime_id,
            "fansub": [fansub_id] if not isinstance(fansub_id, list) else fansub_id,
            "flag": None,
            "type": "TV",
            "subtitle": "Softsub",
            "status": status,
            "url": None,
            "misc": None,
        }
        fisrt_fs_id = fansub_id if not isinstance(fansub_id, list) else fansub_id[0]
        results: dict = await self.request_api("post", "projek/list", json=json_body, headers=headers)
        if results["type"] == "success":
            retry_count = 0
            await asyncio.sleep(0.25)
            while retry_count < 5:
                fansub_project, _ = await self.fetch_fansub_projects(fisrt_fs_id)
                project_id = await self.find_project_id(anime_id, fansub_project)
                if project_id != 0:
                    return True, project_id
                retry_count += 1
                await asyncio.sleep(1)
            return False, "Failed to fetch FansubDB Project ID, please contact N4O or mention him."
        return False, results["message"]

    async def get_project(self, project_id: Union[int, str]) -> Tuple[dict, str]:
        if isinstance(project_id, str):
            try:
                project_id = int(project_id)
            except ValueError:
                return {}, "Project ID is not a valid number."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            results: dict = await self.request_api("get", f"projek/list/{project_id}", headers=headers)
            if results["type"] == "error":
                return None
            return results
        except FSDBAPIError as err:
            if err.code == 404:
                return None
            raise

    async def _internal_update_project(
        self, project_id: Union[int, str], to_update: str, update_data: Optional[Union[int, str, List[int]]]
    ):
        res = await self.get_project(project_id)
        if not res:
            return False, "Project not found."
        headers = {"Authorization": f"Bearer {self._token}"}
        json_body = {to_update: update_data}
        if to_update == "status":
            json_body["url"] = "https://naoti.me/fsdb-landing/"
            if res.get("url") is not None:
                json_body["url"] = res["url"]
        results: dict = await self.request_api(
            "put", f"projek/list/{project_id}", json=json_body, headers=headers
        )
        if results["type"] == "success":
            return True, "Success"
        return False, results["message"]

    async def update_project(
        self,
        project_id: Union[int, str],
        to_update: str,
        update_data: Optional[Union[int, str, List[int]]],
        task_mode=True,
    ) -> Tuple[bool, str]:
        if isinstance(project_id, str):
            try:
                project_id = int(project_id)
            except ValueError:
                return False, "Project ID is not a valid number."
        await self.check_expires()
        if task_mode:
            ctime = arrow.utcnow().int_timestamp
            task_name = f"FSDB-Update-Project-{project_id}_{ctime}"
            self._loop.create_task(
                self._internal_update_project(project_id, to_update, update_data), name=task_name
            )
            return True, "Task created"
        return await self._internal_update_project(project_id, to_update, update_data)

    async def delete_project(self, project_id: Union[int, str]) -> Tuple[bool, str]:
        if isinstance(project_id, str):
            try:
                project_id = int(project_id)
            except ValueError:
                return False, "Project ID is not a valid number."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        results: dict = await self.request_api("delete", f"projek/list/{project_id}", headers=headers)
        if results["type"] == "success":
            return True, "Success"
        return False, results["message"]
