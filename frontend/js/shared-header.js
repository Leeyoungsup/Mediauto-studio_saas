(function () {
    'use strict';

    function labelForRole(role) {
        return {
            admin: 'Admin',
            doctor: 'Doctor',
            labeler: 'Labeler',
            viewer: 'Viewer',
        }[String(role || '').toLowerCase()] || 'Unknown';
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    async function defaultLogout() {
        const token = localStorage.getItem('access_token');
        try {
            if (token) {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: {
                        Authorization: `Bearer ${token}`,
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });
            }
        } catch (_) {
            // Logout should always clear local state even if the server call fails.
        }
        localStorage.clear();
        location.href = '/login';
    }

    async function loadVersion(root) {
        const badge = root.querySelector('.shared-version');
        if (!badge) return;
        try {
            const res = await fetch('/api/version', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                cache: 'no-store',
            });
            if (!res.ok) return;
            const info = await res.json();
            const version = info.version ? `v${info.version}` : '';
            const channel = info.channel && info.channel !== 'production' ? info.channel : '';
            badge.textContent = channel ? `${version} ${channel}` : version;
            badge.title = [info.name, version, channel, info.release_date].filter(Boolean).join(' ');
            badge.setAttribute('aria-label', `${version} release notes`);
            badge.hidden = !version;
        } catch (_) {
            badge.hidden = true;
        }
    }

    function syncStaticCellAnnotationLinks(canUseCellAnnotation) {
        document.querySelectorAll('[data-cell-annotation-link]').forEach((link) => {
            if (canUseCellAnnotation) {
                link.href = '/cell-annotation';
                link.classList.remove('disabled');
                link.removeAttribute('aria-disabled');
                link.removeAttribute('tabindex');
                link.removeAttribute('title');
            } else {
                link.href = '#';
                link.classList.add('disabled');
                link.setAttribute('aria-disabled', 'true');
                link.setAttribute('tabindex', '-1');
                link.setAttribute('title', 'Unavailable');
                link.addEventListener('click', (event) => event.preventDefault());
            }
        });
    }

    function render(options = {}) {
        const root = document.getElementById(options.rootId || 'shared-header-root');
        if (!root) return null;

        const user = options.user || {};
        const active = options.active || '';
        const rawRole = user.str_role || options.role || '';
        const role = ['admin', 'doctor', 'labeler', 'viewer'].includes(String(rawRole).toLowerCase())
            ? String(rawRole).toLowerCase()
            : 'viewer';
        const name = user.str_name || user.str_login_id || '';
        const showAdmin = options.showAdmin ?? role === 'admin';
        const canUseCellAnnotation = true;
        const annotationActive = active === 'annotation' || active === 'tissue-annotation' || active === 'cell-annotation';
        const cellClass = [
            'shared-nav-subitem',
            active === 'cell-annotation' ? 'active' : '',
            canUseCellAnnotation ? '' : 'disabled',
        ].filter(Boolean).join(' ');
        const cellAttrs = canUseCellAnnotation
            ? 'href="/cell-annotation"'
            : 'href="#" aria-disabled="true" tabindex="-1" title="Unavailable"';

        root.innerHTML = `
            <header class="shared-header">
                <div class="shared-header-inner">
                    <div class="shared-brand">
                        <a href="/home" class="shared-brand-home" aria-label="MeDIAuto Studio home">
                            <img src="assets/logo.png" alt="MeDIAuto Studio" class="shared-logo">
                        </a>
                        <a href="/version" class="shared-version" title="View release notes" hidden></a>
                    </div>
                    <nav class="shared-nav" aria-label="Primary">
                        <a href="/home" class="shared-nav-item ${active === 'home' ? 'active' : ''}">Home</a>
                        <a href="/project" class="shared-nav-item ${active === 'project' ? 'active' : ''}">Project</a>
                        <a href="/data-linkage" class="shared-nav-item ${active === 'data-linkage' ? 'active' : ''}">Data Linkage</a>
                        <a href="/ai" class="shared-nav-item ${active === 'viewer' ? 'active' : ''}">AI</a>
                        <a href="/ai-guide.html" class="shared-nav-item">AI 사용 안내</a>
                        <div class="shared-nav-menu">
                            <button type="button" class="shared-nav-item shared-nav-parent ${annotationActive ? 'active' : ''}" aria-haspopup="true" aria-expanded="false">Annotation</button>
                            <div class="shared-nav-submenu" role="menu">
                                <a href="/tissue-annotation" class="shared-nav-subitem ${active === 'tissue-annotation' || active === 'annotation' ? 'active' : ''}" role="menuitem">Tissue</a>
                                <a ${cellAttrs} class="${cellClass}" role="menuitem">Cell</a>
                            </div>
                        </div>
                        ${showAdmin ? `<a href="/admin" class="shared-nav-item ${active === 'admin' ? 'active' : ''}">Admin</a>` : ''}
                    </nav>
                    <div class="shared-user-info">
                        <a href="/profile" class="shared-user-name" title="Edit profile">${esc(name)}</a>
                        <span class="shared-role">${esc(labelForRole(role))}</span>
                        <button class="shared-logout" type="button">Logout</button>
                    </div>
                </div>
            </header>
        `;

        const logout = root.querySelector('.shared-logout');
        logout?.addEventListener('click', options.logout || defaultLogout);
        root.querySelectorAll('.shared-nav-subitem.disabled').forEach((item) => {
            item.addEventListener('click', (event) => event.preventDefault());
        });
        syncStaticCellAnnotationLinks(canUseCellAnnotation);
        loadVersion(root);
        return root;
    }

    window.MediautoHeader = { render };
})();
