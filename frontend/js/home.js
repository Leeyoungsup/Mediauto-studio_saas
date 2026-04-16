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
    const $statFolders = document.getElementById('stat-folders');
    const $statStorage = document.getElementById('stat-storage');
    const $statStorageLabel = document.getElementById('stat-storage-label');
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
        const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (res.status === 401) {
            localStorage.clear();
            location.href = '/login.html';
            return null;
        }
        return res;
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

    // ── AI badge mapping ──
    const AI_BADGE_MAP = {
        'HE-Fit':      { cls: 'badge-hefit',   label: 'HE-Fit' },
        'PD-Score':     { cls: 'badge-pdscore', label: 'PD-Score' },
        'Precise-IHC':  { cls: 'badge-ihc',     label: 'IHC' },
        'VS-IHC':       { cls: 'badge-vs',      label: 'VS' },
    };

    // ── Status badge ──
    function statusBadge(status) {
        if (!status) return '';
        const labels = {
            done: 'Done', in_progress: 'In Progress',
            pending: 'Pending', flagged: 'Flagged',
        };
        return `<span class="badge-status badge-status-${status}">${labels[status] || status}</span>`;
    }

    // ── Render recent slide card ──
    function renderRecentCard(slide) {
        const card = document.createElement('a');
        card.className = 'recent-card';
        card.href = `/app.html?slide=${encodeURIComponent(slide.filename)}&path=${encodeURIComponent(slide.rel_path || '')}`;

        const aiBadges = (slide.ai_done || [])
            .map(k => {
                const b = AI_BADGE_MAP[k];
                return b ? `<span class="recent-card-badge ${b.cls}">${b.label}</span>` : '';
            })
            .join('');

        card.innerHTML = `
            <div class="recent-card-top">
                <div class="recent-card-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2"/>
                        <circle cx="8.5" cy="8.5" r="1.5"/>
                        <path d="M21 15l-5-5L5 21"/>
                    </svg>
                </div>
                <div class="recent-card-info">
                    <div class="recent-card-name" title="${slide.filename}">${slide.filename}</div>
                    <div class="recent-card-path">${slide.rel_path || 'Root'} · ${formatSize(slide.size_bytes)}</div>
                </div>
            </div>
            <div class="recent-card-meta">
                ${statusBadge(slide.status)}
                ${aiBadges}
                <span style="margin-left:auto">${formatTimeAgo(slide.last_opened_at)}</span>
            </div>
        `;
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
            // 전체 슬라이드 중 하나라도 AI 결과가 있는 수 → 가장 많은 모델 수 기준 대략값
            const aiTotal = Math.max(ac['HE-Fit'] || 0, ac['PD-Score'] || 0, ac['Precise-IHC'] || 0, ac['VS-IHC'] || 0);
            $statAiTotal.textContent = aiTotal;

            // AI overview bars
            const total = data.total_slides || 1;
            const barMap = {
                'ai-bar-hefit':  ac['HE-Fit'] || 0,
                'ai-bar-pdscore': ac['PD-Score'] || 0,
                'ai-bar-ihc':    ac['Precise-IHC'] || 0,
                'ai-bar-vs':     ac['VS-IHC'] || 0,
            };
            for (const [id, count] of Object.entries(barMap)) {
                const el = document.getElementById(id);
                if (!el) continue;
                const fill = el.querySelector('.ai-bar-fill');
                const countEl = el.querySelector('.ai-bar-count');
                const pct = Math.min(100, (count / total) * 100);
                fill.style.width = pct + '%';
                countEl.textContent = count + ' / ' + data.total_slides;
            }

            // Recent slides
            $recentGrid.innerHTML = '';
            if (!data.recent_slides || data.recent_slides.length === 0) {
                $recentGrid.innerHTML = '<div class="recent-empty">No recently opened slides</div>';
            } else {
                for (const slide of data.recent_slides) {
                    $recentGrid.appendChild(renderRecentCard(slide));
                }
            }
        } catch (err) {
            console.error('[Dashboard]', err);
            $recentGrid.innerHTML = '<div class="recent-empty">Failed to load dashboard data</div>';
        }
    }

    loadDashboard();
})();
