# 티켓팅 통합 정보 시스템

## 프로젝트 개요
- **목적**: 한국 공연 티켓팅 사이트 통합 조회 시스템
- **버전**: v2.0
- **시작일**: 2026-01-28

## 데이터 소스

### 1. KOPIS API (공연예술통합전산망)
- **API 키**: `2012e419e6c24bfa988ca56e2917d3c0`
- **제공 데이터**: 공연명, 공연일, 장소, 장르, 포스터, 가격, 출연진
- **한계**: 예매 시작일(티켓오픈일) 미제공, K-pop 아이돌 콘서트 누락 많음
- **업데이트 주기**: 매일 10시, 15시

### 2. 인터파크 (NOL 티켓)
- **URL**: tickets.interpark.com
- **크롤링 페이지**:
  - 콘서트: `/contents/genre/concert`
  - 뮤지컬: `/contents/genre/musical`
  - 오픈예정: `/contents/notice` (티켓오픈일 정보)
- **수집 데이터**: 공연명, 날짜, 장소, 티켓오픈일, 포스터

### 3. 멜론티켓
- **URL**: ticket.melon.com
- **크롤링 페이지**: `/csoon/index.htm` (티켓오픈소식)
- **수집 데이터**: 공연명, 티켓오픈일, 포스터

### 4. YES24 티켓
- **URL**: ticket.yes24.com
- **크롤링 페이지**:
  - 콘서트: `/New/Genre/GenreMain.aspx?genre=15457`
  - 뮤지컬: `/New/Genre/GenreMain.aspx?genre=15458`
- **수집 데이터**: 공연명, 날짜, 장소, 포스터

### 제외된 사이트
- **티켓링크**: JavaScript 동적 로딩으로 크롤링 어려움 (Selenium 필요)

## 기술 스택
- **백엔드**: Python Flask
- **프론트엔드**: HTML, CSS, JavaScript (Vanilla)
- **라이브러리**: requests, beautifulsoup4, flask-cors

## 주요 기능

### 구현 완료
- [x] KOPIS API 연동 (공연 목록/상세)
- [x] 인터파크 크롤링
- [x] 멜론티켓 크롤링
- [x] YES24 크롤링
- [x] 통합 검색
- [x] 중복 제거 (KOPIS vs 예매사이트)
- [x] 카드 클릭 시 상세 팝업
- [x] 예매처 바로가기 링크
- [x] D-day 표시 (티켓오픈일 기준)
- [x] 탭별 필터링 (전체/KOPIS/인터파크/멜론/YES24)

### 구현 예정
- [ ] 인터파크 "오픈예정" 페이지 크롤링 추가 (티켓오픈일 수집 강화)
- [ ] 티켓오픈일 우선 표시
- [ ] 티켓오픈일 기준 정렬
- [ ] Brave Search API 연동 (아이돌 콘서트 정보 보완)

## 의사결정 기록

### 2026-01-28 회의 #1
**데이터 수집 방식**
- 1-C: 목록 페이지 크롤링 + 예매처 링크 연결
- 2-B: 티켓링크 제외 (기술적 난이도)
- 3-A: 자체 상세 팝업
- 4-C: 하루 2회 수동 업데이트

### 2026-01-28 회의 #2 (예매가능일 기능)
**결정 필요 사항**
| 번호 | 항목 | 선택 |
|------|------|------|
| 1 | 오픈예정 데이터 소스 | TBD |
| 2 | 표시 우선순위 | TBD |
| 3 | D-day 기준 | TBD |
| 4 | 정렬 기본값 | TBD |

## 파일 구조
```
ticket/
├── app.py              # Flask 백엔드 서버
├── templates/
│   └── index.html      # 프론트엔드 페이지
├── CLAUDE.md           # 프로젝트 문서 (이 파일)
└── README.md           # 사용 가이드
```

## 실행 방법
```bash
cd ticket
pip install flask flask-cors requests beautifulsoup4
python app.py
# 브라우저에서 http://localhost:5000 접속
```

## 법적 고려사항
- 크롤링: 공개된 정보만 수집, 적절한 요청 주기 (서버 부하 방지)
- 상업적 목적 아닌 개인 프로젝트
- 각 사이트 robots.txt 준수 권장

## 연락처
- KOPIS API 문의: 02-2098-2945
- 이메일: kopis@gokams.or.kr
