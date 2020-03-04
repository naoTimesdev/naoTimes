import mimetypes
import sys
from io import BytesIO

import requests
from flask import (Flask, abort, jsonify, redirect, render_template,
                   request, send_file)

from rute.modul.ihateanime import ihateanimeCache
from rute.nh import nhapi
from rute.deprecated_api import deprecatedapi
from rute.pemecah import safelink
from rute.sausnao import sausnao

app = Flask('naoTimesWebServer', template_folder='templates', static_folder='static')
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['JSON_SORT_KEYS'] = False
__version__ = 2.0 # API Version

app.config['DEFAULT_HEADERS'] = {'User-Agent': 'naoTimes mirror API v{}'.format(__version__)}
app.register_blueprint(nhapi)
app.register_blueprint(deprecatedapi)
app.register_blueprint(safelink)
app.register_blueprint(sausnao)

ihaCache = ihateanimeCache()

@app.route('/api')
def nh_api():
    return jsonify({'status_code': 200,
        'method': {
            '/api/v2': 'nhentai API parser version 2.0',
            '/api/pemecah/<url>': {
                'desc': 'solve fastsub shitty link',
                'supported_web': [
                    'samehadaku',
                    'oploverz',
                    'awsubs',
                    'anitoki',
                    'kusonime',
                    'neonime',
                    'moenime'
                ]
            }
        }
    })

@app.route('/api/v2')
def nh_apiv2():
    return jsonify({'status_code': 200,
        'method': {
            '/api/v2/info/<nuke_code>': 'parse nhentai, also proxied images.',
            '/api/v2/latest': 'get latest 25 doujin. (Refreshed every 30 minutes)',
            '/api/v2/search?q=<query>': 'search nhentai, and return result as a json data.',
            '/api/v2/image/<nuke_code>/<N>': 'look up image number `N` on `nuke_code`',
            '/unduh?id=<nuke_code>': 'Download all hentai images as .zip file.',
            '/baca/<nuke_code>': 'Read online without blocking.'
        }
    })

@app.route('/nhi/<path:path>')
def nhi(path):
    """Handle image, use redis to cache image."""
    print('Requested nhi: ' + path)
    image_url = 'https://i.nhentai.net/galleries/' + path
    memes_ = mimetypes.guess_type(image_url)
    print('Checking cache...')
    try:
        cached = ihaCache.get(image_url)
    except:
        cached = None
    session = requests.Session()
    session.headers.update(app.config['DEFAULT_HEADERS'])
    if cached:
        print('Cache found.')
        buffer_image = BytesIO(cached)
        buffer_image.seek(0)
    else:
        print('Cache not found, requesting...')
        while True:
            r = session.get(image_url)  # you can add UA, referrer, here is an example.
            if r.status_code < 400:
                break
            print('Retrying...')
        buffer_image = BytesIO(r.content)
        buffer_image.seek(0)
        print('Caching image...')
        try:
            ihaCache.setex(image_url, (60*60*24*7),
                            buffer_image.getvalue())
        except:
            pass
    print('Sending image...')
    return send_file(buffer_image, mimetype=memes_[0])

@app.route('/nht/<path:path>')
def nht(path):
    """Handle image, use redis to cache image."""
    print('Requested nht: ' + path)
    image_url = 'https://t.nhentai.net/galleries/' + path
    memes_ = mimetypes.guess_type(image_url)
    print('Checking cache...')
    try:
        cached = ihaCache.get(image_url)
    except:
        cached = None
    session = requests.Session()
    session.headers.update(app.config['DEFAULT_HEADERS'])
    if cached:
        print('Cache found.')
        buffer_image = BytesIO(cached)
        buffer_image.seek(0)
    else:
        print('Cache not found, requesting...')
        while True:
            r = session.get(image_url)  # you can add UA, referrer, here is an example.
            if r.status_code < 400:
                break
            print('Retrying...')
        buffer_image = BytesIO(r.content)
        buffer_image.seek(0)
        print('Caching image...')
        try:
            ihaCache.setex(image_url, (60*60*24*7),
                            buffer_image.getvalue())
        except:
            pass
    print('Sending image...')
    return send_file(buffer_image, mimetype=memes_[0])

@app.route('/')
def home():
    return abort(404)

@app.route('/unduh')
def unduh():
    doujin_id = request.args.get('id', None)
    return render_template('nhdown.html', id=doujin_id)

if __name__ == "__main__":
    debug = False
    args = sys.argv[1:]
    if args:
        if args[0].strip() in ['--debug', '-D']:
            debug = True
    app.run(host='localhost', debug=debug)
