"""
This is a custom time parsing that use a format like: 3d50m / 3h / 30 seconds / etc.
Created since I need a custom one for everything that use this kinda thing.

This module will convert a string of text into `:cls:`arrow.Arrow format

---

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

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, NamedTuple, Union

import arrow

__all__ = ("TimeString", "TimeStringError", "TimeStringParseError", "TimeStringValidationError")


_SUFFIXES = ["ms", "s", "m", "h", "w", "d", "mo", "y"]
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


class TimeTuple(NamedTuple):
    t: Union[int, float]
    s: str


TimeSets = List[TimeTuple]


class TimeStringError(Exception):
    pass


class TimeStringParseError(TimeStringError):
    def __init__(self, reason: str):
        self.reason: str = reason
        super().__init__(f"Terjadi kesalahan ketika parsing data waktu, {reason}")


class TimeStringValidationError(TimeStringError):
    def __init__(self, extra_data=None):
        main_text = "Gagal memvalidasi data yang diberikan ke TimeString, mohon periksa lagi"
        if isinstance(extra_data, str):
            main_text += f"\nInfo tambahan: {extra_data}"
        super().__init__(main_text)


def normalize_suffix(suffix: str) -> Union[str, None]:
    if suffix in ["", " "]:
        # Default to seconds
        return "s"
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
        self._data: TimeSets = timesets
        self.__validate()

    def __validate(self):
        if not isinstance(self._data, list):
            raise TimeStringValidationError()
        self._data = self.__concat_dupes(self._data)
        for data in self._data:
            if not isinstance(data.t, (int, float)):
                raise TimeStringValidationError(f"{data.t} bukanlah angka!")
            if not isinstance(data.s, str):
                raise TimeStringValidationError(f"{data.s} bukanlah string!")
            if data.s not in _SUFFIXES:
                raise TimeStringValidationError(f"{data.s} bukanlah suffix yang diperlukan!")

    def __repr__(self):
        text_contents = []
        for data in self._data:
            text_contents.append(f"{_NAME_MAPS.get(data.s)}={data.t}")
        if text_contents:
            return f"<TimeString {' '.join(text_contents)}>"
        return "<TimeString NoData>"

    def __str__(self):
        return self.to_string()

    def __internal_addition(self, other: Union[TimeTuple, TimeSets]) -> TimeSets:
        if not isinstance(other, list) and not isinstance(other, TimeString):
            return TypeError("Not a correct type, must be either TimeTuple or List[TimeTuple].")
        current_data = self._data[:]
        if isinstance(other, TimeTuple):
            other = [other]
        valid_list = []
        for da in other:
            if isinstance(da, TimeTuple):
                valid_list.append(da)
        if len(valid_list) < 1:
            return ValueError("The list given doesn't contains any TimeTuple.")
        current_data.extend(valid_list)
        return self.__concat_dupes(current_data)

    def __add__(self, other: Union[TimeTuple, TimeSets]) -> TimeString:
        return TimeString(self.__internal_addition(other))

    def __iadd__(self, other: Union[TimeTuple, TimeSets]) -> TimeString:
        self._data = self.__internal_addition(other)
        return self

    def __internal_subtract(self, other: Union[TimeTuple, TimeSets]) -> TimeSets:
        if not isinstance(other, list) and not isinstance(other, TimeString):
            return TypeError("Not a correct type, must be either TimeTuple or List[TimeTuple].")
        current_data = self._data[:]
        occured: Dict[str, Union[int, float]] = {}
        for time in current_data:
            if time.s not in occured:
                occured[time.s] = time.t
            else:
                occured[time.s] += time.t

        if isinstance(other, TimeTuple):
            if other.s in occured:
                occured[other.s] -= other.t
                if occured[other.s] < 0:
                    occured[other.s] = 0
        elif isinstance(other, list):
            valid_list: TimeSets = []
            for da in other:
                if isinstance(da, TimeTuple):
                    valid_list.append(da)
            if len(valid_list) < 1:
                return ValueError("The list given doesn't contains any TimeTuple.")
            for da in valid_list:
                if da.s in occured:
                    occured[da.s] -= da.t
                    if occured[da.s] < 0:
                        occured[da.s] = 0
        concatted = []
        for suf, am in occured.items():
            concatted.append(TimeTuple(am, suf))
        return concatted

    def __sub__(self, other: Union[TimeTuple, TimeSets]) -> "TimeString":
        return TimeString(self.__internal_subtract(other))

    def __isub__(self, other: Union[TimeTuple, TimeSets]) -> "TimeString":
        self._data = self.__internal_subtract(other)
        return self

    def __eq__(self, other: "TimeString") -> bool:
        if not isinstance(other, TimeString):
            return False
        return self.timestamp() == other.timestamp()

    def __ne__(self, other: "TimeString") -> bool:
        if not isinstance(other, TimeString):
            return True
        return self.timestamp() != other.timestamp()

    def __lt__(self, other: "TimeString") -> bool:
        if not isinstance(other, TimeString):
            return False
        return self.timestamp() < other.timestamp()

    def __le__(self, other: "TimeString") -> bool:
        if not isinstance(other, TimeString):
            return False
        return self.timestamp() <= other.timestamp()

    def __gt__(self, other: "TimeString") -> bool:
        if not isinstance(other, TimeString):
            return False
        return self.timestamp() > other.timestamp()

    def __ge__(self, other: "TimeString") -> bool:
        if not isinstance(other, TimeString):
            return False
        return self.timestamp() >= other.timestamp()

    @staticmethod
    def __tokenize(text: str) -> List[TimeTuple]:
        def _parse_num(data: str):
            if "." in data:
                return float(data)
            return int(data, 10)

        time_sets = []
        texts: List[str] = list(text)  # Convert to list of string
        current_num = ""
        build_suffix = ""
        current = ""
        for t in texts:
            if t in [" ", ""]:
                if build_suffix.rstrip() and current_num.rstrip():
                    suf = normalize_suffix(build_suffix)
                    if suf is not None:
                        time_sets.append(TimeTuple(_parse_num(current_num), suf))
                        current_num = ""
                        build_suffix = ""
                continue
            if t.isdigit() or t in [".", ","]:
                if t == ",":
                    t = "."
                if current == "s" and build_suffix.rstrip() and current_num.rstrip():
                    suf = normalize_suffix(build_suffix)
                    if suf is not None:
                        time_sets.append(TimeTuple(_parse_num(current_num), suf))
                        current_num = ""
                        build_suffix = ""
                current = "t"
                current_num += t
                continue
            else:
                current = "s"
                build_suffix += t

        if current_num.rstrip():
            suf = normalize_suffix(build_suffix)
            if suf is not None:
                time_sets.append(TimeTuple(_parse_num(current_num), suf))
        return time_sets

    @staticmethod
    def __concat_dupes(time_sets: TimeSets) -> TimeSets:
        occured: Dict[str, Union[int, float]] = {}
        for time in time_sets:
            if time.s not in occured:
                occured[time.s] = time.t
            else:
                occured[time.s] += time.t
        concatted = []
        for suf, am in occured.items():
            concatted.append(TimeTuple(am, suf))
        return concatted

    @staticmethod
    def __multiplier(t: Union[int, float], s: str):
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

    @classmethod
    def from_seconds(cls, seconds: Union[int, float]):
        return cls([TimeTuple(seconds, "s")])

    def timestamp(self) -> int:
        real_seconds = 0
        for data in self._data:
            real_seconds += self.__multiplier(data.t, data.s)
        return real_seconds

    def to_datetime(self) -> arrow.Arrow:
        dt_start = arrow.get(0)
        return dt_start.shift(seconds=self.timestamp())

    def to_delta(self) -> timedelta:
        return timedelta(seconds=self.timestamp())

    def to_string_fmt(self):
        """Parse back into the parseable format by TimeString"""
        ALL_KEYS = list(_NAME_MAPS.keys())
        ALL_KEYS.reverse()
        _PRIORITY_DICT = {k: i for i, k in enumerate(ALL_KEYS)}
        sorted_list = sorted(self._data, key=lambda x: _PRIORITY_DICT.get(x.s))
        return "".join([str(x.t) + x.s for x in sorted_list])

    def to_string(self):
        """Convert to a nice string format!"""
        timestamp = self.timestamp()

        year = timestamp // (3600 * 24 * 365)
        time_remainder = timestamp % (3600 * 24 * 365)
        month = time_remainder // (3600 * 24 * 30)
        time_remainder = time_remainder % (3600 * 24 * 30)
        day = time_remainder // (3600 * 24)
        time_remainder = time_remainder % (3600 * 24)
        hour = time_remainder // 3600
        time_remainder = time_remainder % 3600
        minute = time_remainder // 60
        time_remainder = time_remainder % 60
        second = time_remainder

        second_str = str(second).split(".", 1)
        milisecond = 0
        if len(second_str) > 1:
            mili_part = float(f".{second_str[1]}")
            milisecond = int(round(mili_part * 1000))

        joined_text = []
        if year > 0:
            joined_text.append(f"{int(year)} tahun")
        if month > 0:
            joined_text.append(f"{int(month)} bulan")
        if day > 0:
            joined_text.append(f"{int(day)} hari")
        if hour > 0:
            joined_text.append(f"{int(hour)} jam")
        if minute > 0:
            joined_text.append(f"{int(minute)} menit")
        if second > 0:
            joined_text.append(f"{int(second)} detik")
        if milisecond > 0:
            joined_text.append(f"{int(milisecond)} milidetik")

        if len(joined_text) < 1:
            return "0 detik"

        return " ".join(joined_text)
