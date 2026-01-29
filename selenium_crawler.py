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

# 파트 분류 키워드
def classify_part(name):
    """공연명으로 파트 분류 (concert / theater)"""
    if not name:
        return 'concert'
    name_upper = name.upper()
    theater_keywords = ['뮤지컬', 'MUSICAL', '연극', 'PLAY', 'THEATER', '오페라', 'OPERA',
                       '발레', 'BALLET', '창극', '마당극']
    for kw in theater_keywords:
        if kw in name_upper:
            return 'theater'
    return 'concert'

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
                    'part': classify_part(title),  # 파트 분류
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
    """YES24 콘서트/뮤지컬/연극 크롤링 (undetected-chromedriver)"""
    tickets = []
    driver = None
    import re

    # 크롤링할 장르들: (URL, 파트)
    genre_urls = [
        ("https://ticket.yes24.com/New/Genre/GenreMain.aspx?genre=15457", "concert"),   # 콘서트
        ("https://ticket.yes24.com/New/Genre/GenreMain.aspx?genre=15458", "theater"),   # 뮤지컬
        ("https://ticket.yes24.com/New/Genre/GenreMain.aspx?genre=15459", "theater"),   # 연극
    ]

    seen_codes = set()

    try:
        # undetected-chromedriver 사용 (봇 차단 우회)
        driver = get_undetected_driver()

        for genre_url, default_part in genre_urls:
            try:
                driver.get(genre_url)
                time.sleep(5)  # 페이지 로딩 대기

                soup = BeautifulSoup(driver.page_source, 'html.parser')

                # 링크에서 공연 정보 추출
                perf_links = soup.select('a[href*="PerfCode"], a[href*="Perf/"], a[href*="/New/Perf"]')

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

                        # 이미지 찾기 (여러 레벨에서 탐색)
                        poster = ''
                        img = link.select_one('img')

                        # 링크 안에 없으면 부모들에서 찾기
                        if not img:
                            parent = link.parent
                            for _ in range(5):  # 최대 5단계 상위까지
                                if parent:
                                    img = parent.select_one('img')
                                    if img:
                                        break
                                    parent = parent.parent

                        if img:
                            # 다양한 이미지 속성 체크
                            poster = (img.get('src', '') or
                                      img.get('data-src', '') or
                                      img.get('data-original', '') or
                                      img.get('data-lazy-src', ''))

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

                        # 파트 분류: 기본값 사용하되, 제목으로 재분류
                        item_part = classify_part(title) if default_part == 'concert' else default_part

                        tickets.append({
                            'name': title[:100],
                            'date': date_text,
                            'venue': venue,
                            'poster': poster,
                            'source': 'YES24',
                            'source_color': '#ffc800',
                            'link': full_link,
                            'category': categorize_concert(title),
                            'part': item_part,  # 파트 분류
                            'hash': get_cache_key(title)
                        })
                    except:
                        continue
            except:
                continue  # 개별 장르 페이지 오류 시 다음으로

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

def crawl_melon_detail(prod_id):
    """멜론티켓 상세 페이지 크롤링"""
    driver = None
    import re

    try:
        driver = get_driver()
        url = f"https://ticket.melon.com/performance/index.htm?prodId={prod_id}"
        driver.get(url)
        time.sleep(4)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        result = {
            'date': '',
            'venue': '',
            'price': '',
            'cast': '',
            'runtime': '',
            'age': ''
        }

        # 공연 정보 테이블에서 추출
        info_items = soup.select('.box_consert_info dt, .box_consert_info dd, .info_data dt, .info_data dd')
        current_label = ''
        for item in info_items:
            text = item.get_text(strip=True)
            if item.name == 'dt':
                current_label = text
            elif item.name == 'dd' and current_label:
                if '기간' in current_label or '일시' in current_label or '공연기간' in current_label:
                    result['date'] = text
                elif '장소' in current_label or '공연장' in current_label:
                    result['venue'] = text
                elif '가격' in current_label or '티켓' in current_label:
                    result['price'] = text
                elif '출연' in current_label or '아티스트' in current_label or '캐스팅' in current_label:
                    result['cast'] = text
                elif '관람시간' in current_label or '런타임' in current_label:
                    result['runtime'] = text
                elif '관람등급' in current_label or '연령' in current_label:
                    result['age'] = text

        # 대체 선택자로 시도
        if not result['date']:
            date_el = soup.select_one('.txt_consert_date, .show_date, [class*="date"]')
            if date_el:
                result['date'] = date_el.get_text(strip=True)

        if not result['venue']:
            venue_el = soup.select_one('.txt_consert_place, .show_place, [class*="place"]')
            if venue_el:
                result['venue'] = venue_el.get_text(strip=True)

        if not result['price']:
            price_el = soup.select_one('.txt_consert_price, .show_price, [class*="price"]')
            if price_el:
                result['price'] = price_el.get_text(strip=True)

        return {'success': True, 'data': result}

    except Exception as e:
        return {'success': False, 'error': str(e), 'data': {}}
    finally:
        if driver:
            driver.quit()


def crawl_yes24_detail(perf_code):
    """YES24 상세 페이지 크롤링"""
    driver = None
    import re

    try:
        driver = get_undetected_driver()
        url = f"https://ticket.yes24.com/Perf/{perf_code}"
        driver.get(url)
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        result = {
            'date': '',
            'venue': '',
            'price': '',
            'cast': '',
            'runtime': '',
            'age': ''
        }

        # rn-product-area1 영역에서 정보 추출
        info_area = soup.select_one('.rn-product-area1')
        if info_area:
            # dt/dd 쌍으로 정보 추출
            dts = info_area.select('dt')
            dds = info_area.select('dd')

            for i, dt in enumerate(dts):
                label = dt.get_text(strip=True)
                if i < len(dds):
                    value = dds[i].get_text(strip=True)

                    if '기간' in label or '일시' in label or '일자' in label:
                        result['date'] = value
                    elif '장소' in label or '공연장' in label:
                        result['venue'] = value
                    elif '가격' in label:
                        result['price'] = value
                    elif '출연' in label or '기연' in label or '캐스팅' in label or '아티스트' in label:
                        result['cast'] = value
                    elif '관람시간' in label or '런타임' in label or '시간' in label:
                        result['runtime'] = value
                    elif '관람가' in label or '등급' in label or '연령' in label:
                        result['age'] = value

        # 대체: 전체 페이지에서 찾기
        if not result['date']:
            # 공연 일정 찾기
            schedule_items = soup.select('.rn-product-info dt, .rn-product-info dd, .product-info dt, .product-info dd')
            current_label = ''
            for item in schedule_items:
                text = item.get_text(strip=True)
                if item.name == 'dt':
                    current_label = text
                elif item.name == 'dd' and current_label:
                    if '기간' in current_label or '일시' in current_label:
                        result['date'] = text
                    elif '장소' in current_label:
                        result['venue'] = text
                    elif '가격' in current_label:
                        result['price'] = text
                    elif '출연' in current_label or '기연' in current_label:
                        result['cast'] = text

        # 가격 정보 별도 추출 시도
        if not result['price']:
            price_area = soup.select_one('.rn-price-area, .price-info, [class*="price"]')
            if price_area:
                result['price'] = price_area.get_text(strip=True)[:200]

        return {'success': True, 'data': result}

    except Exception as e:
        return {'success': False, 'error': str(e), 'data': {}}
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: python selenium_crawler.py [melon|yes24|melon_detail|yes24_detail] [id]'}))
        sys.exit(1)

    site = sys.argv[1].lower()

    if site == 'melon':
        result = crawl_melon()
    elif site == 'yes24':
        result = crawl_yes24()
    elif site == 'melon_detail':
        if len(sys.argv) < 3:
            result = {'error': 'prod_id required'}
        else:
            result = crawl_melon_detail(sys.argv[2])
    elif site == 'yes24_detail':
        if len(sys.argv) < 3:
            result = {'error': 'perf_code required'}
        else:
            result = crawl_yes24_detail(sys.argv[2])
    else:
        result = {'error': f'Unknown site: {site}'}

    print(json.dumps(result, ensure_ascii=False))
