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

import argparse
import asyncio
import os
import pathlib
import sys

from arrow._version import __version__ as arrow_version
from packaging.version import parse as parse_version

from naotimes.bot import StartupError, naoTimesBot
from naotimes.config import naoTimesBotConfig, naoTimesNamespace
from naotimes.log import setup_log
from naotimes.monke import (
    monkeypatch_arrow_id_locale,
    monkeypatch_discord_context_menu,
    monkeypatch_discord_tasks_loop,
    monkeypatch_message_delete,
)
from naotimes.utils import verify_port_open
from naotimes.version import version_info

if sys.version_info < (3, 8):
    raise RuntimeError("naoTimes membutuhkan versi Python 3.8 keatas!")

if sys.version_info >= (3, 7) and os.name == "posix":
    try:
        import uvloop  # type: ignore

        print(">> Using UVLoop")
        uvloop.install()
    except ImportError:
        pass


cwd = pathlib.Path(__file__).parent.absolute()
log_file = cwd / "logs" / "naotimes.log"
logger = setup_log(log_file)
# If arrow version is less than equal to 1.2.1, monkeypatch it
if parse_version(arrow_version) <= parse_version("1.2.1"):
    monkeypatch_arrow_id_locale()
monkeypatch_message_delete()
monkeypatch_discord_tasks_loop()
monkeypatch_discord_context_menu()


parser = argparse.ArgumentParser("naotimesbot")
parser.add_argument("-dcog", "--disable-cogs", default=[], action="append", dest="cogs_skip")
parser.add_argument("-skbbi", "--skip-kbbi-check", action="store_true", dest="kbbi_check")
parser.add_argument("-sslash", "--skip-slash-check", action="store_true", dest="slash_check")
parser.add_argument("-sshow", "--skip-showtimes-fetch", action="store_true", dest="showtimes_fetch")
parser.add_argument("-dev", "--dev-mode", action="store_true", dest="dev_mode", help="Enable dev mode")
parser.add_argument(
    "--force-presence", action="store_true", dest="presence", help="Force enable presences intents"
)
parser.add_argument(
    "--force-message", action="store_true", dest="message", help="Force enable message intents"
)
args_parsed = parser.parse_args(namespace=naoTimesNamespace())

logger.info("Looking up config...")

try:
    bot_config = naoTimesBotConfig.from_file(cwd / "config.json", parsed_ns=args_parsed)
except ValueError:
    logger.critical("Could not find config file, exiting...")
    exit(69)


if bot_config.http_server is not None:
    if not verify_port_open(bot_config.http_server.port):
        logger.critical(f"Port {bot_config.http_server.port} (HTTP Server) is not open, exiting...")
        exit(69)
if bot_config.socket is not None:
    if not verify_port_open(bot_config.socket.port):
        logger.critical(f"Port {bot_config.socket.port} (Socket Server) is not open, exiting...")
        exit(69)


if args_parsed.dev_mode:
    os.environ["NAOTIMES_ENV"] = "development"


async def runner(cwd: pathlib.Path, bot_config: naoTimesBotConfig) -> int:
    """
    The actual bot runner, return the exit code
    """
    logger.info(f"Initiating naoTimes v{version_info.text}")
    prod_ready = cwd / "authorize_prod"

    try:
        bot_context = await naoTimesBot.async_create(cwd, bot_config)
    except Exception as e:
        logger.critical(f"Could not initiate bot, exiting... {e}", exc_info=e)
        return 69

    async with bot_context as bot:
        if not bot.dev_mode and not prod_ready.exists():
            logger.critical("Bot is in Production mode and we cannot find the `authorize_prod` file.")
            return 69

        bot.remove_command("help")
        logger.info("Booting up bot...")
        try:
            await bot.start(bot_config.bot_token, reconnect=True)
        except StartupError as e:
            logger.critical(f"Fatal error while starting bot: {str(e)}", exc_info=e)
            return 69

    logger.info("Bot shutting down...")
    return 0


exit_code = 0
try:
    exit_code = asyncio.run(runner(cwd, bot_config))
except KeyboardInterrupt:
    logger.warning("Keyboard interrupt detected, shutting down...")
    exit_code = 420
finally:
    exit(exit_code)
