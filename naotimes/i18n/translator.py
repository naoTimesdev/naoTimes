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

import logging
from typing import Any

import discord
from discord import app_commands

from .errors import MissingModule, MissingTranslation
from .loader import DEFAULT_LANGUAGE, I18nDictionary

__all__ = (
    "naoTimesTranslator",
    "resolve_command_description",
    "resolve_localized",
    "resolve_parameter_description",
)

logger = logging.getLogger("naotimes.i18n.translator")

# Discord client locale -> language directory. Every other locale uses English,
# because a non-Indonesian client should not be served Indonesian metadata.
_LOCALE_MAP = {
    discord.Locale.indonesian: "id",
}
_FALLBACK_LANGUAGE = "en"


def language_for_locale(locale: discord.Locale | str | None) -> str:
    """Map a Discord locale to an available i18n language code."""
    if locale is None:
        return _FALLBACK_LANGUAGE
    if isinstance(locale, str):
        try:
            locale = discord.Locale(locale)
        except ValueError:
            return _FALLBACK_LANGUAGE
    return _LOCALE_MAP.get(locale, _FALLBACK_LANGUAGE)


def resolve_localized(
    i18n: I18nDictionary,
    value: str | app_commands.locale_str,
    locale: discord.Locale | str | None = None,
) -> str:
    """Resolve a ``str`` or ``locale_str`` into displayable text.

    Used by ``/help`` and anywhere a command description is rendered, because
    ``discord.py`` keeps ``locale_str`` objects on the command metadata.
    """
    if not isinstance(value, app_commands.locale_str):
        return str(value)

    key = value.extras.get("key")
    if key:
        try:
            return i18n.get(language_for_locale(locale)).resolve_key(key)
        except (MissingModule, MissingTranslation):
            pass
    return value.message


class naoTimesTranslator(app_commands.Translator):
    """Translate slash command metadata using the bot's translation catalog."""

    def __init__(self, i18n: I18nDictionary):
        self.i18n = i18n
        self.logger = logger

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext[Any, Any],
    ) -> str | None:
        key = string.extras.get("key")
        if not key:
            return None
        language = language_for_locale(locale)
        if language == DEFAULT_LANGUAGE:
            # The source string is already Indonesian; let Discord use it.
            return None
        try:
            return self.i18n.get(language).resolve_key(key)
        except (MissingModule, MissingTranslation):
            return None


def resolve_command_description(
    i18n: I18nDictionary,
    command: app_commands.Command[Any, Any, Any] | app_commands.Group | app_commands.ContextMenu,
    locale: discord.Locale | str | None = None,
) -> str:
    """Resolve a command/group description, honouring ``locale_str`` metadata."""
    value = getattr(command, "_locale_description", None)
    if value is None:
        return str(getattr(command, "description", "") or "")
    return resolve_localized(i18n, value, locale)


def resolve_parameter_description(
    i18n: I18nDictionary,
    parameter: app_commands.Parameter,
    locale: discord.Locale | str | None = None,
) -> str:
    """Resolve a command parameter description, honouring ``locale_str`` metadata."""
    value = getattr(parameter, "locale_description", None)
    if value is None:
        return str(parameter.description)
    return resolve_localized(i18n, value, locale)
