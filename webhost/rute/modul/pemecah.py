import base64
import json
import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


class Destroyer:
    def __init__(self, sesi: requests.Session):
        self.sesi = sesi
        print('Spawned new Destroyer class.')

    class GagalKomunikasi(Exception):
        def __init__(self, url):
                super().__init__('Gagal berkomunikasi dengan server {}'.format(url))

    def _communicate(self, url, mode="get", **kwargs):
        mode_available = {
            "get": self.sesi.get,
            "post": self.sesi.post
        }
        connect = mode_available.get(mode, self.sesi.get)

        try:
            req = connect(url, **kwargs)
            if req.status_code > 399:
                raise self.GagalKomunikasi(self.url)
        except requests.exceptions.ConnectionError:
            raise self.GagalKomunikasi(self.url)
        except requests.Timeout:
            raise self.GagalKomunikasi(self.url)
        except requests.RequestException:
            raise self.GagalKomunikasi(self.url)
        return req

    def anjay_solver(self):
        sf_id = self.url[self.url.find('?id=')+4:]
        req = self._communicate("https://www.anjay.info/issues-of-model-structure-in-a-geocomputational/", 'post', data={
            "eastsafelink_id": sf_id
        })
        new_url = re.findall(r"\#showlink\"\).*\{var a=(?:'|\")(.*)(?:'|\");.*", req.text)
        if not new_url:
            return self.url
        return new_url[0]

    def teknoku_solver(self):
        sf_id = self.url[self.url.find('?id=')+4:]
        _ = self._communicate(self.url, "get")
        req2 = self._communicate("https://teknoku.me/huawei-mate-30-pro-being-launched-soon/", "post", data={
            "get": sf_id
        })
        new_url = re.findall(r"\#showlink\"\).*\{var a=(?:'|\")(.*)(?:'|\");.*", req2.text)
        if not new_url:
            return self.url
        return new_url[0]

    def div_solver(self):
        req = self._communicate(self.url, 'get')
        sup = BeautifulSoup(req.text, 'html.parser')
        dl_link = sup.find('div', class_='download-link')
        if not dl_link:
            return self.url
        redirect_url = dl_link.find('a')['href']
        try:
            final_url = self.sesi.get(redirect_url).url
        except requests.ConnectionError:
            final_url = redirect_url
        return final_url

    def window_solver(self):
        req = self._communicate(self.url, 'get')
        link = re.search(r";window.location=\"([^\"]+)\";}count--", req.text)
        if not link:
            return self.url
        return link.group(1)

    def short_aw_solver(self):
        req = self._communicate(self.url, 'get')
        sup = BeautifulSoup(req.text, 'html.parser')
        dl_link = sup.find('div', class_='kiri')
        if not dl_link:
            return self.url
        return dl_link.find('a')['href']

    def hightech_solver(self):
        sitexid = self.url[self.url.find('?sitex=')+7:]
        decoded = base64.b64decode(sitexid.encode('utf-8')).decode('utf-8')
        return decoded

    def destroy(self, url: str):
        self.url = url
        warning = False
        while True:
            try:
                if 'anjay.info' in self.url:
                    self.url = self.anjay_solver()
                elif 'teknoku.me' in self.url:
                    self.url  = self.teknoku_solver()
                elif 'ahexa.com' in self.url:
                    self.url = self.div_solver()
                elif 'coeg.in' in self.url:
                    self.url = self.div_solver()
                elif 'siotong' in self.url:
                    self.url = self.div_solver()
                elif 'bucin.net' in self.url:
                    self.url = self.div_solver()
                elif 'greget.space' in self.url:
                    self.url = self.div_solver()
                elif 'tetew.info' in self.url:
                    self.url = self.window_solver()
                elif 'short.awsubs' in self.url:
                    self.url = self.short_aw_solver()
                elif 'hexafile.net' in self.url:
                    self.url = self.window_solver()
                elif 'hightech.web' in self.url:
                    self.url = self.hightech_solver()
                elif 'ouo.io' in self.url:
                    warning = True
                    break
                elif 'kontenajaib.' in self.url:
                    warning = True
                    break
                elif 'metroo.me' in self.url:
                    warning = True
                    break
                elif 'lewat.club' in self.url:
                    warning = True
                    break
                else:
                    break
            except self.GagalKomunikasi:
                print('Failed solving: {}'.format(self.url))
                self.url = ''
                break

        return self.url, self.sesi, warning

class CepatSaji:
    def __init__(self, url, cache_client=None):
        self.url = url
        self.sesi = requests.Session()
        self.sesi.headers.update(
            {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'}
        ) # Chrome 79 UA
        self.cache_client = cache_client
        self.solver = None
        self.solver_type = None
        self.unlocked = False
        self.periksa_url()

    class TidakDidukung(Exception):
        def __init__(self, url):
            super().__init__('URL `{}` tidak didukung.'.format(url))

    class SalahCara(Exception):
        def __init__(self):
            super().__init__('Harap gunakan .pecahkan() untuk memecahkan semua safelink URL.')

    class TidakDitemukan(Exception):
        def __init__(self, url):
            super().__init__('URL `{}` tidak dapat ditemukan (error 404).'.format(url))

    def _communicate(self):
        req = self.sesi.get(self.url)
        if req.status_code != 200:
            if req.status_code == 404:
                raise self.TidakDitemukan(self.url)
            else:
                raise Exception('Terjadi kesalahan internal: error code {}'.format(req.status_code))
        return req

    def _solve_url(self, pemecah: Destroyer, secured_url):
        if self.cache_client:
            _warning_ = False
            cache_url = self.cache_client.get(secured_url)
            if cache_url:
                print('Cache detected, using cache...')
                solved_url = cache_url.decode('utf-8')
            else:
                print('No cache, solving...')
                solved_url, self.sesi, _warning_ = pemecah.destroy(secured_url)
                if solved_url and not _warning_: # Don't cache if empty
                    if solved_url.strip() != secured_url.strip():
                        print('Caching url...')
                        self.cache_client.setex(secured_url, (60*60*24*7), solved_url.encode('utf-8')) # Cache for 7 days
        else:
            print('No cache and no redis server, solving...')
            solved_url, self.sesi, _warning_ = pemecah.destroy(secured_url)
        return solved_url, _warning_

    def _pedanghiu(self):
        """
        DO NOT USE THIS METHOD DIRECTLY
        Use CepatSaji.pecahkan() instead
        """
        if not self.unlocked:
            raise self.SalahCara()
        self.unlocked = False

        def internal_filter(set_data, tipe, dataset, sesi):
            Pemecah = Destroyer(sesi)
            tipe = tipe.replace(
                'Video', ''
            ).replace(
                'Versi', ''
            ).lower().strip()
            li_data = set_data.find_all('li')
            for pos, li in enumerate(li_data, 1):
                data_ = {}
                print('Solving inner set number {}/{}'.format(pos, len(li_data)))
                dn = li.find('strong').text.strip()
                if dn == "MP4H" or dn == "MP4HD":
                    dn = "720"
                elif dn == "FullHD":
                    dn = "1080p"
                url_list = {}
                for url in li.find_all('a'):
                    solved_url, _warning_ = self._solve_url(Pemecah, url['href'].strip())
                    url_txt = url.text.strip()
                    if _warning_:
                        url_txt +=  ' [!]'
                    url_list[url_txt] = solved_url
                data_["format"] = "{} [{}]".format(dn, tipe)
                data_["berkas"] = url_list
                dataset.append(data_)
            return dataset, sesi

        req_web = self._communicate()
        print('Processing data...')
        sup = BeautifulSoup(req_web.text, 'html.parser')
        all_links = sup.find_all('div', class_="download-eps")
        judul_rilisan = sup.find('h1').text.strip()

        dataset = []
        # Solve first one
        first_set = all_links[0]
        first_set_name = first_set.previous_sibling.previous_sibling.text
        first_set_name = first_set_name[first_set_name.rfind('Video'):].strip().replace(u'\xa0', ' ')
        print('Solving set number 1')
        dataset, self.sesi = internal_filter(first_set, first_set_name, dataset, self.sesi)

        # Solve other
        other_set = all_links[1:]
        for n, set_ in enumerate(other_set, 2):
            print('Solving set number {}'.format(n))
            dn = set_.previous_sibling.previous_sibling.text.strip().replace(u'\xa0', ' ')
            dataset, self.sesi = internal_filter(set_, dn, dataset, self.sesi)
        return dataset, judul_rilisan

    def _mcdsubs(self):
        """
        DO NOT USE THIS METHOD DIRECTLY
        Use CepatSaji.pecahkan() instead
        """
        if not self.unlocked:
            raise self.SalahCara()
        self.unlocked = False

        req_web = self._communicate()
        print('Processing data...')
        sup = BeautifulSoup(req_web.text, 'html.parser')
        link_data = sup.find('div', class_="dl-box")
        all_links = link_data.find_all('div', class_='dl-item')
        judul_rilisan = sup.find('h1').text.strip()

        parse_title = [i.text.strip().replace(u'\xa0', ' ') for i in link_data.find_all('div', class_='dl-title')]

        def clean_title(title):
            if '\u2013' in title:
                sbstr = '\u2013'
            else:
                sbstr = '-'
            title = title[title.find(sbstr)+2:]
            reso, fmt = title[title.find('['):].split('.')
            reso = " ".join([i.replace(']', '') for i in reso.split('[')[1:]])
            return "{} ({})".format(reso, fmt)

        dataset = []
        for pos, link in enumerate(parse_title):
            Pemecah = Destroyer(self.sesi)
            data_ = {}
            print('Solving set number {}'.format(pos+1))
            proses = all_links[pos]
            link = clean_title(link)
            links_parsed = {}
            links = proses.find_all('a')
            if links:
                for link_ in links:
                    solved_url, _warning_ = self._solve_url(Pemecah, link_['href'].strip())
                    url_txt = link_.text.strip()
                    if _warning_:
                        url_txt +=  ' [!]'
                    links_parsed[url_txt] = solved_url
            data_['format'] = link
            data_['berkas'] = links_parsed
            dataset.append(data_)
        return dataset, judul_rilisan

    def _koplo(self):
        """
        DO NOT USE THIS METHOD DIRECTLY
        Use CepatSaji.pecahkan() instead
        """
        if not self.unlocked:
            raise self.SalahCara()
        self.unlocked = False

        req_web = self._communicate()
        print('Processing data...')
        sup = BeautifulSoup(req_web.text, 'html.parser')
        data = sup.find_all('div', {'class': 'sorattl title-download'})
        judul_rilisan2 = sup.find('h1').text.strip()

        judul_rilisan = sup.find('h1').text.replace(
            '[END]', ''
        ).replace(
            '[TAMAT]', ''
        ).replace(
            'Episode ', ''
        ).replace(
            'Subtitle Indonesia', ''
        ).strip()

        dataset = []
        for pos, d in enumerate(data, 1):
            data_ = {}
            Pemecah = Destroyer(self.sesi)
            print('Solving set number {}'.format(pos))
            title = d.text.strip().replace(
                'oploverz – ', ''
            ).replace(
                'Episode ', ''
            ).replace(
                'Subtitle Indonesia ', ''
            )
            if 'x265' in title:
                add_back = 'x265 '
                title = title.replace(' x265', '')
            else:
                add_back = 'x264 '
            title = title.replace(
                judul_rilisan, ''
            ).strip()
            try:
                link_data = d.next_sibling.next_sibling.find_all('strong')
            except AttributeError:
                continue
            link_dataset = {}
            for linkd in link_data:
                links = linkd.find_all('a')
                if not links:
                    links = linkd.find_all('del')
                    for ld in links:
                        link_dataset[ld.text.strip()] = ''
                else:
                    for link_ in links:
                        solved_url, _warning_ = self._solve_url(Pemecah, link_['href'].strip())
                        url_txt = link_.text.strip()
                        if _warning_:
                            url_txt +=  ' [!]'
                        link_dataset[url_txt] = solved_url
            data_['format'] = add_back + title
            data_['berkas'] = link_dataset
            dataset.append(data_)

        return dataset, judul_rilisan2

    def _anitoki(self):
        """
        DO NOT USE THIS METHOD DIRECTLY
        Use CepatSaji.pecahkan() instead
        """
        if not self.unlocked:
            raise self.SalahCara()
        self.unlocked = False

        req_web = self._communicate()
        print('Processing data...')
        sup = BeautifulSoup(req_web.text, 'html.parser')
        link_data = sup.find_all('div', class_="smokeddl")
        judul_rilisan = sup.find('h1').text.strip()

        dataset = []
        for pos, data in enumerate(link_data):
            Pemecah = Destroyer(self.sesi)
            print('Solving set number {}'.format(pos+1))
            format_ = data.find(
                'div', class_='smokettl'
            ).text.strip().replace(
                'Download ', ''
            ).replace(
                judul_rilisan + ' ', ''
            )
            links_dataset = data.find_all('div', class_='smokeurl')
            for link_data in links_dataset:
                data_ = {}
                links_parsed = {}
                reso = link_data.find('strong')
                if not reso:
                    continue
                reso = reso.text.strip().lower()
                proper_title = "{} {}".format(reso, format_)
                links = link_data.find_all('a')
                for link in links:
                    solved_url, _warning_ = self._solve_url(Pemecah, link['href'].strip())
                    url_txt = link.text.strip()
                    if _warning_:
                        url_txt +=  ' [!]'
                    links_parsed[url_txt] = solved_url
                data_['format'] = proper_title
                data_['berkas'] = links_parsed
                dataset.append(data_)

        return dataset, judul_rilisan

    def _kuso(self):
        """
        DO NOT USE THIS METHOD DIRECTLY
        Use CepatSaji.pecahkan() instead
        """
        if not self.unlocked:
            raise self.SalahCara()
        self.unlocked = False

        req_web = self._communicate()
        print('Processing data...')
        sup = BeautifulSoup(req_web.text, 'html.parser')
        data = sup.find_all('div', class_="smokeurl")
        judul_rilisan = sup.find('h1').text.strip()

        dataset = []
        for pos, d in enumerate(data):
            data_ = {}
            Pemecah = Destroyer(self.sesi)
            print('Solving set number {}'.format(pos+1))
            namae = d.find('strong').text.strip().lower()
            links = d.find_all('a')
            links_parsed = {}
            for link in links:
                solved_url, _warning_ = self._solve_url(Pemecah, link['href'].strip())
                url_txt = link.text.strip()
                if _warning_:
                    url_txt +=  ' [!]'
                links_parsed[url_txt] = solved_url
            data_['format'] = namae
            data_['berkas'] = links_parsed
            dataset.append(data_)

        return dataset, judul_rilisan

    def _neonime(self):
        """
        DO NOT USE THIS METHOD DIRECTLY
        Use CepatSaji.pecahkan() instead
        """
        if not self.unlocked:
            raise self.SalahCara()
        self.unlocked = False

        def split_everything(sup: BeautifulSoup):
            final_data = []
            first_data = sup.find('ul').find('li')
            text = str(first_data)
            for geniter in first_data.next_siblings:
                if geniter.name != "ul":
                    final_data.append(text)
                    text = ''
                text += str(geniter)
            final_data.append(text)
            parsed_data = [BeautifulSoup(i, 'html.parser') for i in final_data]
            return parsed_data

        req = self._communicate()
        sup = BeautifulSoup(req.text, 'html.parser')
        data_head = sup.find('h2', class_="link-download")
        data_main = split_everything(data_head.next_sibling)

        episode = sup.find('h1').text.strip()
        try:
            judul_anime = sup.find(
                'div', class_="imagen"
            ).find('img')['alt'].strip()
        except:
            judul_anime = ''
        judul_rilisan = "{} {}".format(
            judul_anime, episode
        ).strip()
        
        dataset = []
        for data in data_main:
            Pemecah = Destroyer(self.sesi)
            tipe = data.find('li').text.strip()
            ul_stuff = data.find_all('ul')
            for ul in ul_stuff:
                data_ = {}
                label = ul.find('li').find('label').text.strip()
                if 'OP' in label or 'ED' in label:
                    continue
                if tipe not in label:
                    label = "{} {}".format(tipe, label)
                all_links = {}
                for link in ul.find('li').find_all('a'):
                    solved_url, _warning_ = self._solve_url(Pemecah, link['href'].strip())
                    url_txt = link.text.strip()
                    if _warning_:
                        url_txt +=  ' [!]'
                    all_links[url_txt] = solved_url
                data_['format'] = label
                data_['berkas'] = all_links
                dataset.append(data_)

        return dataset, judul_rilisan

    def _moenime(self):
        """
        moenime.id

        DO NOT USE THIS METHOD DIRECTLY
        Use CepatSaji.pecahkan() instead
        """
        if not self.unlocked:
            raise self.SalahCara()
        self.unlocked = False

        index_id = self.url.find('#')
        if index_id == -1:
            raise self.TidakDitemukan(self.url)
        find_ep_id = self.url[index_id+1:]

        req = self._communicate()
        sup = BeautifulSoup(req.text, 'html.parser')

        data_awal = sup.find(
            'td', {
                'id': find_ep_id
            }
        )
        judul_rilisan = data_awal.find(
            'span'
        ).text.strip()[:-2].strip()
        data_all = data_awal.parent.parent.find_all(
            'table'
        )[0].find_all(
            'tr'
        )

        chunked_set = [data_all[i:i + 2] for i in range(0, len(data_all), 2)]

        dataset = []
        for pos, chunks in enumerate(chunked_set):
            print('Solving set number {}'.format(pos+1))
            Pemecah = Destroyer(self.sesi)
            data_ = {}
            if len(chunks) < 2:
                head = chunks[0].text
                head = head[:head.rfind('(')-2].strip()
                data_['format'] = head
                data_['berkas'] = {}
                dataset.append(data_)
                continue

            head, link_data = chunks
            head = head.text
            head = head[:head.rfind('(')-2].strip()
            
            link_set = link_data.find_all('a')
            links = {}
            for link in link_set:
                solved_url, _warning_ = self._solve_url(Pemecah, link['href'].strip())
                url_txt = link.text.strip()
                if _warning_:
                    url_txt +=  ' [!]'
                links[url_txt] = solved_url
            data_['format'] = head
            data_['berkas'] = links
            dataset.append(data_)

        return dataset, judul_rilisan

    def _unknown(self):
        raise self.TidakDidukung(self.url)

    def periksa_url(self):
        supported_url = {
            "samehadaku.tv": [self._pedanghiu, 'samehadaku'],
            "riie.net": [self._pedanghiu, 'riie'],
            "awsubs.tv": [self._mcdsubs, 'awsubs'],
            "oploverz.in": [self._koplo, 'oploverz'],
            "anitoki.com": [self._anitoki, 'anitoki'],
            "kusonime.com": [self._kuso, 'kusonime'],
            "neonime.org": [self._neonime, 'neonime'],
            "moenime.id": [self._moenime, 'moenime']
        }

        domain_name = urlparse(self.url).netloc.replace('www.', '')

        self.solver, self.solver_type = supported_url.get(domain_name, [self._unknown, None])

    def pecahkan(self):
        """Pecahkan pengaman semua link video fastsub yang didukung"""
        self.unlocked = True
        print('Solving {} link...'.format(self.solver_type))
        url_dict, judul_rilisan = self.solver()
        return url_dict, judul_rilisan, "Sukses"


if __name__ == "__main__":
    # Samehada
    #cs = CepatSaji("https://kusonime.com/yuki-no-hana-2019-bd-subtitle-indonesia/")
    #data = cs.pecahkan()
    #print(json.dumps(data, indent=2))
    redis_server = None#redis.StrictRedis(host='localhost', port=6379)

    sesi = requests.Session()
    sesi.headers.update(
        {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'}
    )

    # Anitoket
    cs = CepatSaji("https://www.oploverz.in/one-piece-stampede-subtitle-indonesia/", redis_server)
    data = cs.pecahkan()
    #print(data)
    print(json.dumps(data, indent=2))

    # Oplo
    #cs = CepatSaji("https://www.oploverz.in/boku-no-hero-academia-season-4-episode-11-subtitle-indonesia/")
    #data = cs.pecahkan()
    #print(json.dumps(data, indent=2))
