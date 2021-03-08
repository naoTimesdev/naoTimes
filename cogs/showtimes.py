# -*- coding: utf-8 -*-

import logging

from nthelper.bot import naoTimesBot

from .showtimes_module import (
    ShowtimesAlias,
    ShowtimesData,
    ShowtimesFansubDB,
    ShowtimesKolaborasi,
    ShowtimesOwner,
    ShowtimesStaff,
    ShowtimesUser,
)

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
    if bot.ntdb is None:
        showlogger.warning("Database are not loaded, only loading Owner subcogs...")
        bot.add_cog(ShowtimesOwner(bot))
        return
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            showlogger.info(f"\tLoading {str(ShowTCLoad)} subcogs...")
            bot.add_cog(ShowTCLoad)
        except Exception as ex:  # skipcq: PYL-W0703
            showlogger.error(f"\tFailed to load {str(ShowTCLoad)} subcogs.")
            bot.echo_error(ex)


def teardown(bot: naoTimesBot):
    if bot.ntdb is None:
        showlogger.warning("Database are not loaded, only loading Owner subcogs...")
        bot.remove_cog(ShowtimesOwner(bot).qualified_name)
        return
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            showlogger.info(f"\tUnloading {str(ShowTCLoad)} subcogs...")
            bot.remove_cog(ShowTCLoad.qualified_name)
        except Exception as ex:  # skipcq: PYL-W0703
            showlogger.error(f"\tFailed to load {str(ShowTCLoad)} subcogs.")
            bot.echo_error(ex)
