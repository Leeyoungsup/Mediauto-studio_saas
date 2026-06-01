/**
 * Main AI viewer module for MeDIAuto Studio.
 * Handles project selection, slide browsing, annotation tools, and AI analysis workflows.
 */

import { api } from './api.js?v=20260526-01';
import { AiViewer } from './ai-viewer.js?v=20260528-01';
import { showVisualization } from './visualization.js';

if (!localStorage.getItem('access_token')) {
    window.location.replace('/login');
    throw new Error('Not authenticated - redirecting to /login');
}

function _esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const $ = (sel) => document.querySelector(sel);

function _normalizeUserRole(role) {
    const value = String(role || '').toLowerCase();
    return ['admin', 'doctor', 'labeler', 'viewer'].includes(value) ? value : 'viewer';
}

function _roleLabel(role) {
    return {
        admin: 'Admin',
        doctor: 'Doctor',
        labeler: 'Labeler',
        viewer: 'Viewer',
    }[_normalizeUserRole(role)] || 'Viewer';
}

const $canvas = $('#wsi-canvas');
const $overlay = $('#overlay-canvas');
const $slideName = $('#slide-name');
const $statusText = $('#status-text');
const $zoomInfo = $('#zoom-info');
const $fileInput = $('#file-input');
const $dropOverlay = $('#drop-overlay');
const $minimapContainer = $('#minimap-container');
const $minimapCanvas = $('#minimap-canvas');
const $minimapViewport = $('#minimap-viewport');
const $progressLabel = $('#progress-label');
const $progressBar = $('#progress-bar');
const $resultList = $('#result-list');
const $slideInfoDialog = $('#slide-info-dialog');
const $slideInfoContent = $('#slide-info-content');
const $slideNameSearch = $('#slide-name-search');
const LIST_SLIDE_CLINICAL_FIELDS = [
    { key: 'ER_proportion_score', label: 'ER_proportion_score (0 - 5) or na', type: 'input', required: true },
    { key: 'ER_intensity_score', label: 'ER_intensity_score (0 - 3) or na', type: 'input', required: true },
    { key: 'PR_proportion_score', label: 'PR_proportion_score (0 - 5) or na', type: 'input', required: true },
    { key: 'PR_intensity_score', label: 'PR_intensity_score (0 - 3) or na', type: 'input', required: true },
    { key: 'Ki67_index', label: 'Ki67_index(%) or na', type: 'input', required: true },
    { key: 'PD-L1_CPS_score', label: 'PD-L1_CPS_score or na', type: 'input', required: true },
    { key: 'ISH_for_HER2_(FISH_SISH)', label: 'ISH_for_HER2_(FISH_SISH)', type: 'select', required: true, options: ['', 'ISH negative', 'ISH positive', 'ISH equivocal', 'na'] },
    { key: 'IHC_for_C-erbB2', label: 'IHC_for_C-erbB2 (0 - 3)', type: 'input' },
];
let _slideClinicalInitialJson = '{}';
let _slideClinicalDirty = false;
let _slideInfoClosing = false;

const $userName = $('#user-name');
const $btnLogout = $('#btn-logout');
const $projectUserName = $('#project-user-name');
const $projectUserRole = $('#project-user-role');
const $projectBtnLogout = $('#project-btn-logout');
const $projectLinkAdmin = $('#project-link-admin');

const $btnOpen = $('#btn-open');
const $btnInfo = $('#btn-info');
const $btnFit = $('#btn-fit');
const $btnZoomIn = $('#btn-zoom-in');
const $btnZoomOut = $('#btn-zoom-out');
const $btnDetect = $('#btn-detect');
const $btnVisualize = $('#btn-visualize');
const $btnClearResults = $('#btn-clear-results');
const $btnSaveResults = $('#btn-save-results');
const $btnLoadResults = $('#btn-load-results');
let _lastDetectionResult = null;
let _lastDetectionTissue = null;
let _lastDetectionModel = null;
let _lastDetectionRoi = null;

function _isViewerRole() {
    return window.__currentUserRole === 'viewer';
}

function _isLabelerRole() {
    return window.__currentUserRole === 'labeler';
}

function _canEditAiDetections() {
    return !_isViewerRole() && !_isLabelerRole();
}

function _blockAiResultPersistenceAction(message = 'This role cannot save or load AI results.') {
    if (!_isViewerRole() && !_isLabelerRole()) return false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
    setStatus(message);
    return true;
}

function _blockViewerAction(message = 'Viewer role cannot use AI or annotation features.') {
    if (!_isViewerRole()) return false;
    _applyViewerRoleRestrictions();
    setStatus(message);
    return true;
}

const $btnDrawPolygon = $('#btn-draw-polygon');
const $btnDrawRect = $('#btn-draw-rect');
const $btnDrawRect1mm2 = $('#btn-draw-rect-1mm2');
const $btnDrawCircle1mm2 = $('#btn-draw-circle-1mm2');
const $btnRuler = $('#btn-ruler');

// VS IHC
const $btnVsMembrane = $('#btn-vs-membrane');
const $btnPdScore = $('#btn-pd-score');
const $pdScoreResult = $('#pd-score-result');
const $pdScoreLabel = $('#pd-score-label');
const $pdScoreValue = $('#pd-score-value');
const $pdScoreDetail = $('#pd-score-detail');
const $pdScoreBar = $('#pd-score-bar');
const $btnIhcHer2 = $('#btn-ihc-her2');
const $btnIhcErPr = $('#btn-ihc-erpr');
const $btnIhcKi67 = $('#btn-ihc-ki67');
const $ihcScoreResult = $('#ihc-score-result');
const $ihcScoreLabel = $('#ihc-score-label');
const $ihcScoreValue = $('#ihc-score-value');
const $ihcScoreDetail = $('#ihc-score-detail');
const $ihcScoreBar = $('#ihc-score-bar');
const $btnVsToggle = $('#btn-vs-toggle');
const $btnVsSplit = $('#btn-vs-split');
let _vsRunning = false;
let _vsLastTargetMpp = 2.0;

const $slideList = $('#slide-list');
const $projectSelect = $('#project-select');
const $projectGate = $('#project-gate');
const $projectGateList = $('#project-gate-list');
const $projectGateSearch = $('#project-gate-search');
const $projectGateHospital = $('#project-gate-hospital');
const $projectGateOwner = $('#project-gate-owner');
const $projectGateStatus = $('#project-gate-status');
const $projectGatePageSize = $('#project-gate-page-size');
const $projectGateAdditional = $('#project-gate-additional');
const $projectGateExtra = $('#project-gate-extra');
const $projectGateHasSlides = $('#project-gate-has-slides');
const $projectGateHasFolders = $('#project-gate-has-folders');
const $projectGateMinSlides = $('#project-gate-min-slides');
const $projectGatePager = $('#project-gate-pager');
const $projectStatTotal = $('#project-stat-total');
const $projectStatDone = $('#project-stat-done');
const $projectStatProgress = $('#project-stat-progress');
const $projectStatAi = $('#project-stat-ai');
const $btnNewProject = $('#btn-new-project');
const $btnRenameProject = $('#btn-rename-project');
const $btnDeleteProject = $('#btn-delete-project');
let _lastBrowseData = { folders: [], slides: [] };

let currentSlideId = null;
let currentSlideInfo = null;
let minimapImage = null;
function _setMinimapDisplaySize(img) {
    const body = document.getElementById('minimap-body');
    if (!body || !img) return;
    const maxW = 220;
    const maxH = 170;
    const ratio = Math.min(maxW / img.width, maxH / img.height, 1);
    const displayW = Math.max(120, Math.round(img.width * ratio));
    body.style.width = `${displayW}px`;
}
let lastSegData = null;  // segmentation overlay data from epithelial classification

const viewer = new AiViewer($canvas, $overlay);

viewer.onZoomChange = (zoom, mag, mpp) => {
    $zoomInfo.textContent = `${mag.toFixed(1)}x  |  MPP ${mpp.toFixed(3)} μm/px`;
};
viewer.onViewChange = () => updateMinimap();

const $slideLoadingOverlay = document.getElementById('slide-loading-overlay');
const $slideLoadingBarFill = document.getElementById('slide-loading-bar-fill');
const $slideLoadingPct = document.getElementById('slide-loading-pct');

function _setSlideLoadingProgress(pct) {
    const int_pct = Math.max(0, Math.min(100, Math.round(pct)));
    if ($slideLoadingBarFill) $slideLoadingBarFill.style.width = int_pct + '%';
    if ($slideLoadingPct) $slideLoadingPct.textContent = int_pct + '%';
}

viewer.onPreloadStart = () => {
    if ($slideLoadingOverlay) $slideLoadingOverlay.hidden = true;
    _setSlideLoadingProgress(0);
};

viewer.onPreloadProgress = (int_done, int_total) => {
    if (int_total > 0) {
        _setSlideLoadingProgress((int_done / int_total) * 100);
    }
};

viewer.onPreloadComplete = () => {
    _setSlideLoadingProgress(100);
    if ($slideLoadingOverlay) $slideLoadingOverlay.hidden = true;
};

const $mousePosOverlay = $('#mouse-pos-overlay');
if ($mousePosOverlay) {
    $canvas.addEventListener('mousemove', (e) => {
        if (!currentSlideId) return;
        const rect = $canvas.getBoundingClientRect();
        const [sx, sy] = viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
        $mousePosOverlay.textContent = `x: ${Math.round(sx)}px, y: ${Math.round(sy)}px`;
    });
    $canvas.addEventListener('mouseleave', () => {
        // Hide only after the cursor leaves the canvas.
        });
}

// Tab switching.
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.disabled) return;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        $(`#${btn.dataset.tab}`).classList.add('active');
    });
});

const AI_MODEL_HELP = {
    'hne-tab': {
        title: 'Quanti HE - H&E Cell Detection',
        body: 'Detects individual cells on H&E slides and classifies them into supported cell categories. Breast, Stomach, and Other presets tune the downstream scoring context. Other/background classes are kept out of scoring unless they are explicitly promoted into a visible result class.',
    },
    'vs-tab': {
        title: 'VS IHC - Virtual Staining',
        body: 'Generates a virtual H&E image from an IHC slide. Target Resolution controls the output scale: lower microns per pixel gives finer detail with higher compute cost. Results can be reviewed as an overlay or with split view against the original slide.',
    },
    'pd-tab': {
        title: 'Quanti PD-L1 - PD-L1 Scoring',
        body: 'Detects PD-L1 IHC result cells and calculates the selected score. Stomach uses CPS = (positive tumor + positive immune) / viable tumor x 100. Lung uses TPS = positive tumor / total tumor x 100. Hidden Other cells are excluded from visualization and score calculations unless reclassified.',
    },
    'ihc-tab': {
        title: 'Quanti IHC - HER2 / ER / PR / KI-67',
        body: 'Classifies IHC-positive and IHC-negative result cells for marker-specific scoring. HER2 is summarized from intensity classes, ER/PR use Allred-style proportion and intensity scoring, and KI-67 reports a labeling index based on positive over total counted cells.',
    },
};const $aiHelpIcon = document.querySelector('#ai-help-icon');
let _aiHelpTooltip = null;
function _showAiHelpTooltip() {
    if (!$aiHelpIcon) return;
    const activeBtn = document.querySelector('.tab-btn.active');
    const key = activeBtn ? activeBtn.dataset.tab : 'hne-tab';
    const info = AI_MODEL_HELP[key] || AI_MODEL_HELP['hne-tab'];
    if (!_aiHelpTooltip) {
        _aiHelpTooltip = document.createElement('div');
        _aiHelpTooltip.className = 'ai-help-tooltip';
        document.body.appendChild(_aiHelpTooltip);
    }
    _aiHelpTooltip.innerHTML = `
        <div class="ai-help-title">${info.title}</div>
        <div class="ai-help-body">${info.body}</div>
    `;
    const rect = $aiHelpIcon.getBoundingClientRect();
    _aiHelpTooltip.style.top = `${rect.bottom + 6}px`;
    _aiHelpTooltip.style.left = `${Math.max(8, rect.right - 320)}px`;
    _aiHelpTooltip.classList.add('visible');
}
function _hideAiHelpTooltip() {
    if (_aiHelpTooltip) _aiHelpTooltip.classList.remove('visible');
}
if ($aiHelpIcon) {
    $aiHelpIcon.addEventListener('mouseenter', _showAiHelpTooltip);
    $aiHelpIcon.addEventListener('mouseleave', _hideAiHelpTooltip);
    $aiHelpIcon.addEventListener('focus', _showAiHelpTooltip);
    $aiHelpIcon.addEventListener('blur', _hideAiHelpTooltip);
}

if ($btnLogout) {
    $btnLogout.addEventListener('click', () => {
        _stopAiActivePolling();
        api.logout();
    });
}
if ($projectBtnLogout) {
    $projectBtnLogout.addEventListener('click', () => {
        _stopAiActivePolling();
        api.logout();
    });
}

function openUploadPopup(files, targetPath = currentBrowsePath) {
    const projectName = (targetPath || '').split('/').filter(Boolean)[0] || '';
    if (!projectName) {
        alert('Select a project before uploading slides.');
        _showProjectGate(_projectListCache);
        return;
    }
    if (files) window._pendingUploadFiles = files;
    const w = 520, h = 600;
    const left = (screen.width - w) / 2, top = (screen.height - h) / 2;
    window.open(
        `/upload?path=${encodeURIComponent(targetPath || projectName)}`,
        'upload_popup',
        `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`
    );
}

$btnOpen?.addEventListener('click', () => $fileInput.click());
$fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) openUploadPopup(e.target.files);
    e.target.value = '';
});

window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'upload-complete') {
        loadSlideList();
        setStatus(`${e.data.count} files uploaded`);
    }
});

const SLIDE_EXT_PATTERN = /\.(svs|ndpi|tif|tiff|mrxs|vms|vmu|scn|isyntax|i2syntax)$/i;

async function uploadFiles(fileList, _targetPath) {
    const files = [...fileList].filter(f => SLIDE_EXT_PATTERN.test(f.name));
    if (!files.length) {
        setStatus('No supported slide files selected.');
        return;
    }
    openUploadPopup(fileList, _targetPath || currentBrowsePath);
}

async function uploadOneFile() { /* Deprecated compatibility shim. */ return null; }

const SCANNER_META = {
    'hamamatsu': {
        label: 'Hamamatsu',
        color: '#ee7800',
        svg: `<svg viewBox="0 0 80 20" xmlns="http://www.w3.org/2000/svg"><text x="0" y="15" font-family="Arial,sans-serif" font-size="15" font-weight="800" fill="#ee7800" letter-spacing="-0.5">HAMAMATSU</text></svg>`,
    },
    'aperio': {
        label: 'Leica',
        color: '#e20025',
        svg: `<svg viewBox="0 0 50 20" xmlns="http://www.w3.org/2000/svg"><rect x="0" y="2" width="50" height="16" rx="2" fill="#e20025"/><text x="25" y="14" font-family="Arial,sans-serif" font-size="11" font-weight="800" fill="#fff" text-anchor="middle" letter-spacing="1">LEICA</text></svg>`,
    },
    'leica': {
        label: 'Leica',
        color: '#e20025',
        svg: `<svg viewBox="0 0 50 20" xmlns="http://www.w3.org/2000/svg"><rect x="0" y="2" width="50" height="16" rx="2" fill="#e20025"/><text x="25" y="14" font-family="Arial,sans-serif" font-size="11" font-weight="800" fill="#fff" text-anchor="middle" letter-spacing="1">LEICA</text></svg>`,
    },
    'mirax': {
        label: '3DHistech MIRAX',
        color: '#00529c',
        svg: `<svg viewBox="0 0 90 20" xmlns="http://www.w3.org/2000/svg"><text x="0" y="15" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#00529c">3DHISTECH</text></svg>`,
    },
    '3dhistech': {
        label: '3DHistech',
        color: '#00529c',
        svg: `<svg viewBox="0 0 90 20" xmlns="http://www.w3.org/2000/svg"><text x="0" y="15" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#00529c">3DHISTECH</text></svg>`,
    },
    'philips': {
        label: 'Philips',
        color: '#0b5ed7',
        svg: `<svg viewBox="0 0 60 20" xmlns="http://www.w3.org/2000/svg"><text x="0" y="15" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="#0b5ed7" font-style="italic">PHILIPS</text></svg>`,
    },
    'ventana': {
        label: 'Ventana (Roche)',
        color: '#0066b3',
        svg: `<svg viewBox="0 0 70 20" xmlns="http://www.w3.org/2000/svg"><text x="0" y="15" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#0066b3">VENTANA</text></svg>`,
    },
    'sakura': {
        label: 'Sakura',
        color: '#0062a7',
        svg: `<svg viewBox="0 0 60 20" xmlns="http://www.w3.org/2000/svg"><text x="0" y="15" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="#0062a7">SAKURA</text></svg>`,
    },
    'olympus': {
        label: 'Olympus',
        color: '#004098',
        svg: `<svg viewBox="0 0 70 20" xmlns="http://www.w3.org/2000/svg"><text x="0" y="15" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#004098">OLYMPUS</text></svg>`,
    },
};
const $$slideScanners = [...document.querySelectorAll('.slide-scanner')];
const $slideScanner = $$slideScanners[0] || null;
function _updateScannerBadge(slideInfo) {
    if (!$$slideScanners.length) return;

    const rawVendor = slideInfo?.vendor
        || slideInfo?.str_vendor
        || slideInfo?.scanner
        || slideInfo?.str_scanner
        || slideInfo?.openslide_vendor
        || slideInfo?.properties?.['openslide.vendor']
        || '';
    const str_vendor = String(rawVendor || '').trim().toLowerCase();
    const rawObjective = slideInfo?.objective_power
        || slideInfo?.objective
        || slideInfo?.properties?.['openslide.objective-power']
        || '';
    const int_mag = rawObjective && rawObjective !== 'Unknown'
        ? `${String(rawObjective).replace(/x$/i, '')}x` : '';
    const float_mpp = Number(
        slideInfo?.mpp_x
        || slideInfo?.mpp
        || slideInfo?.float_mpp
        || slideInfo?.native_mpp
        || slideInfo?.properties?.['openslide.mpp-x']
        || 0
    );
    const str_mpp = float_mpp > 0 ? `${float_mpp.toFixed(3)} µm/px` : '';
    const list_details = [int_mag, str_mpp].filter(Boolean);
    const str_info = list_details.join(' · ');

    if ((!str_vendor || str_vendor === 'unknown') && !str_info) {
        $$slideScanners.forEach((el) => {
            el.hidden = true;
            el.innerHTML = '';
        });
        return;
    }

    let meta = null;
    for (const [key, m] of Object.entries(SCANNER_META)) {
        if (str_vendor.includes(key)) { meta = m; break; }
    }

    let html = '';
    let borderColor = '#6c5ce7';
    if (meta) {
        html = `
            <span class="scanner-logo" title="${_esc(meta.label)}">${meta.svg}</span>
            ${str_info ? `<span class="scanner-info">${_esc(str_info)}</span>` : ''}
        `;
        borderColor = meta.color;
    } else {
        html = `
            ${str_vendor && str_vendor !== 'unknown' ? `<span class="scanner-logo scanner-logo-text">${_esc(rawVendor)}</span>` : ''}
            ${str_info ? `<span class="scanner-info">${_esc(str_info)}</span>` : ''}
        `;
    }
    $$slideScanners.forEach((el) => {
        el.innerHTML = html;
        el.style.borderLeftColor = borderColor;
        el.hidden = false;
    });
}

const $btnNdpColor = document.getElementById('btn-ndp-color');
const $ndpColorState = $btnNdpColor ? $btnNdpColor.querySelector('.ndp-color-state') : null;

function _updateNdpColorToggleVisibility(slideInfo) {
    if (!$btnNdpColor) return;
    const str_vendor = String(
        slideInfo?.vendor
        || slideInfo?.str_vendor
        || slideInfo?.scanner
        || slideInfo?.str_scanner
        || slideInfo?.openslide_vendor
        || slideInfo?.properties?.['openslide.vendor']
        || ''
    ).toLowerCase();
    const bool_is_hamamatsu = str_vendor === 'hamamatsu';
    $btnNdpColor.hidden = !bool_is_hamamatsu;
    if (bool_is_hamamatsu) {
        viewer.setColorCorrectionEnabled(true);
        $btnNdpColor.classList.add('active');
        if ($ndpColorState) $ndpColorState.textContent = 'ON';
    } else {
        viewer.setColorCorrectionEnabled(false);
        $btnNdpColor.classList.remove('active');
        if ($ndpColorState) $ndpColorState.textContent = 'OFF';
    }
}

if ($btnNdpColor) {
    $btnNdpColor.addEventListener('click', () => {
        const bool_new = !$btnNdpColor.classList.contains('active');
        viewer.setColorCorrectionEnabled(bool_new);
        $btnNdpColor.classList.toggle('active', bool_new);
        if ($ndpColorState) $ndpColorState.textContent = bool_new ? 'ON' : 'OFF';
    });
}

function onSlideLoaded(slideId, slideInfo, filename) {
    currentSlideId = slideId;
    currentSlideInfo = { ...(slideInfo || {}), filename: filename || slideInfo?.filename || '' };

    _stickyAddClassId = null;
    _hideStickyHud();

    $slideName.textContent = filename;
    _updateScannerBadge(slideInfo);
    _updateNdpColorToggleVisibility(slideInfo);
    setStatus(`Loaded: ${slideInfo.dimensions[0]}x${slideInfo.dimensions[1]} (${slideInfo.level_count} levels)`);

    // Enable AI controls after a slide is loaded.
    $btnDetect.disabled = false;
    $btnVsMembrane.disabled = false;
    if ($btnPdScore) $btnPdScore.disabled = false;
    if ($btnIhcHer2) $btnIhcHer2.disabled = false;
    if ($btnIhcErPr) $btnIhcErPr.disabled = false;
    if ($btnIhcKi67) $btnIhcKi67.disabled = false;
    $btnInfo.disabled = false;
    document.querySelectorAll('.toggle-btn').forEach(b => b.disabled = false);
    document.querySelectorAll('input[name="tissue-type"], input[name="pd-tissue-type"]').forEach(el => {
        el.disabled = false;
    });

    if (!_isViewerRole()) {
        _applyFolderAiRestrictions(currentBrowsePath);
    }

    viewer.canEditDetectionResults = _canEditAiDetections();
    if (_isViewerRole()) {
        _applyViewerRoleRestrictions();
    }
    if (_isLabelerRole()) {
        _applyLabelerRoleRestrictions();
    }

    viewer.loadSlide(slideId, currentSlideInfo);

    if ($mousePosOverlay) $mousePosOverlay.hidden = false;

    // Load minimap for the current slide.
    loadMinimap(slideId);

    // Clear previous AI results.
    clearResults();

    // Reset VS IHC overlay state.
    viewer.clearVirtualStainOverlay();
    _setVsToggleState(false, true);
    _setVsSplitState(false, true);


    setProgress(0);
}

async function _applyFolderAiRestrictions(strFolderPath) {
    if (_isViewerRole()) return;

    let cfg = null;
    try {
        cfg = await api.getFolderAiConfig(strFolderPath || '');
    } catch (err) {
        console.warn('[folder-ai-restrict] load failed:', err);
        return;
    }
    if (_isViewerRole()) return;

    if (!cfg || !cfg.enabled || !Array.isArray(cfg.tasks) || cfg.tasks.length === 0) {
        return;
    }

    const set_allowed = new Set();
    for (const t of cfg.tasks) {
        if (t && t.model && t.variant) set_allowed.add(`${t.model}::${t.variant}`);
    }

    const _restrictRadios = (strName, strModel) => {
        const list_radios = document.querySelectorAll(`input[name="${strName}"]`);
        let bool_first_ok = null;
        let bool_current_ok = false;
        list_radios.forEach(el => {
            const bool_ok = set_allowed.has(`${strModel}::${el.value}`);
            el.disabled = !bool_ok;
            if (bool_ok && bool_first_ok === null) bool_first_ok = el;
            if (bool_ok && el.checked) bool_current_ok = true;
        });
        if (!bool_current_ok && bool_first_ok) {
            bool_first_ok.checked = true;
            bool_first_ok.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return bool_first_ok !== null;
    };

    // Quanti HE
    const bool_hnf_any = _restrictRadios('tissue-type', 'Quanti HE');
    $btnDetect.disabled = !bool_hnf_any;

    // Quanti PD-L1
    const bool_pd_any = _restrictRadios('pd-tissue-type', 'Quanti PD-L1');
    if ($btnPdScore) $btnPdScore.disabled = !bool_pd_any;

    if ($btnIhcHer2) $btnIhcHer2.disabled = !set_allowed.has('Quanti IHC::HER2');
    if ($btnIhcErPr) $btnIhcErPr.disabled = !set_allowed.has('Quanti IHC::ER_PR');
    if ($btnIhcKi67) $btnIhcKi67.disabled = !set_allowed.has('Quanti IHC::KI_67');

    const bool_vs_any = set_allowed.has('VS IHC::ihc_membrane');
    $btnVsMembrane.disabled = !bool_vs_any;

    const dict_tab_visible = {
        'hne-tab': bool_hnf_any,
        'vs-tab': bool_vs_any,
        'pd-tab': bool_pd_any,
        'ihc-tab': !!(
            set_allowed.has('Quanti IHC::HER2') ||
            set_allowed.has('Quanti IHC::ER_PR') ||
            set_allowed.has('Quanti IHC::KI_67')
        ),
    };

    let str_first_visible = null;
    for (const [str_tab_id, bool_show] of Object.entries(dict_tab_visible)) {
        const el_btn = document.querySelector(`.tab-btn[data-tab="${str_tab_id}"]`);
        const el_content = document.getElementById(str_tab_id);
        if (el_btn) {
            el_btn.style.display = bool_show ? '' : 'none';
            el_btn.classList.remove('active');
        }
        if (el_content) {
            el_content.classList.remove('active');
            el_content.style.display = bool_show ? '' : 'none';
        }
        if (bool_show && !str_first_visible) str_first_visible = str_tab_id;
    }

    // Activate the first visible tab.
    if (str_first_visible) {
        const el_new_btn = document.querySelector(`.tab-btn[data-tab="${str_first_visible}"]`);
        const el_new_content = document.getElementById(str_first_visible);
        if (el_new_btn) el_new_btn.classList.add('active');
        if (el_new_content) {
            el_new_content.style.display = '';
            el_new_content.classList.add('active');
        }
    }
}

function _applyViewerRoleRestrictions() {
    document.body.classList.add('role-viewer');
    _stopAiActivePolling();
    if (viewer) viewer.canEditDetectionResults = false;

    const list_draw_btns = ['btn-draw-polygon', 'btn-draw-rect',
                            'btn-draw-rect-1mm2', 'btn-draw-circle-1mm2', 'btn-ruler'];
    list_draw_btns.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.classList.remove('active');
            el.title = 'Viewer role cannot use annotation features.';
        }
    });
    if (viewer && viewer.drawMode) viewer.setDrawMode(null);

    // Disable AI action buttons for viewer role.
    const list_ai_btn_ids = [
        'btn-detect', 'btn-pd-score', 'btn-ihc-her2', 'btn-ihc-erpr',
        'btn-ihc-ki67', 'btn-vs-membrane', 'btn-vs-toggle', 'btn-vs-split',
        'btn-visualize', 'btn-clear-results', 'btn-save-results', 'btn-load-results',
    ];
    list_ai_btn_ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = 'Viewer role cannot use AI analysis features.';
        }
    });

    // Disable AI inputs for viewer role.
    document.querySelectorAll(
        '#right-panel .panel-group:first-child input, #right-panel .panel-group:first-child button'
    ).forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer role cannot use AI analysis features.';
    });

    ['btn-ann-clear', 'btn-ann-save', 'btn-ann-load',
     'btn-new-project', 'btn-rename-project', 'btn-delete-project'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = 'Viewer role cannot use annotation features.';
        }
    });

    document.querySelectorAll('.annotation-group button, .annotation-group input').forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer role cannot use annotation features.';
    });
}

function _applyLabelerRoleRestrictions() {
    document.body.classList.add('role-labeler');
    if (viewer) viewer.canEditDetectionResults = false;
    ['btn-save-results', 'btn-load-results',
     'btn-new-project', 'btn-rename-project', 'btn-delete-project'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = id === 'btn-save-results' || id === 'btn-load-results'
                ? 'Labeler role cannot save or load AI results.'
                : 'Labeler role cannot manage projects.';
        }
    });
}

// Viewer layout helpers.
const $viewerContainer = $('#viewer-container');

function _isFileDrag(e) {
    const t = e.dataTransfer && e.dataTransfer.types;
    if (!t) return false;
    // Support both DOMStringList and Array dataTransfer types.
    if (typeof t.contains === 'function') return t.contains('Files');
    return Array.from(t).includes('Files');
}

$viewerContainer.addEventListener('dragover', (e) => {
    if (!_isFileDrag(e)) return;
    e.preventDefault();
    $dropOverlay.classList.add('visible');
});
$viewerContainer.addEventListener('dragleave', (e) => {
    if (!_isFileDrag(e)) return;
    if (!$viewerContainer.contains(e.relatedTarget)) {
        $dropOverlay.classList.remove('visible');
    }
});
$viewerContainer.addEventListener('drop', (e) => {
    if (!_isFileDrag(e)) return;
    e.preventDefault();
    $dropOverlay.classList.remove('visible');
    if (e.dataTransfer.files.length > 0) uploadFiles(e.dataTransfer.files, currentBrowsePath);
});

let _minimapLoadToken = 0;
let _minimapRequestUrl = '';
let _minimapRequestImage = null;
let _minimapRequestSlideId = '';
function _paintMinimap(slideId, img) {
    if (!img || currentSlideId !== slideId || img.naturalWidth <= 0) return false;
    minimapImage = img;
    viewer.setThumbnailFallbackImage?.(slideId, img);
    $minimapCanvas.width = img.naturalWidth || img.width;
    $minimapCanvas.height = img.naturalHeight || img.height;
    $minimapCanvas.getContext('2d').drawImage(img, 0, 0);
    $minimapContainer.hidden = false;
    $minimapContainer.classList.remove('minimized');
    if ($minimapIcon) $minimapIcon.setAttribute('d', 'M3 7h8');
    _setMinimapDisplaySize(img);
    updateMinimap();
    return true;
}

function _trySidebarMinimap(slideId, token) {
    const thumb = document.querySelector(`.slide-list-item[data-slide-id="${slideId}"] .slide-thumb`);
    if (!thumb) return false;
    if (thumb.complete && thumb.naturalWidth > 0) {
        return _paintMinimap(slideId, thumb);
    }
    thumb.addEventListener('load', () => {
        if (token === _minimapLoadToken) _paintMinimap(slideId, thumb);
    }, { once: true });
    return false;
}

async function loadMinimap(slideId) {
    const token = ++_minimapLoadToken;
    minimapImage = null;
    if ($minimapContainer) $minimapContainer.hidden = true;
    if (_minimapRequestSlideId !== slideId) {
        _minimapRequestSlideId = slideId;
        _minimapRequestUrl = '';
        _minimapRequestImage = null;
    }

    _trySidebarMinimap(slideId, token);

    await api.ensureMediaReady();
    if (token !== _minimapLoadToken || currentSlideId !== slideId) return;
    const str_url = api.thumbnailUrl(slideId, 300, api.shouldUseNdpMatch?.(currentSlideInfo) || false, currentSlideInfo);
    if (!str_url || str_url === _minimapRequestUrl) return;
    const img = new Image();
    _minimapRequestUrl = str_url;
    _minimapRequestImage = img;
    img.onload = () => {
        if (token !== _minimapLoadToken) return;
        _paintMinimap(slideId, img);
    };
    img.onerror = () => {
        if (_minimapRequestImage === img) {
            _minimapRequestUrl = '';
            _minimapRequestImage = null;
            _minimapRequestSlideId = '';
        }
    };
    img.src = str_url;
}

function updateMinimap() {
    if (!minimapImage || !currentSlideInfo) return;
    const vr = viewer.getViewRect();
    if (!vr) return;
    const [imgW, imgH] = currentSlideInfo.dimensions;
    const displayW = $minimapCanvas.clientWidth || $minimapCanvas.width;
    const displayH = $minimapCanvas.clientHeight || $minimapCanvas.height;
    const sx = displayW / imgW;
    const sy = displayH / imgH;
    $minimapViewport.style.left = `${vr.x * sx}px`;
    $minimapViewport.style.top = `${vr.y * sy}px`;
    $minimapViewport.style.width = `${Math.max(4, vr.width * sx)}px`;
    $minimapViewport.style.height = `${Math.max(4, vr.height * sy)}px`;
}

function _navigateMinimapEvent(e) {
    if (!currentSlideInfo) return;
    const rect = $minimapCanvas.getBoundingClientRect();
    const [imgW, imgH] = currentSlideInfo.dimensions;
    const float_x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const float_y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    viewer.navigateTo(
        float_x * imgW,
        float_y * imgH
    );
}

let _minimapPanning = false;
$minimapCanvas.addEventListener('click', _navigateMinimapEvent);
$minimapCanvas.addEventListener('pointerdown', (e) => {
    if (!currentSlideInfo || e.button !== 0) return;
    e.preventDefault();
    _minimapPanning = true;
    $minimapCanvas.setPointerCapture?.(e.pointerId);
    _navigateMinimapEvent(e);
});
$minimapCanvas.addEventListener('pointermove', (e) => {
    if (!_minimapPanning) return;
    e.preventDefault();
    _navigateMinimapEvent(e);
});
function _stopMinimapPanning(e) {
    if (!_minimapPanning) return;
    _minimapPanning = false;
    try { $minimapCanvas.releasePointerCapture?.(e.pointerId); } catch (_) {}
}
$minimapCanvas.addEventListener('pointerup', _stopMinimapPanning);
$minimapCanvas.addEventListener('pointercancel', _stopMinimapPanning);

const $minimapToggle = $('#minimap-toggle');
const $minimapIcon = $('#minimap-toggle-icon');
$minimapToggle?.addEventListener('click', (e) => {
    e.stopPropagation();
    const minimized = $minimapContainer.classList.toggle('minimized');
    $minimapIcon.setAttribute('d', minimized ? 'M3 7h8M7 3v8' : 'M3 7h8');
    $minimapToggle.title = minimized ? 'Expand' : 'Minimize';
});

const $minimapResize = $('#minimap-resize');
const $minimapBody = $('#minimap-body');
let _minimapResizing = false;
let _minimapStartW = 0, _minimapStartX = 0;
const MINIMAP_MIN_W = 100, MINIMAP_MAX_W = 400;

$minimapResize?.addEventListener('pointerdown', (e) => {
    e.preventDefault(); e.stopPropagation();
    _minimapResizing = true;
    _minimapStartW = $minimapBody.offsetWidth;
    _minimapStartX = e.clientX;
    $minimapResize.setPointerCapture(e.pointerId);
});
$minimapResize?.addEventListener('pointermove', (e) => {
    if (!_minimapResizing) return;
    const dx = e.clientX - _minimapStartX;
    const newW = Math.min(MINIMAP_MAX_W, Math.max(MINIMAP_MIN_W, _minimapStartW + dx));
    $minimapBody.style.width = `${newW}px`;
    updateMinimap();
});
$minimapResize?.addEventListener('pointerup', () => { _minimapResizing = false; });
$minimapResize?.addEventListener('pointercancel', () => { _minimapResizing = false; });

// View controls.
$btnZoomIn.addEventListener('click', () => viewer.zoomIn());
$btnZoomOut.addEventListener('click', () => viewer.zoomOut());
$btnFit.addEventListener('click', () => viewer.fitToWindow());

const drawButtons = {
    polygon: $btnDrawPolygon,
    rectangle: $btnDrawRect,
    'rect-1mm2': $btnDrawRect1mm2,
    'circle-1mm2': $btnDrawCircle1mm2,
    ruler: $btnRuler,
};

function setDrawMode(mode) {
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    const newMode = viewer.drawMode === mode ? null : mode;
    viewer.setDrawMode(newMode);
    Object.values(drawButtons).forEach(b => { if (b) b.classList.remove('active'); });
    if (newMode && drawButtons[newMode]) drawButtons[newMode].classList.add('active');
}

$btnDrawPolygon.addEventListener('click', () => setDrawMode('polygon'));
$btnDrawRect.addEventListener('click', () => setDrawMode('rectangle'));
if ($btnDrawRect1mm2) $btnDrawRect1mm2.addEventListener('click', () => setDrawMode('rect-1mm2'));
if ($btnDrawCircle1mm2) $btnDrawCircle1mm2.addEventListener('click', () => setDrawMode('circle-1mm2'));
if ($btnRuler) $btnRuler.addEventListener('click', () => setDrawMode('ruler'));

const $btnUxHelp = $('#btn-ux-help');
const $uxHelpModal = $('#shortcuts-modal');
const $uxHelpClose = $('#shortcuts-close');
const $shortcutPreview = $('#shortcut-preview-popover');
const $shortcutPreviewVideo = $('#shortcut-preview-video');
const $shortcutVideoModal = $('#shortcut-video-modal');
const $shortcutVideoLarge = $('#shortcut-video-large');
const $shortcutVideoClose = $('#shortcut-video-close');
function _openUxHelp() { if ($uxHelpModal) $uxHelpModal.classList.add('visible'); }
function _hideShortcutPreview() {
    if (!$shortcutPreview || !$shortcutPreviewVideo) return;
    $shortcutPreview.hidden = true;
    $shortcutPreviewVideo.pause();
    $shortcutPreviewVideo.removeAttribute('src');
    $shortcutPreviewVideo.load();
}
function _hideShortcutVideoModal() {
    if (!$shortcutVideoModal || !$shortcutVideoLarge) return;
    $shortcutVideoModal.hidden = true;
    $shortcutVideoLarge.pause();
    $shortcutVideoLarge.removeAttribute('src');
    $shortcutVideoLarge.load();
}
function _closeUxHelp() {
    if ($uxHelpModal) $uxHelpModal.classList.remove('visible');
    _hideShortcutPreview();
    _hideShortcutVideoModal();
}
function _positionShortcutPreview(row) {
    if (!$shortcutPreview) return;
    const rect = row.getBoundingClientRect();
    const popWidth = 330;
    const popHeight = 196;
    const gap = 14;
    const viewportPad = 12;
    let left = rect.right + gap;
    if (left + popWidth > window.innerWidth - viewportPad) {
        left = rect.left - popWidth - gap;
    }
    left = Math.max(viewportPad, Math.min(left, window.innerWidth - popWidth - viewportPad));
    let top = rect.top + (rect.height / 2) - (popHeight / 2);
    top = Math.max(viewportPad, Math.min(top, window.innerHeight - popHeight - viewportPad));
    $shortcutPreview.style.left = `${left}px`;
    $shortcutPreview.style.top = `${top}px`;
}
function _showShortcutPreview(row) {
    if (!$shortcutPreview || !$shortcutPreviewVideo || !row?.dataset.preview) return;
    const src = `assets/info_video/${row.dataset.preview}.mp4`;
    _positionShortcutPreview(row);
    if (!$shortcutPreviewVideo.src.endsWith(src)) {
        $shortcutPreviewVideo.src = src;
        $shortcutPreviewVideo.load();
    }
    $shortcutPreview.hidden = false;
    $shortcutPreviewVideo.currentTime = 0;
    $shortcutPreviewVideo.play().catch(() => {});
}
function _showShortcutVideoModal(row) {
    if (!$shortcutVideoModal || !$shortcutVideoLarge || !row?.dataset.preview) return;
    const src = `assets/info_video/${row.dataset.preview}.mp4`;
    _hideShortcutPreview();
    $shortcutVideoLarge.src = src;
    $shortcutVideoLarge.load();
    $shortcutVideoModal.hidden = false;
    $shortcutVideoLarge.currentTime = 0;
    $shortcutVideoLarge.play().catch(() => {});
}
if ($btnUxHelp) $btnUxHelp.addEventListener('click', _openUxHelp);
if ($uxHelpClose) $uxHelpClose.addEventListener('click', _closeUxHelp);
if ($shortcutVideoClose) $shortcutVideoClose.addEventListener('click', _hideShortcutVideoModal);
if ($shortcutVideoModal) {
    $shortcutVideoModal.addEventListener('click', (e) => {
        if (e.target === $shortcutVideoModal) _hideShortcutVideoModal();
    });
}
if ($uxHelpModal) {
    $uxHelpModal.addEventListener('click', (e) => {
        if (e.target === $uxHelpModal) _closeUxHelp();
    });
    $uxHelpModal.querySelectorAll('.shortcut-row[data-preview]').forEach(row => {
        row.tabIndex = 0;
        row.addEventListener('mouseenter', () => _showShortcutPreview(row));
        row.addEventListener('focusin', () => _showShortcutPreview(row));
        row.addEventListener('mousemove', () => _positionShortcutPreview(row));
        row.addEventListener('mouseleave', _hideShortcutPreview);
        row.addEventListener('focusout', _hideShortcutPreview);
        row.addEventListener('click', () => _showShortcutVideoModal(row));
        row.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                _showShortcutVideoModal(row);
            }
        });
    });
}
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && $shortcutVideoModal && !$shortcutVideoModal.hidden) {
        _hideShortcutVideoModal();
        return;
    }
    if (e.key === 'Escape' && $uxHelpModal && $uxHelpModal.classList.contains('visible')) {
        _closeUxHelp();
    }
});

const $btnToggleLeft = $('#btn-toggle-left');
const $btnToggleRight = $('#btn-toggle-right');
const $mobileBackdrop = $('#mobile-backdrop');
function _closeMobilePanels() {
    document.body.classList.remove('panel-left-open');
    document.body.classList.remove('panel-right-open');
}
function _toggleMobilePanel(str_side) {
    const str_cls_open = str_side === 'left' ? 'panel-left-open' : 'panel-right-open';
    const str_cls_other = str_side === 'left' ? 'panel-right-open' : 'panel-left-open';
    const bool_is_open = document.body.classList.contains(str_cls_open);
    document.body.classList.remove(str_cls_other);
    document.body.classList.toggle(str_cls_open, !bool_is_open);
}
if ($btnToggleLeft) $btnToggleLeft.addEventListener('click', () => _toggleMobilePanel('left'));
if ($btnToggleRight) $btnToggleRight.addEventListener('click', () => _toggleMobilePanel('right'));
if ($mobileBackdrop) $mobileBackdrop.addEventListener('click', _closeMobilePanels);
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (document.body.classList.contains('panel-left-open') ||
                                document.body.classList.contains('panel-right-open'))) {
        _closeMobilePanels();
    }
});
window.matchMedia('(max-width: 900px)').addEventListener('change', (e) => {
    if (!e.matches) _closeMobilePanels();
});

// Sync toolbar buttons when draw mode changes.
viewer.onDrawModeChange = (mode) => {
    Object.values(drawButtons).forEach(b => { if (b) b.classList.remove('active'); });
    if (mode && drawButtons[mode]) drawButtons[mode].classList.add('active');
};

const $annList = $('#annotation-list');
const $btnAnnClear = $('#btn-ann-clear');
const $btnAnnSave = $('#btn-ann-save');
const $btnAnnLoad = $('#btn-ann-load');

function renderAnnotationPanel() {
    if (!$annList) return;
    $annList.innerHTML = '';
    for (const ann of viewer.annotations) {
        const [r, g, b] = ann.color;
        const el = document.createElement('div');
        el.className = 'ann-item' + (ann.selected ? ' selected' : '');
        el.dataset.id = ann.id;
        el.innerHTML = `
            <input type="color" class="ann-color-swatch" value="${rgbToHex(r, g, b)}"
                   title="Change color" style="background:rgb(${r},${g},${b})">
            <span class="ann-name" title="Double-click to rename">${_esc(ann.name)}</span>
            <span class="ann-type">${_esc(ann.type)}</span>
            <button class="ann-btn-vis" title="Toggle visibility">${ann.visible ? 'Hide' : 'Show'}</button>
            <button class="ann-btn-del" title="Delete">Del</button>
        `;
        el.addEventListener('click', (e) => {
            if (e.target.closest('.ann-color-swatch') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') || e.target.closest('.ann-name-input')) return;
            viewer.selectAnnotation(ann.id);
        });
        // Rename on double click.
        el.querySelector('.ann-name').addEventListener('dblclick', (e) => {
            e.stopPropagation();
            const nameSpan = e.target;
            const input = document.createElement('input');
            input.className = 'ann-name-input';
            input.value = ann.name;
            nameSpan.replaceWith(input);
            input.focus();
            input.select();
            const finish = () => {
                ann.name = input.value.trim() || ann.name;
                if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
                renderAnnotationPanel();
            };
            input.addEventListener('blur', finish);
            input.addEventListener('keydown', (ke) => { if (ke.key === 'Enter') input.blur(); });
        });
        // Change annotation color.
        el.querySelector('.ann-color-swatch').addEventListener('input', (e) => {
            const hex = e.target.value;
            ann.color = hexToRgb(hex);
            e.target.style.background = `rgb(${ann.color[0]},${ann.color[1]},${ann.color[2]})`;
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
        });
        el.querySelector('.ann-btn-vis').addEventListener('click', (e) => {
            e.stopPropagation();
            ann.visible = !ann.visible;
            viewer.requestRender();
            renderAnnotationPanel();
        });
        el.querySelector('.ann-btn-del').addEventListener('click', (e) => {
            e.stopPropagation();
            viewer.deleteAnnotation(ann.id);
        });
        $annList.appendChild(el);
    }
}

function rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}
function hexToRgb(hex) {
    const m = hex.match(/^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 255, 0];
}

// Sync the annotation panel with viewer events.
viewer.onAnnotationCreated = (ann) => {
    setStatus(`${ann.name} created`);
    renderAnnotationPanel();
};
viewer.onAnnotationSelected = (ann) => {
    renderAnnotationPanel();
};
viewer.onAnnotationDeleted = (ann) => {
    renderAnnotationPanel();
};
viewer.onAnnotationChanged = (ann) => {
    renderAnnotationPanel();
};

const _origDelete = viewer.deleteAnnotation.bind(viewer);
viewer.deleteAnnotation = (id) => {
    const ann = viewer.annotations.find(a => a.id === id);
    _origDelete(id);
    if (ann && viewer.onAnnotationDeleted) viewer.onAnnotationDeleted(ann);
};

let _cellEditPopupEl = null;

function _closeCellEditPopup() {
    if (_cellEditPopupEl) {
        _cellEditPopupEl.remove();
        _cellEditPopupEl = null;
    }
    viewer.clearCellHighlight();
    viewer.clearMultiCellHighlight();
    viewer.clearHiddenCellHighlight?.();
    _cellEditCtx = null;
    document.removeEventListener('mousedown', _outsideCellEditClick, true);
    document.removeEventListener('keydown', _cellEditKeydown, true);
}

function _outsideCellEditClick(e) {
    if (_cellEditPopupEl && !_cellEditPopupEl.contains(e.target)) {
        _closeCellEditPopup();
    }
}

let _cellEditCtx = null; // {idx, classNames, classColors}

function _cellEditKeydown(e) {
    if (!_cellEditCtx) return;
    if (e.key === 'Escape') {
        _closeCellEditPopup();
        e.preventDefault();
        return;
    }
    if ((e.key === 'Delete' || e.key.toLowerCase() === 'd') &&
            _cellEditCtx.mode !== 'add' && _cellEditCtx.mode !== 'sticky-pick') {
        _doDeleteCell();
        e.preventDefault();
        return;
    }
    if (/^[0-9]$/.test(e.key)) {
        const num = parseInt(e.key, 10);
        const slot = num === 0 ? 9 : num - 1;
        if (_cellEditCtx.classButtonOrder && slot < _cellEditCtx.classButtonOrder.length) {
            const targetCls = _cellEditCtx.classButtonOrder[slot];
            if (_cellEditCtx.mode === 'add' || _cellEditCtx.mode === 'sticky-pick') {
                _doAddCell(targetCls);
            } else {
                _doChangeClass(targetCls);
            }
            e.preventDefault();
        }
    }
}

function _doDeleteCell() {
    if (!_cellEditCtx) return;
    if (_cellEditCtx.hiddenOther) {
        _closeCellEditPopup();
        return;
    }
    if (_cellEditCtx.multi) {
        viewer.deleteCells(_cellEditCtx.indices);
    } else {
        viewer.deleteCell(_cellEditCtx.idx);
    }
    _closeCellEditPopup();
}

function _doChangeClass(newClsId) {
    if (!_cellEditCtx) return;
    const name = _cellEditCtx.classNames[String(newClsId)] || `Class ${newClsId}`;
    if (_cellEditCtx.hiddenOther) {
        viewer.promoteHiddenCells?.(_cellEditCtx.indices, newClsId, name);
    } else if (_cellEditCtx.multi) {
        viewer.changeCellsClass(_cellEditCtx.indices, newClsId, name);
    } else {
        viewer.changeCellClass(_cellEditCtx.idx, newClsId, name);
    }
    _closeCellEditPopup();
}

function _toCssColor(c) {
    if (typeof c === 'string') return c;
    if (Array.isArray(c) && c.length >= 3) return `rgb(${c[0]},${c[1]},${c[2]})`;
    return 'rgb(200,200,200)';
}

function _makeCellEditPopupDraggable(popup, handle) {
    if (!popup || !handle) return;
    handle.style.cursor = 'move';
    handle.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        const tag = (e.target && e.target.tagName || '').toLowerCase();
        if (tag === 'button' || tag === 'input' || tag === 'select' || tag === 'textarea') return;
        e.preventDefault();
        e.stopPropagation();

        const rect = popup.getBoundingClientRect();
        const offsetX = e.clientX - rect.left;
        const offsetY = e.clientY - rect.top;

        const move = (ev) => {
            const maxX = Math.max(4, window.innerWidth - popup.offsetWidth - 4);
            const maxY = Math.max(4, window.innerHeight - popup.offsetHeight - 4);
            const x = Math.max(4, Math.min(maxX, ev.clientX - offsetX));
            const y = Math.max(4, Math.min(maxY, ev.clientY - offsetY));
            popup.style.left = `${x}px`;
            popup.style.top = `${y}px`;
        };
        const up = () => {
            document.removeEventListener('mousemove', move, true);
            document.removeEventListener('mouseup', up, true);
        };

        document.addEventListener('mousemove', move, true);
        document.addEventListener('mouseup', up, true);
    });
}

/**
 */
function _attachClassRenamePencil(btnEl, classId, textSpan) {
    const pencil = document.createElement('span');
    pencil.title = 'Rename label';
    pencil.setAttribute('aria-label', 'Rename label');
    pencil.style.cssText = `
        flex:0 0 26px; width:26px; height:26px; margin:2px 5px 2px 0;
        display:flex; align-items:center; justify-content:center;
        border-radius:4px; cursor:pointer; opacity:0.65;
        color:#555; box-sizing:border-box;
    `;
    pencil.innerHTML = `<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11.8 3.4l4.8 4.8-8.7 8.7-4.9 1 1-4.9z"/><path d="M10.5 4.7l4.8 4.8"/></svg>`;
    pencil.onmouseover = () => { pencil.style.opacity = '1'; pencil.style.background = 'rgba(0,0,0,0.08)'; };
    pencil.onmouseout = () => { pencil.style.opacity = '0.65'; pencil.style.background = 'transparent'; };
    pencil.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const original = textSpan.textContent || '';
        const m = original.match(/^\[\d\]\s+(.*)$/);
        const initialName = (m ? m[1] : original).trim();

        const wrap = document.createElement('span');
        wrap.style.cssText = 'flex:1; display:flex; align-items:center; gap:4px; padding:4px 6px;';
        const input = document.createElement('input');
        input.type = 'text';
        input.value = initialName;
        input.style.cssText = `
            flex:1; min-width:0; padding:3px 6px;
            border:1px solid #4a90d9; border-radius:3px;
            font-size:12px; font-family:inherit;
        `;
        const ok = document.createElement('button');
        ok.textContent = 'OK';
        ok.title = 'Apply (Enter)';
        ok.style.cssText = `
            flex:0 0 22px; height:22px; padding:0;
            background:#27ae60; color:#fff; border:none;
            border-radius:3px; cursor:pointer; font-weight:700;
        `;
        const cancel = document.createElement('button');
        cancel.textContent = 'X';
        cancel.title = 'Cancel (Esc)';
        cancel.style.cssText = `
            flex:0 0 22px; height:22px; padding:0;
            background:#e74c3c; color:#fff; border:none;
            border-radius:3px; cursor:pointer; font-weight:700;
        `;
        wrap.append(input, ok, cancel);

        const parent = textSpan.parentElement;
        parent.removeChild(textSpan);
        parent.insertBefore(wrap, pencil);
        pencil.style.display = 'none';

        input.addEventListener('keydown', (kev) => {
            kev.stopPropagation();
            if (kev.key === 'Enter') { commit(); }
            else if (kev.key === 'Escape') { abort(); }
        });
        input.addEventListener('mousedown', (mev) => mev.stopPropagation());
        ok.addEventListener('click', (mev) => { mev.stopPropagation(); commit(); });
        cancel.addEventListener('click', (mev) => { mev.stopPropagation(); abort(); });

        const restoreText = () => {
            wrap.remove();
            parent.insertBefore(textSpan, pencil);
            pencil.style.display = '';
        };
        const abort = () => { restoreText(); };
        const commit = () => {
            const str_new = input.value.trim();
            if (!str_new || str_new === initialName) { restoreText(); return; }
            const ok2 = _renameClassLabel(classId, str_new);
            if (ok2) {
                textSpan.textContent = m ? `[${m[0].match(/\d/)[0]}] ${str_new}` : str_new;
            }
            restoreText();
        };

        setTimeout(() => { input.focus(); input.select(); }, 0);
    });
    btnEl.appendChild(pencil);
}

/**
 */
function _renameClassLabel(classId, newName) {
    if (!_lastDetectionResult) return false;
    const str_new = String(newName || '').trim();
    if (!str_new) return false;
    if (!_lastDetectionResult.class_names) _lastDetectionResult.class_names = {};
    _lastDetectionResult.class_names[String(classId)] = str_new;
    if (Array.isArray(viewer.detectionCells)) {
        for (const cell of viewer.detectionCells) {
            if (cell.class_id === classId) cell.class_name = str_new;
        }
    }
    buildResultList(_lastDetectionResult);
    _updateResultCounts();
    setStatus(`Class ${classId} renamed to "${str_new}"`);
    return true;
}

function _showCellEditPopup(idx, cell, screenX, screenY) {
    if (!_canEditAiDetections()) return;
    _closeCellEditPopup();
    if (!_lastDetectionResult) return;

    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};
    const curCls = cell.class_id;
    const curName = classNames[String(curCls)] || `Class ${curCls}`;
    const curColorCss = _toCssColor(classColors[String(curCls)]);
    const curConf = cell.confidence ?? 0;

    const popup = document.createElement('div');
    popup.className = 'cell-edit-popup';
    popup.style.cssText = `
        position: fixed; z-index: 9999;
        background: #ffffff; color: #222;
        border: 1px solid #ccc; border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        padding: 10px 12px; min-width: 200px;
        font-family: sans-serif; font-size: 12px;
        user-select: none;
    `;

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const swatch = document.createElement('span');
    swatch.style.cssText = `display:inline-block;width:14px;height:14px;border-radius:3px;
        border:1px solid #888;background:${curColorCss};`;
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>${curName}</b>  (conf: ${curConf.toFixed(2)})`;
    header.append(swatch, headerLabel);
    popup.appendChild(header);
    _makeCellEditPopupDraggable(popup, header);

    const sep1 = document.createElement('div');
    sep1.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep1);

    const labelChange = document.createElement('div');
    labelChange.textContent = 'Change Class:';
    labelChange.style.cssText = 'margin-bottom:4px;';
    popup.appendChild(labelChange);

    const classButtonOrder = [];
    const sortedClsIds = Object.keys(classNames)
        .map(k => parseInt(k, 10))
        .sort((a, b) => a - b);

    let keyIdx = 0;
    for (const cid of sortedClsIds) {
        if (cid === curCls) continue;
        const name = classNames[String(cid)];
        const colorCss = _toCssColor(classColors[String(cid)]);
        const keyLabel = keyIdx < 10 ? String((keyIdx + 1) % 10) : '';

        const btn = document.createElement('button');
        btn.style.cssText = `
            display:flex;align-items:center;gap:0;
            width:100%;margin:3px 0;padding:0;
            background:#f0f0f0;color:#222;
            border:1px solid #ccc;border-radius:4px;
            font-size:12px;cursor:pointer;text-align:left;
            box-sizing:border-box;overflow:hidden;
            min-height:30px;
        `;
        btn.onmouseover = () => { btn.style.background = '#4a90d9'; btn.style.color = '#fff'; };
        btn.onmouseout = () => { btn.style.background = '#f0f0f0'; btn.style.color = '#222'; };

        const stripe = document.createElement('span');
        stripe.style.cssText = `flex:0 0 12px;align-self:stretch;
            background:${colorCss};display:block;`;

        // Class color swatch.
        const sw = document.createElement('span');
        sw.style.cssText = `flex:0 0 16px;height:16px;border-radius:3px;
            background:${colorCss};border:1px solid #333;
            display:inline-block;margin-left:8px;`;

        const text = document.createElement('span');
        text.textContent = keyLabel ? `[${keyLabel}] ${name}` : name;
        text.style.cssText = 'flex:1;min-width:0;padding:6px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

        btn.append(stripe, sw, text);
        btn.addEventListener('click', () => _doChangeClass(cid));
        _attachClassRenamePencil(btn, cid, text);
        popup.appendChild(btn);

        classButtonOrder.push(cid);
        keyIdx++;
    }

    const sep2 = document.createElement('div');
    sep2.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep2);

    const delBtn = document.createElement('button');
    delBtn.textContent = 'Delete Cell  (Del / D)';
    delBtn.style.cssText = `
        display:block;width:100%;padding:7px 10px;
        background:#fdecea;color:#c0392b;
        border:1px solid #e74c3c;border-radius:4px;
        font-size:12px;cursor:pointer;font-weight:600;
    `;
    delBtn.onmouseover = () => { delBtn.style.background = '#e74c3c'; delBtn.style.color = '#fff'; };
    delBtn.onmouseout = () => { delBtn.style.background = '#fdecea'; delBtn.style.color = '#c0392b'; };
    delBtn.addEventListener('click', _doDeleteCell);
    popup.appendChild(delBtn);

    document.body.appendChild(popup);

    const pw = popup.offsetWidth;
    const ph = popup.offsetHeight;
    let px = screenX;
    let py = screenY;
    if (px + pw > window.innerWidth) px = window.innerWidth - pw - 8;
    if (py + ph > window.innerHeight) py = window.innerHeight - ph - 8;
    popup.style.left = `${Math.max(4, px)}px`;
    popup.style.top = `${Math.max(4, py)}px`;

    _cellEditPopupEl = popup;
    _cellEditCtx = { idx, classNames, classColors, classButtonOrder };

    // Register outside click and keyboard handlers after the popup is mounted.
    setTimeout(() => {
        document.addEventListener('mousedown', _outsideCellEditClick, true);
        document.addEventListener('keydown', _cellEditKeydown, true);
    }, 0);
}

viewer.onCellEditRequested = _showCellEditPopup;

let _stickyAddClassId = null;

let _stickyHudEl = null;
let _stickyHudShiftHeld = false;
let _stickyHudLastMouse = { x: 0, y: 0 };

function _ensureStickyHud() {
    if (_stickyHudEl) return _stickyHudEl;
    const el = document.createElement('div');
    el.id = 'sticky-class-hud';
    el.style.cssText = `
        position: fixed; z-index: 9998;
        display: none;
        align-items: center; gap: 6px;
        padding: 4px 10px 4px 6px;
        background: rgba(20,20,30,0.88); color: #fff;
        border-radius: 14px;
        font-family: sans-serif; font-size: 12px; font-weight: 600;
        box-shadow: 0 2px 8px rgba(0,0,0,0.35);
        pointer-events: none; user-select: none;
        white-space: nowrap;
    `;
    const dot = document.createElement('span');
    dot.className = '_dot';
    dot.style.cssText = 'width:10px;height:10px;border-radius:50%;border:1px solid rgba(255,255,255,0.6);display:inline-block;';
    const txt = document.createElement('span');
    txt.className = '_txt';
    el.append(dot, txt);
    document.body.appendChild(el);
    _stickyHudEl = el;
    return el;
}

function _updateStickyHudContent() {
    if (!_stickyHudEl) return false;
    if (_stickyAddClassId == null || !_lastDetectionResult) return false;
    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};
    const name = classNames[String(_stickyAddClassId)];
    if (!name) return false;
    _stickyHudEl.querySelector('._dot').style.background = _toCssColor(classColors[String(_stickyAddClassId)]);
    _stickyHudEl.querySelector('._txt').textContent = name;
    return true;
}

function _positionStickyHud() {
    if (!_stickyHudEl) return;
    let x = _stickyHudLastMouse.x + 14;
    let y = _stickyHudLastMouse.y - 28;
    const w = _stickyHudEl.offsetWidth;
    if (x + w > window.innerWidth - 4) x = _stickyHudLastMouse.x - w - 14;
    if (y < 4) y = _stickyHudLastMouse.y + 18;
    _stickyHudEl.style.left = `${Math.max(4, x)}px`;
    _stickyHudEl.style.top  = `${Math.max(4, y)}px`;
}

function _showStickyHud() {
    if (!_stickyHudShiftHeld) return;
    if (_stickyAddClassId == null) return;
    if (!_lastDetectionResult) return;
    if (viewer && viewer.drawMode) return;
    _ensureStickyHud();
    if (!_updateStickyHudContent()) return;
    _stickyHudEl.style.display = 'inline-flex';
    _positionStickyHud();
}

function _hideStickyHud() {
    if (_stickyHudEl) _stickyHudEl.style.display = 'none';
}

window.addEventListener('keydown', (e) => {
    if (e.key === 'Alt' && !_stickyHudShiftHeld) {
        document.body.classList.add('viewer-alt-held');
        _stickyHudShiftHeld = true;
        _showStickyHud();
    }
}, true);
window.addEventListener('keyup', (e) => {
    if (e.key === 'Alt') {
        document.body.classList.remove('viewer-alt-held');
        _stickyHudShiftHeld = false;
        _hideStickyHud();
    }
}, true);
window.addEventListener('blur', () => {
    document.body.classList.remove('viewer-alt-held');
    _stickyHudShiftHeld = false;
    _hideStickyHud();
});
document.addEventListener('mousemove', (e) => {
    _stickyHudLastMouse.x = e.clientX;
    _stickyHudLastMouse.y = e.clientY;
    if (_stickyHudShiftHeld && _stickyHudEl && _stickyHudEl.style.display !== 'none') {
        _positionStickyHud();
    }
}, true);

function _showCellAddPopup(sx, sy, screenX, screenY) {
    if (!_canEditAiDetections()) return;
    _closeCellEditPopup();
    if (!_lastDetectionResult) return;

    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};

    if (_stickyAddClassId != null && classNames[String(_stickyAddClassId)]) {
        const str_name = classNames[String(_stickyAddClassId)];
        viewer.addCell(sx, sy, _stickyAddClassId, str_name);
        setStatus(`Cell added: ${str_name} - Alt+right-click to add, Alt+A to change`);
        return;
    }

    const popup = document.createElement('div');
    popup.className = 'cell-edit-popup';
    popup.style.cssText = `
        position: fixed; z-index: 9999;
        background: #ffffff; color: #222;
        border: 1px solid #ccc; border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        padding: 10px 12px; min-width: 200px;
        font-family: sans-serif; font-size: 12px;
        user-select: none;
    `;

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>Add Cell</b>  (${Math.round(sx).toLocaleString()}, ${Math.round(sy).toLocaleString()})`;
    header.appendChild(headerLabel);
    popup.appendChild(header);
    _makeCellEditPopupDraggable(popup, header);

    const sep = document.createElement('div');
    sep.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep);

    const label = document.createElement('div');
    label.textContent = 'Class:';
    label.style.cssText = 'margin-bottom:4px;';
    popup.appendChild(label);

    const sortedClsIds = Object.keys(classNames)
        .map(k => parseInt(k, 10))
        .sort((a, b) => a - b);

    const classButtonOrder = [];
    let keyIdx = 0;
    for (const cid of sortedClsIds) {
        const name = classNames[String(cid)];
        const colorCss = _toCssColor(classColors[String(cid)]);
        const keyLabel = keyIdx < 10 ? String((keyIdx + 1) % 10) : '';

        const btn = document.createElement('button');
        btn.style.cssText = `
            display:flex;align-items:center;gap:0;
            width:100%;margin:3px 0;padding:0;
            background:#f0f0f0;color:#222;
            border:1px solid #ccc;border-radius:4px;
            font-size:12px;cursor:pointer;text-align:left;
            box-sizing:border-box;overflow:hidden;
            min-height:30px;
        `;
        btn.onmouseover = () => { btn.style.background = '#4a90d9'; btn.style.color = '#fff'; };
        btn.onmouseout = () => { btn.style.background = '#f0f0f0'; btn.style.color = '#222'; };

        const stripe = document.createElement('span');
        stripe.style.cssText = `flex:0 0 12px;align-self:stretch;
            background:${colorCss};display:block;`;
        const sw = document.createElement('span');
        sw.style.cssText = `flex:0 0 16px;height:16px;border-radius:3px;
            background:${colorCss};border:1px solid #333;
            display:inline-block;margin-left:8px;`;
        const text = document.createElement('span');
        text.textContent = keyLabel ? `[${keyLabel}] ${name}` : name;
        text.style.cssText = 'flex:1;min-width:0;padding:6px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

        btn.append(stripe, sw, text);
        btn.addEventListener('click', () => _doAddCell(cid));
        _attachClassRenamePencil(btn, cid, text);
        popup.appendChild(btn);

        classButtonOrder.push(cid);
        keyIdx++;
    }

    document.body.appendChild(popup);

    const pw = popup.offsetWidth;
    const ph = popup.offsetHeight;
    let px = screenX;
    let py = screenY;
    if (px + pw > window.innerWidth) px = window.innerWidth - pw - 8;
    if (py + ph > window.innerHeight) py = window.innerHeight - ph - 8;
    popup.style.left = `${Math.max(4, px)}px`;
    popup.style.top = `${Math.max(4, py)}px`;

    _cellEditPopupEl = popup;
    _cellEditCtx = { mode: 'add', sx, sy, classNames, classColors, classButtonOrder };

    setTimeout(() => {
        document.addEventListener('mousedown', _outsideCellEditClick, true);
        document.addEventListener('keydown', _cellEditKeydown, true);
    }, 0);
}

function _doAddCell(classId) {
    if (!_cellEditCtx) return;
    const name = _cellEditCtx.classNames[String(classId)] || `Class ${classId}`;
    if (_cellEditCtx.mode === 'add') {
        viewer.addCell(_cellEditCtx.sx, _cellEditCtx.sy, classId, name);
        _stickyAddClassId = classId;
        setStatus(`Sticky class: ${name} - Alt+right-click to add, Alt+A to change`);
    } else if (_cellEditCtx.mode === 'sticky-pick') {
        _stickyAddClassId = classId;
        setStatus(`Sticky class: ${name} - Alt+right-click to add`);
    }
    _closeCellEditPopup();
}

/**
 */
function _showStickyClassPickerPopup(screenX, screenY) {
    _closeCellEditPopup();
    if (!_lastDetectionResult) return;

    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};

    const popup = document.createElement('div');
    popup.className = 'cell-edit-popup';
    popup.style.cssText = `
        position: fixed; z-index: 9999;
        background: #ffffff; color: #222;
        border: 1px solid #ccc; border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        padding: 10px 12px; min-width: 200px;
        font-family: sans-serif; font-size: 12px;
        user-select: none;
    `;

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>Pick Sticky Class</b>  <span style="opacity:0.6">(select the class to add)</span>`;
    header.appendChild(headerLabel);
    popup.appendChild(header);
    _makeCellEditPopupDraggable(popup, header);

    const sep = document.createElement('div');
    sep.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep);

    const sortedClsIds = Object.keys(classNames)
        .map(k => parseInt(k, 10))
        .sort((a, b) => a - b);

    const classButtonOrder = [];
    let keyIdx = 0;
    for (const cid of sortedClsIds) {
        const name = classNames[String(cid)];
        const colorCss = _toCssColor(classColors[String(cid)]);
        const keyLabel = keyIdx < 10 ? String((keyIdx + 1) % 10) : '';
        const isCurrent = (cid === _stickyAddClassId);

        const btn = document.createElement('button');
        btn.style.cssText = `
            display:flex;align-items:center;gap:0;
            width:100%;margin:3px 0;padding:0;
            background:${isCurrent ? '#dfe9f5' : '#f0f0f0'};color:#222;
            border:1px solid ${isCurrent ? '#4a90d9' : '#ccc'};border-radius:4px;
            font-size:12px;cursor:pointer;text-align:left;
            box-sizing:border-box;overflow:hidden;
            min-height:30px;
        `;
        btn.onmouseover = () => { btn.style.background = '#4a90d9'; btn.style.color = '#fff'; };
        btn.onmouseout = () => {
            btn.style.background = isCurrent ? '#dfe9f5' : '#f0f0f0';
            btn.style.color = '#222';
        };

        const stripe = document.createElement('span');
        stripe.style.cssText = `flex:0 0 12px;align-self:stretch;background:${colorCss};display:block;`;
        const sw = document.createElement('span');
        sw.style.cssText = `flex:0 0 16px;height:16px;border-radius:3px;
            background:${colorCss};border:1px solid #333;
            display:inline-block;margin-left:8px;`;
        const text = document.createElement('span');
        text.textContent = (keyLabel ? `[${keyLabel}] ` : '') + name + (isCurrent ? '  current' : '');
        text.style.cssText = 'flex:1;min-width:0;padding:6px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

        btn.append(stripe, sw, text);
        btn.addEventListener('click', () => _doAddCell(cid));
        _attachClassRenamePencil(btn, cid, text);
        popup.appendChild(btn);

        classButtonOrder.push(cid);
        keyIdx++;
    }

    document.body.appendChild(popup);

    const pw = popup.offsetWidth;
    const ph = popup.offsetHeight;
    let px = screenX;
    let py = screenY;
    if (px + pw > window.innerWidth) px = window.innerWidth - pw - 8;
    if (py + ph > window.innerHeight) py = window.innerHeight - ph - 8;
    popup.style.left = `${Math.max(4, px)}px`;
    popup.style.top = `${Math.max(4, py)}px`;

    _cellEditPopupEl = popup;
    _cellEditCtx = { mode: 'sticky-pick', classNames, classColors, classButtonOrder };

    setTimeout(() => {
        document.addEventListener('mousedown', _outsideCellEditClick, true);
        document.addEventListener('keydown', _cellEditKeydown, true);
    }, 0);
}

window.addEventListener('keydown', (e) => {
    if (e.key !== 'a' && e.key !== 'A') return;
    if (!e.altKey) return;
    if (e.ctrlKey || e.metaKey || e.shiftKey) return;
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!_lastDetectionResult) return;
    if (viewer && viewer.drawMode) return;
    e.preventDefault();
    e.stopPropagation();
    _showStickyClassPickerPopup(_stickyHudLastMouse.x, _stickyHudLastMouse.y);
}, true);

viewer.onCellAddRequested = _showCellAddPopup;

function _showMultiCellEditPopup(listIndices, listCells, screenX, screenY, options = {}) {
    if (!_canEditAiDetections()) return;
    _closeCellEditPopup();
    if (!_lastDetectionResult || !listIndices || listIndices.length === 0) return;

    const isHiddenOther = !!options.hiddenOther;
    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};

    const dict_counts = {};
    for (const c of listCells) {
        const k = String(c.class_id);
        dict_counts[k] = (dict_counts[k] || 0) + 1;
    }

    const popup = document.createElement('div');
    popup.className = 'cell-edit-popup';
    popup.style.cssText = `
        position: fixed; z-index: 9999;
        background: #ffffff; color: #222;
        border: 1px solid #ccc; border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        padding: 10px 12px; min-width: 220px;
        width: min(360px, calc(100vw - 24px));
        max-width: calc(100vw - 24px);
        box-sizing: border-box;
        font-family: sans-serif; font-size: 12px;
        user-select: none;
    `;

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>${listIndices.length} ${isHiddenOther ? 'Other cells selected' : 'cells selected'}</b>`;
    header.appendChild(headerLabel);
    popup.appendChild(header);
    _makeCellEditPopupDraggable(popup, header);

    const breakdown = document.createElement('div');
    breakdown.style.cssText = 'font-size:11px;color:#666;margin-bottom:6px;max-height:60px;overflow-y:auto;white-space:normal;word-break:break-word;line-height:1.35;';
    const list_breakdownLines = [];
    for (const k of Object.keys(dict_counts).sort((a, b) => parseInt(a) - parseInt(b))) {
        const name = classNames[k] || `Class ${k}`;
        list_breakdownLines.push(`${name}: ${dict_counts[k]}`);
    }
    breakdown.textContent = list_breakdownLines.join(' · ');
    popup.appendChild(breakdown);

    const sep1 = document.createElement('div');
    sep1.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep1);

    const labelChange = document.createElement('div');
    labelChange.textContent = 'Change All To:';
    labelChange.style.cssText = 'margin-bottom:4px;';
    popup.appendChild(labelChange);

    const list_classButtonOrder = [];
    const list_sortedClsIds = Object.keys(classNames)
        .map(k => parseInt(k, 10))
        .sort((a, b) => a - b);

    let int_keyIdx = 0;
    for (const cid of list_sortedClsIds) {
        const name = classNames[String(cid)];
        const str_colorCss = _toCssColor(classColors[String(cid)]);
        const str_keyLabel = int_keyIdx < 10 ? String((int_keyIdx + 1) % 10) : '';

        const btn = document.createElement('button');
        btn.style.cssText = `
            display:flex;align-items:center;gap:0;
            width:100%;margin:3px 0;padding:0;
            background:#f0f0f0;color:#222;
            border:1px solid #ccc;border-radius:4px;
            font-size:12px;cursor:pointer;text-align:left;
            box-sizing:border-box;overflow:hidden;
            min-height:30px;
        `;
        btn.onmouseover = () => { btn.style.background = '#4a90d9'; btn.style.color = '#fff'; };
        btn.onmouseout = () => { btn.style.background = '#f0f0f0'; btn.style.color = '#222'; };

        const stripe = document.createElement('span');
        stripe.style.cssText = `flex:0 0 12px;align-self:stretch;background:${str_colorCss};display:block;`;
        const sw = document.createElement('span');
        sw.style.cssText = `flex:0 0 16px;height:16px;border-radius:3px;
            background:${str_colorCss};border:1px solid #333;
            display:inline-block;margin-left:8px;`;
        const text = document.createElement('span');
        text.textContent = str_keyLabel ? `[${str_keyLabel}] ${name}` : name;
        text.style.cssText = 'flex:1;min-width:0;padding:6px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

        btn.append(stripe, sw, text);
        btn.addEventListener('click', () => _doChangeClass(cid));
        _attachClassRenamePencil(btn, cid, text);
        popup.appendChild(btn);

        list_classButtonOrder.push(cid);
        int_keyIdx++;
    }

    if (!isHiddenOther) {
        const sep2 = document.createElement('div');
        sep2.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
        popup.appendChild(sep2);

        const delBtn = document.createElement('button');
        delBtn.textContent = `Delete ${listIndices.length} Cells  (Del / D)`;
        delBtn.style.cssText = `
            display:block;width:100%;padding:7px 10px;
            background:#fdecea;color:#c0392b;
            border:1px solid #e74c3c;border-radius:4px;
            font-size:12px;cursor:pointer;font-weight:600;
        `;
        delBtn.onmouseover = () => { delBtn.style.background = '#e74c3c'; delBtn.style.color = '#fff'; };
        delBtn.onmouseout = () => { delBtn.style.background = '#fdecea'; delBtn.style.color = '#c0392b'; };
        delBtn.addEventListener('click', _doDeleteCell);
        popup.appendChild(delBtn);
    }

    document.body.appendChild(popup);

    const pw = popup.offsetWidth;
    const ph = popup.offsetHeight;
    let px = screenX;
    let py = screenY;
    if (px + pw > window.innerWidth) px = window.innerWidth - pw - 8;
    if (py + ph > window.innerHeight) py = window.innerHeight - ph - 8;
    popup.style.left = `${Math.max(4, px)}px`;
    popup.style.top = `${Math.max(4, py)}px`;

    _cellEditPopupEl = popup;
    _cellEditCtx = {
        multi: true,
        hiddenOther: isHiddenOther,
        indices: [...listIndices],
        classNames,
        classColors,
        classButtonOrder: list_classButtonOrder,
    };

    setTimeout(() => {
        document.addEventListener('mousedown', _outsideCellEditClick, true);
        document.addEventListener('keydown', _cellEditKeydown, true);
    }, 0);
}

viewer.onCellsMultiEditRequested = _showMultiCellEditPopup;
viewer.onHiddenCellsMultiEditRequested = (listIndices, listCells, screenX, screenY) =>
    _showMultiCellEditPopup(listIndices, listCells, screenX, screenY, { hiddenOther: true });

viewer.onCellEdited = () => {
    if (_lastDetectionResult) {
        _lastDetectionResult.cells = viewer.detectionCells;
        _lastDetectionResult.total_cells = viewer.detectionCells.length;
        _lastDetectionResult.excluded_cells = viewer.hiddenDetectionCells || [];
        buildResultList(_lastDetectionResult);
        _updateResultCounts();
    }
    setStatus(`Cell edited - ${viewer.detectionCells.length} cells`);
};

window.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    if (!viewer || !viewer.detectionCells || viewer.detectionCells.length === 0 && !viewer.canUndoCellEdit?.()) return;

    const key = e.key.toLowerCase();
    if (key === 'z' && !e.shiftKey) {
        if (viewer.canUndoCellEdit && viewer.canUndoCellEdit()) {
            _closeCellEditPopup();
            viewer.undoCellEdit();
            setStatus(`Undo - ${viewer.detectionCells.length} cells`);
            e.preventDefault();
        }
    } else if ((key === 'z' && e.shiftKey) || key === 'y') {
        if (viewer.canRedoCellEdit && viewer.canRedoCellEdit()) {
            _closeCellEditPopup();
            viewer.redoCellEdit();
            setStatus(`Redo - ${viewer.detectionCells.length} cells`);
            e.preventDefault();
        }
    }
}, true);

// Clear All
$btnAnnClear?.addEventListener('click', () => {
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    viewer.clearAnnotations();
    renderAnnotationPanel();
    setStatus('Annotations cleared');
});

// JSON schema:
// { "annotations": [ { id, name, type: "Polygon"|"Rectangle"|"Point",
//                      coordinates: [[x,y],...], color: [r,g,b],
//                      group, visible, properties } ] }

const _TYPE_TO_LABEL = { polygon: 'Polygon', rectangle: 'Rectangle', point: 'Point' };
const _LABEL_TO_TYPE = { polygon: 'polygon', rectangle: 'rectangle', point: 'point' };

function _normalizeColor(c) {
    if (Array.isArray(c) && c.length >= 3) return [c[0] | 0, c[1] | 0, c[2] | 0];
    if (typeof c === 'string') {
        const m = c.replace('#', '').match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
        if (m) return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
    }
    return [0, 255, 0];
}

async function _downloadAnnotations() {
    if (!viewer.annotations.length) {
        setStatus('No annotations to save');
        return;
    }
    const payload = {
        annotations: viewer.annotations.map(ann => ({
            id: ann.id,
            name: ann.name,
            type: _TYPE_TO_LABEL[ann.type] || 'Polygon',
            coordinates: (ann.coordinates || []).map(p => [p[0], p[1]]),
            color: _normalizeColor(ann.color),
            group: ann.group || 'default',
            visible: ann.visible !== false,
            properties: ann.properties || {},
        }))
    };
    const json = JSON.stringify(payload, null, 2);

    let baseName = 'annotations';
    if (currentSlideInfo?.filename) {
        baseName = currentSlideInfo.filename.replace(/\.[^.]+$/, '') + '_roi';
    }
    const suggestedName = `${baseName}.json`;

    if (window.showSaveFilePicker) {
        try {
            const handle = await window.showSaveFilePicker({
                suggestedName,
                types: [{
                    description: 'Annotation JSON',
                    accept: { 'application/json': ['.json'] }
                }]
            });
            const writable = await handle.createWritable();
            await writable.write(json);
            await writable.close();
            setStatus(`ROI saved: ${handle.name} (${payload.annotations.length} items)`);
            return;
        } catch (err) {
            if (err?.name === 'AbortError') {
                setStatus('Save cancelled');
                return;
            }
            console.warn('showSaveFilePicker failed, falling back to download', err);
        }
    }

    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = suggestedName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStatus(`ROI saved: ${a.download} (${payload.annotations.length} items)`);
}

function _uploadAnnotations() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.addEventListener('change', () => {
        const file = input.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            try {
                const parsed = JSON.parse(reader.result);
                const list = Array.isArray(parsed) ? parsed : parsed?.annotations;
                if (!Array.isArray(list)) {
                    setStatus('Invalid file format.');
                    return;
                }
                const loaded = [];
                let counter = 0;
                for (const item of list) {
                    if (!item) continue;
                    const coords = item.coordinates || item.points;
                    if (!Array.isArray(coords)) continue;
                    counter++;
                    const typeRaw = (item.type || 'polygon').toString().toLowerCase();
                    const type = _LABEL_TO_TYPE[typeRaw] || 'polygon';
                    loaded.push({
                        id: item.id || crypto.randomUUID?.() || `${Date.now()}_${counter}`,
                        name: item.name || `ROI_${counter}`,
                        type,
                        coordinates: coords.map(p => [Number(p[0]), Number(p[1])]),
                        color: _normalizeColor(item.color),
                        group: item.group || 'default',
                        visible: item.visible !== false,
                        selected: false,
                        properties: item.properties || {},
                    });
                }
                viewer.annotations = loaded;
                viewer._annotationCounter = loaded.length;
                viewer.selectedAnnotationId = null;
                viewer.requestRender();
                renderAnnotationPanel();
                setStatus(`ROI loaded: ${file.name} (${loaded.length} items)`);
            } catch (err) {
                setStatus(`Failed to load ROI: ${err.message}`);
            }
        };
        reader.readAsText(file, 'utf-8');
    });
    input.click();
}

$btnAnnSave?.addEventListener('click', () => {
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    _downloadAnnotations();
});
$btnAnnLoad?.addEventListener('click', () => {
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    _uploadAnnotations();
});

function _normalizeSlideClinicalInfo(raw) {
    const source = raw || {};
    const normalized = {};
    LIST_SLIDE_CLINICAL_FIELDS.forEach((field) => {
        normalized[field.key] = String(source[field.key] ?? '');
    });
    return normalized;
}

function _collectSlideClinicalInfo() {
    const values = {};
    LIST_SLIDE_CLINICAL_FIELDS.forEach((field) => {
        values[field.key] = '';
    });
    $slideInfoContent.querySelectorAll('[data-clinical-key]').forEach((el) => {
        const key = el.dataset.clinicalKey;
        if (Object.prototype.hasOwnProperty.call(values, key)) {
            values[key] = String(el.value ?? '').trim();
        }
    });
    return values;
}

function _hasAnyClinicalValue(values) {
    return Object.values(values || {}).some((value) => String(value || '').trim() !== '');
}

function _buildSlideClinicalEditor(clinicalInfo) {
    const normalized = _normalizeSlideClinicalInfo(clinicalInfo);
    _slideClinicalInitialJson = JSON.stringify(normalized);
    _slideClinicalDirty = false;

    const wrap = document.createElement('div');
    wrap.className = 'slide-clinical-editor';

    const title = document.createElement('div');
    title.className = 'slide-clinical-title';
    title.textContent = 'Clinical Scores';
    wrap.appendChild(title);

    LIST_SLIDE_CLINICAL_FIELDS.forEach((field) => {
        const row = document.createElement('label');
        row.className = 'slide-clinical-field';

        const label = document.createElement('span');
        label.textContent = field.label;
        if (field.required) {
            const required = document.createElement('b');
            required.textContent = ' *';
            label.appendChild(required);
        }
        row.appendChild(label);

        let control;
        if (field.type === 'select') {
            control = document.createElement('select');
            field.options.forEach((optionValue) => {
                const option = document.createElement('option');
                option.value = optionValue;
                option.textContent = optionValue || 'Select';
                control.appendChild(option);
            });
        } else {
            control = document.createElement('input');
            control.type = 'text';
            control.placeholder = 'Enter value or na';
        }
        control.dataset.clinicalKey = field.key;
        control.value = normalized[field.key] || '';
        control.addEventListener('input', () => { _slideClinicalDirty = true; });
        control.addEventListener('change', () => { _slideClinicalDirty = true; });
        row.appendChild(control);
        wrap.appendChild(row);
    });

    return wrap;
}

async function _loadSlideClinicalInfo() {
    if (!currentSlideId) return currentSlideInfo?.dict_clinical_info || {};
    try {
        const res = await api.getSlideClinicalInfo(currentSlideId);
        const clinicalInfo = res.dict_clinical_info || {};
        currentSlideInfo = { ...(currentSlideInfo || {}), case_name: res.case_name || currentSlideInfo?.case_name || '', dict_clinical_info: clinicalInfo };
        return clinicalInfo;
    } catch (err) {
        console.warn('[slide-info] clinical info load failed:', err);
        return currentSlideInfo?.dict_clinical_info || {};
    }
}

async function _saveSlideClinicalInfoIfNeeded() {
    if (!currentSlideId) return;
    const values = _collectSlideClinicalInfo();
    const nextJson = JSON.stringify(_normalizeSlideClinicalInfo(values));
    if (nextJson === _slideClinicalInitialJson) return;
    if (!_hasAnyClinicalValue(values) && _slideClinicalInitialJson === JSON.stringify(_normalizeSlideClinicalInfo({}))) return;

    const res = await api.updateSlideClinicalInfo(currentSlideId, values);
    const saved = res.dict_clinical_info || values;
    currentSlideInfo = { ...(currentSlideInfo || {}), case_name: res.case_name || currentSlideInfo?.case_name || '', dict_clinical_info: saved };
    _markBrowseSlideClinicalInfo(currentSlideId, saved, res.case_name || '');
    _slideClinicalInitialJson = JSON.stringify(_normalizeSlideClinicalInfo(saved));
    _slideClinicalDirty = false;
    setStatus('Case clinical information saved.');
}

function _markBrowseSlideClinicalInfo(slideId, clinicalInfo, caseName = '') {
    const hasClinical = _hasAnyClinicalValue(clinicalInfo);
    const slide = (_lastBrowseData.slides || []).find((item) => item.slide_id === slideId);
    const targetCase = caseName || slide?.case_name || '';
    const listTargets = (_lastBrowseData.slides || []).filter((item) => (
        targetCase ? item.case_name === targetCase : item.slide_id === slideId
    ));
    listTargets.forEach((itemSlide) => {
        itemSlide.clinical_info = clinicalInfo || {};
        itemSlide.has_clinical_info = hasClinical;
        const item = $slideList?.querySelector(`.slide-list-item[data-slide-id="${itemSlide.slide_id}"]`);
        const cell = item?.querySelector('.slide-state-cell.clinical');
        if (cell) {
            cell.classList.toggle('ready', hasClinical);
            cell.classList.toggle('empty', !hasClinical);
            cell.textContent = hasClinical ? '\u2713' : '-';
            cell.title = hasClinical ? 'Clinical info saved' : 'No clinical info';
        }
    });
    if (!listTargets.length && slide) {
        slide.clinical_info = clinicalInfo || {};
        slide.has_clinical_info = hasClinical;
    }
}

async function _closeSlideInfoDialog() {
    if (_slideInfoClosing) return;
    _slideInfoClosing = true;
    try {
        await _saveSlideClinicalInfoIfNeeded();
    } catch (err) {
        setStatus(`Failed to save slide clinical information: ${err.message}`);
    } finally {
        _slideInfoClosing = false;
        if ($slideInfoDialog.open) $slideInfoDialog.close();
    }
}

// Slide information dialog.
$btnInfo.addEventListener('click', async () => {
    if (!currentSlideInfo) return;
    const info = currentSlideInfo;
    const clinicalInfo = await _loadSlideClinicalInfo();
    const mag = info.objective_power !== 'Unknown' ? `${info.objective_power}x` : '-';
    const physW = info.physical_width_mm?.toFixed(2) ?? '-';
    const physH = info.physical_height_mm?.toFixed(2) ?? '-';

    const rows = [
        ['Filename', info.filename || $slideName?.textContent || '-'],
        ['Vendor', info.vendor || '-'],
        ['Magnification', mag],
        ['Pixel Size', `${info.dimensions[0].toLocaleString()} × ${info.dimensions[1].toLocaleString()} px`],
        ['MPP', `${info.mpp_x?.toFixed(4) ?? '-'} × ${info.mpp_y?.toFixed(4) ?? '-'} μm/px`],
        ['Physical Size', `${physW} × ${physH} mm`],
    ];
    $slideInfoContent.replaceChildren();
    const table = document.createElement('table');
    for (const [label, value] of rows) {
        const tr = document.createElement('tr');
        const tdLabel = document.createElement('td');
        const tdValue = document.createElement('td');
        tdLabel.textContent = label;
        tdValue.textContent = value;
        tr.append(tdLabel, tdValue);
        table.appendChild(tr);
    }
    $slideInfoContent.appendChild(table);
    $slideInfoContent.appendChild(_buildSlideClinicalEditor(clinicalInfo));
    $slideInfoDialog.showModal();
});
$('#close-slide-info').addEventListener('click', (event) => {
    event.preventDefault();
    _closeSlideInfoDialog();
});
$slideInfoDialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    _closeSlideInfoDialog();
});
$slideInfoDialog.addEventListener('close', () => {
    if (!_slideInfoClosing && _slideClinicalDirty) {
        _saveSlideClinicalInfoIfNeeded().catch((err) => {
            setStatus(`Failed to save slide clinical information: ${err.message}`);
        });
    }
});

//   value: { task_id, buttonEl }
const _runningAiTasks = {};

function _setButtonRunning(btnEl, bool_running) {
    if (!btnEl) return;
    if (bool_running) {
        btnEl.classList.add('ai-btn-running');
        btnEl.dataset.origLabel = btnEl.dataset.origLabel || btnEl.textContent;
        btnEl.textContent = 'Stop';
    } else {
        btnEl.classList.remove('ai-btn-running');
        if (btnEl.dataset.origLabel) {
            btnEl.textContent = btnEl.dataset.origLabel;
            delete btnEl.dataset.origLabel;
        }
    }
}

async function _maybeCancelRunning(str_key) {
    const entry = _runningAiTasks[str_key];
    if (!entry) return false;
    if (!entry.task_id) {
        entry.pending_cancel = true;
        setStatus('Cancel queued. The task will stop as soon as it starts.');
        return true;
    }
    try {
        await api.cancelTask(entry.task_id);
        setStatus('Cancel request sent. Cleaning up shortly...');
    } catch (e) {
        console.warn('[cancel] failed', e);
    }
    return true;
}

$btnDetect.addEventListener('click', startDetection);

async function startDetection() {
    if (_blockViewerAction()) return;
    if (!currentSlideId) return;
    if (await _maybeCancelRunning('detect')) return;

    _runningAiTasks['detect'] = { task_id: null, buttonEl: $btnDetect };
    _setButtonRunning($btnDetect, true);
    $progressLabel.textContent = 'Cell Detection...';
    setProgress(0);
    setStatus('Cell Detection started...');

    viewer.setDrawMode(null);

    try {
        const tissueType = document.querySelector('input[name="tissue-type"]:checked')?.value || 'Stomach';

        const roiAnnotations = viewer.annotations.filter(a => a.visible && a.type !== 'point' && a.coordinates.length >= 3);
        const roiPolygons = roiAnnotations.length > 0 ? roiAnnotations.map(a => a.coordinates) : null;

        const { task_id } = await api.startDetection(currentSlideId, roiPolygons, tissueType);
        if (_runningAiTasks['detect']) {
            _runningAiTasks['detect'].task_id = task_id;
            if (_runningAiTasks['detect'].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
            }
        }

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks['detect']) return;
            const st = await api.getTaskStatus(task_id);
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);

            if (st.progress <= 50) {
                $progressLabel.textContent = 'Cell Detection';
            } else if (st.progress < 92) {
                $progressLabel.textContent = 'WSI Segmentation';
            } else if (st.progress < 100) {
                $progressLabel.textContent = 'Epithelial Reclassification';
            }

            if (st.status === 'completed') {
                const result = await api.getTaskResult(task_id, _makeResultDownloadProgress());
                onDetectionComplete(result, roiPolygons, tissueType);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus('Cell Detection cancelled. Partial results were cleared.');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`Cell Detection failed: ${err.message}`);
    } finally {
        delete _runningAiTasks['detect'];
        _setButtonRunning($btnDetect, false);
        if ($progressLabel.textContent === 'Cell Detection...') {
            $progressLabel.textContent = 'AI Progress';
        }
    }
}

function onDetectionComplete(result, roiPolygons = null, tissueType = null) {
    $progressLabel.textContent = 'Detection Complete';

    viewer.clearAnnotations();
    renderAnnotationPanel();

    _lastDetectionResult = result;
    _lastDetectionTissue = tissueType;
    _lastDetectionModel = 'Quanti HE';
    _lastDetectionRoi = roiPolygons;

    lastSegData = result.seg_data || null;

    viewer.classColorOverride = null;
    viewer.defaultConfidence = 0.1;

    viewer.setDetectionResults(result.cells, roiPolygons);
    viewer.setHiddenDetectionResults?.(result.excluded_cells || [], roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);
    setStatus(`Detection complete: ${displayCount.toLocaleString()} cells`);
    buildResultList(result);

    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
}

const CLASS_COLORS = {
    0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
    4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
};

function _renderScoreBar(barEl, segments) {
    if (!barEl) return;
    barEl.innerHTML = '';
    const total = segments.reduce((s, seg) => s + seg.value, 0);
    if (total === 0) { barEl.style.display = 'none'; return; }
    barEl.style.display = '';
    for (const seg of segments) {
        const pct = seg.value / total * 100;
        if (pct < 0.5) continue;
        const el = document.createElement('div');
        el.className = 'score-bar-seg';
        el.style.width = `${pct}%`;
        el.style.backgroundColor = seg.color;
        if (pct > 8) el.setAttribute('data-label', seg.label || '');
        barEl.appendChild(el);
    }
}

function _renderScoreLegend(detailEl, items) {
    const wrap = document.createElement('div');
    wrap.className = 'score-card-legend';
    for (const item of items) {
        const el = document.createElement('span');
        el.className = 'score-card-legend-item';
        el.innerHTML = `<span class="score-card-legend-dot" style="background:${item.color}"></span>${item.label}: ${item.count.toLocaleString()}`;
        wrap.appendChild(el);
    }
    detailEl.appendChild(wrap);
}

function _computeFilteredCounts(cells) {
    const counts = {};
    let total = 0;
    for (const cell of cells) {
        const thr = viewer.classConfidence[cell.class_id] ?? 0.01;
        if ((cell.confidence ?? 1.0) < thr) continue;
        counts[cell.class_id] = (counts[cell.class_id] || 0) + 1;
        total++;
    }
    return { counts, total };
}

function _formatCountWithRatio(int_count, int_total) {
    const str_count = int_count.toLocaleString();
    if (!int_total) return `${str_count} (0%)`;
    return `${str_count} (${(int_count / int_total * 100).toFixed(1)}%)`;
}

let _resultCountRefs = null; // {total: el, perClass: {id: el}}
function _updateResultCounts() {
    if (!_resultCountRefs || !_lastDetectionResult) return;
    const { counts, total } = _computeFilteredCounts(viewer.detectionCells);
    _resultCountRefs.total.textContent = total.toLocaleString();
    for (const [idStr, el] of Object.entries(_resultCountRefs.perClass)) {
        const id = parseInt(idStr);
        el.textContent = _formatCountWithRatio(counts[id] || 0, total);
    }
    _updatePdScoreDisplay(counts);
    _updateHer2ScoreDisplay(counts);
    _updateAllredScoreDisplay(counts);
    _updateKi67ScoreDisplay(counts);
}

function _updatePdScoreDisplay(counts) {
    if (!$pdScoreResult || $pdScoreResult.hidden) return;
    if (!_lastDetectionResult || !_lastDetectionResult.pd_score) return;

    const scoreType = _lastDetectionResult.pd_score.score_type;
    const c = counts || _computeFilteredCounts(viewer.detectionCells).counts;

    if (scoreType === 'CPS') {
        const posTumor = c[3] || 0;
        const posImmune = (c[4] || 0) + (c[5] || 0);
        const negTumor = c[0] || 0;
        const viableTumor = negTumor + posTumor;
        const score = viableTumor === 0
            ? 0
            : Math.min(100, (posTumor + posImmune) / viableTumor * 100);
        $pdScoreLabel.textContent = 'CPS';
        $pdScoreValue.textContent = `${score.toFixed(1)}%`;
        _renderScoreBar($pdScoreBar, [
            { value: posTumor, color: '#e74c3c', label: `Pos T ${posTumor}` },
            { value: posImmune, color: '#f39c12', label: `Pos I ${posImmune}` },
            { value: negTumor, color: '#27ae60', label: `Neg ${negTumor}` },
        ]);
        $pdScoreDetail.innerHTML = '';
        _renderScoreLegend($pdScoreDetail, [
            { color: '#e74c3c', label: 'Pos Tumor', count: posTumor },
            { color: '#f39c12', label: 'Pos Immune', count: posImmune },
            { color: '#27ae60', label: 'Neg Tumor', count: negTumor },
        ]);
    } else if (scoreType === 'TPS') {
        const posTumor = c[1] || 0;
        const negTumor = c[0] || 0;
        const totalTumor = posTumor + negTumor;
        const score = totalTumor === 0 ? 0 : posTumor / totalTumor * 100;
        $pdScoreLabel.textContent = 'TPS';
        $pdScoreValue.textContent = `${score.toFixed(1)}%`;
        _renderScoreBar($pdScoreBar, [
            { value: posTumor, color: '#e74c3c', label: `Pos ${posTumor}` },
            { value: negTumor, color: '#27ae60', label: `Neg ${negTumor}` },
        ]);
        $pdScoreDetail.innerHTML = '';
        _renderScoreLegend($pdScoreDetail, [
            { color: '#e74c3c', label: 'Positive', count: posTumor },
            { color: '#27ae60', label: 'Negative', count: negTumor },
        ]);
    }
}

function _updateHer2ScoreDisplay(counts) {
    if (!$ihcScoreResult || $ihcScoreResult.hidden) return;
    if (!_lastDetectionResult || !_lastDetectionResult.her2_score) return;
    const c = counts || _computeFilteredCounts(viewer.detectionCells).counts;
    const n0 = c[0] || 0, n1 = c[1] || 0, n2 = c[2] || 0, n3 = c[3] || 0;
    const total = n0 + n1 + n2 + n3;
    const weighted = total === 0 ? 0 : (0 * n0 + 1 * n1 + 2 * n2 + 3 * n3) / total;
    const dominant = total === 0 ? 0 : [n0, n1, n2, n3].indexOf(Math.max(n0, n1, n2, n3));
    $ihcScoreLabel.textContent = 'HER2';
    $ihcScoreValue.textContent = `${dominant}+ (${weighted.toFixed(2)})`;
    const HER2_COLORS = ['#27ae60', '#f1c40f', '#e67e22', '#c0392b'];
    _renderScoreBar($ihcScoreBar, [
        { value: n0, color: HER2_COLORS[0], label: `0+ ${n0}` },
        { value: n1, color: HER2_COLORS[1], label: `1+ ${n1}` },
        { value: n2, color: HER2_COLORS[2], label: `2+ ${n2}` },
        { value: n3, color: HER2_COLORS[3], label: `3+ ${n3}` },
    ]);
    $ihcScoreDetail.innerHTML = '';
    _renderScoreLegend($ihcScoreDetail, [
        { color: HER2_COLORS[0], label: '0+', count: n0 },
        { color: HER2_COLORS[1], label: '1+', count: n1 },
        { color: HER2_COLORS[2], label: '2+', count: n2 },
        { color: HER2_COLORS[3], label: '3+', count: n3 },
    ]);
}

function _computeAllredFromCounts(c) {
    const n0 = c[0] || 0, n1 = c[1] || 0, n2 = c[2] || 0, n3 = c[3] || 0;
    const total = n0 + n1 + n2 + n3;
    const pos = n1 + n2 + n3;
    const posPct = total === 0 ? 0 : pos / total * 100;
    let ps = 0;
    if (pos === 0) ps = 0;
    else if (posPct < 1) ps = 1;
    else if (posPct < 10) ps = 2;
    else if (posPct < 33) ps = 3;
    else if (posPct < 66) ps = 4;
    else ps = 5;
    let avg = 0, is_ = 0;
    if (pos > 0) {
        avg = (1 * n1 + 2 * n2 + 3 * n3) / pos;
        if (avg < 0.5) is_ = 0;
        else if (avg < 1.5) is_ = 1;
        else if (avg < 2.5) is_ = 2;
        else is_ = 3;
    }
    const ts = ps + is_;
    return { n0, n1, n2, n3, total, pos, posPct, ps, is_, avg, ts,
             interpretation: ts >= 3 ? 'Positive' : 'Negative' };
}

function _updateAllredScoreDisplay(counts) {
    if (!$ihcScoreResult || $ihcScoreResult.hidden) return;
    if (!_lastDetectionResult || !_lastDetectionResult.allred_score) return;
    const c = counts || _computeFilteredCounts(viewer.detectionCells).counts;
    const a = _computeAllredFromCounts(c);
    const marker = _lastDetectionTissue || 'ER/PR';
    const markerLabel = marker === 'ER_PR' ? 'ER/PR' : marker;
    $ihcScoreLabel.textContent = `${markerLabel} (Allred)`;
    $ihcScoreValue.textContent = `${a.ts} / 8`;
    const ALLRED_COLORS = ['#27ae60', '#f1c40f', '#e67e22', '#c0392b'];
    _renderScoreBar($ihcScoreBar, [
        { value: a.n0, color: ALLRED_COLORS[0], label: `0+ ${a.n0}` },
        { value: a.n1, color: ALLRED_COLORS[1], label: `1+ ${a.n1}` },
        { value: a.n2, color: ALLRED_COLORS[2], label: `2+ ${a.n2}` },
        { value: a.n3, color: ALLRED_COLORS[3], label: `3+ ${a.n3}` },
    ]);
    $ihcScoreDetail.innerHTML =
        `PS: ${a.ps} &nbsp;·&nbsp; IS: ${a.is_} &nbsp;·&nbsp; <strong>${a.interpretation}</strong><br>` +
        `Positive: ${a.posPct.toFixed(1)}% &nbsp;·&nbsp; Avg intensity: ${a.avg.toFixed(2)}`;
    _renderScoreLegend($ihcScoreDetail, [
        { color: ALLRED_COLORS[0], label: '0+', count: a.n0 },
        { color: ALLRED_COLORS[1], label: '1+', count: a.n1 },
        { color: ALLRED_COLORS[2], label: '2+', count: a.n2 },
        { color: ALLRED_COLORS[3], label: '3+', count: a.n3 },
    ]);
}

function _updateKi67ScoreDisplay(counts) {
    if (!$ihcScoreResult || $ihcScoreResult.hidden) return;
    if (!_lastDetectionResult || !_lastDetectionResult.ki67_score) return;
    const c = counts || _computeFilteredCounts(viewer.detectionCells).counts;
    const n0 = c[0] || 0, n1 = c[1] || 0, n2 = c[2] || 0, n3 = c[3] || 0;
    const total = n0 + n1 + n2 + n3;
    const pos = n1 + n2 + n3;
    const ki67Index = total === 0 ? 0 : pos / total * 100;
    const interp = ki67Index >= 14 ? 'High' : 'Low';
    const KI67_COLORS = ['#27ae60', '#e74c3c'];
    $ihcScoreLabel.textContent = 'KI-67';
    $ihcScoreValue.textContent = `${ki67Index.toFixed(1)}%`;
    _renderScoreBar($ihcScoreBar, [
        { value: n0, color: KI67_COLORS[0], label: `Neg ${n0}` },
        { value: pos, color: KI67_COLORS[1], label: `Pos ${pos}` },
    ]);
    $ihcScoreDetail.innerHTML =
        `Labeling Index: ${ki67Index.toFixed(1)}% &nbsp;·&nbsp; <strong>${interp}</strong><br>` +
        `Positive: ${pos.toLocaleString()} &nbsp;·&nbsp; Negative: ${n0.toLocaleString()} &nbsp;·&nbsp; Total: ${total.toLocaleString()}`;
    _renderScoreLegend($ihcScoreDetail, [
        { color: KI67_COLORS[0], label: 'Negative', count: n0 },
        { color: KI67_COLORS[1], label: 'Positive', count: pos },
    ]);
}

function buildResultList(result) {
    $resultList.innerHTML = '';

    let counts, total;
    if (viewer.detectionCells && viewer.detectionCells.length) {
        ({ counts, total } = _computeFilteredCounts(viewer.detectionCells));
    } else {
        counts = {};
        total = 0;
        for (const cell of (result.cells || [])) {
            counts[cell.class_id] = (counts[cell.class_id] || 0) + 1;
            total++;
        }
    }

    // Per-class checkbox references.
    const classCbs = {};
    const perClassCountEls = {};

    const totalItem = document.createElement('div');
    totalItem.className = 'result-item';

    const totalCb = document.createElement('input');
    totalCb.type = 'checkbox';
    totalCb.checked = true;
    totalCb.addEventListener('change', () => {
        const checked = totalCb.checked;
        for (const [id, cb] of Object.entries(classCbs)) {
            cb.checked = checked;
            viewer.classVisibility[parseInt(id)] = checked;
        }
        viewer.requestRender();
    });

    const totalName = document.createElement('span');
    totalName.className = 'class-name';
    totalName.style.fontWeight = '600';
    totalName.textContent = 'Total Cells';

    const totalCount = document.createElement('span');
    totalCount.className = 'class-count';
    totalCount.textContent = total.toLocaleString();

    totalItem.style.cursor = 'pointer';
    totalItem.addEventListener('click', (e) => {
        if (e.target === totalCb) return;
        totalCb.click();
    });

    totalItem.append(totalCb, totalName, totalCount);
    $resultList.appendChild(totalItem);

    for (const [idStr, name] of Object.entries(result.class_names)) {
        const id = parseInt(idStr);
        const count = counts[id] || 0;
        if (count === 0) continue;

        const color = (_lastDetectionResult.class_colors && _lastDetectionResult.class_colors[idStr])
                      || CLASS_COLORS[id] || '#fff';

        const item = document.createElement('div');
        item.className = 'result-item';

        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = true;
        classCbs[id] = cb;
        cb.addEventListener('change', () => {
            viewer.classVisibility[id] = cb.checked;
            // Sync the total checkbox state.
            const allChecked = Object.values(classCbs).every(c => c.checked);
            const noneChecked = Object.values(classCbs).every(c => !c.checked);
            totalCb.checked = allChecked;
            totalCb.indeterminate = !allChecked && !noneChecked;
            viewer.requestRender();
        });

        const dot = document.createElement('span');
        dot.className = 'class-dot';
        dot.style.backgroundColor = color;

        const nameSpan = document.createElement('span');
        nameSpan.className = 'class-name';
        nameSpan.textContent = name;

        const countSpan = document.createElement('span');
        countSpan.className = 'class-count';
        countSpan.textContent = _formatCountWithRatio(count, total);
        perClassCountEls[id] = countSpan;

        item.style.cursor = 'pointer';
        item.addEventListener('click', (e) => {
            if (e.target === cb) return;
            cb.click();
        });

        item.append(cb, dot, nameSpan, countSpan);
        $resultList.appendChild(item);
        // Confidence thresholds are fixed for SaMD reproducibility.
    }

    _resultCountRefs = { total: totalCount, perClass: perClassCountEls };
}

function clearResults() {
    $resultList.innerHTML = '';
    $btnVisualize.disabled = true;
    $btnClearResults.disabled = true;
    $btnSaveResults.disabled = true;
    if ($btnLoadResults) $btnLoadResults.disabled = true;
    viewer.setDetectionResults([]);
    viewer.setHiddenDetectionResults?.([]);
    lastSegData = null;
    _lastDetectionResult = null;
    _lastDetectionTissue = null;
    _stickyAddClassId = null;
    _hideStickyHud();
    _lastDetectionModel = null;
    _lastDetectionRoi = null;
}

$btnClearResults.addEventListener('click', () => {
    if (_blockViewerAction()) return;
    clearResults();
});

$btnVisualize.addEventListener('click', () => {
    if (_blockViewerAction()) return;
    if (viewer.detectionCells.length === 0) return;
    // Visualize cells that pass current confidence thresholds.
    const filtered = viewer.detectionCells.filter(c => {
        const thr = viewer.classConfidence[c.class_id] ?? 0.01;
        return (c.confidence ?? 1.0) >= thr;
    });
    if (filtered.length === 0) {
        setStatus('No cells pass current confidence thresholds');
        return;
    }
    const thumbUrl = currentSlideId ? api.previewUrl(currentSlideId, 4096, false, currentSlideInfo) : null;
    const slideName = ($slideName.textContent || '').replace(/\.[^.]+$/, '') || 'slide';
    const tissue = _lastDetectionTissue || 'Stomach';
    const slideDims = currentSlideInfo?.dimensions || null;  // [w, h] level-0

    const isPdScore = !!(_lastDetectionResult && _lastDetectionResult.pd_score);
    const isHer2 = !!(_lastDetectionResult && _lastDetectionResult.her2_score);
    const isAllred = !!(_lastDetectionResult && _lastDetectionResult.allred_score);
    const isKi67 = !!(_lastDetectionResult && _lastDetectionResult.ki67_score);
    const isIhc = isHer2 || isAllred || isKi67;
    const modelType = isIhc ? 'Quanti IHC' : (isPdScore ? 'Quanti PD-L1' : 'Quanti HE');
    const scoreType = isHer2 ? 'HER2'
        : isAllred ? 'Allred'
        : isKi67 ? 'KI67'
        : (isPdScore ? _lastDetectionResult.pd_score.score_type : null);
    const classNames = _lastDetectionResult?.class_names || null;
    const classColors = _lastDetectionResult?.class_colors || null;

    showVisualization(filtered, lastSegData, thumbUrl, {
        slideName, tissue, slideDims,
        modelType, scoreType, classNames, classColors,
    });
});

$btnSaveResults?.addEventListener('click', async () => {
    if (_blockAiResultPersistenceAction('Labeler role cannot save or load AI results.')) return;
    if (!currentSlideId || !_lastDetectionResult) {
        setStatus('No detection result to save');
        return;
    }
    const tissue = _lastDetectionTissue || 'Stomach';
    const aiMode = _lastDetectionModel || 'Quanti HE';
    try {
        $btnSaveResults.disabled = true;
        if (viewer?.detectionCells) {
            _lastDetectionResult.cells = viewer.detectionCells;
            _lastDetectionResult.total_cells = viewer.detectionCells.length;
            _lastDetectionResult.excluded_cells = viewer.hiddenDetectionCells || [];
        }
        delete _lastDetectionResult.class_confidence;
        delete _lastDetectionResult.default_confidence;
        const r = await api.saveDetectionResult(
            currentSlideId, tissue, _lastDetectionResult, aiMode,
        );
        console.log('[save-result]', r);
        setStatus(`Saved (${aiMode}/${tissue}): ${r.total_cells} cells - ${r.user_name || 'me'}`);
    } catch (err) {
        console.error('[save-result] failed', err);
        setStatus(`Save failed: ${err.message}`);
    } finally {
        $btnSaveResults.disabled = false;
        if (_isViewerRole()) _applyViewerRoleRestrictions();
        if (_isLabelerRole()) _applyLabelerRoleRestrictions();
    }
});

const $loadUserEditDialog = $('#load-user-edit-dialog');
const $loadUserEditList = $('#load-user-edit-list');
const $loadUserEditMeta = $('#load-user-edit-meta');
$('#close-load-user-edit')?.addEventListener('click', () => $loadUserEditDialog?.close());

function _fmtDateIso(str) {
    if (!str) return '';
    try {
        const d = new Date(str);
        return d.toLocaleString();
    } catch (_) { return str; }
}

async function _openLoadUserEditDialog() {
    if (_blockAiResultPersistenceAction('Labeler role cannot save or load AI results.')) return;
    if (!currentSlideId) {
        setStatus('Open a slide first.');
        return;
    }
    if (!_lastDetectionModel || !_lastDetectionTissue) {
        setStatus('Run an AI model first so the matching result type can be loaded.');
        return;
    }
    const aiMode = _lastDetectionModel;
    const variant = _lastDetectionTissue;
    $loadUserEditMeta.textContent = `Mode: ${aiMode}  /  Variant: ${variant}`;
    $loadUserEditList.innerHTML = '<div style="padding:12px; color:#888;">Loading...</div>';
    $loadUserEditDialog.showModal();

    let users = [];
    try {
        const r = await api.listUserAiEdits(currentSlideId, aiMode, variant);
        users = r.users || [];
    } catch (err) {
        $loadUserEditList.replaceChildren();
        const errorEl = document.createElement('div');
        errorEl.style.cssText = 'padding:12px; color:#c66;';
        errorEl.textContent = `Failed: ${err.message}`;
        $loadUserEditList.appendChild(errorEl);
        return;
    }

    $loadUserEditList.innerHTML = '';

    const originalRow = document.createElement('div');
    originalRow.className = 'result-row';
    originalRow.style.cssText = 'padding:10px 12px; cursor:pointer; border-bottom:1px solid #333;';
    originalRow.innerHTML = `
        <div style="font-weight:600;">Original model inference</div>
        <div style="font-size:11px; color:#888; margin-top:2px;">
            Original model inference (${aiMode} / ${variant})
        </div>`;
    originalRow.addEventListener('click', async () => {
        $loadUserEditDialog.close();
        _rerunOriginalInference(aiMode, variant);
    });
    $loadUserEditList.appendChild(originalRow);

    if (users.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding:12px; color:#888; font-size:12px;';
        empty.textContent = 'No saved user edits.';
        $loadUserEditList.appendChild(empty);
        return;
    }

    const myId = window.__currentUserId || '';
    for (const u of users) {
        const row = document.createElement('div');
        row.className = 'result-row';
        row.style.cssText = 'padding:10px 12px; border-bottom:1px solid #333; display:flex; align-items:center; gap:8px;';
        const displayName = u.str_user_name || u.str_login_id || u.str_user_id;
        const isMine = u.str_user_id && u.str_user_id === myId;

        const info = document.createElement('div');
        info.style.cssText = 'flex:1; cursor:pointer; min-width:0;';
        info.innerHTML = `
            <div style="font-weight:600;">
                ${escapeHtml(displayName)}${isMine ? ' <span style="color:#6cf; font-size:10px;">(me)</span>' : ''}
            </div>
            <div style="font-size:11px; color:#888; margin-top:2px;">
                ${u.int_total_cells.toLocaleString()} cells · ${_fmtDateIso(u.dt_updated_at)}
            </div>`;
        info.addEventListener('click', async () => {
            $loadUserEditDialog.close();
            try {
                setStatus(`Loading ${displayName}'s analysis...`);
                const r = await api.loadUserAiEdit(currentSlideId, aiMode, u.str_user_id, variant);
                _applyLoadedResult(aiMode, variant, r.result);
                setStatus(`Loaded: ${displayName} (${r.result?.cells?.length ?? 0} cells)`);
            } catch (err) {
                setStatus(`Load failed: ${err.message}`);
            }
        });
        row.appendChild(info);

        if (isMine) {
            const del = document.createElement('button');
            del.className = 'small-btn';
            del.title = 'Delete my saved analysis';
            del.style.cssText = 'background:transparent; border:1px solid #555; padding:4px 8px; cursor:pointer;';
            del.textContent = 'Delete';
            del.addEventListener('click', async (ev) => {
                ev.stopPropagation();
                if (!confirm(`Delete your saved ${aiMode} / ${variant} analysis for this slide?`)) return;
                try {
                    del.disabled = true;
                    await api.deleteMyUserAiEdit(currentSlideId, aiMode, variant);
                    setStatus('Deleted your saved analysis');
                    _openLoadUserEditDialog();
                } catch (err) {
                    setStatus(`Delete failed: ${err.message}`);
                    del.disabled = false;
                }
            });
            row.appendChild(del);
        }

        $loadUserEditList.appendChild(row);
    }
}

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function _applyLoadedResult(aiMode, variant, result) {
    if (!result) return;
    const roi = _lastDetectionRoi || null;
    if (aiMode === 'Quanti HE') {
        onDetectionComplete(result, roi, variant);
    } else if (aiMode === 'Quanti PD-L1') {
        onPdScoreComplete(result, roi, variant);
    } else if (aiMode === 'Quanti IHC') {
        onPreciseIhcComplete(result, roi, variant);
    }
}

function _rerunOriginalInference(aiMode, variant) {
    // Rerun through the matching AI action button.
    if (aiMode === 'Quanti HE') {
        // Trigger the HE detection button.
        $('#btn-detect')?.click();
    } else if (aiMode === 'Quanti PD-L1') {
        $('#btn-pd-score')?.click();
    } else if (aiMode === 'Quanti IHC') {
        if (variant === 'ER_PR') $('#btn-ihc-erpr')?.click();
        else if (variant === 'KI_67') $('#btn-ihc-ki67')?.click();
        else $('#btn-ihc-her2')?.click();
    }
}

$btnLoadResults?.addEventListener('click', _openLoadUserEditDialog);

function normalizeProgressMessage(statusMsg, pct) {
    const msg = String(statusMsg || '').trim();
    if (!msg || /\btext\b/i.test(msg)) return `${Math.round(pct)}%`;
    return msg;
}

function setProgress(pct, statusMsg = '') {
    $progressBar.querySelector('.progress-fill').style.width = `${pct}%`;
    const $text = $('#progress-text');
    if (pct > 0 && pct < 100) {
        $text.textContent = normalizeProgressMessage(statusMsg, pct);
    } else if (pct >= 100) {
        $text.textContent = 'Complete';
    } else {
        $text.textContent = '';
    }
}

function setStatus(msg) {
    $statusText.textContent = msg;
}

function _makeResultDownloadProgress(label = 'Loading result JSON') {
    return ({ loaded, total, percent }) => {
        if (percent != null) {
            const shown = Math.min(99, Math.max(1, percent));
            setProgress(shown, `${label} ${percent}%`);
            setStatus(`${label}: ${percent}%`);
            return;
        }
        const mb = loaded / (1024 * 1024);
        setProgress(99, `${label} ${mb.toFixed(1)} MB`);
        setStatus(`${label}: ${mb.toFixed(1)} MB`);
    };
}

function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

const $leftPanel = $('#left-panel');
const $resizer = $('#left-panel-resizer');
const $rightPanel = $('#right-panel');
const $rightResizer = $('#right-panel-resizer');

function _resizeViewerCanvasSoon() {
    if (viewer && typeof viewer._resizeCanvas === 'function') {
        viewer._resizeCanvas();
    }
}

function _restorePanelSizes() {
    const int_right_w = parseInt(localStorage.getItem('rightPanelWidth') || '', 10);
    if (!Number.isNaN(int_right_w) && int_right_w >= 280 && int_right_w <= 560) {
        document.documentElement.style.setProperty('--right-panel-w', `${int_right_w}px`);
    }
}
_restorePanelSizes();

const THUMB_RANGE_LIST = { min: 28, max: 96, step: 6, key: '--slide-thumb-list', storage: 'thumbSizeList' };
const THUMB_RANGE_GRID = { min: 60, max: 200, step: 10, key: '--slide-thumb-grid', storage: 'thumbSizeGrid' };
function _restoreThumbSizes() {
    for (const r of [THUMB_RANGE_LIST, THUMB_RANGE_GRID]) {
        const v = parseFloat(localStorage.getItem(r.storage));
        if (!isNaN(v) && v >= r.min && v <= r.max) {
            document.documentElement.style.setProperty(r.key, `${v}px`);
        }
    }
}
_restoreThumbSizes();
$slideList.addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const r = $slideList.classList.contains('grid-view') ? THUMB_RANGE_GRID : THUMB_RANGE_LIST;
    const cur = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(r.key)) || r.min;
    const next = Math.max(r.min, Math.min(r.max, cur + (e.deltaY < 0 ? r.step : -r.step)));
    document.documentElement.style.setProperty(r.key, `${next}px`);
    localStorage.setItem(r.storage, String(next));
}, { passive: false });

$resizer.addEventListener('mousedown', (e) => {
    e.preventDefault();
    $resizer.classList.add('dragging');
    const startX = e.clientX;
    const startW = $leftPanel.offsetWidth;

    function onMove(ev) {
        const w = Math.max(160, Math.min(500, startW + ev.clientX - startX));
        document.documentElement.style.setProperty('--left-panel-w', `${w}px`);
        _resizeViewerCanvasSoon();
    }
    function onUp() {
        $resizer.classList.remove('dragging');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
});

if ($rightResizer && $rightPanel) {
    $rightResizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        $rightResizer.classList.add('dragging');
        const startX = e.clientX;
        const startW = $rightPanel.offsetWidth;

        function onMove(ev) {
            const int_left_w = $leftPanel ? $leftPanel.offsetWidth : 0;
            const int_max_by_viewport = Math.max(280, window.innerWidth - int_left_w - 360);
            const int_max = Math.min(560, int_max_by_viewport);
            const w = Math.max(280, Math.min(int_max, startW - (ev.clientX - startX)));
            document.documentElement.style.setProperty('--right-panel-w', `${w}px`);
            localStorage.setItem('rightPanelWidth', String(w));
            _resizeViewerCanvasSoon();
        }

        function onUp() {
            $rightResizer.classList.remove('dragging');
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        }

        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    });
}

let currentBrowsePath = '';
let _projectListCache = [];
let _projectGatePage = 1;
let _projectGateSort = { key: 'name', dir: 'asc' };
const $breadcrumb = $('#folder-breadcrumb');

function _getCurrentProjectName() {
    return (currentBrowsePath || '').split('/').filter(Boolean)[0] || '';
}

function _setProjectControlsEnabled() {
    const hasProject = !!_getCurrentProjectName();
    const canEdit = window.__currentUserRole !== 'viewer' && window.__currentUserRole !== 'labeler';
    const canDelete = window.__currentUserRole === 'admin';
    if ($btnNewProject) $btnNewProject.disabled = !canEdit;
    if ($btnRenameProject) $btnRenameProject.disabled = !hasProject || !canEdit;
    if ($btnDeleteProject) $btnDeleteProject.disabled = !hasProject || !canDelete;
}

function _hasProjectOption(projectName) {
    return !![...($projectSelect?.options || [])].find(opt => opt.value === projectName);
}

function _syncProjectSelect() {
    if (!$projectSelect) return;
    const projectName = _getCurrentProjectName();
    if (projectName && !_hasProjectOption(projectName)) {
        const opt = document.createElement('option');
        opt.value = projectName;
        opt.textContent = _projectLabelForPath(projectName);
        $projectSelect.appendChild(opt);
    }
    $projectSelect.value = projectName;
    _setProjectControlsEnabled();
}

function _projectLabel(project) {
    const info = project?.info || {};
    return info.title || project?.name || project?.path || '';
}

function _projectLabelForPath(path) {
    const project = _projectListCache.find(p => (p.path || p.name) === path);
    return project ? _projectLabel(project) : 'Selected project';
}

async function loadProjectList() {
    if (!$projectSelect) return [];
    try {
        const data = await api.listProjects();
        const list_projects = data.projects || [];
        _projectListCache = list_projects;
        const currentProject = _getCurrentProjectName();
        $projectSelect.innerHTML = '';
        for (const project of list_projects) {
            const opt = document.createElement('option');
            opt.value = project.path || project.name;
            opt.textContent = _projectLabel(project);
            $projectSelect.appendChild(opt);
        }
        if (currentProject && !_hasProjectOption(currentProject)) {
            const opt = document.createElement('option');
            opt.value = currentProject;
            opt.textContent = _projectLabelForPath(currentProject);
            $projectSelect.appendChild(opt);
        }
        if (!currentProject && !$projectSelect.options.length) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'No projects';
            $projectSelect.appendChild(opt);
        }
        _syncProjectSelect();
        return list_projects;
    } catch (err) {
        console.warn('Project list load failed:', err);
        _projectListCache = [];
        return [];
    }
}

function _projectGateValue(project, key) {
    const info = project?.info || {};
    if (key === 'name') return info.title || project.name || project.path || '';
    if (key === 'hospital') return info.institution || '';
    if (key === 'owner') return info.owner || '';
    if (key === 'slides') return Number(project.slide_count || 0);
    if (key === 'reviewed') return Number(project.reviewed_count || 0);
    if (key === 'progress') return Number(project.in_progress_count || 0);
    if (key === 'ai') return Number(project.ai_analyzed_count || 0);
    if (key === 'folders') return Number(project.folder_count || 0);
    if (key === 'status') return info.status || 'active';
    return '';
}

function _getProjectGatePageSize() {
    const n = parseInt($projectGatePageSize?.value || '30', 10);
    return Number.isFinite(n) && n > 0 ? n : 30;
}

function _setSelectOptions(selectEl, values, allLabel) {
    if (!selectEl) return;
    const current = selectEl.value;
    selectEl.innerHTML = '';
    const allOpt = document.createElement('option');
    allOpt.value = '';
    allOpt.textContent = allLabel;
    selectEl.appendChild(allOpt);
    for (const value of values) {
        if (!value) continue;
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = value;
        selectEl.appendChild(opt);
    }
    selectEl.value = values.includes(current) ? current : '';
}

function _populateProjectGateFilters(list_projects) {
    const hospitals = [...new Set(list_projects.map(p => (p.info?.institution || '').trim()).filter(Boolean))].sort();
    const owners = [...new Set(list_projects.map(p => (p.info?.owner || '').trim()).filter(Boolean))].sort();
    const statuses = [...new Set(list_projects.map(p => (p.info?.status || 'active').trim()).filter(Boolean))].sort();
    _setSelectOptions($projectGateHospital, hospitals, 'All hospitals');
    _setSelectOptions($projectGateOwner, owners, 'All owners');
    _setSelectOptions($projectGateStatus, statuses, 'All status');
}

function _getFilteredProjectGateList(list_projects) {
    const search = ($projectGateSearch?.value || '').trim().toLowerCase();
    const hospital = $projectGateHospital?.value || '';
    const owner = $projectGateOwner?.value || '';
    const status = $projectGateStatus?.value || '';
    const useExtra = !!$projectGateAdditional?.checked;
    const hasSlides = useExtra && !!$projectGateHasSlides?.checked;
    const hasFolders = useExtra && !!$projectGateHasFolders?.checked;
    const minSlidesRaw = useExtra ? parseInt($projectGateMinSlides?.value || '', 10) : NaN;
    const minSlides = Number.isFinite(minSlidesRaw) ? minSlidesRaw : null;

    const filtered = list_projects.filter((project) => {
        const info = project.info || {};
        const haystack = [
            project.name,
            project.path,
            info.title,
            info.institution,
            info.department,
            info.owner,
            info.status,
            info.description,
        ].filter(Boolean).join(' ').toLowerCase();
        if (search && !haystack.includes(search)) return false;
        if (hospital && info.institution !== hospital) return false;
        if (owner && info.owner !== owner) return false;
        if (status && (info.status || 'active') !== status) return false;
        if (hasSlides && Number(project.slide_count || 0) <= 0) return false;
        if (hasFolders && Number(project.folder_count || 0) <= 0) return false;
        if (minSlides != null && Number(project.slide_count || 0) < minSlides) return false;
        return true;
    });

    const dir = _projectGateSort.dir === 'desc' ? -1 : 1;
    return filtered.sort((a, b) => {
        const av = _projectGateValue(a, _projectGateSort.key);
        const bv = _projectGateValue(b, _projectGateSort.key);
        if (typeof av === 'number' || typeof bv === 'number') {
            return (Number(av || 0) - Number(bv || 0)) * dir;
        }
        return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' }) * dir;
    });
}

function _setProjectGateSort(key) {
    if (_projectGateSort.key === key) {
        _projectGateSort.dir = _projectGateSort.dir === 'asc' ? 'desc' : 'asc';
    } else {
        _projectGateSort = {
            key,
            dir: ['slides', 'ai', 'folders'].includes(key) ? 'desc' : 'asc',
        };
    }
    _projectGatePage = 1;
    _renderProjectGate(_projectListCache);
}

function _renderProjectGatePager(total, start, end, totalPages) {
    if (!$projectGatePager) return;
    $projectGatePager.innerHTML = '';

    const summary = document.createElement('div');
    summary.className = 'project-gate-pager-summary';
    summary.textContent = total
        ? `Showing ${start} to ${end} of ${total} projects`
        : 'Showing 0 projects';

    const controls = document.createElement('div');
    controls.className = 'project-gate-pager-controls';
    if (!total) {
        $projectGatePager.append(summary);
        return;
    }

    const buttons = [
        { label: '<<', page: 1, disabled: _projectGatePage <= 1 },
        { label: '<', page: _projectGatePage - 1, disabled: _projectGatePage <= 1 },
        { label: String(_projectGatePage), page: _projectGatePage, active: true, disabled: true },
        { label: '>', page: _projectGatePage + 1, disabled: _projectGatePage >= totalPages },
        { label: '>>', page: totalPages, disabled: _projectGatePage >= totalPages },
    ];
    for (const item of buttons) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = item.label;
        btn.disabled = item.disabled;
        if (item.active) btn.classList.add('active');
        btn.addEventListener('click', () => {
            _projectGatePage = item.page;
            _renderProjectGate(_projectListCache);
        });
        controls.appendChild(btn);
    }

    $projectGatePager.append(controls, summary);
}

function _refreshProjectGate() {
    _projectGatePage = 1;
    _renderProjectGate(_projectListCache);
}

async function _loadProjectGateStats() {
    if (!$projectStatTotal) return;
    try {
        const data = await api.dashboard(false);
        const counts = data.status_counts || {};
        const ai = data.ai_counts || {};
        $projectStatTotal.textContent = data.total_slides || 0;
        $projectStatDone.textContent = counts.done || 0;
        $projectStatProgress.textContent = (counts.in_progress || 0) + (counts.pending || 0);
        $projectStatAi.textContent = Math.max(
            ai['Quanti HE'] || 0,
            ai['Quanti PD-L1'] || 0,
            ai['Quanti IHC'] || 0,
            ai['VS IHC'] || 0
        );
    } catch (err) {
        console.warn('Project summary load failed:', err);
    }
}

function _renderProjectGate(list_projects) {
    if (!$projectGateList) return;
    const list_source = Array.isArray(list_projects) ? list_projects : [];
    _populateProjectGateFilters(list_source);
    const list = _getFilteredProjectGateList(list_source);
    $projectGateList.innerHTML = '';
    if ($projectGatePager) $projectGatePager.innerHTML = '';

    if (!list_source.length) {
        const empty = document.createElement('div');
        empty.className = 'project-gate-empty';
        empty.textContent = 'No projects yet. Create a project from Home first.';
        $projectGateList.appendChild(empty);
        return;
    }

    const header = document.createElement('div');
    header.className = 'project-gate-table-head';
    [
        { label: 'Project', key: 'name' },
        { label: 'Hospital', key: 'hospital' },
        { label: 'Owner', key: 'owner' },
        { label: 'Slides', key: 'slides' },
        { label: 'AI Analyzed', key: 'ai' },
        { label: 'Folders', key: 'folders' },
        { label: 'Status', key: 'status' },
        { label: '', key: '' },
    ].forEach((col) => {
        const cell = document.createElement(col.key ? 'button' : 'span');
        if (col.key) {
            cell.type = 'button';
            cell.className = 'project-gate-sort';
            cell.dataset.sortKey = col.key;
            cell.addEventListener('click', () => _setProjectGateSort(col.key));
        }
        cell.textContent = col.label;
        if (col.key && _projectGateSort.key === col.key) {
            cell.dataset.sortDir = _projectGateSort.dir;
        }
        header.appendChild(cell);
    });
    $projectGateList.appendChild(header);

    const pageSize = _getProjectGatePageSize();
    const totalPages = Math.max(1, Math.ceil(list.length / pageSize));
    _projectGatePage = Math.max(1, Math.min(_projectGatePage, totalPages));
    const start = (_projectGatePage - 1) * pageSize;
    const paged = list.slice(start, start + pageSize);

    if (!paged.length) {
        const empty = document.createElement('div');
        empty.className = 'project-gate-empty';
        empty.textContent = 'No projects match the current filters.';
        $projectGateList.appendChild(empty);
        _renderProjectGatePager(0, 0, 0, 0);
        return;
    }

    for (const project of paged) {
        const info = project.info || {};
        const path = project.path || project.name || '';
        const title = info.title || project.name || path;

        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'project-gate-row';
        row.dataset.path = path;

        const projectEl = document.createElement('div');
        projectEl.className = 'project-gate-project';

        const titleEl = document.createElement('div');
        titleEl.className = 'project-gate-title';
        titleEl.textContent = title;

        projectEl.append(titleEl);

        const hospitalEl = document.createElement('div');
        hospitalEl.className = 'project-gate-cell';
        hospitalEl.textContent = info.institution || '-';

        const ownerEl = document.createElement('div');
        ownerEl.className = 'project-gate-cell';
        ownerEl.textContent = info.owner || '-';

        const slidesEl = document.createElement('div');
        slidesEl.className = 'project-gate-cell project-gate-number';
        slidesEl.textContent = project.slide_count || 0;

        const aiEl = document.createElement('div');
        aiEl.className = 'project-gate-cell project-gate-number';
        aiEl.textContent = project.ai_analyzed_count || 0;

        const foldersEl = document.createElement('div');
        foldersEl.className = 'project-gate-cell project-gate-number';
        foldersEl.textContent = project.folder_count || 0;

        const statusEl = document.createElement('div');
        statusEl.className = 'project-gate-cell';
        const statusChip = document.createElement('span');
        statusChip.className = 'project-gate-status';
        statusChip.textContent = info.status || 'active';
        statusEl.appendChild(statusChip);

        const actionEl = document.createElement('div');
        actionEl.className = 'project-gate-action';
        actionEl.textContent = 'Open';

        row.append(projectEl, hospitalEl, ownerEl, slidesEl, aiEl, foldersEl, statusEl, actionEl);
        row.addEventListener('click', () => _enterProjectFromGate(path));
        $projectGateList.appendChild(row);
    }
    _renderProjectGatePager(list.length, start + 1, start + paged.length, totalPages);
}

function _showProjectGate(list_projects = _projectListCache) {
    if (!$projectGate) return;
    _renderProjectGate(list_projects);
    $projectGate.hidden = false;
    document.body.classList.add('project-gate-open');
    setStatus('Ready');
}

function _hideProjectGate() {
    if ($projectGate) $projectGate.hidden = true;
    document.documentElement.classList.remove('project-gate-boot');
    document.body.classList.remove('project-gate-open');
}

function _enterProjectFromGate(path) {
    if (!path) return;
    _hideProjectGate();
    currentBrowsePath = path;
    history.replaceState(null, '', `/ai?path=${encodeURIComponent(path)}`);
    loadSlideList();
}

[$projectGateSearch, $projectGateHospital, $projectGateOwner, $projectGateStatus,
 $projectGatePageSize, $projectGateHasSlides, $projectGateHasFolders, $projectGateMinSlides]
    .filter(Boolean)
    .forEach((el) => {
        el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', _refreshProjectGate);
    });

if ($projectGateAdditional) {
    $projectGateAdditional.addEventListener('change', () => {
        if ($projectGateExtra) $projectGateExtra.hidden = !$projectGateAdditional.checked;
        _refreshProjectGate();
    });
}

async function loadSlideList() {
    try {
        const data = await api.browse(currentBrowsePath);
        _lastBrowseData = data || { folders: [], slides: [] };
        renderSlideList(_lastBrowseData);
    } catch (err) {
        console.error('Slide list load failed:', err);
    }
}

function _hasSlideAiResult(slide) {
    const aiResults = slide?.ai_results || {};
    return Object.values(aiResults).some((result) => !!result?.has_result);
}

function _hasSlideClinicalInfo(slide) {
    if (slide?.has_clinical_info) return true;
    const info = slide?.clinical_info || {};
    return Object.values(info).some((value) => String(value || '').trim() !== '');
}

function _makeSlideStateCell(kind, state, title) {
    const cell = document.createElement('span');
    cell.className = `slide-state-cell ${kind} ${state}`;
    cell.title = title || '';
    if (state === 'ready') {
        cell.textContent = '\u2713';
    } else if (state === 'running') {
        cell.textContent = '';
    } else {
        cell.textContent = '-';
    }
    return cell;
}

function _getFilteredSlides(slides) {
    const query = String($slideNameSearch?.value || '').trim().toLowerCase();
    if (!query) return slides || [];
    return (slides || []).filter((slide) => String(slide.filename || '').toLowerCase().includes(query));
}

function renderSlideList(data = _lastBrowseData) {
        $slideList.innerHTML = '';
        _syncProjectSelect();
        const filteredSlides = _getFilteredSlides(data.slides || []);

        if ((data.folders || []).length === 0 && filteredSlides.length === 0) {
            $slideList.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;text-align:center;">Empty</div>';
        }

        for (const f of data.folders || []) {
            const folderPath = currentBrowsePath ? `${currentBrowsePath}/${f.name}` : f.name;
            const item = document.createElement('div');
            item.className = 'slide-list-item folder-item';
            item.dataset.folderPath = folderPath;

            const icon = document.createElement('span');
            icon.className = 'folder-icon';
            icon.textContent = 'Folder';

            const name = document.createElement('div');
            name.className = 'slide-list-name';
            name.textContent = f.name;

            item.append(icon, name);

            item.addEventListener('click', () => navigateToFolder(folderPath));
            item.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                showFolderContextMenu(e, folderPath, f.name);
            });
            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                item.classList.add('drag-over');
            });
            item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
            item.addEventListener('drop', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                item.classList.remove('drag-over');
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    await uploadFiles(e.dataTransfer.files, folderPath);
                } else {
                    await _dropMoveFiles(e, folderPath);
                }
            });

            $slideList.appendChild(item);
        }

        for (const s of filteredSlides) {
            const item = document.createElement('div');
            item.className = 'slide-list-item';
            const strSlideStatus = s.ai_status || '';
            if (strSlideStatus) item.classList.add(`status-${strSlideStatus}`);
            item.dataset.filename = s.filename;
            item.dataset.slideId = s.slide_id;
            item.dataset.status = strSlideStatus;
            item.draggable = true;

            const thumb = document.createElement('img');
            thumb.className = 'slide-thumb';
            thumb.alt = s.filename;
            thumb.loading = 'lazy';
            const str_thumb_filename = s.filename;
            const str_thumb_path = currentBrowsePath;
            thumb.src = api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 300);
            api.attachMediaImageRetry(thumb,
                () => api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 300),
                () => { thumb.style.display = 'none'; });

            const name = document.createElement('div');
            name.className = 'slide-list-name';
            name.textContent = s.filename;
            name.title = `${s.filename} (${s.size_mb} MB)`;

            const nameWrap = document.createElement('div');
            nameWrap.className = 'slide-name-cell';
            nameWrap.append(thumb, name);

            const clinicalCell = _makeSlideStateCell(
                'clinical',
                _hasSlideClinicalInfo(s) ? 'ready' : 'empty',
                _hasSlideClinicalInfo(s) ? 'Clinical info saved' : 'No clinical info'
            );
            const aiCell = _makeSlideStateCell(
                'ai',
                _hasSlideAiResult(s) ? 'ready' : 'empty',
                _hasSlideAiResult(s) ? 'AI result exists' : 'No AI result'
            );

            item.append(nameWrap, clinicalCell, aiCell);

            if (strSlideStatus) {
                const statusMeta = {
                    pending:     { label: 'P', color: '#95a5a6', title: 'AI Pending' },
                    in_progress: { label: 'I', color: '#3498db', title: 'AI In Progress' },
                    done:        { label: 'D', color: '#27ae60', title: 'AI Reviewed' },
                    flagged:     { label: 'F', color: '#e74c3c', title: 'AI Flagged' },
                };
                const m = statusMeta[strSlideStatus];
                if (m) {
                    const dot = document.createElement('span');
                    dot.className = 'slide-status-dot';
                    dot.textContent = m.label;
                    dot.style.background = m.color;
                    dot.title = m.title;
                    item.appendChild(dot);
                }
            }

            item.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (!item.classList.contains('selected')) {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                }
                showSlideContextMenu(e);
            });

            item.addEventListener('click', (e) => {
                if (e.ctrlKey || e.metaKey) {
                    item.classList.toggle('selected');
                } else if (e.shiftKey) {
                    const allItems = [...$slideList.querySelectorAll('.slide-list-item:not(.folder-item)')];
                    const lastIdx = allItems.findIndex(el => el.classList.contains('selected'));
                    const curIdx = allItems.indexOf(item);
                    if (lastIdx >= 0 && curIdx >= 0) {
                        const [from, to] = lastIdx < curIdx ? [lastIdx, curIdx] : [curIdx, lastIdx];
                        for (let i = from; i <= to; i++) allItems[i].classList.add('selected');
                    } else {
                        item.classList.add('selected');
                    }
                } else {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                    openSavedSlide(s.filename, item);
                }
            });

            item.addEventListener('dragstart', (e) => {
                if (!item.classList.contains('selected')) {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                }
                const selectedFiles = [...$slideList.querySelectorAll('.slide-list-item.selected')]
                    .map(el => el.dataset.filename)
                    .filter(Boolean);
                e.dataTransfer.setData('text/filenames', JSON.stringify(selectedFiles));
                e.dataTransfer.setData('text/filename', selectedFiles[0]);
                e.dataTransfer.effectAllowed = 'move';
                requestAnimationFrame(() => {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.add('dragging'));
                });
            });
            item.addEventListener('dragend', () => {
                $slideList.querySelectorAll('.slide-list-item.dragging').forEach(el => el.classList.remove('dragging'));
            });

            $slideList.appendChild(item);
        }

        updateBreadcrumb();
        _refreshAiActiveBadges();
        _startAiActivePolling();
}

$slideNameSearch?.addEventListener('input', () => renderSlideList(_lastBrowseData));

let _aiActivePollTimer = null;
function _startAiActivePolling() {
    if (_isViewerRole()) {
        _stopAiActivePolling();
        return;
    }
    if (_aiActivePollTimer) return;
    _aiActivePollTimer = setInterval(_refreshAiActiveBadges, 4000);
}
function _stopAiActivePolling() {
    if (_aiActivePollTimer) {
        clearInterval(_aiActivePollTimer);
        _aiActivePollTimer = null;
    }
}
async function _refreshAiActiveBadges() {
    if (_isViewerRole()) {
        $slideList?.querySelectorAll('.slide-ai-active').forEach(el => el.remove());
        return;
    }

    let dict_active = {};
    try {
        const data = await api.getActiveAiTasks();
        dict_active = data.active || {};
    } catch (_) { return; }

    const items = $slideList.querySelectorAll('.slide-list-item[data-filename]');
    items.forEach((item) => {
        const fn = item.dataset.filename;
        const list_running = dict_active[fn];
        const existing = item.querySelector('.slide-ai-active');
        const aiCell = item.querySelector('.slide-state-cell.ai');
        if (list_running && list_running.length > 0) {
            const str_title = list_running
                .map(t => `${t.model}${t.variant ? '/' + t.variant : ''} · ${t.status}`)
                .join(', ');
            if (aiCell) {
                aiCell.classList.remove('empty', 'ready');
                aiCell.classList.add('running');
                aiCell.textContent = '';
                aiCell.title = str_title || 'AI in progress';
            }
            if (existing) {
                existing.title = str_title;
            } else if (!aiCell) {
                const badge = document.createElement('span');
                badge.className = 'slide-ai-active';
                badge.title = str_title;
                item.appendChild(badge);
            }
        } else {
            if (existing) existing.remove();
            if (aiCell) {
                const hasAi = _hasSlideAiResult(_findSlideByFilename(fn));
                aiCell.classList.remove('running', hasAi ? 'empty' : 'ready');
                aiCell.classList.add(hasAi ? 'ready' : 'empty');
                aiCell.textContent = hasAi ? '\u2713' : '-';
                aiCell.title = hasAi ? 'AI result exists' : 'No AI result';
            }
        }
    });
}

function _findSlideByFilename(filename) {
    return (_lastBrowseData.slides || []).find((slide) => slide.filename === filename) || null;
}

function navigateToFolder(path) {
    _hideProjectGate();
    currentBrowsePath = path;
    loadSlideList();
}

if ($projectSelect) {
    $projectSelect.addEventListener('change', () => {
        if ($projectSelect.value) navigateToFolder($projectSelect.value);
    });
}

async function _dropMoveFiles(e, targetPath) {
    let filenames = [];
    try { filenames = JSON.parse(e.dataTransfer.getData('text/filenames') || '[]'); } catch {}
    if (!filenames.length) {
        const single = e.dataTransfer.getData('text/filename');
        if (single) filenames = [single];
    }
    if (!filenames.length || targetPath === currentBrowsePath) return;
    try {
        for (const fn of filenames) {
            await api.moveFile(fn, currentBrowsePath, targetPath);
        }
        loadSlideList();
        setStatus(`${filenames.length} files moved`);
    } catch (err) { setStatus(`Move failed: ${err.message}`); }
}

function _makeBreadcrumbDroppable(el, targetPath) {
    el.addEventListener('dragover', (e) => { e.preventDefault(); el.style.background = 'var(--accent-light)'; });
    el.addEventListener('dragleave', () => { el.style.background = ''; });
    el.addEventListener('drop', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        el.style.background = '';
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            await uploadFiles(e.dataTransfer.files, targetPath);
        } else {
            await _dropMoveFiles(e, targetPath);
        }
    });
}

// Initialize OS file drop on the left slide list into the current folder.
(function _initSlideListOsDrop() {
    $slideList.addEventListener('dragover', (e) => {
        if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
        e.preventDefault();
        $slideList.classList.add('drag-over-panel');
    });
    $slideList.addEventListener('dragleave', (e) => {
        if (e.target === $slideList) $slideList.classList.remove('drag-over-panel');
    });
    $slideList.addEventListener('drop', async (e) => {
        if (!e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
        e.preventDefault();
        $slideList.classList.remove('drag-over-panel');
        await uploadFiles(e.dataTransfer.files, currentBrowsePath);
    });
})();

function updateBreadcrumb() {
    $breadcrumb.innerHTML = '';
    const projectName = _getCurrentProjectName();
    const root = document.createElement('span');
    root.className = 'breadcrumb-item';
    root.textContent = projectName ? _projectLabelForPath(projectName) : 'Projects';
    root.addEventListener('click', () => {
        if (projectName) navigateToFolder(projectName);
        else _showProjectGate(_projectListCache);
    });
    if (projectName) _makeBreadcrumbDroppable(root, projectName);
    $breadcrumb.appendChild(root);

    if (projectName && currentBrowsePath) {
        const parts = currentBrowsePath.split('/').slice(1);
        let accumulated = '';
        for (const part of parts) {
            accumulated = accumulated ? `${accumulated}/${part}` : `${projectName}/${part}`;
            const sep = document.createElement('span');
            sep.className = 'breadcrumb-sep';
            sep.textContent = '>';
            $breadcrumb.appendChild(sep);

            const crumb = document.createElement('span');
            crumb.className = 'breadcrumb-item';
            crumb.textContent = part;
            const targetPath = accumulated;
            crumb.addEventListener('click', () => navigateToFolder(targetPath));
            _makeBreadcrumbDroppable(crumb, targetPath);
            $breadcrumb.appendChild(crumb);
        }
    }
}

async function openSavedSlide(filename, itemEl) {
    setStatus('Opening...');
    try {
        const info = await api.openSlide(filename, currentBrowsePath);
        if (info.exists) {
            $slideList.querySelectorAll('.slide-list-item').forEach(el => el.classList.remove('active'));
            if (itemEl) itemEl.classList.add('active');
            onSlideLoaded(info.slide_id, info, filename);
        }
    } catch (err) {
        setStatus(`Move failed: ${err.message}`);
    }
}

$('#btn-new-folder').addEventListener('click', async () => {
    if (!_getCurrentProjectName()) {
        alert('Select a project before creating folders.');
        _showProjectGate(_projectListCache);
        return;
    }
    const name = prompt('Folder name:');
    if (!name || !name.trim()) return;
    try {
        await api.createFolder(currentBrowsePath, name.trim());
        loadSlideList();
    } catch (err) {
        alert(`Folder creation failed: ${err.message}`);
    }
});

let _ctxMenu = null;

function removeCtxMenu() {
    if (_ctxMenu) { _ctxMenu.remove(); _ctxMenu = null; }
}
document.addEventListener('click', removeCtxMenu);

function showFolderContextMenu(e, folderPath, folderName) {
    removeCtxMenu();
    const menu = document.createElement('div');
    menu.className = 'ctx-menu';
    menu.style.left = `${e.clientX}px`;
    menu.style.top = `${e.clientY}px`;

    const renameBtn = document.createElement('div');
    renameBtn.className = 'ctx-menu-item';
    renameBtn.textContent = 'Rename';
    renameBtn.addEventListener('click', async () => {
        removeCtxMenu();
        const newName = prompt('New name:', folderName);
        if (!newName || !newName.trim() || newName.trim() === folderName) return;
        try {
            await api.renameFolder(folderPath, newName.trim());
            loadSlideList();
        } catch (err) {
            alert(`Rename failed: ${err.message}`);
        }
    });

    const deleteBtn = document.createElement('div');
    deleteBtn.className = 'ctx-menu-item danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', async () => {
        removeCtxMenu();
        if (!confirm(`Delete folder "${folderName}"?`)) return;
        try {
            await api.deleteFolder(folderPath);
            loadSlideList();
        } catch (err) {
            alert(`Delete failed: ${err.message}`);
        }
    });

    const aiCfgBtn = document.createElement('div');
    aiCfgBtn.className = 'ctx-menu-item';
    aiCfgBtn.textContent = 'Auto AI Settings...';
    aiCfgBtn.addEventListener('click', () => {
        removeCtxMenu();
        openFolderAiConfigDialog(folderPath, folderName);
    });

    menu.append(renameBtn, deleteBtn, aiCfgBtn);
    document.body.appendChild(menu);
    _ctxMenu = menu;
}

function _getSelectedSlideFilenames() {
    return [...$slideList.querySelectorAll('.slide-list-item.selected:not(.folder-item)')]
        .map(el => el.dataset.filename)
        .filter(Boolean);
}

async function _deleteSelectedSlides() {
    const list_filenames = _getSelectedSlideFilenames();
    if (list_filenames.length === 0) return;

    const int_count = list_filenames.length;
    const str_msg = int_count === 1
        ? `Delete "${list_filenames[0]}"?\n\nAll AI analysis results for this slide will also be permanently deleted.\n\nThis action cannot be undone.`
        : `Delete ${int_count} selected slides?\n\nAll AI analysis results for these slides will also be permanently deleted.\n\nThis action cannot be undone.`;

    if (!confirm(str_msg)) return;

    try {
        setStatus(`Deleting ${int_count} slide(s)...`);
        const res = await api.deleteFiles(list_filenames, currentBrowsePath);
        const int_done = (res.deleted || []).length;
        const int_err = (res.errors || []).length;
        if (int_err > 0) {
            alert(`${int_done} deleted, ${int_err} failed:\n${(res.errors || []).map(e => `${e.filename}: ${e.error}`).join('\n')}`);
        } else {
            setStatus(`Deleted ${int_done} slide(s)`);
        }
        loadSlideList();
    } catch (err) {
        alert(`Failed to delete: ${err.message}`);
    }
}

function showSlideContextMenu(e) {
    removeCtxMenu();
    const list_filenames = _getSelectedSlideFilenames();
    if (list_filenames.length === 0) return;

    const menu = document.createElement('div');
    menu.className = 'ctx-menu';
    menu.style.left = `${e.clientX}px`;
    menu.style.top = `${e.clientY}px`;

    const header = document.createElement('div');
    header.className = 'ctx-menu-header';
    header.textContent = list_filenames.length === 1
        ? list_filenames[0]
        : `${list_filenames.length} slides selected`;
    menu.appendChild(header);

    const deleteBtn = document.createElement('div');
    deleteBtn.className = 'ctx-menu-item danger';
    deleteBtn.textContent = list_filenames.length === 1 ? 'Delete' : `Delete ${list_filenames.length} slides`;
    deleteBtn.addEventListener('click', () => {
        removeCtxMenu();
        _deleteSelectedSlides();
    });
    menu.appendChild(deleteBtn);

    document.body.appendChild(menu);
    _ctxMenu = menu;
}

(function _initMarqueeSelection() {
    let bool_active = false;
    let int_startX = 0;
    let int_startY = 0;
    let el_rect = null;
    let list_baseline = [];

    $slideList.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        if (e.target.closest('.slide-list-item')) return;
        const rect_panel = $slideList.getBoundingClientRect();
        if (e.clientX < rect_panel.left || e.clientX > rect_panel.right) return;

        bool_active = true;
        int_startX = e.clientX;
        int_startY = e.clientY;

        if (e.ctrlKey || e.metaKey || e.shiftKey) {
            list_baseline = [...$slideList.querySelectorAll('.slide-list-item.selected')];
        } else {
            list_baseline = [];
            $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
        }

        el_rect = document.createElement('div');
        el_rect.className = 'slide-marquee-rect';
        el_rect.style.left = `${int_startX}px`;
        el_rect.style.top = `${int_startY}px`;
        el_rect.style.width = '0px';
        el_rect.style.height = '0px';
        document.body.appendChild(el_rect);
        e.preventDefault();
    });

    window.addEventListener('mousemove', (e) => {
        if (!bool_active || !el_rect) return;
        const x = Math.min(e.clientX, int_startX);
        const y = Math.min(e.clientY, int_startY);
        const w = Math.abs(e.clientX - int_startX);
        const h = Math.abs(e.clientY - int_startY);
        el_rect.style.left = `${x}px`;
        el_rect.style.top = `${y}px`;
        el_rect.style.width = `${w}px`;
        el_rect.style.height = `${h}px`;

        const rectBox = { left: x, top: y, right: x + w, bottom: y + h };
        const list_items = $slideList.querySelectorAll('.slide-list-item:not(.folder-item)');
        const set_base = new Set(list_baseline);
        for (const el of list_items) {
            const r = el.getBoundingClientRect();
            const bool_intersect = !(r.right < rectBox.left || r.left > rectBox.right ||
                                     r.bottom < rectBox.top || r.top > rectBox.bottom);
            if (bool_intersect || set_base.has(el)) {
                el.classList.add('selected');
            } else {
                el.classList.remove('selected');
            }
        }
    });

    window.addEventListener('mouseup', () => {
        if (!bool_active) return;
        bool_active = false;
        if (el_rect) { el_rect.remove(); el_rect = null; }
    });
})();

$slideList.addEventListener('contextmenu', (e) => {
    if (!e.target.closest('.slide-list-item')) {
        const list_sel = $slideList.querySelectorAll('.slide-list-item.selected:not(.folder-item)');
        if (list_sel.length > 0) {
            e.preventDefault();
            showSlideContextMenu(e);
        }
    }
});

const AUTO_AI_TASK_OPTIONS = [
    { model: 'Quanti HE',      variant: 'Stomach', label: 'Quanti HE · Stomach' },
    { model: 'Quanti HE',      variant: 'Breast',  label: 'Quanti HE · Breast' },
    { model: 'Quanti HE',      variant: 'Other',   label: 'Quanti HE · Other' },
    { model: 'Quanti PD-L1',    variant: 'Stomach', label: 'Quanti PD-L1 · Stomach (CPS)' },
    { model: 'Quanti PD-L1',    variant: 'Lung',    label: 'Quanti PD-L1 · Lung (TPS)' },
    { model: 'Quanti IHC', variant: 'HER2',    label: 'Quanti IHC · HER2' },
    { model: 'Quanti IHC', variant: 'ER_PR',   label: 'Quanti IHC · ER/PR (Allred)' },
    { model: 'Quanti IHC', variant: 'KI_67',   label: 'Quanti IHC · KI-67' },
    { model: 'VS IHC',      variant: 'ihc_membrane', label: 'VS IHC (Virtual Stain)', mpp: true },
];
const VS_MPP_CHOICES = [
    { value: 4.0, label: '4.0 µm/px (x2.5)' },
    { value: 2.0, label: '2.0 µm/px (x5)' },
    { value: 1.0, label: '1.0 µm/px (x10)' },
    { value: 0.5, label: '0.5 µm/px (x20)' },
];

async function openFolderAiConfigDialog(folderPath, folderName) {
    let cfg = { enabled: false, tasks: [] };
    try { cfg = await api.getFolderAiConfig(folderPath); }
    catch (err) { console.warn('Folder config load failed:', err); }

    // Selected base model keys.
    const set_selected = new Set();
    const dict_vs_mpps = {};  // { variant: Set<number> }
    for (const t of (cfg.tasks || [])) {
        if (t.model === 'VS IHC') {
            if (!dict_vs_mpps[t.variant]) dict_vs_mpps[t.variant] = new Set();
            dict_vs_mpps[t.variant].add(Number(t.target_mpp ?? 2.0));
        } else {
            set_selected.add(`${t.model}::${t.variant}`);
        }
    }

    const backdrop = document.createElement('div');
    backdrop.className = 'ai-cfg-backdrop';
    backdrop.innerHTML = `
        <div class="ai-cfg-card">
            <div class="ai-cfg-header">
                <span>Auto AI Settings - ${folderName}</span>
                <button class="ai-cfg-close" type="button">&times;</button>
            </div>
            <div class="ai-cfg-body">
                <label class="ai-cfg-enable">
                    <input type="checkbox" id="ai-cfg-enabled"${cfg.enabled ? ' checked' : ''}>
                    <span>Enable auto analysis for this folder</span>
                </label>
                <div class="ai-cfg-hint">
                    When the system is idle for 10 minutes, this folder is scanned every minute
                    and selected models are run automatically on unanalyzed slides.
                </div>
                <div class="ai-cfg-list" id="ai-cfg-list"></div>
            </div>
            <div class="ai-cfg-footer">
                <button type="button" class="ai-cfg-btn ai-cfg-cancel">Cancel</button>
                <button type="button" class="ai-cfg-btn ai-cfg-save primary">Save</button>
            </div>
        </div>
    `;
    document.body.appendChild(backdrop);

    const $list = backdrop.querySelector('#ai-cfg-list');
    for (const opt of AUTO_AI_TASK_OPTIONS) {
        const key = `${opt.model}::${opt.variant}`;
        const wrap = document.createElement('div');
        wrap.className = 'ai-cfg-item';
        wrap.dataset.model = opt.model;
        wrap.dataset.variant = opt.variant;

        if (opt.mpp) {
            const set_current = dict_vs_mpps[opt.variant] || new Set();
            const bool_parent_checked = set_current.size > 0;
            wrap.innerHTML = `
                <label class="ai-cfg-row">
                    <input type="checkbox" class="ai-cfg-parent"${bool_parent_checked ? ' checked' : ''}>
                    <span>${opt.label}</span>
                </label>
                <div class="ai-cfg-sub"${bool_parent_checked ? '' : ' hidden'}>
                    <div class="ai-cfg-sub-title">Target resolutions:</div>
                    ${VS_MPP_CHOICES.map(m => `
                        <label class="ai-cfg-sub-row">
                            <input type="checkbox" class="ai-cfg-mpp" data-mpp="${m.value}"${set_current.has(m.value) ? ' checked' : ''}>
                            <span>${m.label}</span>
                        </label>
                    `).join('')}
                </div>
            `;
            const $parent = wrap.querySelector('.ai-cfg-parent');
            const $sub = wrap.querySelector('.ai-cfg-sub');
            $parent.addEventListener('change', () => {
                if ($parent.checked) {
                    $sub.hidden = false;
                    const checked = wrap.querySelectorAll('.ai-cfg-mpp:checked');
                    if (checked.length === 0) {
                        const $def = wrap.querySelector('.ai-cfg-mpp[data-mpp="2"]');
                        if ($def) $def.checked = true;
                    }
                } else {
                    $sub.hidden = true;
                    wrap.querySelectorAll('.ai-cfg-mpp').forEach(cb => { cb.checked = false; });
                }
            });
        } else {
            wrap.innerHTML = `
                <label class="ai-cfg-row">
                    <input type="checkbox" data-key="${key}"${set_selected.has(key) ? ' checked' : ''}>
                    <span>${opt.label}</span>
                </label>
            `;
        }
        $list.appendChild(wrap);
    }

    const close = () => backdrop.remove();
    backdrop.querySelector('.ai-cfg-close').addEventListener('click', close);
    backdrop.querySelector('.ai-cfg-cancel').addEventListener('click', close);
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });

    backdrop.querySelector('.ai-cfg-save').addEventListener('click', async () => {
        const enabled = backdrop.querySelector('#ai-cfg-enabled').checked;
        const tasks = [];
        backdrop.querySelectorAll('.ai-cfg-item').forEach((wrap) => {
            const str_model = wrap.dataset.model;
            const str_variant = wrap.dataset.variant;
            if (str_model === 'VS IHC') {
                const $parent = wrap.querySelector('.ai-cfg-parent');
                if (!$parent || !$parent.checked) return;
                const list_mpps = [...wrap.querySelectorAll('.ai-cfg-mpp:checked')]
                    .map(cb => parseFloat(cb.dataset.mpp));
                if (list_mpps.length === 0) return;
                list_mpps.forEach(mpp => {
                    tasks.push({ model: str_model, variant: str_variant, target_mpp: mpp });
                });
            } else {
                const $cb = wrap.querySelector('input[type="checkbox"]');
                if ($cb && $cb.checked) {
                    tasks.push({ model: str_model, variant: str_variant });
                }
            }
        });
        try {
            await api.saveFolderAiConfig(folderPath, enabled, tasks);
            setStatus(`Auto AI settings saved: ${tasks.length} tasks`);
            close();
        } catch (err) {
            alert(`Save failed: ${err.message}`);
        }
    });
}

const $btnViewList = $('#btn-view-list');
const $btnViewGrid = $('#btn-view-grid');

$btnViewList.addEventListener('click', () => {
    $slideList.classList.remove('grid-view');
    $btnViewList.classList.add('active');
    $btnViewGrid.classList.remove('active');
});
$btnViewGrid.addEventListener('click', () => {
    $slideList.classList.add('grid-view');
    $btnViewGrid.classList.add('active');
    $btnViewList.classList.remove('active');
});

async function startVirtualStain(stainType) {
    if (_blockViewerAction()) return;
    if (!currentSlideId) return;
    const str_key = 'vs-' + stainType;
    if (await _maybeCancelRunning(str_key)) return;

    const btnEl = $btnVsMembrane;
    _runningAiTasks[str_key] = { task_id: null, buttonEl: btnEl };
    _vsRunning = true;
    _setButtonRunning(btnEl, true);
    $progressLabel.textContent = 'Virtual Staining...';
    setProgress(0);
    setStatus('Virtual staining started...');

    viewer.setDrawMode(null);

    const roiAnns = viewer.annotations.filter(a =>
        a.visible && a.type !== 'point' && a.coordinates.length >= 3);
    const roiPolygons = roiAnns.length > 0 ? roiAnns.map(a => a.coordinates) : null;

    const targetMpp = _vsMppFromSlider();

    try {
        const { task_id } = await api.startVirtualStain(currentSlideId, stainType, roiPolygons, targetMpp);
        if (_runningAiTasks[str_key]) {
            _runningAiTasks[str_key].task_id = task_id;
            if (_runningAiTasks[str_key].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
            }
        }
        _vsLastTargetMpp = targetMpp;

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks[str_key]) return;
            const st = await api.getTaskStatus(task_id);
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);

            if (st.status === 'completed') {
                const result = await api.getTaskResult(task_id, _makeResultDownloadProgress());
                onVirtualStainComplete(result);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus('Virtual staining cancelled. Partial results were cleared.');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`Virtual staining failed: ${err.message}`);
        $progressLabel.textContent = 'Virtual staining failed';
    } finally {
        delete _runningAiTasks[str_key];
        _vsRunning = false;
        _setButtonRunning(btnEl, false);
    }
}

function onVirtualStainComplete(result) {
    const stain = result.stain_type || 'ihc_membrane';
    const tmpp = result.target_mpp || _vsLastTargetMpp || 2.0;
    viewer.setVirtualStainOverlay({
        slide_id: currentSlideId,
        stain_type: stain,
        target_mpp: tmpp,
        roi_origin: result.roi_origin,
        canvas_l0_w: result.canvas_l0_w,
        canvas_l0_h: result.canvas_l0_h,
        tile_size: result.tile_size || 512,
        levels: result.levels || [],
        roi_polygons: result.roi_polygons || null,
    });
    _setVsToggleState(true, false);
    _setVsSplitState(false, false);
    viewer.clearAnnotations();
    renderAnnotationPanel();

    const tc = result.tissue_count || 0;
    const tot = result.total_patches || 0;
    setProgress(100);
    $progressLabel.textContent = result.cached
        ? 'Virtual staining loaded (cached)'
        : 'Virtual staining complete';
    setStatus(`Virtual staining complete - ${tc}/${tot} tissue patches`);
}

const VS_MPP_VALUES = [4.0, 2.0, 1.0, 0.5];
const VS_MPP_LABELS = [
    '4.0 µm/px (x2.5)',
    '2.0 µm/px (x5)',
    '1.0 µm/px (x10)',
    '0.5 µm/px (x20)',
];
function _vsMppFromSlider() {
    const el = document.querySelector('#vs-target-mpp');
    const idx = el ? parseInt(el.value, 10) : 1;
    return VS_MPP_VALUES[idx] ?? 2.0;
}
const $vsMppSlider = document.querySelector('#vs-target-mpp');
const $vsMppLabel = document.querySelector('#vs-mpp-label');
$vsMppSlider?.addEventListener('input', () => {
    const idx = parseInt($vsMppSlider.value, 10);
    if ($vsMppLabel) $vsMppLabel.textContent = VS_MPP_LABELS[idx] || '';
});

$btnVsMembrane?.addEventListener('click', () => startVirtualStain('ihc_membrane'));

// Quanti PD-L1 scoring.
$btnPdScore?.addEventListener('click', startPdScore);

async function startPdScore() {
    if (_blockViewerAction()) return;
    if (!currentSlideId) return;
    if (await _maybeCancelRunning('pd-score')) return;

    _runningAiTasks['pd-score'] = { task_id: null, buttonEl: $btnPdScore };
    _setButtonRunning($btnPdScore, true);
    if ($pdScoreResult) $pdScoreResult.hidden = true;
    $progressLabel.textContent = 'PD-L1 Detection...';
    setProgress(0);
    setStatus('Quanti PD-L1 started...');

    viewer.setDrawMode(null);

    try {
        const tissueType = document.querySelector('input[name="pd-tissue-type"]:checked')?.value || 'Stomach';
        const roiAnnotations = viewer.annotations.filter(a => a.visible && a.type !== 'point' && a.coordinates.length >= 3);
        const roiPolygons = roiAnnotations.length > 0 ? roiAnnotations.map(a => a.coordinates) : null;

        const { task_id } = await api.startPdScore(currentSlideId, roiPolygons, tissueType);
        if (_runningAiTasks['pd-score']) {
            _runningAiTasks['pd-score'].task_id = task_id;
            if (_runningAiTasks['pd-score'].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
            }
        }

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks['pd-score']) return;
            const st = await api.getTaskStatus(task_id);
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);
            $progressLabel.textContent = 'PD-L1 Detection';

            if (st.status === 'completed') {
                const result = await api.getTaskResult(task_id, _makeResultDownloadProgress());
                onPdScoreComplete(result, roiPolygons, tissueType);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus('Quanti PD-L1 cancelled. Partial results were cleared.');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`Quanti PD-L1 failed: ${err.message}`);
    } finally {
        delete _runningAiTasks['pd-score'];
        _setButtonRunning($btnPdScore, false);
        if ($progressLabel.textContent === 'PD-L1 Detection...') {
            $progressLabel.textContent = 'AI Progress';
        }
    }
}

function onPdScoreComplete(result, roiPolygons = null, tissueType = null) {
    $progressLabel.textContent = 'Quanti PD-L1 Complete';

    viewer.clearAnnotations();
    renderAnnotationPanel();

    _lastDetectionResult = result;
    _lastDetectionTissue = tissueType;
    _lastDetectionModel = 'Quanti PD-L1';
    _lastDetectionRoi = roiPolygons;
    lastSegData = null;

    const colorMap = {};
    if (result.class_colors) {
        for (const [k, v] of Object.entries(result.class_colors)) {
            colorMap[parseInt(k)] = v;
        }
    }
    viewer.classColorOverride = Object.keys(colorMap).length > 0 ? colorMap : null;
    viewer.defaultConfidence = 0.1;

    viewer.setDetectionResults(result.cells, roiPolygons);
    viewer.setHiddenDetectionResults?.(result.excluded_cells || [], roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    if ($pdScoreResult) $pdScoreResult.hidden = false;

    const { counts: dict_counts_status } = _computeFilteredCounts(viewer.detectionCells);
    const str_score_type = (result.pd_score && result.pd_score.score_type) || 'Score';
    let float_status_score = 0;
    if (str_score_type === 'CPS') {
        const pt = dict_counts_status[3] || 0;
        const pi = (dict_counts_status[4] || 0) + (dict_counts_status[5] || 0);
        const viable = (dict_counts_status[0] || 0) + pt;
        float_status_score = viable === 0 ? 0 : Math.min(100, (pt + pi) / viable * 100);
    } else if (str_score_type === 'TPS') {
        const pt = dict_counts_status[1] || 0;
        const tot = pt + (dict_counts_status[0] || 0);
        float_status_score = tot === 0 ? 0 : pt / tot * 100;
    }
    setStatus(`${str_score_type}: ${float_status_score.toFixed(1)}% | ${displayCount.toLocaleString()} cells`);

    _lastDetectionResult.cells = viewer.detectionCells;
    _lastDetectionResult.total_cells = viewer.detectionCells.length;

    buildResultList(_lastDetectionResult);
    _updateResultCounts();
    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
}

$btnIhcHer2?.addEventListener('click', () => startPreciseIhc('HER2'));
$btnIhcErPr?.addEventListener('click', () => startPreciseIhc('ER_PR'));
$btnIhcKi67?.addEventListener('click', () => startPreciseIhc('KI_67'));

function _setIhcMarkerButtonsDisabled(disabled) {
    if ($btnIhcHer2) $btnIhcHer2.disabled = disabled;
    if ($btnIhcErPr) $btnIhcErPr.disabled = disabled;
    if ($btnIhcKi67) $btnIhcKi67.disabled = disabled;
}

async function startPreciseIhc(marker) {
    if (_blockViewerAction()) return;
    if (!currentSlideId) return;
    const str_key = 'ihc-' + marker;
    if (await _maybeCancelRunning(str_key)) return;

    const btnEl = marker === 'ER_PR' ? $btnIhcErPr : (marker === 'KI_67' ? $btnIhcKi67 : $btnIhcHer2);
    const markerLabel = marker === 'ER_PR' ? 'ER/PR' : (marker === 'KI_67' ? 'KI-67' : marker);
    _runningAiTasks[str_key] = { task_id: null, buttonEl: btnEl };
    _setButtonRunning(btnEl, true);
    if ($ihcScoreResult) $ihcScoreResult.hidden = true;
    $progressLabel.textContent = `${markerLabel} Detection...`;
    setProgress(0);
    setStatus(`${markerLabel} started...`);

    viewer.setDrawMode(null);

    try {
        const roiAnnotations = viewer.annotations.filter(
            a => a.visible && a.type !== 'point' && a.coordinates.length >= 3
        );
        const roiPolygons = roiAnnotations.length > 0 ? roiAnnotations.map(a => a.coordinates) : null;

        const { task_id } = await api.startPreciseIhc(currentSlideId, roiPolygons, marker);
        if (_runningAiTasks[str_key]) {
            _runningAiTasks[str_key].task_id = task_id;
            if (_runningAiTasks[str_key].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
            }
        }

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks[str_key]) return;
            const st = await api.getTaskStatus(task_id);
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);
            $progressLabel.textContent = `${markerLabel} Detection`;

            if (st.status === 'completed') {
                const result = await api.getTaskResult(task_id, _makeResultDownloadProgress());
                onPreciseIhcComplete(result, roiPolygons, marker);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus(`${markerLabel} cancelled. Partial results were cleared.`);
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`${markerLabel} failed: ${err.message}`);
    } finally {
        delete _runningAiTasks[str_key];
        _setButtonRunning(btnEl, false);
        if ($progressLabel.textContent === `${markerLabel} Detection...`) {
            $progressLabel.textContent = 'AI Progress';
        }
    }
}

function onPreciseIhcComplete(result, roiPolygons = null, marker = 'HER2') {
    const markerLabel = marker === 'ER_PR' ? 'ER/PR' : (marker === 'KI_67' ? 'KI-67' : marker);
    $progressLabel.textContent = `${markerLabel} Complete`;

    viewer.clearAnnotations();
    renderAnnotationPanel();

    _lastDetectionResult = result;
    _lastDetectionTissue = marker;
    _lastDetectionModel = 'Quanti IHC';
    _lastDetectionRoi = roiPolygons;
    lastSegData = null;

    const colorMap = {};
    if (result.class_colors) {
        for (const [k, v] of Object.entries(result.class_colors)) {
            colorMap[parseInt(k)] = v;
        }
    }
    viewer.classColorOverride = Object.keys(colorMap).length > 0 ? colorMap : null;
    viewer.defaultConfidence = (marker === 'ER_PR' || marker === 'KI_67') ? 0.3 : 0.5;

    viewer.setDetectionResults(result.cells, roiPolygons);
    viewer.setHiddenDetectionResults?.(result.excluded_cells || [], roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    if ($ihcScoreResult) {
        $ihcScoreResult.hidden = false;
        if (result.her2_score) {
            $ihcScoreLabel.textContent = 'HER2';
        } else if (result.allred_score) {
            $ihcScoreLabel.textContent = `${markerLabel} (Allred)`;
        } else if (result.ki67_score) {
            $ihcScoreLabel.textContent = 'KI-67';
        }
    }

    const { counts: dict_counts_ihc } = _computeFilteredCounts(viewer.detectionCells);
    const n0 = dict_counts_ihc[0] || 0, n1 = dict_counts_ihc[1] || 0;
    const n2 = dict_counts_ihc[2] || 0, n3 = dict_counts_ihc[3] || 0;
    if (result.her2_score) {
        const tot = n0 + n1 + n2 + n3;
        const weighted = tot === 0 ? 0 : (n1 + 2 * n2 + 3 * n3) / tot;
        const dominant = tot === 0 ? 0 : [n0, n1, n2, n3].indexOf(Math.max(n0, n1, n2, n3));
        setStatus(`HER2: ${dominant}+ (${weighted.toFixed(2)}) | ${displayCount.toLocaleString()} cells`);
    } else if (result.allred_score) {
        const pos = n1 + n2 + n3;
        const tot = n0 + pos;
        const pos_pct = tot === 0 ? 0 : pos / tot * 100;
        let int_ps = 0;
        if (pos === 0) int_ps = 0;
        else if (pos_pct < 1) int_ps = 1;
        else if (pos_pct < 10) int_ps = 2;
        else if (pos_pct < 33) int_ps = 3;
        else if (pos_pct < 66) int_ps = 4;
        else int_ps = 5;
        const avg = pos === 0 ? 0 : (n1 + 2 * n2 + 3 * n3) / pos;
        const int_is = avg < 0.5 ? 0 : avg < 1.5 ? 1 : avg < 2.5 ? 2 : 3;
        const ts = int_ps + int_is;
        const interp = ts >= 3 ? 'Positive' : 'Negative';
        setStatus(`${markerLabel} Allred: ${ts} (PS ${int_ps} + IS ${int_is}) - ${interp} | ${displayCount.toLocaleString()} cells`);
    } else if (result.ki67_score) {
        const pos = n1 + n2 + n3;
        const tot = n0 + pos;
        const ki67Index = tot === 0 ? 0 : pos / tot * 100;
        const interp = ki67Index >= 14 ? 'High' : 'Low';
        setStatus(`KI-67 Index: ${ki67Index.toFixed(1)}% - ${interp} | ${displayCount.toLocaleString()} cells`);
    }

    _lastDetectionResult.cells = viewer.detectionCells;
    _lastDetectionResult.total_cells = viewer.detectionCells.length;

    buildResultList(_lastDetectionResult);
    _updateResultCounts();
    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
}

function _setVsToggleState(visible, disabled) {
    if (!$btnVsToggle) return;
    $btnVsToggle.disabled = !!disabled;
    $btnVsToggle.setAttribute('aria-pressed', visible ? 'true' : 'false');
    const lab = $btnVsToggle.querySelector('.toggle-pill-label');
    if (lab) lab.textContent = visible ? 'Virtual Stain Overlay: ON' : 'Virtual Stain Overlay: OFF';
}
function _setVsSplitState(enabled, disabled) {
    if (!$btnVsSplit) return;
    $btnVsSplit.disabled = !!disabled;
    $btnVsSplit.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    const lab = $btnVsSplit.querySelector('.toggle-pill-label');
    if (lab) lab.textContent = enabled
        ? 'Split View: ON  (IHC | Virtual H&E)'
        : 'Split View (IHC | Virtual H&E)';
}

$btnVsToggle?.addEventListener('click', () => {
    if (_blockViewerAction()) return;
    if ($btnVsToggle.disabled) return;
    const next = $btnVsToggle.getAttribute('aria-pressed') !== 'true';
    _setVsToggleState(next, false);
    viewer.setVirtualStainVisible(next);
    // Disable split view when the overlay is turned off.
    if (!next) {
        _setVsSplitState(false, false);
        viewer.setVirtualStainSplitMode(false);
    }
});

$btnVsSplit?.addEventListener('click', () => {
    if (_blockViewerAction()) return;
    if ($btnVsSplit.disabled) return;
    const next = $btnVsSplit.getAttribute('aria-pressed') !== 'true';
    _setVsSplitState(next, false);
    if (next) {
        _setVsToggleState(true, false);
        viewer.setVirtualStainVisible(true);
    }
    viewer.setVirtualStainSplitMode(next);
});

// On page load, verify auth and load projects/slides.
(async () => {
    try {
        const dict_me = await api.me();
        if ($userName && dict_me.str_name) {
            $userName.textContent = dict_me.str_name;
        }
        if ($projectUserName) {
            $projectUserName.textContent = dict_me.str_name || dict_me.str_username || '';
        }
        if ($projectUserRole) {
            $projectUserRole.textContent = _roleLabel(dict_me.str_role);
        }
        const normalizedRole = _normalizeUserRole(dict_me.str_role);
        if (normalizedRole === 'admin') {
            const $linkAdmin = document.getElementById('link-admin');
            if ($linkAdmin) {
                $linkAdmin.textContent = 'Admin';
                $linkAdmin.title = 'Admin';
                $linkAdmin.hidden = false;
            }
            if ($projectLinkAdmin) $projectLinkAdmin.hidden = false;
        }
        window.MediautoHeader?.render({
            active: 'viewer',
            user: { ...dict_me, str_role: normalizedRole },
            showAdmin: normalizedRole === 'admin',
            logout: () => {
                _stopAiActivePolling();
                api.logout();
            },
        });
        window.__currentUserRole = normalizedRole;
        window.__currentUserId = String(dict_me._id || '');
        if (window.__currentUserRole === 'viewer') {
            _applyViewerRoleRestrictions();
        }
        if (window.__currentUserRole === 'labeler') {
            _applyLabelerRoleRestrictions();
        }
    } catch (_) {
        return;
    }
    const _urlParams = new URLSearchParams(location.search);
    const _paramSlide = _urlParams.get('slide');
    const _paramPath = _urlParams.get('path');
    if (_paramPath !== null) currentBrowsePath = _paramPath;
    const bool_show_project_gate = !_paramSlide && _paramPath === null;

    const list_projects = await loadProjectList();
    if (bool_show_project_gate) {
        _showProjectGate(list_projects);
        return;
    }

    await loadSlideList();

    if (_paramSlide) {
        openSavedSlide(_paramSlide, null);
        history.replaceState(null, '', '/ai');
    }
})();
