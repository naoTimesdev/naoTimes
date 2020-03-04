import json
import mimetypes
from io import BytesIO
from urllib.parse import unquote_plus

import requests
from flask import Blueprint, jsonify, request, send_file

from .modul.ihateanime import ihateanimeCache
from .modul.nh import nh_communicate, parse_nhentai

nhapi = Blueprint('nhapi', __name__, url_prefix="/api/v2")
__version__ = 2.0 # API Version
DEFAULT_HEADERS = {'User-Agent': 'naoTimes mirror API v{}'.format(__version__)}

ihaCache = ihateanimeCache()

@nhapi.route('/info/<nuke_code>')
def nhinfov2_api(nuke_code):
    print('Parsing code: ' + nuke_code)
    cache_data = ihaCache.get(nuke_code)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    if cache_data:
        print('Info cache exists, checking images cache.')
        json_data = json.loads(cache_data)
        return jsonify(status_code=200, **json_data), 200

    res_data, status = nh_communicate('https://nhentai.net/api/gallery/{}'.format(nuke_code), session)
    if status != 200:
        return jsonify(res_data), status

    parsed_data = parse_nhentai(res_data)

    ihaCache.setex(nuke_code, (60*60*24*3), parsed_data)

    return jsonify(status_code=200, **parsed_data), 200

@nhapi.route('/search')
def nhsearchv2_api():
    query = request.args.get('q')
    pagenum = request.args.get('page', 1)
    if not query:
        return jsonify(status_code=400, message='please provide search query'), 400
    if not isinstance(pagenum, int):
        if pagenum.isdigit():
            pagenum = int(pagenum)
        else:
            pagenum = 1
    if pagenum < 1:
        pagenum = 1
    query = unquote_plus(query)
    query = query.strip()
    print('Searching: ' + query)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    res_data, status = nh_communicate('https://nhentai.net/api/galleries/search?query={}&page={}'.format(query, pagenum), session)
    if status != 200:
        return jsonify(res_data), status

    results = res_data['result']
    if not results:
        return jsonify(status_code=404, message='no results'), 404

    dataset_parsed = []
    for res in results:
        parsed_data = parse_nhentai(res)
        dataset_parsed.append(parsed_data)

    json_data = {
        'query': query,
        'total_data': len(dataset_parsed),
        'total_page': res_data['num_pages'],
        'results': dataset_parsed,
    }

    return jsonify(status_code=200, **json_data), 200

@nhapi.route('/latest')
def nhlatestv2_api():
    print('Fetching latest 25 doujin.')
    pagenum = request.args.get('page', 1)
    if not isinstance(pagenum, int):
        if pagenum.isdigit():
            pagenum = int(pagenum)
        else:
            pagenum = 1
    if pagenum < 1:
        pagenum = 1
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    cache_data = ihaCache.get('latest_nhentai_page{}'.format(pagenum))
    if cache_data:
        print('Cache exist, loading and sending...')
        json_data = json.loads(cache_data)
        return jsonify(status_code=200, **json_data), 200

    res_data, status = nh_communicate('https://nhentai.net/api/galleries/all?page={}'.format(pagenum), session)
    if status != 200:
        return jsonify(res_data), status

    results = res_data['result']
    if not results:
        return jsonify(status_code=404, message='no results'), 404

    dataset_parsed = []
    for res in results:
        parsed_data = parse_nhentai(res)
        dataset_parsed.append(parsed_data)

    json_data = {
        'total_data': len(dataset_parsed),
        'total_page': res_data['num_pages'],
        'results': dataset_parsed
    }

    ihaCache.setex('latest_nhentai_page{}'.format(pagenum), (60*30), json_data)

    return jsonify(status_code=200, **json_data), 200

@nhapi.route('/image/<kode>/<halaman>')
def nhimgv2_api(kode, halaman: str):
    """Handle image, use redis to cache image."""
    print('Requested nhimg_api: ' + kode)
    try:
        cached_query = ihaCache.get(kode)
    except:
        cached_query = None
    if isinstance(halaman, str):
        if not halaman.isdigit():
            return jsonify(status_code=400, message='page number are incorrect'), 400
        halaman = int(halaman)
        if halaman < 1:
            halaman = 1

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    print('Checking nuke_code cache...')
    if cached_query:
        print('Found\nChecking image cache number {}...'.format(halaman))
        json_data = json.loads(cached_query)
        images = json_data['images']
        try:
            img_url = images[halaman - 1]
        except IndexError:
            return jsonify(status_code=404, message='page number doesn\'t exists'), 404

        if 'nhi' in img_url:
            img_url = img_url.replace('https://s.ihateani.me/nhi/', 'https://i.nhentai.net/galleries/')
        elif 'nht' in img_url:
            img_url = img_url.replace('https://s.ihateani.me/nht/', 'https://t.nhentai.net/galleries/')
        memetype = mimetypes.guess_type(img_url)

        try:
            img_cache = ihaCache.get(img_url)
        except:
            img_cache = None
        if img_cache:
            print('Found image.')
            buffer_image = BytesIO(img_cache)
            buffer_image.seek(0)
        else:
            print('Cache not found, requesting...')
            while True:
                r_img = session.get(img_url)
                if r_img.status_code < 400:
                    break
                print('Retrying...')
            buffer_image = BytesIO(r_img.content)
            buffer_image.seek(0)
            try:
                ihaCache.setex(img_url, (60*60*24*7),
                                buffer_image.getvalue())
            except:
                pass
        return send_file(buffer_image, mimetype=memetype[0])

    res_data, status = nh_communicate('https://nhentai.net/api/gallery/{}'.format(kode), session)
    if status != 200:
        return jsonify(res_data), status

    parsed_data = parse_nhentai(res_data)
    try:
        ihaCache.setex(kode, (60*60*24*3), parsed_data)
    except:
        pass
    try:
        img_url = parsed_data['images'][halaman - 1]
    except IndexError:
        return jsonify(status_code=404, message='page number doesn\'t exists'), 404

    if 'nhi' in img_url:
        img_url = img_url.replace('https://s.ihateani.me/nhi/', 'https://i.nhentai.net/galleries/')
    elif 'nht' in img_url:
        img_url = img_url.replace('https://s.ihateani.me/nht/', 'https://t.nhentai.net/galleries/')
    memetype = mimetypes.guess_type(img_url)

    try:
        img_cache = ihaCache.get(img_url)
    except:
        img_cache = None
    if img_cache:
        print('Found.')
        buffer_image = BytesIO(img_cache)
        buffer_image.seek(0)
    else:
        print('Cache not found, requesting...')
        while True:
            r_img = session.get(img_url)
            if r_img.status_code < 400:
                break
            print('Retrying...')
        buffer_image = BytesIO(r_img.content)
        buffer_image.seek(0)
        try:
            ihaCache.setex(img_url, (60*60*24*7),
                            buffer_image.getvalue())
        except:
            pass
    return send_file(buffer_image, mimetype=memetype[0])

