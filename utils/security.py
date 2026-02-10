# -*- coding: utf-8 -*-
"""
보안 유틸리티 함수
"""
import ipaddress
from urllib.parse import urlparse
from config import ALLOWED_IMAGE_DOMAINS


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


def set_security_headers(response):
    """보안 헤더 설정 (Flask after_request 핸들러)"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: http: https:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'self'"
    )
    return response
