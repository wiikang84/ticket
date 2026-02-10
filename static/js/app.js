// =============================================
// 보안 유틸리티
// =============================================
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
}

function sanitizeUrl(url) {
    if (!url) return '';
    const trimmed = url.trim().toLowerCase();
    if (trimmed.startsWith('javascript:') || trimmed.startsWith('data:') || trimmed.startsWith('vbscript:')) {
        return '';
    }
    return url;
}

// =============================================
// 다국어 지원 (i18n)
// =============================================
// PO 파일 기반 번역 시스템
let i18nData = {};
let currentLang = localStorage.getItem('ticket_lang') || 'ko';

async function loadTranslations(lang) {
    try {
        const response = await fetch(`/api/i18n/${lang}`);
        if (response.ok) {
            i18nData[lang] = await response.json();
        }
    } catch (e) {
        console.error(`[i18n] ${lang} 번역 로드 실패:`, e);
    }
}

async function initI18n() {
    await loadTranslations('ko');
    if (currentLang !== 'ko') {
        await loadTranslations(currentLang);
    }
    applyLanguage();
}

async function changeLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('ticket_lang', lang);
    if (!i18nData[lang]) {
        await loadTranslations(lang);
    }
    applyLanguage();
    if (allData && allData.length > 0) {
        renderResults();
    }
}

function applyLanguage() {
    const texts = i18nData[currentLang] || i18nData['ko'] || {};
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (texts[key]) {
            el.textContent = texts[key];
        }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (texts[key]) {
            el.placeholder = texts[key];
        }
    });
    document.getElementById('langSelect').value = currentLang;
    document.title = texts.title || '공연 통합 정보';
}

function t(key) {
    if (i18nData[currentLang] && i18nData[currentLang][key] !== undefined) return i18nData[currentLang][key];
    if (i18nData['ko'] && i18nData['ko'][key] !== undefined) return i18nData['ko'][key];
    return key;
}

// 사전 번역된 데이터에서 번역 텍스트 반환
function getTranslatedText(item, field) {
    if (currentLang === 'ko') return item[field] || '';
    return item[`${field}_${currentLang}`] || item[field] || '';
}

// 지역명 → i18n 키 매핑
function getRegionI18nKey(region) {
    const map = {
        '서울': 'seoul', '경기·인천': 'gyeonggi', '강원': 'gangwon',
        '충청': 'chungcheong', '전라': 'jeolla', '경상': 'gyeongsang', '제주': 'jeju',
        '미분류': 'unclassified'
    };
    return map[region] || region;
}

// 카테고리명 → i18n 키 매핑
function getCategoryI18nKey(category) {
    const map = {
        '아이돌': 'idol', '발라드': 'ballad', '랩/힙합': 'hiphop',
        '락/인디': 'rock', '내한공연': 'worldtour', '팬미팅': 'fanmeeting',
        '페스티벌': 'festival', '트로트': 'trot', '기타': 'etc'
    };
    return map[category] || category;
}

// 현재 날짜 설정
const today = new Date();
const sixtyDaysLater = new Date(today.getTime() + 60 * 24 * 60 * 60 * 1000);

document.getElementById('startDate').value = today.toISOString().split('T')[0];
document.getElementById('endDate').value = sixtyDaysLater.toISOString().split('T')[0];

let allData = [];  // 통합된 공연 리스트
let allDataMap = {};  // hash -> item 매핑
let currentFilter = 'all';  // 장르 필터
let currentPart = 'concert';  // 파트 필터: concert / theater
let currentSource = 'all';  // 소스 필터: all / KOPIS / 인터파크 / 멜론티켓 / YES24
let currentRegion = 'all';  // 지역 필터: all / 서울 / 경기·인천 / 강원 / 충청 / 전라 / 경상 / 제주
let currentView = 'list';  // 현재 뷰: list, calendar
let currentCalendarType = 'ticket';  // 캘린더 타입: ticket, concert
let calendar = null;  // FullCalendar 인스턴스
let favFilterActive = false;  // 관심 공연만 보기 필터

// 홈으로 이동 (초기화)
function goHome() {
    currentPart = 'concert';
    currentSource = 'all';
    currentFilter = 'all';
    document.querySelectorAll('.part-tab').forEach(b => b.classList.remove('active'));
    document.querySelector('.part-tab').classList.add('active');
    document.querySelectorAll('.source-tab').forEach(b => b.classList.remove('active'));
    document.querySelector('.source-tab').classList.add('active');
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.tab-btn').classList.add('active');
    currentRegion = 'all';
    document.querySelectorAll('.region-tab').forEach(b => b.classList.remove('active'));
    document.querySelector('.region-tab').classList.add('active');
    document.getElementById('keyword').value = '';
    document.getElementById('genreTabs').style.display = 'flex';
    loadAllData();
}

// 파트 전환 (콘서트 / 연극&뮤지컬)
function switchPart(part, btn) {
    currentPart = part;
    currentFilter = 'all';  // 장르 필터 초기화
    document.querySelectorAll('.part-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    // 장르 탭은 콘서트 파트에서만 표시
    const genreTabs = document.getElementById('genreTabs');
    if (part === 'concert') {
        genreTabs.style.display = 'flex';
    } else {
        genreTabs.style.display = 'none';
    }

    // 장르 탭 초기화
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.tab-btn').classList.add('active');

    renderResults();
    // 캘린더 업데이트
    if (currentView === 'calendar' && calendar) {
        updateCalendarEvents();
    }
}

// 소스 필터
function filterSource(source, btn) {
    currentSource = source;
    document.querySelectorAll('.source-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderResults();
}

// 지역 필터
function filterRegion(region, btn) {
    currentRegion = region;
    document.querySelectorAll('.region-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderResults();
    if (currentView === 'calendar' && calendar) {
        updateCalendarEvents();
    }
}

// 뷰 전환 (목록 / 캘린더)
function switchView(view, btn) {
    currentView = view;
    document.querySelectorAll('.view-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    if (view === 'list') {
        document.getElementById('listView').style.display = 'block';
        document.getElementById('calendarView').classList.remove('active');
    } else {
        document.getElementById('listView').style.display = 'none';
        document.getElementById('calendarView').classList.add('active');
        initCalendar();
    }
}

// 캘린더 타입 전환 (예매오픈 / 공연일정)
function switchCalendar(type, btn) {
    currentCalendarType = type;
    document.querySelectorAll('.calendar-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    updateCalendarEvents();
}

// 캘린더 초기화
function initCalendar() {
    if (calendar) {
        updateCalendarEvents();
        return;
    }

    const calendarEl = document.getElementById('calendar');
    calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'ko',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,listMonth'
        },
        buttonText: {
            today: '오늘',
            month: '월간',
            list: '목록'
        },
        height: 'auto',
        eventClick: function(info) {
            const item = info.event.extendedProps.item;
            if (item) showDetail(item);
        },
        eventDidMount: function(info) {
            // 툴팁 추가
            info.el.title = info.event.title;
        }
    });
    calendar.render();
    updateCalendarEvents();
}

// 캘린더 이벤트 업데이트
function updateCalendarEvents() {
    if (!calendar) return;

    // 기존 이벤트 삭제
    calendar.removeAllEvents();

    // 파트 + 지역 필터 적용
    let filteredData = allData.filter(item => {
        const itemPart = item.part || 'concert';
        if (itemPart !== currentPart) return false;
        if (currentRegion !== 'all' && item.region !== currentRegion) return false;
        return true;
    });

    // 새 이벤트 추가
    const events = [];
    filteredData.forEach(item => {
        if (currentCalendarType === 'ticket') {
            // 예매오픈 캘린더 - ticket_open 날짜 사용
            if (item.ticket_open) {
                const dateMatch = item.ticket_open.match(/(\d{4})\.(\d{2})\.(\d{2})/);
                if (dateMatch) {
                    events.push({
                        title: getTranslatedText(item, 'name').substring(0, 20) + (getTranslatedText(item, 'name').length > 20 ? '...' : ''),
                        start: `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}`,
                        className: 'ticket-open',
                        extendedProps: { item: item }
                    });
                }
            }
        } else {
            // 공연일정 캘린더 - start_date 또는 date 사용
            let dateStr = item.start_date || item.date || '';
            const dateMatch = dateStr.match(/(\d{4})\.(\d{2})\.(\d{2})/);
            if (dateMatch) {
                let endDate = null;
                if (item.end_date) {
                    const endMatch = item.end_date.match(/(\d{4})\.(\d{2})\.(\d{2})/);
                    if (endMatch) {
                        // 종료일 +1일 (FullCalendar는 종료일 미포함)
                        const ed = new Date(`${endMatch[1]}-${endMatch[2]}-${endMatch[3]}`);
                        ed.setDate(ed.getDate() + 1);
                        endDate = ed.toISOString().split('T')[0];
                    }
                }
                events.push({
                    title: item.name.substring(0, 20) + (item.name.length > 20 ? '...' : ''),
                    start: `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}`,
                    end: endDate,
                    className: 'concert-date',
                    extendedProps: { item: item }
                });
            }
        }
    });

    calendar.addEventSource(events);
}

// 탭 전환 (세부 장르 필터)
function showTab(filter, btn) {
    currentFilter = filter;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderResults();
}

// 전체 데이터 로드 (2단계: 빠른 로딩 → 백그라운드 추가)
async function loadAllData() {
    const resultsDiv = document.getElementById('results');
    const startDate = document.getElementById('startDate').value.replace(/-/g, '');
    const endDate = document.getElementById('endDate').value.replace(/-/g, '');

    // 로딩 UI 표시
    const tips = [
        'KOPIS 공연예술통합전산망에서 데이터를 가져오고 있습니다...',
        '인터파크 티켓 정보를 조회 중입니다...',
        '공연 정보를 콘서트 / 연극&뮤지컬로 분류하고 있습니다...',
        '서울, 경기, 강원 등 7개 권역으로 지역을 분류 중...',
        '중복 공연을 정리하고 판매처를 통합하고 있습니다...',
        '거의 다 됐어요! 조금만 더 기다려주세요...'
    ];

    resultsDiv.innerHTML = `
        <div class="loading-container">
            <div class="loading-spinner-lg"></div>
            <h3>${t('loading')}</h3>
            <div class="loading-steps">
                <div class="loading-step-item active" id="stepKopis">⏳ KOPIS 공연 데이터 조회 중...</div>
                <div class="loading-step-item" id="stepInterpark">⏳ 인터파크 티켓 조회 대기</div>
                <div class="loading-step-item" id="stepMelon">⏳ 멜론티켓 대기</div>
                <div class="loading-step-item" id="stepYes24">⏳ YES24 대기</div>
            </div>
            <div class="loading-tip" id="loadingTip">${tips[0]}</div>
        </div>
    `;

    // 팁 로테이션
    let tipIdx = 0;
    const tipInterval = setInterval(() => {
        tipIdx = (tipIdx + 1) % tips.length;
        const el = document.getElementById('loadingTip');
        if (el) el.textContent = tips[tipIdx];
    }, 3000);

    try {
        // Phase 1: 빠른 로딩 (KOPIS + 인터파크만, Selenium 제외)
        const fastResponse = await fetch(`/api/all?start_date=${startDate}&end_date=${endDate}&skip_selenium=true`);
        const fastResult = await fastResponse.json();

        clearInterval(tipInterval);

        if (fastResult.success) {
            allData = fastResult.data;
            allDataMap = {};
            allData.forEach(item => {
                if (item.hash) allDataMap[item.hash] = item;
            });
            updateStats(fastResult.stats);
            document.getElementById('updateInfo').textContent = `${t('lastUpdate')}: ${fastResult.timestamp}`;
            renderResults();
            if (currentView === 'calendar' && calendar) {
                updateCalendarEvents();
            }

            // Phase 2: 백그라운드에서 멜론/YES24 추가 로딩
            const bgBar = document.createElement('div');
            bgBar.id = 'bgLoadingBar';
            bgBar.className = 'bg-loading-bar';
            bgBar.innerHTML = '🔄 멜론티켓 · YES24 추가 데이터 로딩 중...';
            resultsDiv.parentNode.insertBefore(bgBar, resultsDiv);

            fetch(`/api/all?start_date=${startDate}&end_date=${endDate}`)
                .then(r => r.json())
                .then(fullResult => {
                    const bar = document.getElementById('bgLoadingBar');
                    if (bar) bar.remove();
                    if (fullResult.success && fullResult.data.length > allData.length) {
                        allData = fullResult.data;
                        allDataMap = {};
                        allData.forEach(item => {
                            if (item.hash) allDataMap[item.hash] = item;
                        });
                        updateStats(fullResult.stats);
                        renderResults();
                        if (currentView === 'calendar' && calendar) {
                            updateCalendarEvents();
                        }
                    } else if (bar) {
                        bar.remove();
                    }
                })
                .catch(() => {
                    const bar = document.getElementById('bgLoadingBar');
                    if (bar) bar.textContent = '⚠️ 멜론·YES24 추가 로딩 실패 (Selenium 필요)';
                });
        } else {
            resultsDiv.innerHTML = `<div class="empty-state"><h3>오류 발생</h3><p>${escapeHtml(fastResult.error)}</p></div>`;
        }
    } catch (error) {
        clearInterval(tipInterval);
        resultsDiv.innerHTML = `<div class="empty-state"><h3>오류 발생</h3><p>${escapeHtml(error.message)}</p></div>`;
    }
}

// 통계 업데이트
function updateStats(stats) {
    document.getElementById('totalCount').textContent = stats.total || 0;
    document.getElementById('kopisCount').textContent = stats.kopis || 0;
    document.getElementById('interparkCount').textContent = stats.interpark || 0;
    document.getElementById('melonCount').textContent = stats.melon || 0;
    document.getElementById('yes24Count').textContent = stats.yes24 || 0;
}

// D-day 뱃지 생성
function getDdayBadge(dday) {
    if (dday === null || dday === undefined) return '';

    let className = 'dday-normal';
    let text = '';

    if (dday < 0) {
        text = '종료';
        className = 'dday-normal';
    } else if (dday === 0) {
        text = 'D-Day';
        className = 'dday-urgent';
    } else if (dday <= 7) {
        text = `D-${dday}`;
        className = 'dday-urgent';
    } else if (dday <= 14) {
        text = `D-${dday}`;
        className = 'dday-soon';
    } else {
        text = `D-${dday}`;
        className = 'dday-normal';
    }

    return `<span class="dday-badge ${className}">${text}</span>`;
}

// 지역 색상 반환
function getRegionColor(region) {
    const colors = {
        '서울': '#2563EB',
        '경기·인천': '#059669',
        '강원': '#0891B2',
        '충청': '#7C3AED',
        '전라': '#EA580C',
        '경상': '#DC2626',
        '제주': '#DB2777',
        '미분류': '#888888'
    };
    return colors[region] || '#888';
}

// 판매처 뱃지 생성
function getSiteBadges(availableSites) {
    if (!availableSites || availableSites.length === 0) return '';

    return availableSites.map(site => {
        const icon = site.name === 'KOPIS' ? 'K' :
                    site.name === '인터파크' ? 'I' :
                    site.name === '멜론티켓' ? 'M' :
                    site.name === 'YES24' ? 'Y' : '?';
        return `<span class="site-badge" style="background: ${escapeHtml(site.color)}30; color: ${escapeHtml(site.color)}" title="${escapeHtml(site.name)}">${icon}</span>`;
    }).join('');
}

// 결과 렌더링
function renderResults() {
    const resultsDiv = document.getElementById('results');
    let html = '';

    // 검색어 필터
    const keyword = document.getElementById('keyword').value.trim().toLowerCase();

    // 필터 적용
    let filteredData = allData;

    // 1. 파트 필터링 (concert / theater)
    filteredData = filteredData.filter(item => {
        const itemPart = item.part || 'concert';
        return itemPart === currentPart;
    });

    // 2. 소스 필터링
    if (currentSource !== 'all') {
        filteredData = filteredData.filter(item => {
            if (item.available_sites) {
                return item.available_sites.some(site => site.name === currentSource);
            }
            return item.source === currentSource;
        });
    }

    // 3. 지역 필터링
    if (currentRegion !== 'all') {
        filteredData = filteredData.filter(item => item.region === currentRegion);
    }

    // 4. 검색어 필터링
    if (keyword) {
        filteredData = filteredData.filter(item => {
            const name = (item.name || '').toLowerCase();
            const venue = (item.venue || '').toLowerCase();
            return name.includes(keyword) || venue.includes(keyword);
        });
    }

    // 5. 장르 필터링 (콘서트 파트에서만)
    if (currentPart === 'concert' && currentFilter !== 'all') {
        filteredData = filteredData.filter(item => item.category === currentFilter);
    }

    // 6. 관심 공연만 보기 필터
    if (favFilterActive) {
        const favs = getFavorites();
        filteredData = filteredData.filter(item => item.hash && favs[item.hash]);
    }

    if (filteredData.length > 0) {
        const countText = currentLang === 'ko' || currentLang === 'ja' || currentLang === 'zh' ?
            `(${filteredData.length}${t('count')})` : `(${filteredData.length})`;
        html += `
            <div class="source-section">
                <h3>
                    <span class="source-icon" style="background: #7c3aed30; color: #7c3aed">🎫</span>
                    ${t('performanceList')} ${countText} - ${t('sortByDday')}
                </h3>
                <div class="results-grid">
        `;

        filteredData.forEach((item) => {
            const ddayBadge = getDdayBadge(item.dday);
            const siteBadges = getSiteBadges(item.available_sites);
            const categoryBadge = item.category ?
                `<span class="category-badge">${t(getCategoryI18nKey(item.category))}</span>` : '';

            // YES24/멜론 이미지는 캐싱 프록시 사용
            let posterUrl = item.poster || '';
            if (posterUrl && (posterUrl.includes('yes24.com') || posterUrl.includes('melon.com') || posterUrl.includes('tkfile'))) {
                posterUrl = '/api/proxy/image?url=' + encodeURIComponent(posterUrl);
            }

            const isFav = isFavorite(item.hash);

            const displayName = getTranslatedText(item, 'name') || t('noTitle');
            const displayVenue = getTranslatedText(item, 'venue');

            html += `
                <div class="card" data-hash="${escapeHtml(item.hash)}">
                    <div class="card-img">
                        ${posterUrl ? `<img src="${escapeHtml(posterUrl)}" alt="${escapeHtml(displayName)}" loading="lazy" onerror="this.onerror=null; this.style.display='none'; this.parentElement.classList.add('no-poster');">` : ''}
                        ${ddayBadge}
                        ${categoryBadge}
                        <button class="fav-btn ${isFav ? 'active' : ''}" data-fav-hash="${escapeHtml(item.hash)}" title="${t('addFavorite')}">${isFav ? '♥' : '♡'}</button>
                    </div>
                    <div class="card-body">
                        <div class="card-title">${escapeHtml(displayName)}</div>
                        ${displayVenue ? `<div class="card-info"><span>${t('venue')}</span> ${escapeHtml(displayVenue)}</div>` : ''}
                        ${item.start_date ? `<div class="card-info"><span>${t('period')}</span> ${escapeHtml(item.start_date)} ~ ${escapeHtml(item.end_date || '')}</div>` : ''}
                        ${item.date ? `<div class="card-info"><span>${t('date')}</span> ${escapeHtml(item.date)}</div>` : ''}
                        ${item.ticket_open ? `<div class="card-info"><span>${t('ticketOpen')}</span> ${escapeHtml(item.ticket_open)}</div>` : ''}
                        <div class="site-badges">${siteBadges}</div>
                        ${item.region ? `<span class="region-badge" style="background: ${getRegionColor(item.region)}30; color: ${getRegionColor(item.region)}">${t(getRegionI18nKey(item.region))}</span>` : ''}
                    </div>
                </div>
            `;
        });

        html += '</div></div>';
    }

    if (!html) {
        html = `<div class="empty-state"><h3>${t('noResults')}</h3><p>${t('tryOther')}</p></div>`;
    }

    resultsDiv.innerHTML = html;
}

// hash로 상세 팝업 표시
function showDetailByHash(hash) {
    const item = allDataMap[hash];
    if (item) {
        showDetail(item);
    } else {
        console.error('아이템을 찾을 수 없습니다:', hash);
    }
}

// 상세 팝업 표시
async function showDetail(item) {
    const modal = document.getElementById('modalOverlay');

    // 번역된 텍스트 사용
    const displayName = getTranslatedText(item, 'name') || t('noTitle');
    const displayVenue = getTranslatedText(item, 'venue') || '-';

    // 기본 정보 설정 + 찜 버튼 (DOM API로 안전하게 구성)
    const isFav = isFavorite(item.hash);
    const titleEl = document.getElementById('modalTitle');
    titleEl.textContent = '';
    titleEl.appendChild(document.createTextNode(displayName));
    const modalFavBtn = document.createElement('button');
    modalFavBtn.className = `modal-fav-btn ${isFav ? 'active' : ''}`;
    modalFavBtn.textContent = isFav ? '♥ ' + t('removeFavorite') : '♡ ' + t('addToFavorite');
    modalFavBtn.addEventListener('click', function() { toggleFavorite(item.hash, this, true); });
    titleEl.appendChild(modalFavBtn);
    document.getElementById('modalVenue').textContent = displayVenue;
    document.getElementById('modalGenre').textContent = item.genre || '-';
    document.getElementById('modalState').textContent = item.state || '-';
    document.getElementById('modalTicketOpen').textContent = item.ticket_open || '-';

    // 날짜 정보
    if (item.start_date) {
        document.getElementById('modalDate').textContent = `${item.start_date} ~ ${item.end_date || ''}`;
    } else if (item.date) {
        document.getElementById('modalDate').textContent = item.date;
    } else {
        document.getElementById('modalDate').textContent = '-';
    }

    // 포스터 (YES24/멜론은 캐싱 프록시 사용)
    const posterDiv = document.getElementById('modalPoster');
    if (item.poster) {
        let modalPosterUrl = item.poster;
        if (modalPosterUrl.includes('yes24.com') || modalPosterUrl.includes('melon.com') || modalPosterUrl.includes('tkfile')) {
            modalPosterUrl = '/api/proxy/image?url=' + encodeURIComponent(modalPosterUrl);
        }
        posterDiv.innerHTML = `<img src="${escapeHtml(modalPosterUrl)}" alt="${escapeHtml(displayName)}" onerror="this.parentElement.innerHTML='<span>No Image</span>'">`;
    } else {
        posterDiv.innerHTML = '<span>No Image</span>';
    }

    // D-day
    const ddayDiv = document.getElementById('modalDday');
    if (item.dday !== null && item.dday !== undefined) {
        let ddayText = item.dday === 0 ? 'D-Day' : (item.dday > 0 ? `D-${item.dday}` : '종료');
        let ddayClass = item.dday <= 7 ? 'dday-urgent' : (item.dday <= 14 ? 'dday-soon' : 'dday-normal');
        ddayDiv.textContent = ddayText;
        ddayDiv.className = `modal-dday ${ddayClass}`;
        ddayDiv.style.display = 'inline-block';
    } else {
        ddayDiv.style.display = 'none';
    }

    // 예매 링크 영역 초기화
    const linksDiv = document.getElementById('modalLinks');
    linksDiv.innerHTML = '<p style="color: #888;">예매 정보 로딩 중...</p>';

    // KOPIS인 경우 상세 정보 + 실제 예매 링크 로드
    if (item.id) {
        try {
            const response = await fetch(`/api/kopis/performance/${item.id}`);
            const result = await response.json();
            if (result.success) {
                const detail = result.data;
                document.getElementById('modalPrice').textContent = detail.price || '-';
                document.getElementById('modalCast').textContent = detail.cast || '-';
                if (detail.schedule) {
                    document.getElementById('modalDate').textContent += ` (${detail.schedule})`;
                }

                // 실제 예매 링크 표시 (KOPIS API에서 제공)
                let linksHtml = '';
                if (detail.booking_sites && detail.booking_sites.length > 0) {
                    detail.booking_sites.forEach(site => {
                        linksHtml += `<a href="${sanitizeUrl(escapeHtml(site.url))}" target="_blank" rel="noopener noreferrer" class="modal-link-btn" style="background: ${escapeHtml(site.color)}; color: #fff;">${escapeHtml(site.name)} 예매</a>`;
                    });
                    linksDiv.innerHTML = linksHtml;
                } else {
                    linksDiv.innerHTML = '<p style="color: #888;">등록된 예매처가 없습니다.</p>';
                }
            } else {
                document.getElementById('modalPrice').textContent = '-';
                document.getElementById('modalCast').textContent = '-';
                linksDiv.innerHTML = '<p style="color: #888;">예매 정보를 불러올 수 없습니다.</p>';
            }
        } catch (e) {
            console.log('상세 정보 로드 실패:', e);
            document.getElementById('modalPrice').textContent = '-';
            document.getElementById('modalCast').textContent = '-';
            linksDiv.innerHTML = '<p style="color: #888;">예매 정보를 불러올 수 없습니다.</p>';
        }
    } else {
        // KOPIS ID가 없는 경우 (크롤링 데이터) - 기본 정보만 표시
        document.getElementById('modalPrice').textContent = '-';
        document.getElementById('modalCast').textContent = '-';

        // 예매 링크 표시
        let linksHtml = '';
        if (item.available_sites && item.available_sites.length > 0) {
            item.available_sites.forEach(site => {
                if (site.link && site.link !== '') {
                    linksHtml += `<a href="${sanitizeUrl(escapeHtml(site.link))}" target="_blank" rel="noopener noreferrer" class="modal-link-btn" style="background: ${escapeHtml(site.color)}; color: #fff;">${escapeHtml(site.name)} 예매</a>`;
                }
            });
        }
        linksDiv.innerHTML = linksHtml || '<p style="color: #888;">예매 링크 정보가 없습니다.</p>';
    }

    modal.classList.add('active');
    document.body.classList.add('modal-open');
    document.body.style.overflow = 'hidden';
}

// 모달 닫기
function closeModal(event) {
    if (event && event.target !== document.getElementById('modalOverlay')) return;
    document.getElementById('modalOverlay').classList.remove('active');
    document.body.classList.remove('modal-open');
    document.body.style.overflow = '';
}

// ESC 키로 모달 닫기
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// iOS 터치 이벤트 최적화 - 카드 클릭 + 찜 버튼 (이벤트 위임)
document.getElementById('results').addEventListener('click', function(e) {
    // 찜 버튼 클릭 처리
    const favBtn = e.target.closest('.fav-btn');
    if (favBtn) {
        e.stopPropagation();
        const hash = favBtn.dataset.favHash;
        if (hash) toggleFavorite(hash, favBtn);
        return;
    }
    // 카드 클릭 처리
    const card = e.target.closest('.card');
    if (card) {
        const hash = card.dataset.hash;
        if (hash) {
            e.preventDefault();
            showDetailByHash(hash);
        }
    }
});

// iOS에서 모달 닫기 터치 이벤트
document.getElementById('modalOverlay').addEventListener('touchend', function(e) {
    if (e.target === this) {
        closeModal();
    }
});

// 검색어 입력 시 실시간 필터링
document.getElementById('keyword').addEventListener('input', function(e) {
    if (allData.length > 0) {
        renderResults();
    }
});

// Enter 키로 데이터 새로 로드
document.getElementById('keyword').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        loadAllData();
    }
});

// =============================================
// 관심 공연 (찜) 관리 - LocalStorage
// =============================================

function getFavorites() {
    try {
        return JSON.parse(localStorage.getItem('ticket_favorites') || '{}');
    } catch { return {}; }
}

function saveFavorites(favs) {
    localStorage.setItem('ticket_favorites', JSON.stringify(favs));
}

function isFavorite(hash) {
    if (!hash) return false;
    const favs = getFavorites();
    return !!favs[hash];
}

function toggleFavorite(hash, btnEl, isModal) {
    if (!hash) return;
    const favs = getFavorites();
    const item = allDataMap[hash];

    if (favs[hash]) {
        // 찜 해제
        delete favs[hash];
        if (btnEl) {
            if (isModal) {
                btnEl.classList.remove('active');
                btnEl.innerHTML = '♡ 찜하기';
            } else {
                btnEl.classList.remove('active');
                btnEl.textContent = '♡';
            }
        }
    } else {
        // 찜 등록
        if (item) {
            favs[hash] = {
                name: item.name || '',
                ticket_open: item.ticket_open || '',
                dday: item.dday,
                start_date: item.start_date || '',
                venue: item.venue || ''
            };
        }
        if (btnEl) {
            if (isModal) {
                btnEl.classList.add('active');
                btnEl.innerHTML = '♥ 찜 해제';
            } else {
                btnEl.classList.add('active');
                btnEl.textContent = '♥';
            }
        }
    }

    saveFavorites(favs);
    updateFavCount();

    // 카드의 찜 버튼 상태도 동기화
    if (isModal) {
        const cardBtn = document.querySelector(`.fav-btn[data-hash="${hash}"]`);
        if (cardBtn) {
            if (favs[hash]) {
                cardBtn.classList.add('active');
                cardBtn.textContent = '♥';
            } else {
                cardBtn.classList.remove('active');
                cardBtn.textContent = '♡';
            }
        }
    }
}

function updateFavCount() {
    const favs = getFavorites();
    const count = Object.keys(favs).length;
    document.getElementById('favCount').textContent = count;
}

function toggleFavFilter() {
    favFilterActive = !favFilterActive;
    const badge = document.getElementById('favCountBadge');
    if (favFilterActive) {
        badge.classList.add('filter-active');
    } else {
        badge.classList.remove('filter-active');
    }
    renderResults();
}


// =============================================
// 브라우저 알림 (Notification API)
// =============================================

let notiCheckInterval = null;

// 기기 감지: iOS 또는 네이버앱인지 확인
function isUnsupportedDevice() {
    const ua = navigator.userAgent || '';
    const isIOS = /iPhone|iPad|iPod/i.test(ua);
    const isNaverApp = /NAVER/i.test(ua);
    return isIOS || isNaverApp;
}

function toggleNotification(enabled) {
    const statusEl = document.getElementById('notiStatus');

    // iOS/네이버앱은 알림 미지원
    if (isUnsupportedDevice()) {
        alert('iOS 또는 네이버 앱에서는 브라우저 알림이 지원되지 않습니다.\n\nSafari에서 홈 화면에 추가하거나, Chrome/Samsung 브라우저를 이용해주세요.');
        document.getElementById('notiToggle').checked = false;
        statusEl.textContent = '미지원 기기';
        statusEl.style.color = '#ff4444';
        return;
    }

    if (enabled) {
        // 브라우저 알림 권한 요청
        if (!('Notification' in window)) {
            alert('이 브라우저는 알림을 지원하지 않습니다.');
            document.getElementById('notiToggle').checked = false;
            return;
        }

        Notification.requestPermission().then(permission => {
            if (permission === 'granted') {
                localStorage.setItem('ticket_noti_enabled', 'true');
                statusEl.textContent = '활성';
                statusEl.style.color = '#ff4081';
                startNotiCheck();
            } else {
                document.getElementById('notiToggle').checked = false;
                localStorage.setItem('ticket_noti_enabled', 'false');
                statusEl.textContent = '권한 거부됨';
                statusEl.style.color = '#ff4444';
            }
        });
    } else {
        localStorage.setItem('ticket_noti_enabled', 'false');
        statusEl.textContent = '비활성';
        statusEl.style.color = '#666';
        stopNotiCheck();
    }
}

function startNotiCheck() {
    // 30분마다 D-day 체크
    if (notiCheckInterval) clearInterval(notiCheckInterval);
    checkFavoriteDdays(); // 즉시 1회 체크
    notiCheckInterval = setInterval(checkFavoriteDdays, 30 * 60 * 1000);
}

function stopNotiCheck() {
    if (notiCheckInterval) {
        clearInterval(notiCheckInterval);
        notiCheckInterval = null;
    }
}

function checkFavoriteDdays() {
    if (localStorage.getItem('ticket_noti_enabled') !== 'true') return;
    if (Notification.permission !== 'granted') return;

    const favs = getFavorites();
    const todayKey = new Date().toISOString().split('T')[0].replace(/-/g, '.');
    const notifiedKey = `ticket_notified_${todayKey}`;

    // 오늘 이미 알림 보낸 목록
    let notified = {};
    try {
        notified = JSON.parse(localStorage.getItem(notifiedKey) || '{}');
    } catch { notified = {}; }

    for (const [hash, info] of Object.entries(favs)) {
        if (notified[hash]) continue; // 하루 1회 중복 방지

        const dday = info.dday;
        // ticket_open이 있으면 실시간으로 D-day 재계산
        let currentDday = dday;
        if (info.ticket_open) {
            const match = info.ticket_open.match(/(\d{4})\.(\d{2})\.(\d{2})/);
            if (match) {
                const target = new Date(parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3]));
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                currentDday = Math.ceil((target - today) / (1000 * 60 * 60 * 24));
            }
        }

        // D-1 또는 D-Day에만 알림
        if (currentDday === 1 || currentDday === 0) {
            const title = currentDday === 0 ? '오늘 예매 오픈!' : '내일 예매 오픈!';
            const body = `${info.name}\n${info.ticket_open || ''} | ${info.venue || ''}`;

            const notification = new Notification(title, {
                body: body,
                icon: '🎫',
                tag: hash,
                requireInteraction: true
            });

            notification.onclick = function() {
                window.focus();
                // 해당 공연 상세 팝업 열기
                const item = allDataMap[hash];
                if (item) showDetail(item);
                notification.close();
            };

            // 알림 발송 기록
            notified[hash] = true;
            localStorage.setItem(notifiedKey, JSON.stringify(notified));
        }
    }

    // 오래된 알림 기록 정리 (3일 이전 것 삭제)
    cleanupOldNotifiedRecords();
}

function cleanupOldNotifiedRecords() {
    const today = new Date();
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith('ticket_notified_')) {
            const dateStr = key.replace('ticket_notified_', '');
            try {
                const parts = dateStr.split('.');
                const recordDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                const daysDiff = Math.floor((today - recordDate) / (1000 * 60 * 60 * 24));
                if (daysDiff > 3) {
                    localStorage.removeItem(key);
                }
            } catch {}
        }
    }
}

// 알림 초기 상태 복원
function initNotification() {
    const toggle = document.getElementById('notiToggle');
    const statusEl = document.getElementById('notiStatus');

    // iOS/네이버앱은 알림 UI 비활성화
    if (isUnsupportedDevice()) {
        toggle.disabled = true;
        statusEl.textContent = '미지원 기기';
        statusEl.style.color = '#888';
        updateFavCount();
        return;
    }

    const enabled = localStorage.getItem('ticket_noti_enabled') === 'true';

    if (enabled && Notification.permission === 'granted') {
        toggle.checked = true;
        statusEl.textContent = '활성';
        statusEl.style.color = '#ff4081';
        startNotiCheck();
    } else {
        toggle.checked = false;
        localStorage.setItem('ticket_noti_enabled', 'false');
    }

    updateFavCount();
}


// 페이지 로드 시 자동 조회
window.onload = async function() {
    await initI18n();
    initNotification();
    loadAllData();
};
