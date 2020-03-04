from urllib.parse import quote_plus

import requests


class SauceNAO:
    """
    A wrapper for SauceNAO API
    ------------------------------

    A simple wrapper that wrap around the SauceNAO API
    Designed specifically for my own personal usage
    
    `Version 1.0`

    Internal function
    ------------------

    1. .get_sauce(data)
    `Give the raw dry spaghetti (URL) a good perfect grade sauce`
    Will `:return:` a list of hand-picked sauce.
    To modify the minimum similarity or confidence, you can use the `minsim` attribute

    Usage
    ------

    .. code-block:: python3

        import json

        sn = SauceNAO()
        result = sn.get_sauce("your url")
        # or
        data = open('img', 'rb').read()
        result = sn.get_sauce(data)

        print(json.dumps(result, indent=2))
    """
    def __init__(self, minsim=57.5):
        """
        Initialize the class to start using the sauce finder

        :param url: str: your image url
        :param minsim: float: the minimum confidence/similarity

        :return: SauceNAO ready to use class
        """
        self.api_key = "PLEASECHANGETHIS"
        if not self.api_key:
            raise ValueError('saucenao.py: please change api_key in rute/modul/saucenao.py file with your api_key.')
        if self.api_key == "PLEASECHANGETHIS":
            raise ValueError('saucenao.py: please change api_key in rute/modul/saucenao.py file with your api_key.')
        self.minsim = minsim

    def __format_booru(self, results_data: dict, headers_data: dict, key_id: str) -> tuple:
        """
        A generic booru type website formatter
        SauceNAO return the same format for all the booru website,
        so this was made as the general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API
        :param key_id: str: the string ID or identifier for every booru website (suffixed with `_id`)

        :return: a tuple containing `title`, `extra_info`, and `source`
        :rtype: tuple
        """
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]

        title = ""
        if "creator" in results_data:
            title += "[{}] ".format(results_data['creator'])
        if "material" in results_data:
            title += results_data['material'] + ' '
        if "characters" in results_data:
            if title[-1] != ',':
                title = title[:-1] + ', '
            title += results_data['characters'] + ' '
        if key_id in results_data:
            title += "({})".format(results_data[key_id])
        title = title.rstrip()

        if not title:
            title = headers_data['index_name']

        return title, {}, source

    def __format_yandere(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for yande.re website
        using `.__format_booru` general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s = self.__format_booru(results_data, headers_data, 'yandere_id')
        return t, ei, s, 'yande.re'

    def __format_danbooru(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for danbooru.donmai.us website
        using `.__format_booru` general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s = self.__format_booru(results_data, headers_data, 'danbooru_id')
        return t, ei, s, 'danbooru'

    def __format_gelbooru(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for gelbooru website
        using `.__format_booru` general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s = self.__format_booru(results_data, headers_data, 'gelbooru_id')
        return t, ei, s, 'gelbooru'

    def __format_e621(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for e621.net website
        using `.__format_booru` general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s = self.__format_booru(results_data, headers_data, 'e621_id')
        return t, ei, s, 'e621'

    def __format_sankaku(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for sankakucomplex website
        using `.__format_booru` general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s = self.__format_booru(results_data, headers_data, 'sankaku_id')
        return t, ei, s, 'sankaku'

    def __format_idolcomplex(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for idol.sankakucomplex website
        using `.__format_booru` general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s = self.__format_booru(results_data, headers_data, 'idol_id')
        return t, ei, s, 'idolcomplex'

    def __format_konachan(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for konachan.net website
        using `.__format_booru` general function

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s = self.__format_booru(results_data, headers_data, 'konachan_id')
        return t, ei, s, 'konachan'

    def __format_anidb(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for anime (using anidb)
        Also a wrapper for hanime one too

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        extra_info = {}
        if "source" in results_data:
            title += results_data['source']
            if "part" in results_data:
                title += " - Episode {0}".format(str(results_data['part']).zfill(2))
            if "anidb_aid" in results_data:
                title += " (anidb-{})".format(results_data['anidb_aid'])
        if "est_time" in results_data:
            extra_info['timestamp'] = results_data['est_time']
        title = title.rstrip()
        if not title:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, extra_info, source, 'anidb'

    def __format_hanime(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for H-Anime
        using `.__format_anidb` function since it's the same type

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, ei, s, _ = self.__format_anidb(results_data, headers_data)
        return t, ei, s, 'anidb-hanime'

    def __format_hmisc(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for H-Misc (NHentai and other doujinshi general media :D)

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "eng_name" in results_data:
            title = results_data['eng_name']
            source = "https://nhentai.net/search?q={}".format(quote_plus(title))
        elif "jp_name" in results_data:
            title = results_data['jp_name']
            source = "https://nhentai.net/search?q={}".format(quote_plus(title))
        else:
            title = headers_data['index_name']
            source = "https://nhentai.net/"
        return title, {}, source, "nhentai"

    def __format_hmagz(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for H-Magazine

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "title" in results_data:
            title += results_data['title']
            if "part" in results_data:
                title += ' {}'.format(results_data['part'])
            if "date" in results_data:
                title += ' ({})'.format(results_data['date'])
        if not title:
            title = headers_data['index_name']
        return title, {}, "", "h-magazine"

    def __format_hgcg(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for H-CG Game

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "company" in results_data:
            title += "[{}] ".format(results_data["company"])
        if "title" in results_data:
            title += results_data['title']
            if "getchu_id" in results_data:
                title += ' (getchu-{})'.format(results_data['getchu_id'])
        if not title:
            title = headers_data['index_name']
        return title, {}, "", "h-game.cg"

    def __format_pixiv(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for pixiv website

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "member_name" in results_data:
            title += "[{}] ".format(results_data['member_name'])
        if "title" in results_data:
            title += results_data['title'] + ' '
        if "pixiv_id" in results_data:
            title += "({})".format(results_data["pixiv_id"])
        title = title.rstrip()
        if not title:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, {}, source, 'pixiv'

    def __format_pixiv_historical(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for pixiv except historical
        Using `.__format_pixiv` since it's the same type

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        t, _, s, _ = self.__format_pixiv(results_data, headers_data)
        return t, {}, s, 'pixiv.historical'

    def __format_imdb(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for Shows and Movie (Western and non-weebs)

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        extra_info = {}
        if "source" in results_data:
            title += results_data['source']
            if "part" in results_data:
                title += " - Episode {0:02d}".format(results_data['part'])
            if "imdb_id" in results_data:
                title += " (imdb-{})".format(results_data['imdb_id'])
        if "est_time" in results_data:
            extra_info['timestamp'] = results_data['est_time']
        title = title.rstrip()
        if not title:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, extra_info, source, 'imdb'

    def __format_seiga(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for NicoNico Seiga (Comic/Fanart Website)

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "member_name" in results_data:
            title += "[{}] ".format(results_data['member_name'])
        if "title" in results_data:
            title += results_data['title']
            if "seiga_id" in results_data:
                title += " (im{})".format(results_data['seiga_id'])
        else:
            title = headers_data['index_name']

        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        
        return title, "", source, "niconico.seiga"

    def __format_madokami(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for Madokami (Mainly manga)

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "source" in results_data:
            title += "{}".format(results_data['source'])
            if "part" in results_data:
                title += " - {}".format(results_data['part'])
            if "mu_id" in results_data:
                title += " (mu-{})".format(results_data["mu_id"])
        else:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, "", source, "madokami"

    def __format_mangadex(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for MangaDex.org website

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "artist" in results_data:
            title += "[{}] ".format(results_data['artist'])
        elif "author" in results_data:
            title += "[{}] ".format(results_data['author'])
        if "source" in results_data:
            title += "{}".format(results_data['source'])
            if "part" in results_data:
                title += results_data['part']
            if "md_id" in results_data:
                title += " (md-{})".format(results_data["md_id"])
        else:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, "", source, "mangadex"

    def __format_drawr(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for drawr website

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "member_name" in results_data:
            title += "[{}] ".format(results_data['member_name'])
        if "title" in results_data:
            title += results_data['title']
            if "drawr_id" in results_data:
                title += " (drawr-{})".format(results_data['drawr_id'])
        if not title:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, "", source, "mangadex"

    def __format_bcynet(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for bcy.net website
        Used for the cosplayer part and illustration part

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "member_name" in results_data:
            title += "[{}] ".format(results_data["member_name"])
        if "title" in results_data:
            title += results_data['title']
            if "bcy_id" in results_data:
                title += " (bcy-{})".format(results_data['bcy_id'])
        if not title:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        extra = "unknown"
        if 'bcy_type' in results_data:
            extra = results_data['bcy_type']
        return title, {}, source, 'bcy.{}'.format(extra)

    def __format_deviantart(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for deviantArt website

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "author_name" in results_data:
            title += "[{}] ".format(results_data["author_name"])
        if "title" in results_data:
            title += results_data['title']
            if "da_id" in results_data:
                title += " ({})".format(results_data['da_id'])
        if not title:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, {}, source, 'deviantart'

    def __format_pawoo(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for pawoo website

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = ""
        if "pawoo_user_acct" in results_data:
            title = "[{}] ".format(results_data["pawoo_user_acct"])
        elif "pawoo_user_username" in results_data:
            title = "[{}] ".format(results_data["pawoo_user_username"])
        if "pawoo_id" in results_data:
            title += "{}".format(results_data['pawoo_id'])
        if not title:
            title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, {}, source, 'pawoo'

    def __format_generic(self, results_data: dict, headers_data: dict) -> tuple:
        """
        Formatter for other website that I don't know how to parse
        A generic one using index_name from headers

        :param results_data: dict: a dictionary of `data` from the SauceNAO API
        :param headers_data: dict: a dictionary of `header` from the SauceNAO API

        :return: a tuple containing `title`, `extra_info`, `source`, and `website_name`
        :rtype: tuple
        """
        title = headers_data['index_name']
        source = ''
        if "ext_urls" in results_data:
            if results_data['ext_urls']:
                source = results_data['ext_urls'][0]
        return title, {}, source, 'generic'

    def __build_results(self, results: dict) -> list:
        """
        Main formatter command for all the website that I know
        Can return empty list if there's nothing that exceed the minimum threshold/confidence

        :param results: dict: a dictionary from the SauceNAO API answer

        :return: a list that exceed the minimum threshold
        :rtype: list
        """
        if "results" not in results:
            return []
        res = results['results']
        print('[SauceNAO] Result: {}'.format(len(res)))
        parsed_data = []

        indexer = {
            "0": self.__format_hmagz,
            "2": self.__format_hgcg,
            "5": self.__format_pixiv,
            "6": self.__format_pixiv_historical,
            "8": self.__format_seiga,
            "9": self.__format_danbooru,
            "12": self.__format_yandere,
            "18": self.__format_hmisc, # nhentai
            "21": self.__format_anidb,
            "22": self.__format_hanime,
            "23": self.__format_imdb, # Movie
            "24": self.__format_imdb, # Shows
            "25": self.__format_gelbooru,
            "26": self.__format_konachan,
            "27": self.__format_sankaku,
            "29": self.__format_e621,
            "30": self.__format_idolcomplex,
            "31": self.__format_bcynet, # illust
            "32": self.__format_bcynet, # cosplay
            "34": self.__format_deviantart,
            "35": self.__format_pawoo,
            "36": self.__format_madokami,
            "37": self.__format_mangadex
        }
        for r in res:
            data = {
                'title': '',
                'source': '',
                'confidence': '',
                'thumbnail': ''
            }
            header_d = r['header']
            confidence = float(header_d['similarity'])
            if confidence <= self.minsim:
                continue
            data_d = r['data']
            title, extra_info, source, index_er = indexer.get(str(header_d['index_id']), self.__format_generic)(data_d, header_d)
            data['title'] = title
            data['source'] = source
            data['extra_info'] = extra_info
            data['confidence'] = confidence
            data['indexer'] = index_er
            data['thumbnail'] = header_d['thumbnail']
            parsed_data.append(data)
        parsed_data.sort(key=lambda x: x['confidence']) # Sort by confidence
        parsed_data = parsed_data[::-1] # oops
        return parsed_data

    def get_sauce(self, data):
        """
        Main usable command outside this class

        This command will start fetching the API with the url provided 
        then it will use the internal `.__build_results()` function to format and get the best sauce possible
        Can return empty list if there's nothing that exceed the minimum threshold/confidence

        :return: a list that exceed the minimum threshold
        :rtype: list
        """
        build_url = "https://saucenao.com/search.php?dbmask=137438953471&output_type=2&minsim={}!&numres=6".format(self.minsim)
        build_url += "&api_key=" + self.api_key
        files = {}
        if isinstance(data, str):
            build_url += "&url=" + quote_plus(data)
        else:
            files = {'file': data}
        print(build_url)
        if files:
            r = requests.post(
                build_url,
                files=files
            )
        else:
            r = requests.get(
                build_url
            )
        #with open('sss.json', 'w', encoding="utf-8") as fp:
        #    fp.write(str(r.json()))
        print(r.json())
        return self.__build_results(r.json())

if __name__=="__main__":
    #sn = SauceNAO("https://files.yande.re/sample/87c97f97958bb8d19b4ae3c0f335b436/yande.re%20610182%20sample%20hibike%21_euphonium%20kasaki_nozomi%20liz_to_aoi_tori%20piroaki%20seifuku%20wallpaper%20yoroizuka_mizore%20yuri.jpg")
    #x=sn.get_sauce()
    #sn = SauceNAO("https://p.ihateani.me/eknUoeMF.jpg")
    #x=sn.get_sauce()
    #sn = SauceNAO("https://cdn.discordapp.com/attachments/300947822956773376/678397806272184320/a46f570c42e221cd7bbd6fbe70d868e342659b66afd989030edaece601244230.png")
    #x = sn.get_sauce()
    sn = SauceNAO()
    img = open("IMG_20200212_073728.jpg", 'rb').read()
    from io import BytesIO
    bits = BytesIO(img)
    x = sn.get_sauce(bits)
    print(x)
