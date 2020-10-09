# Based on kbbi-python 0.4.2

import asyncio
import re
from datetime import datetime, timezone
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

__NT_UA__ = "naoTimes/2.0.1a (https://github.com/noaione/naoTimes)"


class GagalKoneksi(kbbi.Galat):
    """Galat ketika laman tidak ditemukan dalam KBBI."""

    def __init__(self):
        super().__init__("Tidak dapat terhubung ke KBBI, kemungkinan website down.")


class AutentikasiKBBI:
    host = "https://kbbi.kemdikbud.go.id"
    lokasi = "Account/Login"

    def __init__(self, posel=None, sandi=None):
        self.sesi = aiohttp.ClientSession(headers={"User-Agent": __NT_UA__})
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
        except TimeoutError:
            raise GagalKoneksi()
        if "Beranda/Error" in final_url:
            raise TerjadiKesalahan()
        if "Account/Login" in final_url:
            raise GagalAutentikasi()


class KBBI:
    """Sebuah laman dalam KBBI daring."""

    host = "https://kbbi.kemdikbud.go.id"

    def __init__(self, asp_cookies=None):
        """Membuat objek KBBI baru berdasarkan kueri yang diberikan.
        :param kueri: Kata kunci pencarian
        :type kueri: str
        :param auth: objek AutentikasiKBBI
        :type auth: AutentikasiKBBI
        """
        self._bs4 = sync_wrap(BeautifulSoup)

        self.entri = []
        self.saran_entri = []
        self.terautentikasi = False
        self._init_sesi(asp_cookies)

        self._username = ""
        self._password = ""
        self._expiry = 0
        self._cookies = asp_cookies

    async def cari(self, kueri):
        self.nama = kueri
        self.entri = []
        self.saran_entri = []
        self._init_lokasi()
        try:
            req = await self.sesi.get(f"{self.host}/{self.lokasi}")
        except aiohttp.ClientConnectionError:
            raise GagalKoneksi()
        except aiohttp.ClientError:
            raise GagalKoneksi()
        except TimeoutError:
            raise GagalKoneksi()
        laman = await req.text()
        if req.status != 200:
            if req.status == 500:
                raise TerjadiKesalahan()
            elif req.status == 404:
                raise TidakDitemukan(self.nama)
            else:
                raise kbbi.Galat(
                    f"Terjadi kesalahan ketika berkomunikasi dengan KBBI, status code: {req.status}"
                )
        await self._cek_autentikasi(laman)
        await self._cek_galat(req, laman)
        await self._init_entri(laman)

    async def tutup(self):
        await self.sesi.close()

    def _init_sesi(self, asp_cookies):
        if asp_cookies:
            self.sesi = aiohttp.ClientSession(
                cookies={".AspNet.ApplicationCookie": asp_cookies}, headers={"User-Agent": __NT_UA__}
            )
        else:
            self.sesi = aiohttp.ClientSession(headers={"User-Agent": __NT_UA__})

    def set_autentikasi(self, username=None, password=None, cookie=None, expiry=None):
        if username is not None:
            self._username = username
        if password is not None:
            self._password = password
        if cookie is not None:
            self._cookies = cookie
        if expiry is not None:
            self._expiry = expiry

    async def reset_connection(self):
        await self.tutup()
        self._init_sesi(self._cookies)

    @property
    def get_cookies(self):
        return {"cookie": self._cookies, "expires": self._expiry}

    async def reautentikasi(self):
        """Autentikasi ulang."""
        auth_kbbi = AutentikasiKBBI(self._username, self._password)
        await auth_kbbi.autentikasi()
        sesi_baru = await auth_kbbi.ambil_cookies()
        await self.tutup()
        self._init_sesi(sesi_baru)
        self._cookies = sesi_baru
        self._expiry = int(round(datetime.now(tz=timezone.utc).timestamp() + (15 * 24 * 60 * 60)))

    async def _cek_autentikasi(self, laman):
        self.terautentikasi = "loginLink" not in laman

    async def cek_auth(self):
        is_auth = False
        async with self.sesi.get(self.host) as resp:
            res = await resp.text()
            is_auth = "loginLink" not in res
        self.terautentikasi = is_auth
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


if __name__ == "__main__":
    import json

    loop = asyncio.get_event_loop()

    kb = KBBI()
    loop.run_until_complete(kb.cari("khayal"))
    res = kb.serialisasi()
    loop.run_until_complete(kb.sesi.close())
    print(res)
    print(json.dumps(res, indent=2, ensure_ascii=False))
