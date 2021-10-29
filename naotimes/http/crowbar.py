"""
A Steam status checker for naoTimes.

This check is mostly the same as what is done by steamstat.us

---

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
import time
from enum import Enum
from typing import Dict, NamedTuple, Optional, Tuple, Union

import aiohttp
import arrow

from ..utils import complex_walk

__all__ = (
    "ServerLoad",
    "ServerStatus",
    "CrowbarStatus",
    "CrowbarClient",
)


class ServerLoad(Enum):
    IDLE = "idle"
    LOW = "low"
    NORMAL = "normal"
    MEDIUM = "medium"
    HIGH = "high"
    SURGE = "surge"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


class ServerStatus(Enum):
    NORMAL = "Normal"
    SLOW = "Very Slow"
    UNAVAILABLE = "Service Unavailable"
    OFFLINE = "Offline"
    UNKNOWN = "Unknown"


RequestResult = Tuple[ServerStatus, Optional[dict]]


class API:
    def __init__(self, url: str, params: list = [], request_only: bool = False):
        self.url = url
        self.params = params
        self.request_only = request_only

    def bucket(self, param_value: dict = {}):
        base_url = self.url
        parsed_param = []
        if self.params:
            for param in self.params:
                if param in param_value:
                    parsed_param.append(f"{param}={param_value[param]}")
        if param_value:
            base_url = f"{base_url}?{'&'.join(parsed_param)}"
        return base_url

    def __str__(self):
        return self.bucket({})

    def __eq__(self, other: Union[str, "API"]):
        if isinstance(other, API):
            return self.url == other.url
        elif isinstance(other, str):
            return self.url == other
        return False


class CrowbarAPI:
    # Steam Services
    ONLINE = API("https://www.valvesoftware.com/en/about/stats")
    STORE = API("https://store.steampowered.com/", request_only=True)
    COMMUNITY = API("https://steamcommunity.com/", request_only=True)
    WEBAPI = API("https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/")

    # Game coordinator (check via WebAPI)
    CSGOGC = API("https://api.steampowered.com/IGCVersion_730/GetServerVersion/v1")
    TF2GC = API("https://api.steampowered.com/IGCVersion_440/GetServerVersion/v1")
    DOTA2GC = API("https://api.steampowered.com/IGCVersion_570/GetServerVersion/v1")
    UNDERLORDSGC = API("https://api.steampowered.com/IGCVersion_1046930/GetServerVersion/v1")
    ARTIFACTGC = API("https://api.steampowered.com/IGCVersion_583950/GetServerVersion/v1")
    # https://developer.valvesoftware.com/wiki/Steam_Web_API#GetServerInfo

    # CS:GO Manager (check via WebAPI)
    # SessionsLogon: Sessions Logon
    # Leaderboards: Player Inventories
    # matchmaking.scheduler: Matchmaking Scheduler
    # datacenters: Region Data
    CSGO = API("https://api.steampowered.com/ICSGOServers_730/GetGameServersStatus/v1", ["key"])


class CSGODatacenter(NamedTuple):
    name: str
    status: ServerLoad = ServerLoad.UNKNOWN


class CrowbarCSGODatacenterStatus:
    _cs_eu_east: ServerLoad = ServerLoad.UNKNOWN
    _cs_eu_north: ServerLoad = ServerLoad.UNKNOWN
    _cs_eu_west: ServerLoad = ServerLoad.UNKNOWN
    _cs_poland: ServerLoad = ServerLoad.UNKNOWN
    _cs_spain: ServerLoad = ServerLoad.UNKNOWN
    _cs_us_northeast: ServerLoad = ServerLoad.UNKNOWN
    _cs_us_southwest: ServerLoad = ServerLoad.UNKNOWN
    _cs_us_northcentral: ServerLoad = ServerLoad.UNKNOWN
    _cs_us_northwest: ServerLoad = ServerLoad.UNKNOWN
    _cs_us_southeast: ServerLoad = ServerLoad.UNKNOWN
    _cs_australia: ServerLoad = ServerLoad.UNKNOWN
    _cs_brazil: ServerLoad = ServerLoad.UNKNOWN
    _cs_argentina: ServerLoad = ServerLoad.UNKNOWN
    _cs_chile: ServerLoad = ServerLoad.UNKNOWN
    _cs_emirates: ServerLoad = ServerLoad.UNKNOWN
    _cs_india: ServerLoad = ServerLoad.UNKNOWN
    _cs_india_east: ServerLoad = ServerLoad.UNKNOWN
    _cs_peru: ServerLoad = ServerLoad.UNKNOWN
    _cs_japan: ServerLoad = ServerLoad.UNKNOWN
    _cs_hong_kong: ServerLoad = ServerLoad.UNKNOWN
    _cs_singapore: ServerLoad = ServerLoad.UNKNOWN
    _cs_south_africa: ServerLoad = ServerLoad.UNKNOWN
    _cs_china_shanghai: ServerLoad = ServerLoad.UNKNOWN
    _cs_china_guangzhou: ServerLoad = ServerLoad.UNKNOWN
    _cs_china_tianjin: ServerLoad = ServerLoad.UNKNOWN

    __NAME_MAPS = {
        "eu_east": "Vienna, AT",
        "eu_north": "Stockholm, SWE",
        "poland": "Warsaw, PL",
        "spain": "Madrid, SPA",
        "eu_west": "Frankfurt, DE",
        "us_northeast": "Sterling, DC, USA",
        "us_southwest": "Los Angeles, CA, USA",
        "us_northcentral": "Chicago, USA",
        "us_northwest": "Moses Lake, WA, USA",
        "us_southeast": "Atlanta, GA, USA",
        "australia": "Sydney, AUS",
        "brazil": "Sao Paulo, BRA",
        "argentina": "Buenos Aires, ARG",
        "chile": "Santiago, CHI",
        "emirates": "Dubai, UAE",
        "india": "Mumbai, IND",
        "india_east": "Chennai, IND",
        "peru": "Lima, PE",
        "japan": "Tokyo, JP",
        "hong_kong": "Hong Kong",
        "singapore": "Singapore",
        "south_africa": "Johannesburg, SA",
        "china_shanghai": "Shanghai, CN",
        "china_guangzhou": "Guangzhou, CN",
        "china_tianjin": "Tianjin, CN",
    }

    def __init__(self, datacenters: Dict[str, Dict[str, str]]):
        for server_name, server_status in datacenters.items():
            server_name = server_name.lower().replace(" ", "_")
            get_server = self.__NAME_MAPS.get(server_name)
            if get_server:
                setattr(self, "_cs_" + server_name, ServerLoad(server_status.get("load", "unknown")))

    def __getattribute__(self, name: str) -> Optional[CSGODatacenter]:
        if name.startswith("_"):
            return super().__getattribute__(name)
        datacenter = getattr(self, "_cs_" + name, None)
        if datacenter is None:
            return None
        get_name = self.__NAME_MAPS.get(name)
        return CSGODatacenter(get_name, datacenter)

    def __iter__(self):
        all_data = self.__dir__()
        for name in all_data:
            if not name.startswith("_cs"):
                continue
            real_name = self.__NAME_MAPS.get(name[4:])
            yield CSGODatacenter(real_name, getattr(self, name))


class CrowbarCSGOConnectionStatus:
    sessions: ServerLoad = ServerLoad.UNKNOWN
    inventories: ServerLoad = ServerLoad.UNKNOWN
    matchmaking: ServerLoad = ServerLoad.UNKNOWN
    datacenters: CrowbarCSGODatacenterStatus = CrowbarCSGODatacenterStatus({})

    def __init__(self, **kwargs):
        for kw_name, kw_val in kwargs.items():
            setattr(self, kw_name, kw_val)


class CrowbarCoordinatorStatus:
    tf2: ServerStatus = ServerStatus.UNKNOWN
    dota2: ServerStatus = ServerStatus.UNKNOWN
    csgo: ServerStatus = ServerStatus.UNKNOWN
    underlords: ServerStatus = ServerStatus.UNKNOWN
    artifact: ServerStatus = ServerStatus.UNKNOWN

    def __init__(self, **kwargs):
        for kw_name, kw_val in kwargs.items():
            setattr(self, kw_name, kw_val)


class CrowbarStatus:
    online_count: int = 0
    ingame_count: int = 0
    store: ServerStatus = ServerStatus.UNKNOWN
    community: ServerStatus = ServerStatus.UNKNOWN
    webapi: ServerStatus = ServerStatus.UNKNOWN

    # Game coordinator
    coordinator: CrowbarCoordinatorStatus = CrowbarCoordinatorStatus()

    # Extra CS:GO status
    csgo: CrowbarCSGOConnectionStatus = CrowbarCSGOConnectionStatus()

    # timestamp
    timestamp: arrow.Arrow = None

    def __init__(self, **kwargs):
        for kw_name, kw_val in kwargs.items():
            setattr(self, kw_name, kw_val)
        self.timestamp = arrow.utcnow()

    def update(self):
        self.timestamp = arrow.utcnow()


def parse_count(data: str) -> int:
    if not data:
        return 0
    data = data.replace(",", "")
    try:
        return int(float(data))
    except ValueError:
        return 0


class CrowbarClient:
    CACHE_BUST: int = 2 * 60

    def __init__(self, api_key: str, session: aiohttp.ClientSession = None):
        if not api_key:
            raise ValueError("Missing API key")
        self.logger = logging.getLogger("http.CrowbarClient")

        self._outside_session = True
        self.session = session
        if self.session is None:
            self._outside_session = False
            self.session = aiohttp.ClientSession(
                {"User-Agent": "CrowbarClient/v1.0 (https://github.com/naoTimesdev/naoTimes)"}
            )

        self.api_key = api_key
        self._CACHE: Optional[CrowbarStatus] = None

    async def close(self):
        if not self._outside_session:
            await self.session.close()

    def set_cache_duration(self, duration: int) -> None:
        if duration < 0:
            raise ValueError("Invalid cache duration")
        self.CACHE_BUST = duration

    async def _request(self, api_route: API) -> RequestResult:
        final_url = api_route.bucket()
        if api_route.params:
            final_url = api_route.bucket({"key": self.api_key})

        req_start = time.perf_counter()

        async with self.session.get(final_url) as response:
            req_end = time.perf_counter()
            route_delta = req_end - req_start
            if response.status == 500:
                return (ServerStatus.UNKNOWN, None)
            elif response.status == 503:
                return (ServerStatus.UNAVAILABLE, None)
            server_stat = ServerStatus.SLOW if route_delta >= 2.5 else ServerStatus.NORMAL
            if api_route.request_only:
                return (server_stat, None)
            try:
                json_response = await response.json()
                return (server_stat, json_response)
            except Exception:
                return (ServerStatus.UNKNOWN, None)

    async def get_status(self) -> CrowbarStatus:
        current_time = arrow.utcnow().int_timestamp
        if self._CACHE is not None:
            cache_bust = self._CACHE.timestamp.int_timestamp + self.CACHE_BUST
            if current_time < cache_bust:
                return self._CACHE

        async def _internal_req(api_route: API) -> Tuple[RequestResult, API]:
            self.logger.debug(f"Requesting route: {api_route}")
            return (await self._request(api_route), api_route)

        request_task = [
            # Services
            _internal_req(CrowbarAPI.ONLINE),
            _internal_req(CrowbarAPI.STORE),
            _internal_req(CrowbarAPI.COMMUNITY),
            _internal_req(CrowbarAPI.WEBAPI),
            # Game coordinator
            _internal_req(CrowbarAPI.CSGOGC),
            _internal_req(CrowbarAPI.TF2GC),
            _internal_req(CrowbarAPI.DOTA2GC),
            _internal_req(CrowbarAPI.UNDERLORDSGC),
            _internal_req(CrowbarAPI.ARTIFACTGC),
            # CS:GO Manager
            _internal_req(CrowbarAPI.CSGO),
        ]

        crowbar_stat = CrowbarStatus()
        for task in asyncio.as_completed(request_task):
            multi_results, api_route = await task
            self.logger.info(f"Parsing route info: {api_route}")
            server_status, json_data = multi_results
            if api_route == CrowbarAPI.STORE:
                crowbar_stat.store = server_status
            elif api_route == CrowbarAPI.COMMUNITY:
                crowbar_stat.community = server_status
            elif api_route == CrowbarAPI.WEBAPI:
                crowbar_stat.webapi = server_status
            elif api_route == CrowbarAPI.ONLINE:
                online_count = complex_walk(json_data, "users_online")
                ingame_count = complex_walk(json_data, "users_ingame")
                if online_count is not None:
                    crowbar_stat.online_count = parse_count(online_count)
                if ingame_count is not None:
                    crowbar_stat.ingame_count = parse_count(ingame_count)
            elif api_route == CrowbarAPI.CSGOGC:
                crowbar_stat.coordinator.csgo = server_status
            elif api_route == CrowbarAPI.TF2GC:
                crowbar_stat.coordinator.tf2 = server_status
            elif api_route == CrowbarAPI.DOTA2GC:
                crowbar_stat.coordinator.dota2 = server_status
            elif api_route == CrowbarAPI.UNDERLORDSGC:
                crowbar_stat.coordinator.underlords = server_status
            elif api_route == CrowbarAPI.ARTIFACTGC:
                crowbar_stat.coordinator.artifact = server_status
            elif api_route == CrowbarAPI.CSGO:
                sess_logon = complex_walk(json_data, "result.services.SessionsLogon") or "unknown"
                player_inv = complex_walk(json_data, "result.services.Leaderboards") or "unknown"
                matchmaking = complex_walk(json_data, "result.matchmaking.scheduler") or "unknown"
                datacenters = complex_walk(json_data, "result.datacenters") or {}
                csgo = CrowbarCSGOConnectionStatus(
                    sessions=ServerLoad(sess_logon),
                    inventories=ServerLoad(player_inv),
                    matchmaking=ServerLoad(matchmaking),
                    datacenters=CrowbarCSGODatacenterStatus(datacenters),
                )
                crowbar_stat.csgo = csgo

        crowbar_stat.update()
        self._CACHE = crowbar_stat
        return crowbar_stat
