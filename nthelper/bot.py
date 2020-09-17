import logging
import traceback
from typing import Dict, Union

import discord
from discord.ext import commands

from .fsdb import FansubDBBridge
from .showtimes_helper import ShowtimesQueue, naoTimesDB
from .utils import __version__


class naoTimesBot(commands.Bot):
    """A modified version of commands.Bot
    ---
    Reason making this is for easier typecasting.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger: logging.Logger = logging.getLogger("naoTimesBot")
        self.automod_folder: str

        self.semver: str = __version__
        self.botconf: Dict[str, Union[str, Dict[str, Union[str, int, bool]]]]
        self.prefix: str

        self.jsdb_streams: dict
        self.jsdb_currency: dict
        self.jsdb_crypto: dict

        self.fcwd: str

        self.kbbi_cookie: str
        self.kbbi_expires: int
        self.kbbi_auth: Dict[str, str]

        self.fsdb: FansubDBBridge
        self.showqueue: ShowtimesQueue

        self.showtimes_resync: list = []
        self.ntdb: naoTimesDB

        self.uptime: float
        self.owner: discord.User

    def echo_error(self, error):
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        self.logger.error("Exception occured\n" + "".join(tb))
