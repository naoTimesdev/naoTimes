"""
An async wrapper for Tesaurus Tematis (tesaurus.kemendikdasmen.go.id)
Based on tesaurus-python 0.1.3

---

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
from typing import cast, override

import bs4
from bs4 import Tag
from tesaurus import KelasKataTidakDiketahui, Lema, LemaEntri, TerjadiKesalahan, TesaurusGalat, TidakDitemukan
from tesaurus import TesaurusAsync as TesaurusAsyncBase

__all__ = [
    "KelasKataTidakDiketahui",
    "Lema",
    "LemaEntri",
    "TerjadiKesalahan",
    "TesaurusAsync",
    "TesaurusGalat",
    "TidakDitemukan",
    "parse_entri",
]

# The website closes the comment around its Google Analytics snippet with
# "--!>" instead of "-->". HTML5 treats that as a valid comment terminator (so
# browsers render the page normally), but Python's stdlib html.parser does not:
# it keeps the comment open and swallows the rest of the document, which leaves
# an empty <body> and no div.contain to scrape. Normalize the terminator so the
# document is parsed the same way a browser would.
_HTML_COMMENT_END_BANG = re.compile(r"--!>")


def _normalize_html(laman: str) -> str:
    return _HTML_COMMENT_END_BANG.sub("-->", laman)


def parse_entri(laman: str, kelas_kata: str | None = None) -> list[LemaEntri]:
    """Parse a Tesaurus Tematis lemma page into a list of :class:`LemaEntri`.

    The page groups its results by word class using ``div.result-postag``; every
    group after that marker is made of ``div.result-set`` blocks. Pages requested
    with an explicit word class (e.g. ``/tematis/lema/makan/verba``) do not carry
    those markers, so the whole result area becomes one group using
    ``kelas_kata`` as the fallback word class.

    :param laman: raw HTML of the lemma page
    :type laman: str
    :param kelas_kata: word class to fall back to when the page has no markers,
                       defaults to None
    :type kelas_kata: str, optional
    :raises TesaurusGalat: when the page has no result container to scrape
    :return: parsed entries, one per word class group
    :rtype: list[LemaEntri]
    """
    sup = bs4.BeautifulSoup(_normalize_html(laman), "html.parser")
    result_contain = sup.find("div", {"class": "contain"})
    if not isinstance(result_contain, Tag):
        raise TesaurusGalat("Gagal memproses entri: elemen div.contain tidak ditemukan")

    potongan: list[str] = []
    buffer: list[str] = []
    for child in result_contain.children:
        # Text nodes between the result blocks are carried along with the block
        # that follows them, they are not word class boundaries.
        if not isinstance(child, Tag):
            buffer.append(str(child))
            continue
        classes = child.get_attribute_list("class")
        if "result-postag" in classes:
            if "".join(buffer).strip():
                potongan.append("".join(buffer))
            buffer = [str(child)]
        else:
            buffer.append(str(child))
    if "".join(buffer).strip():
        potongan.append("".join(buffer))

    if not potongan:
        raise TesaurusGalat("Gagal memproses entri: laman tidak memiliki hasil")

    return [LemaEntri(bagian, cast(str, kelas_kata)) for bagian in potongan]


class TesaurusAsync(TesaurusAsyncBase):
    """Async Tesaurus Tematis client with a parser that survives the live markup.

    The upstream package parses every response with a plain
    ``BeautifulSoup(..., "html.parser")`` and can no longer scrape the site, see
    :func:`parse_entri` for the reason. Only the scraping step is replaced here;
    HTTP handling, caching and error mapping stay upstream.
    """

    @override
    def _buat_entri(self, laman: str) -> None:
        self._entri.extend(parse_entri(laman, self.kelas_kata))
