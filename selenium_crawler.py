# -*- coding: utf-8 -*-
"""
Selenium 크롤러 (별도 프로세스)
멜론티켓, YES24 동적 페이지 크롤링
"""

import sys
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import time
import hashlib

def get_cache_key(data):
    """중복 체크용 해시 생성"""
    return hashlib.md5(data.encode('utf-8')).hexdigest()[:10]

# 콘서트 세부 장르 분류 키워드
CONCERT_CATEGORIES = {
    "아이돌": ["BTS", "방탄", "에이핑크", "Apink", "제로베이스원", "ZEROBASE", "아이브", "IVE",
              "르세라핌", "SSERAFIM", "뉴진스", "NewJeans", "스트레이키즈", "Stray Kids",
              "엔시티", "NCT", "세븐틴", "SEVENTEEN", "블랙핑크", "BLACKPINK", "에스파", "aespa",
              "엑소", "EXO", "샤이니", "SHINee", "레드벨벳", "Red Velvet", "트와이스", "TWICE"],
    "발라드": ["먼데이키즈", "임재범", "성시경", "10CM", "아이유", "IU", "백예린", "헤이즈"],
    "랩/힙합": ["다이나믹듀오", "박재범", "지코", "ZICO", "창모"],
    "트로트": ["트롯", "트로트", "미스터트롯", "송가인", "임영웅", "영탁"],
    "내한공연": ["내한", "World Tour", "Asia Tour", "Live in Seoul"],
    "팬미팅": ["팬미팅", "Fan Meeting", "팬콘", "FAN-CON"],
}

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

def get_driver():
    """헤드리스 크롬 드라이버 생성 (봇 탐지 우회)"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # webdriver 속성 숨기기
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        '''
    })

    return driver


def get_undetected_driver():
    """undetected-chromedriver로 봇 차단 우회 (비표시 모드)"""
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--log-level=3')
    # 창을 화면 밖으로 이동 (headless 대신)
    options.add_argument('--window-position=-2400,-2400')

    # headless=False로 실행 (봇 탐지 우회)
    driver = uc.Chrome(options=options, headless=False, version_main=144)
    return driver

def crawl_melon():
    """멜론티켓 콘서트 크롤링"""
    tickets = []
    driver = None
    import re

    try:
        driver = get_driver()
        driver.get("https://ticket.melon.com/concert/index.htm")
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # show_infor div에서 공연 정보 추출
        show_infors = soup.select('div.show_infor')

        for info in show_infors:
            try:
                # 링크 찾기
                link = info.select_one('a[href*="prodId"]')
                if not link:
                    continue

                href = link.get('href', '')
                prod_match = re.search(r'prodId=(\d+)', href)
                if not prod_match:
                    continue
                prod_id = prod_match.group(1)

                # 제목 - show_infor 전체 텍스트에서 추출
                full_text = info.get_text(strip=True, separator=' ')

                # 특수문자 제거 (nbsp 등)
                full_text = full_text.replace('\xa0', ' ').replace('\u200b', '')

                # "판매중" 또는 "단독판매" 등의 태그 제거
                title = full_text
                for tag in ['단독판매', '판매중', '판매예정', '판매종료']:
                    title = title.replace(tag, '')
                title = ' '.join(title.split())  # 공백 정리

                if not title or len(title) < 3:
                    continue

                # 카테고리 메뉴 필터
                if title in ['콘서트', '뮤지컬/연극', '클래식', '전시/행사']:
                    continue

                # 이미지 찾기
                poster = ''
                img = info.select_one('img')
                if img:
                    poster = img.get('src', '') or img.get('data-src', '')
                    if poster and poster.startswith('//'):
                        poster = 'https:' + poster

                # 링크 생성
                full_link = f'https://ticket.melon.com/performance/index.htm?prodId={prod_id}'

                tickets.append({
                    'name': title[:100],
                    'date': '',
                    'venue': '',
                    'poster': poster,
                    'source': '멜론티켓',
                    'source_color': '#00cd3c',
                    'link': full_link,
                    'category': categorize_concert(title),
                    'hash': get_cache_key(title)
                })
            except:
                continue

    except Exception as e:
        return {'success': False, 'error': str(e), 'data': []}
    finally:
        if driver:
            driver.quit()

    # 중복 제거
    seen = set()
    unique = [t for t in tickets if not (t['hash'] in seen or seen.add(t['hash']))]

    return {'success': True, 'data': unique, 'count': len(unique)}

def crawl_yes24():
    """YES24 콘서트 크롤링 (undetected-chromedriver)"""
    tickets = []
    driver = None
    import re

    try:
        # undetected-chromedriver 사용 (봇 차단 우회)
        driver = get_undetected_driver()
        driver.get("https://ticket.yes24.com/New/Genre/GenreMain.aspx?genre=15457")
        time.sleep(7)  # 페이지 로딩 대기

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # YES24 공연 목록 구조 파싱
        # 랭킹 리스트 또는 상품 리스트 찾기
        items = soup.select('.rank-best li, .list-item, .goods-item, li[class*="item"], .content-list li')

        # 링크에서 공연 정보 추출
        perf_links = soup.select('a[href*="PerfCode"], a[href*="Perf/"], a[href*="/New/Perf"]')
        seen_codes = set()

        for link in perf_links:
            try:
                href = link.get('href', '')
                if not href:
                    continue

                # PerfCode 추출
                code_match = re.search(r'PerfCode=(\d+)', href) or re.search(r'/Perf/(\d+)', href)
                if not code_match:
                    continue
                perf_code = code_match.group(1)

                if perf_code in seen_codes:
                    continue
                seen_codes.add(perf_code)

                # 제목 찾기
                title = link.get('title', '')
                if not title:
                    title = link.get_text(strip=True)

                # 부모에서 제목 찾기
                if not title or len(title) < 3:
                    parent = link.parent
                    for _ in range(3):
                        if parent:
                            title_el = parent.select_one('.goods-name, .tit, .title, strong, h3, h4, p')
                            if title_el:
                                title = title_el.get_text(strip=True)
                                if title and len(title) >= 3:
                                    break
                            parent = parent.parent

                if not title or len(title) < 3:
                    continue

                # 특수문자 정리
                title = title.replace('\xa0', ' ').replace('\u200b', '')
                title = ' '.join(title.split())

                # 필터
                if any(kw in title for kw in ['프로모션', '혜택', '이벤트', '광고']):
                    continue

                # 이미지 찾기
                poster = ''
                img = link.select_one('img')
                if not img:
                    parent = link.parent
                    if parent:
                        img = parent.select_one('img')
                if img:
                    poster = img.get('src', '') or img.get('data-src', '')
                    if poster:
                        if poster.startswith('//'):
                            poster = 'https:' + poster
                        elif not poster.startswith('http'):
                            poster = 'https://ticket.yes24.com' + poster

                # 날짜/장소 찾기 (부모에서)
                date_text = ''
                venue = ''
                parent = link.parent
                if parent:
                    date_el = parent.select_one('.date, .period, [class*="date"]')
                    if date_el:
                        date_text = date_el.get_text(strip=True)
                    venue_el = parent.select_one('.place, .venue, [class*="place"]')
                    if venue_el:
                        venue = venue_el.get_text(strip=True)

                full_link = f'https://ticket.yes24.com/Perf/{perf_code}'

                tickets.append({
                    'name': title[:100],
                    'date': date_text,
                    'venue': venue,
                    'poster': poster,
                    'source': 'YES24',
                    'source_color': '#ffc800',
                    'link': full_link,
                    'category': categorize_concert(title),
                    'hash': get_cache_key(title)
                })
            except:
                continue

    except Exception as e:
        return {'success': False, 'error': str(e), 'data': []}
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

    seen = set()
    unique = [t for t in tickets if not (t['hash'] in seen or seen.add(t['hash']))]

    return {'success': True, 'data': unique, 'count': len(unique)}

if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: python selenium_crawler.py [melon|yes24]'}))
        sys.exit(1)

    site = sys.argv[1].lower()

    if site == 'melon':
        result = crawl_melon()
    elif site == 'yes24':
        result = crawl_yes24()
    else:
        result = {'error': f'Unknown site: {site}'}

    print(json.dumps(result, ensure_ascii=False))
