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

from __future__ import annotations

import uuid
from argparse import Namespace
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union

from discord.enums import VoiceRegion

from .utils import blocking_read_files, blocking_write_files, str_or_none, write_files

if TYPE_CHECKING:
    from pathlib import Path

__all__ = (
    "naoTimesUserPassConfig",
    "naoTimesKBBIConfig",
    "naoTimesMongoConfig",
    "naoTimesRedisConfig",
    "naoTimesSocketConfig",
    "naoTimesWeatherConfig",
    "naoTimesTicketConfig",
    "naoTimesWolframConfig",
    "naoTimesMerriamWebsterConfig",
    "naoTimesStatistics",
    "naoTimesLavaSpotifyNode",
    "naoTimesLavanodes",
    "naoTimesGeniusConfig",
    "naoTimesMusicConfig",
    "naoTimesArgParse",
    "naoTimesBotConfig",
)

BotConfig = Dict[
    str,
    Union[
        str,
        int,
        bool,
        Dict[
            str,
            Union[
                str,
                int,
                bool,
            ],
        ],
    ],
]


class naoTimesNamespace(Namespace):
    cogs_skip: List[str]
    kbbi_check: bool
    slash_check: bool
    showtimes_fetch: bool
    dev_mode: bool
    presence: bool


class ConfigParseError(Exception):
    """An exception thaat will be raised when it failed to parse
    the config.

    Attributes
    ------------
    location: :class:`str`
        The location of the error.
    reason: :class:`str`
        The reason of the error.
    """

    def __init__(self, location: str, reason: str) -> None:
        self.location: str = location
        self.reason: str = reason
        text_data = "Terjadi kesalahan ketika memproses konfigurasi!\n"
        text_data += f"Posisi error: {location}\nAlasan: {reason}"
        super().__init__(text_data)


@dataclass
class naoTimesUserPassConfig:
    username: Optional[str] = None
    password: Optional[str] = None

    @classmethod
    def parse_config(cls: Type[naoTimesUserPassConfig], config: BotConfig):
        username = config.get("username")
        password = config.get("password")
        return cls(username, password)

    def serialize(self):
        return {
            "username": str_or_none(self.username),
            "password": str_or_none(self.password),
        }


@dataclass
class naoTimesKBBIConfig:
    email: Optional[str] = None
    password: Optional[str] = None

    @classmethod
    def parse_config(cls: Type[naoTimesKBBIConfig], config: BotConfig) -> Optional[Type[naoTimesKBBIConfig]]:
        username = config.get("email")
        password = config.get("password")
        if not username and not password:
            return None
        return cls(email=username, password=password)

    def serialize(self):
        return {
            "email": self.email,
            "password": self.password,
        }


@dataclass
class naoTimesMongoConfig:
    ip_hostname: str
    port: int
    dbname: str
    tls: Optional[bool] = True
    auth: Optional[str] = None

    @classmethod
    def parse_config(cls: Type[naoTimesMongoConfig], config: BotConfig) -> Type[naoTimesMongoConfig]:
        ip_hostname = config.get("ip_hostname", "localhost")
        port = config.get("port", 27017)
        dbname = config.get("dbname", "naotimesdb")
        tls = config.get("tls", False)
        auth = config.get("auth", None)
        return cls(ip_hostname, port, dbname, tls, auth)

    def serialize(self):
        return {
            "ip_hostname": self.ip_hostname,
            "port": self.port,
            "dbname": self.dbname,
            "tls": self.tls,
            "auth": self.auth,
        }


@dataclass
class naoTimesRedisConfig:
    ip_hostname: str
    port: int
    password: Optional[str] = None

    @classmethod
    def parse_config(cls: Type[naoTimesRedisConfig], config: BotConfig) -> Type[naoTimesRedisConfig]:
        ip_hostname = config.get("ip_hostname", None)
        if ip_hostname is None:
            raise ConfigParseError(
                "redisdb.ip_hostname", "Redis dibutuhkan untuk berbagai macam fitur naoTimes!"
            )
        port = config.get("port", 6379)
        password = config.get("password", None)
        return cls(ip_hostname, port, password)

    def serialize(self):
        return {
            "ip_hostname": self.ip_hostname,
            "port": self.port,
            "password": self.password,
        }


@dataclass
class naoTimesSocketConfig:
    port: int
    password: Optional[str] = None

    @classmethod
    def parse_config(cls: Type[naoTimesSocketConfig], config: BotConfig) -> Type[naoTimesSocketConfig]:
        port = config.get("port", 25670)
        password = config.get("password", None)
        return cls(port, password)

    def serialize(self):
        return {
            "port": self.port,
            "password": str_or_none(self.password),
        }


@dataclass
class naoTimesWeatherConfig:
    openweather: Optional[str] = None
    opencage: Optional[str] = None

    @classmethod
    def parse_config(cls: Type[naoTimesWeatherConfig], config: BotConfig) -> Type[naoTimesWeatherConfig]:
        openweather = config.get("openweatherapi", None)
        opencage = config.get("opencageapi", None)
        if not openweather and not opencage:
            return None
        return cls(openweather, opencage)

    def serialize(self):
        return {
            "openweatherapi": str_or_none(self.openweather),
            "opencageapi": str_or_none(self.opencage),
        }


@dataclass
class naoTimesTicketConfig:
    id: Optional[int] = None
    srv_id: Optional[int] = None
    log_id: Optional[int] = None

    @classmethod
    def parse_config(cls: Type[naoTimesTicketConfig], config: BotConfig) -> Type[naoTimesTicketConfig]:
        id = config.get("id", None)
        srv_id = config.get("srv_id", None)
        log_id = config.get("log_id", None)
        if any(not v for v in (id, srv_id, log_id)):
            return None
        return cls(id, srv_id, log_id)

    def serialize(self):
        return {
            "id": self.id,
            "srv_id": self.srv_id,
            "log_id": self.log_id,
        }


@dataclass
class naoTimesWolframConfig:
    appid: Optional[str] = None

    @classmethod
    def parse_config(
        cls: Type[naoTimesWolframConfig], config: BotConfig
    ) -> Optional[Type[naoTimesWolframConfig]]:
        appid = config.get("app_id", None)
        if not appid:
            return None
        return cls(appid)

    def serialize(self):
        return {"app_id": str_or_none(self.appid)}


@dataclass
class naoTimesMerriamWebsterConfig:
    dictionary: Optional[str] = None
    thesaurus: Optional[str] = None

    @classmethod
    def parse_config(
        cls: Type[naoTimesMerriamWebsterConfig], config: BotConfig
    ) -> Optional[Type[naoTimesMerriamWebsterConfig]]:
        dictionary = config.get("dictionary", None)
        thesaurus = config.get("thesaurus", None)
        if not dictionary and not thesaurus:
            return None
        return cls(dictionary, thesaurus)

    def serialize(self):
        return {
            "dictionary": str_or_none(self.dictionary),
            "thesaurus": str_or_none(self.thesaurus),
        }


@dataclass
class naoTimesStatistics:
    sentry_dsn: Optional[str] = None

    @classmethod
    def parse_config(cls: Type[naoTimesStatistics], config: BotConfig) -> Type[naoTimesStatistics]:
        sentry_dsn = config.get("sentry_dsn", None)
        return cls(sentry_dsn)

    def serialize(self):
        return {"sentry_dsn": str_or_none(self.sentry_dsn)}


@dataclass
class naoTimesLavaSpotifyNode:
    id: str
    secret: str
    url: Optional[str] = None

    @classmethod
    def parse_config(cls, config: BotConfig):
        id = config.get("id", None)
        if id is None:
            raise ConfigParseError(
                "lavalink_nodes.X.spotify.id", "Spotify ID dibutuhkan untuk fitur Spotify!"
            )
        secret = config.get("secret", None)
        if secret is None:
            raise ConfigParseError(
                "lavalink_nodes.X.spotify.secret", "Spotify Secret dibutuhkan untuk fitur Spotify!"
            )
        url = config.get("url", None)
        return cls(id, secret, url)

    def serialize(self):
        return {"id": self.id, "secret": self.secret, "url": self.url}


@dataclass
class naoTimesGeniusConfig:
    client_id: Optional[str]
    client_secret: Optional[str]

    @classmethod
    def parse_config(cls: Type[naoTimesGeniusConfig], config: BotConfig) -> naoTimesGeniusConfig:
        client_id = config.get("client_id", None)
        client_secret = config.get("client_secret", None)
        return cls(client_id, client_secret)

    def serialize(self):
        return {"client_id": self.client_id, "client_secret": self.client_secret}


@dataclass
class naoTimesLavanodes:
    host: str
    port: int
    password: str
    identifier: str
    region: VoiceRegion

    @classmethod
    def parse_config(cls: Type[naoTimesLavanodes], config: BotConfig) -> Type[naoTimesLavanodes]:
        host = config.get("host", None)
        if host is None:
            raise ConfigParseError(
                "lavalink.host", "Lavalink dibutuhkan untuk berbagai macam fitur naoTimes!"
            )
        port = config.get("port", 2333)
        password = config.get("password", None)
        identifier = config.get("identifier", None)
        if identifier is None:
            idv4 = str(uuid.uuid4())
            identifier = f"potia-lava-{idv4}"
        region = config.get("region", None)
        if region is None:
            region = VoiceRegion.us_west
        else:
            region = VoiceRegion(region.replace("_", "-"))
        return cls(host, port, password, identifier, region)

    def serialize(self):
        return {
            "host": self.host,
            "port": self.port,
            "password": self.password,
            "identifier": self.identifier,
            "region": self.region.value,
        }


@dataclass
class naoTimesMusicConfig:
    nodes: List[naoTimesLavanodes] = field(default_factory=list)
    spotify: Optional[naoTimesLavaSpotifyNode] = None
    genius: Optional[naoTimesGeniusConfig] = None

    @classmethod
    def parse_config(cls: Type[naoTimesMusicConfig], config: BotConfig) -> naoTimesMusicConfig:
        lavanodes = config.get("lavalink_nodes", []) or []
        parsed_nodes = []
        for node in lavanodes:
            parsed_nodes.append(naoTimesLavanodes.parse_config(node))
        spotify_node = config.get("spotify", None)
        if spotify_node:
            spotify_node = naoTimesLavaSpotifyNode.parse_config(spotify_node)
        genius_config = config.get("genius", None)
        if genius_config:
            genius_config = naoTimesGeniusConfig.parse_config(genius_config)
        return cls(parsed_nodes, spotify_node, genius_config)

    def serialize(self):
        base = {
            "lavalink_nodes": [node.serialize() for node in self.nodes],
        }
        if self.spotify is not None:
            base["spotify"] = self.spotify.serialize()
        if self.genius is not None:
            base["genius"] = self.genius.serialize()
        return base


@dataclass
class naoTimesArgParse:
    cogs_skip: List[str] = field(default_factory=list)
    kbbi_check: bool = True
    slash_check: bool = True
    showtimes_fetch: bool = True
    parsed_ns: naoTimesNamespace = None

    @classmethod
    def parse_argparse(cls: Type[naoTimesArgParse], parsed: naoTimesNamespace) -> Type[naoTimesArgParse]:
        skipped_cogs = []
        for cogs in parsed.cogs_skip:
            if not cogs.startswith("cogs."):
                cogs = "cogs." + cogs
            skipped_cogs.append(cogs)

        sshow = skbbi = sslash = True
        if parsed.kbbi_check:
            skbbi = False
        if parsed.slash_check:
            sslash = False
        if parsed.showtimes_fetch:
            sshow = False
        return cls(skipped_cogs, skbbi, sslash, sshow, parsed)


@dataclass
class naoTimesBotConfig:
    bot_id: str
    bot_token: str
    default_prefix: str
    vndb: Optional[naoTimesUserPassConfig]
    nyaasi: Optional[naoTimesUserPassConfig]
    mongodb: Optional[naoTimesMongoConfig]
    redisdb: naoTimesRedisConfig
    socket: Optional[naoTimesSocketConfig]
    kbbi: Optional[naoTimesKBBIConfig]
    fansubdb: Optional[naoTimesUserPassConfig]
    weather: Optional[naoTimesWeatherConfig]
    log_channel: Optional[int]
    ticket: Optional[naoTimesTicketConfig]
    wolfram: Optional[naoTimesWolframConfig]
    merriam_webster: Optional[naoTimesMerriamWebsterConfig]
    crowbar_api: Optional[str]
    slash_test_guild: Optional[int]
    statistics: Optional[naoTimesStatistics]
    music: Optional[naoTimesMusicConfig]
    init_config: Optional[naoTimesArgParse] = None

    @classmethod
    def parse_config(
        cls: Type[naoTimesBotConfig], config: BotConfig, parsed_ns: naoTimesNamespace
    ) -> Type[naoTimesBotConfig]:
        bot_id = config.get("bot_id", None)
        bot_token = config.get("bot_token", None)
        default_prefix = config.get("default_prefix", None)
        if any(v is None for v in (bot_id, bot_token, default_prefix)):
            raise ConfigParseError("Missing bot_id, bot_token or default_prefix")
        parsed_mongodb = naoTimesMongoConfig.parse_config(config.get("mongodb", {}))
        parsed_redis = naoTimesRedisConfig.parse_config(config.get("redisdb", {}))
        nyaasi_config = naoTimesUserPassConfig.parse_config(config.get("nyaasi", {}))
        vndb_config = naoTimesUserPassConfig.parse_config(config.get("vndb", {}))
        sserver_config = naoTimesSocketConfig.parse_config(config.get("socketserver", {}))
        kbbi_config = naoTimesKBBIConfig.parse_config(config.get("kbbi", {}))
        fansubdb_config = naoTimesUserPassConfig.parse_config(config.get("fansubdb", {}))
        weather_config = naoTimesWeatherConfig.parse_config(config.get("weather_data", {}))
        log_channel = config.get("error_logger", None)
        if not isinstance(log_channel, int) and log_channel is not None:
            try:
                log_channel = int(log_channel)
            except ValueError:
                log_channel = None
        ticket_config = naoTimesTicketConfig.parse_config(config.get("ticketing", {}))
        wolfram_config = naoTimesWolframConfig.parse_config(config.get("wolfram", {}))
        merriam_webster_config = naoTimesMerriamWebsterConfig.parse_config(config.get("merriam_webster", {}))
        crowbar_api = config.get("steam_api_key", None)
        if not crowbar_api:
            crowbar_api = None
        statistics_config = naoTimesStatistics.parse_config(config.get("statistics", {}))
        slash_test_guild = config.get("slash_test_guild", None)
        if isinstance(slash_test_guild, (float, str)):
            try:
                slash_test_guild = int(slash_test_guild)
            except ValueError:
                slash_test_guild = None

        music_config = config.get("music", None)
        if music_config:
            music_config = naoTimesMusicConfig.parse_config(music_config)

        return cls(
            bot_id,
            bot_token,
            default_prefix,
            vndb=vndb_config,
            nyaasi=nyaasi_config,
            mongodb=parsed_mongodb,
            redisdb=parsed_redis,
            socket=sserver_config,
            kbbi=kbbi_config,
            fansubdb=fansubdb_config,
            weather=weather_config,
            log_channel=log_channel,
            ticket=ticket_config,
            wolfram=wolfram_config,
            merriam_webster=merriam_webster_config,
            crowbar_api=crowbar_api,
            statistics=statistics_config,
            slash_test_guild=slash_test_guild,
            music=music_config,
            init_config=naoTimesArgParse.parse_argparse(parsed_ns),
        )

    def serialize(self):
        base_serialize = {
            "bot_id": self.bot_id,
            "bot_token": self.bot_token,
            "default_prefix": self.default_prefix,
        }
        if self.vndb:
            base_serialize["vndb"] = self.vndb.serialize()
        if self.nyaasi:
            base_serialize["nyaasi"] = self.nyaasi.serialize()
        if self.mongodb:
            base_serialize["mongodb"] = self.mongodb.serialize()
        if self.redisdb:
            base_serialize["redisdb"] = self.redisdb.serialize()
        if self.socket:
            base_serialize["socketserver"] = self.socket.serialize()
        if self.kbbi:
            base_serialize["kbbi"] = self.kbbi.serialize()
        if self.fansubdb:
            base_serialize["fansubdb"] = self.fansubdb.serialize()
        if self.weather:
            base_serialize["weather_data"] = self.weather.serialize()
        if self.log_channel:
            base_serialize["error_logger"] = self.log_channel
        if self.ticket:
            base_serialize["ticketing"] = self.ticket.serialize()
        if self.wolfram:
            base_serialize["wolfram"] = self.wolfram.serialize()
        if self.merriam_webster:
            base_serialize["merriam_webster"] = self.merriam_webster.serialize()
        if self.statistics:
            base_serialize["statistics"] = self.statistics.serialize()
        if self.music:
            base_serialize["music"] = self.music.serialize()
        return base_serialize

    def update_config(self, key: str, new_data: Any):
        attr = getattr(self, key, None)
        if attr is None:
            return self
        setattr(self, key, new_data)

    def update_prefix(self, new_prefix: str):
        self.default_prefix = new_prefix
        return self

    @classmethod
    def from_file(
        cls: Type[naoTimesBotConfig], file_path: Union[str, Path], *, parsed_ns: naoTimesNamespace
    ) -> Type[naoTimesBotConfig]:
        config_file = blocking_read_files(file_path)
        if config_file is None:
            raise ValueError("Could not read/find config file, exiting...")

        return cls.parse_config(config_file, parsed_ns)

    def save_sync(self, file_path: Union[str, Path]):
        """Save the config to a file."""
        blocking_write_files(self.serialize(), file_path)

    async def save(self, file_path: Union[str, Path]):
        """Save the config to a file.

        This function is a coroutine.
        """
        await write_files(self.serialize(), file_path)
