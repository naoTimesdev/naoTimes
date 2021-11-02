from __future__ import annotations

import glob
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Optional

import coloredlogs

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ("RollingFileHandler", "setup_log")


class RollingFileHandler(RotatingFileHandler):
    """
    A log file handler that follows the same format as RotatingFileHandler,
    but automatically roll over to the next numbering without needing to worry
    about maximum file count or something.

    At startup, we check the last file in the directory and start from there.
    """

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
    ) -> None:
        self._last_backup_count = 0
        super().__init__(
            filename, mode=mode, maxBytes=maxBytes, backupCount=backupCount, encoding=encoding, delay=delay
        )
        self.maxBytes = maxBytes
        self.backupCount = backupCount
        self._determine_start_count()

    def _determine_start_count(self):
        all_files = glob.glob(self.baseFilename + "*")
        if all_files:
            all_files.sort()
            last_digit = all_files[-1].split(".")[-1]
            if last_digit.isdigit():
                self._last_backup_count = int(last_digit)

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        self._last_backup_count += 1
        next_name = "%s.%d" % (self.baseFilename, self._last_backup_count)
        self.rotate(self.baseFilename, next_name)
        if not self.delay:
            self.stream = self._open()


def setup_log(log_path: Path):
    log_path.parent.mkdir(exist_ok=True)

    file_handler = RollingFileHandler(log_path, maxBytes=5_242_880, backupCount=5, encoding="utf-8")
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler],
        format="[%(asctime)s] - (%(name)s)[%(levelname)s](%(funcName)s): %(message)s",  # noqa: E501
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger()
    coloredlogs.install(
        fmt="[%(asctime)s %(hostname)s][%(levelname)s] (%(name)s[%(process)d]): %(funcName)s: %(message)s",
        level=logging.INFO,
        logger=logger,
        stream=sys.stdout,
    )

    # Set default logging for some modules
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.DEBUG)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("chardet").setLevel(logging.WARNING)
    logging.getLogger("async_rediscache").setLevel(logging.WARNING)
    logging.getLogger("wavelink.websocket").setLevel(logging.WARNING)

    # Set back to the default of INFO even if asyncio's debug mode is enabled.
    logging.getLogger("asyncio").setLevel(logging.INFO)

    return logger
