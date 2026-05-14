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
    const $projectTableBody = document.getElementById('project-table-body');
    const $btnNewProject = document.getElementById('btn-new-project');
    const $btnRefreshProjects = document.getElementById('btn-refresh-projects');
    const $projectDialog = document.getElementById('project-dialog');
    const $projectDialogTitle = document.getElementById('project-dialog-title');
    const $projectDialogClose = document.getElementById('project-dialog-close');
    const $projectDialogCancel = document.getElementById('project-dialog-cancel');
    const $projectNameInput = document.getElementById('project-name-input');
    const $projectTitleInput = document.getElementById('project-title-input');
    const $projectInstitutionInput = document.getElementById('project-institution-input');
    const $projectDepartmentInput = document.getElementById('project-department-input');
    const $projectOwnerInput = document.getElementById('project-owner-input');
    const $projectStatusInput = document.getElementById('project-status-input');
    const $projectDueInput = document.getElementById('project-due-input');
    const $projectDescriptionInput = document.getElementById('project-description-input');
    const $projectMoveDialog = document.getElementById('project-move-dialog');
    const $projectMoveClose = document.getElementById('project-move-close');
    const $projectMoveCancel = document.getElementById('project-move-cancel');
    const $moveFolderSelect = document.getElementById('move-folder-select');
    const $moveProjectSelect = document.getElementById('move-project-select');

    let _projects = [];
    let _projectDialogMode = 'create';
    let _editingProjectPath = '';

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

    function projectInfoPayload() {
        return {
            title: $projectTitleInput.value.trim(),
            institution: $projectInstitutionInput.value.trim(),
            department: $projectDepartmentInput.value.trim(),
            owner: $projectOwnerInput.value.trim(),
            status: $projectStatusInput.value,
            due_date: $projectDueInput.value,
            description: $projectDescriptionInput.value.trim(),
        };
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
        $projectNameInput.value = project ? project.name : '';
        $projectNameInput.disabled = mode !== 'create';
        $projectTitleInput.value = info.title || project?.name || '';
        $projectInstitutionInput.value = info.institution || '';
        $projectDepartmentInput.value = info.department || '';
        $projectOwnerInput.value = info.owner || '';
        $projectStatusInput.value = info.status || 'active';
        $projectDueInput.value = info.due_date || '';
        $projectDescriptionInput.value = info.description || '';
        $projectDialog.showModal();
    }

    function closeProjectDialog() {
        if ($projectDialog?.open) $projectDialog.close();
    }

    async function saveProjectDialog() {
        const payload = projectInfoPayload();
        if (_projectDialogMode === 'create') {
            await postForm('/slides/project/create', {
                name: $projectNameInput.value.trim(),
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

    async function renameProject(project) {
        const next = prompt('Project folder name:', project.name);
        if (!next || !next.trim() || next.trim() === project.name) return;
        await postForm('/slides/project/rename', { name: project.name, new_name: next.trim() });
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
    function renderProjects(projects) {
        if (!$projectTableBody) return;
        $projectTableBody.innerHTML = '';
        if (!projects.length) {
            $projectTableBody.innerHTML = '<tr><td colspan="7" class="project-empty">No projects yet</td></tr>';
            return;
        }
        for (const project of projects) {
            const info = project.info || {};
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><div class="project-title">
                    <a href="/app.html?path=${encodeURIComponent(project.path || project.name)}">${_esc(info.title || project.name)}</a>
                    <span class="project-subtitle">${_esc(project.path || project.name)}${info.description ? ' · ' + _esc(info.description) : ''}</span>
                </div></td>
                <td>${_esc(info.institution || '-')}</td>
                <td>${_esc(info.owner || '-')}</td>
                <td><span class="project-status">${_esc(info.status || 'active')}</span></td>
                <td>${project.slide_count || 0}</td>
                <td>${_esc(info.due_date || '-')}</td>
                <td><div class="project-actions-cell"></div></td>
            `;
            const actions = tr.querySelector('.project-actions-cell');
            const openBtn = document.createElement('button');
            openBtn.className = 'project-mini-btn';
            openBtn.textContent = 'Open';
            openBtn.addEventListener('click', () => { location.href = `/app.html?path=${encodeURIComponent(project.path)}`; });
            actions.appendChild(openBtn);
            if (canEditProjects()) {
                const editBtn = document.createElement('button');
                editBtn.className = 'project-mini-btn';
                editBtn.textContent = 'Info';
                editBtn.addEventListener('click', () => openProjectDialog('edit', project));
                const renameBtn = document.createElement('button');
                renameBtn.className = 'project-mini-btn';
                renameBtn.textContent = 'Rename';
                renameBtn.addEventListener('click', () => renameProject(project).catch(err => alert(err.message)));
                const moveBtn = document.createElement('button');
                moveBtn.className = 'project-mini-btn';
                moveBtn.textContent = 'Move';
                moveBtn.addEventListener('click', () => openMoveFolderDialog(project).catch(err => alert(err.message)));
                actions.append(editBtn, renameBtn, moveBtn);
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
        }
    });

    $btnRefreshProjects?.addEventListener('click', () => loadFolderTree());
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

    loadDashboard();
})();
