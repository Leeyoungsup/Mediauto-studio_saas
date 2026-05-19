(function () {
    'use strict';

    const API_BASE = '/api';
    const accessToken = localStorage.getItem('access_token');
    const userRaw = localStorage.getItem('user');

    if (!accessToken) {
        location.href = '/login';
        return;
    }

    let currentUser = null;
    try { currentUser = JSON.parse(userRaw); } catch { currentUser = {}; }

    window.MediautoHeader?.render({
        active: 'profile',
        user: currentUser,
        showAdmin: currentUser?.str_role === 'admin',
    });

    const $alert = document.getElementById('profile-alert');
    const $profileForm = document.getElementById('profile-form');
    const $passwordForm = document.getElementById('password-form');
    const $loginId = document.getElementById('profile-login-id');
    const $name = document.getElementById('profile-name');
    const $department = document.getElementById('profile-department');
    const $role = document.getElementById('profile-role');
    const $currentPassword = document.getElementById('current-password');
    const $newPassword = document.getElementById('new-password');
    const $confirmPassword = document.getElementById('confirm-password');

    function showAlert(message, type = 'success') {
        $alert.textContent = message;
        $alert.className = `profile-alert ${type}`;
        $alert.hidden = false;
    }

    async function authFetch(path, options = {}) {
        const headers = {
            ...(options.headers || {}),
            Authorization: `Bearer ${accessToken}`,
            'X-Requested-With': 'XMLHttpRequest',
        };
        if (options.body && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }
        const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (res.status === 401) {
            localStorage.clear();
            location.href = '/login';
            return null;
        }
        return res;
    }

    function setUser(user) {
        $loginId.value = user.str_login_id || '';
        $name.value = user.str_name || '';
        $department.value = user.str_department || '';
        $role.value = user.str_role || '';
    }

    async function loadMe() {
        const res = await authFetch('/auth/me');
        if (!res || !res.ok) throw new Error('Failed to load profile');
        const user = await res.json();
        currentUser = {
            ...(currentUser || {}),
            str_login_id: user.str_login_id,
            str_name: user.str_name,
            str_role: user.str_role,
            str_department: user.str_department || '',
        };
        localStorage.setItem('user', JSON.stringify(currentUser));
        setUser(currentUser);
        window.MediautoHeader?.render({
            active: 'profile',
            user: currentUser,
            showAdmin: currentUser?.str_role === 'admin',
        });
    }

    $profileForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = $profileForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await authFetch('/users/me', {
                method: 'POST',
                body: JSON.stringify({
                    str_name: $name.value.trim(),
                    str_department: $department.value.trim(),
                }),
            });
            if (!res || !res.ok) throw new Error(res ? await res.text() : 'Failed to save profile');
            const data = await res.json();
            const user = data.dict_user || {};
            currentUser = {
                ...(currentUser || {}),
                str_login_id: user.str_login_id || currentUser.str_login_id,
                str_name: user.str_name || $name.value.trim(),
                str_role: user.str_role || currentUser.str_role,
                str_department: user.str_department || '',
            };
            localStorage.setItem('user', JSON.stringify(currentUser));
            window.MediautoHeader?.render({
                active: 'profile',
                user: currentUser,
                showAdmin: currentUser?.str_role === 'admin',
            });
            showAlert('Profile saved.');
        } catch (err) {
            showAlert(err.message, 'error');
        } finally {
            btn.disabled = false;
        }
    });

    $passwordForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        if ($newPassword.value !== $confirmPassword.value) {
            showAlert('New password confirmation does not match.', 'error');
            return;
        }
        const btn = $passwordForm.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
            const res = await authFetch('/auth/change-password', {
                method: 'POST',
                body: JSON.stringify({
                    str_current_password: $currentPassword.value,
                    str_new_password: $newPassword.value,
                }),
            });
            if (!res || !res.ok) throw new Error(res ? await res.text() : 'Failed to change password');
            showAlert('Password changed. Please log in again.');
            setTimeout(() => {
                localStorage.clear();
                location.href = '/login';
            }, 900);
        } catch (err) {
            showAlert(err.message, 'error');
            btn.disabled = false;
        }
    });

    loadMe().catch((err) => showAlert(err.message, 'error'));
})();
