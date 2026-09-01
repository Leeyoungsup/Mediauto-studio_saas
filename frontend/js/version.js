(function () {
    'use strict';

    const PAGE_SIZE = 30;
    const accessToken = localStorage.getItem('access_token');
    const userRaw = localStorage.getItem('user');

    if (!accessToken) {
        location.href = '/login';
        return;
    }

    let currentUser = {};
    try { currentUser = JSON.parse(userRaw) || {}; } catch (_) { currentUser = {}; }

    window.MediautoHeader?.render({
        active: 'version',
        user: currentUser,
        showAdmin: currentUser?.str_role === 'admin',
    });

    const elements = {
        currentVersion: document.getElementById('current-version'),
        currentReleaseDate: document.getElementById('current-release-date'),
        currentChannel: document.getElementById('current-channel'),
        search: document.getElementById('version-search'),
        series: document.getElementById('version-series'),
        expand: document.getElementById('expand-visible'),
        collapse: document.getElementById('collapse-all'),
        releaseCount: document.getElementById('release-count'),
        changeCount: document.getElementById('change-count'),
        resultSummary: document.getElementById('version-result-summary'),
        list: document.getElementById('version-list'),
        loadMore: document.getElementById('version-load-more'),
        error: document.getElementById('version-error'),
    };

    let history = { current: {}, releases: [] };
    let visibleLimit = PAGE_SIZE;

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function inlineMarkup(value) {
        return esc(value)
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    }

    function seriesFor(version) {
        const parts = String(version || '').split('.');
        return parts.length >= 2 ? `${parts[0]}.${parts[1]}.x` : String(version || 'Other');
    }

    function slug(value) {
        return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    }

    function searchableText(release) {
        return [
            release.version,
            release.date,
            ...(release.sections || []).flatMap((section) => [section.title, ...(section.items || [])]),
        ].join(' ').toLowerCase();
    }

    function filteredReleases() {
        const query = elements.search.value.trim().toLowerCase();
        const selectedSeries = elements.series.value;
        return history.releases.filter((release) => {
            if (selectedSeries !== 'all' && seriesFor(release.version) !== selectedSeries) return false;
            return !query || searchableText(release).includes(query);
        });
    }

    function renderRelease(release, index) {
        const isCurrent = release.version === history.current.version;
        const sectionHtml = (release.sections || []).map((section) => `
            <section class="release-section">
                <h3 data-kind="${esc(slug(section.title))}">${esc(section.title)}</h3>
                <ul>${(section.items || []).map((item) => `<li>${inlineMarkup(item)}</li>`).join('')}</ul>
            </section>
        `).join('');
        return `
            <details class="release-card${isCurrent ? ' current' : ''}" data-version="${esc(release.version)}" ${isCurrent && index === 0 ? 'open' : ''}>
                <summary class="release-summary">
                    <span class="release-chevron" aria-hidden="true"></span>
                    <span class="release-version">v${esc(release.version)}</span>
                    <span class="release-date">${esc(release.date || 'Date not recorded')}</span>
                    <span class="release-meta">
                        <span class="release-count">${Number(release.change_count || 0).toLocaleString()} changes</span>
                        ${isCurrent ? '<span class="release-current">CURRENT</span>' : ''}
                    </span>
                </summary>
                <div class="release-body">${sectionHtml}</div>
            </details>
        `;
    }

    function render() {
        const releases = filteredReleases();
        const shown = releases.slice(0, visibleLimit);
        const totalChanges = history.releases.reduce((sum, release) => sum + Number(release.change_count || 0), 0);

        elements.releaseCount.textContent = Number(history.releases.length).toLocaleString();
        elements.changeCount.textContent = totalChanges.toLocaleString();
        elements.resultSummary.textContent = `Showing ${shown.length.toLocaleString()} of ${releases.length.toLocaleString()} matching releases`;
        elements.list.innerHTML = shown.length
            ? shown.map(renderRelease).join('')
            : '<div class="version-empty">No release notes match the current search.</div>';
        elements.loadMore.hidden = shown.length >= releases.length;
        if (!elements.loadMore.hidden) {
            elements.loadMore.textContent = `Show more releases (${(releases.length - shown.length).toLocaleString()} remaining)`;
        }
    }

    function populateSeries() {
        const series = [...new Set(history.releases.map((release) => seriesFor(release.version)))];
        elements.series.insertAdjacentHTML('beforeend', series.map((item) => `<option value="${esc(item)}">${esc(item)}</option>`).join(''));
    }

    async function loadHistory() {
        const response = await fetch('/api/version-history', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            cache: 'no-store',
        });
        if (!response.ok) throw new Error(`Could not load release history (${response.status})`);
        history = await response.json();
        elements.currentVersion.textContent = `v${history.current.version || '—'}`;
        elements.currentReleaseDate.textContent = history.current.release_date || 'Date not recorded';
        elements.currentChannel.textContent = history.current.channel || 'unknown';
        populateSeries();
        render();
    }

    elements.search.addEventListener('input', () => { visibleLimit = PAGE_SIZE; render(); });
    elements.series.addEventListener('change', () => { visibleLimit = PAGE_SIZE; render(); });
    elements.loadMore.addEventListener('click', () => { visibleLimit += PAGE_SIZE; render(); });
    elements.expand.addEventListener('click', () => {
        elements.list.querySelectorAll('.release-card').forEach((card) => { card.open = true; });
    });
    elements.collapse.addEventListener('click', () => {
        elements.list.querySelectorAll('.release-card').forEach((card) => { card.open = false; });
    });

    loadHistory().catch((error) => {
        elements.error.textContent = error.message;
        elements.error.hidden = false;
        elements.resultSummary.textContent = 'Release history unavailable';
    });
})();
