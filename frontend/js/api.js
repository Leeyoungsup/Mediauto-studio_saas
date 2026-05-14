/**
 * API 클라이언트 — FastAPI 백엔드와 통신
 * JWT 인증 토큰 자동 첨부 + 자동 갱신
 */

const API_BASE = '/api';

// ── 인증 토큰 관리 ──
function _getAccessToken() {
    return localStorage.getItem('access_token') || '';
}

function _getRefreshToken() {
    return localStorage.getItem('refresh_token') || '';
}

function _setTokens(accessToken, refreshToken, expiresIn) {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
    localStorage.setItem('token_expires', Date.now() + expiresIn * 1000);
}

function _clearTokens() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('token_expires');
    localStorage.removeItem('user');
}

function _isTokenExpiringSoon() {
    const expires = parseInt(localStorage.getItem('token_expires') || '0', 10);
    // 2분 전에 갱신
    return Date.now() > expires - 120000;
}

// 동시 다중 호출 직렬화용 싱글톤 프라미스.
// 여러 API 가 거의 동시에 /auth/refresh 를 찌르면 서버의 rotation 로직이 "reuse 공격"
// 으로 오인해 전체 세션을 revoke 해버리는 레이스 컨디션이 있다. 하나가 진행 중이면
// 나머지는 같은 프라미스를 공유해 한 번만 네트워크 호출이 나가도록 한다.
let _refreshInFlight = null;

// bool_force: 만료 임박 체크를 건너뛰고 무조건 refresh 시도 (_authFetch 재시도용)
// bool_silent: 실패 시에도 로그아웃 리다이렉트 하지 않음 (_authFetch 재시도 경로 전용;
//              호출자가 res.status 를 다시 확인해서 처리)
async function _refreshTokenIfNeeded(bool_force = false, bool_silent = false) {
    if (_refreshInFlight) return _refreshInFlight;
    if (!bool_force && !_isTokenExpiringSoon()) return;
    const refreshToken = _getRefreshToken();
    if (!refreshToken) return;

    _refreshInFlight = (async () => {
        try {
            const res = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ str_refresh_token: refreshToken }),
            });
            if (res.ok) {
                const data = await res.json();
                _setTokens(data.str_access_token, data.str_refresh_token, data.int_expires_in);
                if (data.dict_user) {
                    localStorage.setItem('user', JSON.stringify(data.dict_user));
                }
                return true;
            }
            // Refresh 실패. silent 경로(_authFetch 재시도) 면 false 만 리턴,
            // 아니면 여기서 즉시 정리 + 로그인 페이지로. 타이머발 실패가 무한 루프
            // 되는 걸 막는다.
            if (!bool_silent) {
                _clearTokens();
                _clearMediaTicket();
                if (typeof window !== 'undefined' && !window.location.pathname.endsWith('login.html')) {
                    window.location.href = '/login.html';
                }
            }
            return false;
        } catch (e) {
            console.error('Token refresh failed:', e);
            return false;
        } finally {
            _refreshInFlight = null;
        }
    })();
    return _refreshInFlight;
}

// 타일/썸네일 URL 은 <img src> 로 직접 로드되어 _authFetch 를 거치지 않음 → 토큰
// 사전 갱신이 트리거되지 않는다. 백그라운드 타이머로 30초마다 만료 임박 여부를
// 확인해 미리 refresh 해 둔다.
let _refreshTimer = null;
function _startBackgroundTokenRefresh() {
    if (_refreshTimer) return;
    _refreshTimer = setInterval(() => {
        if (_getAccessToken() && _getRefreshToken()) {
            _refreshTokenIfNeeded();
            _ensureMediaTicket();
        }
    }, 30000);
}
if (typeof window !== 'undefined') {
    _startBackgroundTokenRefresh();
}

// ── 미디어 티켓 (타일/썸네일 <img src> 전용) ──
// 과거엔 URL 쿼리에 JWT 를 그대로 실어 보내 브라우저 히스토리/프록시 로그에
// 토큰이 노출되는 문제가 있었다. 이제는 서버의 /auth/media-ticket 엔드포인트로
// 10분 TTL HMAC 오파크 토큰을 받아 `?mt=<token>` 으로 전달한다. 이 티켓은
// 미디어 엔드포인트에만 유효하며, 누출되어도 API 호출 권한은 없다.
let _mediaTicket = null;          // {str_token, int_exp, int_ttl}
let _mediaTicketInFlight = null;  // 중복 발급 방지용 프라미스

function _isMediaTicketValid() {
    if (!_mediaTicket || !_mediaTicket.str_token) return false;
    const int_now = Math.floor(Date.now() / 1000);
    // 만료 120초 전에 갱신
    return _mediaTicket.int_exp - int_now > 120;
}

async function _ensureMediaTicket() {
    if (_isMediaTicketValid()) return _mediaTicket.str_token;
    if (_mediaTicketInFlight) return _mediaTicketInFlight;
    if (!_getAccessToken()) return '';

    _mediaTicketInFlight = (async () => {
        try {
            // 주의: _authFetch 는 내부적으로 _ensureMediaTicket 을 호출하므로
            // 여기서 다시 _authFetch 를 쓰면 무한 루프가 된다. 직접 fetch.
            const res = await fetch(`${API_BASE}/auth/media-ticket`, {
                headers: { 'Authorization': `Bearer ${_getAccessToken()}` },
            });
            if (res.ok) {
                _mediaTicket = await res.json();
                return _mediaTicket.str_token;
            }
        } catch (e) {
            console.error('Media ticket fetch failed:', e);
        } finally {
            _mediaTicketInFlight = null;
        }
        return '';
    })();
    return _mediaTicketInFlight;
}

function _getMediaTicketSync() {
    if (!_mediaTicket || !_mediaTicket.str_token) return '';
    // 만료 임박(120초 이내)이면 백그라운드 갱신 트리거
    const int_now = Math.floor(Date.now() / 1000);
    if (_mediaTicket.int_exp - int_now <= 120) {
        _ensureMediaTicket();  // fire-and-forget (async)
    }
    // 완전히 만료된 토큰은 반환하지 않음 — 401 방지
    if (_mediaTicket.int_exp <= int_now) return '';
    return _mediaTicket.str_token;
}

function _clearMediaTicket() {
    _mediaTicket = null;
    _mediaTicketInFlight = null;
}

function _authHeaders() {
    return {
        'Authorization': `Bearer ${_getAccessToken()}`,
        'X-Requested-With': 'XMLHttpRequest',
    };
}

async function _authFetch(url, options = {}) {
    await _refreshTokenIfNeeded();
    // 미디어 티켓 pre-fetch: 슬라이드 오픈·info 호출 시 자동으로 준비되어
    // 이후 <img src> 가 즉시 유효한 ?mt= 를 쓸 수 있게 된다. 캐시 히트 시
    // 네트워크 호출 없이 즉시 리턴한다.
    await _ensureMediaTicket();

    const headers_initial = { ...(options.headers || {}), ..._authHeaders() };
    let res = await fetch(url, { ...options, headers: headers_initial });

    // 401 을 받으면 바로 로그아웃하지 않고, 강제 refresh 후 1회 재시도.
    // 시나리오:
    //   - access 토큰이 예상보다 일찍 만료 (clock drift / 탭 suspend)
    //   - 다른 탭이 rotation 중이라 localStorage 동기화 지연
    // 재시도까지 실패하면 그때 토큰 정리 + 로그인 페이지.
    // refresh 토큰이 아예 없는 경우(완전 미로그인 / 만료 후 정리됨) 도
    // 똑같이 로그인 페이지로 보내야 호출 측이 빈 뷰어에 머무는 것을 막는다.
    if (res.status === 401) {
        if (_getRefreshToken()) {
            const bool_refreshed = await _refreshTokenIfNeeded(true, true);
            if (bool_refreshed) {
                const headers_retry = { ...(options.headers || {}), ..._authHeaders() };
                res = await fetch(url, { ...options, headers: headers_retry });
            }
        }
        if (res.status === 401) {
            _clearTokens();
            _clearMediaTicket();
            if (typeof window !== 'undefined' && !window.location.pathname.endsWith('login.html')) {
                window.location.href = '/login.html';
            }
            throw new Error('Authentication required');
        }
    }

    return res;
}

export const api = {
    // ── 슬라이드 ──

    /** 폴더 탐색 (하위 폴더 + 슬라이드 목록) */
    async browse(path = '') {
        const res = await _authFetch(`${API_BASE}/slides/browse?path=${encodeURIComponent(path)}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 서버에 파일이 있는지 확인 후 바로 열기 */
    async listProjects() {
        const res = await _authFetch(`${API_BASE}/slides/projects`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async dashboard(includeStorage = false) {
        const qs = includeStorage ? '?include_storage=true' : '';
        const res = await _authFetch(`${API_BASE}/slides/dashboard${qs}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async createProject(name, info = {}) {
        const form = new FormData();
        form.append('name', name);
        for (const key of ['title', 'institution', 'department', 'owner', 'status', 'due_date', 'description']) {
            form.append(key, info[key] || '');
        }
        const res = await _authFetch(`${API_BASE}/slides/project/create`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async updateProject(name, info = {}) {
        const form = new FormData();
        form.append('name', name);
        for (const key of ['title', 'institution', 'department', 'owner', 'status', 'due_date', 'description']) {
            form.append(key, info[key] || '');
        }
        const res = await _authFetch(`${API_BASE}/slides/project/update`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async renameProject(name, newName) {
        const form = new FormData();
        form.append('name', name);
        form.append('new_name', newName);
        const res = await _authFetch(`${API_BASE}/slides/project/rename`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async moveFolderToProject(srcPath, dstProject) {
        const form = new FormData();
        form.append('src_path', srcPath);
        form.append('dst_project', dstProject);
        const res = await _authFetch(`${API_BASE}/slides/project/move-folder`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async deleteProject(name) {
        const form = new FormData();
        form.append('name', name);
        const res = await _authFetch(`${API_BASE}/slides/project/delete`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async openSlide(filename, path = '') {
        const form = new FormData();
        form.append('filename', filename);
        form.append('path', path);
        const res = await _authFetch(`${API_BASE}/slides/open`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 폴더 생성 */
    async createFolder(path, name) {
        const form = new FormData();
        form.append('path', path);
        form.append('name', name);
        const res = await _authFetch(`${API_BASE}/slides/folder/create`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 폴더 이름 변경 */
    async renameFolder(path, newName) {
        const form = new FormData();
        form.append('path', path);
        form.append('new_name', newName);
        const res = await _authFetch(`${API_BASE}/slides/folder/rename`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 폴더 삭제 */
    async deleteFolder(path) {
        const form = new FormData();
        form.append('path', path);
        const res = await _authFetch(`${API_BASE}/slides/folder/delete`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 폴더 AI 자동 추론 설정 조회 */
    async getFolderAiConfig(path) {
        const q = new URLSearchParams({ path: path || '' });
        const res = await _authFetch(`${API_BASE}/slides/folder-config?${q}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 폴더 AI 자동 추론 설정 저장 */
    async saveFolderAiConfig(path, enabled, tasks) {
        const form = new FormData();
        form.append('path', path || '');
        form.append('enabled', enabled ? 'true' : 'false');
        form.append('tasks_json', JSON.stringify(tasks || []));
        const res = await _authFetch(`${API_BASE}/slides/folder-config`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 폴더 AI 자동 추론 설정 삭제 */
    async deleteFolderAiConfig(path) {
        const q = new URLSearchParams({ path: path || '' });
        const res = await _authFetch(`${API_BASE}/slides/folder-config?${q}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 파일들 + AI 결과/타일 캐시 일괄 삭제 */
    async deleteFiles(filenames, path = '') {
        const form = new FormData();
        form.append('filenames_json', JSON.stringify(filenames || []));
        form.append('path', path || '');
        const res = await _authFetch(`${API_BASE}/slides/file/delete`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 슬라이드 리뷰 상태 설정 ("", pending, in_progress, done, flagged) */
    async setFileStatus(filenames, status, path = '', scope = '') {
        const form = new FormData();
        form.append('filenames_json', JSON.stringify(filenames || []));
        form.append('status', status || '');
        form.append('path', path || '');
        if (scope) form.append('scope', scope);
        const res = await _authFetch(`${API_BASE}/slides/file/status`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 파일 이동 */
    async moveFile(filename, srcPath, dstPath) {
        const form = new FormData();
        form.append('filename', filename);
        form.append('src_path', srcPath);
        form.append('dst_path', dstPath);
        const res = await _authFetch(`${API_BASE}/slides/file/move`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 청크 업로드 시작 */
    async uploadStart(filename) {
        const form = new FormData();
        form.append('filename', filename);
        const res = await _authFetch(`${API_BASE}/slides/upload/start`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 청크 업로드 */
    async uploadChunk(uploadId, chunkIndex, blob) {
        const form = new FormData();
        form.append('upload_id', uploadId);
        form.append('chunk_index', chunkIndex.toString());
        form.append('chunk', blob);
        const res = await _authFetch(`${API_BASE}/slides/upload/chunk`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 청크 업로드 완료 */
    async uploadComplete(uploadId, filename, totalChunks, path = '') {
        const form = new FormData();
        form.append('upload_id', uploadId);
        form.append('filename', filename);
        form.append('total_chunks', totalChunks.toString());
        form.append('path', path);
        const res = await _authFetch(`${API_BASE}/slides/upload/complete`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 슬라이드 정보 */
    async getSlideInfo(slideId) {
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/info`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 썸네일 URL (slide_id 기반 — 슬라이드 열린 후).
     *  ndpMatch=true 면 NDP 색 매칭 2차 보정본을 받는다 (Hamamatsu 토글용). */
    thumbnailUrl(slideId, size = 300, ndpMatch = false) {
        const str_ndp = ndpMatch ? '&ndp=true' : '';
        return `${API_BASE}/slides/${slideId}/thumbnail?size=${size}${str_ndp}&mt=${encodeURIComponent(_getMediaTicketSync())}`;
    },

    /** 고해상도 프리뷰 URL (PDF 리포트용).  ndpMatch 동일. */
    previewUrl(slideId, size = 2048, ndpMatch = false) {
        const str_ndp = ndpMatch ? '&ndp=true' : '';
        return `${API_BASE}/slides/${slideId}/preview?size=${size}${str_ndp}&mt=${encodeURIComponent(_getMediaTicketSync())}`;
    },

    /** 썸네일 URL (파일명 기반 — 리스트용, slide_manager 불필요) */
    thumbnailUrlByName(filename, path = '', size = 300) {
        return `${API_BASE}/slides/thumbnail-by-name?filename=${encodeURIComponent(filename)}&path=${encodeURIComponent(path)}&size=${size}&mt=${encodeURIComponent(_getMediaTicketSync())}`;
    },

    /** 미디어 티켓이 준비되지 않았다면 기다린다. 슬라이드 뷰어 초기 렌더에서 호출. */
    async ensureMediaReady() {
        await _ensureMediaTicket();
    },

    /**
     * 썸네일 <img> 에 attach 하는 헬퍼 — 401(만료된 mt) 로딩 실패 시 새 티켓으로 1회 재시도.
     *
     * 페이지를 10분 이상 열어두면 처음 박힌 mt 가 만료되어 lazy-load / 캐시 미스 fetch 가
     * 401 로 떨어진다. _ensureMediaTicket() 은 백그라운드 변수만 갱신하고 이미 DOM 에 박힌
     * src 는 안 바뀌므로 onerror 에서 직접 교체해 준다.
     *
     * fn_on_final_error: 재시도까지 실패한 경우만 호출 (예: 깨진 아이콘 숨김).
     *
     * 사용법:
     *   const img = document.createElement('img');
     *   img.src = api.thumbnailUrlByName(name, path, 200);
     *   api.attachMediaImageRetry(img,
     *       () => api.thumbnailUrlByName(name, path, 200),
     *       () => { img.style.display = 'none'; });
     */
    attachMediaImageRetry(img_el, fn_build_url, fn_on_final_error) {
        if (!img_el || typeof fn_build_url !== 'function') return;
        let bool_retried = false;
        const on_final = () => {
            if (typeof fn_on_final_error === 'function') {
                try { fn_on_final_error(); } catch (_) {}
            }
        };
        img_el.addEventListener('error', async () => {
            if (bool_retried) {                // 1회만 재시도 — 무한 루프 방지
                on_final();
                return;
            }
            bool_retried = true;
            try {
                await _ensureMediaTicket();    // 새 티켓 강제 발급 / 갱신
                const str_new_url = fn_build_url();
                if (str_new_url && str_new_url !== img_el.src) {
                    img_el.src = str_new_url;
                } else {
                    on_final();
                }
            } catch (_) {
                on_final();
            }
        });
    },

    // ── 타일 ──

    /** 타일 이미지 URL (프리제네레이트된 정적 타일).
     *  ndpMatch=true → /ndp/ 서브경로로 NDP 색 매칭 변형본을 받는다.
     *  서버는 ndpmatch 캐시가 없으면 raw 타일에 apply_ndp_fit 을 적용해 생성+저장 후 반환. */
    tileUrl(slideId, level, tileX, tileY, ndpMatch = false) {
        const str_variant = ndpMatch ? `${slideId}/ndp/${level}` : `${slideId}/${level}`;
        return `${API_BASE}/tiles/${str_variant}/${tileX}/${tileY}.jpeg?mt=${encodeURIComponent(_getMediaTicketSync())}`;
    },

    /** stage level 조회 */
    async getStageLevel(slideId, effectiveMpp) {
        const res = await _authFetch(`${API_BASE}/tiles/${slideId}/stage-level?effective_mpp=${effectiveMpp}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    // ── 타일 생성 진행 상태 ──

    /** 타일 프리제네레이션 진행 상태 */
    async getTileProgress(slideId) {
        const res = await _authFetch(`${API_BASE}/slides/tile-progress/${slideId}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    // ── Annotation ──

    /** annotation 저장 */
    async saveAnnotations(slideId, annotations) {
        const form = new FormData();
        form.append('data', JSON.stringify(annotations));
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/annotations/save`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** annotation 불러오기 */
    async loadAnnotations(slideId) {
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/annotations/load`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    // ── AI ──

    /** 검출 시작 */
    async startDetection(slideId, roiPolygons = null, tissueType = 'Stomach') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('tissue_type', tissueType);
        const res = await _authFetch(`${API_BASE}/ai/detect`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** Quanti PD-L1 시작 (Stomach → CPS, Lung → TPS) */
    async startPdScore(slideId, roiPolygons = null, tissueType = 'Stomach') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('tissue_type', tissueType);
        const res = await _authFetch(`${API_BASE}/ai/pd-score`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** Quanti IHC 시작 (현재 HER2 만 지원) */
    async startPreciseIhc(slideId, roiPolygons = null, marker = 'HER2') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('marker', marker);
        const res = await _authFetch(`${API_BASE}/ai/precise-ihc`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 검출 결과 — 현재 사용자 전용 편집본으로 DB 저장 (원본 캐시는 유지) */
    async saveDetectionResult(slideId, tissueType, result, aiMode = 'Quanti HE') {
        const form = new FormData();
        form.append('slide_id', slideId);
        form.append('tissue_type', tissueType);
        form.append('result', JSON.stringify(result));
        form.append('ai_mode', aiMode);
        const res = await _authFetch(`${API_BASE}/ai/save-result`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 사용자별 편집본 목록 — 현재 슬라이드+모드+variant 에 저장본을 가진 사용자들 */
    async listUserAiEdits(slideId, aiMode, variant = '') {
        const qs = new URLSearchParams({ slide_id: slideId, ai_mode: aiMode, variant: variant || '' });
        const res = await _authFetch(`${API_BASE}/ai/user-edits/list?${qs.toString()}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 본인 편집본 삭제 (타 사용자 것은 백엔드에서 거부) */
    async deleteMyUserAiEdit(slideId, aiMode, variant = '') {
        const qs = new URLSearchParams({ slide_id: slideId, ai_mode: aiMode, variant: variant || '' });
        const res = await _authFetch(`${API_BASE}/ai/user-edits?${qs.toString()}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 특정 사용자의 편집본 전체 결과 로드 */
    async loadUserAiEdit(slideId, aiMode, userId, variant = '') {
        const qs = new URLSearchParams({
            slide_id: slideId, ai_mode: aiMode, user_id: userId, variant: variant || ''
        });
        const res = await _authFetch(`${API_BASE}/ai/user-edits/load?${qs.toString()}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 현재 큐/실행중인 AI 작업 (슬라이드 파일명 기준) */
    async getActiveAiTasks() {
        const res = await _authFetch(`${API_BASE}/ai/active-tasks`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 작업 상태 조회 */
    async getTaskStatus(taskId) {
        const res = await _authFetch(`${API_BASE}/ai/task/${taskId}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 실행 중인 AI task 를 취소 요청. 워커는 다음 체크포인트에서 중단하고 부분 캐시를 정리. */
    async cancelTask(taskId) {
        const res = await _authFetch(`${API_BASE}/ai/task/${taskId}/cancel`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** Virtual Stain (VS IHC) 시작 */
    async startVirtualStain(slideId, stainType = 'ihc_membrane', roiPolygons = null, targetMpp = 2.0) {
        const form = new FormData();
        form.append('slide_id', slideId);
        form.append('stain_type', stainType);
        form.append('target_mpp', String(targetMpp));
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        const res = await _authFetch(`${API_BASE}/ai/virtual-stain`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** Virtual Stain 결과 PNG URL (리포트/PDF용 풀해상도 composite) */
    virtualStainImageUrl(slideId, stainType = 'ihc_membrane', targetMpp = 2.0) {
        return `${API_BASE}/ai/virtual-stain/${slideId}/${stainType}.png?target_mpp=${targetMpp}&t=${Date.now()}`;
    },

    /** Virtual Stain 피라미드 타일 URL (뷰어 렌더용) */
    virtualStainTileUrl(slideId, stainType, targetMpp, level, tx, ty) {
        return `${API_BASE}/ai/virtual-stain/${slideId}/${stainType}/tile/${level}/${tx}_${ty}.jpeg?target_mpp=${targetMpp}&mt=${encodeURIComponent(_getMediaTicketSync())}`;
    },

    // ── 인증 ──

    /** 로그아웃 (서버 세션 폐기 + 로컬 토큰 삭제) */
    async logout() {
        try {
            await _authFetch(`${API_BASE}/auth/logout`, { method: 'POST' });
        } catch (_) {
            // 서버 에러 시에도 로컬 토큰은 삭제
        }
        if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
        _clearMediaTicket();
        _clearTokens();
        window.location.href = '/login.html';
    },

    /** 현재 로그인 사용자 정보 조회 */
    async me() {
        const res = await _authFetch(`${API_BASE}/auth/me`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },
};
