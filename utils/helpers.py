# -*- coding: utf-8 -*-
"""
공통 유틸리티 함수
"""
import re
from datetime import datetime


def calculate_dday(date_str):
    """D-day 계산"""
    try:
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
    except Exception:
        pass
    return None


def filter_ended_performances(performances_list):
    """종료된 공연 필터링 (종료일이 오늘 이전인 공연 제외)"""
    today_str = datetime.now().strftime('%Y.%m.%d')
    filtered = []
    for p in performances_list:
        end_date = p.get('end_date') or p.get('start_date') or p.get('date', '')
        if end_date:
            end_clean = re.sub(r'[^\d.]', '', end_date)[:10]
            if len(end_clean) >= 8:
                try:
                    if '.' in end_clean:
                        parts = end_clean.split('.')
                        if len(parts) >= 3:
                            end_formatted = f"{parts[0]}.{parts[1].zfill(2)}.{parts[2].zfill(2)}"
                    else:
                        end_formatted = f"{end_clean[:4]}.{end_clean[4:6]}.{end_clean[6:8]}"
                    if end_formatted >= today_str:
                        filtered.append(p)
                    continue
                except Exception:
                    pass
        filtered.append(p)
    return filtered


def sort_by_dday(performances_list):
    """D-day 순 정렬"""
    def sort_key(p):
        dday = p.get('dday')
        if dday is not None and dday >= 0:
            return (0, dday)
        elif p.get('start_date'):
            try:
                date_str = p['start_date'].replace('.', '')
                return (1, int(date_str))
            except Exception:
                return (2, 0)
        return (2, 0)
    performances_list.sort(key=sort_key)
    return performances_list
