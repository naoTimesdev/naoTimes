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

import asyncio
import logging
import os
from io import BytesIO
from typing import Dict, Type

import orjson
import pyppeteer.connection
from PIL import Image
from pyppeteer.browser import Browser
from pyppeteer.connection import Connection
from pyppeteer.launcher import Launcher

from .enums import CardBase, CardGeneratorNav, CardTemplate

__all__ = ("CardFailure", "CardGenerationFailure", "CardBindFailure", "CardGenerator")


class CardFailure(Exception):
    pass


class CardGenerationFailure(CardFailure):
    def __init__(self, name: str, reason: str = None):
        self.name = name
        error_reason = f"Failed to generate card using {name} template"
        if reason is not None:
            error_reason += f": {reason}"
        super().__init__(error_reason)


class CardBindFailure(CardFailure):
    def __init__(self, template: CardTemplate, reason: str = None):
        self.template = template
        error_reason = f"Failed to bind card to {template.name}"
        if reason is not None:
            error_reason += f": {reason}"
        super().__init__(error_reason)


class CardGenerator:
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        self._browser: Browser = None
        self._loop = loop
        if not self._loop:
            self._loop = asyncio.get_event_loop()
        self._launcher = Launcher(
            headless=True,
            args=["--no-sandbox"],
            loop=self._loop,
            logLevel=logging.INFO,
            autoClose=False,
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False,
        )
        self.logger = logging.getLogger("naoTimes.CardGen")

        self._page_navigator: Dict[str, CardGeneratorNav] = {}

    async def init(self):
        self.logger.info("Initiating the headless browser...")
        self._browser = await self._launcher.launch()
        self.logger.info("Headless browser initiated")

    async def _internal_close_connection(self, connection: Connection):
        connection._connected = False
        self.logger.debug("Clearing out connection callbacks")
        connection._callbacks.clear()
        for session in connection._sessions.values():
            self.logger.debug(f"Closing session: {session}")
            session._on_closed()
        self.logger.debug("Clearing out session...")
        connection._sessions.clear()

        if hasattr(connection, "connection"):
            self.logger.debug("Closing websocket connection")
            await connection.connection.close()
        if not connection._recv_fut.done():
            self.logger.debug("Cancelling future for connection")
            connection._recv_fut.cancel()

    async def _monkeypatched_dispose(self: Type[Connection]):
        self._connected = False

    async def _internal_close_chrome(self):
        self.logger.info("Terminating chrome process...")
        connection = self._launcher.connection
        datadir = self._launcher.temporaryUserDataDir
        if connection and connection._connected:
            try:
                self.logger.debug("Clearing out callbacks")
                # Send the close message
                self.logger.debug("Sending close to listener")
                # Monkeypatch connection
                # The reason I do this is because when you close the browser
                # it try to call a callback and try to dispatch the error
                # which I dont need, so basically this is to silent that bitch.
                original_dispose = pyppeteer.connection.Connection.dispose
                pyppeteer.connection.Connection.dispose = self._monkeypatched_dispose
                await connection.send("Browser.close")
                # Close the underlying connection and undo the monkeypatch
                pyppeteer.connection.Connection.dispose = original_dispose
                self.logger.debug("Closing underlying connection")
                await self._internal_close_connection(connection)
            except Exception as e:
                self.logger.debug(f"Failed to terminate chrome process: {e}", exc_info=e)
        if datadir and os.path.exists(datadir):
            self.logger.info("Trying to terminate chrome and removing data directory...")

    async def close(self):
        self.logger.info("Closing down browser and cleaning up...")
        if not self._launcher.chromeClosed:
            await self._internal_close_chrome()

    async def bind(self, card: CardTemplate):
        self.logger.info(f"Trying to create new page for {card.name}")
        if card.name in self._page_navigator:
            raise CardBindFailure(card, "Already binded")
        if "seleniumCallChange" not in card.html:
            raise CardBindFailure(card, "Missing seleniumCallChange() function")
        new_page = await self._browser.newPage()
        await new_page.goto(f"data:text/html;charset=utf-8,{card.html}")
        self._page_navigator[card.name] = CardGeneratorNav(card, new_page)
        page_no = len(self._page_navigator.keys())
        self.logger.info(f"Template {card.name} is now binded to a page {page_no}")

    @staticmethod
    def _generate_expression(json_data: dict) -> str:
        dumped_data = orjson.dumps(json_data).decode("utf-8").replace("'", "\\'")
        base_function = f"seleniumCallChange('{dumped_data}')"
        wrapped_expression = "() => {" + base_function + "; return '';}"
        return wrapped_expression

    async def _restart_all_page(self):
        new_navigator: Dict[str, CardGeneratorNav] = {}
        for page_name, page_nav in self._page_navigator.items():
            try:
                await page_nav.page.close()
            except Exception:
                self.logger.warning(f"Failed to close page {page_name}", exc_info=True)
            new_page = await self._browser.newPage()
            await new_page.goto(f"data:text/html;charset=utf-8,{page_nav.card.html}")
            self.logger.info(f"Restarted page {page_name}")
            new_navigator[page_name] = CardGeneratorNav(page_nav.card, new_page)
        self._page_navigator = new_navigator

    async def _keepalive(self, specific_page: str):
        if self._launcher.chromeClosed:
            self.logger.debug("Chrome is closed, trying to restart...")
            try:
                await self._internal_close_chrome()
            except Exception:
                pass
            self._browser = await self._launcher.launch()
            self.logger.debug("Chrome restarted, trying to restart pages...")
            await self._restart_all_page()
            self.logger.debug("All pages restarted")
            return

        page_info = self._page_navigator.get(specific_page)
        if page_info is None:
            self.logger.debug(f"Page {specific_page} is not binded")
            return

        if page_info.page.isClosed():
            self.logger.debug(f"Page {specific_page} is closed, reopening")
            new_page = await self._browser.newPage()
            await new_page.goto(f"data:text/html;charset=utf-8,{page_info.card.html}")
            page_info.page = new_page
            self._page_navigator[specific_page] = page_info
            return

    async def generate(self, name: str, data: CardBase) -> bytes:
        if name not in self._page_navigator:
            raise CardGenerationFailure(name, "Unknown template name")

        await self._keepalive(name)

        page_data = self._page_navigator[name]
        max_width = page_data.card.max_width
        pad_height = page_data.card.pad_height

        self.logger.info("Evaluating expression and function...")
        generated_eval = self._generate_expression(data.serialize())
        try:
            await page_data.page.evaluate(generated_eval)
        except Exception as e:
            self.logger.debug(f"Failed to evaluate expression: {e}", exc_info=e)
            raise CardGenerationFailure(name, f"Failed to evaluate expression: {e}")

        try:
            dimensions = await page_data.page.evaluate(
                """() => {
                    return {
                        width: document.body.clientWidth,
                        height: document.body.clientHeight,
                    }
                }
                """
            )
        except Exception as e:
            self.logger.debug(f"Failed to evaluate dimensions: {e}", exc_info=e)
            raise CardGenerationFailure(name, f"Failed to evaluate dimensions: {e}")
        self.logger.info("Taking a screenshot and cropping the image...")
        try:
            screenies = await page_data.page.screenshot()
        except Exception as e:
            self.logger.debug(f"Failed to take screenshot: {e}", exc_info=e)
            raise CardGenerationFailure(name, f"Failed to take screenshot: {e}")

        im = Image.open(BytesIO(screenies))
        im = im.crop((0, 0, max_width, dimensions["height"] + pad_height))
        img_byte_arr = BytesIO()
        im.save(img_byte_arr, format="PNG")
        return img_byte_arr.getvalue()
