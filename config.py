# -*- coding: utf-8 -*-
"""
애플리케이션 설정 및 환경변수
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================
# KOPIS API 설정
# =============================================
KOPIS_API_KEY = os.environ.get('KOPIS_API_KEY', '')
KOPIS_BASE_URL = "http://www.kopis.or.kr/openApi/restful"

# KOPIS 장르 코드
GENRE_CODE_CONCERT = "CCCD"  # 대중음악/콘서트
GENRE_CODE_MUSICAL = "GGGA"  # 뮤지컬
GENRE_CODE_THEATER = "AAAA"  # 연극

GENRE_CODES = {
    'concert': GENRE_CODE_CONCERT,
    'musical': GENRE_CODE_MUSICAL,
    'theater': GENRE_CODE_THEATER
}

# =============================================
# 보안 설정
# =============================================
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*').split(',')

ALLOWED_IMAGE_DOMAINS = [
    'www.kopis.or.kr', 'kopis.or.kr',
    'tickets.interpark.com', 'ticketimage.interpark.com',
    'ticket.melon.com', 'cdnticket.melon.co.kr', 'cdnimg.melon.co.kr',
    'ticket.yes24.com', 'tkfile.yes24.com', 'image.yes24.com',
]

# =============================================
# 이미지 캐시 설정
# =============================================
IMAGE_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'image_cache')
MAX_CACHE_FILES = 500       # 최대 캐시 파일 수
MAX_CACHE_SIZE_MB = 200     # 최대 캐시 크기 (MB)

# =============================================
# 번역 설정
# =============================================
SUPPORTED_LANGS = ['ko', 'en', 'ja', 'zh', 'es']

LANG_CODES = {
    'ko': 'ko',
    'en': 'en',
    'ja': 'ja',
    'zh': 'zh-CN',
    'es': 'es'
}

TRANSLATION_CACHE_FILE = os.path.join(os.path.dirname(__file__), 'translation_cache.json')
TRANSLATION_CACHE_TTL_DAYS = 30       # 캐시 만료 기간 (일)
TRANSLATION_CACHE_MAX_ENTRIES = 10000  # 최대 항목 수
TRANSLATION_CACHE_MAX_FILE_MB = 5     # 최대 파일 크기 (MB)

# =============================================
# Flask 설정
# =============================================
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
