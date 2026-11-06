import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TypeGuard

import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.utils import WalkValue, complex_walk


def get_uv_index(uvi: int | float, t: Callable[..., str]) -> str:
    """
    Get UV index from UV index number.
    """
    uvi_index = str(uvi)
    if uvi < 3:
        uvi_index += f" ({t('cuaca.uv.low')})"
    elif uvi >= 3 and uvi < 6:
        uvi_index += f" ({t('cuaca.uv.moderate')})"
    elif uvi >= 6 and uvi < 8:
        uvi_index += f" ({t('cuaca.uv.high')})"
    elif uvi >= 8 and uvi < 11:
        uvi_index += f" ({t('cuaca.uv.very_high')})"
    elif uvi >= 11:
        uvi_index += f" ({t('cuaca.uv.extreme')})"
    return uvi_index


def get_rain_intensity(precipitation: float, t: Callable[..., str]) -> str:
    """
    Get rain intensity from rain intensity.
    """
    intensity = t("cuaca.rain.heavy")
    if precipitation <= 2.5:
        intensity = t("cuaca.rain.light")
    elif precipitation > 2.5 and precipitation <= 10:
        intensity = t("cuaca.rain.moderate")
    elif precipitation > 10 and precipitation <= 50:
        intensity = t("cuaca.rain.heavy")
    elif precipitation > 50:
        intensity = t("cuaca.rain.heavy")
    return intensity


def _is_walk_value(value: object) -> TypeGuard[WalkValue]:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list | tuple):
        return all(_is_walk_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, (str, int)) and _is_walk_value(item) for key, item in value.items())
    return False


def _mapping(value: object) -> dict[str | int, WalkValue] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str | int, WalkValue] = {}
    for key, item in value.items():
        if not isinstance(key, (str, int)) or not _is_walk_value(item):
            return None
        result[key] = item
    return result


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def get_wind_direction(wind_degress: float) -> str:
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


def translate_weather_info(id: int, fallback: str, t: Callable[..., str]):
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
        200: "cuaca.weather.thunderstorm_light_rain",
        201: "cuaca.weather.thunderstorm_rain",
        202: "cuaca.weather.thunderstorm_heavy_rain",
        210: "cuaca.weather.light_thunderstorm",
        211: "cuaca.weather.thunderstorm",
        212: "cuaca.weather.heavy_thunderstorm",
        221: "cuaca.weather.ragged_thunderstorm",
        230: "cuaca.weather.thunderstorm_light_drizzle",
        231: "cuaca.weather.thunderstorm_drizzle",
        232: "cuaca.weather.thunderstorm_heavy_drizzle",
        300: "cuaca.weather.light_drizzle",
        301: "cuaca.weather.drizzle",
        302: "cuaca.weather.heavy_drizzle",
        310: "cuaca.weather.light_drizzle_rain",
        311: "cuaca.weather.drizzle_rain",
        312: "cuaca.weather.heavy_drizzle_rain",
        313: "cuaca.weather.shower_rain_drizzle",
        314: "cuaca.weather.heavy_shower_rain_drizzle",
        321: "cuaca.weather.shower_drizzle",
        500: "cuaca.weather.light_rain",
        501: "cuaca.weather.moderate_rain",
        502: "cuaca.weather.heavy_rain",
        503: "cuaca.weather.very_heavy_rain",
        504: "cuaca.weather.extreme_rain",
        511: "cuaca.weather.freezing_rain",
        520: "cuaca.weather.light_shower_rain",
        521: "cuaca.weather.shower_rain",
        522: "cuaca.weather.heavy_shower_rain",
        531: "cuaca.weather.ragged_shower_rain",
        600: "cuaca.weather.light_snow",
        601: "cuaca.weather.snow",
        602: "cuaca.weather.heavy_snow",
        611: "cuaca.weather.sleet",
        612: "cuaca.weather.light_shower_sleet",
        613: "cuaca.weather.shower_sleet",
        615: "cuaca.weather.light_rain_snow",
        616: "cuaca.weather.rain_snow",
        620: "cuaca.weather.light_shower_snow",
        621: "cuaca.weather.shower_snow",
        622: "cuaca.weather.heavy_shower_snow",
        701: "cuaca.weather.mist",
        711: "cuaca.weather.smoke",
        721: "cuaca.weather.haze",
        731: "cuaca.weather.dust_whirls",
        741: "cuaca.weather.fog",
        751: "cuaca.weather.sand_dust",
        761: "cuaca.weather.dust",
        762: "cuaca.weather.volcanic_ash",
        771: "cuaca.weather.squalls",
        781: "cuaca.weather.tornado",
        800: "cuaca.weather.clear_sky",
        801: "cuaca.weather.few_clouds",
        802: "cuaca.weather.scattered_clouds",
        803: "cuaca.weather.broken_clouds",
        804: "cuaca.weather.overcast_clouds",
    }

    key = weather_tls_mappings.get(id)
    if key is None:
        return fallback, weather_ids_mappings.get(id, "")
    return t(key), weather_ids_mappings.get(id, "")


@dataclass
class GeoLat:
    name: str | None
    lat: float | None
    lon: float | None


@dataclass
class OWMTemperature:
    real: str
    feels: str


@dataclass
class OWMTemperatureComplex:
    high: str
    low: str
    day: str
    night: str


@dataclass
class OWMSunTime:
    sunrise: str
    sunset: str


@dataclass
class OWMWeatherDetail:
    icon: str
    description: str
    emoji: str


@dataclass
class OWMWind:
    speed: str
    direction: str


@dataclass
class OWMRain:
    precipitation: str
    intensity: str


@dataclass
class OWMCurrent:
    date: str
    temp: OWMTemperature
    pressure: str
    humidity: str
    uv: str | None = None
    clouds: str | None = None
    suntime: OWMSunTime | None = None
    weather: OWMWeatherDetail | None = None
    rain: OWMRain | None = None
    wind: OWMWind | None = None


@dataclass
class OWMDaily:
    date: str
    temp: OWMTemperatureComplex
    pressure: str
    humidity: str
    uv: str | None = None
    clouds: str | None = None
    suntime: OWMSunTime | None = None
    weather: OWMWeatherDetail | None = None
    rain: OWMRain | None = None
    wind: OWMWind | None = None


@dataclass
class OWMResult:
    geo_info: GeoLat
    url: str
    current: OWMCurrent
    daily: list[OWMDaily] = field(default_factory=list)


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
        config = self.conf
        if config is None or not config.opencage:
            return GeoLat(None, None, None)
        if self.bot.aiosession is None:
            return GeoLat(None, None, None)
        param = {
            "q": location,
            "key": config.opencage,
        }
        async with self.bot.aiosession.get(self.OCD_API, params=param) as resp:
            raw_result: object = await resp.json()
        result = _mapping(raw_result)
        if result is None:
            return GeoLat(None, None, None)
        main_res = complex_walk(result, "results")
        if not isinstance(main_res, list) or not main_res:
            self.logger.warning(f"No result found for: {location}")
            return GeoLat(None, None, None)
        first_instance = _mapping(main_res[0])
        if first_instance is None:
            return GeoLat(None, None, None)
        geometry = _mapping(first_instance.get("geometry"))
        if geometry is None:
            return GeoLat(None, None, None)
        lat, lon = _number(geometry.get("lat")), _number(geometry.get("lng"))
        if lat is None or lon is None:
            return GeoLat(None, None, None)
        loc_name = _text(first_instance.get("formatted"), location)
        self.logger.info(f"Found: {loc_name} -- {lat} [:] {lon}")
        return GeoLat(loc_name, lat, lon)

    async def __fetch_weather(self, location: str, t: Callable[..., str], locale: str) -> OWMResult | str | None:
        self.logger.info(f"Finding: {location}")
        config = self.conf
        if config is None or not config.openweather:
            return t("cuaca.error.no_api_key")
        if self.bot.aiosession is None:
            return t("cuaca.error.http_unavailable")
        geo_info = await self.__fetch_geolat(location)
        if geo_info.lat is None or geo_info.lon is None:
            return None

        param_req = {
            "lat": geo_info.lat,
            "lon": geo_info.lon,
            "exclude": "minutely,hourly",
            "appid": config.openweather,
            "units": "metric",
            "lang": locale,
        }

        self.logger.info(f"Requesting weather data for {geo_info.lat}, {geo_info.lon}")
        async with self.bot.aiosession.get(self.OWM_API, params=param_req) as resp:
            self.logger.info(f"{location}: Parsing data...")
            raw_weather: object = await resp.json()

        weather_res = _mapping(raw_weather)
        if weather_res is None:
            return t("cuaca.error.invalid_response")

        error_code = weather_res.get("cod")
        if error_code is not None:
            if error_code == 401:
                return t("cuaca.error.unauthorized")
            return _text(weather_res.get("message"), t("cuaca.error.api_error"))

        self.logger.info("Parsing current base weather data...")
        tz_offset = _number(weather_res.get("timezone_offset")) or 0.0

        hyper_url = self.LINKY.format(lat=geo_info.lat, lon=geo_info.lon)
        currents = _mapping(weather_res.get("current"))
        current_info = None
        if currents is not None:
            try:
                temp_value = _number(currents.get("temp"))
                feels_value = _number(currents.get("feels_like"))
                if temp_value is None or feels_value is None:
                    raise ValueError("Current temperature is missing")
                temperature = OWMTemperature(f"{temp_value}°C", f"{feels_value}°C")
                uv_value = _number(complex_walk(currents, "uvi"))
                uv_info = get_uv_index(uv_value, t) if uv_value is not None else None
                cloud_value = _number(complex_walk(currents, "clouds"))
                cloud_info = f"{cloud_value}%" if cloud_value is not None else None
                pressure_value = _number(currents.get("pressure"))
                pressure = f"{pressure_value}hPa" if pressure_value is not None else "N/A"
                humidity_value = _number(currents.get("humidity"))
                humidity = f"{humidity_value}%" if humidity_value is not None else "N/A"

                sunrise_value = _number(currents.get("sunrise"))
                sunset_value = _number(currents.get("sunset"))
                suntime_info = None
                if sunrise_value is not None and sunset_value is not None:
                    sunrise = arrow.get(sunrise_value).shift(seconds=tz_offset).format("hh:mm [AM]")
                    sunset = arrow.get(sunset_value).shift(seconds=tz_offset).format("hh:mm [PM]")
                    suntime_info = OWMSunTime(sunrise, sunset)

                current_weather = _mapping(complex_walk(currents, "weather.0"))
                if current_weather is None:
                    raise ValueError("Current weather details are missing")
                cw_desc = _text(current_weather.get("description"), t("cuaca.error.unknown_weather")).capitalize()
                cw_icon = self.ICON.format(ic=_text(current_weather.get("icon"), "01d"))
                weather_id = _number(current_weather.get("id")) or 0
                cw_desc, cw_emoji = translate_weather_info(int(weather_id), cw_desc, t)
                cw_current = OWMWeatherDetail(
                    cw_icon,
                    cw_desc,
                    cw_emoji,
                )

                wind_speed_value = _number(currents.get("wind_speed"))
                wind_direction_value = _number(currents.get("wind_deg"))
                wind_info = None
                if wind_speed_value is not None and wind_direction_value is not None:
                    wind_speed = f"{wind_speed_value}m/s"
                    wind_direction = get_wind_direction(wind_direction_value)
                    wind_info = OWMWind(wind_speed, wind_direction)

                rain_info = None
                onehour_rain = _number(complex_walk(currents, "rain.1h"))
                if onehour_rain is not None:
                    rain_precip = f"{onehour_rain}mm"
                    rain_intensity = get_rain_intensity(onehour_rain, t)
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

        if current_info is None:
            return t("cuaca.error.current_invalid")

        daily_response = weather_res.get("daily")
        last_7days_data = daily_response[-6:] if isinstance(daily_response, list) else []

        self.logger.info("Parsing daily data...")
        last_7days_compiled: list[OWMDaily] = []
        for raw_daily_data in last_7days_data:
            daily_data = _mapping(raw_daily_data)
            if daily_data is None:
                continue
            timestamp = _number(daily_data.get("dt"))
            temp_data = _mapping(daily_data.get("temp"))
            if timestamp is None or temp_data is None:
                continue
            datedata = arrow.get(timestamp).shift(seconds=tz_offset)
            date_name = datedata.format("dddd", locale)

            temp_complex = OWMTemperatureComplex(
                f"{_text(temp_data.get('max'), 'N/A')}°C",
                f"{_text(temp_data.get('min'), 'N/A')}°C",
                f"{_text(temp_data.get('day'), 'N/A')}°C",
                f"{_text(temp_data.get('night'), 'N/A')}°C",
            )

            dd_uv_value = _number(complex_walk(daily_data, "uvi"))
            dd_uv_index = get_uv_index(dd_uv_value, t) if dd_uv_value is not None else None

            pressure_value = _number(daily_data.get("pressure"))
            dd_pressure = f"{pressure_value}hPa" if pressure_value is not None else "N/A"
            humidity_value = _number(daily_data.get("humidity"))
            dd_humidity = f"{humidity_value}%" if humidity_value is not None else "N/A"

            cloud_value = _number(complex_walk(daily_data, "clouds"))
            dd_clouds = f"{cloud_value}%" if cloud_value is not None else None

            dd_rain = None
            dd_rain_info = _number(complex_walk(daily_data, "rain"))
            if dd_rain_info is not None:
                dd_rain_precip = f"{dd_rain_info}mm"
                dd_rain_intensity = get_rain_intensity(dd_rain_info, t)
                dd_rain = OWMRain(dd_rain_precip, dd_rain_intensity)
            dd_weather = _mapping(complex_walk(daily_data, "weather.0"))
            if dd_weather is None:
                continue
            ddw_desc = _text(dd_weather.get("description"), t("cuaca.error.unknown_weather")).capitalize()
            ddw_icon = self.ICON.format(ic=_text(dd_weather.get("icon"), "01d"))
            daily_weather_id = _number(dd_weather.get("id")) or 0
            ddw_desc, ddw_emoji = translate_weather_info(int(daily_weather_id), ddw_desc, t)
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

    def _create_embed(self, result: OWMResult, t: Callable[..., str]):
        location = (result.geo_info.name or t("cuaca.error.unknown_location")).split(", ")
        location = ", ".join(location[:2])
        embed = discord.Embed(color=0xEC6E4C)
        current_weather = result.current.weather or OWMWeatherDetail(
            self.ICON.format(ic="01d"), t("cuaca.error.unknown_weather"), ""
        )
        embed.set_thumbnail(url=current_weather.icon)

        description = []
        emoji_base = current_weather.emoji
        if emoji_base:
            emoji_base += " "
        emoji_base += result.current.temp.real
        emoji_base += t("cuaca.embed.feels", feels=result.current.temp.feels)
        description.append(emoji_base)
        description.append(f"`({current_weather.description})`")

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
        if result.current.wind is not None:
            wind_info = f"🎐 {result.current.wind.speed} ({result.current.wind.direction})"
            description.append(wind_info)
        description.append(t("cuaca.embed.pressure", pressure=result.current.pressure))

        embed.description = "\n".join(description)

        self.logger.info(f"{location}: processing daily data...")
        for daily in result.daily:
            weather = daily.weather or OWMWeatherDetail(
                self.ICON.format(ic="01d"), t("cuaca.error.unknown_weather"), ""
            )
            title_teks = weather.emoji
            if title_teks:
                title_teks += " "
            title_teks += daily.date
            temp_dd = daily.temp

            teks_data = []
            teks_data.append(f"`({weather.description})`")
            teks_data.append(t("cuaca.embed.high", value=temp_dd.high))
            teks_data.append(t("cuaca.embed.low", value=temp_dd.low))
            if daily.uv:
                teks_data.append(f"🔥 {daily.uv}")
            if daily.clouds:
                teks_data.append(f"☁️ {daily.clouds}")
            teks_data.append(f"💧 {daily.humidity}")
            if daily.rain:
                teks_data.append(f"☔ {daily.rain.precipitation}")
            teks_data.append(t("cuaca.embed.pressure", pressure=daily.pressure))
            embed.add_field(name=title_teks, value="\n".join(teks_data), inline=True)

        embed.add_field(
            name=t("cuaca.embed.note_field"),
            value=t("cuaca.embed.note_value"),
            inline=False,
        )

        geo_lat = result.geo_info
        embed.set_footer(
            text=t("cuaca.embed.footer", lat=geo_lat.lat, lon=geo_lat.lon),
            icon_url="https://openweathermap.org/themes/openweathermap/assets/vendor/owm/img/icons/logo_60x60.png",
        )
        return embed, location

    @app_commands.command(
        name="cuaca",
        description=app_commands.locale_str("Lihat informasi cuaca sebuah lokasi", key="peninjau.cuaca.description"),
    )
    @app_commands.describe(
        lokasi=app_commands.locale_str("Lokasi yang ingin anda lihat informasi cuacanya", key="peninjau.cuaca.option")
    )
    async def _peninjau_cuaca_slashcmd(self, inter: discord.Interaction, lokasi: str):
        """Lihat informasi cuaca sebuah lokasi"""
        ctx = await self.bot.get_context(inter)
        self.logger.info("Requested /cuaca command")
        if self.conf is None:
            return await ctx.send(ctx.t("cuaca.error.disabled"))
        if not self.conf.opencage:
            return await ctx.send(ctx.t("cuaca.error.no_opencage"))
        if not self.conf.openweather:
            return await ctx.send(ctx.t("cuaca.error.no_openweather"))

        await ctx.defer()
        hasil_cuaca = await self.__fetch_weather(lokasi, ctx.t, ctx.locale)
        if hasil_cuaca is None:
            return await ctx.send(ctx.t("cuaca.error.geo_failed"))
        if isinstance(hasil_cuaca, str):
            self.logger.error(hasil_cuaca)
            return await ctx.send(hasil_cuaca)
        if not hasil_cuaca:
            return await ctx.send(ctx.t("cuaca.error.location_not_found"))

        self.logger.info(f"{lokasi}: memproses hasil cuaca...")

        embed, location = self._create_embed(hasil_cuaca, ctx.t)
        await ctx.send(content=ctx.t("cuaca.header", location=location), embed=embed)


async def setup(bot: naoTimesBot):
    await bot.add_cog(PeninjauCuacaDunia(bot))
