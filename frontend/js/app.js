import { MultiViewFocus } from './multi-view-focus.js?v=20260914-focus-dblclick-02';
import { bindFixedAreaTools } from './annotation-area.js?v=20260914-area-toggle-01';
/**
 * Main AI viewer module for MeDIAuto Studio.
 * Handles project selection, slide browsing, annotation tools, and AI analysis workflows.
 */

import { api } from './api.js?v=20260914-01';
import { AiViewer } from './ai-viewer.js?v=20260914-02';
import { showVisualization } from './visualization.js?v=20260824-07';
import { $, esc as _esc, normalizeUserRole as _normalizeUserRole, roleLabel as _roleLabel } from './common-utils.js?v=20260604-01';

if (!localStorage.getItem('access_token')) {
    window.location.replace('/login');
    throw new Error('Not authenticated - redirecting to /login');
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
const $btnSameCase = $('#btn-same-case');
const $sameCaseDialog = $('#same-case-dialog');
const $sameCaseDialogCase = $('#same-case-dialog-case');
const $sameCaseStatus = $('#same-case-status');
const $sameCaseGrid = $('#same-case-grid');
const $sameCaseSelection = $('#same-case-selection');
const $btnViewSameCase = $('#view-same-case');
const $btnMultiViewSameCase = $('#multi-view-same-case');
const $sameCaseOpenChoice = $('#same-case-open-choice');
const $sameCaseChoiceSlide = $('#same-case-choice-slide');
const $sameCaseChoiceSummary = $('#same-case-choice-summary');
const $btnChoiceViewSlide = $('#choice-view-slide');
const $btnChoiceMultiView = $('#choice-multi-view');
const $multiViewContainer = $('#multi-view-container');
const $multiViewGrid = $('#multi-view-grid');
const $multiViewTitle = $('#multi-view-title');
const $slideNameSearch = $('#slide-name-search');
const $showSlideLabels = $('#show-slide-labels');
const SLIDE_LABEL_VISIBILITY_KEY = 'showSlideLabels';
let _showSlideLabels = localStorage.getItem(SLIDE_LABEL_VISIBILITY_KEY) !== '0';
const _slideLabelAvailability = new Map();
let _slideLabelObserver = null;
if ($showSlideLabels) $showSlideLabels.checked = _showSlideLabels;
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
let _sameCaseSlides = [];
let _selectedSameCaseSlideIds = [];
let _sameCaseRequestSeq = 0;
let _sameCaseChoiceSlideId = '';
let _multiViewPanes = [];
let _multiViewOpenSeq = 0;
let _activeMultiViewPane = null;
let _multiViewOriginalContext = null;
const _multiViewFocus = new MultiViewFocus({
    container: $multiViewContainer,
    grid: $multiViewGrid,
    button: $('#focus-multi-view'),
    getPanes: () => _multiViewPanes,
    getActivePane: () => _activeMultiViewPane,
});

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
const $hneStilResult = $('#hne-stil-result');
const $hneStilValue = $('#hne-stil-value');
const $hneStilMetrics = $('#hne-stil-metrics');
const $btnVisualize = $('#btn-visualize');
const $btnHeatmapToggle = $('#btn-heatmap-toggle');
const $btnStilHeatmapToggle = $('#btn-stil-heatmap-toggle');
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
const $btnDrawBrush = $('#btn-draw-brush');
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
let _lastBrowseData = { path: '', folders: [], slides: [] };
let _slideListRequestSeq = 0;
const _latestReadControllers = new Map();

function _beginLatestRead(str_key) {
    _latestReadControllers.get(str_key)?.abort();
    const controller = new AbortController();
    _latestReadControllers.set(str_key, controller);
    return controller;
}

function _finishLatestRead(str_key, controller) {
    if (_latestReadControllers.get(str_key) === controller) {
        _latestReadControllers.delete(str_key);
    }
}

function _abortLatestRead(str_key) {
    const controller = _latestReadControllers.get(str_key);
    if (!controller) return;
    controller.abort();
    _latestReadControllers.delete(str_key);
}

function _isAbortError(err) {
    return err?.name === 'AbortError' || String(err?.message || '').toLowerCase().includes('aborted');
}

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

let viewer = new AiViewer($canvas, $overlay);
const _primaryViewer = viewer;

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

// AI Analysis topic/model switching.
const $quantiModelBar = document.querySelector('.quanti-model-bar');

function _setActiveAiContent(str_tab_id) {
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const el_content = document.getElementById(str_tab_id);
    if (el_content) el_content.classList.add('active');
}

function _setActiveQuantiTab(str_tab_id) {
    document.querySelectorAll('.quanti-model-bar .tab-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === str_tab_id);
    });
    _setActiveAiContent(str_tab_id);
}

function _setActiveAiTopic(str_topic, str_tab_id = '') {
    document.querySelectorAll('.ai-topic-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.aiTopic === str_topic);
    });
    if ($quantiModelBar) $quantiModelBar.hidden = str_topic !== 'quanti';

    if (str_topic === 'quanti') {
        const str_next_tab = str_tab_id || document.querySelector('.quanti-model-bar .tab-btn.active')?.dataset.tab || 'hne-tab';
        _setActiveQuantiTab(str_next_tab);
        return;
    }

    const str_next_tab = str_tab_id || document.querySelector(`.ai-topic-btn[data-ai-topic="${str_topic}"]`)?.dataset.tab || 'vs-tab';
    _setActiveAiContent(str_next_tab);
}

document.querySelectorAll('.ai-topic-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.disabled) return;
        _setActiveAiTopic(btn.dataset.aiTopic || 'virtualstain', btn.dataset.tab || '');
    });
});

document.querySelectorAll('.quanti-model-bar .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.disabled) return;
        _setActiveAiTopic('quanti', btn.dataset.tab);
    });
});

const AI_MODEL_HELP = {
    'hne-tab': {
        title: 'Quanti HE - H&E Cell Detection',
        body: 'Detects and classifies cells on H&E slides. Breast analysis also reports a calibration-required AI-estimated stromal TIL score using lymphocyte/plasma-cell area over tumor-associated stroma, with a 500 µm local sTIL heatmap. It is a research metric, not a clinical ground-truth score.',
    },
    'vs-tab': {
        title: 'VirtualStain - VS IHC',
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
    'dx-tab': {
        title: 'Dx',
        body: 'Diagnostic AI models can be added here.',
    },
    'px-tab': {
        title: 'Px',
        body: 'Prognostic or predictive AI models can be added here.',
    },
};const $aiHelpIcon = document.querySelector('#ai-help-icon');
let _aiHelpTooltip = null;
function _showAiHelpTooltip() {
    if (!$aiHelpIcon) return;
    const activeContent = document.querySelector('.ai-analysis-group .tab-content.active');
    const key = activeContent ? activeContent.id : 'vs-tab';
    const info = AI_MODEL_HELP[key] || AI_MODEL_HELP['vs-tab'];
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

const SLIDE_EXT_PATTERN = /\.(isyntax|i2syntax|svs|ndpi|tif|tiff|mrxs|vms|vmu|scn)$/i;

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
    for (const str_key of ['clinical-info', 'same-case', 'user-edit-list', 'user-edit-load', 'folder-config']) {
        _abortLatestRead(str_key);
    }
    _exitMultiView(false);
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
    if ($btnSameCase) $btnSameCase.disabled = false;
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

function _restoreManualAiControls() {
    $btnDetect.disabled = false;
    $btnVsMembrane.disabled = false;
    if ($btnPdScore) $btnPdScore.disabled = false;
    if ($btnIhcHer2) $btnIhcHer2.disabled = false;
    if ($btnIhcErPr) $btnIhcErPr.disabled = false;
    if ($btnIhcKi67) $btnIhcKi67.disabled = false;
    document.querySelectorAll('input[name="tissue-type"], input[name="pd-tissue-type"]').forEach(el => {
        el.disabled = false;
    });
    document.querySelectorAll('.ai-topic-btn, .tab-btn[data-tab], .tab-content').forEach(el => {
        el.style.display = '';
    });
    if ($quantiModelBar && !document.querySelector('.ai-topic-btn.active[data-ai-topic="quanti"]')) {
        $quantiModelBar.hidden = true;
    }
    if (!document.querySelector('.ai-topic-btn.active')) {
        _setActiveAiTopic('virtualstain', 'vs-tab');
    } else if (!document.querySelector('.ai-analysis-group .tab-content.active')) {
        const activeTopic = document.querySelector('.ai-topic-btn.active');
        _setActiveAiTopic(activeTopic.dataset.aiTopic || 'virtualstain', activeTopic.dataset.tab || '');
    }
}

async function _applyFolderAiRestrictions(strFolderPath) {
    if (_isViewerRole()) return;
    void strFolderPath;
    _restoreManualAiControls();
}

function _applyViewerRoleRestrictions() {
    document.body.classList.add('role-viewer');
    _stopAiActivePolling();
    if (viewer) viewer.canEditDetectionResults = false;

    const list_draw_btns = ['btn-draw-polygon', 'btn-draw-brush', 'btn-draw-rect',
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
        'btn-visualize', 'btn-heatmap-toggle', 'btn-stil-heatmap-toggle',
        'btn-clear-results', 'btn-save-results', 'btn-load-results',
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
        if (_minimapRequestImage) {
            _minimapRequestImage.onload = null;
            _minimapRequestImage.onerror = null;
            try { _minimapRequestImage.src = ''; } catch (_) {}
        }
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
    brush: $btnDrawBrush,
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
if ($btnDrawBrush) $btnDrawBrush.addEventListener('click', () => setDrawMode('brush'));
$btnDrawRect.addEventListener('click', () => setDrawMode('rectangle'));
bindFixedAreaTools(() => viewer, $btnDrawRect1mm2, $btnDrawCircle1mm2, setDrawMode);
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
    const listAnnotations = viewer.annotations.length
        ? viewer.annotations
        : (_lastDetectionRoi || []).map((coordinates, index) => ({
            id: `ai-region-${index + 1}`,
            name: `AI Region ${index + 1}`,
            type: 'polygon',
            coordinates,
            color: [47, 128, 237],
            visible: true,
            _aiRegion: true,
        }));
    if (!listAnnotations.length) {
        const empty = document.createElement('div');
        empty.className = 'region-empty-state';
        empty.textContent = 'No regions. Draw a polygon or rectangle before running Quanti.';
        $annList.appendChild(empty);
        return;
    }
    for (const ann of listAnnotations) {
        const [r, g, b] = _normalizeColor(ann.color);
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
        const areaLabel = viewer.getAnnotationAreaLabel(ann);
        if (areaLabel) {
            const area = document.createElement('span');
            area.className = 'ann-area';
            area.textContent = areaLabel;
            el.append(area);
        }
        if (ann._aiRegion) {
            el.classList.add('region-ai-item');
            el.style.gridTemplateColumns = '34px minmax(82px, 1fr) 42px 42px 34px';
            el.querySelector('.ann-color-swatch').disabled = true;
            el.querySelector('.ann-btn-vis').disabled = true;
            el.querySelector('.ann-btn-del').disabled = true;
        }
        el.addEventListener('click', (e) => {
            if (e.target.closest('.ann-color-swatch') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') || e.target.closest('.ann-name-input')) return;
            if (ann._aiRegion) viewer.centerOnAnnotation(ann);
            else viewer.selectAnnotation(ann.id);
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
        if (ann.coordinates?.length >= 3 && ann.type !== 'point') {
            el.appendChild(_buildRegionQuantiSummary(ann.coordinates));
        }
    }
}

function _regionPointInPolygon(x, y, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const xi = Number(polygon[i]?.[0]);
        const yi = Number(polygon[i]?.[1]);
        const xj = Number(polygon[j]?.[0]);
        const yj = Number(polygon[j]?.[1]);
        if (!Number.isFinite(xi) || !Number.isFinite(yi) || !Number.isFinite(xj) || !Number.isFinite(yj)) continue;
        const intersect = ((yi > y) !== (yj > y)) &&
            (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

function _getRegionQuantiCounts(polygon) {
    const counts = {};
    let total = 0;
    for (const cell of viewer.detectionCells || []) {
        if (!_regionPointInPolygon(Number(cell.x), Number(cell.y), polygon)) continue;
        const threshold = viewer.classConfidence?.[cell.class_id] ?? 0.01;
        if ((cell.confidence ?? 1) < threshold) continue;
        const id = Number(cell.class_id);
        counts[id] = (counts[id] || 0) + 1;
        total += 1;
    }
    return { counts, total };
}

function _getRegionScoreText(counts) {
    if (!_lastDetectionResult) return '';
    const result = _lastDetectionResult;
    if (_lastDetectionModel === 'Quanti PD-L1' && result.pd_score) {
        const type = result.pd_score.score_type || 'Score';
        if (type === 'CPS') {
            const positiveTumor = counts[3] || 0;
            const positiveImmune = (counts[4] || 0) + (counts[5] || 0);
            const negativeTumor = counts[0] || 0;
            const viableTumor = positiveTumor + negativeTumor;
            const score = viableTumor ? Math.min(100, (positiveTumor + positiveImmune) / viableTumor * 100) : 0;
            return `CPS ${score.toFixed(1)}%`;
        }
        if (type === 'TPS') {
            const positive = counts[1] || 0;
            const negative = counts[0] || 0;
            const total = positive + negative;
            return `TPS ${(total ? positive / total * 100 : 0).toFixed(1)}%`;
        }
    }
    if (_lastDetectionModel === 'Quanti IHC') {
        if (result.her2_score) {
            const values = [counts[0] || 0, counts[1] || 0, counts[2] || 0, counts[3] || 0];
            const total = values.reduce((sum, value) => sum + value, 0);
            const weighted = total ? values.reduce((sum, value, index) => sum + index * value, 0) / total : 0;
            const dominant = total ? values.indexOf(Math.max(...values)) : 0;
            return `HER2 ${dominant}+ (${weighted.toFixed(2)})`;
        }
        if (result.allred_score) {
            const allred = _computeAllredFromCounts(counts);
            return `Allred ${allred.ts}/8 (${allred.interpretation})`;
        }
        if (result.ki67_score) {
            const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
            const positive = (counts[1] || 0) + (counts[2] || 0) + (counts[3] || 0);
            return `KI-67 ${total ? (positive / total * 100).toFixed(1) : '0.0'}%`;
        }
    }
    return '';
}

function _buildRegionQuantiSummary(polygon) {
    const summary = document.createElement('div');
    summary.className = 'region-quanti-summary';
    if (!_lastDetectionResult) {
        summary.textContent = 'Quanti result will be shown after AI analysis.';
        return summary;
    }
    const { counts, total } = _getRegionQuantiCounts(polygon);
    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};
    const breakdown = Object.entries(counts)
        .sort(([, a], [, b]) => b - a)
        .map(([id, count]) => ({
            name: classNames[id] || `Class ${id}`,
            count,
            color: _toCssColor(classColors[id] ?? CLASS_COLORS[Number(id)]),
        }));
    const score = _getRegionScoreText(counts);
    const header = document.createElement('div');
    header.className = 'region-quanti-summary-header';
    const modelEl = document.createElement('span');
    modelEl.className = 'region-quanti-summary-model';
    modelEl.textContent = _lastDetectionModel || 'Quanti';
    const totalEl = document.createElement('span');
    totalEl.className = 'region-quanti-summary-total';
    totalEl.innerHTML = `<strong>${total.toLocaleString()}</strong><span>cells</span>`;
    header.append(modelEl, totalEl);
    if (score) {
        const scoreEl = document.createElement('strong');
        scoreEl.className = 'region-quanti-summary-score';
        scoreEl.textContent = score;
        header.appendChild(scoreEl);
    }
    const detail = document.createElement('div');
    detail.className = 'region-quanti-summary-detail';
    if (!breakdown.length) {
        detail.textContent = 'No cells in this region';
    } else {
        for (const item of breakdown) {
            const chip = document.createElement('span');
            chip.className = 'region-quanti-class-chip';
            chip.title = `${item.name}: ${item.count.toLocaleString()}`;
            const dotEl = document.createElement('span');
            dotEl.className = 'region-quanti-class-dot';
            dotEl.style.backgroundColor = item.color;
            const nameEl = document.createElement('span');
            nameEl.textContent = item.name;
            const countEl = document.createElement('strong');
            countEl.textContent = item.count.toLocaleString();
            chip.append(dotEl, nameEl, countEl);
            detail.appendChild(chip);
        }
    }
    summary.append(header, detail);
    return summary;
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
    // Explicitly clearing Regions also removes the synthetic ROI summary
    // retained after an AI run; the detection result itself remains available.
    _lastDetectionRoi = null;
    renderAnnotationPanel();
    setStatus('Regions cleared');
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
    try {
        if (!await window.MediautoSecurity.authorizeExport(suggestedName)) return;
    } catch (err) {
        setStatus(err.message);
        return;
    }

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
    const str_slide_id = currentSlideId;
    const controller = _beginLatestRead('clinical-info');
    try {
        const res = await api.getSlideClinicalInfo(str_slide_id, { signal: controller.signal });
        if (controller.signal.aborted || currentSlideId !== str_slide_id) {
            return currentSlideInfo?.dict_clinical_info || {};
        }
        const clinicalInfo = res.dict_clinical_info || {};
        currentSlideInfo = { ...(currentSlideInfo || {}), case_name: res.case_name || currentSlideInfo?.case_name || '', dict_clinical_info: clinicalInfo };
        return clinicalInfo;
    } catch (err) {
        if (_isAbortError(err)) return currentSlideInfo?.dict_clinical_info || {};
        console.warn('[slide-info] clinical info load failed:', err);
        return currentSlideInfo?.dict_clinical_info || {};
    } finally {
        _finishLatestRead('clinical-info', controller);
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

function _currentBrowseSlide() {
    return (_lastBrowseData.slides || []).find((slide) => (
        slide.slide_id === currentSlideId ||
        String(slide.filename || '') === String(currentSlideInfo?.filename || '')
    ));
}

function _caseNameFromFilename(filename = '') {
    const leaf = String(filename || '').split(/[\\/]/).pop() || '';
    const stem = leaf.replace(/\.[^.]+$/, '');
    const parts = stem.split('-').filter(Boolean);
    if (parts.length >= 4 && parts[0].toUpperCase() === 'CODIPAI') return parts.slice(1, 4).join('-');
    if (parts.length >= 3) return parts.slice(0, 3).join('-');
    return stem;
}

async function _resolveCurrentCaseName(signal = null) {
    const browseSlide = _currentBrowseSlide();
    const knownCaseName = String(currentSlideInfo?.case_name || browseSlide?.case_name || '').trim();
    if (knownCaseName) return knownCaseName;
    const filenameCaseName = _caseNameFromFilename(currentSlideInfo?.filename || browseSlide?.filename);
    if (filenameCaseName) return filenameCaseName;
    if (!currentSlideId) return '';
    const result = await api.getSlideClinicalInfo(currentSlideId, { signal });
    const caseName = String(result?.case_name || '').trim();
    if (caseName) currentSlideInfo = { ...(currentSlideInfo || {}), case_name: caseName };
    return caseName;
}

function _setSameCaseStatus(message = '') {
    if (!$sameCaseStatus) return;
    $sameCaseStatus.textContent = message;
    $sameCaseStatus.hidden = !message;
}

function _selectedSameCaseSlides() {
    return _selectedSameCaseSlideIds
        .map((slideId) => _sameCaseSlides.find((slide) => slide.slide_id === slideId))
        .filter(Boolean);
}

function _refreshSameCaseSelection(message = '') {
    $sameCaseGrid?.querySelectorAll('.same-case-card').forEach((card) => {
        const selectionIndex = _selectedSameCaseSlideIds.indexOf(card.dataset.slideId);
        const selected = selectionIndex >= 0;
        card.classList.toggle('selected', selected);
        card.setAttribute('aria-selected', selected ? 'true' : 'false');
        const orderBadge = card.querySelector('.same-case-select-order');
        if (orderBadge) {
            orderBadge.hidden = !selected;
            orderBadge.textContent = selected ? String(selectionIndex + 1) : '';
        }
    });
    const selectedSlides = _selectedSameCaseSlides();
    if ($sameCaseSelection) {
        $sameCaseSelection.textContent = message || (
            selectedSlides.length === 1
                ? selectedSlides[0].filename
                : selectedSlides.length > 1
                    ? `${selectedSlides.length} slides selected for Multi View`
                    : `${_sameCaseSlides.length.toLocaleString()} slide${_sameCaseSlides.length === 1 ? '' : 's'} in this case`
        );
    }
    if ($btnViewSameCase) $btnViewSameCase.disabled = selectedSlides.length !== 1;
    if ($btnMultiViewSameCase) {
        $btnMultiViewSameCase.disabled = selectedSlides.length < 2 || selectedSlides.length > 4;
    }
}

function _clearSameCaseSelection() {
    _selectedSameCaseSlideIds = [];
    _refreshSameCaseSelection();
}

function _selectCurrentSameCaseSlide() {
    const currentSlide = _sameCaseSlides.find((slide) => slide.slide_id === currentSlideId);
    _selectedSameCaseSlideIds = currentSlide ? [currentSlide.slide_id] : [];
    _refreshSameCaseSelection();
}

function _toggleSameCaseSlide(slideId = '') {
    const normalizedId = String(slideId || '');
    if (!normalizedId) return;
    const selectionIndex = _selectedSameCaseSlideIds.indexOf(normalizedId);
    if (selectionIndex >= 0) {
        _selectedSameCaseSlideIds.splice(selectionIndex, 1);
    } else if (_selectedSameCaseSlideIds.length >= 4) {
        _refreshSameCaseSelection('Multi View supports up to 4 slides.');
        return;
    } else {
        _selectedSameCaseSlideIds.push(normalizedId);
    }
    _refreshSameCaseSelection();
}

function _ensureSameCaseSlideSelected(slideId = '') {
    const normalizedId = String(slideId || '');
    if (!normalizedId || _selectedSameCaseSlideIds.includes(normalizedId)) return;
    if (_selectedSameCaseSlideIds.length >= 4) _selectedSameCaseSlideIds.pop();
    _selectedSameCaseSlideIds.push(normalizedId);
    _refreshSameCaseSelection();
}

function _sameCaseMultiViewSlides(focusSlideId = '') {
    const selectedSlides = _selectedSameCaseSlides();
    if (selectedSlides.length >= 2) return selectedSlides.slice(0, 4);
    const focusSlide = _sameCaseSlides.find((slide) => slide.slide_id === focusSlideId) || selectedSlides[0];
    const currentSlide = _sameCaseSlides.find((slide) => slide.slide_id === currentSlideId);
    const pair = [];
    for (const slide of [currentSlide, focusSlide]) {
        if (slide && !pair.some((item) => item.slide_id === slide.slide_id)) pair.push(slide);
    }
    return pair;
}

function _sameCaseProjectLabel(path = '') {
    const parts = String(path || '').replace(/^\/+|\/+$/g, '').split('/').filter(Boolean);
    if (!parts.length) return '';
    const projectPath = parts[0];
    const project = _projectListCache.find((item) => (item.path || item.name) === projectPath);
    const projectLabel = project ? _projectLabel(project) : projectPath;
    return [projectLabel, ...parts.slice(1)].join(' / ');
}

function _renderSameCaseSlides(caseName, slides = []) {
    if (!$sameCaseGrid) return;
    $sameCaseGrid.replaceChildren();
    _sameCaseSlides = [...slides].sort((a, b) => {
        const aCurrent = a.slide_id === currentSlideId ? 0 : 1;
        const bCurrent = b.slide_id === currentSlideId ? 0 : 1;
        return aCurrent - bCurrent || String(a.filename || '').localeCompare(String(b.filename || ''));
    });
    _selectedSameCaseSlideIds = [];
    if ($sameCaseDialogCase) $sameCaseDialogCase.textContent = caseName ? `Case: ${caseName}` : '';

    for (const slide of _sameCaseSlides) {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'same-case-card';
        card.dataset.slideId = slide.slide_id || '';
        card.setAttribute('role', 'option');
        card.setAttribute('aria-selected', 'false');
        card.title = `${slide.filename}\nDouble-click to open`;

        const thumbWrap = document.createElement('div');
        thumbWrap.className = 'same-case-thumb-wrap';
        const placeholder = document.createElement('span');
        placeholder.className = 'same-case-thumb-placeholder';
        placeholder.textContent = 'Loading preview...';
        const thumb = document.createElement('img');
        thumb.className = 'same-case-thumb';
        thumb.alt = `${slide.filename} thumbnail`;
        thumb.loading = 'lazy';
        const thumbnailUrl = () => api.thumbnailUrlByName(slide.filename, slide.path || '', 420);
        thumb.addEventListener('load', () => placeholder.remove(), { once: true });
        api.attachMediaImageRetry(thumb, thumbnailUrl, () => {
            thumb.style.display = 'none';
            placeholder.textContent = 'Preview unavailable';
        });
        thumb.src = thumbnailUrl();
        thumbWrap.append(placeholder, thumb);

        if (slide.slide_id === currentSlideId) {
            const currentBadge = document.createElement('span');
            currentBadge.className = 'same-case-current-badge';
            currentBadge.textContent = 'CURRENT';
            thumbWrap.appendChild(currentBadge);
        }
        if (slide.has_ai_result) {
            const aiBadge = document.createElement('span');
            aiBadge.className = 'same-case-ai-badge';
            aiBadge.textContent = 'AI RESULT';
            thumbWrap.appendChild(aiBadge);
        }
        const selectionOrder = document.createElement('span');
        selectionOrder.className = 'same-case-select-order';
        selectionOrder.hidden = true;
        thumbWrap.appendChild(selectionOrder);

        const info = document.createElement('span');
        info.className = 'same-case-card-info';
        const name = document.createElement('span');
        name.className = 'same-case-card-name';
        name.textContent = slide.filename || '-';
        const meta = document.createElement('span');
        meta.className = 'same-case-card-meta';
        const size = Number(slide.size_mb);
        meta.textContent = [
            _sameCaseProjectLabel(slide.path || _getCurrentProjectName()),
            Number.isFinite(size) ? `${size.toLocaleString()} MB` : '',
        ].filter(Boolean).join(' · ');
        info.append(name, meta);
        card.append(thumbWrap, info);
        card.addEventListener('click', () => _toggleSameCaseSlide(slide.slide_id));
        card.addEventListener('dblclick', (event) => {
            event.preventDefault();
            _ensureSameCaseSlideSelected(slide.slide_id);
            _showSameCaseOpenChoice(slide.slide_id);
        });
        $sameCaseGrid.appendChild(card);
    }
    // The slide already open in the viewer is the first comparison selection.
    // One click on another card therefore creates a two-slide Multi View.
    _selectCurrentSameCaseSlide();
}

async function _loadSameCaseSlides() {
    if (!currentSlideId || !$sameCaseDialog) return;
    const requestSeq = ++_sameCaseRequestSeq;
    const controller = _beginLatestRead('same-case');
    _sameCaseSlides = [];
    _selectedSameCaseSlideIds = [];
    $sameCaseGrid?.replaceChildren();
    if ($sameCaseDialogCase) $sameCaseDialogCase.textContent = '';
    if ($sameCaseSelection) $sameCaseSelection.textContent = 'Select a slide to view.';
    if ($btnViewSameCase) $btnViewSameCase.disabled = true;
    if ($btnMultiViewSameCase) $btnMultiViewSameCase.disabled = true;
    _setSameCaseStatus('Loading slides from the same case...');
    if (!$sameCaseDialog.open) $sameCaseDialog.showModal();

    try {
        const caseName = await _resolveCurrentCaseName(controller.signal);
        if (!caseName) throw new Error('Case ID is unavailable for the current slide.');
        if (requestSeq !== _sameCaseRequestSeq || !$sameCaseDialog.open) return;
        if ($sameCaseDialogCase) $sameCaseDialogCase.textContent = `Case: ${caseName}`;
        // A case can span marker/project folders (for example HER2, KI-67, and H&E),
        // so search the upload tree instead of limiting the request to the current folder.
        const result = await api.listCases(
            { sampleNo: caseName, page: 1, pageSize: 100 },
            { signal: controller.signal },
        );
        if (requestSeq !== _sameCaseRequestSeq || !$sameCaseDialog.open) return;
        const normalizedCaseName = caseName.toLocaleLowerCase();
        const matchedCase = (result.cases || []).find((item) => (
            String(item.case_name || '').toLocaleLowerCase() === normalizedCaseName
        ));
        const slides = Array.isArray(matchedCase?.slides) ? matchedCase.slides : [];
        if (!slides.length) throw new Error(`No slides were found for case ${caseName}.`);
        _setSameCaseStatus('');
        _renderSameCaseSlides(caseName, slides);
    } catch (err) {
        if (_isAbortError(err)) return;
        if (requestSeq !== _sameCaseRequestSeq || !$sameCaseDialog.open) return;
        _sameCaseSlides = [];
        _setSameCaseStatus(err?.message || 'Failed to load same-case slides.');
        if ($sameCaseSelection) $sameCaseSelection.textContent = 'No slide selected.';
        if ($btnViewSameCase) $btnViewSameCase.disabled = true;
        if ($btnMultiViewSameCase) $btnMultiViewSameCase.disabled = true;
    } finally {
        _finishLatestRead('same-case', controller);
    }
}

function _closeSameCaseDialog() {
    _sameCaseRequestSeq += 1;
    _abortLatestRead('same-case');
    $sameCaseGrid?.querySelectorAll('img').forEach((img) => api.cancelMediaImage?.(img));
    if ($sameCaseOpenChoice?.open) $sameCaseOpenChoice.close();
    if ($sameCaseDialog?.open) $sameCaseDialog.close();
}

function _captureAnalysisContext() {
    return {
        lastDetectionResult: _lastDetectionResult,
        lastDetectionTissue: _lastDetectionTissue,
        lastDetectionModel: _lastDetectionModel,
        lastDetectionRoi: _lastDetectionRoi,
        segData: lastSegData,
    };
}

function _emptyAnalysisContext() {
    return {
        lastDetectionResult: null,
        lastDetectionTissue: null,
        lastDetectionModel: null,
        lastDetectionRoi: null,
        segData: null,
    };
}

function _restoreAnalysisContext(context = null) {
    const state = context || _emptyAnalysisContext();
    _lastDetectionResult = state.lastDetectionResult || null;
    _lastDetectionTissue = state.lastDetectionTissue || null;
    _lastDetectionModel = state.lastDetectionModel || null;
    _lastDetectionRoi = state.lastDetectionRoi || null;
    lastSegData = state.segData || null;
}

function _captureActiveMultiViewContext() {
    if (!_activeMultiViewPane || viewer !== _activeMultiViewPane.viewer) return;
    _activeMultiViewPane.analysis = _captureAnalysisContext();
}

function _renderActiveViewerPanels() {
    const hasResult = Boolean(_lastDetectionResult);
    $resultList.innerHTML = '';
    _updateStilScoreDisplay(_lastDetectionResult?.stil_score || null);
    if ($pdScoreResult) $pdScoreResult.hidden = !_lastDetectionResult?.pd_score;
    if ($ihcScoreResult) {
        $ihcScoreResult.hidden = !(
            _lastDetectionResult?.her2_score ||
            _lastDetectionResult?.allred_score ||
            _lastDetectionResult?.ki67_score
        );
    }

    if (hasResult) {
        buildResultList(_lastDetectionResult);
        _updateResultCounts();
    }
    $btnVisualize.disabled = !hasResult || !viewer.detectionCells?.length;
    $btnClearResults.disabled = !hasResult;
    $btnSaveResults.disabled = !hasResult;
    if ($btnLoadResults) $btnLoadResults.disabled = !hasResult;
    _syncHeatmapToggle();
    renderAnnotationPanel();
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
}

function _enableActiveSlideControls() {
    $btnDetect.disabled = false;
    $btnVsMembrane.disabled = false;
    if ($btnPdScore) $btnPdScore.disabled = false;
    if ($btnIhcHer2) $btnIhcHer2.disabled = false;
    if ($btnIhcErPr) $btnIhcErPr.disabled = false;
    if ($btnIhcKi67) $btnIhcKi67.disabled = false;
    $btnInfo.disabled = false;
    if ($btnSameCase) $btnSameCase.disabled = false;
    document.querySelectorAll('.toggle-btn').forEach((button) => { button.disabled = false; });
    document.querySelectorAll('input[name="tissue-type"], input[name="pd-tissue-type"]').forEach((input) => {
        input.disabled = false;
    });
    if (!_isViewerRole()) _applyFolderAiRestrictions(currentBrowsePath);
    viewer.canEditDetectionResults = _canEditAiDetections();
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
}

function _bindMultiViewViewerCallbacks(paneViewer) {
    const callbackNames = [
        'onZoomChange', 'onDrawModeChange',
        'onAnnotationCreated', 'onAnnotationSelected', 'onAnnotationDeleted', 'onAnnotationChanged',
        'onCellEditRequested', 'onCellAddRequested', 'onCellsMultiEditRequested',
        'onHiddenCellsMultiEditRequested', 'onCellEdited',
    ];
    for (const name of callbackNames) {
        const primaryCallback = _primaryViewer[name];
        if (typeof primaryCallback !== 'function') continue;
        paneViewer[name] = (...args) => {
            if (viewer !== paneViewer) return undefined;
            return primaryCallback(...args);
        };
    }

    // TileViewer.deleteAnnotation does not emit onAnnotationDeleted itself;
    // mirror the main viewer's application-level wrapper for each pane.
    const deleteAnnotation = paneViewer.deleteAnnotation.bind(paneViewer);
    paneViewer.deleteAnnotation = (id) => {
        const annotation = paneViewer.annotations.find((item) => item.id === id);
        deleteAnnotation(id);
        if (annotation && paneViewer.onAnnotationDeleted) paneViewer.onAnnotationDeleted(annotation);
    };
}

function _activateMultiViewPane(pane, announce = true) {
    if (!pane || pane.element.hidden || !pane.slideInfo || pane.error.hidden === false) return;
    if (_activeMultiViewPane === pane && viewer === pane.viewer) return;

    _closeCellEditPopup();
    _captureActiveMultiViewContext();
    if (viewer?.drawMode) viewer.setDrawMode(null);

    _activeMultiViewPane = pane;
    viewer = pane.viewer;
    currentSlideId = pane.slideInfo.slide_id;
    currentSlideInfo = pane.slideInfo;
    currentBrowsePath = String(pane.slide?.path || '').replace(/^\/+|\/+$/g, '');
    _restoreAnalysisContext(pane.analysis);

    for (const item of _multiViewPanes) {
        const active = item === pane;
        item.element.classList.toggle('active', active);
        item.element.setAttribute('aria-selected', active ? 'true' : 'false');
    }

    $slideName.textContent = pane.slideInfo.filename || pane.slide?.filename || '';
    _updateScannerBadge(pane.slideInfo);
    _updateNdpColorToggleVisibility(pane.slideInfo);
    _enableActiveSlideControls();
    _renderActiveViewerPanels();
    if (typeof viewer.onZoomChange === 'function') {
        viewer.onZoomChange(viewer.zoom, viewer.getMagnification(), viewer.getEffectiveMpp());
    }
    _multiViewFocus.refresh();
    if (announce) setStatus(`Active slide: ${currentSlideInfo.filename}`);
}

function _currentAiTarget() {
    return { viewer, slideId: currentSlideId };
}

function _applyAiResultToTarget(target, applyResult) {
    if (!target?.viewer || !target.slideId || typeof applyResult !== 'function') return false;
    if (target.viewer === viewer && target.slideId === currentSlideId) {
        applyResult();
        return true;
    }

    const targetPane = _multiViewPanes.find((pane) => (
        pane.viewer === target.viewer && pane.slideInfo?.slide_id === target.slideId
    ));
    const targetsOriginalViewer = (
        target.viewer === _primaryViewer &&
        _multiViewOriginalContext?.slideId === target.slideId
    );
    if (!targetPane && !targetsOriginalViewer) return false;

    const activeViewer = viewer;
    const activeSlideId = currentSlideId;
    const activeSlideInfo = currentSlideInfo;
    const activeBrowsePath = currentBrowsePath;
    const activeAnalysis = _captureAnalysisContext();
    _captureActiveMultiViewContext();

    const targetHolder = targetPane || _multiViewOriginalContext;
    viewer = target.viewer;
    currentSlideId = targetPane ? targetPane.slideInfo.slide_id : targetHolder.slideId;
    currentSlideInfo = targetPane ? targetPane.slideInfo : targetHolder.slideInfo;
    currentBrowsePath = targetPane
        ? String(targetPane.slide?.path || '').replace(/^\/+|\/+$/g, '')
        : targetHolder.browsePath;
    _restoreAnalysisContext(targetHolder.analysis);

    try {
        applyResult();
        targetHolder.analysis = _captureAnalysisContext();
    } finally {
        viewer = activeViewer;
        currentSlideId = activeSlideId;
        currentSlideInfo = activeSlideInfo;
        currentBrowsePath = activeBrowsePath;
        _restoreAnalysisContext(activeAnalysis);
        _renderActiveViewerPanels();
    }
    return true;
}

function _ensureMultiViewPanes() {
    if (_multiViewPanes.length || !$multiViewGrid) return;
    for (let index = 0; index < 4; index += 1) {
        const element = document.createElement('section');
        element.className = 'multi-view-pane';
        element.hidden = true;
        element.tabIndex = 0;
        element.setAttribute('role', 'option');
        element.setAttribute('aria-selected', 'false');

        const canvas = document.createElement('canvas');
        canvas.className = 'multi-view-canvas';
        const overlay = document.createElement('canvas');
        overlay.className = 'multi-view-overlay';

        const header = document.createElement('div');
        header.className = 'multi-view-pane-header';
        const label = document.createElement('span');
        label.className = 'multi-view-pane-label';
        const fitButton = document.createElement('button');
        fitButton.type = 'button';
        fitButton.className = 'multi-view-pane-fit';
        fitButton.textContent = 'Fit';
        const focusButton = document.createElement('button');
        focusButton.type = 'button';
        focusButton.className = 'multi-view-pane-focus';
        focusButton.textContent = 'Enlarge';
        focusButton.disabled = true;
        header.append(label, fitButton, focusButton);

        const error = document.createElement('div');
        error.className = 'multi-view-pane-error';
        error.hidden = true;
        element.append(canvas, overlay, header, error);
        $multiViewGrid.appendChild(element);

        const paneViewer = new AiViewer(canvas, overlay);
        paneViewer.canEditDetectionResults = _canEditAiDetections();
        // Split panes have a much smaller viewport than the primary viewer.
        // Keep total decoded-tile memory bounded when four WSIs are open.
        paneViewer._maxCacheTiles = 160;
        const pane = {
            element, canvas, overlay, label, error, focusButton, viewer: paneViewer,
            slide: null, slideInfo: null, analysis: _emptyAnalysisContext(),
        };
        _bindMultiViewViewerCallbacks(paneViewer);
        element.addEventListener('pointerdown', () => _activateMultiViewPane(pane), true);
        element.addEventListener('focus', () => _activateMultiViewPane(pane));
        _multiViewFocus.bindPaneDoubleClick(pane, _activateMultiViewPane);
        fitButton.addEventListener('click', () => {
            _activateMultiViewPane(pane);
            paneViewer.fitToWindow();
        });
        focusButton.addEventListener('click', () => {
            _activateMultiViewPane(pane);
            _multiViewFocus.toggle(pane);
        });
        _multiViewPanes.push(pane);
    }
}

function _resetMultiViewPane(pane) {
    if (!pane) return;
    pane.viewer._loadGeneration += 1;
    pane.viewer._abortInflightImages();
    pane.viewer._resetVsTileLoads(true);
    pane.viewer._tileCache.clear();
    pane.viewer._tileLoading.clear();
    pane.viewer._tileFadeStart.clear();
    pane.viewer._loadQueue.length = 0;
    pane.viewer._loadQueuedKeys.clear();
    pane.viewer._activeLoads = 0;
    pane.viewer._thumbnailBitmap = null;
    pane.viewer.annotations = [];
    pane.viewer.selectedAnnotationId = null;
    pane.viewer.setDetectionResults([]);
    pane.viewer.setHiddenDetectionResults?.([]);
    pane.viewer.slideId = null;
    pane.viewer.slideInfo = null;
    pane.slide = null;
    pane.slideInfo = null;
    pane.analysis = _emptyAnalysisContext();
    pane.element.classList.remove('active');
    pane.element.setAttribute('aria-selected', 'false');
    pane.error.hidden = true;
    pane.focusButton.disabled = true;
}

function _exitMultiView(updateStatus = true) {
    _multiViewFocus.reset();
    _multiViewOpenSeq += 1;
    _abortLatestRead('multi-view-open');
    document.body.classList.remove('ai-multi-view-active');
    if (!$multiViewContainer || $multiViewContainer.hidden) {
        $viewerContainer?.classList.remove('multi-view-active');
        return;
    }

    _closeCellEditPopup();
    _captureActiveMultiViewContext();
    const original = _multiViewOriginalContext;
    viewer = _primaryViewer;
    _activeMultiViewPane = null;
    if (original) {
        currentSlideId = original.slideId;
        currentSlideInfo = original.slideInfo;
        currentBrowsePath = original.browsePath;
        _restoreAnalysisContext(original.analysis);
    }

    for (const pane of _multiViewPanes) {
        _resetMultiViewPane(pane);
        pane.element.hidden = true;
    }
    $multiViewContainer.hidden = true;
    $viewerContainer?.classList.remove('multi-view-active');
    if (currentSlideInfo) {
        $slideName.textContent = currentSlideInfo.filename || '';
        _updateScannerBadge(currentSlideInfo);
        _updateNdpColorToggleVisibility(currentSlideInfo);
        _enableActiveSlideControls();
        _renderActiveViewerPanels();
    }
    _multiViewOriginalContext = null;
    if (updateStatus) setStatus(currentSlideInfo?.filename ? `Loaded: ${currentSlideInfo.filename}` : 'Ready');
    requestAnimationFrame(() => {
        _primaryViewer._resizeCanvas();
        _primaryViewer.requestRender();
    });
}

async function _openMultiView(slides = []) {
    const uniqueSlides = [];
    for (const slide of slides) {
        if (slide?.slide_id && !uniqueSlides.some((item) => item.slide_id === slide.slide_id)) {
            uniqueSlides.push(slide);
        }
    }
    if (uniqueSlides.length < 2 || uniqueSlides.length > 4) {
        _refreshSameCaseSelection('Select 2 to 4 slides for Multi View.');
        return;
    }

    if ($multiViewContainer && !$multiViewContainer.hidden) _exitMultiView(false);
    _multiViewOriginalContext = {
        slideId: currentSlideId,
        slideInfo: currentSlideInfo,
        browsePath: currentBrowsePath,
        analysis: _captureAnalysisContext(),
    };
    const openSeq = ++_multiViewOpenSeq;
    const controller = _beginLatestRead('multi-view-open');
    _ensureMultiViewPanes();
    _multiViewFocus.reset();
    if ($sameCaseOpenChoice?.open) $sameCaseOpenChoice.close();
    _closeSameCaseDialog();
    $viewerContainer?.classList.add('multi-view-active');
    document.body.classList.add('ai-multi-view-active');
    $multiViewContainer.hidden = false;
    $multiViewGrid.className = `multi-view-grid count-${uniqueSlides.length}`;
    if ($multiViewTitle) $multiViewTitle.textContent = `Multi View · ${uniqueSlides.length} slides`;

    _multiViewPanes.forEach((pane, index) => {
        const slide = uniqueSlides[index];
        pane.element.hidden = !slide;
        if (!slide) {
            _resetMultiViewPane(pane);
            return;
        }
        pane.error.hidden = true;
        pane.slide = slide;
        pane.slideInfo = null;
        pane.focusButton.disabled = true;
        pane.analysis = _emptyAnalysisContext();
        pane.label.textContent = `Loading · ${slide.filename}`;
    });

    requestAnimationFrame(() => {
        for (const pane of _multiViewPanes.slice(0, uniqueSlides.length)) pane.viewer._resizeCanvas();
    });

    await Promise.all(uniqueSlides.map(async (slide, index) => {
        const pane = _multiViewPanes[index];
        try {
            const info = await api.openSlide(
                slide.filename,
                slide.path || '',
                'ai',
                { signal: controller.signal },
            );
            if (openSeq !== _multiViewOpenSeq) return;
            if (!info?.exists) throw new Error('Slide is unavailable.');
            const slideInfo = { ...info, filename: slide.filename };
            pane.slideInfo = slideInfo;
            pane.viewer.setColorCorrectionEnabled(!!api.shouldUseNdpMatch?.(slideInfo));
            pane.viewer.loadSlide(info.slide_id, slideInfo);
            _multiViewFocus.refresh();
            pane.label.textContent = `${_sameCaseProjectLabel(slide.path)} · ${slide.filename}`;
            pane.label.title = pane.label.textContent;
            requestAnimationFrame(() => {
                pane.viewer._resizeCanvas();
                pane.viewer.fitToWindow();
            });
        } catch (err) {
            if (_isAbortError(err)) return;
            if (openSeq !== _multiViewOpenSeq) return;
            pane.error.hidden = false;
            pane.error.textContent = `Open failed\n${err?.message || err}`;
            pane.label.textContent = slide.filename;
        }
    }));
    _finishLatestRead('multi-view-open', controller);
    if (openSeq === _multiViewOpenSeq) {
        _multiViewFocus.ready = true;
        const firstAvailablePane = _multiViewPanes
            .slice(0, uniqueSlides.length)
            .find((pane) => pane.slideInfo && pane.error.hidden);
        if (firstAvailablePane) _activateMultiViewPane(firstAvailablePane, false);
        _multiViewFocus.refresh();
        setStatus(`Multi View: ${uniqueSlides.length} slides · click a pane to activate tools`);
    }
}

function _showSameCaseOpenChoice(slideId = '') {
    const slide = _sameCaseSlides.find((item) => item.slide_id === slideId);
    if (!slide || !$sameCaseOpenChoice) return;
    _sameCaseChoiceSlideId = slide.slide_id;
    const multiSlides = _sameCaseMultiViewSlides(slide.slide_id);
    if ($sameCaseChoiceSlide) $sameCaseChoiceSlide.textContent = slide.filename;
    if ($sameCaseChoiceSummary) {
        $sameCaseChoiceSummary.textContent = multiSlides.length >= 2
            ? `${multiSlides.length} slides selected for comparison`
            : 'Select one more slide to use Multi View';
    }
    if ($btnChoiceMultiView) $btnChoiceMultiView.disabled = multiSlides.length < 2;
    if (!$sameCaseOpenChoice.open) $sameCaseOpenChoice.showModal();
}

function _closeSameCaseOpenChoice() {
    if ($sameCaseOpenChoice?.open) $sameCaseOpenChoice.close();
}

async function _viewSelectedSameCaseSlide() {
    const selectedSlides = _selectedSameCaseSlides();
    const slide = selectedSlides.length === 1 ? selectedSlides[0] : null;
    if (!slide) return;
    _exitMultiView(false);
    if (slide.slide_id === currentSlideId) {
        _closeSameCaseDialog();
        setStatus(`Already open: ${slide.filename}`);
        return;
    }
    if ($btnViewSameCase) $btnViewSameCase.disabled = true;
    if ($sameCaseSelection) $sameCaseSelection.textContent = `Opening ${slide.filename}...`;
    const targetPath = String(slide.path || _getCurrentProjectName() || '').replace(/^\/+|\/+$/g, '');
    try {
        if (targetPath !== currentBrowsePath) {
            currentBrowsePath = targetPath;
            history.replaceState(null, '', `/ai?path=${encodeURIComponent(targetPath)}`);
            await loadSlideList();
        }
        const item = [...($slideList?.querySelectorAll('.slide-list-item[data-slide-id]') || [])]
            .find((element) => element.dataset.slideId === slide.slide_id) || null;
        _closeSameCaseDialog();
        await openSavedSlide(slide.filename, item, targetPath);
    } catch (err) {
        setStatus(`Open failed: ${err?.message || err}`);
        if ($sameCaseDialog?.open) _refreshSameCaseSelection();
    }
}

$btnSameCase?.addEventListener('click', _loadSameCaseSlides);
$('#close-same-case')?.addEventListener('click', (event) => {
    event.preventDefault();
    _closeSameCaseDialog();
});
$('#cancel-same-case')?.addEventListener('click', _closeSameCaseDialog);
$btnViewSameCase?.addEventListener('click', _viewSelectedSameCaseSlide);
$btnMultiViewSameCase?.addEventListener('click', () => _openMultiView(_selectedSameCaseSlides()));
$sameCaseDialog?.addEventListener('cancel', (event) => {
    event.preventDefault();
    _closeSameCaseDialog();
});
$sameCaseDialog?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || !event.target?.classList?.contains('same-case-card')) return;
    event.preventDefault();
    _ensureSameCaseSlideSelected(event.target.dataset.slideId);
    _showSameCaseOpenChoice(event.target.dataset.slideId);
});
$('#close-same-case-choice')?.addEventListener('click', _closeSameCaseOpenChoice);
$('#cancel-same-case-choice')?.addEventListener('click', _closeSameCaseOpenChoice);
$sameCaseOpenChoice?.addEventListener('cancel', (event) => {
    event.preventDefault();
    _closeSameCaseOpenChoice();
});
$btnChoiceViewSlide?.addEventListener('click', () => {
    const slideId = _sameCaseChoiceSlideId;
    _selectedSameCaseSlideIds = slideId ? [slideId] : [];
    _refreshSameCaseSelection();
    _closeSameCaseOpenChoice();
    _viewSelectedSameCaseSlide();
});
$btnChoiceMultiView?.addEventListener('click', () => {
    const slides = _sameCaseMultiViewSlides(_sameCaseChoiceSlideId);
    _openMultiView(slides);
});
$('#exit-multi-view')?.addEventListener('click', () => _exitMultiView());

// Slide information dialog.
$btnInfo.addEventListener('click', async () => {
    if (!currentSlideInfo) return;
    const str_slide_id = currentSlideId;
    const info = currentSlideInfo;
    const clinicalInfo = await _loadSlideClinicalInfo();
    if (currentSlideId !== str_slide_id) return;
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
    entry.pending_cancel = true;
    if (!entry.task_id) {
        setStatus('Cancel queued. The task will stop as soon as it starts.');
        return true;
    }
    entry.controller?.abort();
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

    const aiTarget = _currentAiTarget();
    const taskController = new AbortController();
    _runningAiTasks['detect'] = { task_id: null, buttonEl: $btnDetect, target: aiTarget, controller: taskController };
    _setButtonRunning($btnDetect, true);
    $progressLabel.textContent = 'Cell Detection...';
    setProgress(0);
    setStatus('Cell Detection started...');

    viewer.setDrawMode(null);

    try {
        const tissueType = document.querySelector('input[name="tissue-type"]:checked')?.value || 'Stomach';

        const roiAnnotations = viewer.annotations.filter(a => a.visible && a.type !== 'point' && a.coordinates.length >= 3);
        const roiPolygons = roiAnnotations.length > 0 ? roiAnnotations.map(a => a.coordinates) : null;

        const { task_id } = await api.startDetection(aiTarget.slideId, roiPolygons, tissueType);
        if (_runningAiTasks['detect']) {
            _runningAiTasks['detect'].task_id = task_id;
            if (_runningAiTasks['detect'].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
                taskController.abort();
                return;
            }
        }

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks['detect']) return;
            const st = await api.getTaskStatus(task_id, { signal: taskController.signal });
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
                const result = await api.getTaskResult(
                    task_id,
                    _makeResultDownloadProgress(),
                    { signal: taskController.signal },
                );
                if (!_applyAiResultToTarget(aiTarget, () => onDetectionComplete(result, roiPolygons, tissueType))) {
                    setStatus('Detection completed, but its slide is no longer open.');
                }
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
        if (_isAbortError(err)) return;
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
    viewer.setStilHeatmap?.(result.stil_score?.available ? result.stil_score.spatial_heatmap : null);
    _applyInitialQuantiHeVisibility();
    _updateStilScoreDisplay(result.stil_score || null);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);
    const stilStatus = result.stil_score?.available
        ? ` · AI-estimated sTIL ${Number(result.stil_score.score_percent || 0).toFixed(1)}%`
        : '';
    setStatus(`Detection complete: ${displayCount.toLocaleString()} cells${stilStatus}`);
    buildResultList(result);

    $btnVisualize.disabled = false;
    _syncHeatmapToggle();
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
    renderAnnotationPanel();
}

const CLASS_COLORS = {
    0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
    4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
};
const QUANTI_HE_STROMAL_CLASS_ID = 5;

function _updateStilScoreDisplay(score) {
    if (!$hneStilResult) return;
    $hneStilResult.hidden = !score;
    if (!score) {
        if ($hneStilValue) $hneStilValue.textContent = '--';
        if ($hneStilMetrics) $hneStilMetrics.innerHTML = '';
        return;
    }
    if (!score.available) {
        if ($hneStilValue) $hneStilValue.textContent = 'N/A';
        if ($hneStilMetrics) {
            $hneStilMetrics.innerHTML = `
                <div class="stil-score-metric stil-score-metric-wide">
                    <span>Score unavailable</span>
                    <strong>${escapeHtml(score.reason || 'Required tissue was not detected')}</strong>
                </div>`;
        }
        return;
    }

    if ($hneStilValue) $hneStilValue.textContent = `${Number(score.score_percent || 0).toFixed(1)}%`;
    if ($hneStilMetrics) {
        $hneStilMetrics.innerHTML = `
            <div class="stil-score-metric">
                <span>Lymphocyte density</span>
                <strong>${Number(score.lymphocyte_density_cells_mm2 || 0).toLocaleString()} <small>cells/mm²</small></strong>
            </div>
            <div class="stil-score-metric">
                <span>Plasma-cell density</span>
                <strong>${Number(score.plasma_density_cells_mm2 || 0).toLocaleString()} <small>cells/mm²</small></strong>
            </div>
            <div class="stil-score-metric">
                <span>Tumor-associated stroma</span>
                <strong>${Number(score.tumor_associated_stroma_area_mm2 || 0).toFixed(2)} <small>mm²</small></strong>
            </div>
            <div class="stil-score-metric">
                <span>Immune cells in stroma</span>
                <strong>${Number((score.lymphocyte_count || 0) + (score.plasma_count || 0)).toLocaleString()}</strong>
            </div>
        `;
    }
}

function _applyInitialQuantiHeVisibility() {
    if (!viewer?.classVisibility) return;
    if (Object.prototype.hasOwnProperty.call(viewer.classVisibility, QUANTI_HE_STROMAL_CLASS_ID)) {
        viewer.classVisibility[QUANTI_HE_STROMAL_CLASS_ID] = false;
    }
}

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
    renderAnnotationPanel();
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
    const visibleClassEntries = Object.keys(counts).filter(id => counts[id] > 0);
    const bool_all_visible = visibleClassEntries.every(id => viewer.classVisibility[parseInt(id)] !== false);
    const bool_none_visible = visibleClassEntries.every(id => viewer.classVisibility[parseInt(id)] === false);
    totalCb.checked = bool_all_visible;
    totalCb.indeterminate = !bool_all_visible && !bool_none_visible;
    totalCb.addEventListener('change', () => {
        const checked = totalCb.checked;
        for (const [id, cb] of Object.entries(classCbs)) {
            cb.checked = checked;
            viewer.classVisibility[parseInt(id)] = checked;
        }
        viewer.requestRender();
        _updateResultCounts();
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
        cb.checked = viewer.classVisibility[id] !== false;
        classCbs[id] = cb;
        cb.addEventListener('change', () => {
            viewer.classVisibility[id] = cb.checked;
            // Sync the total checkbox state.
            const allChecked = Object.values(classCbs).every(c => c.checked);
            const noneChecked = Object.values(classCbs).every(c => !c.checked);
            totalCb.checked = allChecked;
            totalCb.indeterminate = !allChecked && !noneChecked;
            viewer.requestRender();
            _updateResultCounts();
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
    viewer.setHeatmapVisible?.(false);
    viewer.setStilHeatmapVisible?.(false);
    viewer.setStilHeatmap?.(null);
    viewer.setDetectionResults([]);
    viewer.setHiddenDetectionResults?.([]);
    lastSegData = null;
    _lastDetectionResult = null;
    _lastDetectionTissue = null;
    _stickyAddClassId = null;
    _hideStickyHud();
    _lastDetectionModel = null;
    _lastDetectionRoi = null;
    _updateStilScoreDisplay(null);
    renderAnnotationPanel();
}

function _syncHeatmapToggle() {
    if (!$btnHeatmapToggle) return;
    const enabled = Boolean(viewer.heatmapVisible);
    const hasResults = Array.isArray(viewer.detectionCells) && viewer.detectionCells.length > 0;
    $btnHeatmapToggle.disabled = !hasResults;
    $btnHeatmapToggle.textContent = `Heatmap: ${enabled ? 'On' : 'Off'}`;
    $btnHeatmapToggle.classList.toggle('active', enabled);
    $btnHeatmapToggle.setAttribute('aria-pressed', enabled ? 'true' : 'false');

    if ($btnStilHeatmapToggle) {
        const hasStilHeatmap = Boolean(viewer.stilHeatmap?.cells?.length);
        const stilEnabled = Boolean(viewer.stilHeatmapVisible);
        $btnStilHeatmapToggle.hidden = !hasStilHeatmap;
        $btnStilHeatmapToggle.disabled = !hasResults || !hasStilHeatmap;
        $btnStilHeatmapToggle.textContent = `sTIL Heatmap: ${stilEnabled ? 'On' : 'Off'}`;
        $btnStilHeatmapToggle.classList.toggle('active', stilEnabled);
        $btnStilHeatmapToggle.setAttribute('aria-pressed', stilEnabled ? 'true' : 'false');
    }
}

$btnHeatmapToggle?.addEventListener('click', () => {
    if (_blockViewerAction() || !viewer.detectionCells?.length) return;
    viewer.setHeatmapVisible?.(!viewer.heatmapVisible);
    _syncHeatmapToggle();
    setStatus(viewer.heatmapVisible ? 'Cell-density heatmap enabled' : 'Individual cell display enabled');
});

$btnStilHeatmapToggle?.addEventListener('click', () => {
    if (_blockViewerAction() || !viewer.stilHeatmap?.cells?.length) return;
    viewer.setStilHeatmapVisible?.(!viewer.stilHeatmapVisible);
    _syncHeatmapToggle();
    setStatus(viewer.stilHeatmapVisible ? 'Local sTIL heatmap enabled' : 'Individual cell display enabled');
});

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
    const stilScore = _lastDetectionResult?.stil_score || null;
    const isIhc = isHer2 || isAllred || isKi67;
    const modelType = isIhc ? 'Quanti IHC' : (isPdScore ? 'Quanti PD-L1' : 'Quanti HE');
    const scoreType = isHer2 ? 'HER2'
        : isAllred ? 'Allred'
        : isKi67 ? 'KI67'
        : isPdScore ? _lastDetectionResult.pd_score.score_type
        : stilScore?.available ? 'sTIL' : null;
    const classNames = _lastDetectionResult?.class_names || null;
    const classColors = _lastDetectionResult?.class_colors || null;

    showVisualization(filtered, lastSegData, thumbUrl, {
        slideName, tissue, slideDims,
        modelType, scoreType, classNames, classColors, stilScore,
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
$loadUserEditDialog?.addEventListener('close', () => _abortLatestRead('user-edit-list'));

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
    const str_slide_id = currentSlideId;
    const controller = _beginLatestRead('user-edit-list');
    $loadUserEditMeta.textContent = `Mode: ${aiMode}  /  Variant: ${variant}`;
    $loadUserEditList.innerHTML = '<div style="padding:12px; color:#888;">Loading...</div>';
    $loadUserEditDialog.showModal();

    let users = [];
    try {
        const r = await api.listUserAiEdits(str_slide_id, aiMode, variant, { signal: controller.signal });
        if (controller.signal.aborted || currentSlideId !== str_slide_id || !$loadUserEditDialog.open) return;
        users = r.users || [];
    } catch (err) {
        if (_isAbortError(err)) return;
        $loadUserEditList.replaceChildren();
        const errorEl = document.createElement('div');
        errorEl.style.cssText = 'padding:12px; color:#c66;';
        errorEl.textContent = `Failed: ${err.message}`;
        $loadUserEditList.appendChild(errorEl);
        return;
    } finally {
        _finishLatestRead('user-edit-list', controller);
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
            const aiTarget = _currentAiTarget();
            const loadController = _beginLatestRead('user-edit-load');
            try {
                setStatus(`Loading ${displayName}'s analysis...`);
                const r = await api.loadUserAiEdit(
                    aiTarget.slideId,
                    aiMode,
                    u.str_user_id,
                    variant,
                    { signal: loadController.signal },
                );
                if (!_applyAiResultToTarget(aiTarget, () => _applyLoadedResult(aiMode, variant, r.result))) {
                    setStatus('Result loaded, but its slide is no longer open.');
                    return;
                }
                setStatus(`Loaded: ${displayName} (${r.result?.cells?.length ?? 0} cells)`);
            } catch (err) {
                if (_isAbortError(err)) return;
                setStatus(`Load failed: ${err.message}`);
            } finally {
                _finishLatestRead('user-edit-load', loadController);
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
const LEFT_PANEL_MIN_W = 260;
const LEFT_PANEL_MAX_W = 500;
const LEFT_PANEL_COLLAPSE_W = 130;
const LEFT_PANEL_DEFAULT_W = 260;
const RIGHT_PANEL_MIN_W = 360;
const RIGHT_PANEL_MAX_W = 600;
const RIGHT_PANEL_COLLAPSE_W = 180;
const RIGHT_PANEL_DEFAULT_W = 380;

function _resizeViewerCanvasSoon() {
    if (viewer && typeof viewer._resizeCanvas === 'function') {
        viewer._resizeCanvas();
    }
}

function _setLeftPanelCollapsed(collapsed) {
    const shouldCollapse = Boolean(collapsed);
    const changed = document.body.classList.contains('left-panel-collapsed') !== shouldCollapse;
    document.body.classList.toggle('left-panel-collapsed', shouldCollapse);
    localStorage.setItem('leftPanelCollapsed', shouldCollapse ? '1' : '0');
    $resizer?.setAttribute('aria-label', shouldCollapse ? 'Open slide panel' : 'Resize slide panel');
    $resizer?.setAttribute('title', shouldCollapse ? 'Open slide panel' : 'Drag to resize slide panel');
    if (changed) _resizeViewerCanvasSoon();
}

function _openLeftPanel() {
    const storedWidth = parseInt(localStorage.getItem('leftPanelWidth') || '', 10);
    const width = Number.isFinite(storedWidth) && storedWidth >= LEFT_PANEL_MIN_W && storedWidth <= LEFT_PANEL_MAX_W
        ? storedWidth
        : LEFT_PANEL_DEFAULT_W;
    document.documentElement.style.setProperty('--left-panel-w', `${width}px`);
    _setLeftPanelCollapsed(false);
}

function _setRightPanelCollapsed(collapsed) {
    const shouldCollapse = Boolean(collapsed);
    const changed = document.body.classList.contains('right-panel-collapsed') !== shouldCollapse;
    document.body.classList.toggle('right-panel-collapsed', shouldCollapse);
    localStorage.setItem('rightPanelCollapsed', shouldCollapse ? '1' : '0');
    $rightResizer?.setAttribute('aria-label', shouldCollapse ? 'Open AI panel' : 'Resize AI panel');
    $rightResizer?.setAttribute('title', shouldCollapse ? 'Open AI panel' : 'Drag to resize AI panel');
    if (changed) _resizeViewerCanvasSoon();
}

function _openRightPanel() {
    const storedWidth = parseInt(localStorage.getItem('rightPanelWidth') || '', 10);
    const width = Number.isFinite(storedWidth) && storedWidth >= RIGHT_PANEL_MIN_W && storedWidth <= RIGHT_PANEL_MAX_W
        ? storedWidth
        : RIGHT_PANEL_DEFAULT_W;
    document.documentElement.style.setProperty('--right-panel-w', `${width}px`);
    _setRightPanelCollapsed(false);
}

function _restorePanelSizes() {
    const int_left_w = parseInt(localStorage.getItem('leftPanelWidth') || '', 10);
    if (!Number.isNaN(int_left_w) && int_left_w >= LEFT_PANEL_MIN_W && int_left_w <= LEFT_PANEL_MAX_W) {
        document.documentElement.style.setProperty('--left-panel-w', `${int_left_w}px`);
    } else {
        document.documentElement.style.setProperty('--left-panel-w', `${LEFT_PANEL_DEFAULT_W}px`);
    }
    _setLeftPanelCollapsed(localStorage.getItem('leftPanelCollapsed') === '1');
    const int_right_w = parseInt(localStorage.getItem('rightPanelWidth') || '', 10);
    if (!Number.isNaN(int_right_w) && int_right_w >= RIGHT_PANEL_MIN_W && int_right_w <= RIGHT_PANEL_MAX_W) {
        document.documentElement.style.setProperty('--right-panel-w', `${int_right_w}px`);
    } else {
        document.documentElement.style.setProperty('--right-panel-w', `${RIGHT_PANEL_DEFAULT_W}px`);
    }
    _setRightPanelCollapsed(localStorage.getItem('rightPanelCollapsed') === '1');
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

let _suppressLeftPanelOpenClick = false;
$resizer.addEventListener('mousedown', (e) => {
    e.preventDefault();
    $resizer.classList.add('dragging');
    const startX = e.clientX;
    const storedWidth = parseInt(localStorage.getItem('leftPanelWidth') || '', 10);
    const startW = document.body.classList.contains('left-panel-collapsed')
        ? 0
        : ($leftPanel.offsetWidth || (Number.isFinite(storedWidth) ? storedWidth : LEFT_PANEL_DEFAULT_W));
    let dragged = false;

    function onMove(ev) {
        const rawWidth = startW + ev.clientX - startX;
        if (Math.abs(ev.clientX - startX) > 2) dragged = true;
        if (rawWidth <= LEFT_PANEL_COLLAPSE_W) {
            _setLeftPanelCollapsed(true);
            return;
        }
        _setLeftPanelCollapsed(false);
        const w = Math.max(LEFT_PANEL_MIN_W, Math.min(LEFT_PANEL_MAX_W, rawWidth));
        document.documentElement.style.setProperty('--left-panel-w', `${w}px`);
        localStorage.setItem('leftPanelWidth', String(Math.round(w)));
        _resizeViewerCanvasSoon();
    }
    function onUp() {
        if (dragged) {
            _suppressLeftPanelOpenClick = true;
            setTimeout(() => { _suppressLeftPanelOpenClick = false; }, 0);
        }
        $resizer.classList.remove('dragging');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
});

$resizer.addEventListener('click', () => {
    if (_suppressLeftPanelOpenClick) return;
    if (document.body.classList.contains('left-panel-collapsed')) _openLeftPanel();
});
$resizer.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    if (!document.body.classList.contains('left-panel-collapsed')) return;
    event.preventDefault();
    _openLeftPanel();
});

if ($rightResizer && $rightPanel) {
    let suppressRightPanelOpenClick = false;
    $rightResizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        $rightResizer.classList.add('dragging');
        const startX = e.clientX;
        const storedWidth = parseInt(localStorage.getItem('rightPanelWidth') || '', 10);
        const startW = document.body.classList.contains('right-panel-collapsed')
            ? 0
            : ($rightPanel.offsetWidth || (Number.isFinite(storedWidth) ? storedWidth : RIGHT_PANEL_DEFAULT_W));
        let dragged = false;

        function onMove(ev) {
            const int_left_w = $leftPanel ? $leftPanel.offsetWidth : 0;
            const int_max_by_viewport = Math.max(RIGHT_PANEL_MIN_W, window.innerWidth - int_left_w - 360);
            const int_max = Math.min(RIGHT_PANEL_MAX_W, int_max_by_viewport);
            const rawWidth = startW - (ev.clientX - startX);
            if (Math.abs(ev.clientX - startX) > 2) dragged = true;
            if (rawWidth <= RIGHT_PANEL_COLLAPSE_W) {
                _setRightPanelCollapsed(true);
                return;
            }
            _setRightPanelCollapsed(false);
            const w = Math.max(RIGHT_PANEL_MIN_W, Math.min(int_max, rawWidth));
            document.documentElement.style.setProperty('--right-panel-w', `${w}px`);
            localStorage.setItem('rightPanelWidth', String(Math.round(w)));
            _resizeViewerCanvasSoon();
        }

        function onUp() {
            if (dragged) {
                suppressRightPanelOpenClick = true;
                setTimeout(() => { suppressRightPanelOpenClick = false; }, 0);
            }
            $rightResizer.classList.remove('dragging');
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        }

        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    });
    $rightResizer.addEventListener('click', () => {
        if (suppressRightPanelOpenClick) return;
        if (document.body.classList.contains('right-panel-collapsed')) _openRightPanel();
    });
    $rightResizer.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        if (!document.body.classList.contains('right-panel-collapsed')) return;
        event.preventDefault();
        _openRightPanel();
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
    const controller = _beginLatestRead('project-list');
    try {
        const data = await api.listProjects({ signal: controller.signal });
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
        if (_isAbortError(err)) return _projectListCache;
        console.warn('Project list load failed:', err);
        _projectListCache = [];
        return [];
    } finally {
        _finishLatestRead('project-list', controller);
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
    const controller = _beginLatestRead('project-stats');
    try {
        const data = await api.dashboard(false, { signal: controller.signal });
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
        if (_isAbortError(err)) return;
        console.warn('Project summary load failed:', err);
    } finally {
        _finishLatestRead('project-stats', controller);
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
    const int_request_seq = ++_slideListRequestSeq;
    const str_request_path = currentBrowsePath;
    const controller = _beginLatestRead('slide-list');
    try {
        const data = await api.browse(str_request_path, { signal: controller.signal });
        // Folder changes can overlap. Never render an older folder response
        // using the path of the folder that is active now.
        if (int_request_seq !== _slideListRequestSeq || str_request_path !== currentBrowsePath) return;
        _lastBrowseData = data || { path: str_request_path, folders: [], slides: [] };
        _lastBrowseData.path = str_request_path;
        renderSlideList(_lastBrowseData);
    } catch (err) {
        if (_isAbortError(err) || int_request_seq !== _slideListRequestSeq) return;
        console.error('Slide list load failed:', err);
    } finally {
        _finishLatestRead('slide-list', controller);
    }
}

function _getFilteredSlides(slides) {
    const query = String($slideNameSearch?.value || '').trim().toLowerCase();
    if (!query) return slides || [];
    return (slides || []).filter((slide) => String(slide.filename || '').toLowerCase().includes(query));
}

function _setSlideLabelVisibility(bool_visible) {
    _showSlideLabels = !!bool_visible;
    localStorage.setItem(SLIDE_LABEL_VISIBILITY_KEY, _showSlideLabels ? '1' : '0');
    _slideLabelObserver?.disconnect();
    _slideLabelObserver = null;
    $slideList?.querySelectorAll('.slide-label-thumb').forEach((img) => {
        if (!_showSlideLabels) {
            img.dataset.cancelled = '1';
            img.classList.remove('loaded');
            img.hidden = true;
            img.removeAttribute('src');
            return;
        }
        img.dataset.cancelled = '0';
        _observeSlideLabelThumb(img);
    });
}

function _requestSlideLabelImage(img) {
    if (!img || !_showSlideLabels || img.src) return;
    const str_key = `${img.dataset.path || ''}/${img.dataset.filename || ''}`;
    if (_slideLabelAvailability.get(str_key) === false) return;
    img.dataset.cancelled = '0';
    img.hidden = true;
    const str_url = api.labelUrlByName(img.dataset.filename || '', img.dataset.path || '', 300);
    if (str_url) img.src = str_url;
}

function _getSlideLabelObserver() {
    if (_slideLabelObserver || typeof IntersectionObserver !== 'function') return _slideLabelObserver;
    _slideLabelObserver = new IntersectionObserver((entries, observer) => {
        for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            const img = entry.target.querySelector?.('.slide-label-thumb');
            _requestSlideLabelImage(img);
            observer.unobserve(entry.target);
        }
    }, { root: $slideList, rootMargin: '240px 0px' });
    return _slideLabelObserver;
}

function _observeSlideLabelThumb(img) {
    if (!img || !_showSlideLabels) return;
    const item = img.closest('.slide-list-item');
    const observer = _getSlideLabelObserver();
    if (observer && item) observer.observe(item);
    else _requestSlideLabelImage(img);
}

function _createSlideLabelThumb(filename, path) {
    const img = document.createElement('img');
    img.className = 'slide-label-thumb';
    img.alt = `${filename} label`;
    img.title = 'Scanner label';
    // Native dimensions/hidden state keep the sidebar stable even while a new
    // stylesheet is still being fetched from cache.
    img.width = 40;
    img.height = 40;
    img.hidden = true;
    img.dataset.filename = filename;
    img.dataset.path = path || '';
    img.dataset.cancelled = '0';
    const str_key = `${path || ''}/${filename}`;
    img.addEventListener('load', () => {
        if (!img.naturalWidth || !img.naturalHeight) {
            _slideLabelAvailability.set(str_key, false);
            img.classList.remove('loaded');
            img.hidden = true;
            return;
        }
        _slideLabelAvailability.set(str_key, true);
        if (_showSlideLabels) {
            img.classList.add('loaded');
            img.hidden = false;
        }
    });
    img.addEventListener('error', () => {
        if (img.dataset.cancelled === '1') return;
        _slideLabelAvailability.set(str_key, false);
        img.classList.remove('loaded');
        img.hidden = true;
    });
    return img;
}

function renderSlideList(data = _lastBrowseData) {
        _slideLabelObserver?.disconnect();
        _slideLabelObserver = null;
        $slideList.querySelectorAll('img').forEach((img) => {
            if (img.classList.contains('slide-label-thumb')) img.dataset.cancelled = '1';
            api.cancelMediaImage?.(img);
        });
        $slideList.innerHTML = '';
        _syncProjectSelect();
        const str_list_path = String(data?.path ?? currentBrowsePath);
        const filteredSlides = _getFilteredSlides(data.slides || []);

        if ((data.folders || []).length === 0 && filteredSlides.length === 0) {
            $slideList.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;text-align:center;">Empty</div>';
        }

        for (const f of data.folders || []) {
            const folderPath = str_list_path ? `${str_list_path}/${f.name}` : f.name;
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
            const str_thumb_path = str_list_path;
            thumb.src = api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 300);
            api.attachMediaImageRetry(thumb,
                () => api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 300),
                () => { thumb.style.display = 'none'; });
            const labelThumb = _createSlideLabelThumb(str_thumb_filename, str_thumb_path);

            const name = document.createElement('div');
            name.className = 'slide-list-name';
            name.textContent = s.filename;
            name.title = `${s.filename} (${s.size_mb} MB)`;

            const nameWrap = document.createElement('div');
            nameWrap.className = 'slide-name-cell';
            nameWrap.append(thumb, labelThumb, name);
            item.append(nameWrap);

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
                    openSavedSlide(s.filename, item, str_list_path);
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
            _observeSlideLabelThumb(labelThumb);
        }

        updateBreadcrumb();
        _refreshAiActiveBadges();
        _startAiActivePolling();
}

$slideNameSearch?.addEventListener('input', () => renderSlideList(_lastBrowseData));
$showSlideLabels?.addEventListener('change', () => {
    _setSlideLabelVisibility($showSlideLabels.checked);
});

let _aiActivePollTimer = null;
let _aiActivePollController = null;
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
    if (_aiActivePollController) {
        _aiActivePollController.abort();
        _aiActivePollController = null;
    }
}
async function _refreshAiActiveBadges() {
    if (_isViewerRole()) {
        $slideList?.querySelectorAll('.slide-ai-active').forEach(el => el.remove());
        return;
    }
    // A slow status response must not stack another poll every four seconds.
    if (_aiActivePollController) return;
    const controller = new AbortController();
    _aiActivePollController = controller;

    let dict_active = {};
    try {
        const data = await api.getActiveAiTasks({ signal: controller.signal });
        dict_active = data.active || {};
    } catch (err) {
        if (!_isAbortError(err)) console.warn('[active-ai] status refresh failed:', err);
        return;
    } finally {
        if (_aiActivePollController === controller) _aiActivePollController = null;
    }

    const items = $slideList.querySelectorAll('.slide-list-item[data-filename]');
    items.forEach((item) => {
        const fn = item.dataset.filename;
        const list_running = dict_active[fn];
        const existing = item.querySelector('.slide-ai-active');
        if (list_running && list_running.length > 0) {
            const str_title = list_running
                .map(t => `${t.model}${t.variant ? '/' + t.variant : ''} · ${t.status}`)
                .join(', ');
            if (existing) {
                existing.title = str_title;
            } else {
                const badge = document.createElement('span');
                badge.className = 'slide-ai-active';
                badge.title = str_title;
                item.appendChild(badge);
            }
        } else {
            if (existing) existing.remove();
        }
    });
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
    const clearDragOverPanel = () => {
        $slideList.classList.remove('drag-over-panel');
    };
    $slideList.addEventListener('dragover', (e) => {
        if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
        e.preventDefault();
        $slideList.classList.add('drag-over-panel');
    });
    $slideList.addEventListener('dragleave', (e) => {
        if (!$slideList.contains(e.relatedTarget)) clearDragOverPanel();
    });
    $slideList.addEventListener('drop', async (e) => {
        clearDragOverPanel();
        if (!e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
        e.preventDefault();
        await uploadFiles(e.dataTransfer.files, currentBrowsePath);
    });
    window.addEventListener('drop', clearDragOverPanel);
    window.addEventListener('dragend', clearDragOverPanel);
    window.addEventListener('blur', clearDragOverPanel);
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

let _openSlideAbortController = null;
let _openSlideSeq = 0;

async function openSavedSlide(filename, itemEl, slidePath = currentBrowsePath) {
    _openSlideAbortController?.abort();
    const controller = new AbortController();
    _openSlideAbortController = controller;
    const seq = ++_openSlideSeq;
    setStatus('Opening...');
    try {
        const info = await api.openSlide(filename, slidePath, '', { signal: controller.signal });
        if (seq !== _openSlideSeq || controller.signal.aborted) return;
        if (info.exists) {
            $slideList.querySelectorAll('.slide-list-item').forEach(el => el.classList.remove('active'));
            if (itemEl) itemEl.classList.add('active');
            onSlideLoaded(info.slide_id, info, filename);
        }
    } catch (err) {
        if (err?.name === 'AbortError') return;
        setStatus(`Open failed: ${err.message}`);
    } finally {
        if (_openSlideAbortController === controller) _openSlideAbortController = null;
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
    const controller = _beginLatestRead('folder-config');
    let cfg = { enabled: false, tasks: [] };
    try {
        cfg = await api.getFolderAiConfig(folderPath, { signal: controller.signal });
    } catch (err) {
        if (_isAbortError(err)) return;
        console.warn('Folder config load failed:', err);
    } finally {
        _finishLatestRead('folder-config', controller);
    }

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
    const taskController = new AbortController();
    _runningAiTasks[str_key] = { task_id: null, buttonEl: btnEl, controller: taskController };
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
                taskController.abort();
                return;
            }
        }
        _vsLastTargetMpp = targetMpp;

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks[str_key]) return;
            const st = await api.getTaskStatus(task_id, { signal: taskController.signal });
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);

            if (st.status === 'completed') {
                const result = await api.getTaskResult(
                    task_id,
                    _makeResultDownloadProgress(),
                    { signal: taskController.signal },
                );
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
        if (_isAbortError(err)) return;
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

    const aiTarget = _currentAiTarget();
    const taskController = new AbortController();
    _runningAiTasks['pd-score'] = { task_id: null, buttonEl: $btnPdScore, target: aiTarget, controller: taskController };
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

        const { task_id } = await api.startPdScore(aiTarget.slideId, roiPolygons, tissueType);
        if (_runningAiTasks['pd-score']) {
            _runningAiTasks['pd-score'].task_id = task_id;
            if (_runningAiTasks['pd-score'].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
                taskController.abort();
                return;
            }
        }

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks['pd-score']) return;
            const st = await api.getTaskStatus(task_id, { signal: taskController.signal });
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);
            $progressLabel.textContent = 'PD-L1 Detection';

            if (st.status === 'completed') {
                const result = await api.getTaskResult(
                    task_id,
                    _makeResultDownloadProgress(),
                    { signal: taskController.signal },
                );
                if (!_applyAiResultToTarget(aiTarget, () => onPdScoreComplete(result, roiPolygons, tissueType))) {
                    setStatus('Quanti PD-L1 completed, but its slide is no longer open.');
                }
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
        if (_isAbortError(err)) return;
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
    _syncHeatmapToggle();
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
    renderAnnotationPanel();
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
    const aiTarget = _currentAiTarget();
    const taskController = new AbortController();
    _runningAiTasks[str_key] = { task_id: null, buttonEl: btnEl, target: aiTarget, controller: taskController };
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

        const { task_id } = await api.startPreciseIhc(aiTarget.slideId, roiPolygons, marker);
        if (_runningAiTasks[str_key]) {
            _runningAiTasks[str_key].task_id = task_id;
            if (_runningAiTasks[str_key].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
                taskController.abort();
                return;
            }
        }

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks[str_key]) return;
            const st = await api.getTaskStatus(task_id, { signal: taskController.signal });
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);
            $progressLabel.textContent = `${markerLabel} Detection`;

            if (st.status === 'completed') {
                const result = await api.getTaskResult(
                    task_id,
                    _makeResultDownloadProgress(),
                    { signal: taskController.signal },
                );
                if (!_applyAiResultToTarget(aiTarget, () => onPreciseIhcComplete(result, roiPolygons, marker))) {
                    setStatus(`${markerLabel} completed, but its slide is no longer open.`);
                }
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
        if (_isAbortError(err)) return;
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
    _syncHeatmapToggle();
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
    if (_isLabelerRole()) _applyLabelerRoleRestrictions();
    renderAnnotationPanel();
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
    const _urlParams = new URLSearchParams(location.search);
    const _paramSlides = _urlParams.getAll('slide').filter(Boolean);
    const _paramPaths = _urlParams.getAll('path');
    const _paramSlideIds = _urlParams.getAll('slideId');
    const _paramSlide = _paramSlides[0] || null;
    const _paramPath = _paramPaths.length ? _paramPaths[0] : _urlParams.get('path');
    const _paramMultiView = _urlParams.get('multiView') === '1';
    const _paramMultiSlides = _paramSlides.map((filename, index) => ({
        filename,
        path: _paramPaths[index] || '',
        slide_id: _paramSlideIds[index] || '',
    })).filter((slide) => slide.filename && slide.slide_id).slice(0, 4);
    if (_paramPath !== null) currentBrowsePath = _paramPath;
    const bool_show_project_gate = !_paramSlide && _paramPath === null;

    // Project metadata does not depend on the user profile. Start it while
    // the authentication request is in flight instead of waiting for /me.
    // api._authFetch serializes the initial media-ticket request, then both
    // authenticated API requests can complete in parallel.
    const _projectListPromise = loadProjectList();

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

    const list_projects = await _projectListPromise;
    if (bool_show_project_gate) {
        _showProjectGate(list_projects);
        return;
    }

    await loadSlideList();

    if (_paramMultiView && _paramMultiSlides.length >= 2) {
        const firstSlide = _paramMultiSlides[0];
        await openSavedSlide(firstSlide.filename, null, firstSlide.path);
        await _openMultiView(_paramMultiSlides);
        history.replaceState(null, '', '/ai');
    } else if (_paramSlide) {
        await openSavedSlide(_paramSlide, null, _paramPath || currentBrowsePath);
        history.replaceState(null, '', '/ai');
    }
})();
