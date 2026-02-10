# -*- coding: utf-8 -*-
"""
티켓팅 통합 정보 시스템 - 웹 서버 v2.0
KOPIS API + 예매사이트 크롤링 (인터파크, 멜론, YES24)
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re
import json
import hashlib
from urllib.parse import urlparse
import ipaddress
from dotenv import load_dotenv
from constants import (
    CONCERT_CATEGORIES, THEATER_KEYWORDS, VENUE_REGION_KEYWORDS,
    get_cache_key, normalize_name, classify_part, classify_region, categorize_concert
)

load_dotenv()

# Selenium for dynamic page crawling
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import threading
import time as time_module
import subprocess
import os
import logging
import polib

# APScheduler (12시간 자동 업데이트)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# 크롬 드라이버 경로 캐시
_chrome_driver_path = None

def get_chrome_driver_path():
    """크롬 드라이버 경로 (캐시)"""
    global _chrome_driver_path
    if _chrome_driver_path is None:
        _chrome_driver_path = ChromeDriverManager().install()
    return _chrome_driver_path

# Selenium 브라우저 생성 함수
def get_chrome_driver():
    """헤드리스 크롬 브라우저 생성"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    options.add_argument('--remote-debugging-port=0')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--log-level=3')

    service = Service(get_chrome_driver_path())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

app = Flask(__name__)
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*').split(',')
CORS(app, origins=ALLOWED_ORIGINS)
# TODO: Rate Limiting 도입 시 flask-limiter 사용
# from flask_limiter import Limiter
# limiter = Limiter(app=app, default_limits=["200 per hour"])

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https: http:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'self'"
    )
    return response

# KOPIS API 설정
KOPIS_API_KEY = os.environ.get('KOPIS_API_KEY', '')
if not KOPIS_API_KEY:
    logging.warning("KOPIS_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
KOPIS_BASE_URL = "http://www.kopis.or.kr/openApi/restful"

# SSRF 방어용 이미지 프록시 허용 도메인
ALLOWED_IMAGE_DOMAINS = [
    'www.kopis.or.kr', 'kopis.or.kr',
    'tickets.interpark.com', 'ticketimage.interpark.com',
    'ticket.melon.com', 'cdnticket.melon.co.kr', 'cdnimg.melon.co.kr',
    'ticket.yes24.com', 'tkfile.yes24.com', 'image.yes24.com',
]

def is_safe_url(url):
    """URL 안전성 검증 (SSRF 방지)"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if not any(hostname == d or hostname.endswith('.' + d) for d in ALLOWED_IMAGE_DOMAINS):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False

# KOPIS 장르 코드
GENRE_CODE_CONCERT = "CCCD"  # 대중음악/콘서트
GENRE_CODE_MUSICAL = "GGGA"  # 뮤지컬
GENRE_CODE_THEATER = "AAAA"  # 연극

# 장르 코드 매핑
GENRE_CODES = {
    'concert': GENRE_CODE_CONCERT,
    'musical': GENRE_CODE_MUSICAL,
    'theater': GENRE_CODE_THEATER
}


# 분류 상수/함수는 constants.py에서 import


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



# get_cache_key, normalize_name은 constants.py에서 import


def calculate_dday(date_str):
    """D-day 계산"""
    try:
        # 다양한 날짜 형식 처리
        date_str = re.sub(r'[^\d.]', '', date_str)
        if len(date_str) >= 8:
            if '.' in date_str:
                parts = date_str.split('.')
                if len(parts) >= 3:
                    target = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            else:
                target = datetime.strptime(date_str[:8], '%Y%m%d')

            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            diff = (target - today).days
            return diff
    except Exception:
        pass
    return None


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



# categorize_concert은 constants.py에서 import


def merge_performance_data(base, new_item, source_name):
    """공연 데이터 병합 - 새 소스 정보 추가"""
    # 판매처 정보 추가
    site_info = {
        'name': source_name,
        'link': new_item.get('link', ''),
        'color': new_item.get('source_color', '#888')
    }

    if 'available_sites' not in base:
        base['available_sites'] = []

    # 중복 사이트 체크
    existing_sites = [s['name'] for s in base['available_sites']]
    if source_name not in existing_sites:
        base['available_sites'].append(site_info)

    # 티켓오픈일 정보가 있으면 업데이트
    if new_item.get('ticket_open') and not base.get('ticket_open'):
        base['ticket_open'] = new_item['ticket_open']
        base['dday'] = new_item.get('dday')

    # 포스터가 없으면 추가
    if not base.get('poster') and new_item.get('poster'):
        base['poster'] = new_item['poster']

    return base


def scheduled_update():
    """스케줄러에 의해 실행: KOPIS + 인터파크 데이터 자동 수집 (Selenium 제외)"""
    scheduler_logger.info("자동 업데이트 시작...")
    try:
        start_date = datetime.now().strftime('%Y%m%d')
        end_date = (datetime.now() + timedelta(days=60)).strftime('%Y%m%d')
        today_str = datetime.now().strftime('%Y.%m.%d')

        merged_performances = {}
        source_counts = {'kopis': 0, 'interpark': 0, 'melon': 0, 'yes24': 0}

        # KOPIS 데이터 수집
        kopis_genres = [
            (GENRE_CODE_CONCERT, 'concert'),
            (GENRE_CODE_MUSICAL, 'theater'),
            (GENRE_CODE_THEATER, 'theater')
        ]

        for genre_code, part_type in kopis_genres:
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
                        merged_performances[perf_hash] = perf
                        source_counts['kopis'] += 1
            except Exception as e:
                scheduler_logger.warning(f"KOPIS 수집 실패 ({genre_code}): {e}")

        # 인터파크 데이터 수집
        try:
            with app.test_request_context():
                interpark_response = get_interpark_tickets()
                interpark_data = interpark_response.get_json()
                if interpark_data.get('success'):
                    for item in interpark_data.get('data', []):
                        perf_hash = get_cache_key(normalize_name(item.get('name', '')))
                        source_counts['interpark'] += 1
                        if perf_hash in merged_performances:
                            merged_performances[perf_hash] = merge_performance_data(
                                merged_performances[perf_hash], item, '인터파크'
                            )
                        else:
                            item['available_sites'] = [{'name': '인터파크', 'link': item.get('link', ''), 'color': '#ff6464'}]
                            item['hash'] = perf_hash
                            if 'part' not in item:
                                item['part'] = classify_part(item.get('name', ''))
                            if 'region' not in item:
                                item['region'] = classify_region(item.get('venue', ''))
                            merged_performances[perf_hash] = item
        except Exception as e:
            scheduler_logger.warning(f"인터파크 수집 실패: {e}")

        # 종료된 공연 필터링
        performances_list = list(merged_performances.values())
        filtered_list = []
        for p in performances_list:
            end_date_val = p.get('end_date') or p.get('start_date') or p.get('date', '')
            if end_date_val:
                end_clean = re.sub(r'[^\d.]', '', end_date_val)[:10]
                if len(end_clean) >= 8:
                    try:
                        if '.' in end_clean:
                            parts = end_clean.split('.')
                            if len(parts) >= 3:
                                end_formatted = f"{parts[0]}.{parts[1].zfill(2)}.{parts[2].zfill(2)}"
                        else:
                            end_formatted = f"{end_clean[:4]}.{end_clean[4:6]}.{end_clean[6:8]}"
                        if end_formatted >= today_str:
                            filtered_list.append(p)
                        continue
                    except Exception:
                        pass
            filtered_list.append(p)

        # 정렬 (D-day 순)
        def sort_key(p):
            dday = p.get('dday')
            if dday is not None and dday >= 0:
                return (0, dday)
            elif p.get('start_date'):
                try:
                    date_str = p['start_date'].replace('.', '')
                    return (1, int(date_str))
                except Exception:
                    return (2, 0)
            return (2, 0)

        filtered_list.sort(key=sort_key)

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

        # KOPIS 데이터 - 콘서트, 뮤지컬, 연극 모두 조회
        kopis_genres = [
            (GENRE_CODE_CONCERT, 'concert'),   # 대중음악/콘서트
            (GENRE_CODE_MUSICAL, 'theater'),   # 뮤지컬
            (GENRE_CODE_THEATER, 'theater')    # 연극
        ]

        for genre_code, part_type in kopis_genres:
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

                        # 콘서트 세부 장르 분류
                        sub_category = categorize_concert(name)
                        # 파트 분류
                        perf_part = classify_part(name, genre_name) if part_type == 'concert' else part_type

                        perf = {
                            'id': db.find('mt20id').text if db.find('mt20id') is not None else '',
                            'name': name,
                            'start_date': db.find('prfpdfrom').text if db.find('prfpdfrom') is not None else '',
                            'end_date': db.find('prfpdto').text if db.find('prfpdto') is not None else '',
                            'venue': venue_name,
                            'poster': db.find('poster').text if db.find('poster') is not None else '',
                            'genre': genre_name,
                            'category': sub_category,  # 세부 장르
                            'part': perf_part,  # 파트: concert / theater
                            'region': classify_region(venue_name, area),  # 지역 분류
                            'state': db.find('prfstate').text if db.find('prfstate') is not None else '',
                            'hash': perf_hash,
                            'available_sites': [{
                                'name': 'KOPIS',
                                'link': '',
                                'color': '#00d4ff'
                            }]
                        }
                        merged_performances[perf_hash] = perf
                        source_counts['kopis'] += 1
            except Exception as e:
                pass

        # 인터파크 데이터
        try:
            interpark_response = get_interpark_tickets()
            interpark_data = interpark_response.get_json()
            if interpark_data.get('success'):
                for item in interpark_data.get('data', []):
                    perf_hash = get_cache_key(normalize_name(item.get('name', '')))
                    source_counts['interpark'] += 1

                    if perf_hash in merged_performances:
                        # 기존 공연에 판매처 추가
                        merged_performances[perf_hash] = merge_performance_data(
                            merged_performances[perf_hash], item, '인터파크'
                        )
                    else:
                        # 새 공연 추가
                        item['available_sites'] = [{
                            'name': '인터파크',
                            'link': item.get('link', ''),
                            'color': '#ff6464'
                        }]
                        item['hash'] = perf_hash
                        if 'part' not in item:
                            item['part'] = classify_part(item.get('name', ''))
                        if 'region' not in item:
                            item['region'] = classify_region(item.get('venue', ''))
                        merged_performances[perf_hash] = item
        except Exception:
            pass

        # 멜론티켓 데이터 (skip_selenium이면 건너뜀)
        if not skip_selenium:
            try:
                melon_response = get_melon_tickets()
                melon_data = melon_response.get_json()
                if melon_data.get('success'):
                    for item in melon_data.get('data', []):
                        perf_hash = get_cache_key(normalize_name(item.get('name', '')))
                        source_counts['melon'] += 1

                        if perf_hash in merged_performances:
                            merged_performances[perf_hash] = merge_performance_data(
                                merged_performances[perf_hash], item, '멜론티켓'
                            )
                        else:
                            item['available_sites'] = [{
                                'name': '멜론티켓',
                                'link': item.get('link', ''),
                                'color': '#00cd3c'
                            }]
                            item['hash'] = perf_hash
                            if 'part' not in item:
                                item['part'] = classify_part(item.get('name', ''))
                            if 'region' not in item:
                                item['region'] = classify_region(item.get('venue', ''))
                            merged_performances[perf_hash] = item
            except Exception:
                pass

        # YES24 데이터 (skip_selenium이면 건너뜀)
        if not skip_selenium:
            try:
                yes24_response = get_yes24_tickets()
                yes24_data = yes24_response.get_json()
                if yes24_data.get('success'):
                    for item in yes24_data.get('data', []):
                        perf_hash = get_cache_key(normalize_name(item.get('name', '')))
                        source_counts['yes24'] += 1

                        if perf_hash in merged_performances:
                            merged_performances[perf_hash] = merge_performance_data(
                                merged_performances[perf_hash], item, 'YES24'
                            )
                        else:
                            item['available_sites'] = [{
                                'name': 'YES24',
                                'link': item.get('link', ''),
                                'color': '#ffc800'
                            }]
                            item['hash'] = perf_hash
                            if 'part' not in item:
                                item['part'] = classify_part(item.get('name', ''))
                            if 'region' not in item:
                                item['region'] = classify_region(item.get('venue', ''))
                            merged_performances[perf_hash] = item
            except Exception:
                pass

        # 리스트로 변환
        performances_list = list(merged_performances.values())

        # 파트 필터 적용
        if part_filter:
            performances_list = [p for p in performances_list if p.get('part') == part_filter]

        # 지역 필터 적용
        if region_filter:
            performances_list = [p for p in performances_list if p.get('region') == region_filter]

        # 끝난 공연 제외 (종료일이 오늘 이전인 공연)
        today_str = datetime.now().strftime('%Y.%m.%d')
        filtered_list = []
        for p in performances_list:
            end_date = p.get('end_date') or p.get('start_date') or p.get('date', '')
            # 날짜 형식 통일 (YYYY.MM.DD)
            if end_date:
                # 다양한 형식 처리
                end_clean = re.sub(r'[^\d.]', '', end_date)[:10]
                if len(end_clean) >= 8:
                    try:
                        if '.' in end_clean:
                            parts = end_clean.split('.')
                            if len(parts) >= 3:
                                end_formatted = f"{parts[0]}.{parts[1].zfill(2)}.{parts[2].zfill(2)}"
                        else:
                            end_formatted = f"{end_clean[:4]}.{end_clean[4:6]}.{end_clean[6:8]}"

                        # 오늘 이후 공연만 포함
                        if end_formatted >= today_str:
                            filtered_list.append(p)
                        continue
                    except Exception:
                        pass
            # 날짜 파싱 실패시 일단 포함
            filtered_list.append(p)

        performances_list = filtered_list

        # 정렬: D-day 있는 것 우선, 그 다음 공연일 순
        def sort_key(p):
            dday = p.get('dday')
            if dday is not None and dday >= 0:
                return (0, dday)  # D-day 있고 미래: 가까운 순
            elif p.get('start_date'):
                try:
                    date_str = p['start_date'].replace('.', '')
                    return (1, int(date_str))  # D-day 없음: 공연일 순
                except Exception:
                    return (2, 0)
            return (2, 0)

        performances_list.sort(key=sort_key)

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


# 이미지 캐시 설정
IMAGE_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'image_cache')
IMAGE_CACHE_HOURS = 24  # 캐시 유효 시간
MAX_CACHE_FILES = 500   # 최대 캐시 파일 수
MAX_CACHE_SIZE_MB = 200 # 최대 캐시 크기 (MB)

# 캐시 폴더 생성
if not os.path.exists(IMAGE_CACHE_DIR):
    os.makedirs(IMAGE_CACHE_DIR)


def cleanup_old_cache():
    """오래된 캐시 파일 삭제 + 크기/수량 제한"""
    try:
        now = datetime.now()
        files = []
        total_size = 0

        for filename in os.listdir(IMAGE_CACHE_DIR):
            filepath = os.path.join(IMAGE_CACHE_DIR, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                file_size = os.path.getsize(filepath)

                # 24시간 초과 파일 삭제
                if (now - file_time).total_seconds() > IMAGE_CACHE_HOURS * 3600:
                    os.remove(filepath)
                    continue

                files.append((filepath, file_time, file_size))
                total_size += file_size

        # 수량 제한 초과 시 오래된 것부터 삭제
        if len(files) > MAX_CACHE_FILES:
            files.sort(key=lambda x: x[1])
            for filepath, _, file_size in files[:len(files) - MAX_CACHE_FILES]:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    total_size -= file_size

        # 크기 제한 초과 시 오래된 것부터 삭제
        if total_size > MAX_CACHE_SIZE_MB * 1024 * 1024:
            remaining = [(f, t, s) for f, t, s in files if os.path.exists(f)]
            remaining.sort(key=lambda x: x[1])
            for filepath, _, file_size in remaining:
                if total_size <= MAX_CACHE_SIZE_MB * 1024 * 1024:
                    break
                if os.path.exists(filepath):
                    os.remove(filepath)
                    total_size -= file_size

    except Exception as e:
        logging.warning(f"캐시 정리 실패: {e}")


@app.route('/api/proxy/image')
def proxy_image():
    """외부 이미지 프록시 (캐싱 지원)"""
    url = request.args.get('url', '')
    if not url:
        return '', 404

    # SSRF 방어: URL 안전성 검증
    if not is_safe_url(url):
        return '', 403

    # URL을 해시로 변환하여 파일명 생성
    url_hash = hashlib.md5(url.encode()).hexdigest()
    ext = '.jpg'  # 기본 확장자
    if '.png' in url.lower():
        ext = '.png'
    elif '.gif' in url.lower():
        ext = '.gif'
    elif '.webp' in url.lower():
        ext = '.webp'

    cache_path = os.path.join(IMAGE_CACHE_DIR, url_hash + ext)

    # 캐시에 있으면 바로 반환
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                content = f.read()
            content_type = 'image/jpeg'
            if ext == '.png':
                content_type = 'image/png'
            elif ext == '.gif':
                content_type = 'image/gif'
            elif ext == '.webp':
                content_type = 'image/webp'
            return content, 200, {'Content-Type': content_type, 'Cache-Control': 'max-age=86400'}
        except Exception:
            pass

    # 캐시에 없으면 다운로드
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://ticket.yes24.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        }

        # 멜론 이미지는 Referer 변경
        if 'melon' in url:
            headers['Referer'] = 'https://ticket.melon.com/'

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            content = response.content
            content_type = response.headers.get('Content-Type', 'image/jpeg')

            # YES24 로고 이미지 감지 (약 5KB 미만이고 특정 패턴)
            # 로고 이미지는 보통 작은 크기
            if len(content) < 10000:  # 10KB 미만
                # 이미지 해시로 로고 감지
                img_hash = hashlib.md5(content).hexdigest()
                # 알려진 로고 해시들 (필요시 추가)
                logo_hashes = [
                    '7f9b8c5a3d2e1f4b',  # 예시
                ]
                # 너무 작은 이미지는 로고로 간주
                if len(content) < 3000:
                    return '', 404

            # 캐시에 저장
            try:
                with open(cache_path, 'wb') as f:
                    f.write(content)
            except Exception:
                pass

            # 가끔 오래된 캐시 정리
            if hash(url) % 100 == 0:
                cleanup_old_cache()

            return content, 200, {'Content-Type': content_type, 'Cache-Control': 'max-age=86400'}
        else:
            return '', response.status_code
    except Exception as e:
        return '', 500


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

SUPPORTED_LANGS = ['ko', 'en', 'ja', 'zh', 'es']
TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), 'translations')

_ui_translations = {}

def load_ui_translations():
    """PO 파일에서 UI 번역을 메모리에 로드"""
    global _ui_translations
    _ui_translations = {}
    for lang in SUPPORTED_LANGS:
        po_path = os.path.join(TRANSLATIONS_DIR, lang, 'LC_MESSAGES', 'messages.po')
        try:
            po = polib.pofile(po_path)
            _ui_translations[lang] = {entry.msgid: entry.msgstr for entry in po if entry.msgid}
        except Exception as e:
            logging.warning(f"PO 파일 로드 실패 ({lang}): {e}")
            _ui_translations[lang] = {}

load_ui_translations()


@app.route('/api/i18n/<lang>')
def get_ui_translations(lang):
    """UI 번역을 JSON으로 반환"""
    if lang not in SUPPORTED_LANGS:
        lang = 'ko'
    translations = _ui_translations.get(lang, _ui_translations.get('ko', {}))
    response = jsonify(translations)
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


# ============================================================
# 번역 API (MyMemory) - 서버 사이드 전용
# ============================================================

# 영속 번역 캐시
TRANSLATION_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'translation_cache.json')

def load_translation_cache():
    """JSON 파일에서 번역 캐시 로드"""
    try:
        if os.path.exists(TRANSLATION_CACHE_FILE):
            with open(TRANSLATION_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.warning(f"번역 캐시 로드 실패: {e}")
    return {}

def save_translation_cache():
    """번역 캐시를 JSON 파일에 저장"""
    try:
        with translation_cache_lock:
            data = dict(translation_cache)
        with open(TRANSLATION_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning(f"번역 캐시 저장 실패: {e}")

translation_cache = load_translation_cache()
translation_cache_lock = threading.Lock()

# 언어 코드 매핑 (MyMemory용)
LANG_CODES = {
    'ko': 'ko',
    'en': 'en',
    'ja': 'ja',
    'zh': 'zh-CN',
    'es': 'es'
}

def translate_text(text, from_lang='ko', to_lang='en'):
    """MyMemory API로 텍스트 번역"""
    if not text or from_lang == to_lang:
        return text

    # 캐시 키 (text|to_lang 형식으로 통일)
    cache_key = f"{text}|{to_lang}"

    with translation_cache_lock:
        if cache_key in translation_cache:
            return translation_cache[cache_key]
        # 이전 형식 호환 (text|from|to)
        old_key = f"{text}|{from_lang}|{to_lang}"
        if old_key in translation_cache:
            return translation_cache[old_key]

    try:
        # MyMemory API 호출
        from_code = LANG_CODES.get(from_lang, from_lang)
        to_code = LANG_CODES.get(to_lang, to_lang)

        url = "https://api.mymemory.translated.net/get"
        params = {
            'q': text[:500],  # 최대 500자
            'langpair': f"{from_code}|{to_code}"
        }

        response = requests.get(url, params=params, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('responseStatus') == 200:
                translated = data.get('responseData', {}).get('translatedText', text)

                # 캐시에 저장
                with translation_cache_lock:
                    translation_cache[cache_key] = translated

                return translated
    except Exception as e:
        logging.debug(f"번역 API 오류: {e}")

    return text


@app.route('/api/translate')
def translate_api():
    """텍스트 번역 API (deprecated: 프론트엔드에서 더 이상 사용하지 않음. 디버깅용으로 유지)"""
    text = request.args.get('text', '')
    to_lang = request.args.get('to', 'en')
    from_lang = request.args.get('from', 'ko')

    if not text:
        return jsonify({'success': False, 'error': '텍스트가 필요합니다.'})

    translated = translate_text(text, from_lang, to_lang)

    return jsonify({
        'success': True,
        'original': text,
        'translated': translated,
        'from': from_lang,
        'to': to_lang
    })


@app.route('/api/translate/batch', methods=['POST'])
def translate_batch_api():
    """여러 텍스트 일괄 번역 API (deprecated: 프론트엔드에서 더 이상 사용하지 않음. 디버깅용으로 유지)"""
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'JSON 데이터가 필요합니다.'})

    texts = data.get('texts', [])
    to_lang = data.get('to', 'en')
    from_lang = data.get('from', 'ko')

    if not texts:
        return jsonify({'success': False, 'error': '번역할 텍스트가 없습니다.'})

    results = []
    for text in texts[:50]:  # 최대 50개
        translated = translate_text(text, from_lang, to_lang)
        results.append({
            'original': text,
            'translated': translated
        })
        # API 부하 방지 (0.1초 딜레이)
        time_module.sleep(0.1)

    return jsonify({
        'success': True,
        'results': results,
        'from': from_lang,
        'to': to_lang
    })


# ============================================================
# 스크래핑 시 공연 데이터 사전 번역
# ============================================================

def translate_performance_data(performances):
    """스크래핑 시 공연 name/venue를 4개 언어로 사전 번역"""
    global translation_cache
    target_langs = [l for l in SUPPORTED_LANGS if l != 'ko']

    # 번역이 필요한 텍스트 수집 (중복 제거)
    texts_to_translate = []
    for perf in performances:
        for field in ['name', 'venue']:
            text = perf.get(field, '')
            if not text:
                continue
            for lang in target_langs:
                cache_key = f"{text}|{lang}"
                if cache_key not in translation_cache:
                    texts_to_translate.append((text, lang, cache_key))

    # 중복 제거
    seen = set()
    unique_texts = []
    for text, lang, cache_key in texts_to_translate:
        if cache_key not in seen:
            seen.add(cache_key)
            unique_texts.append((text, lang, cache_key))

    # MyMemory API로 번역 (rate limiting 적용)
    for text, lang, cache_key in unique_texts:
        translated = translate_text(text, 'ko', lang)
        with translation_cache_lock:
            translation_cache[cache_key] = translated
        time_module.sleep(0.1)

    # 번역 결과를 공연 데이터에 flat key로 추가
    for perf in performances:
        for field in ['name', 'venue']:
            text = perf.get(field, '')
            for lang in target_langs:
                cache_key = f"{text}|{lang}"
                with translation_cache_lock:
                    perf[f"{field}_{lang}"] = translation_cache.get(cache_key, text)

    # 캐시 파일에 저장
    save_translation_cache()


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
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, port=port, host='0.0.0.0', use_reloader=False)
