import logging
from typing import List, NamedTuple, Optional, Union

import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.utils import complex_walk


def get_uv_index(uvi: int) -> str:
    """
    Get UV index from UV index number.
    """
    if uvi is None:
        return None
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
    """
    Get rain intensity from rain intensity.
    """
    if precipitation is None:
        return None
    if precipitation <= 2.5:
        intensity = "Hujan ringan"
    elif precipitation > 2.5 and precipitation <= 10:
        intensity = "Hujan sedang"
    elif precipitation > 10 and precipitation <= 50:
        intensity = "Hujan lebat"
    elif precipitation > 50:
        intensity = "Hujan deras"
    return intensity


def get_wind_direction(wind_degress: Union[float, int]) -> str:
    """
    Get wind direction from wind degree.
    """
    if wind_degress < 45:
        res = f"↑ {wind_degress}°"
    elif wind_degress >= 45 and wind_degress < 90:
        res = f"↗ {wind_degress}°"
    elif wind_degress >= 90 and wind_degress < 135:
        res = f"→ {wind_degress}°"
    elif wind_degress >= 135 and wind_degress < 180:
        res = f"↘ {wind_degress}°"
    elif wind_degress >= 180 and wind_degress < 225:
        res = f"↓ {wind_degress}°"
    elif wind_degress >= 225 and wind_degress < 270:
        res = f"↙ {wind_degress}°"
    elif wind_degress >= 270 and wind_degress < 315:
        res = f"← {wind_degress}°"
    elif wind_degress >= 315 and wind_degress < 360:
        res = f"↖ {wind_degress}°"
    else:
        res = f"↑ {wind_degress}°"
    return res


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


def translate_weather_info(id: int, fallback: str):
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

    return weather_tls_mappings.get(id, fallback), weather_ids_mappings.get(id, "")


class GeoLat(NamedTuple):
    name: Optional[str]
    lat: Optional[float]
    lon: Optional[float]


class OWMTemperature(NamedTuple):
    real: str
    feels: str


class OWMTemperatureComplex(NamedTuple):
    high: str
    low: str
    day: str
    night: str


class OWMSunTime(NamedTuple):
    sunrise: str
    sunset: str


class OWMWeatherDetail(NamedTuple):
    icon: str
    description: str
    emoji: str


class OWMWind(NamedTuple):
    speed: str
    direction: str


class OWMRain(NamedTuple):
    precipitation: str
    intensity: str


class OWMCurrent(NamedTuple):
    date: str
    temp: OWMTemperature
    pressure: str
    humidity: str
    uv: str = None
    clouds: str = None
    suntime: OWMSunTime = None
    weather: OWMWeatherDetail = None
    rain: OWMRain = None
    wind: OWMWind = None


class OWMDaily(OWMCurrent):
    temp: OWMTemperatureComplex


class OWMResult(NamedTuple):
    geo_info: GeoLat
    url: str
    current: OWMCurrent
    daily: List[OWMDaily] = []


class PeninjauCuacaDunia(commands.Cog):
    OCD_API = "https://api.opencagedata.com/geocode/v1/json"
    OWM_API = "https://api.openweathermap.org/data/2.5/onecall"
    ICON = "https://openweathermap.org/img/wn/{ic}@2x.png"
    LINKY = "https://openweathermap.org/weathermap?lat={lat}&lon={lon}"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Peninjau.CuacaDunia")
        self.conf = bot.config.weather

    async def __fetch_geolat(self, location: str):
        self.logger.info(f"Finding: {location}")
        param = {
            "q": location,
            "key": self.conf.opencage,
        }
        async with self.bot.aiosession.get(self.OCD_API, params=param) as resp:
            result = await resp.json()
            main_res = complex_walk(result, "results")
            if isinstance(main_res, list) and len(main_res) < 1:
                self.logger.warning(f"No result found for: {location}")
                return GeoLat(None, None, None)
            first_instance = main_res[0]
            geometry = first_instance.get("geometry")
        lat, lon = geometry.get("lat"), geometry.get("lng")
        loc_name = first_instance.get("formatted")
        self.logger.info(f"Found: {loc_name} -- {lat} [:] {lon}")
        return GeoLat(loc_name, lat, lon)

    async def __fetch_weather(self, location: str):
        self.logger.info(f"Finding: {location}")
        geo_info = await self.__fetch_geolat(location)
        if geo_info.lat is None:
            return None

        param_req = {
            "lat": geo_info.lat,
            "lon": geo_info.lon,
            "exclude": "minutely,hourly",
            "appid": self.conf.openweather,
            "units": "metric",
            "lang": "id",
        }

        self.logger.info(f"Requesting weather data for {geo_info.lat}, {geo_info.lon}")
        async with self.bot.aiosession.get(self.OWM_API, params=param_req) as resp:
            self.logger.info(f"{location}: Parsing data...")
            weather_res = await resp.json()

        error_code = weather_res.get("cod")
        if error_code is not None:
            if error_code == 401:
                return "API key bot owner belum terautentikasi. Mohon kontak Bot Owner atau tunggu beberapa jam kemudian."  # noqa: E501
            return weather_res.get("message", "Terjadi kesalahan ketika menghubungi API OpenWeather")

        self.logger.info("Parsing current base weather data...")
        tz_offset = weather_res.get("timezone_offset")

        hyper_url = self.LINKY.format(lat=geo_info.lat, lon=geo_info.lon)
        currents: dict = weather_res.get("current")
        current_info = None
        if currents is not None:
            try:
                temperature = OWMTemperature(f"{currents['temp']}°C", f"{currents['feels_like']}°C")
                uv_info = complex_walk(currents, "uvi")
                if uv_info is not None:
                    uv_info = get_uv_index(uv_info)
                cloud_info = complex_walk(currents, "clouds")
                if cloud_info is not None:
                    cloud_info = f"{cloud_info}%"
                pressure = currents.get("pressure")
                if pressure is not None:
                    pressure = f"{pressure}hPa"
                humidity = currents.get("humidity")
                if humidity is not None:
                    humidity = f"{humidity}%"

                sunrise = currents.get("sunrise")
                sunset = currents.get("sunset")
                if sunrise is not None:
                    sunrise = arrow.get(currents["sunrise"]).shift(seconds=tz_offset).format("hh:mm [AM]")
                if sunset is not None:
                    sunset = arrow.get(currents["sunset"]).shift(seconds=tz_offset).format("hh:mm [PM]")
                suntime_info = OWMSunTime(sunrise, sunset)

                current_weather = complex_walk(currents, "weather.0")
                cw_desc = current_weather["description"].capitalize()
                cw_icon = self.ICON.format(ic=current_weather["icon"])
                cw_desc, cw_emoji = translate_weather_info(current_weather["id"], cw_desc)
                cw_current = OWMWeatherDetail(
                    cw_icon,
                    cw_desc,
                    cw_emoji,
                )

                wind_speed = f"{currents['wind_speed']}m/s"
                wind_direction = get_wind_direction(currents["wind_deg"])
                wind_info = OWMWind(wind_speed, wind_direction)

                rain_info = None
                onehour_rain = complex_walk(currents, "rain.1h")
                if onehour_rain is not None:
                    rain_precip = f"{onehour_rain}mm"
                    rain_intensity = get_rain_intensity(onehour_rain)
                    rain_info = OWMRain(rain_precip, rain_intensity)

                current_info = OWMCurrent(
                    "Current",
                    temperature,
                    pressure,
                    humidity,
                    uv_info,
                    cloud_info,
                    suntime_info,
                    cw_current,
                    rain_info,
                    wind_info,
                )
            except Exception:
                self.logger.exception("Error parsing current weather data")

        last_7days_data = weather_res["daily"][-6:]

        self.logger.info("Parsing daily data...")
        last_7days_compiled: List[OWMDaily] = []
        for daily_data in last_7days_data:
            datedata = arrow.get(daily_data["dt"]).shift(seconds=tz_offset)
            temp_data = daily_data.get("temp")
            date_name = translate_day(datedata.format("dddd", "id"))

            temp_complex = OWMTemperatureComplex(
                f"{temp_data['max']}°C",
                f"{temp_data['min']}°C",
                f"{temp_data['day']}°C",
                f"{temp_data['night']}°C",
            )

            dd_uv_index = complex_walk(daily_data, "uvi")
            if dd_uv_index is not None:
                dd_uv_index = get_uv_index(dd_uv_index)

            dd_pressure = f"{daily_data['pressure']}hPa"
            dd_humidity = f"{daily_data['humidity']}%"

            dd_clouds = complex_walk(daily_data, "clouds")
            if dd_clouds is not None:
                dd_clouds = f"{dd_clouds}%"

            dd_rain = None
            dd_rain_info = complex_walk(daily_data, "rain")
            if dd_rain_info is not None:
                dd_rain_precip = f"{dd_rain_info}mm"
                dd_rain_intensity = get_rain_intensity(dd_rain_info)
                dd_rain = OWMRain(dd_rain_precip, dd_rain_intensity)
            dd_weather = complex_walk(currents, "weather.0")
            ddw_desc = dd_weather["description"].capitalize()
            ddw_icon = self.ICON.format(ic=dd_weather["icon"])
            ddw_desc, ddw_emoji = translate_weather_info(dd_weather["id"], ddw_desc)
            ddw_current = OWMWeatherDetail(
                ddw_icon,
                ddw_desc,
                ddw_emoji,
            )

            daily_parsed = OWMDaily(
                date_name,
                temp_complex,
                dd_pressure,
                dd_humidity,
                dd_uv_index,
                dd_clouds,
                None,
                ddw_current,
                dd_rain,
                None,
            )
            last_7days_compiled.append(daily_parsed)

        weather_info = OWMResult(geo_info, hyper_url, current_info, last_7days_compiled)
        return weather_info

    def _create_embed(self, result: OWMResult):
        location = result.geo_info.name.split(", ")
        location = ", ".join(location[:2])
        embed = discord.Embed(color=0xEC6E4C)
        embed.set_thumbnail(url=result.current.weather.icon)

        description = []
        emoji_base = result.current.weather.emoji
        if emoji_base:
            emoji_base += " "
        emoji_base += result.current.temp.real
        emoji_base += f" (Terasa {result.current.temp.feels})"
        description.append(emoji_base)
        description.append(f"`({result.current.weather.description})`")

        if result.current.suntime:
            suntime = result.current.suntime
            description.append(f"☀️ {suntime.sunrise} | 🌑 {suntime.sunset}")
        if result.current.uv:
            description.append(f"🔥 {result.current.uv}")
        if result.current.clouds:
            description.append(f"☁️ {result.current.clouds}")
        description.append(f"💧 {result.current.humidity}")
        if result.current.rain:
            description.append(f"☔ {result.current.rain.precipitation}")
        wind_info = f"🎐 {result.current.wind.speed} ({result.current.wind.direction})"
        description.append(wind_info)
        description.append(f"**Tekanan**: {result.current.pressure}")

        embed.description = "\n".join(description)

        self.logger.info(f"{location}: processing daily data...")
        for daily in result.daily:
            weather = daily.weather
            title_teks = weather.emoji
            if title_teks:
                title_teks += " "
            title_teks += daily.date
            temp_dd = daily.temp

            teks_data = []
            teks_data.append(f"`({weather.description})`")
            teks_data.append(f"**Tertinggi**: {temp_dd.high}")
            teks_data.append(f"**Terendah**: {temp_dd.low}")
            if daily.uv:
                teks_data.append(f"🔥 {daily.uv}")
            if daily.clouds:
                teks_data.append(f"☁️ {daily.clouds}")
            teks_data.append(f"💧 {daily.humidity}")
            if daily.rain:
                teks_data.append(f"☔ {daily.rain.precipitation}")
            teks_data.append(f"**Tekanan**: {daily.pressure}")
            embed.add_field(name=title_teks, value="\n".join(teks_data), inline=True)

        embed.add_field(
            name="Note",
            value="🔥 `Indeks UV`\n"
            "☁️ `Curah Awan`\n"
            "💧 `Kelembapan`\n"
            "☀️ `Terbit`\n"
            "🌑 `Tenggelam`\n"
            "☔ `Presipitasi Hujan`\n"
            "🎐 `Arah angin/Kecepatan angin`",
            inline=False,
        )

        geo_lat = result.geo_info
        embed.set_footer(
            text=f"{geo_lat.lat}, {geo_lat.lon} | Diprakasai oleh OpenWeatherMap & OpenCage Geocoder",
            icon_url="https://openweathermap.org/themes/openweathermap/assets/vendor/owm/img/icons/logo_60x60.png",  # noqa: E501
        )
        return embed, location

    @commands.command(name="cuaca", aliases=["c", "w", "weather"])
    async def _peninjau_cuaca_cmd(self, ctx: naoTimesContext, *, lokasi: str):
        self.logger.info("Requested !cuaca command")
        if self.conf is None:
            return await ctx.send("Owner Bot tidak menyiapkan API key untuk perintah ini!")
        if not self.conf.opencage:
            return await ctx.send("Owner Bot tidak memberikan API untuk OpenCage (Digunakan untuk lokasi)")
        if not self.conf.openweather:
            return await ctx.send("Owner Bot tidak memberikan API key untuk OpenWeater API (API utama)")

        hasil_cuaca = await self.__fetch_weather(lokasi)
        if hasil_cuaca is None:
            return await ctx.send("Gagal mengambil latitude/longtitude lokasi anda!")
        if isinstance(hasil_cuaca, str):
            self.logger.error(hasil_cuaca)
            return await ctx.send(hasil_cuaca)
        if not hasil_cuaca:
            return await ctx.send("Tidak dapat menemukan lokasi tersebut!")

        self.logger.info(f"{lokasi}: memproses hasil cuaca...")

        embed, location = self._create_embed(hasil_cuaca)
        await ctx.send(content=f"Cuaca untuk **{location}**", embed=embed)

    @app_commands.command(name="cuaca")
    @app_commands.describe(lokasi="Lokasi yang ingin anda lihat informasi cuacanya")
    async def _peninjau_cuaca_slashcmd(self, inter: discord.Interaction, lokasi: str):
        """Lihat informasi cuaca sebuah lokasi"""
        ctx = await self.bot.get_context(inter)
        self.logger.info("Requested /cuaca command")
        if self.conf is None:
            return await ctx.send("Owner Bot tidak menyiapkan API key untuk perintah ini!")
        if not self.conf.opencage:
            return await ctx.send("Owner Bot tidak memberikan API untuk OpenCage (Digunakan untuk lokasi)")
        if not self.conf.openweather:
            return await ctx.send("Owner Bot tidak memberikan API key untuk OpenWeater API (API utama)")

        await ctx.defer()
        hasil_cuaca = await self.__fetch_weather(lokasi)
        if hasil_cuaca is None:
            return await ctx.send("Gagal mengambil latitude/longtitude lokasi anda!")
        if isinstance(hasil_cuaca, str):
            self.logger.error(hasil_cuaca)
            return await ctx.send(hasil_cuaca)
        if not hasil_cuaca:
            return await ctx.send("Tidak dapat menemukan lokasi tersebut!")

        self.logger.info(f"{lokasi}: memproses hasil cuaca...")

        embed, location = self._create_embed(hasil_cuaca)
        await ctx.send(content=f"Cuaca untuk **{location}**", embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(PeninjauCuacaDunia(bot))
