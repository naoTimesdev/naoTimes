import re
from urllib.parse import unquote_plus
from flask import Blueprint, request, jsonify

from .modul.ihateanime import ihateanimeCache
from .modul.pemecah import CepatSaji

safelink = Blueprint('safelink', __name__, url_prefix="/api")

ihaCache = ihateanimeCache()

@safelink.route('/pemecah/<path:url>')
def pemecahapi_api(url: str):
    url = url.strip()
    url = unquote_plus(url)

    if url[-1] == '/':
        url = url[:-1]
    print('Processing url: {}'.format(url))

    regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
            r'localhost|' #localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    if not re.match(regex, url):
        return jsonify({'message': 'bukan format url yang valid.', 'status_code': 400}), 400
    cs = CepatSaji(url, cache_client=ihaCache)
    try:
        hasil, judul, _ = cs.pecahkan()
    except cs.TidakDidukung:
        return jsonify({
            'message': 'URL tidak didukung.',
            'supported_web': [
                'samehadaku',
                'oploverz',
                'awsubs',
                'anitoki',
                'kusonime',
                'neonime',
                'moenime'
            ],
            'status_code': 400
        }), 400
    except cs.TidakDitemukan:
        return jsonify(message="URL tersebut tidak dapat ditemukan (404)", status_code=404), 404
    except NotImplementedError:
        return jsonify(message="Bypass URL tersebut masih dalam pengembangan oleh N4O, silakan coba lagi besok.", status_code=501), 501
    except Exception as exc:
        return jsonify(
            {
                'message': 'terjadi kesalahan internal saat memecahkan url anda. mohon laporkan ke N4O#8868 di Discord.',
                'detailed_error': str(exc),
                'status_code': 500
            }
        ), 500

    json_data = {
        "url": url,
        "judul": judul,
        "tipe": cs.solver_type,
        "hasil": hasil
    }

    return jsonify(**json_data, status_code=200), 200