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

async function _refreshTokenIfNeeded() {
    if (!_isTokenExpiringSoon()) return;
    const refreshToken = _getRefreshToken();
    if (!refreshToken) return;

    try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ str_refresh_token: refreshToken }),
        });
        if (res.ok) {
            const data = await res.json();
            _setTokens(data.str_access_token, data.str_refresh_token, data.int_expires_in);
            if (data.dict_user) {
                localStorage.setItem('user', JSON.stringify(data.dict_user));
            }
        } else {
            // Refresh 실패 → 로그인 페이지로
            _clearTokens();
            window.location.href = '/login.html';
        }
    } catch (e) {
        console.error('Token refresh failed:', e);
    }
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
        }
    }, 30000);
}
if (typeof window !== 'undefined') {
    _startBackgroundTokenRefresh();
}

function _authHeaders() {
    return { 'Authorization': `Bearer ${_getAccessToken()}` };
}

async function _authFetch(url, options = {}) {
    await _refreshTokenIfNeeded();

    const headers = { ...(options.headers || {}), ..._authHeaders() };
    const res = await fetch(url, { ...options, headers });

    if (res.status === 401) {
        _clearTokens();
        window.location.href = '/login.html';
        throw new Error('Authentication required');
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
    async setFileStatus(filenames, status, path = '') {
        const form = new FormData();
        form.append('filenames_json', JSON.stringify(filenames || []));
        form.append('status', status || '');
        form.append('path', path || '');
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

    /** 썸네일 URL (slide_id 기반 — 슬라이드 열린 후) */
    thumbnailUrl(slideId, size = 300) {
        return `${API_BASE}/slides/${slideId}/thumbnail?size=${size}&token=${encodeURIComponent(_getAccessToken())}`;
    },

    /** 고해상도 프리뷰 URL (PDF 리포트용) */
    previewUrl(slideId, size = 2048) {
        return `${API_BASE}/slides/${slideId}/preview?size=${size}&token=${encodeURIComponent(_getAccessToken())}`;
    },

    /** 썸네일 URL (파일명 기반 — 리스트용, slide_manager 불필요) */
    thumbnailUrlByName(filename, path = '', size = 300) {
        return `${API_BASE}/slides/thumbnail-by-name?filename=${encodeURIComponent(filename)}&path=${encodeURIComponent(path)}&size=${size}&token=${encodeURIComponent(_getAccessToken())}`;
    },

    // ── 타일 ──

    /** 타일 이미지 URL (프리제네레이트된 정적 타일) */
    tileUrl(slideId, level, tileX, tileY) {
        return `${API_BASE}/tiles/${slideId}/${level}/${tileX}/${tileY}.jpeg?token=${encodeURIComponent(_getAccessToken())}`;
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

    /** PD-Score 시작 (Stomach → CPS, Lung → TPS) */
    async startPdScore(slideId, roiPolygons = null, tissueType = 'Stomach') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('tissue_type', tissueType);
        const res = await _authFetch(`${API_BASE}/ai/pd-score`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** Precise-IHC 시작 (현재 HER2 만 지원) */
    async startPreciseIhc(slideId, roiPolygons = null, marker = 'HER2') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('marker', marker);
        const res = await _authFetch(`${API_BASE}/ai/precise-ihc`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** 검출 결과 내부 저장 */
    async saveDetectionResult(slideId, tissueType, result) {
        const form = new FormData();
        form.append('slide_id', slideId);
        form.append('tissue_type', tissueType);
        form.append('result', JSON.stringify(result));
        const res = await _authFetch(`${API_BASE}/ai/save-result`, { method: 'POST', body: form });
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

    /** Virtual Stain (VS-IHC) 시작 */
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
        return `${API_BASE}/ai/virtual-stain/${slideId}/${stainType}/tile/${level}/${tx}_${ty}.jpeg?target_mpp=${targetMpp}&token=${encodeURIComponent(_getAccessToken())}`;
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
