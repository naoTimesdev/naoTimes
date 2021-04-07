"""
An implementation of Wolfram API in Python
This wraps the Segment or Pods or whatever into an usable object for my bot

Made specifically for naoTimes

---

MIT License

Copyright (c) 2021 Aiman Maharana

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
import json
from typing import Any, Dict, List, Mapping, NamedTuple, Union

import aiohttp

__version__ = "2.1.0"


class WolframSubPod(NamedTuple):
    id: str
    title: str
    image: Union[str, None]
    plaintext: str


class WolframPod:
    def __init__(self, raw_data: Dict[str, Any]) -> None:
        self._RAW_DATA = raw_data
        self._parse_pod()

    def _parse_pod(self):
        if not hasattr(self, "_RAW_DATA"):
            return
        setattr(self, "_title", self._RAW_DATA.get("title"))
        id_type = self._RAW_DATA.get("id", "Unknown")
        setattr(self, "_scanner", self._RAW_DATA.get("scanner"))
        setattr(self, "_type", id_type)
        setattr(self, "_position", self._RAW_DATA.get("position"))
        subpods = self._RAW_DATA.get("subpods", [])
        collected_pods: List[WolframSubPod] = []
        for sub in subpods:
            img_data = sub.get("img", {})
            image_src = img_data.get("src")
            title = sub.get("title", "")
            if title == "" and img_data:
                title = img_data.get("alt", "")
            plaintext = sub.get("plaintext", "")
            collected_pods.append(WolframSubPod(id_type, title, image_src, plaintext))
        setattr(self, "_subpods", collected_pods)

    @property
    def title(self) -> Union[str, None]:
        return getattr(self, "_title", None)

    @property
    def scanner(self) -> Union[str, None]:
        return getattr(self, "_scanner", None)

    @property
    def type(self) -> str:
        return getattr(self, "_type", "Unknon")

    @property
    def pods(self) -> List[WolframSubPod]:
        return getattr(self, "_subpods", [])


class WolframPods:
    def __init__(self, pods: List[Dict[str, Any]]) -> None:
        self._raw_data = pods
        self._pods: List[WolframPod] = []
        for pod in pods:
            self._pods.append(WolframPod(pod))

        self._result_pods = []
        for pod in self._pods:
            if pod.type == "Result":
                self._result_pods.append(pod)

    def __next__(self):
        if len(self._result_pods) < 1:
            raise StopIteration
        # A very primitive cycling.
        first_pod = self._result_pods.pop(0)
        self._result_pods.append(first_pod)
        return first_pod

    @property
    def pods(self) -> List[WolframPod]:
        return self._pods


class WolframAPI:
    def __init__(self, app_id: str) -> None:
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{__version__} (https://github.com/noaione/naoTimes)"}
        )
        self._APP_ID = app_id
        self._on_closing = False
        self._on_queue = False

    async def close(self):
        while self._on_queue:
            if not self._on_queue:
                break
            await asyncio.sleep(0.2)
        self._on_closing = True
        await self._session.close()

    async def _request(self, question: str) -> Mapping[str, Any]:
        params = {
            "input": question,
            "output": "json",
            "appid": self._APP_ID,
            "format": "image,plaintext",
        }
        try:
            async with self._session.get("http://api.wolframalpha.com/v2/query", params=params) as resp:
                if resp.status != 200:
                    if resp.status == 501:
                        return {"error": "Input tidak dapat dipahami oleh WolframAlpha"}
                    elif resp.status == 404:
                        return {"error": "Tidak dapat hasil"}
                    return {"error": f"Mendapatkan error status {resp.status}"}
                raw_resp = await resp.text()
                try:
                    responses = json.loads(raw_resp)
                    return responses
                except ValueError:
                    return {"error": "Tidak dapat memproses hasil dari API"}
        except aiohttp.ClientError:
            return {"error": "Terjadi kesalahan internal ketika menghubungi API"}

    async def query(self, query_txt: str) -> Union[WolframPods, str]:
        requested = await self._request(query_txt)
        if "error" in requested:
            return requested["error"]
        query_res = requested["queryresult"]
        if not query_res["success"]:
            return "Tidak ada hasil"
        if query_res["error"]:
            return "Tidak ada hasil"

        return WolframPods(query_res["pods"])
