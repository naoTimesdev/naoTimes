import logging
from enum import Enum
from typing import Tuple

import discord
from discord.ext import app, commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.utils import complex_walk, quoteblock


class KursType(Enum):
    CURRENCY = 0
    CRYPTO = 1


class PeninjauKursMataUang(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.KursUang")
        self.CRYPTO = bot.jsdb_crypto
        self.CURRENCY = bot.jsdb_currency

    async def _fetch_yahoo_finance(self, ticker_from: str, ticker_target: str):
        body_data = {
            "data": {
                "base": ticker_from.upper(),
                "period": "week",
                "term": ticker_target.upper(),
            },
            "method": "spotRateHistory",
        }
        extra_headers = {
            "Origin": "https://widget-yahoo.ofx.com",
            "Referer": "https://widget-yahoo.ofx.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36",  # noqa: E501
        }
        async with self.bot.aiosession.post(
            "https://api.rates-history-service.prd.aws.ofx.com/rate-history/api/1",
            headers=extra_headers,
            json=body_data,
        ) as response:
            try:
                result = await response.json()
                return complex_walk(result, "data.CurrentInterbankRate")
            except Exception as e:
                self.logger.error(f"Error fetching data from Yahoo Finance: {e}")
                return "Gagal memproses hasil, mengekspetasi JSON tetapi mendapatkan HTML"

    async def _fetch_coinmarketcap(self, ticker_from: str, ticker_target: str):
        extra_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip",
            "accept-language": "en-US,en;q=0.9,id-ID;q=0.8,id;q=0.7,ja-JP;q=0.6,ja;q=0.5",  # noqa: E501
            "cache-control": "no-cache",
            "origin": "https://coinmarketcap.com",
            "referer": "https://coinmarketcap.com/converter/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36",  # noqa: E501
        }
        URL_TARGET = (
            "https://api.coinmarketcap.com/data-api/v3/tools/price-conversion?amount=1&convert_id={t}&id={f}"
        )

        async with self.bot.aiosession.get(
            URL_TARGET.format(f=ticker_from, t=ticker_target),
            headers=extra_headers,
        ) as response:
            try:
                result = await response.json()
                error_msg = complex_walk(result, "status.error_message")
                if error_msg and error_msg != "SUCCESS":
                    return f"Tidak dapat terhubung dengan API.\nAPI Response: {quoteblock(error_msg)}"
                error_msg = error_msg or "Unknown error"
                if response.status >= 300:
                    return f"Tidak dapat terhubung dengan API.\nAPI Response: {quoteblock(error_msg)}"
                return complex_walk(result, "data.quote.0.price")
            except Exception as e:
                self.logger.error(f"Error fetching data from CoinMarketCap: {e}")
                return "Gagal memproses hasil, mengekspetasi JSON tetapi mendapatkan HTML"

    @staticmethod
    def _rounded_nicely(now: float, total: float) -> Tuple[str, int]:
        nnr = 2
        while True:
            conv_num = round(now * total, nnr)
            safe_str = str(conv_num).replace(".", "")
            if safe_str.count("0") != len(safe_str):
                break
            nnr += 1
        mm = str(conv_num)
        if "e-" in mm:
            nnr = int(mm.split("e-")[1]) + 1
        formatter = ",." + str(nnr) + "f"
        return format(conv_num, formatter), nnr

    async def _process_kurs(self, dari: str, ke: str, jumlah: float = None):
        before, after = dari.upper(), ke.upper()
        if before == after:
            return "Apakah anda bodoh?"

        MODE_LIST = {
            KursType.CRYPTO: {
                "text": "Diprakasai dengan CoinMarketCap dan yahoo!finance",
                "icon_url": "https://p.ihateani.me/zbpzveak.png",
            },
            KursType.CURRENCY: {
                "text": "Diprakasai dengan yahoo!finance",
                "icon_url": "https://ihateani.me/o/y!.png",
            },
        }

        ALL_CRYPTO = False
        MODE = KursType.CURRENCY
        if before in self.CRYPTO and after in self.CRYPTO:
            ticker_from = str(self.CRYPTO[before]["id"])
            ticker_to = str(self.CRYPTO[after]["id"])
            symbol_from = self.CRYPTO[before]["symbol"]
            symbol_to = self.CRYPTO[after]["symbol"]
            name_from = self.CRYPTO[before]["name"]
            name_to = self.CRYPTO[after]["name"]
            ALL_CRYPTO = True
            MODE = KursType.CRYPTO
        elif after in self.CRYPTO:
            ticker_from = "2781"
            ticker_to = str(self.CRYPTO[after]["id"])
            if before not in self.CURRENCY:
                return f"Tidak dapat menemukan kode negara mata utang **{before}** di database"
            symbol_from = self.CURRENCY[before]["symbols"][0]
            symbol_to = self.CRYPTO[after]["symbol"]
            name_from = self.CURRENCY[before]["name"]
            name_to = self.CRYPTO[after]["name"]
            after = "USD"
            MODE = KursType.CRYPTO
        elif before in self.CRYPTO and after in self.CURRENCY:
            ticker_from = str(self.CRYPTO[before]["id"])
            ticker_to = "2781"
            if after not in self.CURRENCY:
                return f"Tidak dapat menemukan kode negara mata utang **{after}** di database"
            symbol_from = self.CRYPTO[before]["symbol"]
            symbol_to = self.CURRENCY[after]["symbols"][0]
            name_from = self.CRYPTO[before]["name"]
            name_to = self.CURRENCY[after]["name"]
            before = "USD"
            MODE = KursType.CRYPTO
        elif before in self.CURRENCY and after in self.CURRENCY:
            ticker_from = before
            ticker_to = after
            symbol_from = self.CURRENCY[before]["symbols"][0]
            symbol_to = self.CURRENCY[after]["symbols"][0]
            name_from = self.CURRENCY[before]["name"]
            name_to = self.CURRENCY[after]["name"]
        else:
            if before not in self.CURRENCY:
                return f"Tidak dapat menemukan kode negara mata utang **{before}** di database"
            elif after not in self.CURRENCY:
                return f"Tidak dapat menemukan kode negara mata utang **{after}** di database"
            return "Tidak dapat menemukan salah kode negara mata uang!"

        crypto_currency = None
        if MODE == KursType.CRYPTO:
            self.logger.info(f"converting crypto ({ticker_from} -> {ticker_to})")
            crypto_currency = await self._fetch_coinmarketcap(ticker_from, ticker_to)
            self.logger.debug(f"crypto conversion rate for {ticker_from} -> {ticker_to} is {crypto_currency}")
            if isinstance(crypto_currency, str):
                return crypto_currency

        if not ALL_CRYPTO:
            self.logger.info(f"converting {before} -> {after}")
            currency_data = await self._fetch_yahoo_finance(before, after)
            self.logger.debug(f"Conversion rate for {before} -> {after} is {currency_data}")
            if isinstance(currency_data, str):
                return currency_data

        if not jumlah:
            jumlah = 1.0

        if MODE == KursType.CRYPTO:
            if not ALL_CRYPTO:
                currency_data = currency_data * crypto_currency
            else:
                currency_data = crypto_currency

        self.logger.info("Rounding results...")
        converted_number, _ = self._rounded_nicely(currency_data, jumlah)
        embed = discord.Embed(
            title=":gear: Konversi mata uang", colour=0x50E3C2, timestamp=self.bot.now().datetime
        )
        description = [f":small_red_triangle_down: `{name_from}` ke `{name_to}`"]
        description.append(f":small_orange_diamond: {symbol_from}{jumlah:,}")
        description.append(f":small_blue_diamond: {symbol_to}{converted_number}")
        embed.description = "\n".join(description)
        embed.set_footer(**MODE_LIST.get(MODE, MODE_LIST[KursType.CURRENCY]))
        return embed

    @app.slash_command(
        name="kurs",
        description="Konversi mata uang dari satu mata uang ke yang lain",
    )
    @app.option("dari", str, description="Mata uang awal")
    @app.option("ke", str, description="Mata uang tujuan")
    @app.option("jumlah", str, description="Jumlah yang ingin diubah", required=False)
    async def _peninjau_kurs_slash(self, ctx: app.ApplicationContext, dari: str, ke: str, jumlah: str = None):
        if jumlah:
            try:
                jumlah = float(jumlah)
            except ValueError:
                return await ctx.send(
                    content="Bukan jumlah uang yang valid (jangan memakai koma, pakai titik)"
                )

        await ctx.defer()
        embed = await self._process_kurs(dari, ke, jumlah)
        if isinstance(embed, str):
            return await ctx.send(embed)
        await ctx.send(embed=embed)

    @commands.command(name="kurs", aliases=["konversiuang", "currency"])
    async def _peninjau_kurs_cmd(self, ctx: naoTimesContext, dari: str, ke: str, jumlah: float = None):
        embed = await self._process_kurs(dari, ke, jumlah)
        if isinstance(embed, str):
            return await ctx.send(embed)

        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(PeninjauKursMataUang(bot))
