# -*- coding: utf-8 -*-
"""
번역 서비스 (MyMemory API + PO 파일)
"""
import os
import json
import logging
import threading
import time as time_module
import polib
import requests

from config import (
    SUPPORTED_LANGS, LANG_CODES,
    TRANSLATION_CACHE_FILE, TRANSLATION_CACHE_TTL_DAYS,
    TRANSLATION_CACHE_MAX_ENTRIES, TRANSLATION_CACHE_MAX_FILE_MB
)


def load_translation_cache():
    """JSON 파일에서 번역 캐시 로드 (만료 항목 제거, 기존 형식 호환)"""
    try:
        if os.path.exists(TRANSLATION_CACHE_FILE):
            file_size = os.path.getsize(TRANSLATION_CACHE_FILE)
            if file_size > TRANSLATION_CACHE_MAX_FILE_MB * 1024 * 1024:
                logging.warning(f"번역 캐시 파일 크기 초과 ({file_size // 1024}KB), 초기화")
                return {}

            with open(TRANSLATION_CACHE_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)

            now = time_module.time()
            ttl_seconds = TRANSLATION_CACHE_TTL_DAYS * 86400
            cache = {}
            for key, val in raw.items():
                if isinstance(val, dict) and 'v' in val and 't' in val:
                    if now - val['t'] < ttl_seconds:
                        cache[key] = val
                else:
                    cache[key] = {'v': val, 't': now}

            if len(cache) > TRANSLATION_CACHE_MAX_ENTRIES:
                sorted_items = sorted(cache.items(), key=lambda x: x[1].get('t', 0), reverse=True)
                cache = dict(sorted_items[:TRANSLATION_CACHE_MAX_ENTRIES])
                logging.info(f"번역 캐시 항목 제한 적용: {len(raw)} → {len(cache)}")

            return cache
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


# 모듈 로드 시 캐시 초기화
translation_cache = load_translation_cache()
translation_cache_lock = threading.Lock()


def translate_text(text, from_lang='ko', to_lang='en'):
    """MyMemory API로 텍스트 번역"""
    if not text or from_lang == to_lang:
        return text

    cache_key = f"{text}|{to_lang}"

    with translation_cache_lock:
        if cache_key in translation_cache:
            entry = translation_cache[cache_key]
            return entry['v'] if isinstance(entry, dict) else entry
        old_key = f"{text}|{from_lang}|{to_lang}"
        if old_key in translation_cache:
            entry = translation_cache[old_key]
            return entry['v'] if isinstance(entry, dict) else entry

    try:
        from_code = LANG_CODES.get(from_lang, from_lang)
        to_code = LANG_CODES.get(to_lang, to_lang)

        url = "https://api.mymemory.translated.net/get"
        params = {
            'q': text[:500],
            'langpair': f"{from_code}|{to_code}"
        }

        response = requests.get(url, params=params, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('responseStatus') == 200:
                translated = data.get('responseData', {}).get('translatedText', text)

                with translation_cache_lock:
                    translation_cache[cache_key] = {'v': translated, 't': time_module.time()}

                return translated
    except Exception as e:
        logging.debug(f"번역 API 오류: {e}")

    return text


def translate_performance_data(performances):
    """스크래핑 시 공연 name/venue를 4개 언어로 사전 번역"""
    global translation_cache
    target_langs = [l for l in SUPPORTED_LANGS if l != 'ko']

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

    seen = set()
    unique_texts = []
    for text, lang, cache_key in texts_to_translate:
        if cache_key not in seen:
            seen.add(cache_key)
            unique_texts.append((text, lang, cache_key))

    for text, lang, cache_key in unique_texts:
        translated = translate_text(text, 'ko', lang)
        with translation_cache_lock:
            translation_cache[cache_key] = {'v': translated, 't': time_module.time()}
        time_module.sleep(0.1)

    for perf in performances:
        for field in ['name', 'venue']:
            text = perf.get(field, '')
            for lang in target_langs:
                cache_key = f"{text}|{lang}"
                with translation_cache_lock:
                    entry = translation_cache.get(cache_key, text)
                    perf[f"{field}_{lang}"] = entry['v'] if isinstance(entry, dict) and 'v' in entry else entry

    save_translation_cache()


def load_po_translations():
    """PO 파일에서 번역 데이터 로드"""
    translations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'translations')
    all_translations = {}
    for lang in SUPPORTED_LANGS:
        po_path = os.path.join(translations_dir, lang, 'LC_MESSAGES', 'messages.po')
        try:
            if os.path.exists(po_path):
                po = polib.pofile(po_path)
                lang_dict = {}
                for entry in po:
                    if entry.msgstr:
                        lang_dict[entry.msgid] = entry.msgstr
                all_translations[lang] = lang_dict
        except Exception as e:
            logging.warning(f"PO 파일 로드 실패 ({lang}): {e}")
    return all_translations
