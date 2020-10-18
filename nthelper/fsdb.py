import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import AnyStr, List, Optional, Tuple, Union

import aiohttp
import ujson


class FansubDBBridge:
    def __init__(self, username, password, loop=None):
        self.logger = logging.getLogger("nthelper.fsdb.FansubDBBridge")
        self.session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "User-Agent": "naoTimes/2.0.1a (https://github.com/noaione/naoTimes)",
                "x-requested-by": "naoTimes-FSDB-Bridge",
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
        self._wib_tz = timezone(timedelta(hours=7))

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

    async def request_api(self, method: str, endpoint: str, **kwargs):
        url = f"{self.BASE_API}/{endpoint}"
        self.logger.info(f"{method}: request to {endpoint}")
        res = await self.request_db(method, url, **kwargs)
        data = ujson.loads(res)
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
        ctime = datetime.now(tz=timezone.utc).timestamp()
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

    async def fetch_animes(self) -> List[dict]:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        anime_list: List[dict] = await self.request_api("get", "anime/list", headers=headers)
        anime_list.sort(key=lambda x: x["id"])
        for data in anime_list:
            data["mal_id"] = int(data["mal_id"])
        return anime_list

    async def fetch_anime(self, anime_id: Union[int, str]) -> dict:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        anime_info: dict = await self.request_api("get", f"anime/list/{anime_id}", headers=headers)
        return anime_info

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

    async def fetch_fansubs(self, search_query: str = "") -> List[dict]:
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        fansubs_list: list = await self.request_api("get", "fansub/list", headers=headers)
        if search_query.rstrip() != "":
            fansubs_list = self.get_close_matches(search_query, fansubs_list)
        return fansubs_list

    async def fetch_anime_fansubs(self, anime_id: Union[int, str]) -> Tuple[List[dict], str]:
        if isinstance(anime_id, str):
            try:
                anime_id = int(anime_id)
            except ValueError:
                return [], "Anime ID is not a valid number."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        fansubs_list: list = await self.request_api("get", f"projek/anime/{anime_id}", headers=headers)
        return fansubs_list, "Success"

    async def fetch_fansub_projects(self, fansub_id: Union[int, str]) -> Tuple[List[dict], str]:
        if isinstance(fansub_id, str):
            try:
                fansub_id = int(fansub_id)
            except ValueError:
                return [], "Fansub ID is not a valid number."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        project_lists: list = await self.request_api("get", f"projek/fansub/{fansub_id}", headers=headers)
        return project_lists, "Success"

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
        results: dict = await self.request_api("get", f"projek/list/{project_id}", headers=headers)
        return results, "Success"

    async def update_project(
        self, project_id: Union[int, str], to_update: str, update_data: Optional[Union[int, str, List[int]]]
    ) -> Tuple[bool, str]:
        if isinstance(project_id, str):
            try:
                project_id = int(project_id)
            except ValueError:
                return False, "Project ID is not a valid number."
        await self.check_expires()
        headers = {"Authorization": f"Bearer {self._token}"}
        json_body = {to_update: update_data}
        results: dict = await self.request_api(
            "put", f"projek/list/{project_id}", json=json_body, headers=headers
        )
        if results["type"] == "success":
            return True, "Success"
        return False, results["message"]

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


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    fsdb = FansubDBBridge("", "", loop)
    # success, fs_id = loop.run_until_complete(fsdb.import_mal())
    loop.run_until_complete(fsdb.authorize())
    res, _ = loop.run_until_complete(fsdb.fetch_fansub_projects(18))
    with open("delima_projects.json", "w", encoding="utf-8") as fp:
        ujson.dump(
            res, fp, indent=4, ensure_ascii=False, encode_html_chars=False, escape_forward_slashes=False
        )
    loop.run_until_complete(fsdb.close())
