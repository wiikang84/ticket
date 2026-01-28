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

# 장르 코드
GENRE_CODES = {
    "연극": "AAAA",
    "무용": "BBBC",
    "클래식": "CCCA",
    "콘서트": "CCCD",
    "뮤지컬": "GGGA",
    "복합": "EEEA"
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
    """KOPIS API로 공연 상세 정보 조회"""
    try:
        params = {'service': KOPIS_API_KEY}
        response = requests.get(f"{KOPIS_BASE_URL}/pblprfr/{perf_id}", params=params, timeout=10)

        if response.status_code == 200:
            root = ET.fromstring(response.content)
            db = root.find('.//db')

            if db is not None:
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
                    'schedule': db.find('dtguidance').text if db.find('dtguidance') is not None else ''
                }
                return jsonify({'success': True, 'data': detail})

        return jsonify({'success': False, 'error': '공연 정보를 찾을 수 없습니다.'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/ticketing/interpark')
def get_interpark_tickets():
    """인터파크 티켓오픈 예정 조회"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        }

        tickets = []

        # 콘서트 카테고리 페이지
        urls = [
            "https://tickets.interpark.com/contents/genre/concert",
            "https://tickets.interpark.com/contents/genre/musical"
        ]

        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # 다양한 선택자 시도
                    items = soup.select('[class*="RankItem"], [class*="Product"], [class*="item"], .concert-item, .musical-item')

                    for item in items[:30]:
                        try:
                            # 제목 찾기
                            title_el = item.select_one('[class*="title"], [class*="name"], h3, h4, a')
                            if not title_el:
                                continue

                            title = title_el.get_text(strip=True)
                            if not title or len(title) < 2:
                                continue

                            # 날짜 찾기
                            date_el = item.select_one('[class*="date"], [class*="period"], time')
                            date_text = date_el.get_text(strip=True) if date_el else ''

                            # 장소 찾기
                            venue_el = item.select_one('[class*="place"], [class*="venue"], [class*="location"]')
                            venue = venue_el.get_text(strip=True) if venue_el else ''

                            # 티켓오픈일 찾기
                            open_el = item.select_one('[class*="open"], [class*="ticket"]')
                            ticket_open = open_el.get_text(strip=True) if open_el else ''

                            # 링크 찾기
                            link_el = item.select_one('a[href]')
                            link = link_el.get('href', '') if link_el else ''
                            if link and not link.startswith('http'):
                                link = 'https://tickets.interpark.com' + link

                            # 이미지 찾기
                            img_el = item.select_one('img')
                            poster = img_el.get('src', '') if img_el else ''

                            # D-day 계산
                            dday = calculate_dday(ticket_open) if ticket_open else None

                            tickets.append({
                                'name': title[:100],
                                'date': date_text,
                                'venue': venue,
                                'ticket_open': ticket_open,
                                'dday': dday,
                                'poster': poster,
                                'source': '인터파크',
                                'source_color': '#ff6464',
                                'link': link or 'https://tickets.interpark.com',
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


@app.route('/api/all')
def get_all_data():
    """모든 소스에서 데이터 통합 조회 (중복 제거)"""
    try:
        start_date = request.args.get('start_date', datetime.now().strftime('%Y%m%d'))
        end_date = request.args.get('end_date', (datetime.now() + timedelta(days=60)).strftime('%Y%m%d'))
        genre = request.args.get('genre', '')

        all_data = {
            'kopis': [],
            'interpark': [],
            'melon': [],
            'yes24': [],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

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

            response = requests.get(f"{KOPIS_BASE_URL}/pblprfr", params=params, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for db in root.findall('.//db'):
                    name = db.find('prfnm').text if db.find('prfnm') is not None else ''
                    all_data['kopis'].append({
                        'id': db.find('mt20id').text if db.find('mt20id') is not None else '',
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
                    })
        except Exception as e:
            all_data['kopis_error'] = str(e)

        # KOPIS 공연명 해시 수집 (중복 체크용)
        kopis_hashes = set(item['hash'] for item in all_data['kopis'])

        # 인터파크 데이터 (KOPIS와 중복 제외)
        try:
            interpark_response = get_interpark_tickets()
            interpark_data = interpark_response.get_json()
            if interpark_data.get('success'):
                for item in interpark_data.get('data', []):
                    if item['hash'] not in kopis_hashes:
                        all_data['interpark'].append(item)
        except:
            pass

        # 멜론티켓 데이터 (KOPIS와 중복 제외)
        try:
            melon_response = get_melon_tickets()
            melon_data = melon_response.get_json()
            if melon_data.get('success'):
                for item in melon_data.get('data', []):
                    if item['hash'] not in kopis_hashes:
                        all_data['melon'].append(item)
        except:
            pass

        # YES24 데이터 (KOPIS와 중복 제외)
        try:
            yes24_response = get_yes24_tickets()
            yes24_data = yes24_response.get_json()
            if yes24_data.get('success'):
                for item in yes24_data.get('data', []):
                    if item['hash'] not in kopis_hashes:
                        all_data['yes24'].append(item)
        except:
            pass

        return jsonify({
            'success': True,
            'data': all_data,
            'stats': {
                'kopis': len(all_data['kopis']),
                'interpark': len(all_data['interpark']),
                'melon': len(all_data['melon']),
                'yes24': len(all_data['yes24']),
                'total': len(all_data['kopis']) + len(all_data['interpark']) + len(all_data['melon']) + len(all_data['yes24'])
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
