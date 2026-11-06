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

__all__ = ("I18nError", "I18nFormatError", "MissingModule", "MissingTranslation")


class I18nError(Exception):
    """Base exception for every error raised by the i18n subsystem."""


class I18nFormatError(I18nError, ValueError):
    """Raised when a translation file does not follow the documented layout."""


class MissingModule(I18nError, KeyError):
    """Raised when a language does not contain the requested module."""

    def __init__(self, module: str) -> None:
        self.module = module
        super().__init__(f"Unknown i18n module: {module}")

    def __str__(self) -> str:
        # ``KeyError`` would otherwise wrap the message in quotes.
        return self.args[0]


class MissingTranslation(I18nError, KeyError):
    """Raised when a key can not be resolved in the requested or fallback language."""

    def __init__(self, module: str, key: str, language: str | None = None) -> None:
        self.module = module
        self.key = key
        self.language = language
        location = f"{module}.{key}" if module else key
        detail = f" (language: {language})" if language else ""
        super().__init__(f"Missing translation key: {location}{detail}")

    def __str__(self) -> str:
        return self.args[0]
