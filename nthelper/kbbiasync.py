# Based on kbbi-python 0.4.2

import asyncio
import re
from urllib.parse import quote

import aiohttp
import kbbi
from bs4 import BeautifulSoup
from kbbi import (  # noqa: F401
    BatasSehari,
    GagalAutentikasi,
    TerjadiKesalahan,
    TidakDitemukan,
)

from .utils import sync_wrap


class GagalKoneksi(kbbi.Galat):
    """Galat ketika laman tidak ditemukan dalam KBBI."""

    def __init__(self):
        super().__init__("Tidak dapat terhubung ke KBBI, kemungkinan website down.")


class AutentikasiKBBI:
    host = "https://kbbi.kemdikbud.go.id"
    lokasi = "Account/Login"

    def __init__(self, posel=None, sandi=None):
        self.sesi = aiohttp.ClientSession()
        self.posel = posel
        self.sandi = sandi

    async def ambil_cookies(self) -> str:
        cookie = self.sesi.cookie_jar.filter_cookies("https://kbbi.kemdikbud.go.id/")
        final_cookie = cookie[".AspNet.ApplicationCookie"].value
        await self.sesi.close()
        return final_cookie

    async def __ambil_token(self):
        async with self.sesi.get(f"{self.host}/{self.lokasi}") as resp:
            laman = await resp.text()
        token = re.search(r"<input name=\"__RequestVerificationToken\".*value=\"(.*)\" />", laman,)
        if not token:
            raise kbbi.TerjadiKesalahan()
        return token.group(1)

    async def autentikasi(self):
        token = await self.__ambil_token()
        payload = {
            "__RequestVerificationToken": token,
            "Posel": self.posel,
            "KataSandi": self.sandi,
            "IngatSaya": True,
        }
        try:
            async with self.sesi.post(f"{self.host}/{self.lokasi}", data=payload) as resp:
                await resp.text()
                final_url = str(resp.url)
        except aiohttp.ClientConnectionError:
            raise GagalKoneksi()
        except aiohttp.ClientError:
            raise GagalKoneksi()
        except aiohttp.ClientTimeout:
            raise GagalKoneksi()
        except TimeoutError:
            raise GagalKoneksi()
        if "Beranda/Error" in final_url:
            raise TerjadiKesalahan()
        if "Account/Login" in final_url:
            raise GagalAutentikasi()


class KBBI:
    """Sebuah laman dalam KBBI daring."""

    host = "https://kbbi.kemdikbud.go.id"

    def __init__(self, kueri, asp_cookies=None):
        """Membuat objek KBBI baru berdasarkan kueri yang diberikan.
        :param kueri: Kata kunci pencarian
        :type kueri: str
        :param auth: objek AutentikasiKBBI
        :type auth: AutentikasiKBBI
        """
        self._bs4 = sync_wrap(BeautifulSoup)

        self.nama = kueri
        self.entri = []
        self.saran_entri = []
        self._init_lokasi()
        self._init_sesi(asp_cookies)

    async def cari(self):
        try:
            req = await self.sesi.get(f"{self.host}/{self.lokasi}")
        except aiohttp.ClientConnectionError:
            raise GagalKoneksi()
        except aiohttp.ClientError:
            raise GagalKoneksi()
        except aiohttp.ClientTimeout:
            raise GagalKoneksi()
        except TimeoutError:
            raise GagalKoneksi()
        laman = await req.text()
        await self._cek_autentikasi(laman)
        await self._cek_galat(req, laman)
        await self._init_entri(laman)

    async def tutup(self):
        await self.sesi.close()

    def _init_sesi(self, asp_cookies):
        if asp_cookies:
            self.sesi = aiohttp.ClientSession(cookies={".AspNet.ApplicationCookie": asp_cookies})
        else:
            self.sesi = aiohttp.ClientSession()

    async def _cek_autentikasi(self, laman):
        self.terautentikasi = "loginLink" not in laman

    async def cek_auth(self):
        is_auth = False
        async with self.sesi.get(self.host) as resp:
            res = await resp.text()
            is_auth = "loginLink" not in res
        return is_auth

    def _init_lokasi(self):
        kasus_khusus = [
            "." in self.nama,
            "?" in self.nama,
            self.nama.lower() == "nul",
            self.nama.lower() == "bin",
        ]
        if any(kasus_khusus):
            self.lokasi = f"Cari/Hasil?frasa={quote(self.nama)}"
        else:
            self.lokasi = f"entri/{quote(self.nama)}"

    async def _cek_galat(self, req, laman):
        if "Beranda/Error" in str(req.url):
            raise kbbi.TerjadiKesalahan()
        if "Beranda/BatasSehari" in str(req.url):
            raise kbbi.BatasSehari()
        if "Entri tidak ditemukan." in laman:
            await self._init_saran(laman)
            raise kbbi.TidakDitemukan(self.nama)

    async def _init_saran(self, laman):
        if "Berikut beberapa saran entri lain yang mirip." not in laman:
            return
        sup = await self._bs4(laman, "html.parser")
        self.saran_entri = [saran.text.strip() for saran in sup.find_all(class_="col-md-3")]

    async def _init_entri(self, laman):
        sup = await self._bs4(laman, "html.parser")
        estr = ""
        label = sup.find("hr").next_sibling
        while not (label.name == "hr" and label.get("style") is None):
            if label.name == "h2":
                if label.get("style") == "color:gray":  # Lampiran
                    label = label.next_sibling
                    continue
                if estr:
                    self.entri.append(kbbi.Entri(estr, self.terautentikasi))
                    estr = ""
            estr += str(label).strip()
            label = label.next_sibling
        self.entri.append(kbbi.Entri(estr, self.terautentikasi))

    def serialisasi(self, fitur_pengguna=True):
        """Mengembalikan hasil serialisasi objek KBBI ini.
        :returns: Dictionary hasil serialisasi
        :rtype: dict
        """
        kbbi = {
            "pranala": f"{self.host}/{self.lokasi}",
            "entri": [entri.serialisasi(fitur_pengguna) for entri in self.entri],
        }
        if self.terautentikasi and fitur_pengguna and not self.entri:
            kbbi["saran_entri"] = self.saran_entri
        return kbbi

    def __str__(self, contoh=True, terkait=True, fitur_pengguna=True):
        return "\n\n".join(entri.__str__(contoh, terkait, fitur_pengguna) for entri in self.entri)

    def __repr__(self):
        return f"<KBBI: {self.nama}>"


if __name__ == "__main__":
    import json

    loop = asyncio.get_event_loop()

    cookies = ""  # noqa: E501
    # auth = AutentikasiKBBI("", "")
    # loop.run_until_complete(auth.autentikasi())
    # cookie = loop.run_until_complete(auth.ambil_cookies())
    # print(cookie)
    kb = KBBI("idola", cookies)
    loop.run_until_complete(kb.cari())
    res = kb.serialisasi()
    loop.run_until_complete(kb.sesi.close())
    print(res)
    print(json.dumps(res, indent=2, ensure_ascii=False))
