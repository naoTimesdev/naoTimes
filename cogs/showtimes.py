# -*- coding: utf-8 -*-

import logging

from discord.ext import commands

from .showtimes_module import (
    ShowtimesAlias,
    ShowtimesData,
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
    ShowtimesOwner,
]


def setup(bot: commands.Bot):
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            showlogger.info(f"\tLoading {str(ShowTCLoad)} subcogs...")
            bot.add_cog(ShowTCLoad)
        except Exception as ex:
            showlogger.error(f"\tFailed to load {str(ShowTCLoad)} subcogs.")
            showlogger.error(f"\tTraceback -> {ex}")


def teardown(bot: commands.Bot):
    for ShowTC in ShowTimesCommands:
        try:
            ShowTCLoad = ShowTC(bot)
            showlogger.info(f"\tUnloading {str(ShowTCLoad)} subcogs...")
            bot.remove_cog(ShowTCLoad.qualified_name)
        except Exception as ex:
            showlogger.error(f"\tFailed to load {str(ShowTCLoad)} subcogs.")
            showlogger.error(f"\tTraceback -> {ex}")
