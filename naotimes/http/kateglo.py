"""
A wrapper of Kateglo, an ID thesaurus dictionary.

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

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import quote as urlquote

import aiohttp

from ..utils import traverse
from ..version import __version__

__all__ = ("KategloError", "KategloTidakAdaRelasi", "KategloTidakDitemukan", "KategloTipe", "kateglo_relasi")
logger = logging.getLogger("naoTimes.Kateglo")


class KategloError(Exception):
    pass


class KategloTidakDitemukan(KategloError):
    def __init__(self, kata: str) -> None:
        super().__init__(f"Kata `{kata}` tidak dapat ditemukan")


class KategloTidakAdaRelasi(KategloError):
    def __init__(self, kata: str) -> None:
        super().__init__(f"Tidak ada relasi untuk kata `{kata}`")


class KategloTipe(Enum):
    Sinonim = "sinonim"
    Antonim = "antonim"
    Turunan = "d"
    Gabungan = "c"
    Peribahasa = "pb"
    Berkaitan = "r"
    TidakDiketahui = "td"


@dataclass
class KategloRelasi:
    id: str | None
    tipe: KategloTipe
    kata: str

    def to_dict(self):
        return {"id": self.id, "tipe": self.tipe, "kata": self.kata}


def cherry_pick_safe(dataset: dict[str, Any] | list[Any] | None, note: str) -> Any | None:
    """A safe traversal that basically return None if not found.

    :param dataset: dataset to be propagated
    :type dataset: dict
    :param note: the dot notation of the keys
    :type note: str
    :return: content of provided `note` if found.
    :rtype: Union[Any, None]
    """
    if dataset is None:
        return None
    try:
        return traverse(dataset, note)
    except (ValueError, KeyError, AttributeError, TypeError):
        return None


def collect_relations(dataset: Any, tipe: KategloTipe) -> list[KategloRelasi]:
    """Collect type of relations from a dataset.

    :param dataset: data from Kateglo
    :type dataset: Any
    :param tipe: Type of word relations to be matched
    :type tipe: KategloTipe
    :return: A collected relation of the provided type
    :rtype: List[KategloRelasi]
    """
    collected: list[KategloRelasi] = []

    # The current API returns relation phrases as lists. Subentries are objects
    # with an ``id`` and ``entri``; thesaurus links are plain strings.
    relasidata = dataset if isinstance(dataset, list) else cherry_pick_safe(dataset, tipe.value)
    if isinstance(relasidata, list):
        for index, relasi in enumerate(relasidata):
            if isinstance(relasi, str):
                collected.append(KategloRelasi(None, tipe, relasi))
                continue
            if not isinstance(relasi, dict):
                continue
            phrase = cherry_pick_safe(relasi, "entri")
            if phrase is None:
                phrase = cherry_pick_safe(relasi, "related_phrase")
            if not isinstance(phrase, str):
                continue
            uuid = cherry_pick_safe(relasi, "id")
            if uuid is None:
                uuid = cherry_pick_safe(relasi, "rel_uid")
            collected.append(KategloRelasi(str(uuid) if uuid is not None else str(index), tipe, phrase))
        return collected

    # Keep support for the previous API shape, where each relation type was a
    # map of numeric keys to ``related_phrase`` records.
    if not isinstance(relasidata, dict):
        return collected
    for key, relasi in relasidata.items():
        if not key.isdigit():
            continue
        phrase = cherry_pick_safe(relasi, "related_phrase")
        if not isinstance(phrase, str):
            continue
        uuid = cherry_pick_safe(relasi, "rel_uid")
        if uuid is None:
            uuid = key
        collected.append(KategloRelasi(str(uuid), tipe, phrase))
    return collected


async def kateglo_relasi(kata: str) -> list[KategloRelasi]:
    """Mencari relasi kata di Kateglo.com

    :param kata: kata yang ingin dicari relasinya
    :type kata: str
    :raises KategloTidakDitemukan: Jika kata tidak ditemukan
    :raises KategloTidakAdaRelasi: Jika tidak ada relasi pada kata tersebut
    :raises KategloError: Error lainnya, biasanya untuk gagal koneksi
    :return: Relasi untuk kata yang dicari
    :rtype: List[KategloRelasi]
    """
    logger.info(f"searching for {kata}")
    kata_encoded = urlquote(kata)
    async with aiohttp.ClientSession(
        headers={"User-Agent": f"naoTimes/v{__version__} (https://github.com/naoTimesdev)"}
    ) as sesi:
        try:
            async with sesi.get(
                f"https://kateglo.org/api/publik/kamus/detail/{kata_encoded}", params={"limit": "20"}
            ) as resp:
                if resp.status != 200:
                    logger.error(f"{kata}: Got non-200 code: {resp.status}")
                    raise KategloError(f"Error, Mendapatkan kode status {resp.status} dari API")
                if "application/json" not in resp.headers["content-type"]:
                    logger.warning(f"{kata}: expected JSON data, but got {resp.headers['content-type']} instead")
                    raise KategloTidakDitemukan(kata)
                res = await resp.json()
        except aiohttp.ClientError:
            logger.error(f"{kata}: failed to fetch to API")
            raise KategloError("Tidak dapat menghubungi API Kateglo untuk mendapatkan hasil.")

    logger.info(f"{kata}: traversing to kateglo relation")
    entri = cherry_pick_safe(res, "entri")
    if isinstance(entri, list) and not entri:
        logger.warning(f"{kata}: word was not found")
        raise KategloTidakDitemukan(kata)

    relasi_kata = cherry_pick_safe(res, "tesaurus")
    if relasi_kata is None and not isinstance(entri, list):
        logger.warning(f"{kata}: failed to fetch relation data")
        raise KategloTidakAdaRelasi(kata)

    antonim = collect_relations(relasi_kata, KategloTipe.Antonim)
    gabungan_kata = collect_relations(relasi_kata, KategloTipe.Gabungan)
    sinonim = collect_relations(relasi_kata, KategloTipe.Sinonim)
    turunan = collect_relations(relasi_kata, KategloTipe.Turunan)
    peribahasa = collect_relations(relasi_kata, KategloTipe.Peribahasa)
    berkaitan = collect_relations(relasi_kata, KategloTipe.Berkaitan)

    # In the current response schema, derived forms, compounds, and proverbs
    # are attached to each entry instead of the top-level thesaurus object.
    if isinstance(entri, list):
        for data_entri in entri:
            subentri = cherry_pick_safe(data_entri, "subentri")
            gabungan_kata.extend(collect_relations(cherry_pick_safe(subentri, "gabungan"), KategloTipe.Gabungan))
            turunan.extend(collect_relations(cherry_pick_safe(subentri, "turunan"), KategloTipe.Turunan))
            peribahasa.extend(collect_relations(cherry_pick_safe(subentri, "peribahasa"), KategloTipe.Peribahasa))

    bulk_results: list[KategloRelasi] = []
    bulk_results.extend(antonim)
    bulk_results.extend(gabungan_kata)
    bulk_results.extend(sinonim)
    bulk_results.extend(turunan)
    bulk_results.extend(peribahasa)
    bulk_results.extend(berkaitan)
    logger.info(f"{kata}: got {len(bulk_results)} results")
    bulk_results.sort(key=lambda x: x.id or "")
    return bulk_results
