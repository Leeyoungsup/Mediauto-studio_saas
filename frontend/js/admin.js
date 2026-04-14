// MeDICus Studio — 관리자 페이지 로직
// 단일 파일 스크립트 (모듈 X). localStorage access_token 사용.

const API_BASE = '/api';
const PAGE_LIMIT = 20;

// ─── 토큰/사용자 ───
const accessToken = localStorage.getItem('access_token');
const userRaw = localStorage.getItem('user');

if (!accessToken || !userRaw) {
    location.href = '/login.html';
}

let currentUser = null;
try { currentUser = JSON.parse(userRaw); } catch { currentUser = null; }

if (!currentUser || currentUser.str_role !== 'admin') {
    alert('관리자 권한이 필요합니다.');
    location.href = '/app.html';
}

document.getElementById('current-user-name').textContent = currentUser.str_name || currentUser.str_login_id;
document.getElementById('current-user-role').textContent = currentUser.str_role;

// ─── fetch 래퍼 ───
async function authFetch(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    headers['Authorization'] = `Bearer ${accessToken}`;
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401) {
        alert('세션이 만료되었습니다. 다시 로그인 해주세요.');
        localStorage.clear();
        location.href = '/login.html';
        return null;
    }
    if (res.status === 403) {
        const d = await res.json().catch(() => ({}));
        alert(d.detail || '권한이 없습니다.');
        location.href = '/app.html';
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

// ─── 알림 ───
const $alert = document.getElementById('admin-alert');
function showAlert(msg, type = 'success') {
    if (typeof msg === 'object') msg = JSON.stringify(msg);
    $alert.textContent = msg;
    $alert.className = `admin-alert ${type}`;
    $alert.hidden = false;
    setTimeout(() => { $alert.hidden = true; }, 4000);
}

// ─── 탭 ───
document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.admin-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab).classList.add('active');

        if (tab.dataset.tab === 'pending-panel') loadPending();
        else if (tab.dataset.tab === 'users-panel') loadUsers();
    });
});

// ─── 로그아웃 ───
document.getElementById('btn-logout').addEventListener('click', async () => {
    try { await authFetch('/auth/logout', { method: 'POST' }); } catch {}
    localStorage.clear();
    location.href = '/login.html';
});

// ─── 유틸 ───
function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return '—';
    return d.toLocaleString('ko-KR', { hour12: false });
}
function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// ═══════════════════════════════════════
// 승인 대기
// ═══════════════════════════════════════
async function loadPending() {
    const $tbody = document.getElementById('pending-tbody');
    $tbody.innerHTML = '<tr><td colspan="6" class="empty-row">로딩 중...</td></tr>';
    try {
        const data = await apiGet('/users/pending');
        if (!data) return;
        const list = data.list_pending || [];
        updatePendingBadge(list.length);
        if (list.length === 0) {
            $tbody.innerHTML = '<tr><td colspan="6" class="empty-row">승인 대기 중인 사용자가 없습니다.</td></tr>';
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
                    <button class="admin-btn-approve" data-approve="${u._id}">승인</button>
                    <button class="admin-btn-reject" data-reject="${u._id}">거부</button>
                </td>
            `;
            $tbody.appendChild(tr);
        }
    } catch (err) {
        showAlert(err.message, 'error');
        $tbody.innerHTML = '<tr><td colspan="6" class="empty-row">로드 실패</td></tr>';
    }
}

document.getElementById('pending-tbody').addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    if (btn.dataset.approve) {
        const userId = btn.dataset.approve;
        const role = document.querySelector(`[data-role-for="${userId}"]`).value;
        if (!confirm(`이 사용자를 ${role} 역할로 승인하시겠습니까?`)) return;
        try {
            await apiJson('/users/approve', 'POST', { str_user_id: userId, str_new_role: role });
            showAlert('승인 완료', 'success');
            loadPending();
        } catch (err) { showAlert(err.message, 'error'); }
    } else if (btn.dataset.reject) {
        const userId = btn.dataset.reject;
        const reason = prompt('거부 사유를 입력하세요 (선택):', '') || '';
        if (reason === null) return;
        if (!confirm('정말 이 가입 요청을 거부하시겠습니까?')) return;
        try {
            await apiJson('/users/reject', 'POST', { str_user_id: userId, str_reason: reason });
            showAlert('거부 처리 완료', 'success');
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
// 사용자 관리
// ═══════════════════════════════════════
let currentPage = 0;
let totalUsers = 0;
const userCache = new Map(); // id → user doc

async function loadUsers() {
    const $tbody = document.getElementById('users-tbody');
    $tbody.innerHTML = '<tr><td colspan="8" class="empty-row">로딩 중...</td></tr>';
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
            $tbody.innerHTML = '<tr><td colspan="8" class="empty-row">사용자가 없습니다.</td></tr>';
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
                <td><strong>${esc(u.str_login_id)}</strong>${isSelf ? ' <small>(나)</small>' : ''}</td>
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
                    <button class="admin-btn-secondary" data-edit="${u._id}">수정</button>
                    ${u.bool_is_locked ? `<button class="admin-btn-secondary" data-unlock="${u._id}">잠금해제</button>` : ''}
                    ${!isSelf ? `<button class="admin-btn-secondary" data-toggle-active="${u._id}" data-active="${u.bool_is_active ? '1' : '0'}">${u.bool_is_active ? '비활성화' : '활성화'}</button>` : ''}
                    ${!isSelf ? `<button class="admin-btn-danger" data-delete="${u._id}" data-login="${esc(u.str_login_id)}">삭제</button>` : ''}
                </td>
            `;
            $tbody.appendChild(tr);
        }
        updatePager();
    } catch (err) {
        showAlert(err.message, 'error');
        $tbody.innerHTML = '<tr><td colspan="8" class="empty-row">로드 실패</td></tr>';
    }
}

function updatePager() {
    const totalPages = Math.max(1, Math.ceil(totalUsers / PAGE_LIMIT));
    document.getElementById('page-info').textContent = `${currentPage + 1} / ${totalPages} (총 ${totalUsers}명)`;
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
        if (!confirm(`정말 사용자 '${login}' 을(를) 삭제하시겠습니까?`)) return;
        try {
            await apiDelete(`/users/delete/${btn.dataset.delete}`);
            showAlert('삭제 완료', 'success');
            loadUsers();
        } catch (err) { showAlert(err.message, 'error'); }
    } else if (btn.dataset.unlock) {
        try {
            const res = await authFetch(`/users/unlock/${btn.dataset.unlock}`, { method: 'POST' });
            if (res && res.ok) { showAlert('잠금 해제 완료', 'success'); loadUsers(); }
            else { const d = await res.json().catch(() => ({})); throw new Error(d.detail || '실패'); }
        } catch (err) { showAlert(err.message, 'error'); }
    } else if (btn.dataset.toggleActive !== undefined) {
        const nowActive = btn.dataset.active === '1';
        try {
            await apiJson('/users/toggle-active', 'POST', {
                str_user_id: btn.dataset.toggleActive,
                bool_is_active: !nowActive,
            });
            showAlert(nowActive ? '계정 비활성화' : '계정 활성화', 'success');
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
    if (!confirm(`역할을 ${newRole} 로 변경하시겠습니까?`)) {
        loadUsers();
        return;
    }
    try {
        await apiJson('/users/role', 'POST', { str_user_id: userId, str_new_role: newRole });
        showAlert('역할 변경 완료', 'success');
        loadUsers();
    } catch (err) {
        showAlert(err.message, 'error');
        loadUsers();
    }
});

// ─── 수정 다이얼로그 ───
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
        showAlert('수정 완료', 'success');
        $editDialog.close();
        loadUsers();
    } catch (err) {
        showAlert(err.message, 'error');
    }
});

// ═══════════════════════════════════════
// 사용자 생성
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
        showAlert(`생성 완료: ${data.str_login_id}`, 'success');
        e.target.reset();
    } catch (err) {
        showAlert(err.message, 'error');
    }
});

// ─── 초기 로드 ───
loadPending();
