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

import argparse
import asyncio
import os
import pathlib
import sys

from naotimes.bot import StartupError, naoTimesBot
from naotimes.config import naoTimesBotConfig, naoTimesNamespace
from naotimes.log import setup_log
from naotimes.version import version_info

if sys.version_info < (3, 8):
    raise RuntimeError("naoTimes membutuhkan versi Python 3.8 keatas!")

if sys.version_info >= (3, 7) and os.name == "posix":
    try:
        import uvloop

        print(">> Using UVLoop")
        uvloop.install()
    except ImportError:
        pass

log_file = pathlib.Path("logs", "naotimes.log")
logger = setup_log(log_file)

parser = argparse.ArgumentParser("naotimesbot")
parser.add_argument("-dcog", "--disable-cogs", default=[], action="append", dest="cogs_skip")
parser.add_argument("-skbbi", "--skip-kbbi-check", action="store_true", dest="kbbi_check")
parser.add_argument("-sslash", "--skip-slash-check", action="store_true", dest="slash_check")
parser.add_argument("-sshow", "--skip-showtimes-fetch", action="store_true", dest="showtimes_fetch")
parser.add_argument("-dev", "--dev-mode", action="store_true", dest="dev_mode", help="Enable dev mode")
parser.add_argument(
    "--force-presence", action="store_true", dest="presence", help="Force enable presences intents"
)
args_parsed = parser.parse_args(namespace=naoTimesNamespace())

logger.info("Looking up config...")
cwd = pathlib.Path(__file__).parent.absolute()

try:
    bot_config = naoTimesBotConfig.from_file(cwd / "config.json", parsed_ns=args_parsed)
except ValueError:
    logger.critical("Could not find config file, exiting...")
    exit(69)

async_loop: asyncio.AbstractEventLoop = None
if args_parsed.dev_mode:
    os.environ["NAOTIMES_ENV"] = "development"

try:
    logger.info(f"Initiating naoTimes v{version_info.text}")
    bot = naoTimesBot.create(cwd, bot_config)
    if not bot.dev_mode and not os.path.isfile(cwd / "authorize_prod"):
        logger.critical("Bot is in Production mode and we cannot find the `authorize_prod` file.")
        bot.loop.run_until_complete(bot.close())
        bot.loop.close()
        exit(69)
    async_loop = bot.loop
    bot.remove_command("help")
    logger.info("Bot loaded, starting bot...")
    bot.run(bot_config.bot_token)
    logger.info("Bot shutting down...")
    async_loop.close()
except StartupError as e:
    logger.critical(f"Fatal error while starting bot: {str(e)}", exc_info=e)
    if async_loop is not None:
        async_loop.close()
    exit(69)
