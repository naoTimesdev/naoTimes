"""
MIT License

Copyright (c) 2019-2022 naoTimesdev

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

import re
from typing import Dict, TypedDict

import schema as sc

__all__ = ("AnyKeySchema", "I18nSchema")


AnyKeySchema = sc.Schema(
    {
        sc.Regex(r"^[a-zA-Z0-9_]+$", re.I): str,
    }
)

I18nSchema = sc.Schema(
    {
        "default": sc.Or(AnyKeySchema, dict),
        sc.Optional("ayaya"): sc.Or(AnyKeySchema, dict),
        sc.Optional("bahaya"): sc.Or(AnyKeySchema, dict),
        sc.Optional("botbrain"): sc.Or(AnyKeySchema, dict),
        sc.Optional("fun"): sc.Or(AnyKeySchema, dict),
        sc.Optional("kutubuku"): sc.Or(AnyKeySchema, dict),
        sc.Optional("modlogs"): sc.Or(AnyKeySchema, dict),
        sc.Optional("modtools"): sc.Or(AnyKeySchema, dict),
        sc.Optional("musik"): sc.Or(AnyKeySchema, dict),
        sc.Optional("peninjau"): sc.Or(AnyKeySchema, dict),
        sc.Optional("showtimes"): sc.Or(AnyKeySchema, dict),
        sc.Optional("vote"): sc.Or(AnyKeySchema, dict),
    }
)


class _OptionalI18nData(TypedDict, total=False):
    ayaya: Dict[str, str]
    bahaya: Dict[str, str]
    botbrain: Dict[str, str]
    fun: Dict[str, str]
    kutubuku: Dict[str, str]
    modlogs: Dict[str, str]
    modtools: Dict[str, str]
    musik: Dict[str, str]
    peninjau: Dict[str, str]
    showtimes: Dict[str, str]
    vote: Dict[str, str]


class I18nData(_OptionalI18nData):
    default: Dict[str, str]
