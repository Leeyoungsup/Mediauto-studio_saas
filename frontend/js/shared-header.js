(function () {
    'use strict';

    function labelForRole(role) {
        return role || 'viewer';
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
        location.href = '/login.html';
    }

    function render(options = {}) {
        const root = document.getElementById(options.rootId || 'shared-header-root');
        if (!root) return null;

        const user = options.user || {};
        const active = options.active || '';
        const role = user.str_role || options.role || '';
        const name = user.str_name || user.str_login_id || '';
        const showAdmin = options.showAdmin ?? role === 'admin';

        root.innerHTML = `
            <header class="shared-header">
                <div class="shared-header-inner">
                    <a href="/home.html" class="shared-brand">
                        <img src="assets/logo.png" alt="MeDIAuto Studio" class="shared-logo">
                    </a>
                    <nav class="shared-nav" aria-label="Primary">
                        <a href="/home.html" class="shared-nav-item ${active === 'home' ? 'active' : ''}">Home</a>
                        <a href="/app.html" class="shared-nav-item ${active === 'viewer' ? 'active' : ''}">AI</a>
                        <a href="/annotation.html" class="shared-nav-item ${active === 'annotation' ? 'active' : ''}">Annotation</a>
                        ${showAdmin ? `<a href="/admin.html" class="shared-nav-item ${active === 'admin' ? 'active' : ''}">Admin</a>` : ''}
                    </nav>
                    <div class="shared-user-info">
                        <a href="/profile.html" class="shared-user-name" title="Edit profile">${esc(name)}</a>
                        <span class="shared-role">${esc(labelForRole(role))}</span>
                        <button class="shared-logout" type="button">Logout</button>
                    </div>
                </div>
            </header>
        `;

        const logout = root.querySelector('.shared-logout');
        logout?.addEventListener('click', options.logout || defaultLogout);
        return root;
    }

    window.MediautoHeader = { render };
})();
