"""
MIT License

Copyright (c) 2020-2021 Rob Wagner

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

A rewrite of the original cogwatch.py by Rob Wagner
https://github.com/robertwayne/cogwatch
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from discord.ext.commands.errors import (
    ExtensionAlreadyLoaded,
    ExtensionError,
    ExtensionNotFound,
    ExtensionNotLoaded,
)

if TYPE_CHECKING:

    from ..bot import naoTimesBot

run_watcher = False
try:
    from watchgod import Change, awatch

    run_watcher = True
except ImportError:
    pass


__all__ = ("CogWatcher",)


class CogWatcher:
    def __init__(self, client: naoTimesBot, loop: asyncio.AbstractEventLoop = None):
        self.logger = logging.getLogger("naoTimes.CogWatcher")
        self.client = client
        self.loop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()
        self.path = client.fcwd / "cogs"
        self._task: asyncio.Task = None
        if client.dev_mode:
            if run_watcher:
                self.logger.info("Starting cogs hot-reload")
                self._task = self.loop.create_task(self.start(), name="cog-watcher-task")
            else:
                self.logger.warning("watchgod is not installed. Hot-reloading will not work.")

    def __del__(self):
        self.close()

    def close(self):
        if self._task is not None:
            self._task.cancel()

    @staticmethod
    def get_cog_name(path: str) -> str:
        """Returns the cog file name without .py appended to it."""
        _path = os.path.normpath(path)
        return _path.split(os.sep)[-1:][0][:-3]

    def get_dotted_cog_path(self, path: str) -> str:
        """Returns the full dotted path that discord.py uses to load cog files."""
        _path = os.path.normpath(path)
        tokens = _path.split(os.sep)
        rtokens = list(reversed(tokens))

        # iterate over the list backwards in order to get the first occurrence in cases where a duplicate
        # name exists in the path (ie. example_proj/example_proj/commands)
        try:
            root_index = rtokens.index(self.path.split("/")[0]) + 1
        except ValueError:
            raise ValueError("Use forward-slash delimiter in your `path` parameter.")

        return ".".join([token for token in tokens[-root_index:-1]])

    def validate_dir(self):
        """
        Validates that the directory exists.

        Raises
        ------
        FileNotFoundError
            If the directory does not exist.
        """
        if not self.path.exists():
            raise FileNotFoundError(f"{self.path} does not exist.")

    async def _internal_start(self):
        """
        Starts the cog watcher.

        This is called automatically by the client.
        """
        # Wait until the client is ready
        self.logger.info("Starting hot-reloader internal task, waiting for bot to come online")
        await self.client.wait_until_ready()

        self.logger.info(f"Bot went online, watching {self.path}")
        while self.client.is_ready():
            try:
                async for changes in awatch(self.path):
                    self.validate_dir()
                    reverse_ordered_changes = sorted(changes, reverse=True)

                    for change in reverse_ordered_changes:
                        tipe, name = change

                        filename = self.get_cog_name(name)
                        new_dir = self.get_dotted_cog_path(name)

                        cog_dir = (
                            f"{new_dir}.{filename.lower()}" if new_dir else f"{self.path}.{filename.lower()}"
                        )

                        if tipe == Change.added:
                            self.logger.info(f"{filename} was added.")
                            self.load_cog(cog_dir)
                        elif tipe == Change.deleted:
                            self.logger.info(f"{filename} was deleted.")
                            self.unload_cog(cog_dir)
                        elif tipe == Change.modified:
                            self.logger.info(f"{filename} was modified.")
                            self.reload_cog(cog_dir)
            except FileNotFoundError:
                continue
            else:
                await asyncio.sleep(1)

    async def start(self):
        try:
            await self._internal_start()
        except asyncio.CancelledError:
            self.logger.warning("Task got cancelled, cleaning up!")

    # Module reloader

    async def load_cog(self, cog_name: str):
        try:
            self.client.load_extension(cog_name)
        except ExtensionAlreadyLoaded:
            self.logger.error(f"{cog_name} is already loaded.")
            return
        except (ExtensionNotFound, ModuleNotFoundError):
            self.logger.error(f"{cog_name} was not found.")
            return
        except ExtensionError as cef:
            self.logger.error(f"Failed to load {cog_name}", exc_info=cef)
            return

    async def unload_cog(self, cog_name: str):
        try:
            self.client.unload_extension(cog_name)
        except ExtensionNotLoaded:
            self.logger.error(f"{cog_name} is already loaded.")
            return
        except (ExtensionNotFound, ModuleNotFoundError):
            self.logger.error(f"{cog_name} was not found.")
            return
        except ExtensionError as cef:
            self.logger.error(f"Failed to load {cog_name}", exc_info=cef)
            return

    async def reload_cog(self, cog_name: str):
        try:
            self.client.reload_extension(cog_name)
        except ExtensionNotLoaded:
            self.logger.warning(f"{cog_name} is not loaded yet, trying to load")
            await self.load_cog(cog_name)
            return
        except (ExtensionNotFound, ModuleNotFoundError):
            self.logger.error(f"{cog_name} was not found.")
            return
        except ExtensionError as cef:
            self.logger.error(f"Failed to load {cog_name}", exc_info=cef)
            return
