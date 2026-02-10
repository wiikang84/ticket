# -*- coding: utf-8 -*-
"""
공통 상수 및 분류 함수
app.py와 selenium_crawler.py에서 공유
"""

import re
import hashlib

# =============================================
# 파트 분류 키워드 (concert / theater)
# =============================================
THEATER_KEYWORDS = [
    '뮤지컬', 'MUSICAL', '연극', 'PLAY', 'THEATER', '오페라', 'OPERA',
    '발레', 'BALLET', '창극', '마당극', '희곡', '무용'
]

# =============================================
# 콘서트 세부 장르 분류 키워드
# =============================================
CONCERT_CATEGORIES = {
    "아이돌": ["BTS", "방탄", "에이핑크", "Apink", "제로베이스원", "ZEROBASE", "아이브", "IVE",
              "르세라핌", "SSERAFIM", "뉴진스", "NewJeans", "스트레이키즈", "Stray Kids",
              "엔시티", "NCT", "세븐틴", "SEVENTEEN", "블랙핑크", "BLACKPINK", "에스파", "aespa",
              "투모로우바이투게더", "TXT", "엔하이픈", "ENHYPEN", "있지", "ITZY", "케플러", "Kep1er",
              "엑소", "EXO", "샤이니", "SHINee", "레드벨벳", "Red Velvet", "트와이스", "TWICE",
              "마마무", "MAMAMOO", "오마이걸", "OH MY GIRL", "에이티즈", "ATEEZ", "더보이즈", "THE BOYZ",
              "스키즈", "SKZ", "빅뱅", "BIGBANG", "위너", "WINNER", "아이콘", "iKON", "트레저", "TREASURE",
              "엔믹스", "NMIXX", "아이들", "(G)I-DLE", "IDLE", "기들", "스테이씨", "STAYC",
              "RIIZE", "라이즈", "보이넥스트도어", "BOYNEXTDOOR", "ILLIT", "아일릿", "BABYMONSTER",
              "NCT127", "NCT DREAM", "WayV", "위이브", "FIFTY FIFTY", "KISS OF LIFE",
              "PLAVE", "플레이브", "xikers", "싸이커스", "ZEROBASEONE", "ZB1",
              "소녀시대", "Girls Generation", "2NE1", "투애니원", "원더걸스", "Wonder Girls",
              "인피니트", "INFINITE", "비스트", "BEAST", "하이라이트", "Highlight",
              "몬스타엑스", "MONSTA X", "크래비티", "CRAVITY", "피원하모니", "P1Harmony"],
    "발라드": ["먼데이키즈", "임재범", "성시경", "이수", "엠씨더맥스", "MC THE MAX", "나얼",
              "박효신", "김범수", "휘성", "거미", "이적", "10CM", "폴킴", "백예린", "헤이즈", "Heize",
              "규현", "KYUHYUN", "케이윌", "K.Will", "이소라", "정승환", "에일리", "Ailee", "벤", "Ben",
              "소향", "김연우", "임창정", "이승기", "김필", "하동균", "윤도현", "YB", "이선희",
              "김건모", "이문세", "조용필", "양희은", "이영현", "솔지", "태연", "TAEYEON",
              "아이유", "IU", "볼빨간사춘기", "BOL4", "선미", "SUNMI", "청하", "CHUNG HA",
              "멜로망스", "MeloMance", "어반자카파", "Urban Zakapa", "소유", "SOYOU",
              "다비치", "DAVICHI", "린", "LYn", "알리", "Ali", "백지영", "Baek Ji Young",
              "양다일", "임한별", "김나영", "이무진", "태일", "TAEIL"],
    "랩/힙합": ["다이나믹듀오", "Dynamic Duo", "쇼미", "힙합", "래퍼", "Rapper", "AOMG", "하이어뮤직",
               "박재범", "Jay Park", "지코", "ZICO", "사이먼도미닉", "Simon Dominic", "그레이", "GRAY",
               "쌈디", "도끼", "DOK2", "빈지노", "Beenzino", "치타", "스윙스", "Swings",
               "pH-1", "식케이", "Sik-K", "우원재", "Woo", "창모", "CHANGMO", "래원", "Layone",
               "이영지", "래퍼", "BE'O", "비오", "ASH ISLAND", "키드밀리", "Kid Milli",
               "릴보이", "Lil Boi", "넉살", "Nucksal", "해쉬스완", "Hash Swan", "딘딘", "DinDin",
               "빈첸", "VINXEN", "쿠기", "COOGIE", "조광일", "가호", "Gaho"],
    "락/인디": ["밴드", "Band", "록", "Rock", "인디", "Indie", "데이식스", "DAY6",
               "잔나비", "JANNABI", "혁오", "Hyukoh", "실리카겔", "SILICA GEL", "넬", "NELL",
               "버즈", "BUZZ", "FT아일랜드", "FT Island", "씨엔블루", "CNBLUE", "N.Flying", "엔플라잉",
               "더로즈", "The Rose", "카더가든", "Car the Garden", "새소년", "SE SO NEON",
               "이날치", "양방언", "국카스텐", "Guckkasten", "트로이카", "소규모아카시아밴드",
               "YB밴드", "윤도현밴드", "크라잉넛", "Crying Nut", "노브레인", "No Brain",
               "장기하", "장기하와 얼굴들", "이승환", "김동률", "루시", "LUCY", "엔드어스", "N.Tic",
               "피플인텔리"],
    "내한공연": ["내한", "World Tour", "Asia Tour", "Live in Seoul", "Live in Korea", "in Seoul",
               "Tour", "콘서트", "Concert", "in Korea", "한국", "서울", "Korea Tour"],
    "팬미팅": ["팬미팅", "Fan Meeting", "팬콘", "FAN-CON", "팬콘서트", "FANCON", "FANMEETING",
             "생일", "Birthday", "팬파티", "FAN PARTY", "쇼케이스", "Showcase", "팬이벤트"],
    "페스티벌": ["페스티벌", "Festival", "뮤직페스타", "Music Festa", "뮤직페스티벌", "FEST",
               "록페스티벌", "재즈페스티벌", "EDM", "울트라", "Ultra", "워터밤", "Waterbomb",
               "지산", "펜타포트", "Pentaport", "슬로우라이프", "그린플러그드", "인디고", "Incheon"],
    "트로트": ["트롯", "트로트", "미스터트롯", "미스트롯", "송가인", "임영웅", "영탁",
              "정동원", "장민호", "김희재", "이찬원", "홍진영", "태진아", "설운도", "나훈아",
              "주현미", "진성", "류지광", "양지은", "김다현", "박서진", "임태경", "김호중",
              "진해성", "남진", "나태주", "김수찬", "신유", "최진희", "박상철"]
}

# =============================================
# 지역 분류 키워드 매핑 (7개 권역)
# =============================================
VENUE_REGION_KEYWORDS = {
    '서울': ['서울', '예술의전당', '올림픽공원', '올림픽홀', '잠실', '블루스퀘어',
             '세종문화회관', '세종문화', '국립극장', '대학로', 'LG아트센터', '샤롯데',
             '광림아트', '고척스카이돔', '고척', 'KSPO', 'YES24 LIVE', 'KBS아레나',
             'KBS 아레나', '장충체육관', '충무아트', '두산아트', 'COEX', '코엑스',
             '롯데콘서트홀', '디큐브', '강동아트', '마포아트', '드림씨어터',
             '무신사 가라지', '서울숲', '링크아트', '국립중앙', '남산'],
    '경기·인천': ['인천', '경기', '킨텍스', 'KINTEX', '고양아람', '고양시', '수원',
                 '성남아트', '성남시', '부천', '안산', '일산', '용인', '파주',
                 '의정부', '화성', '평택', '안양', '광명', '이천', '시흥',
                 '군포', '하남', '구리', '남양주', '양주', '포천', '동두천'],
    '강원': ['강원', '춘천', '원주', '강릉', '속초', '동해', '삼척', '태백',
            '정선', '평창', '횡성', '영월', '화천', '인제', '양양', '홍천'],
    '충청': ['충청', '대전', '세종', '청주', '천안', '아산', '충북', '충남',
            '서산', '당진', '공주', '보령', '논산', '제천', '충주', '옥천'],
    '전라': ['전라', '광주', '전주', '여수', '순천', '목포', '전북', '전남',
            '익산', '군산', '정읍', '남원', '나주', '무안', '광양'],
    '경상': ['경상', '부산', '대구', '울산', '창원', '포항', '경주', '김해', '경북', '경남',
            'BEXCO', '벡스코', '해운대', '김천', '안동', '구미', '영주',
            '진주', '통영', '거제', '양산', '엑스코', 'EXCO', '대구콘서트'],
    '제주': ['제주', '서귀포', '한라'],
}


# =============================================
# 정규식 사전 컴파일 (키워드 매칭 정확도 향상)
# =============================================
def _is_ascii_keyword(keyword):
    """영문/숫자로만 이루어진 키워드 여부"""
    return all(ord(c) < 128 for c in keyword.replace(' ', '').replace('-', '').replace('.', '').replace("'", ''))


def _build_keyword_pattern(keyword):
    """키워드별 최적 정규식 패턴 생성 (영문: 단어 경계, 한국어: 포함 매칭)"""
    escaped = re.escape(keyword)
    if _is_ascii_keyword(keyword):
        return re.compile(r'(?<![A-Za-z0-9])' + escaped + r'(?![A-Za-z0-9])', re.IGNORECASE)
    else:
        return re.compile(escaped, re.IGNORECASE)


# 카테고리별 사전 컴파일 패턴
CONCERT_CATEGORY_PATTERNS = {}
for _cat, _keywords in CONCERT_CATEGORIES.items():
    CONCERT_CATEGORY_PATTERNS[_cat] = [(_kw, _build_keyword_pattern(_kw)) for _kw in _keywords]

THEATER_KEYWORD_PATTERNS = [(_kw, _build_keyword_pattern(_kw)) for _kw in THEATER_KEYWORDS]


# =============================================
# 공통 함수
# =============================================
def get_cache_key(data):
    """중복 체크용 해시 생성 (SHA-256, 64비트)"""
    return hashlib.sha256(data.encode('utf-8')).hexdigest()[:16]


def normalize_name(name):
    """공연명 정규화 (매칭 정확도 향상)"""
    if not name:
        return ''
    normalized = re.sub(r'[^\w가-힣]', '', name).lower()
    return normalized


def classify_part(name, genre=''):
    """공연명/장르로 파트 분류 (concert / theater)"""
    if not name:
        return 'concert'

    if genre:
        for kw, pattern in THEATER_KEYWORD_PATTERNS:
            if pattern.search(genre):
                return 'theater'

    for kw, pattern in THEATER_KEYWORD_PATTERNS:
        if pattern.search(name):
            return 'theater'

    return 'concert'


def classify_region(venue_name='', area=''):
    """공연장/지역으로 지역 분류 (7개 권역)"""
    if area:
        for region, keywords in VENUE_REGION_KEYWORDS.items():
            for kw in keywords:
                if kw in area:
                    return region

    if venue_name:
        venue_upper = venue_name.upper()
        for region, keywords in VENUE_REGION_KEYWORDS.items():
            for kw in keywords:
                if kw.upper() in venue_upper:
                    return region

    return '미분류'


def categorize_concert(name):
    """공연명으로 콘서트 세부 장르 분류 (정규식 단어 경계 매칭)"""
    if not name:
        return "기타"

    for category, patterns in CONCERT_CATEGORY_PATTERNS.items():
        for keyword, pattern in patterns:
            if pattern.search(name):
                return category

    return "기타"
