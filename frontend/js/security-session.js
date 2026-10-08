/* Human activity is separate from polling, image loads and token rotation. */
(() => {
    'use strict';
    const idleMs = 30 * 60 * 1000;
    const activityKey = 'security_last_activity';
    const originalFetch = window.fetch.bind(window);
    let lastSent = 0;
    let activityInFlight = false;
    let lastLocalActivity = 0;
    const hasSession = () => Boolean(localStorage.getItem('access_token'));
    const isIdle = () => Date.now() - Number(localStorage.getItem(activityKey) || 0) >= idleMs;
    function expire() {
        for (const key of ['access_token', 'refresh_token', 'token_expires', 'user', activityKey]) localStorage.removeItem(key);
        if (!location.pathname.endsWith('/login')) location.replace('/login');
    }
    window.fetch = async (input, options = {}) => {
        const response = await originalFetch(input, options);
        const url = String(typeof input === 'string' ? input : input.url);
        if (url.includes('/api/') && !/\/auth\/(login|register)(?:$|[?])/.test(url)) {
            if (response.status === 401 && hasSession()) expire();
            if (response.status === 403) {
                const body = await response.clone().json().catch(() => ({}));
                if (body.detail === 'PASSWORD_CHANGE_REQUIRED') location.replace('/profile');
            }
        }
        return response;
    };
    if (hasSession() && !localStorage.getItem(activityKey)) localStorage.setItem(activityKey, Date.now());
    function activity(event) {
        if (!event.isTrusted || !hasSession()) return;
        if (isIdle()) { expire(); return; }
        if (Date.now() - lastLocalActivity < 1000) return;
        lastLocalActivity = Date.now();
        localStorage.setItem(activityKey, lastLocalActivity);
        if (activityInFlight || Date.now() - lastSent < 10000) return;
        activityInFlight = true;
        const token = localStorage.getItem('access_token');
        window.fetch('/api/auth/activity', {method: 'POST', headers: {Authorization: `Bearer ${token}`}})
            .then(res => { if (res.ok) lastSent = Date.now(); })
            .catch(() => {}).finally(() => { activityInFlight = false; });
    }
    for (const event of ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart']) {
        window.addEventListener(event, activity, {passive: true});
    }
    setInterval(() => { if (hasSession() && isIdle()) expire(); }, 1000);
    window.addEventListener('storage', event => {
        if (event.key === 'access_token' && !event.newValue && !location.pathname.endsWith('/login')) location.replace('/login');
    });
    window.MediautoSecurity = {
        async authorizeExport(filename) {
            const reason = window.prompt('다운로드 사유를 입력하세요 (2~200자). 환자정보는 입력하지 마세요.');
            if (reason === null) return false;
            if (reason.trim().length < 2 || reason.trim().length > 200) throw new Error('다운로드 사유는 2~200자로 입력하세요.');
            const res = await window.fetch('/api/auth/download-intent', {
                method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`},
                body: JSON.stringify({str_reason: reason.trim(), str_filename: filename}),
            });
            if (!res.ok) throw new Error('다운로드 사유 기록에 실패했습니다. 다시 시도하세요.');
            return true;
        },
        requestReason() {
            const reason = window.prompt('다운로드 사유를 입력하세요 (2~200자). 환자정보는 입력하지 마세요.');
            if (reason === null) return null;
            if (reason.trim().length < 2 || reason.trim().length > 200) throw new Error('다운로드 사유는 2~200자로 입력하세요.');
            return reason.trim();
        },
    };
})();
