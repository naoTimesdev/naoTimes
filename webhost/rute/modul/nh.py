"""
Main nHentai API Parsing

Created by: N4O
(C) 2019 N4O (Protected by MIT License)
"""

import json
import time
from copy import deepcopy


def nh_communicate(url: str, sess) -> dict:
    """Start connection with nhentai.

    :param url: URL
    :type url: str
    :param sess: Session
    :type sess: requests.Session
    :return: API Result
    """
    req = sess.get(url)

    if req.status_code != 200:
        if req.status_code == 404 or req.status_code == 403:
            return {'message': 'no results', 'status_code': 404}, 404
        else:
            return {'message': 'Unknown error occured.', 'status_code': req.status_code}, req.status_code

    try:
        res = req.json()
    except json.JSONDecodeError:
        return res.content
    res['status_code'] = 200
    return res, 200


def parse_nhentai(res_data: dict) -> dict:
    """Parse doujin code

    :param res_data: [description]
    :type res_data: dict
    :return: parsed data
    :rtype: dict
    """
    parsed_data = {
        'id': '',
        'title': '',
        'original_title': {
            'japanese': '',
            'other': ''
        },
        'cover': '',
        'tags': {},
        'images': [],
        'url': '',
        'posted_time': 0,
        'favorites': 0,
        'total_pages': 0
    }
    parsed_tags = {
        'parodies': [],
        'characters': [],
        'tags': [],
        'artists': [],
        'groups': [],
        'languages': [],
        'categories': []
    }
    exts = {
        'j': 'jpg',
        'p': 'png',
        'g': 'gif'
    }
    availtags = {
        'tag': 'tags',
        'language': 'languages',
        'group': 'groups',
        'artist': 'artists',
        'category': 'categories',
        'parody': 'parodies',
        'character': 'characters'
    }

    coverfmt = 'https://s.ihateani.me/nht/{mId}/cover.{ext}'
    imagefmt = 'https://s.ihateani.me/nhi/{mId}/{n}.{ext}'

    media_id = res_data['media_id']

    titles = res_data['title']

    parsed_data['id'] = res_data['id']
    parsed_data['title'] = titles.get('pretty', titles.get('english', ''))
    parsed_data['original_title']['japanese'] = titles.get('japanese', '')
    parsed_data['original_title']['other'] = titles.get('english', '')

    image_set = res_data['images']

    parsed_data['cover'] = coverfmt.format(mId=media_id, ext=exts.get(image_set['cover']['t'], 'jpg'))

    # Parse tags
    tags = res_data['tags']
    for tag in tags:
        tag_name = availtags.get(tag['type'], None)
        if not tag_name:
            continue
        tags_data = deepcopy(parsed_tags[tag_name])
        tags_data.append(
            [tag['name'], tag['count']]
        )
        parsed_tags[tag_name] = tags_data
    parsed_data['tags'] = parsed_tags

    # Parse images
    images = image_set['pages']
    img_list = []
    size_list = []
    for index, img in enumerate(images, 1):
        img_list.append(
            imagefmt.format(mId=media_id, n=index, ext=exts.get(img['t'], 'jpg'))
        )
        size_list.append(
            [img['w'], img['h']]
        )
    parsed_data['images'] = img_list

    parsed_data['url'] = 'https://nhentai.net/g/{}'.format(res_data['id'])
    parsed_data['posted_time'] = res_data.get('upload_date', round(time.time()))
    parsed_data['favorites'] = res_data.get('num_favorites', 0)
    parsed_data['total_pages'] = res_data.get('num_pages', len(img_list))
    parsed_data['images_size'] = size_list

    return parsed_data
