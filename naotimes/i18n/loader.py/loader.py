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

import asyncio
import logging
from os.path import basename, splitext
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from aiopath import AsyncPath
from ruamel.yaml import YAML
from schema import SchemaError

from ._schema import I18nData, I18nSchema
from .models import InternalizationMod

__all__ = (
    "load_i18n_async",
    "I18nDictionary",
)
CURRENT = Path(__file__).absolute().parent
I18N_PATH = AsyncPath(CURRENT.parent.parent / "i18n")
logger = logging.getLogger("naotimes.i18n")


def get_language(filename: str):
    return splitext(basename(filename))[0]


async def validate_i18n(i18n_data: I18nData, *, loop: asyncio.AbstractEventLoop = None):
    loop = loop or asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            I18nSchema.validate,
            i18n_data,
        )
        return True
    except SchemaError:
        return False


async def parse_yaml_file(yaml_file: AsyncPath) -> Union[Any, str, str]:
    yaml_parser = YAML(typ="safe")
    async with yaml_file.open() as fp:
        yaml_data = await fp.read()
        parsed_yaml = yaml_parser.load(yaml_data)
    lang = get_language(yaml_file.parent.name)
    return parsed_yaml[lang], get_language(yaml_file.name), lang


class I18nDictionary:
    __i18n_sets: Dict[str, InternalizationMod]
    __default: Optional[str]

    def __init__(self):
        self.__i18n_sets = {}
        self.__default = None

    def get(self, key: str, default: Optional[InternalizationMod] = None) -> Optional[InternalizationMod]:
        actual_value = self.__i18n_sets.get(key.lower())
        default_value = default or self.getdefault()
        # Return value or the default value
        return actual_value or default_value

    def pop(self, key: str, default: Optional[str] = None) -> Optional[InternalizationMod]:
        self.__annotations__.pop(key.lower(), None)
        return self.__i18n_sets.pop(key.lower(), default)

    def __repr__(self):
        return f"<I18nDictionary: {len(self)} languages>"

    def __iter__(self) -> Iterator[InternalizationMod]:
        for key in self.__i18n_sets.keys():
            yield key

    def keys(self) -> Iterator[str]:
        for key in self.__i18n_sets.keys():
            yield key

    def values(self) -> Iterator[InternalizationMod]:
        for value in self.__i18n_sets.values():
            yield value

    def items(self) -> Iterator[Tuple[str, InternalizationMod]]:
        for key, value in self.__i18n_sets.items():
            yield key, value

    def __getitem__(self, key: str) -> Optional[InternalizationMod]:
        return self.get(key)

    def __setitem__(self, key: str, value: InternalizationMod) -> None:
        if not isinstance(value, InternalizationMod):
            raise TypeError(f"Value must be an instance of InternalizationMod, not {type(value)}")
        if self.__default is None:
            self.__default = key.lower()
        self.__annotations__[key.lower()] = InternalizationMod
        self.__i18n_sets[key.lower()] = value

    def __delitem__(self, key: str) -> None:
        try:
            del self.__i18n_sets[key.lower()]
        except KeyError:
            pass

    def __len__(self) -> int:
        return len(list(self.__i18n_sets.keys()))

    def setdefault(self, key: str):
        key = key.lower()
        if key in self.__i18n_sets:
            self.__default = key

    def getdefault(self) -> InternalizationMod:
        if self.__default is None:
            return self.__i18n_sets[list(self.__i18n_sets.keys())[0]]
        return self.__i18n_sets[self.__default]

    def merge(self, language: str, data: InternalizationMod):
        if language not in self.__i18n_sets:
            self.__i18n_sets[language] = data
            return

        for mod, mod_val in data.modules.items():
            for key, val in mod_val.strings.items():
                self.__i18n_sets[language].patch(mod, key, val)

    def __add__(self, other: InternalizationMod):
        if not isinstance(other, InternalizationMod):
            raise TypeError(f"Value must be an instance of InternalizationMod, not {type(other)}")
        lang = other.language
        self.merge(lang, other)
        return self

    __radd__ = __add__

    def __iadd__(self, other: InternalizationMod):
        return self.__add__(other)


def _create_mod(language: str, data: Dict[str, Dict[str, str]]):
    i18n_mod = InternalizationMod(language, {})
    for module, module_data in data.items():
        for key_tl, value_tl in module_data.items():
            i18n_mod.patch(module, key_tl, value_tl)
    return i18n_mod


async def load_i18n_async(loop: asyncio.AbstractEventLoop = None) -> Optional[I18nDictionary]:
    loop = loop or asyncio.get_event_loop()
    actually_exists = not (await I18N_PATH.is_file()) and await I18N_PATH.exists()
    if not actually_exists:
        return None

    logger.info("Creating i18n dictionary...")
    i18n_modules = I18nDictionary()
    all_yaml_files: List[AsyncPath] = []
    logger.info("Fetching all yaml files...")
    async for yaml_file in I18N_PATH.rglob("*.yaml"):
        all_yaml_files.append(yaml_file)
    async for yaml_file in I18N_PATH.rglob("*.yml"):
        all_yaml_files.append(yaml_file)
    logger.info(f"Got {len(all_yaml_files)} files! Parsing...")
    finalized_json_files: Dict[str, Dict[str, str]] = {}
    for yaml_file in all_yaml_files:
        as_json_yaml, module_name, language = await parse_yaml_file(yaml_file)
        if language not in finalized_json_files:
            finalized_json_files[language] = {}
        if module_name not in finalized_json_files[language]:
            finalized_json_files[language][module_name] = {}
        for key, value in as_json_yaml.items():
            finalized_json_files[language][module_name][key] = value
    for language, i18n_data in finalized_json_files.items():
        is_valid_i18n = await validate_i18n(i18n_data, loop=loop)
        if is_valid_i18n:
            logger.info(f"Creating i18n mod for {language}...")
            parsed_mod_yaml = _create_mod(language, i18n_data)
            i18n_modules += parsed_mod_yaml

    return i18n_modules
