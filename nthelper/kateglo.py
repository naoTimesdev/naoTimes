import aiohttp
import logging
from typing import Any, Dict, List, NamedTuple, Union
from enum import Enum

from .utils import __version__, traverse

logger = logging.getLogger("nthelper.kateglo")


class KategloError(Exception):
    pass


class KategloTidakDitemukan(KategloError):
    def __init__(self, kata: str) -> None:
        super().__init__(f"Kata `{kata}` tidak dapat ditemukan")


class KategloTidakAdaRelasi(KategloError):
    def __init__(self, kata: str) -> None:
        super().__init__(f"Tidak ada relasi untuk kata `{kata}`")


class KategloTipe(Enum):
    Sinonim = "s"
    Antonim = "a"
    Turunan = "d"
    Gabungan = "c"
    Peribahasa = "pb"
    Berkaitan = "r"
    TidakDiketahui = "td"


class KategloRelasi(NamedTuple):
    id: Union[str, None]
    tipe: KategloTipe
    kata: str

    def to_dict(self):
        return {"id": self.id, "tipe": self.tipe, "kata": self.kata}


def cherry_pick_safe(dataset: dict, note: str) -> Union[Any, None]:
    """A safe traversal that basically return None if not found.

    :param dataset: dataset to be propagated
    :type dataset: dict
    :param note: the dot notation of the keys
    :type note: str
    :return: content of provided `note` if found.
    :rtype: Union[Any, None]
    """
    try:
        return traverse(dataset, note)
    except (ValueError, KeyError, AttributeError):
        return None


def collect_relations(dataset: Any, tipe: KategloTipe) -> List[KategloRelasi]:
    """Collect type of relations from a dataset.

    :param dataset: data from Kateglo
    :type dataset: Any
    :param tipe: Type of word relations to be matched
    :type tipe: KategloTipe
    :return: A collected relation of the provided type
    :rtype: List[KategloRelasi]
    """
    relasidata: Union[Dict[str, dict], None] = cherry_pick_safe(dataset, tipe.value)
    if not isinstance(relasidata, dict):
        return []
    collected: List[KategloRelasi] = []
    for key, relasi in relasidata.items():
        if not key.isdigit():
            continue
        phrase = cherry_pick_safe(relasi, "related_phrase")
        if phrase is None:
            continue
        uuid = cherry_pick_safe(relasi, "rel_uid")
        if uuid is None:
            uuid = key
        collected.append(KategloRelasi(uuid, tipe, phrase))
    return collected


async def kateglo_relasi(kata: str) -> List[KategloRelasi]:
    """Mencari relasi kata di Kateglo.com

    :param kata: kata yang ingin dicari relasinya
    :type kata: str
    :raises KategloTidakDitemukan: Jika kata tidak ditemukan
    :raises KategloTidakAdaRelasi: Jika tidak ada relasi pada kata tersebut
    :raises KategloError: Error lainnya, biasanya untuk gagal koneksi
    :return: Relasi untuk kata yang dicari
    :rtype: List[KategloRelasi]
    """
    query_params = {"format": "json", "phrase": kata}
    logger.info(f"searching for {kata}")
    async with aiohttp.ClientSession(
        headers={"User-Agent": f"naoTimes/v{__version__} (https://github.com/naoTimesdev)"}
    ) as sesi:
        try:
            async with sesi.get("https://kateglo.com/api.php", params=query_params) as resp:
                if resp.status != 200:
                    logger.error(f"{kata}: Got non-200 code: {resp.status}")
                    raise KategloError(f"Error, Mendapatkan kode status {resp.status} dari API")
                if "application/json" not in resp.headers["content-type"]:
                    logger.warning(
                        f"{kata}: expected JSON data, but got {resp.headers['content-type']} instead"
                    )
                    raise KategloTidakDitemukan(kata)
                res = await resp.json()
        except aiohttp.ClientError:
            logger.error(f"{kata}: failed to fetch to API")
            raise KategloError("Tidak dapat menghubungi API Kateglo untuk mendapatkan hasil.")

    logger.info(f"{kata}: traversing to kateglo relation")
    relasi_kata = cherry_pick_safe(res, "kateglo.relation")

    if relasi_kata is None:
        logger.warning(f"{kata}: failed to fetch relation data")
        raise KategloTidakAdaRelasi(kata)

    antonim = collect_relations(relasi_kata, KategloTipe.Antonim)
    gabungan_kata = collect_relations(relasi_kata, KategloTipe.Gabungan)
    sinonim = collect_relations(relasi_kata, KategloTipe.Sinonim)
    turunan = collect_relations(relasi_kata, KategloTipe.Turunan)
    peribahasa = collect_relations(relasi_kata, KategloTipe.Peribahasa)
    berkaitan = collect_relations(relasi_kata, KategloTipe.Berkaitan)

    bulk_results: List[KategloRelasi] = []
    bulk_results.extend(antonim)
    bulk_results.extend(gabungan_kata)
    bulk_results.extend(sinonim)
    bulk_results.extend(turunan)
    bulk_results.extend(peribahasa)
    bulk_results.extend(berkaitan)
    logger.info(f"{kata}: got {len(bulk_results)} results")
    bulk_results.sort(key=lambda x: x.id)
    return bulk_results
