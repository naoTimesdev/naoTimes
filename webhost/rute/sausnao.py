import json
import mimetypes
import random
from io import BytesIO
from string import ascii_lowercase
from urllib.parse import unquote_plus

import requests
from flask import Blueprint, abort, jsonify, request, send_file

from .modul.ihateanime import ihateanimeCache
from .modul.saucenao import SauceNAO

sausnao = Blueprint('sausnao', __name__, url_prefix="/api/v2")

ihaCache = ihateanimeCache()

@sausnao.route('/saus', methods=["GET", "POST"])
def saucenao():
    print('[SauceNAO] Request detected, method: {}'.format(request.method))
    if request.method == "POST":
        payload_url = request.form.get('url')
        if not payload_url:
            return jsonify({'message': 'please provide data with `url` key', 'status_code': 400}), 400

        print('[SauceNAO] POST: Downloading image link')
        bd = b''
        with requests.get(payload_url, stream=True) as req:
            ctype = req.headers['content-type']
            if not ctype.startswith('image'):
                return jsonify({'message': 'url is not an image', 'status_code': 400}), 400
            for x in req.iter_content(1024):
                bd += x

        print('[SauceNAO] POST: Caching image with random generated strings.')
        bd_buffer = BytesIO(bd)
        bd_buffer.seek(0)
        #ihaCache.set(rng, bd_buffer.getvalue())
        #ihaCache.set(rng+'_ext', cty)
        print('[SauceNAO] POST: Searching for sauce...')
        saus = SauceNAO()
        tomat = saus.get_sauce(bd_buffer)
        print('[SauceNAO] POST: Found: {} sauce'.format(len(tomat)))
        #ihaCache.setex(payload_url, 60*60*24*3, dict(tomat))
        #ihaCache.delete(rng)
        #ihaCache.delete(rng+'_ext')
        return jsonify({'results': tomat, 'status_code': 200}), 200

    abort(405)