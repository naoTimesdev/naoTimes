"""
MIT License

Copyright (c) 2019-2022 naoTimesdev

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
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, overload

from .utils import blocking_read_files, blocking_write_files, str_or_none, write_files

if TYPE_CHECKING:
    from pathlib import Path

__all__ = (
    "naoTimesArgParse",
    "naoTimesBotConfig",
    "naoTimesGeniusConfig",
    "naoTimesI18nConfig",
    "naoTimesKBBIConfig",
    "naoTimesLavaSpotifyNode",
    "naoTimesLavanodes",
    "naoTimesMerriamWebsterConfig",
    "naoTimesMongoConfig",
    "naoTimesMusicConfig",
    "naoTimesRedisConfig",
    "naoTimesSocketConfig",
    "naoTimesStatistics",
    "naoTimesTicketConfig",
    "naoTimesUserPassConfig",
    "naoTimesVNDBConfig",
    "naoTimesWeatherConfig",
    "naoTimesWolframConfig",
)

BotConfig = Mapping[str, object]
SerializedConfig = dict[str, object]


def _as_config(value: object, location: str) -> BotConfig:
    if not isinstance(value, Mapping):
        raise ConfigParseError(location, "Konfigurasi harus berupa objek!")
    if not all(isinstance(key, str) for key in value):
        raise ConfigParseError(location, "Nama konfigurasi harus berupa teks!")
    return {key: item for key, item in value.items() if isinstance(key, str)}


@overload
def _get_str(config: BotConfig, key: str, default: str) -> str: ...


@overload
def _get_str(config: BotConfig, key: str, default: None = None) -> str | None: ...


def _get_str(config: BotConfig, key: str, default: str | None = None) -> str | None:
    value = config.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigParseError(key, "Nilai konfigurasi harus berupa teks!")
    return value


@overload
def _get_int(config: BotConfig, key: str, default: int) -> int: ...


@overload
def _get_int(config: BotConfig, key: str, default: None = None) -> int | None: ...


def _get_int(config: BotConfig, key: str, default: int | None = None) -> int | None:
    value = config.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ConfigParseError(key, "Nilai konfigurasi harus berupa angka!")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ConfigParseError(key, "Nilai konfigurasi harus berupa angka!") from exc
    raise ConfigParseError(key, "Nilai konfigurasi harus berupa angka!")


def _get_int_list(config: BotConfig, key: str) -> list[int]:
    value = config.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigParseError(key, "Konfigurasi harus berupa daftar angka!")

    result: list[int] = []
    for index, item in enumerate(value):
        if isinstance(item, bool):
            raise ConfigParseError(f"{key}[{index}]", "Nilai konfigurasi harus berupa angka!")
        if isinstance(item, int):
            result.append(item)
        elif isinstance(item, str):
            try:
                result.append(int(item))
            except ValueError as exc:
                raise ConfigParseError(f"{key}[{index}]", "Nilai konfigurasi harus berupa angka!") from exc
        else:
            raise ConfigParseError(f"{key}[{index}]", "Nilai konfigurasi harus berupa angka!")
    return result


@overload
def _get_bool(config: BotConfig, key: str, default: bool) -> bool: ...


@overload
def _get_bool(config: BotConfig, key: str, default: None = None) -> bool | None: ...


def _get_bool(config: BotConfig, key: str, default: bool | None = None) -> bool | None:
    value = config.get(key, default)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ConfigParseError(key, "Nilai konfigurasi harus berupa boolean!")
    return value


def _get_section(config: BotConfig, key: str, default: BotConfig | None = None) -> BotConfig:
    if key not in config:
        return {} if default is None else default
    return _as_config(config[key], key)


def _optional_section(config: BotConfig, key: str) -> BotConfig | None:
    value = config.get(key)
    if value is None or value is False or value == {}:
        return None
    return _as_config(value, key)


def _get_section_list(config: BotConfig, key: str) -> list[BotConfig]:
    value = config.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigParseError(key, "Konfigurasi harus berupa daftar!")
    return [_as_config(item, f"{key}[{index}]") for index, item in enumerate(value)]


class naoTimesNamespace(Namespace):
    cogs_skip: list[str]
    kbbi_check: bool
    slash_check: bool
    showtimes_fetch: bool
    dev_mode: bool
    presence: bool
    message: bool


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
    username: str | None = None
    password: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesUserPassConfig], config: BotConfig) -> naoTimesUserPassConfig:
        username = _get_str(config, "username")
        password = _get_str(config, "password")
        return cls(username, password)

    def serialize(self) -> SerializedConfig:
        return {
            "username": str_or_none(self.username),
            "password": str_or_none(self.password),
        }


@dataclass
class naoTimesVNDBConfig:
    token: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesVNDBConfig], config: BotConfig) -> naoTimesVNDBConfig:
        return cls(token=_get_str(config, "token"))

    def serialize(self) -> SerializedConfig:
        return {"token": str_or_none(self.token)}


@dataclass
class naoTimesKBBIConfig:
    email: str | None = None
    password: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesKBBIConfig], config: BotConfig) -> naoTimesKBBIConfig | None:
        username = _get_str(config, "email")
        password = _get_str(config, "password")
        if not username and not password:
            return None
        return cls(email=username, password=password)

    def serialize(self) -> SerializedConfig:
        return {
            "email": self.email,
            "password": self.password,
        }


@dataclass
class naoTimesMongoConfig:
    ip_hostname: str
    port: int
    dbname: str
    tls: bool | None = True
    auth: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesMongoConfig], config: BotConfig) -> naoTimesMongoConfig:
        ip_hostname = _get_str(config, "ip_hostname", "localhost")
        port = _get_int(config, "port", 27017)
        dbname = _get_str(config, "dbname", "naotimesdb")
        tls = _get_bool(config, "tls", False)
        auth = _get_str(config, "auth")
        return cls(ip_hostname, port, dbname, tls, auth)

    def serialize(self) -> SerializedConfig:
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
    password: str | None = None
    db: int = 0

    @classmethod
    def parse_config(cls: type[naoTimesRedisConfig], config: BotConfig) -> naoTimesRedisConfig:
        ip_hostname = _get_str(config, "ip_hostname")
        if ip_hostname is None:
            raise ConfigParseError("redisdb.ip_hostname", "Redis dibutuhkan untuk berbagai macam fitur naoTimes!")
        port = _get_int(config, "port", 6379)
        password = _get_str(config, "password")
        db = _get_int(config, "db", 0)
        if db < 0:
            raise ConfigParseError("redisdb.db", "Nomor database Redis tidak boleh negatif!")
        return cls(ip_hostname, port, password, db)

    def serialize(self) -> SerializedConfig:
        return {
            "ip_hostname": self.ip_hostname,
            "port": self.port,
            "password": self.password,
            "db": self.db,
        }


@dataclass
class naoTimesSocketConfig:
    port: int
    password: str | None = None
    enabled: bool = True

    @classmethod
    def parse_config(cls: type[naoTimesSocketConfig], config: BotConfig | bool | None) -> naoTimesSocketConfig:
        # `"socketserver": null` or `false` disables the socket server completely.
        if config is None or config is False:
            return cls(25670, None, False)
        if not isinstance(config, Mapping):
            raise ConfigParseError("socketserver", "Konfigurasi socketserver harus berupa objek!")
        section = _as_config(config, "socketserver")
        port = _get_int(section, "port", 25670)
        password = _get_str(section, "password")
        enabled = _get_bool(section, "enabled", True)
        return cls(port, password, enabled)

    def serialize(self) -> SerializedConfig:
        return {
            "enabled": self.enabled,
            "port": self.port,
            "password": str_or_none(self.password),
        }


@dataclass
class naoTimesHTTPServerConfig:
    host: str
    port: int
    password: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesHTTPServerConfig], config: BotConfig) -> naoTimesHTTPServerConfig:
        host = _get_str(config, "host", "localhost")
        port = _get_int(config, "port", 25671)
        password = _get_str(config, "password")
        return cls(host, port, password)

    def serialize(self) -> SerializedConfig:
        return {
            "host": self.host,
            "port": self.port,
            "password": str_or_none(self.password),
        }


@dataclass
class naoTimesWeatherConfig:
    openweather: str | None = None
    opencage: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesWeatherConfig], config: BotConfig) -> naoTimesWeatherConfig | None:
        openweather = _get_str(config, "openweatherapi")
        opencage = _get_str(config, "opencageapi")
        if not openweather and not opencage:
            return None
        return cls(openweather, opencage)

    def serialize(self) -> SerializedConfig:
        return {
            "openweatherapi": str_or_none(self.openweather),
            "opencageapi": str_or_none(self.opencage),
        }


@dataclass
class naoTimesTicketConfig:
    id: int | None = None
    srv_id: int | None = None
    log_id: int | None = None

    @classmethod
    def parse_config(cls: type[naoTimesTicketConfig], config: BotConfig) -> naoTimesTicketConfig | None:
        id = _get_int(config, "id")
        srv_id = _get_int(config, "srv_id")
        log_id = _get_int(config, "log_id")
        if not id or not srv_id or not log_id:
            return None
        return cls(id, srv_id, log_id)

    def serialize(self) -> SerializedConfig:
        return {
            "id": self.id,
            "srv_id": self.srv_id,
            "log_id": self.log_id,
        }


@dataclass
class naoTimesWolframConfig:
    appid: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesWolframConfig], config: BotConfig) -> naoTimesWolframConfig | None:
        appid = _get_str(config, "app_id")
        if not appid:
            return None
        return cls(appid)

    def serialize(self) -> SerializedConfig:
        return {"app_id": str_or_none(self.appid)}


@dataclass
class naoTimesMerriamWebsterConfig:
    dictionary: str | None = None
    thesaurus: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesMerriamWebsterConfig], config: BotConfig) -> naoTimesMerriamWebsterConfig | None:
        dictionary = _get_str(config, "dictionary")
        thesaurus = _get_str(config, "thesaurus")
        if not dictionary and not thesaurus:
            return None
        return cls(dictionary, thesaurus)

    def serialize(self) -> SerializedConfig:
        return {
            "dictionary": str_or_none(self.dictionary),
            "thesaurus": str_or_none(self.thesaurus),
        }


@dataclass
class naoTimesStatistics:
    sentry_dsn: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesStatistics], config: BotConfig) -> naoTimesStatistics:
        sentry_dsn = _get_str(config, "sentry_dsn")
        return cls(sentry_dsn)

    def serialize(self) -> SerializedConfig:
        return {"sentry_dsn": str_or_none(self.sentry_dsn)}


@dataclass
class naoTimesLavaSpotifyNode:
    """
    Spotify bridge settings.

    ``url`` is the base URL of the HTTP bridge. A Spotify link such as
    ``https://open.spotify.com/track/<ID>`` is rewritten to ``<url>/track/<ID>``
    (same for album, playlist, episode, show and artist) and handed to Lavalink.
    ``id`` and ``secret`` are legacy fields, no longer used and kept so older configs still parse.
    """

    url: str
    id: str | None = None
    secret: str | None = None

    @classmethod
    def parse_config(cls: type[naoTimesLavaSpotifyNode], config: BotConfig) -> naoTimesLavaSpotifyNode:
        url = _get_str(config, "url")
        if not url:
            raise ConfigParseError("music.spotify.url", "URL bridge Spotify dibutuhkan untuk fitur Spotify!")
        return cls(url.rstrip("/"), _get_str(config, "id"), _get_str(config, "secret"))

    def serialize(self) -> SerializedConfig:
        return {"url": self.url, "id": self.id, "secret": self.secret}


@dataclass
class naoTimesGeniusConfig:
    client_id: str | None
    client_secret: str | None

    @classmethod
    def parse_config(cls: type[naoTimesGeniusConfig], config: BotConfig) -> naoTimesGeniusConfig:
        client_id = _get_str(config, "client_id")
        client_secret = _get_str(config, "client_secret")
        return cls(client_id, client_secret)

    def serialize(self) -> SerializedConfig:
        return {"client_id": self.client_id, "client_secret": self.client_secret}


@dataclass
class naoTimesMusixmatchConfig:
    api_key: str | None

    @classmethod
    def parse_config(cls: type[naoTimesMusixmatchConfig], config: BotConfig) -> naoTimesMusixmatchConfig:
        api_key = _get_str(config, "api_key")
        return cls(api_key)

    def serialize(self) -> SerializedConfig:
        return {"api_key": self.api_key}


@dataclass
class naoTimesLavanodes:
    host: str
    port: int
    password: str
    identifier: str

    @classmethod
    def parse_config(cls: type[naoTimesLavanodes], config: BotConfig) -> naoTimesLavanodes:
        host = _get_str(config, "host")
        if host is None:
            raise ConfigParseError("lavalink.host", "Lavalink dibutuhkan untuk berbagai macam fitur naoTimes!")
        port = _get_int(config, "port", 2333)
        password = _get_str(config, "password")
        if password is None:
            raise ConfigParseError("lavalink.password", "Password Lavalink dibutuhkan!")
        identifier = _get_str(config, "identifier")
        if identifier is None:
            idv4 = str(uuid.uuid4())
            identifier = f"potia-lava-{idv4}"
        return cls(host, port, password, identifier)

    def serialize(self) -> SerializedConfig:
        return {
            "host": self.host,
            "port": self.port,
            "password": self.password,
            "identifier": self.identifier,
        }


@dataclass
class naoTimesMusicConfig:
    nodes: list[naoTimesLavanodes] = field(default_factory=list)
    spotify: naoTimesLavaSpotifyNode | None = None
    genius: naoTimesGeniusConfig | None = None
    musixmatch: naoTimesMusixmatchConfig | None = None

    @classmethod
    def parse_config(cls: type[naoTimesMusicConfig], config: BotConfig) -> naoTimesMusicConfig:
        parsed_nodes = [naoTimesLavanodes.parse_config(node) for node in _get_section_list(config, "lavalink_nodes")]
        spotify_section = _optional_section(config, "spotify")
        spotify_node = naoTimesLavaSpotifyNode.parse_config(spotify_section) if spotify_section is not None else None
        genius_section = _optional_section(config, "genius")
        genius_config = naoTimesGeniusConfig.parse_config(genius_section) if genius_section is not None else None
        mxm_section = _optional_section(config, "musixmatch")
        mxm_config = naoTimesMusixmatchConfig.parse_config(mxm_section) if mxm_section is not None else None
        return cls(parsed_nodes, spotify_node, genius_config, mxm_config)

    def serialize(self) -> SerializedConfig:
        base: SerializedConfig = {
            "lavalink_nodes": [node.serialize() for node in self.nodes],
        }
        if self.spotify is not None:
            base["spotify"] = self.spotify.serialize()
        if self.genius is not None:
            base["genius"] = self.genius.serialize()
        if self.musixmatch is not None:
            base["musixmatch"] = self.musixmatch.serialize()
        return base


@dataclass
class naoTimesArgParse:
    cogs_skip: list[str] = field(default_factory=list)
    kbbi_check: bool = True
    slash_check: bool = True
    showtimes_fetch: bool = True
    parsed_ns: naoTimesNamespace | None = None

    @classmethod
    def parse_argparse(cls: type[naoTimesArgParse], parsed: naoTimesNamespace) -> naoTimesArgParse:
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
class naoTimesI18nConfig:
    default_language: str = "id"
    available_languages: list[str] | None = None

    @classmethod
    def parse_config(cls, config: BotConfig) -> naoTimesI18nConfig:
        default_language = (_get_str(config, "default_language") or "id").strip().lower()
        raw_available = config.get("available_languages")
        available_languages: list[str] | None = None
        if raw_available is not None:
            if not isinstance(raw_available, list) or not all(isinstance(item, str) for item in raw_available):
                raise ConfigParseError("i18n.available_languages", "Konfigurasi harus berupa daftar teks!")
            available_languages = [item.strip().lower() for item in raw_available if item.strip()]
        return cls(default_language=default_language, available_languages=available_languages)

    def serialize(self) -> SerializedConfig:
        data: SerializedConfig = {"default_language": self.default_language}
        if self.available_languages:
            data["available_languages"] = self.available_languages
        return data


@dataclass
class naoTimesBotConfig:
    bot_id: str
    bot_token: str
    default_prefix: str
    vndb: naoTimesVNDBConfig
    mongodb: naoTimesMongoConfig
    redisdb: naoTimesRedisConfig
    socket: naoTimesSocketConfig
    http_server: naoTimesHTTPServerConfig
    kbbi: naoTimesKBBIConfig | None
    fansubdb: naoTimesUserPassConfig
    weather: naoTimesWeatherConfig | None
    log_channel: int | None
    ticket: naoTimesTicketConfig | None
    wolfram: naoTimesWolframConfig | None
    merriam_webster: naoTimesMerriamWebsterConfig | None
    tmdb_api: str | None
    slash_test_guild: int | None
    owner_exclude: list[int]
    dev_mode: bool
    statistics: naoTimesStatistics
    music: naoTimesMusicConfig | None
    google_translate_api_key: str | None = None
    init_config: naoTimesArgParse | None = None
    i18n: naoTimesI18nConfig = field(default_factory=naoTimesI18nConfig)

    @classmethod
    def parse_config(
        cls: type[naoTimesBotConfig], config: BotConfig, parsed_ns: naoTimesNamespace
    ) -> naoTimesBotConfig:
        bot_id = _get_str(config, "bot_id")
        bot_token = _get_str(config, "bot_token")
        default_prefix = _get_str(config, "default_prefix")
        if bot_id is None or bot_token is None or default_prefix is None:
            raise ConfigParseError("bot", "Missing bot_id, bot_token or default_prefix")
        parsed_mongodb = naoTimesMongoConfig.parse_config(_get_section(config, "mongodb"))
        parsed_redis = naoTimesRedisConfig.parse_config(_get_section(config, "redisdb"))
        vndb_config = naoTimesVNDBConfig.parse_config(_get_section(config, "vndb"))
        socket_config = config.get("socketserver", {})
        if socket_config is None or socket_config is False:
            sserver_config = naoTimesSocketConfig.parse_config(socket_config)
        else:
            sserver_config = naoTimesSocketConfig.parse_config(_as_config(socket_config, "socketserver"))
        kbbi_config = naoTimesKBBIConfig.parse_config(_get_section(config, "kbbi"))
        fansubdb_config = naoTimesUserPassConfig.parse_config(_get_section(config, "fansubdb"))
        weather_config = naoTimesWeatherConfig.parse_config(_get_section(config, "weather_data"))
        log_channel = _get_int(config, "error_logger")
        ticket_config = naoTimesTicketConfig.parse_config(_get_section(config, "ticketing"))
        wolfram_config = naoTimesWolframConfig.parse_config(_get_section(config, "wolfram"))
        merriam_webster_config = naoTimesMerriamWebsterConfig.parse_config(_get_section(config, "merriam_webster"))
        tmdb_api = _get_str(config, "tmdb_api_key")
        if not tmdb_api:
            tmdb_api = None
        google_translate_api_key = _get_str(config, "google_translate_api_key")
        if not google_translate_api_key:
            google_translate_api_key = None
        statistics_config = naoTimesStatistics.parse_config(_get_section(config, "statistics"))
        # The `-dev` CLI flag can still force dev mode on.
        dev_mode = _get_bool(config, "dev_mode", False) or bool(getattr(parsed_ns, "dev_mode", False))
        slash_test_value = config.get("slash_test_guild")
        slash_test_guild: int | None = None
        if isinstance(slash_test_value, bool):
            raise ConfigParseError("slash_test_guild", "ID server uji harus berupa angka!")
        if isinstance(slash_test_value, (float, str)):
            try:
                slash_test_guild = int(slash_test_value)
            except ValueError:
                slash_test_guild = None
        elif isinstance(slash_test_value, int):
            slash_test_guild = slash_test_value
        elif slash_test_value is not None:
            raise ConfigParseError("slash_test_guild", "ID server uji harus berupa angka!")
        owner_exclude = _get_int_list(config, "owner_exclude")
        http_server = naoTimesHTTPServerConfig.parse_config(_get_section(config, "http_server"))

        i18n_config = naoTimesI18nConfig.parse_config(_get_section(config, "i18n"))

        music_section = _optional_section(config, "music")
        music_config = naoTimesMusicConfig.parse_config(music_section) if music_section is not None else None

        return cls(
            bot_id,
            bot_token,
            default_prefix,
            vndb=vndb_config,
            mongodb=parsed_mongodb,
            redisdb=parsed_redis,
            socket=sserver_config,
            http_server=http_server,
            kbbi=kbbi_config,
            fansubdb=fansubdb_config,
            weather=weather_config,
            log_channel=log_channel,
            ticket=ticket_config,
            wolfram=wolfram_config,
            merriam_webster=merriam_webster_config,
            tmdb_api=tmdb_api,
            google_translate_api_key=google_translate_api_key,
            statistics=statistics_config,
            slash_test_guild=slash_test_guild,
            owner_exclude=owner_exclude,
            dev_mode=dev_mode,
            music=music_config,
            init_config=naoTimesArgParse.parse_argparse(parsed_ns),
            i18n=i18n_config,
        )

    def serialize(self) -> SerializedConfig:
        base_serialize: SerializedConfig = {
            "bot_id": self.bot_id,
            "bot_token": self.bot_token,
            "default_prefix": self.default_prefix,
        }
        if self.i18n:
            base_serialize["i18n"] = self.i18n.serialize()
        if self.vndb:
            base_serialize["vndb"] = self.vndb.serialize()
        if self.mongodb:
            base_serialize["mongodb"] = self.mongodb.serialize()
        if self.redisdb:
            base_serialize["redisdb"] = self.redisdb.serialize()
        if self.socket:
            base_serialize["socketserver"] = self.socket.serialize()
        if self.http_server:
            base_serialize["http_server"] = self.http_server.serialize()
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
        if self.tmdb_api:
            base_serialize["tmdb_api_key"] = self.tmdb_api
        if self.google_translate_api_key:
            base_serialize["google_translate_api_key"] = self.google_translate_api_key
        if self.slash_test_guild:
            base_serialize["slash_test_guild"] = self.slash_test_guild
        if self.owner_exclude:
            base_serialize["owner_exclude"] = self.owner_exclude
        base_serialize["dev_mode"] = self.dev_mode
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
        cls: type[naoTimesBotConfig], file_path: str | Path, *, parsed_ns: naoTimesNamespace
    ) -> naoTimesBotConfig:
        config_file = blocking_read_files(str(file_path))
        if config_file is None:
            raise ValueError("Could not read/find config file, exiting...")

        return cls.parse_config(_as_config(config_file, "root"), parsed_ns)

    def save_sync(self, file_path: str | Path):
        """Save the config to a file."""
        blocking_write_files(self.serialize(), str(file_path))

    async def save(self, file_path: str | Path):
        """Save the config to a file.

        This function is a coroutine.
        """
        await write_files(self.serialize(), str(file_path))
