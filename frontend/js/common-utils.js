export function esc(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function $(selector) {
    return document.querySelector(selector);
}

export function normalizeUserRole(role) {
    const value = String(role || '').toLowerCase();
    return ['admin', 'doctor', 'labeler', 'viewer'].includes(value) ? value : 'viewer';
}

export function roleLabel(role) {
    return {
        admin: 'Admin',
        doctor: 'Doctor',
        labeler: 'Labeler',
        viewer: 'Viewer',
    }[normalizeUserRole(role)] || 'Viewer';
}
