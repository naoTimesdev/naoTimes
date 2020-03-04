from flask import Blueprint, jsonify

deprecatedapi = Blueprint('deprecatedapi', __name__, url_prefix="/api")

@deprecatedapi.route('/v1')
def nh_apiv1():
    return jsonify({'status_code': 200,
        'method': 'deprecated, use v2.'
    })

@deprecatedapi.route('/download/<nuke_code>')
def deprecate_dlapi(nuke_code):
    return jsonify({'error': 'API Deprecated, use: `/unduh?id=<nuke_code>`', 'status_code': 410}), 410

@deprecatedapi.route('/info/<nuke_code>')
def deprecate_infoapi(nuke_code):
    return jsonify({'error': 'API Deprecated, use: `/api/v2/info/<nuke_code>`', 'status_code': 410}), 410

@deprecatedapi.route('/search')
def deprecate_searchapi():
    return jsonify({'error': 'API Deprecated, use: `/api/v2/search?q=<query>`', 'status_code': 410}), 410

@deprecatedapi.route('/mirror/<nuke_code>')
def deprecate_mirrorapi(nuke_code):
    return jsonify({'error': 'API Route Deleted, recommended to use `/api/v2/image/<nuke_code>/<Number>` individually', 'status_code': 410}), 410

@deprecatedapi.route('/image/<kode>/<halaman>')
def moveroute_imageapi(nuke_code):
    return jsonify({'error': 'API Route Moved, use `/api/v2/image/<nuke_code>/<Number>`', 'status_code': 410}), 410
