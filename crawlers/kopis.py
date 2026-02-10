# -*- coding: utf-8 -*-
"""
KOPIS API 크롤러
"""
import logging
import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import KOPIS_API_KEY, KOPIS_BASE_URL, GENRE_CODE_CONCERT, GENRE_CODE_MUSICAL, GENRE_CODE_THEATER
from constants import get_cache_key, normalize_name, classify_part, classify_region, categorize_concert


def fetch_kopis_genre(genre_code, part_type, start_date, end_date):
    """KOPIS 단일 장르 데이터 수집 (병렬 실행용)"""
    results = []
    try:
        params = {
            'service': KOPIS_API_KEY,
            'stdate': start_date,
            'eddate': end_date,
            'cpage': '1',
            'rows': '50',
            'shcate': genre_code
        }
        response = requests.get(f"{KOPIS_BASE_URL}/pblprfr", params=params, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for db in root.findall('.//db'):
                name = db.find('prfnm').text if db.find('prfnm') is not None else ''
                genre_name = db.find('genrenm').text if db.find('genrenm') is not None else ''
                venue_name = db.find('fcltynm').text if db.find('fcltynm') is not None else ''
                area = db.find('area').text if db.find('area') is not None else ''
                perf_hash = get_cache_key(normalize_name(name))
                sub_category = categorize_concert(name)
                perf_part = classify_part(name, genre_name) if part_type == 'concert' else part_type

                perf = {
                    'id': db.find('mt20id').text if db.find('mt20id') is not None else '',
                    'name': name,
                    'start_date': db.find('prfpdfrom').text if db.find('prfpdfrom') is not None else '',
                    'end_date': db.find('prfpdto').text if db.find('prfpdto') is not None else '',
                    'venue': venue_name,
                    'poster': db.find('poster').text if db.find('poster') is not None else '',
                    'genre': genre_name,
                    'category': sub_category,
                    'part': perf_part,
                    'region': classify_region(venue_name, area),
                    'state': db.find('prfstate').text if db.find('prfstate') is not None else '',
                    'hash': perf_hash,
                    'available_sites': [{'name': 'KOPIS', 'link': '', 'color': '#00d4ff'}]
                }
                results.append(perf)
    except Exception as e:
        logging.warning(f"KOPIS 수집 실패 ({genre_code}): {e}")
    return results


def fetch_all_kopis(start_date, end_date):
    """KOPIS 3장르 병렬 수집"""
    kopis_genres = [
        (GENRE_CODE_CONCERT, 'concert'),
        (GENRE_CODE_MUSICAL, 'theater'),
        (GENRE_CODE_THEATER, 'theater')
    ]
    all_results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fetch_kopis_genre, gc, pt, start_date, end_date): gc
            for gc, pt in kopis_genres
        }
        for future in as_completed(futures):
            all_results.extend(future.result())
    return all_results


def fetch_kopis_detail(perf_id):
    """KOPIS 공연 상세정보 조회"""
    try:
        params = {'service': KOPIS_API_KEY}
        response = requests.get(f"{KOPIS_BASE_URL}/pblprfr/{perf_id}", params=params, timeout=10)

        if response.status_code == 200:
            root = ET.fromstring(response.content)
            db = root.find('.//db')
            if db is not None:
                detail = {
                    'id': perf_id,
                    'name': db.find('prfnm').text if db.find('prfnm') is not None else '',
                    'start_date': db.find('prfpdfrom').text if db.find('prfpdfrom') is not None else '',
                    'end_date': db.find('prfpdto').text if db.find('prfpdto') is not None else '',
                    'venue': db.find('fcltynm').text if db.find('fcltynm') is not None else '',
                    'poster': db.find('poster').text if db.find('poster') is not None else '',
                    'genre': db.find('genrenm').text if db.find('genrenm') is not None else '',
                    'state': db.find('prfstate').text if db.find('prfstate') is not None else '',
                    'cast': db.find('prfcast').text if db.find('prfcast') is not None else '',
                    'price': db.find('pcseguidance').text if db.find('pcseguidance') is not None else '',
                    'runtime': db.find('prfruntime').text if db.find('prfruntime') is not None else '',
                    'schedule': db.find('dtguidance').text if db.find('dtguidance') is not None else '',
                    'booking_links': [],
                    'poster_images': []
                }

                # 예매처 링크
                for relate in db.findall('.//relate'):
                    rel_name = relate.find('relatenm').text if relate.find('relatenm') is not None else ''
                    rel_url = relate.find('relateurl').text if relate.find('relateurl') is not None else ''
                    if rel_name and rel_url:
                        detail['booking_links'].append({'name': rel_name, 'url': rel_url})

                # 포스터 이미지
                for styurl in db.findall('.//styurl'):
                    if styurl.text:
                        detail['poster_images'].append(styurl.text)

                return detail
    except Exception as e:
        logging.error(f"KOPIS 상세 조회 오류 ({perf_id}): {e}")
    return None
