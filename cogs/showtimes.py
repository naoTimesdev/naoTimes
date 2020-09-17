# -*- coding: utf-8 -*-

import logging

from .showtimes_module import (
    ShowtimesUser,
    ShowtimesStaff,
    ShowtimesAlias,
    ShowtimesKolaborasi,
    ShowtimesData,
    ShowtimesFansubDB,
    ShowtimesOwner,
)

from nthelper.bot import naoTimesBot

showlogger = logging.getLogger("cogs.showtimes")

ShowTimesCommands = [
    ShowtimesUser,
    ShowtimesStaff,
    ShowtimesAlias,
    ShowtimesKolaborasi,
    ShowtimesData,
    ShowtimesFansubDB,
    ShowtimesOwner,
]


def setup(bot: naoTimesBot):
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            showlogger.info(f"\tLoading {str(ShowTCLoad)} subcogs...")
            bot.add_cog(ShowTCLoad)
        except Exception as ex:
            showlogger.error(f"\tFailed to load {str(ShowTCLoad)} subcogs.")
            showlogger.error(f"\tTraceback -> {ex}")


def teardown(bot: naoTimesBot):
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            showlogger.info(f"\tUnloading {str(ShowTCLoad)} subcogs...")
            bot.remove_cog(ShowTCLoad.qualified_name)
        except Exception as ex:
            showlogger.error(f"\tFailed to load {str(ShowTCLoad)} subcogs.")
            showlogger.error(f"\tTraceback -> {ex}")
