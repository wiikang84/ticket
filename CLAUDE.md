# 콘서트 통합 정보 시스템

## 프로젝트 개요
- **목적**: K-POP/콘서트 티켓팅 통합 조회 시스템
- **버전**: v2.1
- **시작일**: 2026-01-28
- **업데이트**: 12시간 단위 (00시, 12시)

## 데이터 소스

### 1. KOPIS API (공연예술통합전산망)
- **API 키**: `2012e419e6c24bfa988ca56e2917d3c0`
- **조회 장르**: 대중음악/콘서트만 (CCCD)
- **제공 데이터**: 공연명, 공연일, 장소, 포스터, 가격, 출연진, **예매처 링크**
- **예매처 정보**: relates 태그에서 인터파크/멜론/YES24 실제 링크 제공

### 2. 인터파크 (NOL 티켓)
- **URL**: tickets.interpark.com
- **크롤링 페이지**: `/contents/genre/concert` (콘서트만)
- **수집 방식**: JSON 파싱 (goodsCode, goodsName, placeName, posterImageUrl)
- **수집 데이터**: 공연명, 날짜, 장소, 포스터, 상품링크

### 제외된 사이트
- **멜론티켓/YES24**: JavaScript 동적 로딩으로 크롤링 불가 (KOPIS 예매처 링크로 대체)
- **티켓링크**: 동일

## 콘서트 세부 장르 분류

| 카테고리 | 키워드 예시 |
|----------|-------------|
| 아이돌 | BTS, 에이핑크, 제로베이스원, 르세라핌, NCT 등 |
| 발라드 | 먼데이키즈, 임재범, 성시경, 10CM 등 |
| 랩/힙합 | 다이나믹듀오, AOMG 등 |
| 락/인디 | 밴드, 데이식스 등 |
| 내한공연 | World Tour, Asia Tour, Live in Seoul |
| 팬미팅 | 팬미팅, 팬콘, FAN-CON |
| 페스티벌 | 뮤직페스티벌 |
| 트로트 | 미스터트롯, 임영웅, 송가인 등 |

## 기술 스택
- **백엔드**: Python Flask
- **프론트엔드**: HTML, CSS, JavaScript (Vanilla)
- **캘린더**: FullCalendar 6.1 (CDN)
- **라이브러리**: requests, beautifulsoup4, flask-cors

## 주요 기능

### 구현 완료
- [x] KOPIS API 연동 (콘서트/대중음악만)
- [x] 인터파크 JSON 크롤링
- [x] 공연 통합 + 실제 판매처만 표시
- [x] KOPIS 상세 API에서 예매 링크 추출
- [x] 콘서트 세부 장르 자동 분류
- [x] 장르별 탭 필터링
- [x] 카드 클릭 시 상세 팝업
- [x] D-day 순 정렬
- [x] **캘린더 뷰** (예매오픈 / 공연일정)
- [x] 모바일 반응형

### 구현 예정
- [ ] 12시간 자동 업데이트 스케줄러
- [ ] 알림 기능 (티켓오픈 D-day)

## 의사결정 기록

### 2026-01-28 회의 #1~#4
- 콘서트/대중음악만 표시 (연극, 클래식, 뮤지컬 제외)
- 인터파크처럼 세부 장르 분류
- KOPIS API의 relates 태그로 실제 예매 링크 표시
- 캘린더 2종류: 예매오픈일 / 공연일정

### 2026-01-28 회의 #5 (캘린더)
- FullCalendar 라이브러리 사용
- 12시간 업데이트 (00시, 12시)
- 모바일 반응형

## 파일 구조
```
ticket/
├── app.py              # Flask 백엔드 서버
├── templates/
│   └── index.html      # 프론트엔드 (목록+캘린더)
├── CLAUDE.md           # 프로젝트 문서 (이 파일)
└── .gitignore
```

## 실행 방법
```bash
cd ticket
pip install flask flask-cors requests beautifulsoup4
python app.py
# 브라우저에서 http://localhost:5000 접속
```

## 법적 고려사항
- 크롤링: 공개된 정보만 수집
- 상업적 목적 아닌 개인 프로젝트
- 각 사이트 robots.txt 준수

## 연락처
- KOPIS API 문의: 02-2098-2945
- 이메일: kopis@gokams.or.kr
