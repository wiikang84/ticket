# -*- coding: utf-8 -*-
"""
티켓팅 통합 정보 시스템 - 웹 서버 v3.0
KOPIS API + 예매사이트 크롤링 (인터파크, 멜론, YES24)
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re
import json
import threading
import time as time_module
import subprocess
from concurrent.futures import ThreadPoolExecutor
import os
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    KOPIS_API_KEY, KOPIS_BASE_URL, GENRE_CODES,
    GENRE_CODE_CONCERT, GENRE_CODE_MUSICAL, GENRE_CODE_THEATER,
    ALLOWED_ORIGINS, ALLOWED_IMAGE_DOMAINS, SUPPORTED_LANGS, FLASK_DEBUG
)
from constants import (
    get_cache_key, normalize_name, classify_part, classify_region, categorize_concert
)
from utils.security import is_safe_url, set_security_headers
from utils.helpers import calculate_dday, filter_ended_performances, sort_by_dday
from services.merger import merge_performance_data, merge_source_data
from services.image_proxy import get_cached_or_download, cleanup_old_cache
from services.translation import (
    translate_text, translate_performance_data, save_translation_cache,
    load_po_translations, translation_cache, translation_cache_lock
)
from crawlers.kopis import fetch_all_kopis, fetch_kopis_detail

app = Flask(__name__)
CORS(app, origins=ALLOWED_ORIGINS)
# TODO: Rate Limiting 도입 시 flask-limiter 사용
# from flask_limiter import Limiter
# limiter = Limiter(app=app, default_limits=["200 per hour"])

app.after_request(set_security_headers)

if not KOPIS_API_KEY:
    logging.warning("KOPIS_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
KOPIS_BASE_URL = "http://www.kopis.or.kr/openApi/restful"



# 캐시 저장소 (하루 2회 업데이트용)
cache = {
    'data': None,
    'last_update': None
}
cache_lock = threading.Lock()

# 기본 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 스케줄러 로거
scheduler_logger = logging.getLogger('scheduler')
scheduler_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[스케줄러] %(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
scheduler_logger.addHandler(handler)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/kopis/performances')
def get_kopis_performances():
    """KOPIS API로 공연 목록 조회"""
    try:
        start_date = request.args.get('start_date', datetime.now().strftime('%Y%m%d'))
        end_date = request.args.get('end_date', (datetime.now() + timedelta(days=60)).strftime('%Y%m%d'))
        genre = request.args.get('genre', '')
        rows = request.args.get('rows', '50')
        page = request.args.get('page', '1')

        params = {
            'service': KOPIS_API_KEY,
            'stdate': start_date,
            'eddate': end_date,
            'cpage': page,
            'rows': rows
        }

        if genre and genre in GENRE_CODES:
            params['shcate'] = GENRE_CODES[genre]

        response = requests.get(f"{KOPIS_BASE_URL}/pblprfr", params=params, timeout=10)

        if response.status_code == 200:
            root = ET.fromstring(response.content)
            performances = []

            for db in root.findall('.//db'):
                perf_id = db.find('mt20id').text if db.find('mt20id') is not None else ''
                name = db.find('prfnm').text if db.find('prfnm') is not None else ''

                perf = {
                    'id': perf_id,
                    'name': name,
                    'start_date': db.find('prfpdfrom').text if db.find('prfpdfrom') is not None else '',
                    'end_date': db.find('prfpdto').text if db.find('prfpdto') is not None else '',
                    'venue': db.find('fcltynm').text if db.find('fcltynm') is not None else '',
                    'poster': db.find('poster').text if db.find('poster') is not None else '',
                    'genre': db.find('genrenm').text if db.find('genrenm') is not None else '',
                    'state': db.find('prfstate').text if db.find('prfstate') is not None else '',
                    'source': 'KOPIS',
                    'source_color': '#00d4ff',
                    'hash': get_cache_key(normalize_name(name))
                }
                performances.append(perf)

            return jsonify({
                'success': True,
                'data': performances,
                'count': len(performances)
            })
        else:
            return jsonify({'success': False, 'error': f'API 오류: {response.status_code}'})

    except Exception as e:
        logging.error(f"KOPIS 공연 조회 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'error': '공연 데이터를 불러오는 중 오류가 발생했습니다.'})


@app.route('/api/kopis/performance/<perf_id>')
def get_kopis_performance_detail(perf_id):
    """KOPIS API로 공연 상세 정보 조회 (예매 링크 포함)"""
    try:
        params = {'service': KOPIS_API_KEY}
        response = requests.get(f"{KOPIS_BASE_URL}/pblprfr/{perf_id}", params=params, timeout=10)

        if response.status_code == 200:
            root = ET.fromstring(response.content)
            db = root.find('.//db')

            if db is not None:
                # 예매 링크 정보 추출
                booking_sites = []
                relates = db.find('relates')
                if relates is not None:
                    for relate in relates.findall('relate'):
                        site_name = relate.find('relatenm').text if relate.find('relatenm') is not None else ''
                        site_url = relate.find('relateurl').text if relate.find('relateurl') is not None else ''
                        if site_name and site_url:
                            # 사이트별 색상 지정
                            color = '#888'
                            if '인터파크' in site_name:
                                color = '#ff6464'
                            elif '멜론' in site_name:
                                color = '#00cd3c'
                            elif 'YES24' in site_name or '예스24' in site_name:
                                color = '#ffc800'
                            elif '티켓링크' in site_name:
                                color = '#0066cc'

                            booking_sites.append({
                                'name': site_name,
                                'url': site_url,
                                'color': color
                            })

                detail = {
                    'id': db.find('mt20id').text if db.find('mt20id') is not None else '',
                    'name': db.find('prfnm').text if db.find('prfnm') is not None else '',
                    'start_date': db.find('prfpdfrom').text if db.find('prfpdfrom') is not None else '',
                    'end_date': db.find('prfpdto').text if db.find('prfpdto') is not None else '',
                    'venue': db.find('fcltynm').text if db.find('fcltynm') is not None else '',
                    'cast': db.find('prfcast').text if db.find('prfcast') is not None else '',
                    'runtime': db.find('prfruntime').text if db.find('prfruntime') is not None else '',
                    'price': db.find('pcseguidance').text if db.find('pcseguidance') is not None else '',
                    'poster': db.find('poster').text if db.find('poster') is not None else '',
                    'genre': db.find('genrenm').text if db.find('genrenm') is not None else '',
                    'state': db.find('prfstate').text if db.find('prfstate') is not None else '',
                    'story': db.find('sty').text if db.find('sty') is not None else '',
                    'schedule': db.find('dtguidance').text if db.find('dtguidance') is not None else '',
                    'booking_sites': booking_sites  # 실제 예매 링크
                }
                return jsonify({'success': True, 'data': detail})

        return jsonify({'success': False, 'error': '공연 정보를 찾을 수 없습니다.'})

    except Exception as e:
        logging.error(f"KOPIS 상세 조회 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'error': '공연 상세 정보를 불러오는 중 오류가 발생했습니다.'})


@app.route('/api/ticketing/interpark')
def get_interpark_tickets():
    """인터파크 콘서트/뮤지컬 조회 (JSON 파싱)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        }

        tickets = []

        # 콘서트 페이지만 크롤링 (뮤지컬 제외)
        urls = [
            "https://tickets.interpark.com/contents/genre/concert"
        ]

        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code == 200:
                    html = response.text

                    # JSON 객체 패턴으로 공연 정보 추출 (예매시작일 포함)
                    # {"goodsCode":"26000365","goodsName":"...","placeName":"...","posterImageUrl":"...","playStartDate":"...","ticketOpenDate":"..."}
                    goods_pattern = r'\{"goodsCode":"(\d+)","goodsName":"([^"]+)"[^}]*"placeName":"([^"]*)"[^}]*"posterImageUrl":"([^"]*)"[^}]*"playStartDate":"(\d+)"[^}]*"playEndDate":"(\d+)"(?:[^}]*"ticketOpenDate":"(\d*)")?'
                    matches = re.findall(goods_pattern, html)

                    for match in matches:
                        # 7개 필드 (ticketOpenDate 포함)
                        if len(match) >= 7:
                            goods_code, goods_name, place_name, poster_url, start_date, end_date, ticket_open = match
                        else:
                            goods_code, goods_name, place_name, poster_url, start_date, end_date = match[:6]
                            ticket_open = ''

                        # 광고/프로모션 필터링
                        skip_keywords = ['골드클래스', '프로모션', '우수회원', '혜택', '쿠폰', 'VIP', 'NOL']
                        if any(kw in goods_name for kw in skip_keywords):
                            continue

                        # 링크 생성
                        link = f"https://tickets.interpark.com/goods/{goods_code}"

                        # 포스터 이미지
                        poster = poster_url
                        if poster and poster.startswith('//'):
                            poster = 'https:' + poster

                        # 날짜 포맷팅
                        try:
                            start_fmt = f"{start_date[:4]}.{start_date[4:6]}.{start_date[6:]}"
                            end_fmt = f"{end_date[:4]}.{end_date[4:6]}.{end_date[6:]}"
                            date_str = f"{start_fmt} - {end_fmt}" if start_date != end_date else start_fmt
                        except Exception:
                            date_str = ''
                            start_fmt = ''

                        # 예매 오픈일 포맷팅
                        ticket_open_fmt = ''
                        ticket_dday = None
                        if ticket_open and len(ticket_open) >= 8:
                            try:
                                ticket_open_fmt = f"{ticket_open[:4]}.{ticket_open[4:6]}.{ticket_open[6:8]}"
                                ticket_dday = calculate_dday(ticket_open_fmt)
                            except Exception:
                                pass

                        # 예매오픈일 없으면 공연 시작 2주 전으로 추정
                        if not ticket_open_fmt and start_date and len(start_date) >= 8:
                            try:
                                perf_start = datetime.strptime(start_date[:8], '%Y%m%d')
                                estimated_open = perf_start - timedelta(days=14)
                                # 이미 지난 날짜면 표시 안 함
                                if estimated_open >= datetime.now():
                                    ticket_open_fmt = estimated_open.strftime('%Y.%m.%d') + ' (추정)'
                                    ticket_dday = calculate_dday(estimated_open.strftime('%Y.%m.%d'))
                            except Exception:
                                pass

                        tickets.append({
                            'name': goods_name,
                            'date': date_str,
                            'start_date': start_fmt if 'start_fmt' in dir() and start_fmt else '',
                            'end_date': end_fmt if 'end_fmt' in dir() else '',
                            'venue': place_name,
                            'poster': poster,
                            'source': '인터파크',
                            'source_color': '#ff6464',
                            'link': link,
                            'category': categorize_concert(goods_name),  # 세부 장르
                            'part': classify_part(goods_name),  # 파트: concert / theater
                            'region': classify_region(place_name),  # 지역 분류
                            'ticket_open': ticket_open_fmt,
                            'dday': ticket_dday,
                            'hash': get_cache_key(normalize_name(goods_name))
                        })

            except Exception as e:
                continue

        # 중복 제거
        seen = set()
        unique_tickets = []
        for t in tickets:
            if t['hash'] not in seen:
                seen.add(t['hash'])
                unique_tickets.append(t)

        return jsonify({
            'success': True,
            'data': unique_tickets,
            'source': '인터파크',
            'count': len(unique_tickets)
        })

    except Exception as e:
        logging.error(f"인터파크 크롤링 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'error': '인터파크 데이터 로딩 실패', 'source': '인터파크', 'data': []})


@app.route('/api/ticketing/melon')
def get_melon_tickets():
    """멜론티켓 콘서트 조회 (Selenium - subprocess)"""
    try:
        # 별도 프로세스로 Selenium 실행
        script_path = os.path.join(os.path.dirname(__file__), 'selenium_crawler.py')
        result = subprocess.run(
            ['python', script_path, 'melon'],
            capture_output=True,
            timeout=120,
            cwd=os.path.dirname(__file__),
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            data['source'] = '멜론티켓'
            return jsonify(data)
        else:
            return jsonify({
                'success': False,
                'error': result.stderr or 'No output',
                'source': '멜론티켓',
                'data': []
            })

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout (2분 초과)', 'source': '멜론티켓', 'data': []})
    except Exception as e:
        logging.error(f"멜론티켓 크롤링 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'error': '멜론티켓 데이터 로딩 실패', 'source': '멜론티켓', 'data': []})


@app.route('/api/ticketing/yes24')
def get_yes24_tickets():
    """YES24 티켓 콘서트 조회 (Selenium - subprocess)"""
    try:
        # 별도 프로세스로 Selenium 실행
        script_path = os.path.join(os.path.dirname(__file__), 'selenium_crawler.py')
        result = subprocess.run(
            ['python', script_path, 'yes24'],
            capture_output=True,
            timeout=120,
            cwd=os.path.dirname(__file__),
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            data['source'] = 'YES24'
            return jsonify(data)
        else:
            return jsonify({
                'success': False,
                'error': result.stderr or 'No output',
                'source': 'YES24',
                'data': []
            })

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout (2분 초과)', 'source': 'YES24', 'data': []})
    except Exception as e:
        logging.error(f"YES24 크롤링 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'YES24 데이터 로딩 실패', 'source': 'YES24', 'data': []})





def scheduled_update():
    """스케줄러에 의해 실행: KOPIS + 인터파크 데이터 자동 수집 (Selenium 제외)"""
    scheduler_logger.info("자동 업데이트 시작...")
    try:
        start_date = datetime.now().strftime('%Y%m%d')
        end_date = (datetime.now() + timedelta(days=60)).strftime('%Y%m%d')
        today_str = datetime.now().strftime('%Y.%m.%d')

        merged_performances = {}
        source_counts = {'kopis': 0, 'interpark': 0, 'melon': 0, 'yes24': 0}

        # KOPIS 3장르 병렬 수집
        kopis_results = fetch_all_kopis(start_date, end_date)
        for perf in kopis_results:
            merged_performances[perf['hash']] = perf
            source_counts['kopis'] += 1

        # 인터파크 데이터 수집
        try:
            with app.test_request_context():
                interpark_response = get_interpark_tickets()
                interpark_data = interpark_response.get_json()
                if interpark_data.get('success'):
                    merge_source_data(merged_performances, interpark_data['data'],
                                      '인터파크', '#ff6464', 'interpark', source_counts)
        except Exception as e:
            scheduler_logger.warning(f"인터파크 수집 실패: {e}")

        # 종료된 공연 필터링 + 정렬
        filtered_list = filter_ended_performances(list(merged_performances.values()))
        sort_by_dday(filtered_list)

        # 공연 데이터 사전 번역
        try:
            translate_performance_data(filtered_list)
            scheduler_logger.info(f"공연 데이터 번역 완료: {len(filtered_list)}건")
        except Exception as e:
            scheduler_logger.warning(f"공연 데이터 번역 실패: {e}")

        # 캐시에 저장
        with cache_lock:
            cache['data'] = {
                'success': True,
                'data': filtered_list,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stats': {
                    'kopis': source_counts['kopis'],
                    'interpark': source_counts['interpark'],
                    'melon': source_counts['melon'],
                    'yes24': source_counts['yes24'],
                    'total': len(filtered_list)
                }
            }
            cache['last_update'] = datetime.now()

        scheduler_logger.info(f"자동 업데이트 완료: {len(filtered_list)}건 (KOPIS: {source_counts['kopis']}, 인터파크: {source_counts['interpark']})")

    except Exception as e:
        scheduler_logger.error(f"자동 업데이트 오류: {e}")


def init_scheduler():
    """APScheduler 초기화: 매일 00시, 12시 실행"""
    scheduler = BackgroundScheduler(daemon=True)
    # 매일 00:00 실행
    scheduler.add_job(scheduled_update, CronTrigger(hour=0, minute=0), id='update_00', replace_existing=True)
    # 매일 12:00 실행
    scheduler.add_job(scheduled_update, CronTrigger(hour=12, minute=0), id='update_12', replace_existing=True)
    scheduler.start()
    scheduler_logger.info("APScheduler 시작 (00시, 12시 자동 업데이트)")
    return scheduler


@app.route('/api/cache/status')
def cache_status():
    """캐시 상태 확인 API"""
    with cache_lock:
        last_update = cache['last_update']
        data_count = len(cache['data']['data']) if cache['data'] else 0

    return jsonify({
        'has_cache': cache['data'] is not None,
        'last_update': last_update.strftime('%Y-%m-%d %H:%M:%S') if last_update else None,
        'data_count': data_count,
        'cache_age_minutes': round((datetime.now() - last_update).total_seconds() / 60, 1) if last_update else None
    })


@app.route('/api/all')
def get_all_data():
    """모든 소스에서 데이터 통합 조회 (공연 기준 통합 + 판매처 표시)"""
    try:
        # 캐시가 12시간 이내면 캐시 데이터 즉시 반환 (빠른 응답)
        skip_selenium = request.args.get('skip_selenium', '') == 'true'
        with cache_lock:
            if cache['data'] and cache['last_update']:
                cache_age = (datetime.now() - cache['last_update']).total_seconds()
                if cache_age < 12 * 3600 and skip_selenium:
                    # 캐시 데이터에서 파트/지역 필터는 프론트에서 처리하므로 그대로 반환
                    return jsonify(cache['data'])

        start_date = request.args.get('start_date', datetime.now().strftime('%Y%m%d'))
        end_date = request.args.get('end_date', (datetime.now() + timedelta(days=60)).strftime('%Y%m%d'))
        genre = request.args.get('genre', '')
        part_filter = request.args.get('part', '')  # 파트 필터: concert / theater / (빈값=전체)
        region_filter = request.args.get('region', '')  # 지역 필터: 서울 / 경기·인천 / ... / (빈값=전체)
        skip_selenium = request.args.get('skip_selenium', '') == 'true'  # Selenium 크롤링 스킵 (빠른 로딩용)

        # 통합 공연 목록 (hash -> 공연 정보)
        merged_performances = {}
        source_counts = {'kopis': 0, 'interpark': 0, 'melon': 0, 'yes24': 0}

        # Phase 1: KOPIS 3장르 + 인터파크 병렬 수집
        def fetch_interpark_data():
            try:
                resp = get_interpark_tickets()
                data = resp.get_json()
                return data.get('data', []) if data.get('success') else []
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=4) as executor:
            kopis_future = executor.submit(fetch_all_kopis, start_date, end_date)
            interpark_future = executor.submit(fetch_interpark_data)

            # KOPIS 결과 병합
            for perf in kopis_future.result():
                merged_performances[perf['hash']] = perf
                source_counts['kopis'] += 1

            # 인터파크 결과 병합
            interpark_items = interpark_future.result()
            merge_source_data(merged_performances, interpark_items,
                              '인터파크', '#ff6464', 'interpark', source_counts)

        # Phase 2: 멜론 + YES24 병렬 수집 (skip_selenium이면 건너뜀)
        if not skip_selenium:
            def fetch_melon_data():
                try:
                    resp = get_melon_tickets()
                    data = resp.get_json()
                    return data.get('data', []) if data.get('success') else []
                except Exception:
                    return []

            def fetch_yes24_data():
                try:
                    resp = get_yes24_tickets()
                    data = resp.get_json()
                    return data.get('data', []) if data.get('success') else []
                except Exception:
                    return []

            with ThreadPoolExecutor(max_workers=2) as executor:
                melon_future = executor.submit(fetch_melon_data)
                yes24_future = executor.submit(fetch_yes24_data)

                merge_source_data(merged_performances, melon_future.result(),
                                  '멜론티켓', '#00cd3c', 'melon', source_counts)
                merge_source_data(merged_performances, yes24_future.result(),
                                  'YES24', '#ffc800', 'yes24', source_counts)

        # 리스트 변환 + 필터 적용
        performances_list = list(merged_performances.values())
        if part_filter:
            performances_list = [p for p in performances_list if p.get('part') == part_filter]
        if region_filter:
            performances_list = [p for p in performances_list if p.get('region') == region_filter]

        # 종료된 공연 필터링 + 정렬
        performances_list = filter_ended_performances(performances_list)
        sort_by_dday(performances_list)

        # 공연 데이터 사전 번역
        try:
            translate_performance_data(performances_list)
        except Exception as e:
            logging.warning(f"공연 데이터 번역 실패: {e}")

        return jsonify({
            'success': True,
            'data': performances_list,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stats': {
                'kopis': source_counts['kopis'],
                'interpark': source_counts['interpark'],
                'melon': source_counts['melon'],
                'yes24': source_counts['yes24'],
                'total': len(performances_list)
            }
        })

    except Exception as e:
        logging.error(f"전체 데이터 로딩 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'error': '데이터를 불러오는 중 오류가 발생했습니다.'})


@app.route('/api/proxy/image')
def proxy_image():
    """외부 이미지 프록시 (캐싱 지원)"""
    url = request.args.get('url', '')
    if not url:
        return '', 404

    if not is_safe_url(url):
        return '', 403

    content, content_type, status_code = get_cached_or_download(url)
    if content and status_code == 200:
        return content, 200, {'Content-Type': content_type, 'Cache-Control': 'max-age=86400'}
    return '', status_code


@app.route('/api/ticketing/detail')
def get_ticket_detail():
    """멜론/YES24 상세 정보 조회 (Selenium - subprocess)"""
    try:
        source = request.args.get('source', '')
        link = request.args.get('link', '')

        if not source or not link:
            return jsonify({'success': False, 'error': 'source와 link 파라미터가 필요합니다.'})

        script_path = os.path.join(os.path.dirname(__file__), 'selenium_crawler.py')

        # 링크에서 ID 추출
        if source == 'melon' or '멜론' in source:
            # 멜론 링크에서 prodId 추출
            import re
            match = re.search(r'prodId=(\d+)', link)
            if not match:
                return jsonify({'success': False, 'error': 'prodId를 찾을 수 없습니다.'})
            prod_id = match.group(1)

            result = subprocess.run(
                ['python', script_path, 'melon_detail', prod_id],
                capture_output=True,
                timeout=60,
                cwd=os.path.dirname(__file__),
                encoding='utf-8',
                errors='replace'
            )

        elif source == 'yes24' or 'YES24' in source:
            # YES24 링크에서 PerfCode 추출
            import re
            match = re.search(r'/Perf/(\d+)', link) or re.search(r'PerfCode=(\d+)', link)
            if not match:
                return jsonify({'success': False, 'error': 'PerfCode를 찾을 수 없습니다.'})
            perf_code = match.group(1)

            result = subprocess.run(
                ['python', script_path, 'yes24_detail', perf_code],
                capture_output=True,
                timeout=60,
                cwd=os.path.dirname(__file__),
                encoding='utf-8',
                errors='replace'
            )

        else:
            return jsonify({'success': False, 'error': f'지원하지 않는 소스: {source}'})

        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return jsonify(data)
        else:
            return jsonify({
                'success': False,
                'error': result.stderr or 'No output',
                'data': {}
            })

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Timeout (1분 초과)', 'data': {}})
    except Exception as e:
        logging.error(f"티켓 상세 조회 오류: {e}", exc_info=True)
        return jsonify({'success': False, 'error': '상세 정보를 불러오는 중 오류가 발생했습니다.', 'data': {}})


@app.route('/api/search')
def search_all():
    """통합 검색"""
    keyword = request.args.get('keyword', '')

    if not keyword:
        return jsonify({'success': False, 'error': '검색어를 입력해주세요.'})

    results = {
        'keyword': keyword,
        'kopis': [],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # KOPIS 검색
    try:
        start_date = datetime.now().strftime('%Y%m%d')
        end_date = (datetime.now() + timedelta(days=90)).strftime('%Y%m%d')

        params = {
            'service': KOPIS_API_KEY,
            'stdate': start_date,
            'eddate': end_date,
            'cpage': '1',
            'rows': '50',
            'shprfnm': keyword
        }

        response = requests.get(f"{KOPIS_BASE_URL}/pblprfr", params=params, timeout=10)

        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for db in root.findall('.//db'):
                name = db.find('prfnm').text if db.find('prfnm') is not None else ''
                results['kopis'].append({
                    'id': db.find('mt20id').text if db.find('mt20id') is not None else '',
                    'name': name,
                    'venue': db.find('fcltynm').text if db.find('fcltynm') is not None else '',
                    'start_date': db.find('prfpdfrom').text if db.find('prfpdfrom') is not None else '',
                    'end_date': db.find('prfpdto').text if db.find('prfpdto') is not None else '',
                    'poster': db.find('poster').text if db.find('poster') is not None else '',
                    'genre': db.find('genrenm').text if db.find('genrenm') is not None else '',
                    'source': 'KOPIS',
                    'source_color': '#00d4ff'
                })
    except Exception as e:
        results['kopis_error'] = str(e)

    return jsonify({'success': True, 'data': results})


# ============================================================
# PO 파일 기반 UI 번역
# ============================================================

_ui_translations = load_po_translations()


@app.route('/api/i18n/<lang>')
def get_ui_translations(lang):
    """UI 번역을 JSON으로 반환"""
    if lang not in SUPPORTED_LANGS:
        lang = 'ko'
    translations = _ui_translations.get(lang, _ui_translations.get('ko', {}))
    resp = jsonify(translations)
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


@app.route('/api/translate')
def translate_api():
    """텍스트 번역 API (디버깅용)"""
    text = request.args.get('text', '')
    to_lang = request.args.get('to', 'en')
    from_lang = request.args.get('from', 'ko')

    if not text:
        return jsonify({'success': False, 'error': '텍스트가 필요합니다.'})

    translated = translate_text(text, from_lang, to_lang)
    return jsonify({'success': True, 'original': text, 'translated': translated, 'from': from_lang, 'to': to_lang})


@app.route('/api/translate/batch', methods=['POST'])
def translate_batch_api():
    """여러 텍스트 일괄 번역 API (디버깅용)"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON 데이터가 필요합니다.'})

    texts = data.get('texts', [])
    to_lang = data.get('to', 'en')
    from_lang = data.get('from', 'ko')

    if not texts:
        return jsonify({'success': False, 'error': '번역할 텍스트가 없습니다.'})

    results = []
    for text in texts[:50]:
        translated = translate_text(text, from_lang, to_lang)
        results.append({'original': text, 'translated': translated})
        time_module.sleep(0.1)

    return jsonify({'success': True, 'results': results, 'from': from_lang, 'to': to_lang})


# gunicorn 호환: 모듈 로드 시 스케줄러 자동 시작
_scheduler = None

def start_scheduler_once():
    """스케줄러 1회만 시작 (중복 방지)"""
    global _scheduler
    if _scheduler is None:
        _scheduler = init_scheduler()
        # 최초 1회 데이터 갱신 (백그라운드)
        threading.Thread(target=scheduled_update, daemon=True).start()

# gunicorn으로 실행 시에도 스케줄러 시작
start_scheduler_once()


if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    port = int(os.environ.get('PORT', 5000))

    print("=" * 50)
    print("  티켓팅 통합 정보 시스템 v3.3")
    print("  - KOPIS + 인터파크 + 멜론티켓 + YES24")
    print("  - 콘서트 / 연극&뮤지컬 파트 분류")
    print("  - 7개 권역 지역 필터")
    print("  - 12시간 자동 업데이트 (APScheduler)")
    print("  - 브라우저 알림 (찜 기능)")
    print("=" * 50)
    print(f"  PC: http://localhost:{port}")
    print(f"  모바일: http://{local_ip}:{port}")
    print("=" * 50)
    app.run(debug=FLASK_DEBUG, port=port, host='0.0.0.0', use_reloader=False)
