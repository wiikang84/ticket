# -*- coding: utf-8 -*-
"""
이미지 프록시 + 캐시 서비스
"""
import os
import hashlib
import logging
from datetime import datetime
import requests

from config import IMAGE_CACHE_DIR, MAX_CACHE_FILES, MAX_CACHE_SIZE_MB

IMAGE_CACHE_HOURS = 24  # 캐시 유효 시간

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

                if (now - file_time).total_seconds() > IMAGE_CACHE_HOURS * 3600:
                    os.remove(filepath)
                    continue

                files.append((filepath, file_time, file_size))
                total_size += file_size

        if len(files) > MAX_CACHE_FILES:
            files.sort(key=lambda x: x[1])
            for filepath, _, file_size in files[:len(files) - MAX_CACHE_FILES]:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    total_size -= file_size

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


def get_cached_or_download(url):
    """이미지를 캐시에서 반환하거나 다운로드 (content, content_type, status_code 반환)"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    ext = '.jpg'
    if '.png' in url.lower():
        ext = '.png'
    elif '.gif' in url.lower():
        ext = '.gif'
    elif '.webp' in url.lower():
        ext = '.webp'

    cache_path = os.path.join(IMAGE_CACHE_DIR, url_hash + ext)

    ext_to_mime = {'.jpg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}

    # 캐시 히트
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                content = f.read()
            return content, ext_to_mime.get(ext, 'image/jpeg'), 200
        except Exception:
            pass

    # noimg 플레이스홀더 URL 차단 (YES24 기본 로고)
    if 'noimg' in url.lower():
        return None, None, 404

    # 다운로드
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://ticket.yes24.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        }

        if 'melon' in url:
            headers['Referer'] = 'https://ticket.melon.com/'

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            content = response.content
            content_type = response.headers.get('Content-Type', 'image/jpeg')

            # 너무 작은 이미지는 로고로 간주
            if len(content) < 3000:
                return None, None, 404

            # 캐시에 저장
            try:
                with open(cache_path, 'wb') as f:
                    f.write(content)
            except Exception:
                pass

            # 가끔 오래된 캐시 정리
            if hash(url) % 100 == 0:
                cleanup_old_cache()

            return content, content_type, 200
        else:
            return None, None, response.status_code
    except Exception:
        return None, None, 500
