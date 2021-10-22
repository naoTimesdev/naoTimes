"""
A simple wrapper around Sentry SDK
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
import os
import sys
from dataclasses import dataclass

from yarl import URL

from .version import __version__

try:
    import sentry_sdk
    from sentry_sdk import Hub
    from sentry_sdk._compat import reraise
    from sentry_sdk.integrations import Integration
    from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger
    from sentry_sdk.integrations.redis import patch_redis_client
    from sentry_sdk.utils import capture_internal_exceptions, event_from_exception

    use_sentry = True
except ImportError:
    use_sentry = False

    class Integration:
        @staticmethod
        def setup_once():
            raise NotImplementedError


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

    dsn: str = None
    release: str = __version__
    git_commit: str = None
    server_name: str = "naoTimesBotClient"
    is_dev: bool = os.getenv("NAOTIMES_ENV", "production") == "development"


class RedisIntegration(Integration):
    """Custom redis integrations for Sentry
    This is the same as the original support but patching aioredis.

    """

    identifier = "redis"

    @staticmethod
    def setup_once():
        import aioredis

        log.info("Patching aioredis.StrictRedis and aioredis.Redis ...")
        patch_redis_client(aioredis.StrictRedis)


class AIOHTPPClientIntegration(Integration):
    """Custom interceptor for aiohttp.ClientSession"""

    identifier = "aiohttp_client"

    @staticmethod
    def setup_once():
        import aiohttp

        old_request_cmd = aiohttp.ClientSession._request

        def _capture_exception(hub: Hub):
            exc_info = sys.exc_info()
            event, hint = event_from_exception(
                exc_info,
                client_options=hub.client.options,
                mechanism={"type": "aiohttp-client", "handled": False},
            )
            hub.capture_event(event, hint=hint)
            return exc_info

        async def aiohttp_request_patched(self, method: str, str_or_url: str, **kwargs):
            hub = Hub.current
            if hub.get_integration(AIOHTPPClientIntegration) is None:
                return await old_request_cmd(self, method, str_or_url, **kwargs)

            url_part = URL(str_or_url)
            description = repr(url_part)

            with capture_internal_exceptions():
                description_parts = [url_part]
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
                    reraise(*_capture_exception(hub))
                span.set_tag("aiohttp.status_code", str(response.status))
                span.set_http_status(response.status)
                return response

        log.info("Patching aiohttp.ClientSession._request...")
        aiohttp.ClientSession._request = aiohttp_request_patched


class MongoDBIntegration(Integration):
    """Integration with MongoDB.
    Currently wrap pymongo.
    """

    identifier = "mongodb"

    @staticmethod
    def setup_once():
        import pymongo.network

        original_network_command = pymongo.network.command

        def patched_command(sock_info, dbname, *args, **kwargs):
            hub = Hub.current

            if hub.get_integration(MongoDBIntegration) is None:
                return original_network_command(sock_info, dbname, *args, **kwargs)

            with hub.start_span(op="mongodb", description=dbname) as span:
                span.set_tag("mongodb.dbname", dbname)
                span.set_tag("mongodb.args", args)
                span.set_tag("mongodb.kwargs", kwargs)
                return original_network_command(sock_info, dbname, *args, **kwargs)

        log.info("Patching pymongo.network.command...")
        pymongo.network.command = patched_command


def setup_sentry(config: SentryConfig) -> None:
    """Setup the sentry integrations"""

    if not use_sentry:
        log.warning("The SDK is not installed yet, please install with `pip install -U sentry-sdk`")
        return False

    # Ignore some loggers.
    ignore_logger("discord")
    ignore_logger("websockets")
    ignore_logger("chardet")
    ignore_logger("async_rediscache")

    sentry_logging = LoggingIntegration(
        level=logging.DEBUG,
        event_level=logging.ERROR,  # Send errors as events
    )

    release_note = f"naoTimes@{config.release}"
    if config.git_commit is not None:
        release_note += f"+{config.git_commit}"

    sentry_sdk.init(
        dsn=config.dsn,
        integrations=[
            sentry_logging,
            RedisIntegration(),
            AIOHTPPClientIntegration(),
            MongoDBIntegration(),
        ],
        release=release_note,
        server_name=config.server_name,
        environment=config.is_dev and "development" or "production",
    )
    log.info("Sentry SDK is now ready!")
    return True
