// MeDIAuto Studio admin page.

const API_BASE = '/api';
const PAGE_LIMIT = 20;
const ACTIVITY_PAGE_LIMIT = 50;
const USER_ACTIVITY_PAGE_LIMIT = 100;
const ROLE_OPTIONS = [
    ['viewer', 'Viewer'],
    ['labeler', 'Labeler'],
    ['doctor', 'Doctor'],
    ['admin', 'Admin'],
];

const accessToken = localStorage.getItem('access_token');
const userRaw = localStorage.getItem('user');

if (!accessToken || !userRaw) {
    location.href = '/login';
}

let currentUser = null;
try {
    currentUser = JSON.parse(userRaw);
} catch {
    currentUser = null;
}

window.MediautoHeader?.render({
    active: 'admin',
    user: currentUser,
    showAdmin: true,
});

if (!currentUser || currentUser.str_role !== 'admin') {
    alert('Administrator permission is required.');
    location.href = '/ai';
}

const currentUserId = String(currentUser?._id || currentUser?.str_id || currentUser?.id || '');
const $alert = document.getElementById('admin-alert');
const userCache = new Map();

let currentPage = 0;
let totalUsers = 0;
let activitySkip = 0;
let activityTotal = 0;
let activityUserFilter = '';
let currentActivityUserId = '';
let currentActivityCategory = 'all';
let userActivitySkip = 0;
let userActivityTotal = 0;
let userActivityStart = '';
let userActivityEnd = '';
let boolLoadingSettings = false;

document.getElementById('current-user-name').textContent =
    currentUser.str_name || currentUser.str_login_id || '-';
document.getElementById('current-user-role').textContent = currentUser.str_role || 'admin';
populateCreateRoleSelect();

function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[ch]));
}

function roleOptionsHtml(selected = 'viewer') {
    return ROLE_OPTIONS.map(([value, label]) => (
        `<option value="${esc(value)}" ${selected === value ? 'selected' : ''}>${esc(label)}</option>`
    )).join('');
}

function populateCreateRoleSelect() {
    const createSelect = document.getElementById('new-role');
    if (createSelect) createSelect.innerHTML = roleOptionsHtml(createSelect.value || 'viewer');
}

function fmtDate(value) {
    if (!value) return '-';
    let text = String(value);
    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(text)) text += 'Z';
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString('ko-KR', { hour12: false, timeZone: 'Asia/Seoul' });
}

function showAlert(message, type = 'success') {
    $alert.textContent = typeof message === 'object' ? JSON.stringify(message) : String(message);
    $alert.className = `admin-alert ${type}`;
    $alert.hidden = false;
    setTimeout(() => {
        $alert.hidden = true;
    }, 4000);
}

async function authFetch(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    headers.Authorization = `Bearer ${accessToken}`;
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
        const data = await res.json().catch(() => ({}));
        alert(data.detail || 'Permission denied.');
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

function setEmpty(tbody, colspan, message) {
    tbody.innerHTML = `<tr><td colspan="${colspan}" class="empty-row">${esc(message)}</td></tr>`;
}

function updatePendingBadge(count) {
    const badge = document.getElementById('pending-badge');
    badge.textContent = String(count || 0);
    badge.setAttribute('data-count', String(count || 0));
}

document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.admin-tab').forEach(item => item.classList.remove('active'));
        document.querySelectorAll('.admin-panel').forEach(panel => panel.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab).classList.add('active');

        if (tab.dataset.tab === 'pending-panel') loadPending();
        if (tab.dataset.tab === 'users-panel') loadUsers();
        if (tab.dataset.tab === 'activity-panel') loadActivity();
        if (tab.dataset.tab === 'settings-panel') loadSettings();
    });
});

document.getElementById('btn-logout').addEventListener('click', async () => {
    try {
        await authFetch('/auth/logout', { method: 'POST' });
    } catch {}
    localStorage.clear();
    location.href = '/login';
});

async function loadPending() {
    const tbody = document.getElementById('pending-tbody');
    setEmpty(tbody, 6, 'Loading...');
    try {
        const data = await apiGet('/users/pending');
        if (!data) return;
        const list = data.list_pending || [];
        updatePendingBadge(list.length);
        if (!list.length) {
            setEmpty(tbody, 6, 'No users are waiting for approval.');
            return;
        }
        tbody.innerHTML = '';
        for (const user of list) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${esc(user.str_login_id)}</strong></td>
                <td>${esc(user.str_name)}</td>
                <td>${esc(user.str_department || '-')}</td>
                <td>${fmtDate(user.dt_created_at)}</td>
                <td>
                    <select class="role-select" data-role-for="${esc(user._id)}">
                        ${roleOptionsHtml('viewer')}
                    </select>
                </td>
                <td class="row-actions">
                    <button class="admin-btn-approve" data-approve="${esc(user._id)}">Approve</button>
                    <button class="admin-btn-reject" data-reject="${esc(user._id)}">Reject</button>
                </td>
            `;
            tbody.appendChild(tr);
        }
    } catch (err) {
        showAlert(err.message, 'error');
        setEmpty(tbody, 6, 'Load failed');
    }
}

document.getElementById('pending-tbody').addEventListener('click', async (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.approve) {
        const userId = button.dataset.approve;
        const role = document.querySelector(`[data-role-for="${CSS.escape(userId)}"]`)?.value || 'viewer';
        if (!confirm(`Approve this user as ${role}?`)) return;
        try {
            await apiJson('/users/approve', 'POST', { str_user_id: userId, str_new_role: role });
            showAlert('User approved.', 'success');
            loadPending();
        } catch (err) {
            showAlert(err.message, 'error');
        }
    }
    if (button.dataset.reject) {
        const userId = button.dataset.reject;
        const reason = prompt('Enter a rejection reason (optional):', '') || '';
        if (!confirm('Reject this signup request?')) return;
        try {
            await apiJson('/users/reject', 'POST', { str_user_id: userId, str_reason: reason });
            showAlert('User rejected.', 'success');
            loadPending();
        } catch (err) {
            showAlert(err.message, 'error');
        }
    }
});

document.getElementById('btn-refresh-pending').addEventListener('click', loadPending);

async function loadUsers() {
    const tbody = document.getElementById('users-tbody');
    setEmpty(tbody, 8, 'Loading...');
    try {
        const params = new URLSearchParams({
            int_skip: String(currentPage * PAGE_LIMIT),
            int_limit: String(PAGE_LIMIT),
        });
        const status = document.getElementById('filter-status').value;
        const search = document.getElementById('filter-search').value.trim();
        if (status) params.set('str_approval_status', status);
        if (search) params.set('str_search', search);

        const data = await apiGet(`/users/list?${params}`);
        if (!data) return;
        totalUsers = data.int_total || 0;
        updatePendingBadge(data.int_pending_total || 0);
        const list = data.list_users || [];
        if (!list.length) {
            setEmpty(tbody, 8, 'No users found.');
            updatePager();
            return;
        }
        tbody.innerHTML = '';
        userCache.clear();
        for (const user of list) {
            userCache.set(user._id, user);
            const isSelf = String(user._id) === currentUserId;
            const activeText = user.bool_is_active ? 'Active' : 'Inactive';
            const lockedText = user.bool_is_locked ? ' Locked' : '';
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${esc(user.str_login_id)}</strong>${isSelf ? ' <small>(me)</small>' : ''}</td>
                <td>${esc(user.str_name)}</td>
                <td>${esc(user.str_department || '-')}</td>
                <td>
                    <select class="role-select" data-role-change="${esc(user._id)}" ${isSelf ? 'disabled' : ''}>
                        ${roleOptionsHtml(user.str_role || 'viewer')}
                    </select>
                </td>
                <td><span class="status-pill ${esc(user.str_approval_status || 'approved')}">${esc(user.str_approval_status || 'approved')}</span></td>
                <td>${esc(activeText + lockedText)}</td>
                <td>${fmtDate(user.dt_last_login)}</td>
                <td class="row-actions">
                    <button class="admin-btn-secondary" data-edit="${esc(user._id)}">Edit</button>
                    ${user.bool_is_locked ? `<button class="admin-btn-secondary" data-unlock="${esc(user._id)}">Unlock</button>` : ''}
                    ${!isSelf ? `<button class="admin-btn-secondary" data-toggle-active="${esc(user._id)}" data-active="${user.bool_is_active ? '1' : '0'}">${user.bool_is_active ? 'Deactivate' : 'Activate'}</button>` : ''}
                    ${!isSelf ? `<button class="admin-btn-danger" data-delete="${esc(user._id)}" data-login="${esc(user.str_login_id)}">Delete</button>` : ''}
                </td>
            `;
            tbody.appendChild(tr);
        }
        updatePager();
    } catch (err) {
        showAlert(err.message, 'error');
        setEmpty(tbody, 8, 'Load failed');
    }
}

function updatePager() {
    const totalPages = Math.max(1, Math.ceil(totalUsers / PAGE_LIMIT));
    document.getElementById('page-info').textContent =
        `${currentPage + 1} / ${totalPages} (total ${totalUsers})`;
    document.getElementById('btn-prev-page').disabled = currentPage === 0;
    document.getElementById('btn-next-page').disabled = currentPage + 1 >= totalPages;
}

document.getElementById('btn-refresh-users').addEventListener('click', () => {
    currentPage = 0;
    loadUsers();
});
document.getElementById('filter-status').addEventListener('change', () => {
    currentPage = 0;
    loadUsers();
});
let searchTimer = null;
document.getElementById('filter-search').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        currentPage = 0;
        loadUsers();
    }, 300);
});
document.getElementById('btn-prev-page').addEventListener('click', () => {
    if (currentPage > 0) {
        currentPage--;
        loadUsers();
    }
});
document.getElementById('btn-next-page').addEventListener('click', () => {
    currentPage++;
    loadUsers();
});

document.getElementById('users-tbody').addEventListener('click', async (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.delete) {
        if (!confirm(`Delete user '${button.dataset.login}'?`)) return;
        try {
            await apiDelete(`/users/delete/${encodeURIComponent(button.dataset.delete)}`);
            showAlert('User deleted.', 'success');
            loadUsers();
        } catch (err) {
            showAlert(err.message, 'error');
        }
    } else if (button.dataset.unlock) {
        try {
            await authFetch(`/users/unlock/${encodeURIComponent(button.dataset.unlock)}`, { method: 'POST' });
            showAlert('Account unlocked.', 'success');
            loadUsers();
        } catch (err) {
            showAlert(err.message, 'error');
        }
    } else if (button.dataset.toggleActive !== undefined) {
        const nowActive = button.dataset.active === '1';
        try {
            await apiJson('/users/toggle-active', 'POST', {
                str_user_id: button.dataset.toggleActive,
                bool_is_active: !nowActive,
            });
            showAlert(nowActive ? 'Account deactivated.' : 'Account activated.', 'success');
            loadUsers();
        } catch (err) {
            showAlert(err.message, 'error');
        }
    } else if (button.dataset.edit) {
        const user = userCache.get(button.dataset.edit);
        if (user) openEditDialog(user);
    }
});

document.getElementById('users-tbody').addEventListener('change', async (event) => {
    const select = event.target;
    if (!select.matches('[data-role-change]')) return;
    const userId = select.dataset.roleChange;
    const newRole = select.value;
    if (!confirm(`Change role to ${newRole}?`)) {
        loadUsers();
        return;
    }
    try {
        await apiJson('/users/role', 'POST', { str_user_id: userId, str_new_role: newRole });
        showAlert('Role updated.', 'success');
        loadUsers();
    } catch (err) {
        showAlert(err.message, 'error');
        loadUsers();
    }
});

const editDialog = document.getElementById('edit-dialog');
function openEditDialog(user) {
    document.getElementById('edit-user-id').value = user._id;
    document.getElementById('edit-login-id').value = user.str_login_id || '';
    document.getElementById('edit-name').value = user.str_name || '';
    document.getElementById('edit-department').value = user.str_department || '';
    document.getElementById('edit-password').value = '';
    editDialog.showModal();
}

document.getElementById('btn-edit-cancel').addEventListener('click', () => editDialog.close());
document.getElementById('btn-edit-save').addEventListener('click', async () => {
    const editForm = document.getElementById('edit-form');
    if (editForm && !editForm.reportValidity()) return;
    const body = {
        str_user_id: document.getElementById('edit-user-id').value,
        str_name: document.getElementById('edit-name').value,
        str_department: document.getElementById('edit-department').value,
    };
    const password = document.getElementById('edit-password').value;
    if (password) body.str_password = password;
    try {
        await apiJson('/users/update', 'POST', body);
        showAlert('User updated.', 'success');
        editDialog.close();
        loadUsers();
    } catch (err) {
        showAlert(err.message, 'error');
    }
});

document.getElementById('create-form').addEventListener('submit', async (event) => {
    event.preventDefault();
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
        event.target.reset();
    } catch (err) {
        showAlert(err.message, 'error');
    }
});

function parseDevice(userAgent) {
    if (!userAgent) return '-';
    if (/Windows NT/.test(userAgent)) return 'Windows';
    if (/Mac OS X/.test(userAgent)) return 'macOS';
    if (/Android/.test(userAgent)) return 'Android';
    if (/iPhone|iPad|iPod/.test(userAgent)) return 'iOS';
    if (/Linux/.test(userAgent)) return 'Linux';
    return userAgent.split(' ')[0] || '-';
}

function fmtLocation(log) {
    const parts = [];
    if (log.str_city) parts.push(log.str_city);
    if (log.str_region && log.str_region !== log.str_city) parts.push(log.str_region);
    if (log.str_country_name) parts.push(log.str_country_name);
    else if (log.str_country) parts.push(log.str_country);
    return parts.length ? esc(parts.join(', ')) : '-';
}

async function loadActivity() {
    const tbody = document.getElementById('activity-tbody');
    setEmpty(tbody, 7, 'Loading...');
    try {
        const params = new URLSearchParams({
            int_skip: String(activitySkip),
            int_limit: String(ACTIVITY_PAGE_LIMIT),
        });
        const data = await apiGet(`/users/activity/logins?${params}`);
        if (!data) return;
        let list = data.list_logs || [];
        activityTotal = data.int_total || 0;
        if (activityUserFilter) {
            const query = activityUserFilter.toLowerCase();
            list = list.filter(log => {
                const user = log.dict_user || {};
                return (user.str_login_id || '').toLowerCase().includes(query)
                    || (user.str_name || '').toLowerCase().includes(query);
            });
        }
        if (!list.length) {
            setEmpty(tbody, 7, 'No activity found.');
        } else {
            tbody.innerHTML = '';
            for (const log of list) {
                const user = log.dict_user || {};
                const tr = document.createElement('tr');
                tr.className = 'activity-row';
                tr.dataset.userId = log.str_user_id || '';
                tr.innerHTML = `
                    <td>${fmtDate(log.dt_created_at)}</td>
                    <td><strong>${esc(user.str_login_id || log.str_user_email || '-')}</strong></td>
                    <td>${esc(user.str_name || '-')} <span class="role-chip">${esc(user.str_role || '')}</span></td>
                    <td><code>${esc(log.str_ip_address || '-')}</code></td>
                    <td>${fmtLocation(log)}</td>
                    <td>${esc(parseDevice(log.str_user_agent))}</td>
                    <td><button class="admin-btn-secondary btn-view-activity" data-user-id="${esc(log.str_user_id || '')}">Details</button></td>
                `;
                tbody.appendChild(tr);
            }
        }
        updateActivityPager();
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-row">Error: ${esc(err.message)}</td></tr>`;
    }
}

function updateActivityPager() {
    const page = Math.floor(activitySkip / ACTIVITY_PAGE_LIMIT) + 1;
    const totalPages = Math.max(1, Math.ceil(activityTotal / ACTIVITY_PAGE_LIMIT));
    document.getElementById('activity-page-info').textContent = `${page} / ${totalPages}`;
    document.getElementById('btn-activity-prev').disabled = activitySkip <= 0;
    document.getElementById('btn-activity-next').disabled =
        activitySkip + ACTIVITY_PAGE_LIMIT >= activityTotal;
}

document.getElementById('btn-refresh-activity').addEventListener('click', () => {
    activitySkip = 0;
    loadActivity();
});
document.getElementById('activity-filter-user').addEventListener('input', (event) => {
    activityUserFilter = event.target.value.trim();
    loadActivity();
});
document.getElementById('btn-activity-prev').addEventListener('click', () => {
    if (activitySkip <= 0) return;
    activitySkip = Math.max(0, activitySkip - ACTIVITY_PAGE_LIMIT);
    loadActivity();
});
document.getElementById('btn-activity-next').addEventListener('click', () => {
    if (activitySkip + ACTIVITY_PAGE_LIMIT >= activityTotal) return;
    activitySkip += ACTIVITY_PAGE_LIMIT;
    loadActivity();
});
document.getElementById('activity-tbody').addEventListener('click', (event) => {
    const button = event.target.closest('.btn-view-activity');
    const row = event.target.closest('.activity-row');
    const userId = button?.dataset.userId || row?.dataset.userId || '';
    if (userId) openUserActivityDialog(userId);
});

const userActivityDialog = document.getElementById('user-activity-dialog');
const userActivityTbody = document.getElementById('user-activity-tbody');
const userActivityTitle = document.getElementById('user-activity-title');

function ensureUserActivityControls() {
    if (document.getElementById('user-activity-page-info')) return;
    const body = userActivityDialog.querySelector('.activity-body');
    body.insertAdjacentHTML('beforebegin', `
        <div class="activity-date-filter">
            <label>From <input id="user-activity-start-date" type="date"></label>
            <label>To <input id="user-activity-end-date" type="date"></label>
            <button id="btn-user-activity-apply-date" class="admin-btn-primary" type="button">Apply</button>
            <button id="btn-user-activity-clear-date" class="admin-btn-secondary" type="button">Clear</button>
        </div>
    `);
    body.insertAdjacentHTML('afterend', `
        <div class="pager user-activity-pager">
            <button id="btn-user-activity-prev" class="admin-btn-secondary" type="button">Previous</button>
            <span id="user-activity-page-info">1 / 1</span>
            <label class="page-jump">Page <input id="user-activity-page-input" type="number" min="1" value="1"></label>
            <button id="btn-user-activity-page-go" class="admin-btn-secondary" type="button">Go</button>
            <button id="btn-user-activity-next" class="admin-btn-secondary" type="button">Next</button>
        </div>
        <div id="user-activity-range" class="activity-range"></div>
    `);
    document.getElementById('btn-user-activity-apply-date').addEventListener('click', () => {
        userActivityStart = document.getElementById('user-activity-start-date').value || '';
        userActivityEnd = document.getElementById('user-activity-end-date').value || '';
        userActivitySkip = 0;
        loadUserActivity();
    });
    document.getElementById('btn-user-activity-clear-date').addEventListener('click', () => {
        userActivityStart = '';
        userActivityEnd = '';
        document.getElementById('user-activity-start-date').value = '';
        document.getElementById('user-activity-end-date').value = '';
        userActivitySkip = 0;
        loadUserActivity();
    });
    document.getElementById('btn-user-activity-prev').addEventListener('click', () => {
        if (userActivitySkip <= 0) return;
        userActivitySkip = Math.max(0, userActivitySkip - USER_ACTIVITY_PAGE_LIMIT);
        loadUserActivity();
    });
    document.getElementById('btn-user-activity-next').addEventListener('click', () => {
        if (userActivitySkip + USER_ACTIVITY_PAGE_LIMIT >= userActivityTotal) return;
        userActivitySkip += USER_ACTIVITY_PAGE_LIMIT;
        loadUserActivity();
    });
    const jumpToPage = () => {
        const input = document.getElementById('user-activity-page-input');
        const totalPages = Math.max(1, Math.ceil(userActivityTotal / USER_ACTIVITY_PAGE_LIMIT));
        const page = Math.min(Math.max(parseInt(input.value || '1', 10) || 1, 1), totalPages);
        userActivitySkip = (page - 1) * USER_ACTIVITY_PAGE_LIMIT;
        loadUserActivity();
    };
    document.getElementById('btn-user-activity-page-go').addEventListener('click', jumpToPage);
    document.getElementById('user-activity-page-input').addEventListener('keydown', (event) => {
        if (event.key === 'Enter') jumpToPage();
    });
}

function updateUserActivityPager(count) {
    const totalPages = Math.max(1, Math.ceil(userActivityTotal / USER_ACTIVITY_PAGE_LIMIT));
    const page = Math.floor(userActivitySkip / USER_ACTIVITY_PAGE_LIMIT) + 1;
    const start = userActivityTotal === 0 ? 0 : userActivitySkip + 1;
    const end = Math.min(userActivitySkip + count, userActivityTotal);
    document.getElementById('user-activity-page-info').textContent = `${page} / ${totalPages}`;
    document.getElementById('user-activity-range').textContent = `${start} - ${end} / ${userActivityTotal}`;
    document.getElementById('btn-user-activity-prev').disabled = userActivitySkip <= 0;
    document.getElementById('btn-user-activity-next').disabled =
        userActivitySkip + USER_ACTIVITY_PAGE_LIMIT >= userActivityTotal;
    const input = document.getElementById('user-activity-page-input');
    input.max = String(totalPages);
    input.value = String(page);
}

async function openUserActivityDialog(userId) {
    currentActivityUserId = userId;
    currentActivityCategory = 'all';
    userActivitySkip = 0;
    userActivityStart = '';
    userActivityEnd = '';
    document.querySelectorAll('.activity-cat-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.cat === 'all');
    });
    ensureUserActivityControls();
    document.getElementById('user-activity-start-date').value = '';
    document.getElementById('user-activity-end-date').value = '';
    if (!userActivityDialog.open) userActivityDialog.showModal();
    await loadUserActivity();
}

async function loadUserActivity() {
    ensureUserActivityControls();
    setEmpty(userActivityTbody, 4, 'Loading...');
    try {
        const params = new URLSearchParams({
            int_limit: String(USER_ACTIVITY_PAGE_LIMIT),
            int_skip: String(userActivitySkip),
            str_category: currentActivityCategory,
        });
        if (userActivityStart) params.set('str_start_date', userActivityStart);
        if (userActivityEnd) params.set('str_end_date', userActivityEnd);
        const data = await apiGet(`/users/${encodeURIComponent(currentActivityUserId)}/activity?${params}`);
        if (!data) return;
        const user = data.dict_user || {};
        userActivityTitle.textContent =
            `${user.str_name || '-'} (${user.str_login_id || '-'}) - ${user.str_role || '-'}`;
        const counts = data.dict_counts || {};
        const allCount = (counts.login || 0) + (counts.slide || 0) +
            (counts.ai || 0) + (counts.project || 0) + (counts.file || 0);
        setBadge('all', allCount);
        setBadge('login', counts.login || 0);
        setBadge('slide', counts.slide || 0);
        setBadge('ai', counts.ai || 0);
        setBadge('project', counts.project || 0);
        setBadge('file', counts.file || 0);

        const list = data.list_logs || [];
        userActivityTotal = data.int_total || 0;
        updateUserActivityPager(list.length);
        if (!list.length) {
            setEmpty(userActivityTbody, 4, 'No activity found.');
            return;
        }
        userActivityTbody.innerHTML = '';
        for (const log of list) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${fmtDate(log.dt_created_at)}</td>
                <td>${fmtActionPill(log.str_action)}</td>
                <td>${fmtActivityDetail(log)}</td>
                <td><code>${esc(log.str_ip_address || '-')}</code><br><small>${fmtLocation(log)}</small></td>
            `;
            userActivityTbody.appendChild(tr);
        }
    } catch (err) {
        userActivityTbody.innerHTML = `<tr><td colspan="4" class="empty-row">Error: ${esc(err.message)}</td></tr>`;
    }
}

function setBadge(name, count) {
    const badge = document.querySelector(`.cat-badge[data-badge="${name}"]`);
    if (badge) badge.textContent = String(count || 0);
}

function fmtActionPill(action) {
    const labels = {
        'project.create': ['Project created', 'success'],
        'project.update': ['Project updated', 'info'],
        'project.rename': ['Project renamed', 'accent'],
        'project.move_folder': ['Project moved', 'accent'],
        'project.delete': ['Project deleted', 'error'],
        'folder.create': ['Folder created', 'success'],
        'folder.rename': ['Folder renamed', 'accent'],
        'folder.delete': ['Folder deleted', 'error'],
        'folder.ai_config_update': ['Auto analysis settings', 'info'],
        'folder.ai_config_delete': ['Auto analysis settings deleted', 'error'],
        'file.delete': ['File deleted', 'error'],
        'file.move': ['File moved', 'accent'],
        'slide.upload': ['Slide uploaded', 'success'],
        'slide.status_update': ['Slide status', 'info'],
        'user.login_success': ['Sign in', 'success'],
        'user.login_failed': ['Login failed', 'error'],
        'user.logout': ['Logout', 'neutral'],
        'slide.view': ['Slide viewed', 'info'],
        'ai.analyze': ['AI analysis', 'accent'],
    };
    const pair = labels[action] || [action || '-', 'neutral'];
    return `<span class="action-pill ${pair[1]}">${esc(pair[0])}</span>`;
}

function fmtActivityDetail(log) {
    if (log.str_action === 'slide.view') {
        const path = log.str_rel_path ? `${log.str_rel_path}/` : '';
        return `<strong>${esc(log.str_detail || '-')}</strong>` +
            (path ? `<br><small>${esc(path)}</small>` : '');
    }
    if (log.str_action === 'ai.analyze') {
        return `<strong>${esc(log.str_model || '')} - ${esc(log.str_variant || '')}</strong>` +
            (log.str_slide_filename ? `<br><small>${esc(log.str_slide_filename)}</small>` : '');
    }
    if ((log.str_action || '').startsWith('project.')
        || (log.str_action || '').startsWith('folder.')
        || (log.str_action || '').startsWith('file.')
        || log.str_action === 'slide.upload'
        || log.str_action === 'slide.status_update') {
        const bits = [];
        if (log.str_rel_path) bits.push(log.str_rel_path);
        if (log.str_src_path || log.str_dst_path) {
            bits.push(`${log.str_src_path || '-'} -> ${log.str_dst_path || '-'}`);
        }
        if (Array.isArray(log.list_filenames) && log.list_filenames.length) {
            bits.push(log.list_filenames.join(', '));
        }
        return `<strong>${esc(log.str_detail || '-')}</strong>` +
            (bits.length ? `<br><small>${esc(bits.join(' / '))}</small>` : '');
    }
    return esc(log.str_detail || '-');
}

document.querySelectorAll('.activity-cat-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.activity-cat-tab').forEach(item => item.classList.remove('active'));
        tab.classList.add('active');
        currentActivityCategory = tab.dataset.cat;
        userActivitySkip = 0;
        loadUserActivity();
    });
});

document.getElementById('btn-user-activity-close').addEventListener('click', () => {
    userActivityDialog.close();
});

function setStatusBadge(id, boolValue, trueLabel, falseLabel) {
    const badge = document.getElementById(id);
    if (!badge) return;
    badge.textContent = boolValue ? trueLabel : falseLabel;
    badge.className = `status-pill ${boolValue ? 'approved' : 'rejected'}`;
}

function setSettingsInputsDisabled(disabled) {
    document.getElementById('setting-ai-worker').disabled = disabled;
    document.getElementById('setting-tile-worker').disabled = disabled;
}

function renderSettings(data) {
    document.getElementById('setting-ai-worker').checked = !!data.bool_ai_worker_enabled;
    document.getElementById('setting-tile-worker').checked = !!data.bool_tile_worker_enabled;
    setStatusBadge(
        'setting-ai-worker-enabled',
        !!data.bool_ai_worker_enabled,
        'Enabled',
        'Disabled',
    );
    setStatusBadge(
        'setting-ai-worker-running',
        !!data.bool_ai_worker_running,
        'Running',
        'Stopped',
    );
    setStatusBadge(
        'setting-tile-worker-enabled',
        !!data.bool_tile_worker_enabled,
        'Enabled',
        'Disabled',
    );
    setStatusBadge(
        'setting-tile-worker-running',
        !!data.bool_tile_worker_running,
        'Running',
        'Stopped',
    );
}

async function loadSettings() {
    if (boolLoadingSettings) return;
    boolLoadingSettings = true;
    setSettingsInputsDisabled(true);
    try {
        const data = await apiGet('/admin/settings');
        if (!data) return;
        renderSettings(data);
    } catch (err) {
        showAlert(err.message, 'error');
    } finally {
        boolLoadingSettings = false;
        setSettingsInputsDisabled(false);
    }
}

async function saveWorkerSettings() {
    if (boolLoadingSettings) return;
    boolLoadingSettings = true;
    setSettingsInputsDisabled(true);
    try {
        const body = {
            bool_ai_worker_enabled: document.getElementById('setting-ai-worker').checked,
            bool_tile_worker_enabled: document.getElementById('setting-tile-worker').checked,
        };
        const data = await apiJson('/admin/settings/workers', 'PUT', body);
        if (!data) return;
        renderSettings(data);
        showAlert('Worker settings saved.', 'success');
    } catch (err) {
        showAlert(err.message, 'error');
        boolLoadingSettings = false;
        await loadSettings();
    } finally {
        boolLoadingSettings = false;
        setSettingsInputsDisabled(false);
    }
}

document.getElementById('btn-refresh-settings')?.addEventListener('click', loadSettings);
document.getElementById('setting-ai-worker')?.addEventListener('change', saveWorkerSettings);
document.getElementById('setting-tile-worker')?.addEventListener('change', saveWorkerSettings);

loadPending();
