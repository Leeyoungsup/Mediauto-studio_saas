// MeDIAuto Studio — text text text
// text text text (text X). localStorage access_token text.

const API_BASE = '/api';
const PAGE_LIMIT = 20;

// ─── text/text ───
const accessToken = localStorage.getItem('access_token');
const userRaw = localStorage.getItem('user');

if (!accessToken || !userRaw) {
    location.href = '/login';
}

let currentUser = null;
try { currentUser = JSON.parse(userRaw); } catch { currentUser = null; }
window.MediautoHeader?.render({
    active: 'admin',
    user: currentUser,
    showAdmin: true,
});

if (!currentUser || currentUser.str_role !== 'admin') {
    alert('Administrator permission is required.');
    location.href = '/ai';
}

document.getElementById('current-user-name').textContent = currentUser.str_name || currentUser.str_login_id;
document.getElementById('current-user-role').textContent = currentUser.str_role;

// ─── fetch text ───
async function authFetch(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    headers['Authorization'] = `Bearer ${accessToken}`;
    headers['X-Requested-With'] = 'XMLHttpRequest';
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401) {
        alert('Your session has expired. Please sign in again.');
        localStorage.clear();
        location.href = '/login';
        return null;
    }
    if (res.status === 403) {
        const d = await res.json().catch(() => ({}));
        alert(d.detail || 'Permission denied.');
        location.href = '/ai';
        return null;
    }
    return res;
}

async function apiGet(path) {
    const res = await authFetch(path);
    if (!res) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
    return data;
}

async function apiJson(path, method, body) {
    const res = await authFetch(path, { method, body: JSON.stringify(body || {}) });
    if (!res) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
    return data;
}

async function apiDelete(path) {
    const res = await authFetch(path, { method: 'DELETE' });
    if (!res) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
    return data;
}

// ─── text ───
const $alert = document.getElementById('admin-alert');
function showAlert(msg, type = 'success') {
    if (typeof msg === 'object') msg = JSON.stringify(msg);
    $alert.textContent = msg;
    $alert.className = `admin-alert ${type}`;
    $alert.hidden = false;
    setTimeout(() => { $alert.hidden = true; }, 4000);
}

// ─── text ───
document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.admin-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab).classList.add('active');

        if (tab.dataset.tab === 'pending-panel') loadPending();
        else if (tab.dataset.tab === 'users-panel') loadUsers();
        else if (tab.dataset.tab === 'activity-panel') loadActivity();
    });
});

// ─── text ───
document.getElementById('btn-logout').addEventListener('click', async () => {
    try { await authFetch('/auth/logout', { method: 'POST' }); } catch {}
    localStorage.clear();
    location.href = '/login';
});

// ─── text ───
function fmtDate(iso) {
    if (!iso) return '—';
    // text naive datetime (timezone suffix text) text text text text —
    // DB text UTC text text suffix text Z(UTC)No search results found.
    let str_iso = String(iso);
    if (typeof iso === 'string' && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(str_iso)) {
        str_iso += 'Z';
    }
    const d = new Date(str_iso);
    if (isNaN(d)) return '—';
    return d.toLocaleString('ko-KR', { hour12: false, timeZone: 'Asia/Seoul' });
}
function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// ═══════════════════════════════════════
// text text
// ═══════════════════════════════════════
async function loadPending() {
    const $tbody = document.getElementById('pending-tbody');
    $tbody.innerHTML = '<tr><td colspan="6" class="empty-row">Loading...</td></tr>';
    try {
        const data = await apiGet('/users/pending');
        if (!data) return;
        const list = data.list_pending || [];
        updatePendingBadge(list.length);
        if (list.length === 0) {
            $tbody.innerHTML = '<tr><td colspan="6" class="empty-row">No users are waiting for approval.</td></tr>';
            return;
        }
        $tbody.innerHTML = '';
        for (const u of list) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${esc(u.str_login_id)}</strong></td>
                <td>${esc(u.str_name)}</td>
                <td>${esc(u.str_department || '—')}</td>
                <td>${fmtDate(u.dt_created_at)}</td>
                <td>
                    <select class="role-select" data-role-for="${u._id}">
                        <option value="viewer" selected>Viewer</option>
                        <option value="doctor">Doctor</option>
                        <option value="admin">Admin</option>
                    </select>
                </td>
                <td class="row-actions">
                    <button class="admin-btn-approve" data-approve="${u._id}">Previous</button>
                    <button class="admin-btn-reject" data-reject="${u._id}">Previous</button>
                </td>
            `;
            $tbody.appendChild(tr);
        }
    } catch (err) {
        showAlert(err.message, 'error');
        $tbody.innerHTML = '<tr><td colspan="6" class="empty-row">Load failed</td></tr>';
    }
}

document.getElementById('pending-tbody').addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    if (btn.dataset.approve) {
        const userId = btn.dataset.approve;
        const role = document.querySelector(`[data-role-for="${userId}"]`).value;
        if (!confirm(`Approve this user as ${role}?`)) return;
        try {
            await apiJson('/users/approve', 'POST', { str_user_id: userId, str_new_role: role });
            showAlert('Completed successfully.', 'success');
            loadPending();
        } catch (err) { showAlert(err.message, 'error'); }
    } else if (btn.dataset.reject) {
        const userId = btn.dataset.reject;
        const reason = prompt('Enter a rejection reason (optional):', '') || '';
        if (reason === null) return;
        if (!confirm('Reject this signup request?')) return;
        try {
            await apiJson('/users/reject', 'POST', { str_user_id: userId, str_reason: reason });
            showAlert('Updated successfully.', 'success');
            loadPending();
        } catch (err) { showAlert(err.message, 'error'); }
    }
});

document.getElementById('btn-refresh-pending').addEventListener('click', loadPending);

function updatePendingBadge(count) {
    const $badge = document.getElementById('pending-badge');
    $badge.textContent = String(count || 0);
    $badge.setAttribute('data-count', String(count || 0));
}

// ═══════════════════════════════════════
// text text
// ═══════════════════════════════════════
let currentPage = 0;
let totalUsers = 0;
const userCache = new Map(); // id → user doc

async function loadUsers() {
    const $tbody = document.getElementById('users-tbody');
    $tbody.innerHTML = '<tr><td colspan="8" class="empty-row">Loading...</td></tr>';
    try {
        const params = new URLSearchParams({
            int_skip: currentPage * PAGE_LIMIT,
            int_limit: PAGE_LIMIT,
        });
        const status = document.getElementById('filter-status').value;
        const search = document.getElementById('filter-search').value.trim();
        if (status) params.append('str_approval_status', status);
        if (search) params.append('str_search', search);

        const data = await apiGet(`/users/list?${params}`);
        if (!data) return;
        totalUsers = data.int_total || 0;
        updatePendingBadge(data.int_pending_total || 0);

        const list = data.list_users || [];
        if (list.length === 0) {
            $tbody.innerHTML = '<tr><td colspan="8" class="empty-row">text text.</td></tr>';
            updatePager();
            return;
        }
        $tbody.innerHTML = '';
        userCache.clear();
        for (const u of list) {
            userCache.set(u._id, u);
            const isSelf = u._id === currentUser.str_id;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${esc(u.str_login_id)}</strong>${isSelf ? ' <small>(me)</small>' : ''}</td>
                <td>${esc(u.str_name)}</td>
                <td>${esc(u.str_department || '—')}</td>
                <td>
                    <select class="role-select" data-role-change="${u._id}" ${isSelf ? 'disabled' : ''}>
                        <option value="viewer" ${u.str_role === 'viewer' ? 'selected' : ''}>Viewer</option>
                        <option value="doctor" ${u.str_role === 'doctor' ? 'selected' : ''}>Doctor</option>
                        <option value="admin" ${u.str_role === 'admin' ? 'selected' : ''}>Admin</option>
                    </select>
                </td>
                <td><span class="status-pill ${u.str_approval_status || 'approved'}">${u.str_approval_status || 'approved'}</span></td>
                <td>
                    ${u.bool_is_active ? '✔' : '—'}
                    ${u.bool_is_locked ? ' 🔒' : ''}
                </td>
                <td>${fmtDate(u.dt_last_login)}</td>
                <td class="row-actions">
                    <button class="admin-btn-secondary" data-edit="${u._id}">Previous</button>
                    ${u.bool_is_locked ? `<button class="admin-btn-secondary" data-unlock="${u._id}">Previous</button>` : ''}
                    ${!isSelf ? `<button class="admin-btn-secondary" data-toggle-active="${u._id}" data-active="${u.bool_is_active ? '1' : '0'}">${u.bool_is_active ? 'Deactivate' : 'Activate'}</button>` : ''}
                    ${!isSelf ? `<button class="admin-btn-danger" data-delete="${u._id}" data-login="${esc(u.str_login_id)}">Previous</button>` : ''}
                </td>
            `;
            $tbody.appendChild(tr);
        }
        updatePager();
    } catch (err) {
        showAlert(err.message, 'error');
        $tbody.innerHTML = '<tr><td colspan="8" class="empty-row">Load failed</td></tr>';
    }
}

function updatePager() {
    const totalPages = Math.max(1, Math.ceil(totalUsers / PAGE_LIMIT));
    document.getElementById('page-info').textContent = `${currentPage + 1} / ${totalPages} (total ${totalUsers})`;
    document.getElementById('btn-prev-page').disabled = currentPage === 0;
    document.getElementById('btn-next-page').disabled = currentPage + 1 >= totalPages;
}

document.getElementById('btn-refresh-users').addEventListener('click', () => { currentPage = 0; loadUsers(); });
document.getElementById('filter-status').addEventListener('change', () => { currentPage = 0; loadUsers(); });
let searchTimer = null;
document.getElementById('filter-search').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { currentPage = 0; loadUsers(); }, 300);
});
document.getElementById('btn-prev-page').addEventListener('click', () => { if (currentPage > 0) { currentPage--; loadUsers(); } });
document.getElementById('btn-next-page').addEventListener('click', () => { currentPage++; loadUsers(); });

document.getElementById('users-tbody').addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;

    if (btn.dataset.delete) {
        const login = btn.dataset.login;
        if (!confirm(`Delete user '${login}'?`)) return;
        try {
            await apiDelete(`/users/delete/${btn.dataset.delete}`);
            showAlert('Completed successfully.', 'success');
            loadUsers();
        } catch (err) { showAlert(err.message, 'error'); }
    } else if (btn.dataset.unlock) {
        try {
            const res = await authFetch(`/users/unlock/${btn.dataset.unlock}`, { method: 'POST' });
            if (res && res.ok) { showAlert('Updated successfully.', 'success'); loadUsers(); }
            else { const d = await res.json().catch(() => ({})); throw new Error(d.detail || 'Failed'); }
        } catch (err) { showAlert(err.message, 'error'); }
    } else if (btn.dataset.toggleActive !== undefined) {
        const nowActive = btn.dataset.active === '1';
        try {
            await apiJson('/users/toggle-active', 'POST', {
                str_user_id: btn.dataset.toggleActive,
                bool_is_active: !nowActive,
            });
            showAlert(nowActive ? 'Account deactivated.' : 'Account activated.', 'success');
            loadUsers();
        } catch (err) { showAlert(err.message, 'error'); }
    } else if (btn.dataset.edit) {
        const u = userCache.get(btn.dataset.edit);
        if (u) openEditDialog({
            id: u._id,
            login_id: u.str_login_id,
            name: u.str_name,
            department: u.str_department || '',
        });
    }
});

document.getElementById('users-tbody').addEventListener('change', async (e) => {
    const select = e.target;
    if (!select.matches('[data-role-change]')) return;
    const userId = select.dataset.roleChange;
    const newRole = select.value;
    if (!confirm(`Change role to ${newRole}?`)) {
        loadUsers();
        return;
    }
    try {
        await apiJson('/users/role', 'POST', { str_user_id: userId, str_new_role: newRole });
        showAlert('Updated successfully.', 'success');
        loadUsers();
    } catch (err) {
        showAlert(err.message, 'error');
        loadUsers();
    }
});

// ─── text text ───
const $editDialog = document.getElementById('edit-dialog');
function openEditDialog(u) {
    document.getElementById('edit-user-id').value = u.id;
    document.getElementById('edit-login-id').value = u.login_id;
    document.getElementById('edit-name').value = u.name || '';
    document.getElementById('edit-department').value = u.department || '';
    document.getElementById('edit-password').value = '';
    $editDialog.showModal();
}
document.getElementById('btn-edit-cancel').addEventListener('click', () => $editDialog.close());
document.getElementById('btn-edit-save').addEventListener('click', async () => {
    const body = {
        str_user_id: document.getElementById('edit-user-id').value,
        str_name: document.getElementById('edit-name').value,
        str_department: document.getElementById('edit-department').value,
    };
    const pw = document.getElementById('edit-password').value;
    if (pw) body.str_password = pw;
    try {
        await apiJson('/users/update', 'POST', body);
        showAlert('Completed successfully.', 'success');
        $editDialog.close();
        loadUsers();
    } catch (err) {
        showAlert(err.message, 'error');
    }
});

// ═══════════════════════════════════════
// text text
// ═══════════════════════════════════════
document.getElementById('create-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
        str_login_id: document.getElementById('new-login-id').value.trim(),
        str_password: document.getElementById('new-password').value,
        str_name: document.getElementById('new-name').value.trim(),
        str_department: document.getElementById('new-department').value.trim(),
        str_role: document.getElementById('new-role').value,
    };
    try {
        const data = await apiJson('/users/create', 'POST', body);
        showAlert(`Created: ${data.str_login_id}`, 'success');
        e.target.reset();
    } catch (err) {
        showAlert(err.message, 'error');
    }
});

// ═══════════════════════════════════════
// text text
// ═══════════════════════════════════════
const ACTIVITY_PAGE_LIMIT = 50;
let _int_activity_skip = 0;
let _int_activity_total = 0;
let _str_activity_user_filter = '';

function _parseDevice(strUa) {
    if (!strUa) return '—';
    const ua = strUa;
    if (/Windows NT/.test(ua)) return 'Windows';
    if (/Mac OS X/.test(ua)) return 'macOS';
    if (/Android/.test(ua)) return 'Android';
    if (/iPhone|iPad|iPod/.test(ua)) return 'iOS';
    if (/Linux/.test(ua)) return 'Linux';
    return ua.split(' ')[0] || '—';
}

function _fmtLocation(log) {
    const list_parts = [];
    if (log.str_city) list_parts.push(log.str_city);
    if (log.str_region && log.str_region !== log.str_city) list_parts.push(log.str_region);
    if (log.str_country_name) list_parts.push(log.str_country_name);
    else if (log.str_country) list_parts.push(log.str_country);
    return list_parts.length ? esc(list_parts.join(', ')) : '—';
}

async function loadActivity() {
    const $tbody = document.getElementById('activity-tbody');
    $tbody.innerHTML = '<tr><td colspan="7" class="empty-row">Loading...</td></tr>';
    try {
        const params = new URLSearchParams({
            int_skip: String(_int_activity_skip),
            int_limit: String(ACTIVITY_PAGE_LIMIT),
        });
        const data = await apiGet(`/users/activity/logins?${params}`);
        if (!data) return;
        const list = data.list_logs || [];
        _int_activity_total = data.int_total || 0;
        if (list.length === 0) {
            $tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No search results found.</td></tr>';
        } else {
            let list_filtered = list;
            if (_str_activity_user_filter) {
                const q = _str_activity_user_filter.toLowerCase();
                list_filtered = list.filter(l => {
                    const u = l.dict_user || {};
                    return (u.str_login_id || '').toLowerCase().includes(q) ||
                           (u.str_name || '').toLowerCase().includes(q);
                });
            }
            if (list_filtered.length === 0) {
                $tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No search results found.</td></tr>';
            } else {
                $tbody.innerHTML = '';
                for (const log of list_filtered) {
                    const u = log.dict_user || {};
                    const tr = document.createElement('tr');
                    tr.className = 'activity-row';
                    tr.dataset.userId = log.str_user_id || '';
                    tr.innerHTML = `
                        <td>${fmtDate(log.dt_created_at)}</td>
                        <td><strong>${esc(u.str_login_id || log.str_user_email || '—')}</strong></td>
                        <td>${esc(u.str_name || '—')} <span class="role-chip">${esc(u.str_role || '')}</span></td>
                        <td><code>${esc(log.str_ip_address || '—')}</code></td>
                        <td>${_fmtLocation(log)}</td>
                        <td>${esc(_parseDevice(log.str_user_agent))}</td>
                        <td><button class="admin-btn-secondary btn-view-activity" data-user-id="${esc(log.str_user_id || '')}">Details</button></td>
                    `;
                    $tbody.appendChild(tr);
                }
            }
        }
        _updateActivityPager();
    } catch (err) {
        $tbody.innerHTML = `<tr><td colspan="7" class="empty-row">Error: ${esc(err.message)}</td></tr>`;
    }
}

function _updateActivityPager() {
    const int_page = Math.floor(_int_activity_skip / ACTIVITY_PAGE_LIMIT) + 1;
    const int_total_pages = Math.max(1, Math.ceil(_int_activity_total / ACTIVITY_PAGE_LIMIT));
    document.getElementById('activity-page-info').textContent = `${int_page} / ${int_total_pages}`;
    document.getElementById('btn-activity-prev').disabled = _int_activity_skip <= 0;
    document.getElementById('btn-activity-next').disabled =
        _int_activity_skip + ACTIVITY_PAGE_LIMIT >= _int_activity_total;
}

document.getElementById('btn-refresh-activity').addEventListener('click', () => {
    _int_activity_skip = 0;
    loadActivity();
});
document.getElementById('activity-filter-user').addEventListener('input', (e) => {
    _str_activity_user_filter = e.target.value.trim();
    loadActivity();
});
document.getElementById('btn-activity-prev').addEventListener('click', () => {
    if (_int_activity_skip <= 0) return;
    _int_activity_skip = Math.max(0, _int_activity_skip - ACTIVITY_PAGE_LIMIT);
    loadActivity();
});
document.getElementById('btn-activity-next').addEventListener('click', () => {
    if (_int_activity_skip + ACTIVITY_PAGE_LIMIT >= _int_activity_total) return;
    _int_activity_skip += ACTIVITY_PAGE_LIMIT;
    loadActivity();
});

// text text / text text text text text
document.getElementById('activity-tbody').addEventListener('click', (e) => {
    const $btn = e.target.closest('.btn-view-activity');
    const $row = e.target.closest('.activity-row');
    const str_user_id = ($btn && $btn.dataset.userId) || ($row && $row.dataset.userId);
    if (str_user_id) openUserActivityDialog(str_user_id);
});

// ═══════════════════════════════════════
// text text text text
// ═══════════════════════════════════════
const $userActivityDialog = document.getElementById('user-activity-dialog');
const $userActivityTbody = document.getElementById('user-activity-tbody');
const $userActivityTitle = document.getElementById('user-activity-title');
const USER_ACTIVITY_PAGE_LIMIT = 100;
let _str_current_activity_user = null;
let _str_current_activity_cat = 'all';
let _int_user_activity_skip = 0;
let _int_user_activity_total = 0;
let _str_user_activity_start = '';
let _str_user_activity_end = '';

function _ensureUserActivityPager() {
    if (!$userActivityDialog || document.getElementById('user-activity-page-info')) return;
    const $body = $userActivityDialog.querySelector('.activity-body');
    if (!$body) return;
    $body.insertAdjacentHTML('beforebegin', `
        <div class="activity-date-filter">
            <label>From <input id="user-activity-start-date" type="date"></label>
            <label>To <input id="user-activity-end-date" type="date"></label>
            <button id="btn-user-activity-apply-date" class="admin-btn-primary" type="button">Apply</button>
            <button id="btn-user-activity-clear-date" class="admin-btn-secondary" type="button">Clear</button>
        </div>
    `);
    $body.insertAdjacentHTML('afterend', `
        <div class="pager user-activity-pager">
            <button id="btn-user-activity-prev" class="admin-btn-secondary" type="button">Previous</button>
            <span id="user-activity-page-info">1 / 1</span>
            <label class="page-jump">Page <input id="user-activity-page-input" type="number" min="1" value="1"></label>
            <button id="btn-user-activity-page-go" class="admin-btn-secondary" type="button">Go</button>
            <button id="btn-user-activity-next" class="admin-btn-secondary" type="button">Next</button>
        </div>
        <div id="user-activity-range" class="activity-range"></div>
    `);
    document.getElementById('btn-user-activity-apply-date')?.addEventListener('click', () => {
        _str_user_activity_start = document.getElementById('user-activity-start-date')?.value || '';
        _str_user_activity_end = document.getElementById('user-activity-end-date')?.value || '';
        _int_user_activity_skip = 0;
        _loadUserActivity();
    });
    document.getElementById('btn-user-activity-clear-date')?.addEventListener('click', () => {
        _str_user_activity_start = '';
        _str_user_activity_end = '';
        const $start = document.getElementById('user-activity-start-date');
        const $end = document.getElementById('user-activity-end-date');
        if ($start) $start.value = '';
        if ($end) $end.value = '';
        _int_user_activity_skip = 0;
        _loadUserActivity();
    });
    document.getElementById('btn-user-activity-prev')?.addEventListener('click', () => {
        if (_int_user_activity_skip <= 0) return;
        _int_user_activity_skip = Math.max(0, _int_user_activity_skip - USER_ACTIVITY_PAGE_LIMIT);
        _loadUserActivity();
    });
    document.getElementById('btn-user-activity-next')?.addEventListener('click', () => {
        if (_int_user_activity_skip + USER_ACTIVITY_PAGE_LIMIT >= _int_user_activity_total) return;
        _int_user_activity_skip += USER_ACTIVITY_PAGE_LIMIT;
        _loadUserActivity();
    });
    const jumpToPage = () => {
        const $input = document.getElementById('user-activity-page-input');
        const int_total_pages = Math.max(1, Math.ceil(_int_user_activity_total / USER_ACTIVITY_PAGE_LIMIT));
        const int_page = Math.min(Math.max(parseInt($input?.value || '1', 10) || 1, 1), int_total_pages);
        _int_user_activity_skip = (int_page - 1) * USER_ACTIVITY_PAGE_LIMIT;
        _loadUserActivity();
    };
    document.getElementById('btn-user-activity-page-go')?.addEventListener('click', jumpToPage);
    document.getElementById('user-activity-page-input')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') jumpToPage();
    });
}

function _updateUserActivityPager(intCount) {
    const int_total_pages = Math.max(1, Math.ceil(_int_user_activity_total / USER_ACTIVITY_PAGE_LIMIT));
    const int_page = Math.floor(_int_user_activity_skip / USER_ACTIVITY_PAGE_LIMIT) + 1;
    const int_start = _int_user_activity_total === 0 ? 0 : _int_user_activity_skip + 1;
    const int_end = Math.min(_int_user_activity_skip + intCount, _int_user_activity_total);
    const $info = document.getElementById('user-activity-page-info');
    const $range = document.getElementById('user-activity-range');
    const $prev = document.getElementById('btn-user-activity-prev');
    const $next = document.getElementById('btn-user-activity-next');
    const $input = document.getElementById('user-activity-page-input');
    if ($info) $info.textContent = `${int_page} / ${int_total_pages}`;
    if ($range) $range.textContent = `${int_start} - ${int_end} / ${_int_user_activity_total}`;
    if ($prev) $prev.disabled = _int_user_activity_skip <= 0;
    if ($next) $next.disabled = _int_user_activity_skip + USER_ACTIVITY_PAGE_LIMIT >= _int_user_activity_total;
    if ($input) {
        $input.max = String(int_total_pages);
        $input.value = String(int_page);
    }
}

async function openUserActivityDialog(strUserId) {
    _str_current_activity_user = strUserId;
    _str_current_activity_cat = 'all';
    _int_user_activity_skip = 0;
    _str_user_activity_start = '';
    _str_user_activity_end = '';
    document.querySelectorAll('.activity-cat-tab').forEach(t =>
        t.classList.toggle('active', t.dataset.cat === 'all')
    );
    _ensureUserActivityPager();
    const $start = document.getElementById('user-activity-start-date');
    const $end = document.getElementById('user-activity-end-date');
    if ($start) $start.value = '';
    if ($end) $end.value = '';
    if (!$userActivityDialog.open) $userActivityDialog.showModal();
    await _loadUserActivity();
}

async function _loadUserActivity() {
    _ensureUserActivityPager();
    $userActivityTbody.innerHTML = '<tr><td colspan="4" class="empty-row">Loading...</td></tr>';
    try {
        const params = new URLSearchParams({
            int_limit: String(USER_ACTIVITY_PAGE_LIMIT),
            int_skip: String(_int_user_activity_skip),
            str_category: _str_current_activity_cat,
        });
        if (_str_user_activity_start) params.set('str_start_date', _str_user_activity_start);
        if (_str_user_activity_end) params.set('str_end_date', _str_user_activity_end);
        const data = await apiGet(`/users/${encodeURIComponent(_str_current_activity_user)}/activity?${params}`);
        if (!data) return;
        const u = data.dict_user || {};
        $userActivityTitle.textContent =
            `${u.str_name || '—'} (${u.str_login_id || '—'}) · ${u.str_role || '—'}`;

        // text text
        const dict_counts = data.dict_counts || {};
        const int_all = (dict_counts.login || 0) + (dict_counts.slide || 0) +
            (dict_counts.ai || 0) + (dict_counts.project || 0) + (dict_counts.file || 0);
        document.querySelector('.cat-badge[data-badge="all"]').textContent = String(int_all);
        document.querySelector('.cat-badge[data-badge="login"]').textContent = String(dict_counts.login || 0);
        document.querySelector('.cat-badge[data-badge="slide"]').textContent = String(dict_counts.slide || 0);
        document.querySelector('.cat-badge[data-badge="ai"]').textContent = String(dict_counts.ai || 0);
        document.querySelector('.cat-badge[data-badge="project"]').textContent = String(dict_counts.project || 0);
        document.querySelector('.cat-badge[data-badge="file"]').textContent = String(dict_counts.file || 0);

        const list = data.list_logs || [];
        _int_user_activity_total = data.int_total || 0;
        _updateUserActivityPager(list.length);
        if (list.length === 0) {
            $userActivityTbody.innerHTML = '<tr><td colspan="4" class="empty-row">text No search results found.</td></tr>';
            return;
        }
        $userActivityTbody.innerHTML = '';
        for (const log of list) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${fmtDate(log.dt_created_at)}</td>
                <td>${_fmtActionPill(log.str_action)}</td>
                <td>${_fmtActivityDetail(log)}</td>
                <td><code>${esc(log.str_ip_address || '—')}</code><br><small>${_fmtLocation(log)}</small></td>
            `;
            $userActivityTbody.appendChild(tr);
        }
    } catch (err) {
        $userActivityTbody.innerHTML = `<tr><td colspan="4" class="empty-row">Error: ${esc(err.message)}</td></tr>`;
    }
}

function _fmtActionPill(strAction) {
    const dict_label = {
        'project.create':     ['Project created', 'success'],
        'project.update':     ['Project updated', 'info'],
        'project.rename':     ['Project renamed', 'accent'],
        'project.move_folder':['Project moved', 'accent'],
        'project.delete':     ['Project deleted', 'error'],
        'folder.create':      ['Folder created', 'success'],
        'folder.rename':      ['Folder renamed', 'accent'],
        'folder.delete':      ['Folder deleted', 'error'],
        'folder.ai_config_update': ['Auto analysis settings', 'info'],
        'folder.ai_config_delete': ['Auto analysis settings deleted', 'error'],
        'file.delete':        ['File deleted', 'error'],
        'file.move':          ['File moved', 'accent'],
        'slide.upload':       ['Slide uploaded', 'success'],
        'slide.status_update':['Slide status', 'info'],
        'user.login_success': ['Sign in', 'success'],
        'user.login_failed':  ['Login failed', 'error'],
        'user.logout':        ['Logout', 'neutral'],
        'slide.view':         ['Slide viewed', 'info'],
        'ai.analyze':         ['AI analysis', 'accent'],
    };
    const pair = dict_label[strAction] || [strAction, 'neutral'];
    return `<span class="action-pill ${pair[1]}">${esc(pair[0])}</span>`;
}

function _fmtActivityDetail(log) {
    if (log.str_action === 'slide.view') {
        const str_path = log.str_rel_path ? `${log.str_rel_path}/` : '';
        return `<strong>${esc(log.str_detail || '—')}</strong>` +
               (str_path ? `<br><small>${esc(str_path)}</small>` : '');
    }
    if (log.str_action === 'ai.analyze') {
        return `<strong>${esc(log.str_model || '')} · ${esc(log.str_variant || '')}</strong>` +
               (log.str_slide_filename ? `<br><small>${esc(log.str_slide_filename)}</small>` : '');
    }
    if ((log.str_action || '').startsWith('project.') || (log.str_action || '').startsWith('folder.') ||
        (log.str_action || '').startsWith('file.') || log.str_action === 'slide.upload' ||
        log.str_action === 'slide.status_update') {
        const list_bits = [];
        if (log.str_rel_path) list_bits.push(log.str_rel_path);
        if (log.str_src_path || log.str_dst_path) list_bits.push(`${log.str_src_path || '-'} -> ${log.str_dst_path || '-'}`);
        if (Array.isArray(log.list_filenames) && log.list_filenames.length) list_bits.push(log.list_filenames.join(', '));
        return `<strong>${esc(log.str_detail || '??')}</strong>` +
               (list_bits.length ? `<br><small>${esc(list_bits.join(' / '))}</small>` : '');
    }
    return esc(log.str_detail || '—');
}

const $activityTabs = document.querySelector('.activity-tabs');
if ($activityTabs && !$activityTabs.querySelector('[data-cat="project"]')) {
    $activityTabs.insertAdjacentHTML('beforeend', `
        <button class="activity-cat-tab" data-cat="project">Projects <span class="cat-badge" data-badge="project">0</span></button>
        <button class="activity-cat-tab" data-cat="file">Files <span class="cat-badge" data-badge="file">0</span></button>
    `);
}

document.querySelectorAll('.activity-cat-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.activity-cat-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        _str_current_activity_cat = tab.dataset.cat;
        _int_user_activity_skip = 0;
        _loadUserActivity();
    });
});

document.getElementById('btn-user-activity-close').addEventListener('click', () => {
    $userActivityDialog.close();
});

// ─── text text ───
loadPending();
