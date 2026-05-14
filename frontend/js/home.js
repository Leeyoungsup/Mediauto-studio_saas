/**
 * MeDIAuto Studio — Dashboard Home
 */
(function () {
    'use strict';

    const API_BASE = '/api';
    const accessToken = localStorage.getItem('access_token');
    const userRaw = localStorage.getItem('user');

    // 미로그인 → 로그인 페이지
    if (!accessToken) {
        location.href = '/login.html';
        return;
    }

    let currentUser = null;
    try { currentUser = JSON.parse(userRaw); } catch { /* ignore */ }

    // ── DOM refs ──
    const $userName = document.getElementById('user-name');
    const $userRole = document.getElementById('user-role');
    const $btnAdmin = document.getElementById('btn-admin');
    const $btnLogout = document.getElementById('btn-logout');
    const $quickAdmin = document.getElementById('quick-admin');

    const $statTotal = document.getElementById('stat-total');
    const $statDone = document.getElementById('stat-done');
    const $statInProgress = document.getElementById('stat-in-progress');
    const $statAiTotal = document.getElementById('stat-ai-total');

    const $recentGrid = document.getElementById('recent-grid');

    // ── User info ──
    if (currentUser) {
        $userName.textContent = currentUser.str_name || currentUser.str_login_id || '—';
        $userRole.textContent = currentUser.str_role || '—';
    }
    // admin 전용 UI
    if (currentUser && currentUser.str_role === 'admin') {
        $btnAdmin.hidden = false;
    } else {
        if ($quickAdmin) $quickAdmin.style.display = 'none';
    }

    // viewer 역할은 업로드 버튼 숨기기
    if (currentUser && currentUser.str_role === 'viewer') {
        const $quickUpload = document.getElementById('quick-upload');
        if ($quickUpload) $quickUpload.style.display = 'none';
    }

    // ── Auth fetch ──
    async function authFetch(path, options = {}) {
        const headers = { ...(options.headers || {}) };
        headers['Authorization'] = `Bearer ${accessToken}`;
        headers['X-Requested-With'] = 'XMLHttpRequest';
        const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (res.status === 401) {
            localStorage.clear();
            location.href = '/login.html';
            return null;
        }
        return res;
    }

    // ── Media ticket (썸네일용) ──
    let _mediaTicket = null;
    async function getMediaTicket() {
        if (_mediaTicket && _mediaTicket.int_exp - Math.floor(Date.now() / 1000) > 30) {
            return _mediaTicket.str_token;
        }
        try {
            const res = await authFetch('/auth/media-ticket');
            if (res) _mediaTicket = await res.json();
            return _mediaTicket ? _mediaTicket.str_token : '';
        } catch { return ''; }
    }

    // ── Logout ──
    $btnLogout.addEventListener('click', async () => {
        try {
            await authFetch('/auth/logout', { method: 'POST' });
        } catch { /* ignore */ }
        localStorage.clear();
        location.href = '/login.html';
    });

    // ── Time formatting ──
    function formatTimeAgo(isoStr) {
        if (!isoStr) return '';
        const dt = new Date(isoStr);
        const diff = Date.now() - dt.getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 30) return `${days}d ago`;
        return dt.toLocaleDateString('ko-KR');
    }

    function formatSize(bytes) {
        if (!bytes) return '';
        const mb = bytes / (1024 * 1024);
        if (mb >= 1024) return (mb / 1024).toFixed(1) + ' GB';
        return mb.toFixed(1) + ' MB';
    }

    function formatStorageShort(bytes) {
        if (!bytes) return '0 B';
        const gb = bytes / (1024 * 1024 * 1024);
        if (gb >= 1024) return (gb / 1024).toFixed(1) + ' TB';
        if (gb >= 1) return gb.toFixed(1) + ' GB';
        const mb = bytes / (1024 * 1024);
        return mb.toFixed(0) + ' MB';
    }

    // ── AI badge mapping ──
    const AI_BADGE_MAP = {
        'Quanti HE':      { cls: 'badge-hefit',   label: 'Quanti HE' },
        'Quanti PD-L1':     { cls: 'badge-pdscore', label: 'Quanti PD-L1' },
        'Quanti IHC':  { cls: 'badge-ihc',     label: 'IHC' },
        'VS IHC':       { cls: 'badge-vs',      label: 'VS' },
    };

    // ── Status badge ──
    function statusBadge(status) {
        if (!status) return '';
        const labels = {
            done: 'Done', in_progress: 'In Progress',
            pending: 'Pending', flagged: 'Flagged',
        };
        if (!Object.prototype.hasOwnProperty.call(labels, status)) return '';
        return `<span class="badge-status badge-status-${status}">${labels[status]}</span>`;
    }

    // HTML 이스케이프 — innerHTML 에 들어갈 신뢰 불가능한 문자열 (filename, rel_path 등)
    function _esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // ── Render recent slide card ──
    function _buildThumbUrl(filename, relPath, token) {
        return `/api/slides/thumbnail-by-name?filename=${encodeURIComponent(filename)}&path=${encodeURIComponent(relPath || '')}&size=200&mt=${token}`;
    }

    function renderRecentCard(slide, mediaToken) {
        const card = document.createElement('a');
        card.className = 'recent-card';
        card.href = `/app.html?slide=${encodeURIComponent(slide.filename)}&path=${encodeURIComponent(slide.rel_path || '')}`;

        const thumbUrl = _buildThumbUrl(slide.filename, slide.rel_path, mediaToken);

        const aiBadges = (slide.ai_done || [])
            .map(k => {
                const b = AI_BADGE_MAP[k];
                return b ? `<span class="recent-card-badge ${b.cls}">${_esc(b.label)}</span>` : '';
            })
            .join('');

        // 사용자가 업로드한 파일명/폴더명은 신뢰 불가 — 항상 _esc 통과시킨다.
        card.innerHTML = `
            <div class="recent-card-thumb">
                <img src="${thumbUrl}" alt="" loading="lazy">
            </div>
            <div class="recent-card-body">
                <div class="recent-card-name" title="${_esc(slide.filename)}">${_esc(slide.filename)}</div>
                <div class="recent-card-path">${_esc(slide.rel_path || 'Root')} · ${formatSize(slide.size_bytes)}</div>
            </div>
            <div class="recent-card-meta">
                ${statusBadge(slide.status)}
                ${aiBadges}
                <span style="margin-left:auto">${formatTimeAgo(slide.last_opened_at)}</span>
            </div>
        `;

        // 페이지를 오래 열어두면 mediaToken 이 만료(10분)되어 lazy-load / 캐시 미스 fetch 가
        // 401 로 떨어진다. 첫 error 에서 새 티켓으로 1회 재시도.
        const img = card.querySelector('img');
        if (img) {
            let bool_retried = false;
            img.addEventListener('error', async () => {
                if (bool_retried) return;
                bool_retried = true;
                const str_new_token = await getMediaTicket();
                if (str_new_token && str_new_token !== mediaToken) {
                    img.src = _buildThumbUrl(slide.filename, slide.rel_path, str_new_token);
                }
            });
        }
        return card;
    }

    // ── Load dashboard ──
    async function loadDashboard() {
        try {
            const res = await authFetch('/slides/dashboard');
            if (!res) return;
            const data = await res.json();

            // Stat cards
            $statTotal.textContent = data.total_slides || 0;
            const sc = data.status_counts || {};
            $statDone.textContent = sc.done || 0;
            $statInProgress.textContent = (sc.in_progress || 0) + (sc.pending || 0);

            // AI total (unique slides with any AI result)
            const ac = data.ai_counts || {};
            const aiTotal = Math.max(ac['Quanti HE'] || 0, ac['Quanti PD-L1'] || 0, ac['Quanti IHC'] || 0, ac['VS IHC'] || 0);
            $statAiTotal.textContent = aiTotal;

            // Storage bar
            const usedBytes = data.storage_used_bytes || 0;
            const totalBytes = data.storage_total_bytes || 1;
            const storagePct = Math.min(100, (usedBytes / totalBytes) * 100);
            const $storageFill = document.getElementById('storage-bar-fill');
            const $storageUsed = document.getElementById('storage-used');
            const $storageTotal = document.getElementById('storage-total');
            const $storagePct = document.getElementById('storage-pct');
            if ($storageFill) $storageFill.style.width = storagePct + '%';
            if ($storageUsed) $storageUsed.textContent = formatStorageShort(usedBytes);
            if ($storageTotal) $storageTotal.textContent = formatStorageShort(totalBytes);
            if ($storagePct) $storagePct.textContent = `(${storagePct.toFixed(1)}%)`;

            // Folder tree
            loadFolderTree();

            // Recent slides
            $recentGrid.innerHTML = '';
            if (!data.recent_slides || data.recent_slides.length === 0) {
                $recentGrid.innerHTML = '<div class="recent-empty">No recently opened slides</div>';
            } else {
                const mt = await getMediaTicket();
                for (const slide of data.recent_slides) {
                    $recentGrid.appendChild(renderRecentCard(slide, mt));
                }
            }
        } catch (err) {
            console.error('[Dashboard]', err);
            $recentGrid.innerHTML = '<div class="recent-empty">Failed to load dashboard data</div>';
        }
    }

    // ── Load folder tree (root level) ──
    async function loadFolderTree() {
        const $tree = document.getElementById('folder-tree');
        if (!$tree) return;
        try {
            const res = await authFetch('/slides/projects');
            if (!res) return;
            const data = await res.json();
            $tree.innerHTML = '';

            const folders = data.projects || [];

            if (folders.length === 0) {
                $tree.innerHTML = '<div class="folder-tree-empty">No projects yet</div>';
                return;
            }

            for (const folder of folders) {
                const el = document.createElement('a');
                el.className = 'folder-tree-item';
                el.href = `/app.html?path=${encodeURIComponent(folder.path || folder.name)}`;
                el.innerHTML = `
                    <div class="folder-tree-icon">
                        <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
                            <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/>
                        </svg>
                    </div>
                    <span class="folder-tree-name">${_esc(folder.name)}</span>
                    <span class="folder-tree-count">${folder.slide_count || 0} slides</span>
                `;
                $tree.appendChild(el);
            }

        } catch {
            $tree.innerHTML = '<div class="folder-tree-empty">Failed to load projects</div>';
        }
    }

    // ── 업로드 팝업 완료 시 대시보드 새로고침 ──
    window.addEventListener('message', (e) => {
        if (e.data && e.data.type === 'upload-complete') {
            loadDashboard();
        }
    });

    loadDashboard();
})();
