/**
 * API client for the FastAPI backend.
 * Adds JWT auth, refresh handling, and short-lived media tickets for images.
 */

const API_BASE = '/api';

// Auth token helpers.
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
    // Refresh two minutes before expiry.
    return Date.now() > expires - 120000;
}

// Serialize concurrent refresh attempts so refresh-token rotation does not race.
let _refreshInFlight = null;

// bool_force skips the near-expiry check.
// bool_silent returns false instead of redirecting on refresh failure.
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
            // Failed refresh clears the session unless the caller requested a silent retry path.
            if (!bool_silent) {
                _clearTokens();
                _clearMediaTicket();
                if (typeof window !== 'undefined' && !window.location.pathname.endsWith('login')) {
                    window.location.href = '/login';
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

// Image URLs bypass _authFetch, so keep auth/media tickets warm in the background.
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

// Media tickets are opaque, short-lived tokens for tile/thumbnail <img src> URLs.
let _mediaTicket = null;          // {str_token, int_exp, int_ttl}
let _mediaTicketInFlight = null;

function _isMediaTicketValid() {
    if (!_mediaTicket || !_mediaTicket.str_token) return false;
    const int_now = Math.floor(Date.now() / 1000);
    // Refresh two minutes before expiry.
    return _mediaTicket.int_exp - int_now > 120;
}

async function _ensureMediaTicket() {
    if (_isMediaTicketValid()) return _mediaTicket.str_token;
    if (_mediaTicketInFlight) return _mediaTicketInFlight;
    if (!_getAccessToken()) return '';

    _mediaTicketInFlight = (async () => {
        try {
            // Do not use _authFetch here because _authFetch itself prepares media tickets.
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
    // Trigger a background refresh if the ticket is close to expiring.
    const int_now = Math.floor(Date.now() / 1000);
    if (_mediaTicket.int_exp - int_now <= 120) {
        _ensureMediaTicket();  // fire-and-forget (async)
    }
    // Do not return an already expired ticket.
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
    // Pre-fetch a media ticket so subsequent image URLs can be created immediately.
    await _ensureMediaTicket();

    const headers_initial = { ...(options.headers || {}), ..._authHeaders() };
    let res = await fetch(url, { ...options, headers: headers_initial });

    // Retry one time after a forced refresh before sending the user back to login.
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
            if (typeof window !== 'undefined' && !window.location.pathname.endsWith('login')) {
                window.location.href = '/login';
            }
            throw new Error('Authentication required');
        }
    }

    return res;
}

async function _jsonOrThrow(res, label = 'API') {
    const text = await res.text();
    if (!res.ok) {
        throw new Error(text || `${label} failed with HTTP ${res.status}`);
    }
    if (!text.trim()) {
        throw new Error(`${label} returned an empty response`);
    }
    try {
        return JSON.parse(text);
    } catch (err) {
        const preview = text.slice(0, 160).replace(/\s+/g, ' ').trim();
        throw new Error(`${label} returned invalid JSON${preview ? `: ${preview}` : ''}`);
    }
}

function _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function _isNdpiFilename(value) {
    return /\.ndpi(?:$|[?#])/i.test(String(value || '').trim());
}

function _slideMetaLooksNdpi(meta) {
    if (!meta) return false;
    if (typeof meta === 'string') return _isNdpiFilename(meta);
    const candidates = [
        meta.filename,
        meta.name,
        meta.file_name,
        meta.file_path,
        meta.path,
        meta.original_filename,
        meta.slide_filename,
    ];
    if (Array.isArray(meta.files)) candidates.push(...meta.files);
    return candidates.some(_isNdpiFilename);
}

function _isTransientJsonResponseError(err) {
    const msg = String(err?.message || '');
    return msg.includes('returned an empty response') || msg.includes('returned invalid JSON');
}

async function _fetchJsonWithRetry(fn_fetch, label = 'API', tries = 3) {
    let lastErr = null;
    for (let i = 0; i < tries; i++) {
        try {
            const res = await fn_fetch();
            return await _jsonOrThrow(res, label);
        } catch (err) {
            lastErr = err;
            if (!_isTransientJsonResponseError(err) || i === tries - 1) break;
            await _sleep(250 * (i + 1));
        }
    }
    throw lastErr;
}

async function _jsonOrThrowWithProgress(res, label = 'API', onProgress = null) {
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `${label} failed with HTTP ${res.status}`);
    }

    const total = Number(res.headers.get('content-length') || 0);
    if (!res.body || typeof res.body.getReader !== 'function') {
        return _jsonOrThrow(res, label);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    const chunks = [];
    let loaded = 0;

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        loaded += value.byteLength;
        chunks.push(value);
        if (typeof onProgress === 'function') {
            onProgress({
                loaded,
                total,
                percent: total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : null,
            });
        }
    }
    if (typeof onProgress === 'function') {
        onProgress({ loaded, total, percent: total > 0 ? 100 : null });
    }

    const bytes = new Uint8Array(loaded);
    let offset = 0;
    for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
    }
    const text = decoder.decode(bytes);

    if (!text.trim()) {
        throw new Error(`${label} returned an empty response`);
    }
    try {
        return JSON.parse(text);
    } catch (err) {
        const preview = text.slice(0, 160).replace(/\s+/g, ' ').trim();
        throw new Error(`${label} returned invalid JSON${preview ? `: ${preview}` : ''}`);
    }
}

async function _fetchJsonWithProgressRetry(fn_fetch, label = 'API', onProgress = null, tries = 3) {
    let lastErr = null;
    for (let i = 0; i < tries; i++) {
        try {
            const res = await fn_fetch();
            return await _jsonOrThrowWithProgress(res, label, onProgress);
        } catch (err) {
            lastErr = err;
            if (!_isTransientJsonResponseError(err) || i === tries - 1) break;
            await _sleep(250 * (i + 1));
        }
    }
    throw lastErr;
}

function _normalizeCellArray(cell) {
    if (!Array.isArray(cell)) return cell;
    const normalized = {
        x: cell[0],
        y: cell[1],
        class_id: cell[2],
        confidence: cell[3],
    };
    const hasBbox = cell.length >= 8 && [4, 5, 6, 7].every(idx => typeof cell[idx] === 'number');
    if (hasBbox) {
        normalized.x0 = cell[4];
        normalized.y0 = cell[5];
        normalized.x1 = cell[6];
        normalized.y1 = cell[7];
        normalized.width = Math.max(0, Number(cell[6]) - Number(cell[4]));
        normalized.height = Math.max(0, Number(cell[7]) - Number(cell[5]));
        if (cell[8]) normalized.hidden = true;
        if (cell[9]) normalized.exclude_from_score = true;
    } else {
        if (cell[4]) normalized.hidden = true;
        if (cell[5]) normalized.exclude_from_score = true;
    }
    return normalized;
}

function _normalizeAiResultPayload(result) {
    if (!result || typeof result !== 'object') return result;
    for (const key of ['cells', 'excluded_cells']) {
        if (Array.isArray(result[key])) {
            result[key] = result[key].map(_normalizeCellArray);
        }
    }
    return result;
}

export const api = {

    /**   (  +  ) */
    async browse(path = '') {
        const res = await _authFetch(`${API_BASE}/slides/browse?path=${encodeURIComponent(path)}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async listCases({ project = '', hospital = '', sampleNo = '', page = 1, pageSize = 15, sortBy = 'case_name', sortDir = 'asc' } = {}) {
        const q = new URLSearchParams({
            project: project || '',
            hospital: hospital || '',
            sample_no: sampleNo || '',
            page: String(page || 1),
            page_size: String(pageSize || 15),
            sort_by: sortBy || 'case_name',
            sort_dir: sortDir || 'asc',
        });
        const res = await _authFetch(`${API_BASE}/slides/cases?${q}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**        */
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
        form.append('project_ai_enabled', String(Boolean(info.project_ai_enabled)));
        form.append('project_ai_tasks_json', info.project_ai_tasks_json || JSON.stringify(info.project_ai_tasks || []));
        form.append('annotation_ai_enabled', String(Boolean(info.annotation_ai_enabled)));
        form.append('annotation_ai_key', info.annotation_ai_key || info.annotation_ai?.key || '');
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
        form.append('project_ai_enabled', String(Boolean(info.project_ai_enabled)));
        form.append('project_ai_tasks_json', info.project_ai_tasks_json || JSON.stringify(info.project_ai_tasks || []));
        form.append('annotation_ai_enabled', String(Boolean(info.annotation_ai_enabled)));
        form.append('annotation_ai_key', info.annotation_ai_key || info.annotation_ai?.key || '');
        const res = await _authFetch(`${API_BASE}/slides/project/update`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async downloadTerminationCompletedCellPatches(projectPath) {
        const res = await _authFetch(
            `${API_BASE}/cell-annotation/projects/${encodeURIComponent(projectPath)}/termination-export`
        );
        if (!res.ok) throw new Error(await res.text());
        const blob = await res.blob();
        const disposition = res.headers.get('content-disposition') || '';
        const match = disposition.match(/filename="?([^";]+)"?/i);
        const filename = match?.[1] || `${projectPath}_termination_completed_cell_patches.zip`;
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        return { filename };
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

    async openSlide(filename, path = '', openPage = '', options = {}) {
        const form = new FormData();
        form.append('filename', filename);
        form.append('path', path);
        const page = openPage || (
            location.pathname.includes('cell-annotation') ? 'cell-annotation'
            : location.pathname.includes('annotation') ? 'tissue-annotation'
            : 'ai'
        );
        form.append('open_page', page);
        const res = await _authFetch(`${API_BASE}/slides/open`, { method: 'POST', body: form, signal: options.signal });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**   */
    async createFolder(path, name) {
        const form = new FormData();
        form.append('path', path);
        form.append('name', name);
        const res = await _authFetch(`${API_BASE}/slides/folder/create`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**    */
    async renameFolder(path, newName) {
        const form = new FormData();
        form.append('path', path);
        form.append('new_name', newName);
        const res = await _authFetch(`${API_BASE}/slides/folder/rename`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**   */
    async deleteFolder(path) {
        const form = new FormData();
        form.append('path', path);
        const res = await _authFetch(`${API_BASE}/slides/folder/delete`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**  AI     */
    async getFolderAiConfig(path) {
        const q = new URLSearchParams({ path: path || '' });
        const res = await _authFetch(`${API_BASE}/slides/folder-config?${q}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**  AI     */
    async saveFolderAiConfig(path, enabled, tasks) {
        const form = new FormData();
        form.append('path', path || '');
        form.append('enabled', enabled ? 'true' : 'false');
        form.append('tasks_json', JSON.stringify(tasks || []));
        const res = await _authFetch(`${API_BASE}/slides/folder-config`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**  AI     */
    async deleteFolderAiConfig(path) {
        const q = new URLSearchParams({ path: path || '' });
        const res = await _authFetch(`${API_BASE}/slides/folder-config?${q}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**  + AI /    */
    async deleteFiles(filenames, path = '') {
        const form = new FormData();
        form.append('filenames_json', JSON.stringify(filenames || []));
        form.append('path', path || '');
        const res = await _authFetch(`${API_BASE}/slides/file/delete`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**     ("", pending, in_progress, done, flagged) */
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

    /**   */
    async moveFile(filename, srcPath, dstPath) {
        const form = new FormData();
        form.append('filename', filename);
        form.append('src_path', srcPath);
        form.append('dst_path', dstPath);
        const res = await _authFetch(`${API_BASE}/slides/file/move`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**    */
    async uploadStart(filename) {
        const form = new FormData();
        form.append('filename', filename);
        const res = await _authFetch(`${API_BASE}/slides/upload/start`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**   */
    async uploadChunk(uploadId, chunkIndex, blob) {
        const form = new FormData();
        form.append('upload_id', uploadId);
        form.append('chunk_index', chunkIndex.toString());
        form.append('chunk', blob);
        const res = await _authFetch(`${API_BASE}/slides/upload/chunk`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**    */
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

    /**   */
    async getSlideInfo(slideId) {
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/info`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**  URL (slide_id     ).
      *
    /** Slide-level clinical score metadata shared by AI and annotation viewers. */
    async getSlideClinicalInfo(slideId) {
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/clinical-info`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async updateSlideClinicalInfo(slideId, clinicalInfo) {
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/clinical-info`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dict_clinical_info: clinicalInfo || {} }),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async updateCaseClinicalInfo(caseName, clinicalInfo) {
        const res = await _authFetch(`${API_BASE}/slides/cases/${encodeURIComponent(caseName)}/clinical-info`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dict_clinical_info: clinicalInfo || {} }),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    isNdpiFilename(value) {
        return _isNdpiFilename(value);
    },

    shouldUseNdpMatch(meta) {
        return _slideMetaLooksNdpi(meta);
    },

    thumbnailUrl(slideId, size = 300, ndpMatch = false, slideMeta = null) {
        const str_ticket = _getMediaTicketSync();
        if (!str_ticket) return '';
        const int_size = Math.max(64, Math.min(8192, Number(size) || 300));
        const str_ndp = (ndpMatch || _slideMetaLooksNdpi(slideMeta)) ? '&ndp=true' : '';
        return `${API_BASE}/slides/${slideId}/thumbnail?size=${int_size}${str_ndp}&mt=${encodeURIComponent(str_ticket)}`;
    },

    /**   URL (PDF ).  ndpMatch . */
    previewUrl(slideId, size = 2048, ndpMatch = false, slideMeta = null) {
        const str_ticket = _getMediaTicketSync();
        if (!str_ticket) return '';
        const str_ndp = (ndpMatch || _slideMetaLooksNdpi(slideMeta)) ? '&ndp=true' : '';
        return `${API_BASE}/slides/${slideId}/preview?size=${size}${str_ndp}&mt=${encodeURIComponent(str_ticket)}`;
    },

    /**  URL (   , slide_manager ) */
    thumbnailUrlByName(filename, path = '', size = 300, ndpMatch = null) {
        const str_ticket = _getMediaTicketSync();
        if (!str_ticket) return '';
        const int_size = Math.max(64, Math.min(8192, Number(size) || 300));
        const bool_ndp = ndpMatch === true || (ndpMatch !== false && (_isNdpiFilename(filename) || _isNdpiFilename(path)));
        const str_ndp = bool_ndp ? '&ndp=true' : '';
        return `${API_BASE}/slides/thumbnail-by-name?filename=${encodeURIComponent(filename)}&path=${encodeURIComponent(path)}&size=${int_size}${str_ndp}&mt=${encodeURIComponent(str_ticket)}`;
    },

    /** Scanner specimen-label image URL. Returns no content when no label is stored. */
    labelUrlByName(filename, path = '', size = 300) {
        const str_ticket = _getMediaTicketSync();
        if (!str_ticket) return '';
        const int_size = Math.max(64, Math.min(1024, Number(size) || 300));
        return `${API_BASE}/slides/label-by-name?filename=${encodeURIComponent(filename)}&path=${encodeURIComponent(path)}&size=${int_size}&mt=${encodeURIComponent(str_ticket)}`;
    },

    /**     .     . */
    async ensureMediaReady() {
        await _ensureMediaTicket();
    },

    /**
      *
     *
      *
      *
      *
     *
      *
     *
      *
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
            if (bool_retried) {
                on_final();
                return;
            }
            bool_retried = true;
            try {
                await _ensureMediaTicket();
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


    /** Build a tile image URL. */
    tileUrl(slideId, level, tileX, tileY, ndpMatch = false) {
        const str_variant = ndpMatch ? `${slideId}/ndp/${level}` : `${slideId}/${level}`;
        return `${API_BASE}/tiles/${str_variant}/${tileX}/${tileY}.jpeg?mt=${encodeURIComponent(_getMediaTicketSync())}`;
    },

    /** stage level  */
    async getStageLevel(slideId, effectiveMpp) {
        const res = await _authFetch(`${API_BASE}/tiles/${slideId}/stage-level?effective_mpp=${effectiveMpp}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },


    /**     */
    async getTileProgress(slideId) {
        const res = await _authFetch(`${API_BASE}/slides/tile-progress/${slideId}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },


    /** annotation  */
    async saveAnnotations(slideId, annotations) {
        const form = new FormData();
        form.append('data', JSON.stringify(annotations));
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/annotations/save`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** annotation  */
    async loadAnnotations(slideId) {
        const res = await _authFetch(`${API_BASE}/slides/${slideId}/annotations/load`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getCellGridConfig(slideId, options = {}) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/grid-config`, { signal: options.signal });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getCellRequiredRegions(slideId, options = {}) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/required-regions`, { signal: options.signal });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async saveCellRequiredRegions(slideId, regions) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/required-regions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ regions: regions || [] }),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async recomputeCellPatchStatus(slideId) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/patches/recompute-status`, {
            method: 'POST',
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getCellPatches(slideId, status = '', options = {}) {
        const q = status ? `?status=${encodeURIComponent(status)}` : '';
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/patches${q}`, { signal: options.signal });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async clearCellPatches(slideId) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/patches`, {
            method: 'DELETE',
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getPatchCells(slideId, patchId) {
        const cacheBust = Date.now();
        const res = await _authFetch(
            `${API_BASE}/cell-annotation/${slideId}/patches/${encodeURIComponent(patchId)}/cells?_=${cacheBust}`,
            { cache: 'no-store' },
        );
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getPatchAssistanceCells(slideId, patchId, options = {}) {
        const cacheBust = Date.now();
        const res = await _authFetch(
            `${API_BASE}/cell-annotation/${slideId}/patches/${encodeURIComponent(patchId)}/assistance-cells?_=${cacheBust}`,
            { cache: 'no-store', signal: options.signal },
        );
        if (!res.ok) throw new Error(await res.text());
        // Large patch result JSON can take noticeable time to arrive. Read the
        // response stream so Patch View can report actual download progress.
        if (typeof options.onProgress !== 'function' || !res.body?.getReader) return res.json();
        const total = Number(res.headers.get('content-length')) || 0;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let loaded = 0;
        let text = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            loaded += value?.byteLength || 0;
            text += decoder.decode(value, { stream: true });
            const percent = total ? Math.min(100, loaded / total * 100) : 0;
            try { options.onProgress({ loaded, total, percent }); } catch (_) { /* UI progress must not break API parsing. */ }
        }
        text += decoder.decode();
        try { options.onProgress({ loaded, total, percent: 100 }); } catch (_) { /* noop */ }
        return JSON.parse(text);
    },

    async savePatchCells(slideId, patchId, cells, options = {}) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/patches/${encodeURIComponent(patchId)}/cells`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cells: cells || [], ...(options || {}) }),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async updatePatchStatus(slideId, patchId, status, options = {}) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/patches/${encodeURIComponent(patchId)}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status, ...(options || {}) }),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },


    /**   */
    async loadAnnotationClasses(path) {
        const res = await _authFetch(`${API_BASE}/slides/annotation-classes?path=${encodeURIComponent(path || '')}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async saveAnnotationClasses(path, classes) {
        const form = new FormData();
        form.append('path', path || '');
        form.append('data', JSON.stringify({ classes }));
        const res = await _authFetch(`${API_BASE}/slides/annotation-classes`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async loadCellAnnotationClasses(path) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/classes?path=${encodeURIComponent(path || '')}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async saveCellAnnotationClasses(path, classes) {
        const form = new FormData();
        form.append('path', path || '');
        form.append('data', JSON.stringify({ classes }));
        const res = await _authFetch(`${API_BASE}/cell-annotation/classes`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async saveUserPreferences(preferences = {}) {
        const res = await _authFetch(`${API_BASE}/users/me/preferences`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dict_preferences: preferences }),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async startDetection(slideId, roiPolygons = null, tissueType = 'Stomach') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('tissue_type', tissueType);
        const res = await _authFetch(`${API_BASE}/ai/detect`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** Quanti PD-L1  (Stomach  CPS, Lung  TPS) */
    async startPdScore(slideId, roiPolygons = null, tissueType = 'Stomach') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('tissue_type', tissueType);
        const res = await _authFetch(`${API_BASE}/ai/pd-score`, { method: 'POST', body: form });
        return _jsonOrThrow(res, 'Quanti PD-L1 start');
    },

    /** Quanti IHC  ( HER2  ) */
    async startPreciseIhc(slideId, roiPolygons = null, marker = 'HER2') {
        const form = new FormData();
        form.append('slide_id', slideId);
        if (roiPolygons) form.append('roi_polygons', JSON.stringify(roiPolygons));
        form.append('marker', marker);
        const res = await _authFetch(`${API_BASE}/ai/precise-ihc`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**        DB  (  ) */
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

    /**      ++variant     */
    async listUserAiEdits(slideId, aiMode, variant = '') {
        const qs = new URLSearchParams({ slide_id: slideId, ai_mode: aiMode, variant: variant || '' });
        const res = await _authFetch(`${API_BASE}/ai/user-edits/list?${qs.toString()}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**    (    ) */
    async deleteMyUserAiEdit(slideId, aiMode, variant = '') {
        const qs = new URLSearchParams({ slide_id: slideId, ai_mode: aiMode, variant: variant || '' });
        const res = await _authFetch(`${API_BASE}/ai/user-edits?${qs.toString()}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**       */
    async loadUserAiEdit(slideId, aiMode, userId, variant = '') {
        const qs = new URLSearchParams({
            slide_id: slideId, ai_mode: aiMode, user_id: userId, variant: variant || ''
        });
        const res = await _authFetch(`${API_BASE}/ai/user-edits/load?${qs.toString()}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**  / AI  (  ) */
    async getActiveAiTasks() {
        const res = await _authFetch(`${API_BASE}/ai/active-tasks`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /**    */
    async getTaskStatus(taskId) {
        return _fetchJsonWithRetry(
            () => _authFetch(`${API_BASE}/ai/task/${taskId}`),
            'AI task status',
            4
        );
    },

    async getTaskResult(taskId, onProgress = null) {
        const result = await _fetchJsonWithProgressRetry(
            () => _authFetch(`${API_BASE}/ai/task/${taskId}/result`),
            'AI task result',
            onProgress,
            3
        );
        return _normalizeAiResultPayload(result);
    },

    /**   AI task   .       . */
    async cancelTask(taskId) {
        const res = await _authFetch(`${API_BASE}/ai/task/${taskId}/cancel`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    /** Virtual Stain (VS IHC)  */
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

    /** Virtual Stain  PNG URL (/PDF  composite) */
    virtualStainImageUrl(slideId, stainType = 'ihc_membrane', targetMpp = 2.0) {
        return `${API_BASE}/ai/virtual-stain/${slideId}/${stainType}.png?target_mpp=${targetMpp}&t=${Date.now()}`;
    },

    /** Virtual Stain   URL ( ) */
    virtualStainTileUrl(slideId, stainType, targetMpp, level, tx, ty) {
        return `${API_BASE}/ai/virtual-stain/${slideId}/${stainType}/tile/${level}/${tx}_${ty}.jpeg?target_mpp=${targetMpp}&mt=${encodeURIComponent(_getMediaTicketSync())}`;
    },

    async getVirtualStainTileManifest(slideId, stainType, targetMpp = 2.0) {
        const url = `${API_BASE}/ai/virtual-stain/${slideId}/${stainType}/tile-manifest?target_mpp=${encodeURIComponent(targetMpp)}`;
        const res = await _authFetch(url);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getWsiLabelingAssistance(slideId, options = {}) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/wsi-labeling-assistance`, { signal: options.signal });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getWsiLabelingAssistanceOptions(slideId, options = {}) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/wsi-labeling-assistance/options`, { signal: options.signal });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async startWsiLabelingAssistance(slideId, annotationAiKey = '') {
        const body = JSON.stringify(annotationAiKey ? { annotation_ai_key: annotationAiKey } : {});
        const res = await _authFetch(`${API_BASE}/cell-annotation/${slideId}/wsi-labeling-assistance/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },

    async getWsiLabelingAssistanceTask(taskId) {
        const res = await _authFetch(`${API_BASE}/cell-annotation/wsi-labeling-assistance/task/${taskId}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },


    /**  (   +   ) */
    async logout() {
        try {
            await _authFetch(`${API_BASE}/auth/logout`, { method: 'POST' });
        } catch (_) {
        }
        if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
        _clearMediaTicket();
        _clearTokens();
        window.location.href = '/login';
    },

    /**      */
    async me() {
        const res = await _authFetch(`${API_BASE}/auth/me`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },
};
