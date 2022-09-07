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

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

__all__ = ("InternalizationMod", "Internalization", "InternalizationString")
fmt_re = re.compile(r"(\{([\d\w]+)?\})", re.I)


@dataclass
class InternalizationString:
    key: str
    value: str

    def __post_init__(self):
        all_keys = fmt_re.finditer(self.value)
        valid_keys: List[str] = []
        for key in all_keys:
            valid_keys.append(key.group(2))
        setattr(self, "__valid_keys", valid_keys)

    def __format__(self, *args: List[Any], **kwargs: Dict[str, Any]) -> str:
        return self.value.format(*args, **kwargs)

    def format(self, *args, **kwargs):
        return self.__format__(*args, **kwargs)


@dataclass(eq=False)
class Internalization:
    module: str
    strings: Dict[str, InternalizationString]

    def __eq__(self, target: Union[str, Internalization]) -> bool:
        if isinstance(target, Internalization):
            return self.module == target.module
        elif isinstance(target, str):
            return self.module == target
        return False

    def __ne__(self, target: Union[str, Internalization]) -> bool:
        return not self.__eq__(target)

    def tl(self, key: str, *args: List[Any], **kwargs: Dict[str, Any]) -> str:
        if key not in self.strings:
            raise KeyError(f"Unknown key: {key}")
        return self.strings[key].format(*args, **kwargs)

    def add(self, key: str, value: Union[str, InternalizationString]):
        if isinstance(value, str):
            value = InternalizationString(key, value)
        self.strings[key] = value

    t = tl


@dataclass(eq=False)
class InternalizationMod:
    language: str
    modules: Dict[str, Internalization]

    def __eq__(self, target: Union[str, InternalizationMod]) -> bool:
        if isinstance(target, InternalizationMod):
            return self.language == target.language
        elif isinstance(target, str):
            return self.language == target
        return False

    def __ne__(self, target: Union[str, InternalizationMod]) -> bool:
        return not self.__eq__(target)

    def get(self, module: str) -> Internalization:
        if module not in self.modules:
            raise KeyError(f"Unknown module: {module}")
        return self.modules[module]

    def tl(self, module: str, key: str, *args: List[Any], **kwargs: Dict[str, Any]) -> str:
        return self.get(module).tl(key, *args, **kwargs)

    t = tl

    def patch(self, module: str, key: str, value: Union[str, InternalizationString]):
        if module not in self.modules:
            self.modules[module] = Internalization(module, {})
        self.modules[module].add(key, value)

    def add(self, module: str, value: Internalization):
        self.modules[module] = value

    def remove(self, module: str) -> Optional[Internalization]:
        return self.modules.pop(module, None)
