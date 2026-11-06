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

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML, YAMLError

from ._schema import flatten_module_data, validate_language, validate_module_name
from .errors import I18nError, I18nFormatError
from .models import Internalization, InternalizationMod, InternalizationString

__all__ = (
    "DEFAULT_LANGUAGE",
    "I18nDictionary",
    "load_i18n",
    "load_i18n_async",
)

CURRENT = Path(__file__).absolute().parent
I18N_PATH = CURRENT.parent.parent / "i18n"
DEFAULT_LANGUAGE = "id"
logger = logging.getLogger("naotimes.i18n")

_YAML_EXTENSIONS = frozenset({".yaml", ".yml"})


class I18nDictionary:
    """A collection of translations for every available language."""

    def __init__(self, default_language: str = DEFAULT_LANGUAGE):
        self._languages: dict[str, InternalizationMod] = {}
        self.default_language = validate_language(default_language)

    @property
    def languages(self) -> list[str]:
        return list(self._languages)

    @property
    def known_modules(self) -> frozenset[str]:
        """Every module name that exists in at least one language."""
        modules: set[str] = set()
        for mod in self._languages.values():
            modules.update(mod.modules)
        return frozenset(modules)

    def is_module(self, module: str) -> bool:
        return any(module in mod.modules for mod in self._languages.values())

    def __repr__(self) -> str:
        return f"<I18nDictionary: {len(self)} languages>"

    def __iter__(self) -> Iterator[str]:
        return iter(self._languages)

    def __contains__(self, language: object) -> bool:
        return isinstance(language, str) and language.lower() in self._languages

    def __len__(self) -> int:
        return len(self._languages)

    def keys(self) -> Iterator[str]:
        return iter(self._languages.keys())

    def values(self) -> Iterator[InternalizationMod]:
        return iter(self._languages.values())

    def items(self) -> Iterator[tuple[str, InternalizationMod]]:
        return iter(self._languages.items())

    def __getitem__(self, language: str) -> InternalizationMod | None:
        return self.get(language)

    def __setitem__(self, language: str, value: InternalizationMod) -> None:
        if not isinstance(value, InternalizationMod):
            raise TypeError(f"Value must be an instance of InternalizationMod, not {type(value)}")
        normalised = validate_language(language)
        value.language = normalised
        self._languages[normalised] = value
        self._apply_fallback()

    def __delitem__(self, language: str) -> None:
        self._languages.pop(language.lower(), None)
        self._refresh_default()
        self._apply_fallback()

    def _refresh_default(self) -> None:
        if self.default_language in self._languages or not self._languages:
            return
        self.default_language = next(iter(self._languages))

    def _apply_fallback(self) -> None:
        default: InternalizationMod | None = self._languages.get(self.default_language)
        for language, module in self._languages.items():
            module.fallback = None if language == self.default_language else default

    def set_default(self, language: str) -> None:
        normalised = validate_language(language)
        if normalised not in self._languages:
            raise KeyError(f"Language {normalised!r} is not loaded")
        self.default_language = normalised
        self._apply_fallback()

    def get(self, language: str | None = None, default: InternalizationMod | None = None) -> InternalizationMod:
        """Return a language, falling back to the default language when unknown."""
        if language is not None:
            value = self._languages.get(language.lower())
            if value is not None:
                return value
        if default is not None:
            return default
        return self.getdefault()

    def getdefault(self) -> InternalizationMod:
        if not self._languages:
            raise I18nError("No translations were loaded")
        default = self._languages.get(self.default_language)
        if default is not None:
            return default
        return next(iter(self._languages.values()))

    def pop(self, language: str, default: InternalizationMod | None = None) -> InternalizationMod | None:
        value = self._languages.pop(language.lower(), default)
        self._refresh_default()
        self._apply_fallback()
        return value

    def merge(self, language: str, data: InternalizationMod) -> None:
        normalised = validate_language(language)
        existing = self._languages.get(normalised)
        if existing is None:
            self[normalised] = data
            return
        for module_name, module in data.modules.items():
            target = existing.modules.get(module_name)
            if target is None:
                existing.modules[module_name] = Internalization(module_name, dict(module.strings))
            else:
                target.strings.update(module.strings)
        self._apply_fallback()

    def translate(self, language: str | None, module: str, key: str, *args: Any, **kwargs: Any) -> str:
        return self.get(language).resolve(module, key, *args, **kwargs)

    def translate_key(self, language: str | None, dotted_key: str, *args: Any, **kwargs: Any) -> str:
        return self.get(language).resolve_key(dotted_key, *args, **kwargs)

    def __add__(self, other: InternalizationMod) -> I18nDictionary:
        if not isinstance(other, InternalizationMod):
            raise TypeError(f"Value must be an instance of InternalizationMod, not {type(other)}")
        self.merge(other.language, other)
        return self

    __radd__ = __add__

    def __iadd__(self, other: InternalizationMod) -> I18nDictionary:
        return self.__add__(other)


def _read_module_file(path: Path, language: str) -> dict[str, str]:
    parser = YAML(typ="safe")
    try:
        with path.open("r", encoding="utf-8") as file:
            data = parser.load(file)
    except (OSError, YAMLError) as exc:
        raise I18nFormatError(f"{path}: could not parse YAML: {exc}") from exc

    if data is None:
        raise I18nFormatError(f"{path}: file is empty")
    if not isinstance(data, dict):
        raise I18nFormatError(f"{path}: expected a mapping at the top level")
    if tuple(data.keys()) == (language,):
        raise I18nFormatError(
            f"{path}: legacy language wrapper detected; store translations directly "
            f"under {language!r} without the top-level language key"
        )

    module = validate_module_name(path.stem)
    return flatten_module_data(module, data, source=str(path))


def _build_mod(language: str, modules: dict[str, dict[str, str]]) -> InternalizationMod:
    mod = InternalizationMod(language, {})
    for module_name, strings in modules.items():
        internalization = Internalization(module_name, {})
        for key, value in strings.items():
            internalization.strings[key] = InternalizationString(key, value)
        mod.modules[module_name] = internalization
    return mod


def _warn_about_mismatch(dictionary: I18nDictionary) -> None:
    default = dictionary.getdefault()
    for mod in dictionary.values():
        if mod.language == dictionary.default_language:
            continue
        for module_name, module in mod.modules.items():
            base = default.get_optional(module_name)
            if base is None:
                logger.warning(
                    "i18n: module %r exists in %r but not in the default language %r",
                    module_name,
                    mod.language,
                    dictionary.default_language,
                )
                continue
            for key in sorted(module.strings.keys() - base.strings.keys()):
                logger.warning(
                    "i18n: %s.%s exists in %r but not in the default language %r",
                    module_name,
                    key,
                    mod.language,
                    dictionary.default_language,
                )
            for key in sorted(module.strings.keys() & base.strings.keys()):
                translated = module.strings[key]
                source = base.strings[key]
                if translated.placeholders != source.placeholders:
                    logger.warning(
                        "i18n: placeholder mismatch for %s.%s (%r has %s, default has %s)",
                        module_name,
                        key,
                        mod.language,
                        sorted(translated.placeholders),
                        sorted(source.placeholders),
                    )


def load_i18n(base_path: str | Path | None = None, default_language: str = DEFAULT_LANGUAGE) -> I18nDictionary:
    """Load every translation file below ``base_path``.

    The language is taken from the parent directory name and the module name
    from the file name: ``i18n/<language>/<module>.yaml``.
    """
    root = Path(base_path) if base_path is not None else I18N_PATH
    default_language = validate_language(default_language)

    if not root.exists():
        logger.warning("i18n directory %s does not exist; translations are unavailable", root)
        return I18nDictionary(default_language=default_language)

    files = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in _YAML_EXTENSIONS)
    loaded: dict[str, dict[str, dict[str, str]]] = {}
    errors: list[str] = []

    for path in files:
        language = path.parent.name.lower()
        try:
            validate_language(language)
        except ValueError as exc:
            errors.append(f"{path}: {exc}")
            continue
        module = path.stem.lower()
        try:
            flat = _read_module_file(path, language)
        except (I18nFormatError, ValueError) as exc:
            errors.append(str(exc))
            continue
        bucket = loaded.setdefault(language, {})
        if module in bucket:
            errors.append(f"{path}: duplicate module {module!r} for language {language!r}")
            continue
        bucket[module] = flat

    for message in errors:
        logger.error("i18n: %s", message)

    default_modules = loaded.get(default_language)
    if not default_modules:
        detail = "\n".join(errors) if errors else "no translation files were found"
        raise I18nError(f"Could not load the default language {default_language!r}: {detail}")

    dictionary = I18nDictionary(default_language=default_language)
    dictionary[default_language] = _build_mod(default_language, default_modules)
    for language in sorted(loaded):
        if language == default_language:
            continue
        dictionary[language] = _build_mod(language, loaded[language])

    _warn_about_mismatch(dictionary)
    logger.info(
        "Loaded %d language(s) from %d file(s): %s",
        len(dictionary),
        len(files),
        ", ".join(dictionary.languages),
    )
    return dictionary


async def load_i18n_async(
    loop: asyncio.AbstractEventLoop | None = None,
    base_path: str | Path | None = None,
    default_language: str = DEFAULT_LANGUAGE,
) -> I18nDictionary:
    """Asynchronous wrapper around :func:`load_i18n`."""
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: load_i18n(base_path, default_language))
