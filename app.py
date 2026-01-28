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

app = Flask(__name__)
CORS(app)

# KOPIS API 설정
KOPIS_API_KEY = "2012e419e6c24bfa988ca56e2917d3c0"
KOPIS_BASE_URL = "http://www.kopis.or.kr/openApi/restful"

# 콘서트/대중음악만 조회
GENRE_CODE_CONCERT = "CCCD"  # 대중음악/콘서트

# 콘서트 세부 장르 분류 키워드
CONCERT_CATEGORIES = {
    "아이돌": ["BTS", "방탄", "에이핑크", "Apink", "제로베이스원", "ZEROBASE", "아이브", "IVE",
              "르세라핌", "SSERAFIM", "뉴진스", "NewJeans", "스트레이키즈", "Stray Kids",
              "엔시티", "NCT", "세븐틴", "SEVENTEEN", "블랙핑크", "BLACKPINK", "에스파", "aespa",
              "투모로우바이투게더", "TXT", "엔하이픈", "ENHYPEN", "있지", "ITZY", "케플러", "Kep1er"],
    "발라드": ["먼데이키즈", "임재범", "성시경", "이수", "엠씨더맥스", "MC THE MAX", "나얼",
              "박효신", "김범수", "휘성", "거미", "이적", "10CM", "폴킴"],
    "랩/힙합": ["다이나믹듀오", "Dynamic Duo", "쇼미", "힙합", "래퍼", "Rapper", "AOMG", "하이어뮤직"],
    "락/인디": ["밴드", "Band", "록", "Rock", "인디", "Indie", "데이식스", "DAY6"],
    "내한공연": ["내한", "World Tour", "Asia Tour", "Live in Seoul", "Live in Korea", "in Seoul"],
    "팬미팅": ["팬미팅", "Fan Meeting", "팬콘", "FAN-CON", "팬콘서트"],
    "페스티벌": ["페스티벌", "Festival", "뮤직페스타", "Music Festa"],
    "트로트": ["트롯", "트로트", "미스터트롯", "미스트롯", "송가인", "임영웅", "영탁"]
}

# 캐시 저장소 (하루 2회 업데이트용)
cache = {
    'data': None,
    'last_update': None
}


def get_cache_key(data):
    """중복 체크용 해시 생성"""
    return hashlib.md5(data.encode('utf-8')).hexdigest()[:10]


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
    except:
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
                    'hash': get_cache_key(name)
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
        return jsonify({'success': False, 'error': str(e)})


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
        return jsonify({'success': False, 'error': str(e)})


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

                    # JSON 객체 패턴으로 공연 정보 추출
                    # {"goodsCode":"26000365","goodsName":"...","placeName":"...","posterImageUrl":"...","playStartDate":"..."}
                    goods_pattern = r'\{"goodsCode":"(\d+)","goodsName":"([^"]+)"[^}]*"placeName":"([^"]*)"[^}]*"posterImageUrl":"([^"]*)"[^}]*"playStartDate":"(\d+)"[^}]*"playEndDate":"(\d+)"'
                    matches = re.findall(goods_pattern, html)

                    for match in matches:
                        goods_code, goods_name, place_name, poster_url, start_date, end_date = match

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
                        except:
                            date_str = ''

                        tickets.append({
                            'name': goods_name,
                            'date': date_str,
                            'venue': place_name,
                            'poster': poster,
                            'source': '인터파크',
                            'source_color': '#ff6464',
                            'link': link,
                            'category': categorize_concert(goods_name),  # 세부 장르
                            'hash': get_cache_key(goods_name)
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
        return jsonify({'success': False, 'error': str(e), 'source': '인터파크', 'data': []})


@app.route('/api/ticketing/melon')
def get_melon_tickets():
    """멜론티켓 오픈예정 조회"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        tickets = []
        url = "https://ticket.melon.com/csoon/index.htm"

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # 멜론티켓 목록 아이템
            items = soup.select('.list_ticket li, .ticket_list li, [class*="item"], .csoon_list li')

            for item in items[:30]:
                try:
                    # 제목
                    title_el = item.select_one('.tit, .title, a, h3')
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not title or len(title) < 2:
                        continue

                    # 티켓오픈일
                    open_el = item.select_one('.date, .open_date, [class*="date"]')
                    ticket_open = open_el.get_text(strip=True) if open_el else ''

                    # 링크
                    link_el = item.select_one('a[href]')
                    link = link_el.get('href', '') if link_el else ''
                    if link and not link.startswith('http'):
                        link = 'https://ticket.melon.com' + link

                    # 이미지
                    img_el = item.select_one('img')
                    poster = img_el.get('src', '') if img_el else ''

                    # D-day 계산
                    dday = calculate_dday(ticket_open) if ticket_open else None

                    tickets.append({
                        'name': title[:100],
                        'ticket_open': ticket_open,
                        'dday': dday,
                        'poster': poster,
                        'source': '멜론티켓',
                        'source_color': '#00cd3c',
                        'link': link or 'https://ticket.melon.com',
                        'hash': get_cache_key(title)
                    })
                except:
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
            'source': '멜론티켓',
            'count': len(unique_tickets)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'source': '멜론티켓', 'data': []})


@app.route('/api/ticketing/yes24')
def get_yes24_tickets():
    """YES24 티켓 콘서트/뮤지컬 조회"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        tickets = []

        # 콘서트, 뮤지컬 카테고리
        urls = [
            "http://ticket.yes24.com/New/Genre/GenreMain.aspx?genre=15457",  # 콘서트
            "http://ticket.yes24.com/New/Genre/GenreMain.aspx?genre=15458"   # 뮤지컬
        ]

        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')

                    items = soup.select('.list-item, .item, [class*="product"], .rank-item, li[class*="item"]')

                    for item in items[:20]:
                        try:
                            # 제목
                            title_el = item.select_one('.title, .tit, a, .name, h3')
                            if not title_el:
                                continue
                            title = title_el.get_text(strip=True)
                            if not title or len(title) < 2:
                                continue

                            # 날짜
                            date_el = item.select_one('.date, .period, [class*="date"]')
                            date_text = date_el.get_text(strip=True) if date_el else ''

                            # 장소
                            venue_el = item.select_one('.place, .venue, [class*="place"]')
                            venue = venue_el.get_text(strip=True) if venue_el else ''

                            # 링크
                            link_el = item.select_one('a[href]')
                            link = link_el.get('href', '') if link_el else ''
                            if link and not link.startswith('http'):
                                link = 'http://ticket.yes24.com' + link

                            # 이미지
                            img_el = item.select_one('img')
                            poster = img_el.get('src', '') if img_el else ''

                            tickets.append({
                                'name': title[:100],
                                'date': date_text,
                                'venue': venue,
                                'poster': poster,
                                'source': 'YES24',
                                'source_color': '#ffc800',
                                'link': link or 'http://ticket.yes24.com',
                                'hash': get_cache_key(title)
                            })
                        except:
                            continue
            except:
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
            'source': 'YES24',
            'count': len(unique_tickets)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'source': 'YES24', 'data': []})


def normalize_name(name):
    """공연명 정규화 (매칭 정확도 향상)"""
    if not name:
        return ''
    # 특수문자, 공백 제거 후 소문자로
    normalized = re.sub(r'[^\w가-힣]', '', name).lower()
    return normalized


def categorize_concert(name):
    """공연명으로 콘서트 세부 장르 분류"""
    if not name:
        return "기타"

    name_upper = name.upper()

    for category, keywords in CONCERT_CATEGORIES.items():
        for keyword in keywords:
            if keyword.upper() in name_upper:
                return category

    return "기타"


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


@app.route('/api/all')
def get_all_data():
    """모든 소스에서 데이터 통합 조회 (공연 기준 통합 + 판매처 표시)"""
    try:
        start_date = request.args.get('start_date', datetime.now().strftime('%Y%m%d'))
        end_date = request.args.get('end_date', (datetime.now() + timedelta(days=60)).strftime('%Y%m%d'))
        genre = request.args.get('genre', '')

        # 통합 공연 목록 (hash -> 공연 정보)
        merged_performances = {}
        source_counts = {'kopis': 0, 'interpark': 0, 'melon': 0, 'yes24': 0}

        # KOPIS 데이터
        try:
            params = {
                'service': KOPIS_API_KEY,
                'stdate': start_date,
                'eddate': end_date,
                'cpage': '1',
                'rows': '50'
            }
            if genre and genre in GENRE_CODES:
                params['shcate'] = GENRE_CODES[genre]

            # 콘서트/대중음악만 조회
            params['shcate'] = GENRE_CODE_CONCERT

            response = requests.get(f"{KOPIS_BASE_URL}/pblprfr", params=params, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for db in root.findall('.//db'):
                    name = db.find('prfnm').text if db.find('prfnm') is not None else ''
                    genre_name = db.find('genrenm').text if db.find('genrenm') is not None else ''

                    perf_hash = get_cache_key(normalize_name(name))

                    # 콘서트 세부 장르 분류
                    sub_category = categorize_concert(name)

                    perf = {
                        'id': db.find('mt20id').text if db.find('mt20id') is not None else '',
                        'name': name,
                        'start_date': db.find('prfpdfrom').text if db.find('prfpdfrom') is not None else '',
                        'end_date': db.find('prfpdto').text if db.find('prfpdto') is not None else '',
                        'venue': db.find('fcltynm').text if db.find('fcltynm') is not None else '',
                        'poster': db.find('poster').text if db.find('poster') is not None else '',
                        'genre': genre_name,
                        'category': sub_category,  # 세부 장르
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
                        merged_performances[perf_hash] = item
        except:
            pass

        # 멜론티켓 데이터
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
                        merged_performances[perf_hash] = item
        except:
            pass

        # YES24 데이터
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
                        merged_performances[perf_hash] = item
        except:
            pass

        # 리스트로 변환
        performances_list = list(merged_performances.values())

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
                    except:
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
                except:
                    return (2, 0)
            return (2, 0)

        performances_list.sort(key=sort_key)

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
        return jsonify({'success': False, 'error': str(e)})


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


if __name__ == '__main__':
    print("=" * 50)
    print("  티켓팅 통합 정보 시스템 v2.0")
    print("  - KOPIS + 인터파크 + 멜론티켓 + YES24")
    print("  - 중복 제거 / 상세 팝업 / 예매처 링크")
    print("=" * 50)
    print("  브라우저에서 http://localhost:5000 접속")
    print("=" * 50)
    app.run(debug=True, port=5000)
