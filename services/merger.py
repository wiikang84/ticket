# -*- coding: utf-8 -*-
"""
데이터 통합 + 소스 병합 서비스
"""
from constants import get_cache_key, normalize_name, classify_part, classify_region


def merge_performance_data(base, new_item, source_name):
    """공연 데이터 병합 - 새 소스 정보 추가"""
    site_info = {
        'name': source_name,
        'link': new_item.get('link', ''),
        'color': new_item.get('source_color', '#888')
    }

    if 'available_sites' not in base:
        base['available_sites'] = []

    existing_sites = [s['name'] for s in base['available_sites']]
    if source_name not in existing_sites:
        base['available_sites'].append(site_info)

    if new_item.get('ticket_open') and not base.get('ticket_open'):
        base['ticket_open'] = new_item['ticket_open']
        base['dday'] = new_item.get('dday')

    if not base.get('poster') and new_item.get('poster'):
        base['poster'] = new_item['poster']

    return base


def merge_source_data(merged_performances, items, source_name, source_color, source_counts_key, source_counts):
    """소스 데이터를 merged_performances에 병합하는 공통 함수"""
    for item in items:
        perf_hash = get_cache_key(normalize_name(item.get('name', '')))
        source_counts[source_counts_key] += 1

        if perf_hash in merged_performances:
            merged_performances[perf_hash] = merge_performance_data(
                merged_performances[perf_hash], item, source_name
            )
        else:
            item['available_sites'] = [{'name': source_name, 'link': item.get('link', ''), 'color': source_color}]
            item['hash'] = perf_hash
            if 'part' not in item:
                item['part'] = classify_part(item.get('name', ''))
            if 'region' not in item:
                item['region'] = classify_region(item.get('venue', ''))
            merged_performances[perf_hash] = item
