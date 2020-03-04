import pymongo

from flask import Blueprint, abort, jsonify, request, send_file

#from .modul.ihateanime import ihateanimeCache

naotimes = Blueprint('naotimes', __name__, url_prefix="/api/v2/naotimes")

def determine_yn(t):
    tt = {
        "y": True,
        "x": False,
        "n": False,
        "Y": True,
        "X": False,
        "N": False,
        "D": True
    }
    return tt.get(t, False)

@naotimes.route('/<path:path>')
def utang_api(path):
    pretty = request.args.get('pretty', False)
    client = pymongo.MongoClient('localhost', 13307)
    db = client['naotimesdb']
    srv_list = db.list_collection_names(filter={"name": {"$regex": "^srv"}})
    path = str(path)
    if not path.startswith("srv_"):
        path = 'srv_' + path
    if path not in srv_list:
        return []
    
    srv = db[path]
    final_set = []
    dataset = list(srv.find({}))[0]
    anime_list = dataset['anime']
    for k, v in anime_list.items():
        ss = {}
        ss['title'] = k
        statuses = v['status']
        ep = None
        for k, v in statuses.items():
            if v['status'] != 'released':
                ep = k
                break
        if ep:
            ss['episode'] = ep
            ss['airing_time'] = statues[ep]['airing_time']
            ss['status'] = statuses[ep]['staff_status']
            final_set.append(ss)
    
    if pretty:
        final_finalset = []
        for ff in final_set:
            sf = ff['status']
            ss = {
                "title": ff['title'],
                "episode": ff['episode'],
                "status": {
                    "TL": determine_yn(sf["TL"]),
                    "TLC": determine_yn(sf['TLC']),
                    "Encode": determine_yn(sf['ENC']),
                    "Edit": determine_yn(sf['ED']),
                    "Timing": determine_yn(sf['TM']),
                    "TS": determine_yn(sf['TS']),
                    "QC": determine_yn(sf['QC'])
                }
            }
            final_finalset.append(ss)
        final_set = final_finalset
        del final_finalset

    final_set.sort(key=lambda x: x['title'])

    return jsonify(final_set)
