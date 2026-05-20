import { api } from './api.js?v=20260520-02';

(function () {
    'use strict';

    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
        location.href = '/login';
        return;
    }

    let currentUser = null;
    try { currentUser = JSON.parse(localStorage.getItem('user') || '{}'); } catch (_) { currentUser = {}; }

    window.MediautoHeader?.render({
        active: 'data-linkage',
        user: currentUser,
        showAdmin: currentUser?.str_role === 'admin',
    });

    const CLINICAL_FIELDS = [
        { key: 'ER_proportion_score', label: 'ER_proportion_score (0 - 5) or na', type: 'text' },
        { key: 'ER_intensity_score', label: 'ER_intensity_score (0 - 3) or na', type: 'text' },
        { key: 'PR_proportion_score', label: 'PR_proportion_score (0 - 5) or na', type: 'text' },
        { key: 'PR_intensity_score', label: 'PR_intensity_score (0 - 3) or na', type: 'text' },
        { key: 'Ki67_index', label: 'Ki67_index(%) or na', type: 'text' },
        { key: 'PD-L1_CPS_score', label: 'PD-L1_CPS_score or na', type: 'text' },
        { key: 'ISH_for_HER2_(FISH_SISH)', label: 'ISH_for_HER2_(FISH_SISH)', type: 'select', options: ['', 'ISH negative', 'ISH positive', 'not tested', 'na'] },
        { key: 'IHC_for_C-erbB2', label: 'IHC_for_C-erbB2 (0 - 3)', type: 'text' },
    ];

    const $project = document.getElementById('dl-project-select');
    const $hospital = document.getElementById('dl-hospital-select');
    const $sampleSearch = document.getElementById('dl-sample-search');
    const $search = document.getElementById('dl-search-btn');
    const $pageSize = document.getElementById('dl-page-size');
    const $caseList = document.getElementById('dl-case-list');
    const $prev = document.getElementById('dl-prev-page');
    const $next = document.getElementById('dl-next-page');
    const $pageIndicator = document.getElementById('dl-page-indicator');
    const $totalLabel = document.getElementById('dl-total-label');
    const $previewImg = document.getElementById('dl-preview-img');
    const $previewEmpty = document.getElementById('dl-preview-empty');
    const $year = document.getElementById('dl-year');
    const $sampleId = document.getElementById('dl-sample-id');
    const $thumbnailRow = document.getElementById('dl-thumbnail-row');
    const $form = document.getElementById('dl-clinical-form');
    const $save = document.getElementById('dl-save-btn');
    const $saveStatus = document.getElementById('dl-save-status');

    let state = {
        cases: [],
        projects: [],
        hospitals: [],
        total: 0,
        page: 1,
        pageSize: Number($pageSize?.value || 15),
        selectedCase: null,
        selectedSlide: null,
        dirty: false,
    };

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function hasClinicalInfo(info) {
        return Object.values(info || {}).some((value) => String(value || '').trim());
    }

    function fillSelect(select, items, placeholder, getValue, getLabel) {
        if (!select) return;
        const current = select.value;
        select.innerHTML = `<option value="">${esc(placeholder)}</option>`;
        items.forEach((item) => {
            const opt = document.createElement('option');
            opt.value = getValue(item);
            opt.textContent = getLabel(item);
            select.appendChild(opt);
        });
        if ([...select.options].some((opt) => opt.value === current)) select.value = current;
    }

    function renderCaseList() {
        if (!$caseList) return;
        if (!state.cases.length) {
            $caseList.innerHTML = '<div class="data-linkage-empty-row">No cases found.</div>';
            return;
        }
        $caseList.innerHTML = state.cases.map((item) => {
            const active = state.selectedCase?.case_name === item.case_name ? ' active' : '';
            const clinicalClass = item.has_clinical_info ? 'ok' : 'empty';
            const clinicalText = item.has_clinical_info ? '✓' : '-';
            return `
                <button type="button" class="data-linkage-row${active}" data-case="${esc(item.case_name)}">
                    <span>${item.no || ''}</span>
                    <strong>${esc(item.case_name)}</strong>
                    <span class="data-linkage-state ${clinicalClass}">${clinicalText}</span>
                    <span>${esc(item.last_activity || '-')}</span>
                </button>
            `;
        }).join('');
    }

    function renderPager() {
        const pageCount = Math.max(1, Math.ceil(state.total / state.pageSize));
        $pageIndicator.textContent = String(state.page);
        $prev.disabled = state.page <= 1;
        $next.disabled = state.page >= pageCount;
        const start = state.total ? ((state.page - 1) * state.pageSize) + 1 : 0;
        const end = Math.min(state.total, state.page * state.pageSize);
        $totalLabel.textContent = `Showing ${start} to ${end} of ${state.total} entries`;
    }

    async function setPreview(slide) {
        state.selectedSlide = slide || null;
        $previewImg.removeAttribute('src');
        $previewImg.hidden = true;
        $previewEmpty.hidden = false;
        if (!slide) return;
        await api.ensureMediaReady();
        const url = api.thumbnailUrlByName(slide.filename, slide.path || '', 2048);
        if (!url) return;
        $previewImg.src = url;
        api.attachMediaImageRetry?.($previewImg, () => api.thumbnailUrlByName(slide.filename, slide.path || '', 2048));
        $previewImg.hidden = false;
        $previewEmpty.hidden = true;
    }

    async function selectCase(caseName) {
        const item = state.cases.find((row) => row.case_name === caseName);
        if (!item) return;
        state.selectedCase = item;
        state.dirty = false;
        $year.textContent = item.year || '-';
        $sampleId.textContent = item.case_name || '-';
        renderCaseList();
        renderThumbnails(item);
        renderClinicalForm(item.clinical_info || {});
        await setPreview(item.slides?.[0] || null);
        $saveStatus.textContent = item.has_clinical_info ? 'Saved clinical info' : 'No clinical info';
    }

    async function renderThumbnails(item) {
        $thumbnailRow.innerHTML = '';
        const slides = item.slides || [];
        if (!slides.length) {
            $thumbnailRow.innerHTML = '<span class="data-linkage-muted">No linked images</span>';
            return;
        }
        await api.ensureMediaReady();
        slides.forEach((slide, index) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `data-linkage-thumb${index === 0 ? ' active' : ''}`;
            btn.title = slide.filename;
            const img = document.createElement('img');
            const setSrc = () => api.thumbnailUrlByName(slide.filename, slide.path || '', 180);
            img.src = setSrc();
            api.attachMediaImageRetry?.(img, setSrc);
            btn.appendChild(img);
            btn.addEventListener('click', async () => {
                $thumbnailRow.querySelectorAll('.data-linkage-thumb').forEach((el) => el.classList.remove('active'));
                btn.classList.add('active');
                await setPreview(slide);
            });
            $thumbnailRow.appendChild(btn);
        });
    }

    function renderClinicalForm(info) {
        $form.innerHTML = CLINICAL_FIELDS.map((field) => {
            const value = info[field.key] || '';
            if (field.type === 'select') {
                return `
                    <label class="data-linkage-field">
                        <span>${esc(field.label)}<b>*</b></span>
                        <select data-clinical-key="${esc(field.key)}">
                            ${field.options.map((option) => `<option value="${esc(option)}" ${option === value ? 'selected' : ''}>${esc(option || 'Select')}</option>`).join('')}
                        </select>
                    </label>
                `;
            }
            return `
                <label class="data-linkage-field">
                    <span>${esc(field.label)}<b>*</b></span>
                    <input data-clinical-key="${esc(field.key)}" value="${esc(value)}">
                </label>
            `;
        }).join('');
        $form.querySelectorAll('[data-clinical-key]').forEach((input) => {
            input.addEventListener('input', () => {
                state.dirty = true;
                $saveStatus.textContent = 'Unsaved changes';
            });
            input.addEventListener('change', () => {
                state.dirty = true;
                $saveStatus.textContent = 'Unsaved changes';
            });
        });
    }

    function collectClinicalInfo() {
        const info = {};
        $form.querySelectorAll('[data-clinical-key]').forEach((input) => {
            info[input.dataset.clinicalKey] = input.value.trim();
        });
        return info;
    }

    async function saveClinicalInfo() {
        if (!state.selectedCase) return;
        const info = collectClinicalInfo();
        $save.disabled = true;
        $saveStatus.textContent = 'Saving...';
        try {
            const res = await api.updateCaseClinicalInfo(state.selectedCase.case_name, info);
            state.selectedCase.clinical_info = res.dict_clinical_info || info;
            state.selectedCase.has_clinical_info = hasClinicalInfo(state.selectedCase.clinical_info);
            state.dirty = false;
            renderCaseList();
            $saveStatus.textContent = 'Saved';
        } catch (err) {
            console.error(err);
            $saveStatus.textContent = 'Save failed';
        } finally {
            $save.disabled = false;
        }
    }

    async function loadCases({ keepSelection = false } = {}) {
        const selectedName = keepSelection ? state.selectedCase?.case_name : '';
        $caseList.innerHTML = '<div class="data-linkage-empty-row">Loading...</div>';
        const data = await api.listCases({
            project: $project.value,
            hospital: $hospital.value,
            sampleNo: $sampleSearch.value,
            page: state.page,
            pageSize: state.pageSize,
        });
        state.cases = data.cases || [];
        state.projects = data.projects || state.projects || [];
        state.hospitals = data.hospitals || state.hospitals || [];
        state.total = Number(data.total || 0);
        fillSelect($project, state.projects, 'Project (all) *', (item) => item.path || item.name, (item) => item.name || item.path);
        fillSelect($hospital, state.hospitals, 'Hospital (all) *', (item) => item, (item) => item);
        renderCaseList();
        renderPager();
        const nextName = selectedName && state.cases.some((item) => item.case_name === selectedName)
            ? selectedName
            : state.cases[0]?.case_name;
        if (nextName) {
            await selectCase(nextName);
        } else {
            state.selectedCase = null;
            $year.textContent = '-';
            $sampleId.textContent = '-';
            $thumbnailRow.innerHTML = '';
            $form.innerHTML = '<div class="data-linkage-form-empty">Clinical fields appear after selecting a sample.</div>';
            await setPreview(null);
        }
    }

    $caseList?.addEventListener('click', (event) => {
        const row = event.target.closest('[data-case]');
        if (row) selectCase(row.dataset.case);
    });
    $search?.addEventListener('click', () => { state.page = 1; loadCases(); });
    $sampleSearch?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            state.page = 1;
            loadCases();
        }
    });
    $project?.addEventListener('change', () => { state.page = 1; loadCases(); });
    $hospital?.addEventListener('change', () => { state.page = 1; loadCases(); });
    $pageSize?.addEventListener('change', () => {
        state.pageSize = Number($pageSize.value || 15);
        state.page = 1;
        loadCases();
    });
    $prev?.addEventListener('click', () => {
        if (state.page > 1) {
            state.page -= 1;
            loadCases();
        }
    });
    $next?.addEventListener('click', () => {
        if (state.page < Math.ceil(state.total / state.pageSize)) {
            state.page += 1;
            loadCases();
        }
    });
    $save?.addEventListener('click', saveClinicalInfo);

    window.addEventListener('beforeunload', (event) => {
        if (!state.dirty) return;
        event.preventDefault();
        event.returnValue = '';
    });

    loadCases().catch((err) => {
        console.error(err);
        $caseList.innerHTML = '<div class="data-linkage-empty-row">Failed to load cases.</div>';
    });
})();
