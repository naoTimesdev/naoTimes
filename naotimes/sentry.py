"""
A simple wrapper around Sentry SDK
---

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

import asyncio
import importlib
import logging
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable

from yarl import URL

from .version import __version__

if TYPE_CHECKING:
    from sentry_sdk.integrations import Integration as _IntegrationBase
else:
    try:
        from sentry_sdk.integrations import Integration as _IntegrationBase
    except ImportError:

        class _IntegrationBase:
            pass


class Integration(_IntegrationBase):
    """Base class with a runtime fallback when Sentry is not installed."""


_sentry_sdk: ModuleType | None = None
_LoggingIntegration: type[Any] | None = None
_ignore_logger: Callable[[str], None] | None = None
_RedisIntegration: type[Any] | None = None

try:
    import sentry_sdk as _imported_sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration as _imported_logging_integration
    from sentry_sdk.integrations.logging import ignore_logger as _imported_ignore_logger
    from sentry_sdk.integrations.redis import RedisIntegration as _imported_redis_integration
except ImportError:
    pass
else:
    _sentry_sdk = _imported_sentry_sdk
    _LoggingIntegration = _imported_logging_integration
    _ignore_logger = _imported_ignore_logger
    _RedisIntegration = _imported_redis_integration


__all__ = (
    "SentryConfig",
    "setup_sentry",
)


log = logging.getLogger("naoTimes.Sentry")


@dataclass
class SentryConfig:
    """
    Configuration for the Sentry integration
    """

    dsn: str | None = None
    release: str = __version__
    git_commit: str | None = None
    server_name: str = "naoTimesBotClient"
    is_dev: bool = False


class AIOHTPPClientIntegration(Integration):
    """Custom interceptor for aiohttp.ClientSession"""

    identifier = "aiohttp_client"

    @staticmethod
    def setup_once():
        if _sentry_sdk is None:
            return

        import aiohttp
        from sentry_sdk import Hub
        from sentry_sdk.utils import capture_internal_exceptions, event_from_exception

        old_request_cmd = getattr(aiohttp.ClientSession, "_request")

        def _capture_exception(hub: Hub) -> None:
            client = hub.client
            if client is None:
                return
            exc_info = sys.exc_info()
            event, hint = event_from_exception(
                exc_info,
                client_options=client.options,
                mechanism={"type": "aiohttp-client", "handled": False},
            )
            if event is not None:
                hub.capture_event(event, hint=hint)

        async def aiohttp_request_patched(self, method: str, str_or_url: str, **kwargs: Any) -> Any:
            hub = Hub.current
            if hub is None or hub.get_integration(AIOHTPPClientIntegration) is None:
                return await old_request_cmd(self, method, str_or_url, **kwargs)

            url_part = URL(str_or_url)
            description = repr(url_part)

            with capture_internal_exceptions():
                description_parts = [str(url_part)]
                for i, arg in enumerate(list(kwargs.values())):
                    if i > 10:
                        break
                    description_parts.append(repr(arg))
                description = " ".join(description_parts)

            repl_desc = {}
            for name, value in kwargs.items():
                repl_desc[name] = value

            with hub.start_span(op="aiohttp-client", description=description) as span:
                span.set_tag("aiohttp.method", method)
                span.set_tag("aiohttp.url", str(url_part))
                span.set_data("aiohttp.kwargs", repl_desc)

                try:
                    response = await old_request_cmd(self, method, str_or_url, **kwargs)
                except aiohttp.ClientResponseError as e:
                    span.set_http_status(e.status)
                    raise
                except asyncio.CancelledError:
                    span.set_status("cancelled")
                    raise
                except Exception:
                    _capture_exception(hub)
                    raise
                span.set_tag("aiohttp.status_code", str(response.status))
                span.set_http_status(response.status)
                return response

        log.info("Patching aiohttp.ClientSession._request...")
        setattr(aiohttp.ClientSession, "_request", aiohttp_request_patched)


class MongoDBIntegration(Integration):
    """Integration with MongoDB.
    Currently wrap pymongo.
    """

    identifier = "mongodb"

    @staticmethod
    def setup_once():
        if _sentry_sdk is None:
            return

        from sentry_sdk import Hub

        try:
            pymongo_network = importlib.import_module("pymongo.network")
        except ImportError:
            log.debug("PyMongo network module is unavailable; MongoDB tracing is disabled.")
            return

        original_network_command = getattr(pymongo_network, "command", None)
        if not callable(original_network_command):
            log.debug("PyMongo network command is unavailable; MongoDB tracing is disabled.")
            return

        def patched_command(sock_info: Any, dbname: str, *args: Any, **kwargs: Any) -> Any:
            hub = Hub.current

            if hub is None or hub.get_integration(MongoDBIntegration) is None:
                return original_network_command(sock_info, dbname, *args, **kwargs)

            with hub.start_span(op="mongodb", description=dbname) as span:
                span.set_tag("mongodb.dbname", dbname)
                span.set_tag("mongodb.args", args)
                span.set_tag("mongodb.kwargs", kwargs)
                return original_network_command(sock_info, dbname, *args, **kwargs)

        log.info("Patching pymongo.network.command...")
        setattr(pymongo_network, "command", patched_command)


def setup_sentry(config: SentryConfig) -> bool:
    """Setup the sentry integrations"""

    if _sentry_sdk is None or _LoggingIntegration is None or _ignore_logger is None or _RedisIntegration is None:
        log.warning("The Sentry SDK or a required integration is unavailable.")
        return False

    # Ignore some loggers.
    _ignore_logger("discord")
    _ignore_logger("websockets")
    _ignore_logger("chardet")
    _ignore_logger("async_rediscache")

    sentry_logging = _LoggingIntegration(
        level=logging.DEBUG,
        event_level=logging.ERROR,  # Send errors as events
    )

    release_note = f"naoTimes@{config.release}"
    if config.git_commit is not None:
        release_note += f"+{config.git_commit}"

    _sentry_sdk.init(
        dsn=config.dsn,
        integrations=[
            sentry_logging,
            _RedisIntegration(),
            AIOHTPPClientIntegration(),
            MongoDBIntegration(),
        ],
        release=release_note,
        server_name=config.server_name,
        environment=(config.is_dev and "development") or "production",
    )
    log.info("Sentry SDK is now ready!")
    return True
