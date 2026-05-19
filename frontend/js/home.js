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
        location.href = '/login';
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

    const $recentGrid = document.getElementById('recent-grid');
    const $projectDashboardCharts = document.getElementById('project-dashboard-charts');
    const $projectTableBody = document.getElementById('project-table-body');
    const $projectPager = document.getElementById('project-pager');
    const $projectPagePrev = document.getElementById('project-page-prev');
    const $projectPageNext = document.getElementById('project-page-next');
    const $projectPageInfo = document.getElementById('project-page-info');
    const $btnNewProject = document.getElementById('btn-new-project');
    const $btnRefreshProjects = document.getElementById('btn-refresh-projects');
    const $projectDialog = document.getElementById('project-dialog');
    const $projectDialogTitle = document.getElementById('project-dialog-title');
    const $projectDialogClose = document.getElementById('project-dialog-close');
    const $projectDialogCancel = document.getElementById('project-dialog-cancel');
    const $projectTitleInput = document.getElementById('project-title-input');
    const $projectInstitutionInput = document.getElementById('project-institution-input');
    const $projectDepartmentInput = document.getElementById('project-department-input');
    const $projectOwnerInput = document.getElementById('project-owner-input');
    const $projectStatusInput = document.getElementById('project-status-input');
    const $projectDueInput = document.getElementById('project-due-input');
    const $projectDescriptionInput = document.getElementById('project-description-input');
    const $projectAiEnabledInput = document.getElementById('project-ai-enabled-input');
    const $projectAiTaskList = document.getElementById('project-ai-task-list');
    const $projectMoveDialog = document.getElementById('project-move-dialog');
    const $projectMoveClose = document.getElementById('project-move-close');
    const $projectMoveCancel = document.getElementById('project-move-cancel');
    const $moveFolderSelect = document.getElementById('move-folder-select');
    const $moveProjectSelect = document.getElementById('move-project-select');
    const $projectOpenDialog = document.getElementById('project-open-dialog');
    const $projectOpenClose = document.getElementById('project-open-close');
    const $projectOpenTitle = document.getElementById('project-open-title');
    const $projectOpenAi = document.getElementById('project-open-ai');
    const $projectOpenOptions = document.querySelectorAll('[data-open-page]');

    let _projects = [];
    let _projectPage = 1;
    const PROJECT_PAGE_SIZE = 10;
    let _projectDialogMode = 'create';
    let _editingProjectPath = '';
    let _openingProjectPath = '';

    const PROJECT_AI_TASK_OPTIONS = [
        { model: 'Quanti HE', variant: 'Stomach', label: 'Quanti HE - Stomach' },
        { model: 'Quanti HE', variant: 'Breast', label: 'Quanti HE - Breast' },
        { model: 'Quanti HE', variant: 'Other', label: 'Quanti HE - Other' },
        { model: 'Quanti PD-L1', variant: 'Stomach', label: 'Quanti PD-L1 - Stomach (CPS)' },
        { model: 'Quanti PD-L1', variant: 'Lung', label: 'Quanti PD-L1 - Lung (TPS)' },
        { model: 'Quanti IHC', variant: 'HER2', label: 'Quanti IHC - HER2' },
        { model: 'Quanti IHC', variant: 'ER_PR', label: 'Quanti IHC - ER/PR (Allred)' },
        { model: 'Quanti IHC', variant: 'KI_67', label: 'Quanti IHC - KI-67' },
        { model: 'VS IHC', variant: 'ihc_membrane', label: 'VS IHC (Virtual Stain)', mpp: true },
    ];
    const PROJECT_VS_MPP_CHOICES = [
        { value: 4.0, label: '4.0 um/px (x2.5)' },
        { value: 2.0, label: '2.0 um/px (x5)' },
        { value: 1.0, label: '1.0 um/px (x10)' },
        { value: 0.5, label: '0.5 um/px (x20)' },
    ];
    const PROJECT_CHART_COLORS = [
        '#67b7dc', '#6794dc', '#6771dc', '#8067dc', '#a367dc',
        '#c767dc', '#dc67ce', '#dc67ab', '#dc6788', '#dc6967',
        '#dc8c67', '#dcb167',
    ];

    const IS_PROJECT_PAGE = location.pathname.replace(/\/+$/, '') === '/project';

    window.MediautoHeader?.render({
        active: IS_PROJECT_PAGE ? 'project' : 'home',
        user: currentUser,
        showAdmin: currentUser?.str_role === 'admin',
    });

    function canEditProjects() {
        return currentUser && currentUser.str_role !== 'viewer';
    }

    function canDeleteProjects() {
        return currentUser && currentUser.str_role === 'admin';
    }

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
    if (!canEditProjects() && $btnNewProject) {
        $btnNewProject.hidden = true;
    }

    // ── Auth fetch ──
    async function authFetch(path, options = {}) {
        const headers = { ...(options.headers || {}) };
        headers['Authorization'] = `Bearer ${accessToken}`;
        headers['X-Requested-With'] = 'XMLHttpRequest';
        const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (res.status === 401) {
            localStorage.clear();
            location.href = '/login';
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
        location.href = '/login';
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
        card.href = `/ai?slide=${encodeURIComponent(slide.filename)}&path=${encodeURIComponent(slide.rel_path || '')}`;

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

    function setProjectAiListEnabled(enabled) {
        if (!$projectAiTaskList) return;
        $projectAiTaskList.classList.toggle('disabled', !enabled);
        $projectAiTaskList.querySelectorAll('input').forEach(input => {
            input.disabled = !enabled;
        });
    }

    function renderProjectAiTasks(tasks = []) {
        if (!$projectAiTaskList) return;
        const selected = new Set();
        const vsMpps = {};
        for (const task of tasks || []) {
            if (task?.model === 'VS IHC') {
                if (!vsMpps[task.variant]) vsMpps[task.variant] = new Set();
                vsMpps[task.variant].add(Number(task.target_mpp ?? 2.0));
            } else if (task?.model && task?.variant) {
                selected.add(`${task.model}::${task.variant}`);
            }
        }
        $projectAiTaskList.innerHTML = '';
        for (const opt of PROJECT_AI_TASK_OPTIONS) {
            const wrap = document.createElement('div');
            wrap.className = 'project-ai-item';
            wrap.dataset.model = opt.model;
            wrap.dataset.variant = opt.variant;
            if (opt.mpp) {
                const current = vsMpps[opt.variant] || new Set();
                const isChecked = current.size > 0;
                wrap.innerHTML = `
                    <label class="project-ai-row">
                        <input type="checkbox" class="project-ai-parent"${isChecked ? ' checked' : ''}>
                        <span>${_esc(opt.label)}</span>
                    </label>
                    <div class="project-ai-sub"${isChecked ? '' : ' hidden'}>
                        ${PROJECT_VS_MPP_CHOICES.map(m => `
                            <label class="project-ai-sub-row">
                                <input type="checkbox" class="project-ai-mpp" data-mpp="${m.value}"${current.has(m.value) ? ' checked' : ''}>
                                <span>${_esc(m.label)}</span>
                            </label>
                        `).join('')}
                    </div>
                `;
                const parent = wrap.querySelector('.project-ai-parent');
                const sub = wrap.querySelector('.project-ai-sub');
                parent?.addEventListener('change', () => {
                    if (parent.checked) {
                        sub.hidden = false;
                        if (!wrap.querySelector('.project-ai-mpp:checked')) {
                            const def = wrap.querySelector('.project-ai-mpp[data-mpp="2"]');
                            if (def) def.checked = true;
                        }
                    } else {
                        sub.hidden = true;
                        wrap.querySelectorAll('.project-ai-mpp').forEach(cb => { cb.checked = false; });
                    }
                });
            } else {
                const key = `${opt.model}::${opt.variant}`;
                wrap.innerHTML = `
                    <label class="project-ai-row">
                        <input type="checkbox" class="project-ai-task" ${selected.has(key) ? ' checked' : ''}>
                        <span>${_esc(opt.label)}</span>
                    </label>
                `;
            }
            $projectAiTaskList.appendChild(wrap);
        }
        setProjectAiListEnabled(Boolean($projectAiEnabledInput?.checked));
    }

    function collectProjectAiTasks() {
        if (!$projectAiTaskList) return [];
        const tasks = [];
        $projectAiTaskList.querySelectorAll('.project-ai-item').forEach(wrap => {
            const model = wrap.dataset.model;
            const variant = wrap.dataset.variant;
            if (model === 'VS IHC') {
                const parent = wrap.querySelector('.project-ai-parent');
                if (!parent?.checked) return;
                wrap.querySelectorAll('.project-ai-mpp:checked').forEach(cb => {
                    tasks.push({ model, variant, target_mpp: parseFloat(cb.dataset.mpp) });
                });
            } else if (wrap.querySelector('.project-ai-task')?.checked) {
                tasks.push({ model, variant });
            }
        });
        return tasks;
    }

    function summarizeProjectAi(info) {
        if (!info?.project_ai_enabled) return '-';
        const tasks = Array.isArray(info.project_ai_tasks) ? info.project_ai_tasks : [];
        if (!tasks.length) return '<span class="project-ai-badge muted">Enabled, empty</span>';
        const labels = tasks.map(task => {
            const opt = PROJECT_AI_TASK_OPTIONS.find(item => item.model === task?.model && item.variant === task?.variant);
            const modelClass = projectAiModelClass(task?.model);
            if (task?.model === 'VS IHC' && task.target_mpp != null) {
                const mpp = PROJECT_VS_MPP_CHOICES.find(item => Number(item.value) === Number(task.target_mpp));
                return {
                    label: `${opt?.label || 'VS IHC'}${mpp ? ` ${mpp.label}` : ''}`,
                    cls: modelClass,
                };
            }
            return {
                label: opt?.label || [task?.model, task?.variant].filter(Boolean).join(' - '),
                cls: modelClass,
            };
        }).filter(item => item.label);
        return `<div class="project-ai-list">${labels.map(item => `<span class="project-ai-chip ${item.cls}">${_esc(item.label)}</span>`).join('')}</div>`;
    }

    function projectAiModelClass(model) {
        if (model === 'Quanti HE') return 'model-he';
        if (model === 'Quanti PD-L1') return 'model-pdl1';
        if (model === 'Quanti IHC') return 'model-ihc';
        if (model === 'VS IHC') return 'model-vs';
        return 'model-default';
    }

    function projectDisplayName(project) {
        const info = project?.info || {};
        return info.title || project?.name || project?.path || 'Untitled';
    }

    function normalizeChartEntries(items, maxItems = 10) {
        const total = items.reduce((sum, item) => sum + item.value, 0);
        const sorted = items
            .filter(item => item.value > 0)
            .sort((a, b) => b.value - a.value);
        if (sorted.length <= maxItems) return { entries: sorted, total };
        const head = sorted.slice(0, maxItems - 1);
        const otherValue = sorted.slice(maxItems - 1).reduce((sum, item) => sum + item.value, 0);
        return { entries: [...head, { name: 'Others', value: otherValue }], total };
    }

    function renderDonutSegments(entries, total) {
        if (!total || !entries.length) return '';
        let cursor = 0;
        return entries.map((entry, index) => {
            const start = cursor;
            const share = (entry.value / total) * 100;
            const end = cursor + share;
            cursor = end;
            const color = PROJECT_CHART_COLORS[index % PROJECT_CHART_COLORS.length];
            const tooltip = `${entry.name} ${entry.value.toLocaleString()} slides (${share.toFixed(1)}%)`;
            return `
                <circle
                    class="project-donut-segment"
                    cx="120"
                    cy="120"
                    r="84"
                    pathLength="100"
                    fill="none"
                    stroke="${color}"
                    stroke-width="46"
                    stroke-dasharray="${share.toFixed(3)} ${Math.max(0, 100 - share).toFixed(3)}"
                    stroke-dashoffset="${(-start).toFixed(3)}"
                    data-color="${_esc(color)}"
                    data-tooltip="${_esc(tooltip)}"
                    aria-label="${_esc(tooltip)}"
                    tabindex="0"
                ></circle>
            `;
        }).join('');
    }

    function readableTextColor(hexColor) {
        const hex = String(hexColor || '').replace('#', '');
        if (!/^[0-9a-f]{6}$/i.test(hex)) return '#07142d';
        const r = parseInt(hex.slice(0, 2), 16);
        const g = parseInt(hex.slice(2, 4), 16);
        const b = parseInt(hex.slice(4, 6), 16);
        const luminance = (0.299 * r + 0.587 * g + 0.114 * b);
        return luminance > 150 ? '#07142d' : '#ffffff';
    }

    function renderDistributionChart(title, items) {
        const { entries, total } = normalizeChartEntries(items);
        if (!total) {
            return `
                <article class="project-chart-card">
                    <h3 class="project-chart-title">${_esc(title)}</h3>
                    <div class="project-chart-empty">No slide data yet</div>
                </article>
            `;
        }
        return `
            <article class="project-chart-card">
                <h3 class="project-chart-title">${_esc(title)}</h3>
                <div class="project-donut">
                    <svg class="project-donut-svg" viewBox="0 0 240 240" role="img" aria-label="${_esc(title)} distribution">
                        <circle class="project-donut-track" cx="120" cy="120" r="84" pathLength="100"></circle>
                        <g transform="rotate(-90 120 120)">
                            ${renderDonutSegments(entries, total)}
                        </g>
                    </svg>
                    <div class="project-donut-center">
                        <span class="project-donut-label">total</span>
                        <span class="project-donut-value">${total.toLocaleString()}</span>
                    </div>
                </div>
                <div class="project-chart-tooltip" role="status"></div>
                <div class="project-chart-legend">
                    ${entries.map((entry, index) => {
                        const pct = total ? (entry.value / total) * 100 : 0;
                        const color = PROJECT_CHART_COLORS[index % PROJECT_CHART_COLORS.length];
                        return `
                            <div class="project-chart-legend-item" title="${_esc(entry.name)}: ${entry.value} slides (${pct.toFixed(1)}%)">
                                <span class="project-chart-swatch" style="background:${color}"></span>
                                <span class="project-chart-name">${_esc(entry.name)}</span>
                                <span class="project-chart-value">${entry.value.toLocaleString()} (${pct.toFixed(1)}%)</span>
                            </div>
                        `;
                    }).join('')}
                </div>
            </article>
        `;
    }

    function bindProjectChartTooltips() {
        if (!$projectDashboardCharts) return;
        $projectDashboardCharts.querySelectorAll('.project-chart-card').forEach(card => {
            const tooltip = card.querySelector('.project-chart-tooltip');
            if (!tooltip) return;

            const showTooltip = (target, event) => {
                const text = target.dataset.tooltip;
                if (!text) return;
                tooltip.textContent = text;
                const color = target.dataset.color || '#7fa8ed';
                tooltip.style.setProperty('--tooltip-bg', color);
                tooltip.style.setProperty('--tooltip-fg', readableTextColor(color));
                tooltip.classList.add('visible');
                const rect = card.getBoundingClientRect();
                const pointer = Number.isFinite(event?.clientX)
                    ? event
                    : { clientX: rect.left + 130, clientY: rect.top + 130 };
                moveTooltip(pointer);
            };
            const moveTooltip = (event) => {
                const rect = card.getBoundingClientRect();
                const x = Math.min(Math.max(event.clientX - rect.left + 14, 12), rect.width - tooltip.offsetWidth - 12);
                const y = Math.min(Math.max(event.clientY - rect.top - 42, 12), rect.height - tooltip.offsetHeight - 12);
                tooltip.style.left = `${x}px`;
                tooltip.style.top = `${y}px`;
            };
            const hideTooltip = () => {
                tooltip.classList.remove('visible');
            };

            card.querySelectorAll('.project-donut-segment').forEach(segment => {
                segment.addEventListener('mouseenter', event => showTooltip(segment, event));
                segment.addEventListener('mousemove', moveTooltip);
                segment.addEventListener('mouseleave', hideTooltip);
                segment.addEventListener('focus', event => showTooltip(segment, event));
                segment.addEventListener('blur', hideTooltip);
            });
        });
    }

    function renderProjectDashboardCharts(projects = []) {
        if (!$projectDashboardCharts) return;
        const projectItems = projects.map(project => ({
            name: projectDisplayName(project),
            value: Number(project.slide_count || 0),
        }));
        const hospitalMap = new Map();
        for (const project of projects) {
            const info = project.info || {};
            const hospital = String(info.institution || 'Unspecified').trim() || 'Unspecified';
            hospitalMap.set(hospital, (hospitalMap.get(hospital) || 0) + Number(project.slide_count || 0));
        }
        const hospitalItems = [...hospitalMap.entries()].map(([name, value]) => ({ name, value }));
        if (!projectItems.some(item => item.value > 0) && !hospitalItems.some(item => item.value > 0)) {
            $projectDashboardCharts.innerHTML = '<div class="project-chart-empty">No project slide data yet</div>';
            return;
        }
        $projectDashboardCharts.innerHTML = [
            renderDistributionChart('Slides By Project', projectItems),
            renderDistributionChart('Slides By Hospital', hospitalItems),
        ].join('');
        bindProjectChartTooltips();
    }

    function projectInfoPayload() {
        return {
            title: $projectTitleInput.value.trim(),
            institution: $projectInstitutionInput.value.trim(),
            department: $projectDepartmentInput.value.trim(),
            owner: $projectOwnerInput.value.trim(),
            status: $projectStatusInput.value,
            due_date: $projectDueInput.value,
            description: $projectDescriptionInput.value.trim(),
            project_ai_enabled: Boolean($projectAiEnabledInput?.checked),
            project_ai_tasks_json: JSON.stringify(collectProjectAiTasks()),
        };
    }

    function makeInternalProjectName(title) {
        const base = (title || '')
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9_-]+/g, '_')
            .replace(/^_+|_+$/g, '')
            .slice(0, 40) || 'project';
        return `${base}_${Date.now().toString(36)}`;
    }

    async function postForm(path, fields) {
        const form = new FormData();
        for (const [key, value] of Object.entries(fields)) {
            form.append(key, value == null ? '' : String(value));
        }
        const res = await authFetch(path, { method: 'POST', body: form });
        if (!res || !res.ok) throw new Error(res ? await res.text() : 'Request failed');
        return res.json();
    }

    function openProjectDialog(mode, project = null) {
        if (!$projectDialog) return;
        _projectDialogMode = mode;
        _editingProjectPath = project ? project.path : '';
        const info = project?.info || {};
        $projectDialogTitle.textContent = mode === 'create' ? 'New Project' : 'Project Information';
        $projectTitleInput.value = info.title || project?.name || '';
        $projectInstitutionInput.value = info.institution || '';
        $projectDepartmentInput.value = info.department || '';
        $projectOwnerInput.value = info.owner || '';
        $projectStatusInput.value = info.status || 'active';
        $projectDueInput.value = info.due_date || '';
        $projectDescriptionInput.value = info.description || '';
        if ($projectAiEnabledInput) {
            $projectAiEnabledInput.checked = Boolean(info.project_ai_enabled);
        }
        renderProjectAiTasks(info.project_ai_tasks || []);
        $projectDialog.showModal();
    }

    function closeProjectDialog() {
        if ($projectDialog?.open) $projectDialog.close();
    }

    function closeProjectOpenDialog() {
        if ($projectOpenDialog?.open) $projectOpenDialog.close();
    }

    function openProjectRouteDialog(project) {
        const projectPath = project?.path || project?.name || '';
        if (!projectPath) return;
        const info = project.info || {};
        _openingProjectPath = projectPath;
        if ($projectOpenTitle) {
            $projectOpenTitle.textContent = info.title || project.name || projectPath;
        }
        if ($projectOpenDialog?.showModal) $projectOpenDialog.showModal();
        else location.href = `/ai?path=${encodeURIComponent(projectPath)}`;
    }

    function openSelectedProjectRoute(page) {
        if (!_openingProjectPath) return;
        closeProjectOpenDialog();
        location.href = `/${page}?path=${encodeURIComponent(_openingProjectPath)}`;
    }

    async function saveProjectDialog() {
        const payload = projectInfoPayload();
        if (!payload.title) throw new Error('Project title is required.');
        if (_projectDialogMode === 'create') {
            await postForm('/slides/project/create', {
                name: makeInternalProjectName(payload.title),
                ...payload,
            });
        } else {
            await postForm('/slides/project/update', {
                name: _editingProjectPath,
                ...payload,
            });
        }
        closeProjectDialog();
        await loadFolderTree();
    }

    async function deleteProject(project) {
        if (!confirm(`Delete empty project "${project.name}"?`)) return;
        await postForm('/slides/project/delete', { name: project.name });
        await loadFolderTree();
    }

    async function openMoveFolderDialog(project) {
        if (!$projectMoveDialog) return;
        const res = await authFetch('/slides/folder-tree');
        if (!res || !res.ok) throw new Error('Failed to load folders');
        const data = await res.json();
        const folders = (data.folders || []).filter(f => f.includes('/'));
        $moveFolderSelect.innerHTML = '';
        $moveProjectSelect.innerHTML = '';
        for (const folder of folders) {
            const opt = document.createElement('option');
            opt.value = folder;
            opt.textContent = '/' + folder;
            if (folder.startsWith(project.path + '/')) opt.selected = true;
            $moveFolderSelect.appendChild(opt);
        }
        for (const p of _projects) {
            const opt = document.createElement('option');
            opt.value = p.path;
            opt.textContent = p.name;
            if (p.path !== project.path) $moveProjectSelect.appendChild(opt);
        }
        if (!$moveFolderSelect.options.length || !$moveProjectSelect.options.length) {
            alert('Movable folders or target projects are not available.');
            return;
        }
        $projectMoveDialog.showModal();
    }

    async function saveMoveFolderDialog() {
        await postForm('/slides/project/move-folder', {
            src_path: $moveFolderSelect.value,
            dst_project: $moveProjectSelect.value,
        });
        if ($projectMoveDialog?.open) $projectMoveDialog.close();
        await loadFolderTree();
    }

    // ── Load dashboard ──
    async function loadDashboard() {
        try {
            const res = await authFetch('/slides/dashboard');
            if (!res) return;
            const data = await res.json();

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
    function renderProjects(projects) {
        renderProjectDashboardCharts(projects);
        if (!$projectTableBody) return;
        $projectTableBody.innerHTML = '';
        if (!projects.length) {
            $projectTableBody.innerHTML = '<tr><td colspan="7" class="project-empty">No projects yet</td></tr>';
            if ($projectPager) $projectPager.hidden = true;
            return;
        }
        const totalPages = Math.max(1, Math.ceil(projects.length / PROJECT_PAGE_SIZE));
        _projectPage = Math.min(Math.max(_projectPage, 1), totalPages);
        const start = (_projectPage - 1) * PROJECT_PAGE_SIZE;
        const pagedProjects = projects.slice(start, start + PROJECT_PAGE_SIZE);
        if ($projectPager) $projectPager.hidden = projects.length <= PROJECT_PAGE_SIZE;
        if ($projectPageInfo) $projectPageInfo.textContent = `${_projectPage} / ${totalPages}`;
        if ($projectPagePrev) $projectPagePrev.disabled = _projectPage <= 1;
        if ($projectPageNext) $projectPageNext.disabled = _projectPage >= totalPages;
        for (const project of pagedProjects) {
            const info = project.info || {};
            const projectPath = project.path || project.name;
            const tr = document.createElement('tr');
            const subtitle = info.description
                ? `<span class="project-subtitle">${_esc(info.description)}</span>`
                : '';
            tr.innerHTML = `
                <td><div class="project-title">
                    <a href="/ai?path=${encodeURIComponent(projectPath)}" class="project-open-link">${_esc(info.title || project.name)}</a>
                    ${subtitle}
                </div></td>
                <td>${_esc(info.institution || '-')}</td>
                <td>${_esc(info.owner || '-')}</td>
                <td><span class="project-status">${_esc(info.status || 'active')}</span></td>
                <td>${project.slide_count || 0}</td>
                <td>${summarizeProjectAi(info)}</td>
                <td><div class="project-actions-cell"></div></td>
            `;
            tr.querySelector('.project-open-link')?.addEventListener('click', (e) => {
                e.preventDefault();
                openProjectRouteDialog(project);
            });
            const actions = tr.querySelector('.project-actions-cell');
            const openBtn = document.createElement('button');
            openBtn.className = 'project-mini-btn';
            openBtn.textContent = 'Open';
            openBtn.addEventListener('click', () => openProjectRouteDialog(project));
            actions.appendChild(openBtn);
            if (canEditProjects()) {
                const editBtn = document.createElement('button');
                editBtn.className = 'project-mini-btn';
                editBtn.textContent = 'Info';
                editBtn.addEventListener('click', () => openProjectDialog('edit', project));
                actions.appendChild(editBtn);
            }
            if (canDeleteProjects()) {
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'project-mini-btn danger';
                deleteBtn.textContent = 'Delete';
                deleteBtn.addEventListener('click', () => deleteProject(project).catch(err => alert(err.message)));
                actions.appendChild(deleteBtn);
            }
            $projectTableBody.appendChild(tr);
        }
    }

    async function loadFolderTree() {
        const $tree = document.getElementById('folder-tree');
        try {
            const res = await authFetch('/slides/projects');
            if (!res) return;
            const data = await res.json();
            _projects = data.projects || [];
            renderProjects(_projects);
            if (!$tree) return;
            $tree.innerHTML = '';

            const folders = _projects;

            if (folders.length === 0) {
                $tree.innerHTML = '<div class="folder-tree-empty">No projects yet</div>';
                return;
            }

            for (const folder of folders) {
                const el = document.createElement('a');
                el.className = 'folder-tree-item';
                el.href = `/ai?path=${encodeURIComponent(folder.path || folder.name)}`;
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
            if ($projectTableBody) {
                $projectTableBody.innerHTML = '<tr><td colspan="7" class="project-empty">Failed to load projects</td></tr>';
            }
            if ($tree) $tree.innerHTML = '<div class="folder-tree-empty">Failed to load projects</div>';
        }
    }

    // ── 업로드 팝업 완료 시 대시보드 새로고침 ──
    window.addEventListener('message', (e) => {
        if (e.data && e.data.type === 'upload-complete') {
            loadDashboard();
            loadFolderTree();
        }
    });

    $btnRefreshProjects?.addEventListener('click', () => loadFolderTree());
    $projectAiEnabledInput?.addEventListener('change', () => {
        setProjectAiListEnabled($projectAiEnabledInput.checked);
    });
    $projectPagePrev?.addEventListener('click', () => {
        if (_projectPage <= 1) return;
        _projectPage -= 1;
        renderProjects(_projects);
    });
    $projectPageNext?.addEventListener('click', () => {
        const totalPages = Math.max(1, Math.ceil(_projects.length / PROJECT_PAGE_SIZE));
        if (_projectPage >= totalPages) return;
        _projectPage += 1;
        renderProjects(_projects);
    });
    $btnNewProject?.addEventListener('click', () => openProjectDialog('create'));
    $projectDialogClose?.addEventListener('click', closeProjectDialog);
    $projectDialogCancel?.addEventListener('click', closeProjectDialog);
    $projectDialog?.addEventListener('submit', (e) => {
        e.preventDefault();
        saveProjectDialog().catch(err => alert(err.message));
    });
    $projectMoveClose?.addEventListener('click', () => { if ($projectMoveDialog?.open) $projectMoveDialog.close(); });
    $projectMoveCancel?.addEventListener('click', () => { if ($projectMoveDialog?.open) $projectMoveDialog.close(); });
    $projectMoveDialog?.addEventListener('submit', (e) => {
        e.preventDefault();
        saveMoveFolderDialog().catch(err => alert(err.message));
    });
    $projectOpenClose?.addEventListener('click', closeProjectOpenDialog);
    $projectOpenAi?.addEventListener('click', () => openSelectedProjectRoute('ai'));
    $projectOpenOptions.forEach(button => {
        button.addEventListener('click', () => openSelectedProjectRoute(button.dataset.openPage));
    });

    loadFolderTree();
    loadDashboard();
})();
