"""
A wrapper of JishoAPI (Utilizing ihateani.me API)

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

import asyncio
import logging
import time
from typing import List, Tuple, Union

import aiohttp
import cutlet

from ..version import __version__ as semver

__all__ = ("JishoParseFailed", "JishoWord", "JishoAPI")


class JishoParseFailed(Exception):
    pass


class JishoWord:
    def __init__(self, raw_data: dict):
        self.__raw = raw_data
        self.__katsu = cutlet.Cutlet("hepburn")
        self.__parse()

    def __repr__(self) -> str:
        rep = "JishoWord(word={})".format(getattr(self, "__word", ""))
        return rep

    def __str__(self) -> str:
        """Return a parsed data as a readable text for end-user
        This is auto-formatted.

        :return: formatted text of the data
        :rtype: str
        """
        build_text = f"{self.word}\n{self.meanings}"
        other_forms = self.other_forms
        if other_forms:
            build_text += f"\n{other_forms}"
        return build_text

    def __parse(self):
        """Internal data parser

        DO NOT USE MANUALLY
        """
        if len(list(self.__raw.keys())) < 1:
            setattr(self, "__success", False)
            return
        raw_slug = self.__raw.get("slug")
        parsed_slug = raw_slug.split("-")
        if len(parsed_slug) > 1:
            word = parsed_slug[0]
            try:
                numbering = parsed_slug[1]
                if numbering:
                    numbering = int(numbering)
                else:
                    numbering = -1
            except (ValueError, IndexError):
                numbering = -1
        else:
            word = parsed_slug[0]
            numbering = -1
        is_slug_only = False
        try:
            int(raw_slug, 16)
            is_slug_only = True
        except ValueError:
            pass
        setattr(self, "__sluggish", raw_slug)
        if not is_slug_only:
            setattr(self, "__word", word)
        setattr(self, "__numbering", numbering)
        common_word = self.__raw.get("is_common", False)
        setattr(self, "__is_common", common_word)
        jlpt = self.__raw.get("jlpt", [])
        if jlpt:
            jl, level = jlpt[0].split("-")
            setattr(self, "__jlpt", f"{jl.upper()} {level.upper()}")
        else:
            setattr(self, "__jlpt", None)
        tags = self.__raw.get("tags")
        wanikani = None
        for tag in tags:
            if "wanikani" in tag:
                wani_level = tag.replace("wanikani", "")
                wanikani = f"Wanikani Level {wani_level}"
        other_readings = []
        for n, jpwords in enumerate(self.__raw.get("japanese", [])):
            if n == 0:
                real_word = jpwords.get("word")
                if real_word and is_slug_only:
                    setattr(self, "__word", real_word)
                reading = jpwords.get("reading")
                if reading is not None or not reading:
                    setattr(self, "__reading", reading)
                    if real_word is None:
                        setattr(self, "__reading", None)
                    try:
                        setattr(self, "__romaji", self.__katsu.romaji(reading))
                    except Exception:  # skipcq: PYL-W0703
                        setattr(self, "__romaji", None)
                else:
                    setattr(self, "__reading", None)
                    setattr(self, "__romaji", None)
                continue
            word = jpwords.get("word")
            reading = jpwords.get("reading")
            romanization = None
            if reading is not None or not reading:
                romanization = self.__katsu.romaji(reading)
            if word is None and reading is not None:
                word = reading
                reading = None
            other_readings.append({"word": word, "reading": reading, "romaji": romanization})
        setattr(self, "__other_forms", other_readings)
        meanings = []
        _temporary_wiki_meaning_single = None
        meanings = []
        for meaning in self.__raw.get("senses", []):
            parts = ", ".join(meaning["parts_of_speech"]).lower()
            wrap_parts = [f"({part.lower()})" for part in meaning.get("parts_of_speech", [])]
            english_definitions = ", ".join(meaning.get("english_definitions", []))
            if not english_definitions:
                english_definitions = "Tidak ada definisi"
            tagged_stuff = " // ".join(meaning.get("tags", []))
            extra_info = "; ".join(meaning.get("info", []))
            see_also = "; ".join(meaning.get("see_also", []))
            if "wikipedia" in parts:
                if _temporary_wiki_meaning_single is None:
                    _temporary_wiki_meaning_single = {
                        "part": ["(wiki)"],
                        "definition": english_definitions,
                        "extra_info": extra_info or None,
                        "suggestion": see_also or None,
                        "tags": tagged_stuff,
                    }
                continue
            if not extra_info:
                extra_info = None
            if not see_also:
                see_also = None
            meanings.append(
                {
                    "part": wrap_parts,
                    "definition": english_definitions,
                    "extra_info": extra_info,
                    "suggestion": see_also,
                    "tags": tagged_stuff,
                }
            )
        if not meanings and _temporary_wiki_meaning_single is not None:
            meanings.append(_temporary_wiki_meaning_single)
        setattr(self, "__meanings", meanings)
        setattr(self, "__wanikani", wanikani)
        setattr(self, "__success", True)
        try:
            delattr(self, "_JishoWord__raw")
        except AttributeError:
            try:
                delattr(self, "__raw")
            except AttributeError:
                pass

    @property
    def is_success(self) -> bool:
        """Is the parsing success or not"""
        return bool(getattr(self, "__success", False))

    @property
    def word(self) -> str:
        """Create a formatted string of the word

        This might contains the original kanji, readings, and romanization
        and possibly the numbering if available

        :return: A formatted string of the word
        :rtype: str
        """
        build_text = ""
        numbering = getattr(self, "__numbering", -1)
        build_text += getattr(self, "__word", "????") + " "
        if numbering > 0:
            build_text += f"<{numbering}> "
        reading = getattr(self, "__reading", None)
        romaji = getattr(self, "__romaji", None)
        if isinstance(reading, str):
            build_text += f"({reading}) "
        if isinstance(romaji, str):
            build_text += f"[{romaji}] "
        return build_text.rstrip(" ")

    @property
    def url(self) -> str:
        slug = getattr(self, "__sluggish", None)
        return f"https://jisho.org/word/{slug}"

    @property
    def meanings(self) -> str:
        """Return a formatted text of the word meanings or definitions of it

        :return: formatted text of the definitions or meanings
        :rtype: str
        """
        meanings: List[dict] = getattr(self, "__meanings", [])
        if len(meanings) < 1:
            return "Tidak ada arti."
        collected_text = []
        for n, meaning in enumerate(meanings, 1):
            build_txt = ""
            parts = " ".join(meaning.get("part", []))
            build_txt += f"{n}. "
            if parts:
                build_txt += f"{parts} "
            build_txt += meaning.get("definition", "Tidak ada definisi")
            extra_info = meaning.get("extra_info", "")
            suggestion = meaning.get("suggestion", "")
            tags = meaning.get("tags", "")
            if extra_info:
                build_txt += f"\n\t{extra_info}"
            if tags:
                build_txt += f"\n\t{tags}"
            if suggestion:
                build_txt += f"\n\tLihat juga: {suggestion}"
            collected_text.append(build_txt)
        return "\n".join(collected_text).rstrip("\n")

    @property
    def other_forms(self) -> str:
        """Return a formatted string of any other forms

        Include the kanji, reading, and romaji.
        Not all of the might be available if the kanji is already in kana format.

        :return: formatted string of the other forms
        :rtype: str
        """
        other_forms = getattr(self, "__other_forms", [])
        if len(other_forms) < 1:
            return ""
        collected_text = []
        for other in other_forms:
            build_text = ""
            build_text += other.get("word") + " "
            reading = other.get("reading", None)
            romaji = other.get("romaji", None)
            if isinstance(reading, str):
                build_text += f"({reading}) "
            if isinstance(romaji, str):
                build_text += f"[{romaji}] "
            collected_text.append(build_text.rstrip(" "))
        return "Bentuk lain: " + "; ".join(collected_text)

    def to_dict(self) -> dict:
        """Convert the parsed data into a dictionary that can be used.

        :return: A dict data of the parsed data.
        :rtype: dict
        """
        word = getattr(self, "__word", "????")
        numbering = getattr(self, "__numbering", -1)
        reading = getattr(self, "__reading", None)
        romaji = getattr(self, "__romaji", None)
        is_common = getattr(self, "__is_common", False)

        other_forms = getattr(self, "__other_forms", [])

        meanings: List[dict] = getattr(self, "__meanings", [])
        wanikani = getattr(self, "__wanikani", None)
        jlpt = getattr(self, "__jlpt", None)

        return {
            "word": word,
            "numbering": numbering,
            "reading": {"kana": reading, "romaji": romaji},
            "other_forms": other_forms,
            "definitions": meanings,
            "appearances": {"jlpt": jlpt, "wanikani": wanikani},
            "is_common": is_common,
            "is_success": self.is_success,
        }


class JishoAPI:
    def __init__(self, session: aiohttp.ClientSession = None) -> None:
        if session is None:
            self._conn = aiohttp.ClientSession(
                headers={"User-Agent": f"naoTimes/v{semver} (https://github.com/noaione/naoTimes)"}
            )
            self._internal_session = True
        else:
            self._conn = session
            self._internal_session = False
        self._logger = logging.getLogger("naoTimes.JishoAPI")

        self._is_closing = False
        self._on_request = []

    async def close(self):
        """Terminate the underlying connection"""
        if not self._internal_session:
            self._is_closing = True
            return
        while len(self._on_request) > 0:
            if len(self._on_request) < 1:
                break
            await asyncio.sleep(0.2)
        self._is_closing = True
        await self._conn.close()

    async def parse(self, results: Union[List[dict], dict]) -> List[JishoWord]:
        """|coro|

        This function parse the results of a Jisho API response or the data list of it.

        :param results: The results of the API response, can be the list of the data or the raw result
        :type results: Union[List[dict], dict]
        :return: Parsed data
        :rtype: List[JishoWord]
        """
        if isinstance(results, dict):
            meta = results.get("meta", {})
            status_code = meta.get("status", 503)
            if status_code >= 400:
                return []
            results = results.get("data", [])
        parsed_results: List[JishoWord] = []
        for n, result in enumerate(results):
            try:
                parsed_results.append(JishoWord(result))
            except JishoParseFailed:
                self._logger.error(f"Failed to parse data index {n}")
        return parsed_results

    async def search(self, keyword: str) -> Tuple[List[JishoWord], str]:
        """|coro|

        Search Jisho for a kanji, word, or anything else by providing a keyword.

        :param keyword: Keyword to search, can be kanji, kana, or normal english writing.
        :type keyword: str
        :return: Result from the API, parsed into a nice format ready to use.
        :rtype: List[JishoWord]
        """
        if self._is_closing:
            return []
        uniq_id = f"search_{time.time()}"
        self._on_request.append(uniq_id)
        parameter = {"keyword": keyword}
        async with self._conn.get("https://jisho.org/api/v1/search/words", params=parameter) as resp:
            if resp.status != 200:
                if resp.status == 404:
                    return [], "Tidak ada hasil."
                self._logger.warning(f"error, status code: {resp.status}")
                self._on_request.remove(uniq_id)
                return (
                    [],
                    f"Terjadi kesalahan ketika menghubungi Jisho, mendapatkan HTTP Status {resp.status}",
                )
            try:
                raw_dict: dict = await resp.json()
            except ValueError:
                self._logger.warning("Failed to parse fetch result.")
                self._on_request.remove(uniq_id)
                return [], "Gagal memparsing data dari API."
            results = raw_dict.get("data", [])
            self._on_request.remove(uniq_id)
        parsed_data = await self.parse(results)
        if len(parsed_data) < 1:
            return parsed_data, "Tidak ada hasil."
        return parsed_data, "Sukses."
