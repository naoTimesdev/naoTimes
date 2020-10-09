import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple, Union

import aiohttp
import discord
from discord.ext import commands
from nthelper.bot import naoTimesBot

wlogger = logging.getLogger("cogs.cuaca")


async def fetch_geolat(
    location: str, GEOCODE_API: str
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    API_ENDPOINT = "https://api.opencagedata.com/geocode/v1/json"
    wlogger.info(f"Finding: {location}")
    param = {
        "q": location,
        "key": GEOCODE_API,
    }
    async with aiohttp.ClientSession(headers={"User-Agent": "api.ihateani.me/0.7.3"}) as session:
        async with session.get(API_ENDPOINT, params=param) as resp:
            res = await resp.json()
            if res["results"] == []:
                wlogger.info("No results.")
                return None, None, None
            first_res = res["results"][0]
            geometry = first_res["geometry"]
    lat, lng = geometry["lat"], geometry["lng"]
    loc_name = first_res["formatted"]
    wlogger.info(f"Info get! Location name: {loc_name}")
    return lat, lng, loc_name


def get_uv_index(uvi: int) -> str:
    uvi_index = str(uvi)
    if uvi < 3:
        uvi_index += " (Rendah)"
    elif uvi >= 3 and uvi < 6:
        uvi_index += " (Menengah)"
    elif uvi >= 6 and uvi < 8:
        uvi_index += " (Tinggi)"
    elif uvi >= 8 and uvi < 11:
        uvi_index += " (Sangat Tinggi)"
    elif uvi >= 11:
        uvi_index += " (Ekstrim/Bahaya)"
    return uvi_index


def get_rain_intensity(precipitation: float) -> str:
    if precipitation <= 2.5:
        intensity = "Hujan ringan"
    elif precipitation > 2.5 and precipitation <= 10:
        intensity = "Hujan sedang"
    elif precipitation > 10 and precipitation <= 50:
        intensity = "Hujan lebat"
    elif precipitation > 50:
        intensity = "Hujan deras"
    return intensity


def translate_day(day_name: str) -> str:
    day_set = {
        "Monday": "Senin",
        "Tuesday": "Selasa",
        "Wednesday": "Rabu",
        "Thursday": "Kamis",
        "Friday": "Jumat",
        "Saturday": "Sabtu",
        "Sunday": "Minggu",
    }
    return day_set.get(day_name, day_name)


def get_wind_degrees(wind_deg: Union[float, int]) -> str:
    if wind_deg < 45:
        res = f"↑ {wind_deg}°"
    elif wind_deg >= 45 and wind_deg < 90:
        res = f"↗ {wind_deg}°"
    elif wind_deg >= 90 and wind_deg < 135:
        res = f"→ {wind_deg}°"
    elif wind_deg >= 135 and wind_deg < 180:
        res = f"↘ {wind_deg}°"
    elif wind_deg >= 180 and wind_deg < 225:
        res = f"↓ {wind_deg}°"
    elif wind_deg >= 225 and wind_deg < 270:
        res = f"↙ {wind_deg}°"
    elif wind_deg >= 270 and wind_deg < 315:
        res = f"← {wind_deg}°"
    elif wind_deg >= 315 and wind_deg < 360:
        res = f"↖ {wind_deg}°"
    else:
        res = f"↑ {wind_deg}°"
    return res


async def fetch_owm(location: str, bot_conf: dict) -> Union[dict, str]:
    wlogger.info("Fetching GeoCode...")
    geo_lat, geo_lng, loc_name = await fetch_geolat(location, bot_conf["weather_data"]["opencageapi"])
    if geo_lat is None:
        return {}

    wicon_template = "https://openweathermap.org/img/wn/{ic}@2x.png"
    hyperlink = "https://openweathermap.org/weathermap?lat={lat}&lon={lon}"
    weather_ids_mappings = {
        200: "⛈️",
        201: "⛈️",
        202: "⛈️",
        210: "🌩️",
        211: "🌩️",
        212: "🌩️",
        221: "🌩️",
        230: "⛈️",
        231: "⛈️",
        232: "⛈️",
        300: "🌧️",
        301: "🌧️",
        302: "🌧️",
        310: "🌧️",
        311: "🌧️",
        312: "🌧️",
        313: "🌧️",
        314: "🌧️",
        321: "🌧️",
        500: "🌧️",
        501: "🌧️",
        502: "🌧️",
        503: "🌧️",
        504: "🌧️",
        511: "🌨️",
        520: "🌧️",
        521: "🌧️",
        522: "🌧️",
        531: "🌧️",
        600: "❄️",
        601: "❄️",
        602: "❄️",
        611: "❄️",
        612: "🌨️",
        613: "🌨️",
        615: "🌨️",
        616: "🌨️",
        620: "🌨️",
        621: "🌨️",
        622: "🌨️",
        701: "🌫️",
        711: "💨",
        721: "🌫️",
        731: "💨",
        741: "🌁",
        751: "💨",
        761: "💨",
        762: "🌋",
        771: "🌀",
        781: "🌪️",
        800: "☀️",
        801: "⛅",
        802: "☁️",
        803: "☁️",
        804: "☁️",
    }
    weather_tls_mappings = {
        200: "Badai petir dengan hujan ringan",
        201: "Badai petir dengan hujan",
        202: "Badai petir dengan hujan deras",
        210: "Badai petir ringan",
        211: "Badai petir",
        212: "Badai petir lebat",
        221: "Badai petir buruk",
        230: "Badai petir dengan gerimis ringan",
        231: "Badai petir dengan gerimis",
        232: "Badai petir dengan gerimis lebat",
        300: "Gerimis ringan",
        301: "Gerimis",
        302: "Gerimis lebat",
        310: "Hujan gerimis ringan",
        311: "Hujan gerimis",
        312: "Hujan gerimis lebat",
        313: "Hujan dan gerimis",
        314: "Hujan lebat dan gerimis",
        321: "Gerimis lebat",
        500: "Hujan ringan",
        501: "Hujan sedang",
        502: "Hujan lebat",
        503: "Hujan sangat lebat",
        504: "Hujan ekstrim",
        511: "Hujan dingin",
        520: "Hujan ringan singkat",
        521: "Hujan singkat",
        522: "Hujan lebat singkat",
        531: "Hujan buruk singkat",
        600: "Bersalju ringan",
        601: "Bersalju",
        602: "Bersalju tebal",
        611: "Hujan es",
        612: "Hujan es ringan",
        613: "Hujan es singkat",
        615: "Hujan ringan dan bersalju",
        616: "Hujan dan bersalju",
        620: "Hujan singkat dan bersalju",
        621: "Salju singkat",
        622: "Salju tebal singkat",
        701: "Berkabut",
        711: "Berasap",
        721: "Berkabut tipis",
        731: "Pusaran debu",
        741: "Berkabut",
        751: "Berdebu pasir",
        761: "Berdebu",
        762: "Abu vulkanik",
        771: "Angin badai",
        781: "Angin topan",
        800: "Cerah",
        801: "Berawan ringan",
        802: "Berawan",
        803: "Berawan cukup tebal",
        804: "Berawan tebal",
    }

    param_req = {
        "lat": str(geo_lat),
        "lon": str(geo_lng),
        "exclude": "minutely,hourly",
        "appid": bot_conf["weather_data"]["openweatherapi"],
        "units": "metric",
        "lang": "id",
    }

    wlogger.info("Requesting to OWM API...")
    wlogger.info(f"{geo_lat}, {geo_lng}")
    API_ENDPOINT = "https://api.openweathermap.org/data/2.5/onecall"
    async with aiohttp.ClientSession() as sesi:
        async with sesi.get(API_ENDPOINT, params=param_req) as resp:
            wlogger.info("[OWN] Parsing data...")
            weather_res = await resp.json()

    if "cod" in weather_res:
        if weather_res["cod"] == 401:
            return "API key bot owner belum terautentikasi. Mohon kontak Bot Owner atau tunggu beberapa jam kemudian."  # noqa: E501
        else:
            return weather_res["message"]

    wlogger.info("Parsing current weather data...")
    tz_off = weather_res["timezone_offset"]
    full_dataset: Dict[str, Any] = {}
    full_dataset["location"] = loc_name
    full_dataset["url"] = hyperlink.format(lat=geo_lat, lon=geo_lng)
    full_dataset["coords"] = {
        "lat": geo_lat,
        "lon": geo_lng,
    }

    current_weather: Dict[str, Any] = {}
    try:
        currents = weather_res["current"]
        current_weather["temp"] = f"{currents['temp']}°C"
        current_weather["feels_like"] = f"{currents['feels_like']}°C"
        try:
            current_weather["uv"] = get_uv_index(currents["uvi"])
        except KeyError:
            pass
        try:
            current_weather["clouds"] = f"{currents['clouds']}%"
        except KeyError:
            pass
        current_weather["pressure"] = f"{currents['pressure']}hPa"
        current_weather["humidity"] = f"{currents['humidity']}%"

        try:
            sunrise = datetime.fromtimestamp(currents["sunrise"] + tz_off, tz=timezone.utc).strftime(
                "%I:%M AM"
            )
            sunset = datetime.fromtimestamp(currents["sunset"] + tz_off, tz=timezone.utc).strftime("%I:%M PM")

            current_weather["sstime"] = {
                "sunrise": sunrise,
                "sunset": sunset,
            }
        except KeyError:
            pass

        cweather = currents["weather"][0]
        cw_desc_orig = cweather["description"]
        cw_desc_orig = cw_desc_orig[0].upper() + cw_desc_orig[1:]
        cweather_data = {}
        cweather_data["icon"] = wicon_template.format(ic=cweather["icon"])
        cweather_data["description"] = weather_tls_mappings.get(cweather["id"], cw_desc_orig)
        cweather_data["emoji"] = weather_ids_mappings.get(cweather["id"], "")
        full_dataset["weather"] = cweather_data

        cwind_data = {}
        cwind_data["speed"] = f"{currents['wind_speed']}m/s"
        cwind_data["deg"] = get_wind_degrees(currents["wind_deg"])
        current_weather["wind"] = cwind_data

        try:
            rain_data: Dict[str, Any] = {}
            rain_data["precipitation"] = f"{currents['rain']['1h']}mm"
            rain_data["intensity"] = get_rain_intensity(currents["rain"]["1h"])
            current_weather["rain"] = rain_data
        except KeyError:
            pass
    except KeyError:
        pass

    full_dataset["current"] = current_weather
    last_7days_data = weather_res["daily"][-6:]

    wlogger.info("Parsing daily data...")
    last_7days_compiled = []
    for daily_data in last_7days_data:
        d_data: Dict[str, Any] = {}
        datedata = datetime.fromtimestamp(daily_data["dt"] + tz_off, tz=timezone.utc)
        temp_data = daily_data["temp"]
        d_data["date_name"] = translate_day(datedata.strftime("%A"))
        d_data["temp"] = {
            "high": f"{temp_data['max']}°C",
            "low": f"{temp_data['min']}°C",
            "day": f"{temp_data['day']}°C",
            "night": f"{temp_data['night']}°C",
        }
        try:
            d_data["uv"] = get_uv_index(daily_data["uvi"])
        except KeyError:
            pass
        d_data["pressure"] = f"{daily_data['pressure']}hPa"
        d_data["humidity"] = f"{daily_data['humidity']}%"
        try:
            d_data["clouds"] = f"{daily_data['clouds']}%"
        except KeyError:
            pass

        try:
            d_rain_data: Dict[str, Any] = {}
            d_rain_data["precipitation"] = f"{daily_data['rain']}mm"
            d_rain_data["intensity"] = get_rain_intensity(daily_data["rain"])
            d_data["rain"] = d_rain_data
        except KeyError:
            pass

        ld_wdata: Dict[str, Any] = {}
        ld_weather = daily_data["weather"][0]
        ldw_desc_orig = ld_weather["description"]
        ldw_desc_orig = ldw_desc_orig[0].upper() + ldw_desc_orig[1:]
        ld_wdata["icon"] = wicon_template.format(ic=ld_weather["icon"])
        ld_wdata["description"] = weather_tls_mappings.get(ld_weather["id"], ldw_desc_orig)
        ld_wdata["emoji"] = weather_ids_mappings.get(ld_weather["id"], "")
        d_data["weather"] = ld_wdata
        last_7days_compiled.append(d_data)

    full_dataset["daily"] = last_7days_compiled
    return full_dataset


class CuacaDunia(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.cuaca.CuacaDunia")

    @commands.command(aliases=["c", "w", "weather"])
    async def cuaca(self, ctx, *, lokasi: str):
        self.logger.info("Requested !cuaca command...")
        if "weather_data" not in self.bot.botconf:
            return await ctx.send(
                "Owner Bot tidak memberikan API Key untuk command cuaca, mohon kontak owner."
            )
        if "openweatherapi" not in self.bot.botconf and self.bot.botconf["openweatherapi"] == "":
            return await ctx.send(
                "Owner Bot tidak memberikan API Key OpenWeatherMap untuk command cuaca, mohon kontak owner."
            )
        if "opencageapi" not in self.bot.botconf and self.bot.botconf["opencageapi"] == "":
            return await ctx.send(
                "Owner Bot tidak memberikan API Key OpenCage untuk command cuaca, mohon kontak owner."
            )
        hasil_cuaca = await fetch_owm(lokasi, self.bot.botconf)
        if isinstance(hasil_cuaca, str):
            self.logger.error(hasil_cuaca)
            return await ctx.send(hasil_cuaca)
        if hasil_cuaca == {}:
            self.logger.warn("no results")
            return await ctx.send("Tidak dapat menemukan lokasi tersebut.")

        self.logger.info(f"{lokasi}: Processing cuaca results...")
        cw_data = hasil_cuaca["weather"]
        cur_data = hasil_cuaca["current"]
        loc_name = hasil_cuaca["location"].split(", ")
        loc_name = ", ".join(loc_name[:2])
        embed = discord.Embed(color=0xEC6E4C)
        embed.set_thumbnail(url=cw_data["icon"])
        if cur_data:
            description = cw_data["emoji"]
            if description:
                description += " "
            description += cur_data["temp"]
            description += f" (Terasa {cur_data['feels_like']})\n"
            description += f"`({cw_data['description']})`\n"

            if "sstime" in cur_data:
                cw_sstime = cur_data["sstime"]
                description += f"☀️ {cw_sstime['sunrise']} | 🌑 {cw_sstime['sunset']}\n"
            if "uv" in cur_data:
                description += f"🔥 {cur_data['uv']}\n"
            if "clouds" in cur_data:
                description += f"☁️ {cur_data['clouds']}\n"
            description += f"💦 {cur_data['humidity']}\n"
            if "rain" in cur_data:
                description += f"☔ {cur_data['rain']['precipitation']}\n"
            description += f"💨 {cur_data['wind']['speed']} "
            description += f"({cur_data['wind']['deg']})\n"
            description += f"**Tekanan**: {cur_data['pressure']}"

        if description:
            embed.description = description

        self.logger.info(f"{lokasi}: Processing daily data...")
        for daily_data in hasil_cuaca["daily"]:
            ld_wd = daily_data["weather"]
            judul_teks = ld_wd["emoji"]
            if judul_teks:
                judul_teks += " "
            judul_teks += daily_data["date_name"]
            temp_dd = daily_data["temp"]
            teks_data = f"`({ld_wd['description']})`"
            teks_data = f"**Tertinggi**: {temp_dd['high']}\n"
            teks_data += f"**Terendah**: {temp_dd['low']}\n"
            if "uv" in daily_data:
                teks_data += f"🔥 {daily_data['uv']}\n"
            if "clouds" in daily_data:
                teks_data += f"☁️ {daily_data['clouds']}\n"
            teks_data += f"💦 {daily_data['humidity']}\n"
            if "rain" in daily_data:
                teks_data += f"☔ {daily_data['rain']['precipitation']}\n"
            teks_data += f"**Tekanan**: {daily_data['pressure']}"
            embed.add_field(name=judul_teks, value=teks_data, inline=True)

        embed.add_field(
            name="Note",
            value="🔥 `Indeks UV`\n"
            "☁️ `Curah Awan`\n"
            "💦 `Kelembapan`\n"
            "☀️ `Terbit`\n"
            "🌑 `Tenggelam`\n"
            "☔ `Presipitasi Hujan`\n"
            "💨 `Arah angin/Kecepatan angin`",
            inline=False,
        )

        coords = hasil_cuaca["coords"]
        embed.set_footer(
            text=f"{coords['lat']}, {coords['lon']} " "| Diprakasai oleh OpenWeatherMap & OpenCage Geocoder",
            icon_url="https://openweathermap.org/themes/openweathermap/assets/vendor/owm/img/icons/logo_60x60.png",  # noqa: E501
        )

        self.logger.info(f"{lokasi}: Sending results...")
        await ctx.send(content=f"Cuaca untuk **{loc_name}**", embed=embed)


def setup(bot: naoTimesBot):
    wlogger.debug("adding cogs...")
    bot.add_cog(CuacaDunia(bot))
