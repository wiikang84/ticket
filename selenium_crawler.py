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
    """YES24 콘서트 크롤링"""
    tickets = []
    driver = None

    try:
        driver = get_driver()
        driver.get("https://ticket.yes24.com/New/Genre/GenreMain.aspx?genre=15457")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'body'))
        )
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        items = soup.select('.goods-list li, .ranking-list li, #divGoodsList li, .list-item, .item-box, article')

        for item in items[:25]:
            try:
                title_el = item.select_one('.goods-name, .tit, .title, a[title], h3, h4, strong')
                if not title_el:
                    link_el = item.select_one('a[title]')
                    if link_el:
                        title = link_el.get('title', '')
                    else:
                        continue
                else:
                    title = title_el.get_text(strip=True)

                if not title or len(title) < 3:
                    continue

                if any(kw in title for kw in ['프로모션', '혜택', '이벤트']):
                    continue

                date_el = item.select_one('.goods-date, .date, .period')
                date_text = date_el.get_text(strip=True) if date_el else ''

                venue_el = item.select_one('.goods-place, .place, .venue')
                venue = venue_el.get_text(strip=True) if venue_el else ''

                link_el = item.select_one('a[href]')
                link = ''
                if link_el:
                    href = link_el.get('href', '')
                    if href.startswith('http'):
                        link = href
                    elif href.startswith('/'):
                        link = 'https://ticket.yes24.com' + href

                img_el = item.select_one('img')
                poster = ''
                if img_el:
                    poster = img_el.get('src', '') or img_el.get('data-src', '')
                    if poster and poster.startswith('//'):
                        poster = 'https:' + poster

                tickets.append({
                    'name': title[:100],
                    'date': date_text,
                    'venue': venue,
                    'poster': poster,
                    'source': 'YES24',
                    'source_color': '#ffc800',
                    'link': link or 'https://ticket.yes24.com',
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
