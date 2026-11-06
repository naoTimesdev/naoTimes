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
from string import Formatter
from typing import Any

from .errors import I18nFormatError

__all__ = (
    "KEY_SEGMENT_RE",
    "LANGUAGE_RE",
    "MODULE_RE",
    "extract_placeholders",
    "flatten_module_data",
    "validate_language",
    "validate_module_name",
)

LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
MODULE_RE = re.compile(r"^[a-z0-9_]+$")
KEY_SEGMENT_RE = re.compile(r"^[a-z0-9_]+$")

_FORMATTER = Formatter()


def extract_placeholders(text: str) -> frozenset[str]:
    """Return every named field used by :meth:`str.format` in ``text``.

    Positional fields (``{0}``) are ignored because they are formatted from
    positional arguments and can not be validated by name.
    """
    names: set[str] = set()
    try:
        parsed = list(_FORMATTER.parse(text))
    except ValueError as exc:
        raise I18nFormatError(f"Invalid format string {text!r}: {exc}") from exc
    for _, field_name, _, _ in parsed:
        if not field_name:
            continue
        # ``name.attr`` and ``name[index]`` are not used by the bot, keep the base name.
        base = re.split(r"[.[]", field_name, maxsplit=1)[0]
        if base.isdigit():
            continue
        names.add(base)
    return frozenset(names)


def validate_language(language: str) -> str:
    """Normalise and validate a language code such as ``id`` or ``en``."""
    normalized = language.strip().lower()
    if not LANGUAGE_RE.match(normalized):
        raise ValueError(f"Invalid language code: {language!r}")
    return normalized


def validate_module_name(module: str) -> str:
    """Normalise and validate a module name such as ``kutubuku``."""
    normalized = module.strip().lower()
    if not MODULE_RE.match(normalized):
        raise ValueError(f"Invalid i18n module name: {module!r}")
    return normalized


def flatten_module_data(module: str, data: Any, *, source: str = "") -> dict[str, str]:
    """Flatten a nested mapping of translations into ``dotted.key -> string`` pairs.

    Every leaf must be a non-empty string. A path can not be both a leaf and a
    namespace, which keeps lookups unambiguous.
    """
    where = source or module
    flat: dict[str, str] = {}
    namespace: set[str] = set()

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            if not node:
                raise I18nFormatError(f"{where}: empty mapping at {prefix or '<root>'!r}")
            for raw_key, child in node.items():
                if not isinstance(raw_key, str):
                    message = f"{where}: mapping key {raw_key!r} under {prefix or '<root>'!r} is not a string"
                    raise I18nFormatError(message)
                key = raw_key.strip()
                if not KEY_SEGMENT_RE.match(key):
                    raise I18nFormatError(
                        f"{where}: invalid key segment {raw_key!r} under {prefix or '<root>'!r}; "
                        "use lowercase letters, digits and underscores only"
                    )
                if prefix:
                    namespace.add(prefix)
                walk(f"{prefix}.{key}" if prefix else key, child)
            return

        if not isinstance(node, str):
            raise I18nFormatError(f"{where}: value for {prefix!r} must be a string, got {type(node).__name__}")
        if not node.strip():
            raise I18nFormatError(f"{where}: value for {prefix!r} is empty")
        if prefix in flat:
            raise I18nFormatError(f"{where}: duplicate key {prefix!r}")
        flat[prefix] = node

    walk("", data)

    collisions = namespace & flat.keys()
    if collisions:
        joined = ", ".join(sorted(collisions))
        raise I18nFormatError(f"{where}: key(s) used as both a value and a namespace: {joined}")

    return flat
