import asyncio
import json
import logging
from io import BytesIO
from typing import Any, NamedTuple, Optional

from PIL import Image
from pyppeteer.browser import Browser
from pyppeteer.launcher import Launcher
from pyppeteer.page import Page
from websockets.exceptions import ConnectionClosedError

HTML_PAGE = """
<!DOCTYPE html>
<html>
    <head>
        <title>User Card Generator Page</title>
        <style>
            body {
                background-color: rgb(24, 25, 28);
                color: white;
                font-family: "Inter";
            }

            .p-online {
                border-color: #57F287 !important;
            }

            .p-idle {
                border-color: #FEE75C !important;
            }

            .p-dnd {
                border-color: #ED4245 !important;
            }

            .p-off {
                border-color: #b3b3b3 !important;
            }

            .mono {
                font-family: 'Courier New', Courier, monospace;
            }

            .bold {
                font-weight: 700;
            }
        </style>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
    </head>
    <body id="main-root" style="max-width: 500px; display: flex; flex-direction: column; ">
        <div style="display:flex;margin-left: 10px;margin-top: 20px;">
            <img id="img-base" style="border-radius: 9999px; z-index: 10;" src="https://cdn.discordapp.com/avatars/466469077444067372/95d2673b3cd4d66e73e2bb05a6f8df31.png?size=1024" width="128" height="128">
            <div id="avatar-status" class="p-idle" style="position: absolute;border: 2px solid;width: 135px;height: 135px;/* margin-right: 2px; */border-radius: 9999px;margin-left: -6px;margin-top: -5.5px;"></div>
            <div style="font-weight: 700; margin-left: 20px; display: flex; gap: 0;font-size: 20px;">
                <span id="uname">N4O<span style="color:#b3b3b3;" id="udisc">#8868</span></span>
            </div>
        </div>
        <div style="display: flex; flex-direction: column;margin-left: 10px;margin-top:20px;gap: 4px">
            <div style="display: flex;">
                <span id="nname"><span style="font-weight: 700;">Panggilan</span>: Tidak ada</span>
            </div>
            <div style="display: flex; flex-direction: row; align-items: center;">
                <span style="width: 10px; height: 10px; background-color: #FEE75C; border-radius: 9999px;" id="status-bubble"></span>
                <span style="margin-left: 4px"><span style="font-weight: 700;">Status</span>: Halo????</span>
            </div>
            <span style="margin-top: 8px; margin-bottom: 4px; font-weight: 700;">Takhta Tertinggi</span>
            <div style="display: flex; flex-direction: row; margin-top: 5px;">
                <div style="display: flex; flex-direction: row; align-items: center; padding: 2px; border: 2px solid; border-color: rgb(185, 187, 190); border-radius: 20px" id="role-wrap">
                    <span style="width: 10px; height: 10px; background-color: rgb(185, 187, 190); border-radius: 9999px; margin-left: 3px" id="role-bubble"></span>
                    <span style="margin-right: 4px; margin-left: 4px; font-weight: 700;" id="role-name">Admin</span>
                </div>
            </div>
            <div style="display: flex; margin-top: 5px;">
                <span><span style="font-weight: 700;">Akun Dibuat</span>: Rabu, 11 Juli 2018 @ 05:01:34</span>
            </div>
            <div style="display: flex; margin-top: 2px;">
                <span><span style="font-weight: 700;">Bergabung</span>: Sabtu, 03 Oktober 2020 @ 11:44:54</span>
            </div>
        </div>
        <script type="text/javascript">
            "use strict";

            const colorMap = {
                online: "#57F287",
                idle: "#FEE75C",
                dnd: "#ED4245",
                off: "#b3b3b3"
            }
            const AVATAR_DEFAULT = "iVBORw0KGgoAAAANSUhEUgAAAfQAAAH0CAIAAABEtEjdAAAACXBIWXMAAC4jAAAuIwF4pT92AAAF0WlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQiPz4gPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iQWRvYmUgWE1QIENvcmUgNS42LWMxNDUgNzkuMTYzNDk5LCAyMDE4LzA4LzEzLTE2OjQwOjIyICAgICAgICAiPiA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiPiA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIiB4bWxuczp4bXA9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC8iIHhtbG5zOnhtcE1NPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvbW0vIiB4bWxuczpzdEV2dD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlRXZlbnQjIiB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iIHhtbG5zOnBob3Rvc2hvcD0iaHR0cDovL25zLmFkb2JlLmNvbS9waG90b3Nob3AvMS4wLyIgeG1wOkNyZWF0b3JUb29sPSJBZG9iZSBQaG90b3Nob3AgQ0MgMjAxOSAoV2luZG93cykiIHhtcDpDcmVhdGVEYXRlPSIyMDIxLTA3LTEwVDEzOjI4OjM2KzA3OjAwIiB4bXA6TWV0YWRhdGFEYXRlPSIyMDIxLTA3LTEwVDEzOjI4OjM2KzA3OjAwIiB4bXA6TW9kaWZ5RGF0ZT0iMjAyMS0wNy0xMFQxMzoyODozNiswNzowMCIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlpZDozYjljOWJhMS0yZmNhLTI1NGYtOWJjYi01ZThlZDk3MDQwNzQiIHhtcE1NOkRvY3VtZW50SUQ9ImFkb2JlOmRvY2lkOnBob3Rvc2hvcDpiNDdiNWJhMC0xYTQyLTk0NDQtYmZi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";
            const DEFAULT_COL = "rgb(185, 187, 190)";
            const uName = document.evaluate("/html/body/div[1]/div[2]/span/text()", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            const panggilan = document.evaluate("/html/body/div[2]/div[1]/span/text()", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            const statusText = document.evaluate("/html/body/div[2]/div[2]/span[2]/text()", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            const createdAt = document.evaluate("/html/body/div[2]/div[4]/span/text()", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            const joinedAt = document.evaluate("/html/body/div[2]/div[5]/span/text()", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;

            function changeData(fullData) {
                let { u, ud, un, created, joined, highRole: {hName, hCol}, status: {sText, sId}, avaB64 } = fullData;

                const selColor = colorMap[sId || "off"];
                panggilan.data = `: ${un || "Tidak ada"}`;
                statusText.data = `: ${sText || "Tidak diketahui"}`;

                document.getElementById("avatar-status").className = `p-${sId || "off"}`
                document.getElementById("status-bubble").style.backgroundColor = selColor;

                createdAt.data = `: ${created || "Tidak diketahui"}`;
                joinedAt.data = `: ${joined || "Tidak diketahui"}`;

                document.getElementById("role-wrap").style.borderColor = hCol || DEFAULT_COL;
                document.getElementById("role-bubble").style.backgroundColor = hCol || DEFAULT_COL;
                document.getElementById("role-name").textContent = hName || "Tidak diketahui";
                uName.data = u || "[????]";
                document.getElementById("udisc").textContent = `#${ud || "0000"}`;
                document.getElementById("img-base").setAttribute("src", avaB64 || `data:image/png;base64,${AVATAR_DEFAULT}`);
            }

            function seleniumCallChange(stringData) {
                const loadedData = JSON.parse(stringData);
                changeData(loadedData || {highRole: {}, status: {}});
            }
        </script>
    </body>
</html>
"""  # noqa: E501


class UserCardGenerationFailure(Exception):
    pass


class UserCardHighRole(NamedTuple):
    name: str
    color: str

    def serialize(self):
        return {
            "hName": self.name,
            "hCol": self.color,
        }


class UserCardStatus(NamedTuple):
    id: str
    text: str

    def serialize(self):
        return {"sText": self.text, "sId": self.id}


class UserCard(NamedTuple):
    username: str
    discriminator: str
    nickname: Optional[str]
    createdAt: str
    joinedAt: str
    highest_role: UserCardHighRole
    status: UserCardStatus
    avatar: str

    def serialize(self):
        real_data = {
            "u": self.username,
            "ud": self.discriminator,
            "created": self.createdAt,
            "joinedAt": self.joinedAt,
            "highRole": self.highest_role.serialize(),
            "status": self.status.serialize(),
            "avaB64": self.avatar,
        }
        if isinstance(self.nickname, str) and len(self.nickname) > 0 and self.nickname != self.username:
            real_data["un"] = self.nickname
        return real_data


class UserCardGenerator:
    def __init__(self, loop: asyncio.AbstractEventLoop = None) -> None:
        self._browser: Browser = None
        self._page: Page = None
        self._loop = loop
        if not self._loop:
            self._loop = asyncio.get_event_loop()
        self._launcher = Launcher(
            None,
            headless=True,
            loop=self._loop,
            logLevel=logging.INFO,
            autoClose=False,
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False,
        )
        self.logger = logging.getLogger("usercard.UserCardGenerator")

    async def init(self):
        self.logger.info("Initiating the headless browser...")
        self._browser = await self._launcher.launch()
        self._page = await self._browser.newPage()
        self.logger.info("Navigating to the UserCard HTML!")
        await self._page.goto(f"data:text/html;charset=utf-8,{HTML_PAGE}")
        self.logger.info("Card generator ready!")

    async def close(self):
        self.logger.info("Closing down browser and cleaning up...")
        if not self._launcher.chromeClosed:
            try:
                await self._launcher.killChrome()
            except (
                asyncio.exceptions.CancelledError,
                ConnectionClosedError,
                asyncio.exceptions.InvalidStateError,
            ):
                pass

    @staticmethod
    def _generate_expression(json_data: Any):
        function_value = f"seleniumCallChange('{json.dumps(json_data, ensure_ascii=False)}')"
        wrapped_function = "() => {" + function_value + "; return '';}"
        return wrapped_function

    async def generate(self, user: UserCard):
        if self._page is None:
            raise UserCardGenerationFailure("The page is not loaded yet!")
        self.logger.info("Evaluating expression and function...")
        generated_eval = self._generate_expression(user.serialize())
        await self._page.evaluate(generated_eval)
        dimensions = await self._page.evaluate(
            """() => {
                return {
                    width: document.body.clientWidth,
                    height: document.body.clientHeight,
                }
            }
            """
        )
        self.logger.info("Taking a screenshot of the page and cropping it...")
        screenies = await self._page.screenshot()

        im = Image.open(BytesIO(screenies))
        im = im.crop((0, 0, 510, dimensions["height"] + 40))
        img_byte_arr = BytesIO()
        im.save(img_byte_arr, format="PNG")
        return img_byte_arr.getvalue()
