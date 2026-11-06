import logging
from collections.abc import Callable
from enum import Enum

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.utils import FIREFOX_USER_AGENT, complex_walk, quoteblock


class KursType(Enum):
    CURRENCY = 0
    CRYPTO = 1


class PeninjauKursMataUang(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.KursUang")
        self.CRYPTO = bot.jsdb_crypto
        self.CURRENCY = bot.jsdb_currency

    async def _fetch_yahoo_finance(self, ticker_from: str, ticker_target: str, t: Callable[..., str]):
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
            "User-Agent": FIREFOX_USER_AGENT,
        }
        if self.bot.aiosession is None:
            return t("kurs.http_unavailable")
        async with self.bot.aiosession.post(
            "https://api.rates-history-service.prd.aws.ofx.com/rate-history/api/1",
            headers=extra_headers,
            json=body_data,
        ) as response:
            try:
                result = await response.json()
                rate = complex_walk(result, "data.CurrentInterbankRate")
                if isinstance(rate, (int, float)) and not isinstance(rate, bool):
                    return float(rate)
                return t("kurs.invalid_rate")
            except Exception as e:
                self.logger.error(f"Error fetching data from Yahoo Finance: {e}")
                return t("kurs.json_error")

    async def _fetch_coinmarketcap(self, ticker_from: str, ticker_target: str, t: Callable[..., str]):
        extra_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip",
            "accept-language": "en-US,en;q=0.9,id-ID;q=0.8,id;q=0.7,ja-JP;q=0.6,ja;q=0.5",
            "cache-control": "no-cache",
            "origin": "https://coinmarketcap.com",
            "referer": "https://coinmarketcap.com/converter/",
            "user-agent": FIREFOX_USER_AGENT,
        }
        URL_TARGET = "https://api.coinmarketcap.com/data-api/v3/tools/price-conversion?amount=1&convert_id={t}&id={f}"

        if self.bot.aiosession is None:
            return t("kurs.http_unavailable")
        async with self.bot.aiosession.get(
            URL_TARGET.format(f=ticker_from, t=ticker_target),
            headers=extra_headers,
        ) as response:
            try:
                result = await response.json()
                error_msg = complex_walk(result, "status.error_message")
                if error_msg and error_msg != "SUCCESS":
                    return t("kurs.api_connect_failed", response=quoteblock(str(error_msg)))
                error_msg = error_msg or t("kurs.unknown_error")
                if response.status >= 300:
                    return t("kurs.api_connect_failed", response=quoteblock(error_msg))
                rate = complex_walk(result, "data.quote.0.price")
                if isinstance(rate, (int, float)) and not isinstance(rate, bool):
                    return float(rate)
                return t("kurs.invalid_crypto_rate")
            except Exception as e:
                self.logger.error(f"Error fetching data from CoinMarketCap: {e}")
                return t("kurs.json_error")

    @staticmethod
    def _rounded_nicely(now: float, total: float) -> tuple[str, int]:
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

    async def _process_kurs(self, dari: str, ke: str, jumlah: float | None, t: Callable[..., str]):
        before, after = dari.upper(), ke.upper()
        if before == after:
            return t("kurs.same_currency")
        if jumlah is None:
            jumlah = 1.0

        MODE_LIST = {
            KursType.CRYPTO: {
                "text": t("kurs.powered_crypto"),
                "icon_url": "https://p.ihateani.me/zbpzveak.png",
            },
            KursType.CURRENCY: {
                "text": t("kurs.powered_currency"),
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
                return t("kurs.unknown_code", code=before)
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
                return t("kurs.unknown_code", code=after)
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
                return t("kurs.unknown_code", code=before)
            elif after not in self.CURRENCY:
                return t("kurs.unknown_code", code=after)
            return t("kurs.unknown_code_generic")

        crypto_currency = None
        currency_data: float | None = None
        if MODE == KursType.CRYPTO:
            self.logger.info(f"converting crypto ({ticker_from} -> {ticker_to})")
            crypto_currency = await self._fetch_coinmarketcap(ticker_from, ticker_to, t)
            self.logger.debug(f"crypto conversion rate for {ticker_from} -> {ticker_to} is {crypto_currency}")
            if isinstance(crypto_currency, str):
                return crypto_currency
            if ALL_CRYPTO:
                currency_data = crypto_currency

        if not ALL_CRYPTO:
            self.logger.info(f"converting {before} -> {after}")
            yahoo_rate = await self._fetch_yahoo_finance(before, after, t)
            if isinstance(yahoo_rate, str):
                return yahoo_rate
            currency_data = yahoo_rate
            self.logger.debug(f"Conversion rate for {before} -> {after} is {currency_data}")

        if not jumlah:
            jumlah = 1.0

        if MODE == KursType.CRYPTO:
            if not ALL_CRYPTO:
                if currency_data is None or crypto_currency is None:
                    return t("kurs.fetch_failed")
                currency_data = currency_data * crypto_currency

        if currency_data is None:
            return t("kurs.fetch_failed")

        self.logger.info("Rounding results...")
        converted_number, _ = self._rounded_nicely(currency_data, jumlah)
        embed = discord.Embed(title=t("kurs.title"), colour=0x50E3C2, timestamp=self.bot.now().datetime)
        description = [t("kurs.conversion", source=name_from, target=name_to)]
        description.append(t("kurs.amount", symbol=symbol_from, amount=f"{jumlah:,}"))
        description.append(t("kurs.result", symbol=symbol_to, amount=converted_number))
        embed.description = "\n".join(description)
        embed.set_footer(**MODE_LIST.get(MODE, MODE_LIST[KursType.CURRENCY]))
        return embed

    @app_commands.command(
        name="kurs",
        description=app_commands.locale_str(
            "Konversi mata uang dari satu mata uang ke yang lain", key="peninjau.kurs.description"
        ),
    )
    @app_commands.describe(
        dari=app_commands.locale_str("Mata uang awal", key="peninjau.kurs.option_from"),
        ke=app_commands.locale_str("Mata uang tujuan", key="peninjau.kurs.option_to"),
        jumlah=app_commands.locale_str("Jumlah mata uang yang ingin ditukar", key="peninjau.kurs.option_amount"),
    )
    async def _peninjau_kurs_slash(self, inter: discord.Interaction, dari: str, ke: str, jumlah: str | None = None):
        """Konversi mata uang dari satu mata uang ke yang lain"""
        ctx = await self.bot.get_context(inter)
        parsed_amount: float | None = None
        if jumlah:
            try:
                parsed_amount = float(jumlah)
            except ValueError:
                return await ctx.send(content=ctx.t("kurs.invalid_amount"))

        await ctx.defer()
        embed = await self._process_kurs(dari, ke, parsed_amount, ctx.t)
        if isinstance(embed, str):
            return await ctx.send(embed)
        await ctx.send(embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(PeninjauKursMataUang(bot))
