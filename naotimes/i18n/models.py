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

from dataclasses import dataclass, field
from typing import Any

from ._schema import extract_placeholders
from .errors import MissingModule, MissingTranslation

__all__ = ("Internalization", "InternalizationMod", "InternalizationString", "ModuleTranslator")


@dataclass
class InternalizationString:
    """A single translated string."""

    key: str
    value: str
    placeholders: frozenset[str] = field(init=False, repr=False, default_factory=frozenset)

    def __post_init__(self) -> None:
        self.placeholders = extract_placeholders(self.value)

    def __format__(self, format_spec: str) -> str:
        return format(self.value, format_spec)

    def format(self, *args: Any, **kwargs: Any) -> str:
        return self.value.format(*args, **kwargs)


@dataclass(eq=False)
class Internalization:
    """Every string that belongs to one module in one language."""

    module: str
    strings: dict[str, InternalizationString] = field(default_factory=dict)

    def __eq__(self, target: object) -> bool:
        if isinstance(target, Internalization):
            return self.module == target.module
        if isinstance(target, str):
            return self.module == target
        return NotImplemented

    def __ne__(self, target: object) -> bool:
        result = self.__eq__(target)
        if result is NotImplemented:
            return result
        return not result

    def __contains__(self, key: str) -> bool:
        return key in self.strings

    def __len__(self) -> int:
        return len(self.strings)

    def has(self, key: str) -> bool:
        return key in self.strings

    def get(self, key: str) -> InternalizationString | None:
        return self.strings.get(key)

    def add(self, key: str, value: str | InternalizationString) -> None:
        if isinstance(value, str):
            value = InternalizationString(key, value)
        self.strings[key] = value

    def format(self, translation_key: str, *args: Any, **kwargs: Any) -> str:
        entry = self.strings.get(translation_key)
        if entry is None:
            raise MissingTranslation(self.module, translation_key)
        return entry.format(*args, **kwargs)

    def tl(self, translation_key: str, *args: Any, **kwargs: Any) -> str:
        return self.format(translation_key, *args, **kwargs)

    # Backwards-compatible short alias.
    def t(self, translation_key: str, *args: Any, **kwargs: Any) -> str:
        return self.format(translation_key, *args, **kwargs)


@dataclass(eq=False)
class InternalizationMod:
    """Every translation that belongs to one language."""

    language: str
    modules: dict[str, Internalization] = field(default_factory=dict)
    fallback: InternalizationMod | None = field(default=None, repr=False)

    def __eq__(self, target: object) -> bool:
        if isinstance(target, InternalizationMod):
            return self.language == target.language
        if isinstance(target, str):
            return self.language == target
        return NotImplemented

    def __ne__(self, target: object) -> bool:
        result = self.__eq__(target)
        if result is NotImplemented:
            return result
        return not result

    def has_module(self, module: str) -> bool:
        return module in self.modules

    def get(self, module: str) -> Internalization:
        value = self.modules.get(module)
        if value is None:
            raise MissingModule(module)
        return value

    def get_optional(self, module: str) -> Internalization | None:
        return self.modules.get(module)

    def resolve(self, module: str, translation_key: str, *args: Any, **kwargs: Any) -> str:
        """Resolve ``module``/``translation_key`` in this language, falling back to the default one."""
        current = self.modules.get(module)
        if current is not None and current.has(translation_key):
            return current.format(translation_key, *args, **kwargs)
        if self.fallback is not None and self.fallback is not self:
            return self.fallback.resolve(module, translation_key, *args, **kwargs)
        raise MissingTranslation(module, translation_key, self.language)

    def resolve_key(self, dotted_key: str, *args: Any, **kwargs: Any) -> str:
        """Resolve a fully qualified key such as ``common.errors.user_info``."""
        module, separator, key = dotted_key.partition(".")
        if not separator or not module or not key:
            raise MissingTranslation("", dotted_key, self.language)
        return self.resolve(module, key, *args, **kwargs)

    def tl(self, module: str, translation_key: str, *args: Any, **kwargs: Any) -> str:
        return self.resolve(module, translation_key, *args, **kwargs)

    # Backwards-compatible short alias.
    def t(self, module: str, translation_key: str, *args: Any, **kwargs: Any) -> str:
        return self.resolve(module, translation_key, *args, **kwargs)

    def patch(self, module: str, translation_key: str, value: str | InternalizationString) -> None:
        target = self.modules.get(module)
        if target is None:
            target = Internalization(module, {})
            self.modules[module] = target
        target.add(translation_key, value)

    def add(self, module: str, value: Internalization) -> None:
        self.modules[module] = value

    def remove(self, module: str) -> Internalization | None:
        return self.modules.pop(module, None)


class ModuleTranslator:
    """A language set bound to one module, for code without a context."""

    __slots__ = ("_mod", "_module")

    def __init__(self, mod: InternalizationMod, module: str):
        self._mod = mod
        self._module = module

    @property
    def language(self) -> str:
        return self._mod.language

    @property
    def module(self) -> str:
        return self._module

    def t(self, translation_key: str, *args: Any, **kwargs: Any) -> str:
        return self._mod.resolve(self._module, translation_key, *args, **kwargs)

    __call__ = t
