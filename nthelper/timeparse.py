"""
This is a custom time parsing that use a format like: 3d50m / 3h / 30 seconds / etc.
Created since I need a custom one for everything that use this kinda thing.

This module will convert a string of text into `:cls:`datetime.datetime format

---

MIT License

Copyright (c) 2019-2021 Aiman Maharana

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

import schema as sc
from datetime import datetime, timedelta
from typing import Dict, List, Union

TimeSets = List[Dict[str, Union[str, int]]]

TimeStringSchema = sc.Schema(
    [
        {
            "t": sc.Or(int, float),
            "s": sc.And(str, sc.Use(str.lower), lambda s: s in ("ms", "s", "m", "h", "w", "d", "mo", "y")),
        }
    ]
)

_NAME_MAPS = {
    "ms": "Milisecond",
    "s": "Detik",
    "m": "Menit",
    "h": "Jam",
    "w": "Minggu",
    "d": "Hari",
    "mo": "Bulan",
    "y": "Tahun",
}


class TimeStringError(Exception):
    pass


class TimeStringParseError(TimeStringError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(f"Terjadi kesalahan ketika parsing data waktu, {reason}")


class TimeStringValidationError(TimeStringError):
    def __init__(self, extra_data=None):
        main_text = "Gagal memvalidasi data yang diberikan ke TimeString, mohon periksa lagi"
        if isinstance(extra_data, str):
            main_text += f"\nInfo tambahan: {extra_data}"
        super().__init__(main_text)


def normalize_suffix(suffix: str) -> Union[str, None]:
    if suffix in ["s", "sec", "secs", "second", "seconds", "detik"]:
        return "s"
    if suffix in [
        "ms",
        "mil",
        "mill",
        "millis",
        "milli",
        "msec",
        "msecs",
        "milisec",
        "miliseconds",
        "milisecond",
    ]:
        return "ms"
    if suffix in ["m", "min", "mins", "minute", "minutes", "menit"]:
        return "m"
    if suffix in ["h", "hr", "hrs", "hour", "hours", "jam", "j"]:
        return "h"
    if suffix in ["d", "day", "days", "hari"]:
        return "d"
    if suffix in ["w", "wk", "week", "weeks", "minggu"]:
        return "w"
    if suffix in ["M", "mo", "month", "months", "b", "bulan"]:
        return "mo"
    if suffix in ["y", "year", "years", "tahun", "t"]:
        return "y"
    return None


class TimeString:
    def __init__(self, timesets: TimeSets) -> None:
        self._data = timesets
        self.__validate()

    def __validate(self):
        if not isinstance(self._data, list):
            raise TimeStringValidationError()
        self.__check_limit(self._data)
        self.__check_dupes(self._data)
        try:
            TimeStringSchema.validate(self._data)
        except sc.SchemaError as se:
            raise TimeStringValidationError(se.code)

    def __repr__(self):
        text_contents = []
        for data in self._data:
            text_contents.append(f"{_NAME_MAPS.get(data['s'])}={data['t']}")
        if text_contents:
            return f"<TimeString {' '.join(text_contents)}>"
        return "<TimeString NoData>"

    @staticmethod
    def __tokenize(text: str) -> TimeSets:
        time_sets = []
        texts: List[str] = list(text)  # Convert to list of string
        current_num = ""
        build_suffix = ""
        current = ""
        for t in texts:
            print(t, current, current_num, build_suffix)
            if t == " " or t == "":
                if build_suffix.rstrip() and current_num.rstrip():
                    suf = normalize_suffix(build_suffix)
                    if suf is not None:
                        nt = {"t": int(current_num, 10), "s": suf}
                        time_sets.append(nt)
                        current_num = ""
                        build_suffix = ""
                continue
            if t.isdigit():
                if current == "s" and build_suffix.rstrip() and current_num.rstrip():
                    suf = normalize_suffix(build_suffix)
                    if suf is not None:
                        nt = {"t": int(current_num, 10), "s": suf}
                        time_sets.append(nt)
                        current_num = ""
                        build_suffix = ""
                current = "t"
                current_num += t
                continue
            else:
                current = "s"
                build_suffix += t

        print(current, current_num, build_suffix)
        if build_suffix.rstrip() and current_num.rstrip():
            suf = normalize_suffix(build_suffix)
            if suf is not None:
                nt = {"t": int(current_num, 10), "s": suf}
                time_sets.append(nt)
        return time_sets

    @staticmethod
    def __check_dupes(time_sets: TimeSets):
        occured = {}
        for time in time_sets:
            if time["s"] not in occured:
                occured[time["s"]] = time["t"]
            else:
                nama = _NAME_MAPS.get(time["s"])
                raise TimeStringParseError(
                    f"Ada duplikat pada {nama}.\nData baru yaitu {time['t']} tetapi ada data "
                    f"lama yaitu {occured[time['s']]}"
                )

    @staticmethod
    def __check_limit(time_sets: TimeSets):
        limits = {
            "ms": 1000,
            "s": 60,
            "m": 60,
            "h": 24,
            "w": -1,
            "d": -1,
            "mo": -1,
            "y": -1,
        }
        for time in time_sets:
            limit = limits.get(time["s"], -1)
            if limit == -1:
                continue
            if time["t"] > limit:
                nama = _NAME_MAPS.get(time["s"])
                raise TimeStringParseError(
                    f"{nama} melebihi batas waktu {limit} {nama} (yang diberikan: {time['t']})"
                )

    @staticmethod
    def __multiplier(t, s):
        if s == "s":
            return t
        if s == "ms":
            return t / 1000
        if s == "m":
            return t * 60
        if s == "h":
            return t * 3600
        if s == "d":
            return t * 3600 * 24
        if s == "w":
            return t * 3600 * 24 * 7
        if s == "mo":
            return t * 3600 * 24 * 30
        if s == "y":
            return t * 3600 * 24 * 365

    @classmethod
    def parse(cls, timestring: str):
        time_data = cls.__tokenize(timestring)
        if len(time_data) < 1:
            raise TimeStringParseError("hasil akhir parsing kosong, walaupun input diberikan.")
        return cls(time_data)

    def timestamp(self) -> int:
        real_seconds = 0
        for data in self._data:
            real_seconds += self.__multiplier(data["t"], data["s"])
        return real_seconds

    def to_datetime(self) -> datetime:
        dt_start = datetime.utcfromtimestamp(0)
        delta = timedelta(seconds=self.timestamp())
        combined = dt_start + delta
        return combined
