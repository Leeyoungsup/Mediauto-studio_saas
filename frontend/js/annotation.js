import { bindFixedAreaTools } from './annotation-area.js?v=20260914-area-toggle-01';
/**
 * MeDIAuto Studio SaaS annotation entry point.
 */

import { api } from './api.js?v=20260914-01';
import { TissueAnnotationViewer } from './tissue-annotation-viewer.js?v=20260914-02';
import { CellAnnotationViewer } from './cell-annotation-viewer.js?v=20260914-02';
import { CellPatchWorkflow } from './cell-patch-workflow.js?v=20260831-01';
import { showVisualization } from './visualization.js?v=20260824-07';
import { $, esc as _esc, normalizeUserRole as _normalizeUserRole, roleLabel as _roleLabel } from './common-utils.js?v=20260604-01';

if (!localStorage.getItem('access_token')) {
    window.location.replace('/login');
    throw new Error('Not authenticated - redirecting to /login');
}

function _isAnnotationPage() {
    return true;
}

const ANNOTATION_PAGE_KIND = location.pathname.includes('cell') ? 'cell' : 'tissue';
const ANNOTATION_PAGE_ROUTE = ANNOTATION_PAGE_KIND === 'cell' ? '/cell-annotation' : '/tissue-annotation';
const ANNOTATION_HEADER_ACTIVE = ANNOTATION_PAGE_KIND === 'cell' ? 'cell-annotation' : 'tissue-annotation';
const ANNOTATION_STATUS_SCOPE = ANNOTATION_PAGE_KIND === 'cell' ? 'cell_annotation' : 'tissue_annotation';
document.body.classList.toggle('cell-annotation-page', ANNOTATION_PAGE_KIND === 'cell');
document.body.classList.toggle('tissue-annotation-page', ANNOTATION_PAGE_KIND !== 'cell');

const $canvas = $('#wsi-canvas');
const $overlay = $('#overlay-canvas');
const $slideName = $('#slide-name');
const $statusText = $('#status-text');
const $aiAssistanceToolbarStatus = $('#ai-assistance-toolbar-status');
const $aiAssistanceToolbarLabel = $('#ai-assistance-toolbar-label');
const $aiAssistanceToolbarPercent = $('#ai-assistance-toolbar-percent');
const $aiAssistanceToolbarFill = $('#ai-assistance-toolbar-fill');
const $zoomInfo = $('#zoom-info');
const $patchZoomControl = $('#patch-zoom-control');
const $patchZoomInfo = $('#patch-zoom-info');
const $zoomSlider = $('#zoom-slider');
const $patchScaleBar = $('#patch-scale-bar');
const $patchScaleBarLine = $('#patch-scale-bar-line');
const $patchScaleBarLabel = $('#patch-scale-bar-label');
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

// Toolbar buttons
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
    if (_isLabelerRole() && ANNOTATION_PAGE_KIND === 'cell' && cellPatchWorkflow?.patchFocusActive) return true;
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
const $btnDrawPoint = $('#btn-draw-point');
const $btnCutPolygon = $('#btn-cut-polygon');
const $btnDrawRect1mm2 = $('#btn-draw-rect-1mm2');
const $btnDrawCircle1mm2 = $('#btn-draw-circle-1mm2');
const $btnRuler = $('#btn-ruler');
const $btnSlideMemo = $('#btn-slide-memo');

[$btnDrawPolygon, $btnDrawBrush, $btnDrawRect, $btnDrawPoint, $btnCutPolygon,
 $btnDrawRect1mm2, $btnDrawCircle1mm2, $btnRuler].forEach((el) => {
    if (el && !el.dataset.defaultTitle) el.dataset.defaultTitle = el.title || '';
});

if (ANNOTATION_PAGE_KIND === 'cell') {
    [$btnDrawPoint, $btnCutPolygon].forEach((el) => {
        if (!el) return;
        el.hidden = true;
        el.disabled = true;
        el.style.display = 'none';
    });
}

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
const $btnVsPanelMinimize = $('#btn-vs-panel-minimize');
const $aiAnalysisGroup = document.querySelector('.ai-analysis-group');
let _vsRunning = false;
let _vsLastTargetMpp = 2.0;

const $slideList = $('#slide-list');
const $annotationStatusSelect = $('#annotation-status-select');
const $annotationStatusWorkflow = $('#annotation-status-workflow');
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

let currentSlideId = null;
let currentSlideInfo = null;
let currentSlideFilename = '';
let currentSlideMemo = '';
let currentSlideMemoHistory = [];
let currentAnnotationStatus = '';
let _annotationStatusSaving = false;
let _annotationRunningStep = '';
let _annotationWorkflowFinished = false;
let cellPatchWorkflow = null;
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

const ANNOTATION_WORKFLOW_ORDER = ['annotation', 'review', 'termination'];

function _normalizeAnnotationWorkflowStatus(status) {
    const strStatus = status || '';
    if (strStatus === 'review' || strStatus === 'done') return 'review';
    if (strStatus === 'termination' || strStatus === 'termination_in_progress' || strStatus === 'flagged') return 'termination';
    return 'annotation';
}

function _annotationWorkflowStorageStatus(status) {
    const strStatus = _normalizeAnnotationWorkflowStatus(status);
    if (strStatus === 'review') return 'done';
    if (strStatus === 'termination') return 'flagged';
    return 'pending';
}

function _annotationWorkflowRunningStorageStatus(status) {
    const strStatus = _normalizeAnnotationWorkflowStatus(status);
    if (strStatus === 'review') return 'review';
    if (strStatus === 'termination') return 'termination_in_progress';
    return 'in_progress';
}

function _annotationWorkflowCompleteStorageStatus(status) {
    const strStatus = _normalizeAnnotationWorkflowStatus(status);
    if (strStatus === 'review') return 'flagged';
    if (strStatus === 'termination') return 'termination';
    return 'done';
}

function _browseAnnotationStatus(slide) {
    if (!slide) return '';
    if (ANNOTATION_PAGE_KIND === 'cell') {
        return slide.cell_annotation_status || '';
    }
    return slide.tissue_annotation_status || slide.annotation_status || slide.status || '';
}

async function _saveAnnotationWorkflowStorageStatus(filename, status) {
    try {
        await api.setFileStatus([filename], status, currentBrowsePath, ANNOTATION_STATUS_SCOPE);
    } catch (err) {
        if (status === 'termination') {
            await api.setFileStatus([filename], 'flagged', currentBrowsePath, ANNOTATION_STATUS_SCOPE);
            return;
        }
        throw err;
    }
}

function _annotationWorkflowMeta(status) {
    const strStatus = _normalizeAnnotationWorkflowStatus(status);
    return {
        annotation: { label: 'A', color: '#f4b400', title: 'Annotation' },
        review: { label: 'R', color: '#2ecc71', title: 'Review' },
        termination: { label: 'T', color: '#6c5ce7', title: 'Termination' },
    }[strStatus];
}

function _annotationWorkflowIndex(status) {
    return ANNOTATION_WORKFLOW_ORDER.indexOf(_normalizeAnnotationWorkflowStatus(status));
}

function _annotationWorkflowRawStatus(status) {
    return String(status || '').toLowerCase();
}

function _annotationWorkflowRunningStep(status) {
    const strRawStatus = _annotationWorkflowRawStatus(status);
    if (strRawStatus === 'in_progress') return 'annotation';
    if (strRawStatus === 'review') return 'review';
    if (strRawStatus === 'termination_in_progress') return 'termination';
    return '';
}

function _annotationWorkflowStepState(status, step) {
    const strRawStatus = _annotationWorkflowRawStatus(status);
    if (_annotationWorkflowRunningStep(status) === step) return 'running';
    const intCurrent = _annotationWorkflowIndex(status);
    const intStep = _annotationWorkflowIndex(step);
    if (step === 'termination' && strRawStatus === 'termination') return 'complete';
    if (intStep < intCurrent) return 'complete';
    if (intStep === intCurrent) return 'active';
    return 'pending';
}

function _annotationWorkflowStepSymbol(state) {
    if (state === 'rejected') return 'X';
    if (state === 'complete') return '\u2713';
    if (state === 'running') return '...';
    if (state === 'active') return '\u25b6';
    return '-';
}

function _annotationWorkflowActionState(boolComplete, boolRunning, boolActive) {
    if (boolComplete) return 'done';
    if (boolRunning) return 'running';
    if (boolActive) return 'current';
    return 'pending';
}

function _annotationWorkflowActionLabel(state) {
    if (state === 'done') return 'Done';
    if (state === 'running') return 'Running';
    if (state === 'current') return 'Current';
    return 'Pending';
}

function _nextAnnotationWorkflowStatus(status) {
    const int_current = _annotationWorkflowIndex(status);
    return ANNOTATION_WORKFLOW_ORDER[Math.min(int_current + 1, ANNOTATION_WORKFLOW_ORDER.length - 1)];
}

// Viewer initialization.
const ViewerClass = ANNOTATION_PAGE_KIND === 'cell'
    ? CellAnnotationViewer
    : TissueAnnotationViewer;
const viewer = new ViewerClass($canvas, $overlay);

function _updateAiAssistanceToolbarStatus(payload = {}) {
    if (!$aiAssistanceToolbarStatus) return;
    const state = String(payload.state || 'idle');
    if (state === 'idle') {
        $aiAssistanceToolbarStatus.hidden = true;
        return;
    }
    const percent = Math.max(0, Math.min(100, Number(payload.percent) || 0));
    const label = String(payload.label || (state === 'ready'
        ? 'AI assistance ready'
        : state === 'running' ? 'AI assistance' : state === 'disabled'
            ? 'AI assistance disabled' : 'AI assistance failed'));
    $aiAssistanceToolbarStatus.hidden = false;
    $aiAssistanceToolbarStatus.classList.toggle('is-ready', state === 'ready');
    $aiAssistanceToolbarStatus.classList.toggle('is-error', state === 'error');
    $aiAssistanceToolbarStatus.classList.toggle('is-disabled', state === 'disabled');
    $aiAssistanceToolbarLabel.textContent = label;
    $aiAssistanceToolbarPercent.textContent = state === 'running' ? `${Math.round(percent)}%` : '';
    $aiAssistanceToolbarFill.style.width = `${Math.round(percent)}%`;
    $aiAssistanceToolbarStatus.title = payload.detail ? `${label}: ${payload.detail}` : label;
}

function _updatePatchAiAssistanceToolbarStatus(payload = {}) {
    if (payload.state === 'idle' && cellPatchWorkflow?.assistanceReady) {
        _updateAiAssistanceToolbarStatus({ state: 'ready', label: 'AI assistance ready', percent: 100 });
        return;
    }
    _updateAiAssistanceToolbarStatus(payload);
}

cellPatchWorkflow = ANNOTATION_PAGE_KIND === 'cell'
    ? new CellPatchWorkflow({
        api,
        viewer,
        canvas: $canvas,
        setStatus,
        onAssistanceStatusChange: _updateAiAssistanceToolbarStatus,
        onPatchAssistanceStatusChange: _updatePatchAiAssistanceToolbarStatus,
        onRequiredRegionSaved: () => _markAnnotationWorkflowInProgressIfIdle(),
        onWorkflowSummaryChange: ({ slideId, summaries }) => {
            _renderCellPatchWorkflowCellsForSlide(slideId, summaries);
            _setCellPatchProjectSummary(slideId, summaries);
        },
    })
    : null;

function _niceScaleLength(rawLength) {
    if (!Number.isFinite(rawLength) || rawLength <= 0) return 1;
    const exponent = Math.floor(Math.log10(rawLength));
    const magnitude = 10 ** exponent;
    const normalized = rawLength / magnitude;
    const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return factor * magnitude;
}

function _formatScaleLength(lengthUm) {
    if (lengthUm >= 1000) {
        const mm = lengthUm / 1000;
        return `${mm >= 10 ? mm.toFixed(0) : mm.toFixed(1).replace(/\.0$/, '')} mm`;
    }
    return `${lengthUm >= 10 ? lengthUm.toFixed(0) : lengthUm.toFixed(1).replace(/\.0$/, '')} μm`;
}

function _updatePatchScaleBar(zoom, mpp) {
    if (!$patchScaleBar || !$patchScaleBarLine || !$patchScaleBarLabel) return;
    if (ANNOTATION_PAGE_KIND !== 'cell' || !cellPatchWorkflow?.patchFocusActive ||
            !Number.isFinite(zoom) || zoom <= 0 || !Number.isFinite(mpp) || mpp <= 0) {
        $patchScaleBar.hidden = true;
        return;
    }

    // mpp is the effective micrometers-per-screen-pixel value reported by the viewer.
    const screenPixelsPerMicrometer = 1 / mpp;
    const targetScreenPixels = 110;
    const scaleLengthUm = _niceScaleLength(targetScreenPixels / screenPixelsPerMicrometer);
    const screenWidth = Math.max(36, Math.round(scaleLengthUm * screenPixelsPerMicrometer));
    $patchScaleBarLine.style.width = `${screenWidth}px`;
    $patchScaleBarLabel.textContent = _formatScaleLength(scaleLengthUm);
    $patchScaleBar.setAttribute('aria-label', `Scale bar: ${_formatScaleLength(scaleLengthUm)}`);
    $patchScaleBar.hidden = false;
}

viewer.onZoomChange = (zoom, mag, mpp) => {
    const zoomText = `${mag.toFixed(1)}x  |  MPP ${mpp.toFixed(3)} μm/px`;
    $zoomInfo.textContent = zoomText;
    if ($patchZoomInfo) $patchZoomInfo.textContent = zoomText;
    if ($zoomSlider) {
        const minZoom = Math.max(Number(viewer.minZoom) || 0.000001, 0.000001);
        const maxZoom = Math.max(minZoom, Number(viewer.maxZoom) || minZoom);
        const span = Math.log(maxZoom / minZoom);
        const ratio = span > 0 ? Math.log(Math.max(minZoom, zoom) / minZoom) / span : 0;
        $zoomSlider.value = String(Math.round(Math.max(0, Math.min(1, ratio)) * 1000));
        $zoomSlider.setAttribute('aria-valuetext', `${mag.toFixed(1)}x, ${mpp.toFixed(3)} micrometers per pixel`);
    }
    _updatePatchScaleBar(zoom, mpp);
};
viewer.onViewChange = () => updateMinimap();

function _setPatchZoomSliderVisible(visible) {
    const isVisible = ANNOTATION_PAGE_KIND === 'cell' && Boolean(visible);
    if ($patchZoomControl) $patchZoomControl.hidden = !isVisible;
    if ($zoomInfo) $zoomInfo.hidden = isVisible;
    if ($patchScaleBar) $patchScaleBar.hidden = !isVisible;
}

function _zoomFromSliderValue(value) {
    const minZoom = Math.max(Number(viewer.minZoom) || 0.000001, 0.000001);
    const maxZoom = Math.max(minZoom, Number(viewer.maxZoom) || minZoom);
    const ratio = Math.max(0, Math.min(1, Number(value) / 1000));
    const span = Math.log(maxZoom / minZoom);
    return span > 0 ? minZoom * Math.exp(span * ratio) : minZoom;
}

$zoomSlider?.addEventListener('input', (event) => {
    if (ANNOTATION_PAGE_KIND !== 'cell' || !cellPatchWorkflow?.patchFocusActive) return;
    viewer.setZoom(_zoomFromSliderValue(event.target.value));
});

_setPatchZoomSliderVisible(false);
window.addEventListener('cellpatch:viewchange', (event) => {
    const isPatchView = Boolean(event.detail?.patchFocusActive);
    _setPatchZoomSliderVisible(isPatchView);
    if (isPatchView) _updatePatchScaleBar(viewer.zoom, viewer.getEffectiveMpp?.());
});

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
    });
}

function _activateAiTab(str_tab_id) {
    const btn = document.querySelector(`.tab-btn[data-tab="${str_tab_id}"]`);
    const content = document.getElementById(str_tab_id);
    if (!btn || !content || btn.disabled) return;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    content.classList.add('active');
}

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        _activateAiTab(btn.dataset.tab);
    });
});

if (_isAnnotationPage()) {
    _activateAiTab('vs-tab');
}

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

const SLIDE_EXT_PATTERN = /\.(isyntax|i2syntax|svs|ndpi|tif|tiff|mrxs|vms|vmu|scn)$/i;

async function uploadFiles(fileList, _targetPath) {
    const files = [...fileList].filter(f => SLIDE_EXT_PATTERN.test(f.name));
    if (!files.length) {
        setStatus('No supported slide files selected.');
        return;
    }
    openUploadPopup(fileList, _targetPath || currentBrowsePath);
}


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
    currentSlideFilename = currentSlideInfo.filename;
    currentSlideMemo = '';
    currentSlideMemoHistory = [];
    currentAnnotationStatus = _findSlideListStatus(currentSlideFilename);
    _annotationRunningStep = _annotationWorkflowRunningStep(currentAnnotationStatus);
    _annotationWorkflowFinished = _annotationWorkflowRawStatus(currentAnnotationStatus) === 'termination';
    _syncAnnotationStatusControl(currentAnnotationStatus);

    _stickyAddClassId = null;
    _hideStickyHud();

    $slideName.textContent = filename;
    _updateScannerBadge(slideInfo);
    _updateNdpColorToggleVisibility(slideInfo);
    setStatus(`Loaded: ${slideInfo.dimensions[0]}x${slideInfo.dimensions[1]} (${slideInfo.level_count} levels)`);

    $btnDetect.disabled = false;
    $btnVsMembrane.disabled = false;
    if ($btnPdScore) $btnPdScore.disabled = false;
    if ($btnIhcHer2) $btnIhcHer2.disabled = false;
    if ($btnIhcErPr) $btnIhcErPr.disabled = false;
    if ($btnIhcKi67) $btnIhcKi67.disabled = false;
    $btnInfo.disabled = false;
    if ($btnSlideMemo) {
        $btnSlideMemo.disabled = _isViewerRole();
        $btnSlideMemo.classList.remove('has-memo', 'has-history');
    }
    document.querySelectorAll('.toggle-btn').forEach(b => b.disabled = false);
    document.querySelectorAll('input[name="tissue-type"], input[name="pd-tissue-type"]').forEach(el => {
        el.disabled = false;
    });

    if (!_isViewerRole() && !_isAnnotationPage()) {
        _applyFolderAiRestrictions(currentBrowsePath);
    }

    viewer.canEditDetectionResults = _canEditAiDetections();
    viewer.cellAnnotationForceTumorBbox = _isPdL1StCellAnnotationProject();
    if (_isViewerRole()) {
        _applyViewerRoleRestrictions();
    }
    if (_isLabelerRole()) {
        _applyLabelerRoleRestrictions();
    }
    _syncCellPatchAnnotationTools();

    viewer.loadSlide(slideId, currentSlideInfo);

    if ($mousePosOverlay) $mousePosOverlay.hidden = false;

    // Minimap
    loadMinimap(slideId);

    // Reset results.
    clearResults();

    viewer.clearVirtualStainOverlay();
    _setVsToggleState(false, true);
    _setVsSplitState(false, true);

    _loadSavedAnnotationsForSlide(slideId);
    if (cellPatchWorkflow) {
        cellPatchWorkflow.load(slideId).catch((err) => {
            setStatus(`Cell patch workflow failed: ${err.message}`);
        });
    }

    setProgress(0);
}

function _findSlideListStatus(filename) {
    if (!filename || !$slideList) return '';
    const items = $slideList.querySelectorAll('.slide-list-item:not(.folder-item)');
    for (const item of items) {
        if (item.dataset.filename === filename) return item.dataset.status || '';
    }
    return '';
}

function _appendAnnotationSlideListHeader() {
    if (!$slideList || !_isAnnotationPage()) return;
    const header = document.createElement('div');
    header.className = 'slide-list-table-header';
    ['', 'Name', 'Anno.', 'Rev.', 'Term.'].forEach((label) => {
        const cell = document.createElement('span');
        cell.textContent = label;
        if (!label) cell.setAttribute('aria-hidden', 'true');
        header.appendChild(cell);
    });
    $slideList.appendChild(header);
}

function _renderAnnotationWorkflowCells(item, status) {
    if (!item) return;
    item.querySelectorAll('.slide-workflow-cell').forEach(el => el.remove());
    const listSteps = [
        ['annotation', 'Annotation'],
        ['review', 'Review'],
        ['termination', 'Termination'],
    ];
    for (const [step, label] of listSteps) {
        const state = _annotationWorkflowStepState(status, step);
        const cell = document.createElement('span');
        cell.className = `slide-workflow-cell is-${state}`;
        cell.dataset.workflowStep = step;
        cell.textContent = _annotationWorkflowStepSymbol(state);
        cell.title = `${label}: ${state}`;
        item.appendChild(cell);
    }
}

function _syncAnnotationStatusControl(status = currentAnnotationStatus) {
    const strStatus = _normalizeAnnotationWorkflowStatus(status);
    const boolDisabled = !currentSlideFilename || _isViewerRole() || _annotationStatusSaving;
    const boolLabeler = _isLabelerRole();
    const boolLabelerCellWsiLocked = boolLabeler && ANNOTATION_PAGE_KIND === 'cell' && !cellPatchWorkflow?.patchFocusActive;
    const boolLabelerWorkflowLocked = boolLabeler && (
        _annotationRunningStep === 'review' ||
        _annotationRunningStep === 'termination' ||
        strStatus === 'review' ||
        strStatus === 'termination' ||
        _annotationWorkflowFinished
    );
    if ($annotationStatusSelect) {
        $annotationStatusSelect.value = SLIDE_STATUS_OPTIONS.some(opt => opt.value === strStatus)
            ? strStatus
            : 'annotation';
        $annotationStatusSelect.disabled = boolDisabled || boolLabeler;
    }
    if ($annotationStatusWorkflow) {
        const intCurrent = _annotationWorkflowIndex(strStatus);
        $annotationStatusWorkflow.dataset.status = strStatus;
        $annotationStatusWorkflow.classList.toggle('is-disabled', boolDisabled || boolLabelerCellWsiLocked);
        $annotationStatusWorkflow.classList.toggle('is-running', !!_annotationRunningStep);
        $annotationStatusWorkflow.querySelectorAll('[data-annotation-status]').forEach((btn) => {
            const strTarget = _normalizeAnnotationWorkflowStatus(btn.dataset.annotationStatus);
            const intTarget = _annotationWorkflowIndex(strTarget);
            const boolComplete = intTarget < intCurrent || (_annotationWorkflowFinished && strTarget === 'termination');
            const boolActive = strTarget === strStatus && !_annotationWorkflowFinished;
            const boolRunning = _annotationRunningStep === strTarget;
            const strLabel = SLIDE_STATUS_OPTIONS.find(opt => opt.value === strTarget)?.label || strTarget;
            const strActionState = _annotationWorkflowActionState(boolComplete, boolRunning, boolActive);
            btn.innerHTML = `<span class="annotation-step-label">${strLabel}</span>`;
            let stateIcon = btn.nextElementSibling;
            if (!stateIcon || !stateIcon.classList.contains('annotation-step-state')) {
                stateIcon = document.createElement('span');
                stateIcon.className = 'annotation-step-state';
                btn.insertAdjacentElement('afterend', stateIcon);
            }
            stateIcon.className = `annotation-step-state annotation-step-icon is-${strActionState}`;
            stateIcon.dataset.workflowStateFor = strTarget;
            stateIcon.setAttribute('aria-label', _annotationWorkflowActionLabel(strActionState));
            stateIcon.title = _annotationWorkflowActionLabel(strActionState);
            btn.classList.toggle('is-active', boolActive);
            btn.classList.toggle('is-complete', boolComplete);
            btn.classList.toggle('is-running', boolRunning);
            btn.dataset.actionState = strActionState;
            const boolLabelerBlocked = boolLabeler && (
                boolLabelerCellWsiLocked ||
                strTarget !== 'annotation' ||
                boolLabelerWorkflowLocked
            );
            btn.disabled = boolDisabled || boolLabelerBlocked;
            btn.title = boolActive
                ? (boolRunning ? `${strLabel} complete` : `${strLabel} start`)
                : `Move to ${strLabel}`;
        });
        $annotationStatusWorkflow.querySelectorAll('[data-connector]').forEach((el) => {
            el.hidden = true;
            el.textContent = '';
        });
    }
    cellPatchWorkflow?.syncAnnotationStatusPanel?.();
}

function _setSlideListItemAnnotationStatus(filename, status) {
    if (!filename || !$slideList) return;
    const items = $slideList.querySelectorAll('.slide-list-item:not(.folder-item)');
    for (const item of items) {
        if (item.dataset.filename !== filename) continue;
        ['pending', 'in_progress', 'done', 'flagged', 'annotation', 'review', 'termination_in_progress', 'termination'].forEach(value => {
            item.classList.remove(`status-${value}`);
        });
        const strRawStatus = status || 'annotation';
        const strStatus = _normalizeAnnotationWorkflowStatus(strRawStatus);
        item.dataset.status = strRawStatus;
        item.dataset.workflowStatus = strStatus;
        item.querySelectorAll('.slide-status-dot').forEach(el => el.remove());
        item.classList.add(`status-${strStatus}`);
        _renderAnnotationWorkflowCells(item, strRawStatus);
        break;
    }
}

// Folder auto-AI restrictions
// Minimap.

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
    document.querySelectorAll('.tab-btn[data-tab], .tab-content').forEach(el => {
        el.style.display = '';
    });
    if (!document.querySelector('.tab-btn.active[data-tab]')) {
        const el_btn = document.querySelector('.tab-btn[data-tab="hne-tab"]');
        const el_content = document.getElementById('hne-tab');
        if (el_btn) el_btn.classList.add('active');
        if (el_content) el_content.classList.add('active');
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

    const list_draw_btns = ['btn-draw-polygon', 'btn-draw-brush', 'btn-draw-rect', 'btn-draw-point', 'btn-cut-polygon',
                            'btn-draw-rect-1mm2', 'btn-draw-circle-1mm2', 'btn-ruler'];
    list_draw_btns.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.classList.remove('active');
            el.title = 'Viewer role cannot use annotation features.';
        }
    });
    // Turn off drawing mode if it was active.
    if (viewer && viewer.drawMode) viewer.setDrawMode(null);

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

    document.querySelectorAll(
        '#right-panel .panel-group:first-child input, #right-panel .panel-group:first-child button:not(.panel-minimize-btn)'
    ).forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer role cannot use AI analysis features.';
    });

    ['btn-ann-clear', 'btn-ann-save',
     'btn-slide-memo',
     'btn-new-project', 'btn-rename-project', 'btn-delete-project'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = 'Viewer role cannot use annotation features.';
        }
    });

    document.querySelectorAll([
        '.annotation-group button:not(.panel-minimize-btn)',
        '.annotation-group input',
        '.annotation-group select',
        '.cell-classes-panel button:not(.panel-minimize-btn)',
        '.cell-classes-panel input',
        '.cell-classes-panel select',
        '.cell-annotations-panel button:not(.panel-minimize-btn)',
        '.cell-annotations-panel input',
        '.cell-annotations-panel select',
        '.cell-display-section button:not(.panel-minimize-btn)',
        '.cell-display-section input',
        '.cell-display-section select',
        '.cell-patch-list-section button:not(.panel-minimize-btn)',
        '.cell-patch-list-section input',
        '.cell-patch-list-section select',
    ].join(',')).forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer role cannot use annotation features.';
    });
}

function _cellPatchSlideListState(summary) {
    const state = summary?.state || 'before';
    if (state === 'rejected') return 'rejected';
    if (state === 'completed') return 'complete';
    if (state === 'running') return 'running';
    return 'pending';
}

function _emptyCellPatchWorkflowSummaries() {
    const zero = { state: 'before', percent: 0, completed: 0, total: 0, rejected: 0 };
    return {
        annotation: { ...zero },
        review: { ...zero },
        termination: { ...zero },
    };
}

const _cellPatchProjectSummaries = new Map();

function _renderCellPatchProjectProgress() {
    if (!$breadcrumb) return;
    $breadcrumb.querySelector('.cell-project-termination-progress')?.remove();
    if (ANNOTATION_PAGE_KIND !== 'cell' || !_getCurrentProjectName()) return;
    let completed = 0;
    let total = 0;
    for (const summaries of _cellPatchProjectSummaries.values()) {
        const termination = summaries?.termination || {};
        completed += Number(termination.completed || 0);
        total += Number(termination.total || 0);
    }
    const progress = document.createElement('span');
    progress.className = 'cell-project-termination-progress';
    progress.textContent = `Termination ${completed.toLocaleString()}/${total.toLocaleString()}`;
    progress.title = `Termination completed patches: ${completed.toLocaleString()} of ${total.toLocaleString()}`;
    progress.setAttribute('aria-label', progress.title);
    $breadcrumb.appendChild(progress);
}

function _setCellPatchProjectSummary(slideId, summaries, { render = true } = {}) {
    if (ANNOTATION_PAGE_KIND !== 'cell' || !slideId || !summaries) return;
    _cellPatchProjectSummaries.set(String(slideId), summaries);
    if (render) _renderCellPatchProjectProgress();
}

function _renderCellPatchWorkflowCells(item, summaries) {
    if (!item || !summaries) return;
    item.querySelectorAll('.slide-workflow-cell').forEach(el => el.remove());
    const listSteps = [
        ['annotation', 'Annotation'],
        ['review', 'Review'],
        ['termination', 'Termination'],
    ];
    for (const [step, label] of listSteps) {
        const summary = summaries[step] || { state: 'before', percent: 0, completed: 0, total: 0 };
        const state = _cellPatchSlideListState(summary);
        const cell = document.createElement('span');
        cell.className = `slide-workflow-cell is-${state}`;
        cell.dataset.workflowStep = step;
        cell.dataset.cellPatchAuto = '1';
        cell.textContent = _annotationWorkflowStepSymbol(state);
        const rejectedText = summary.rejected ? ` / rejected ${summary.rejected}` : '';
        cell.title = `${label}: ${summary.percent || 0}% (${summary.completed || 0}/${summary.total || 0}${rejectedText})`;
        item.appendChild(cell);
    }
}

function _renderCellPatchWorkflowCellsForSlide(slideId, summaries) {
    if (ANNOTATION_PAGE_KIND !== 'cell' || !slideId || !$slideList || !summaries) return;
    const item = $slideList.querySelector(`.slide-list-item[data-slide-id="${CSS.escape(String(slideId))}"]`);
    if (item) _renderCellPatchWorkflowCells(item, summaries);
}

function _applyLabelerRoleRestrictions() {
    document.body.classList.add('role-labeler');
    if (viewer) viewer.canEditDetectionResults = _canEditAiDetections();
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
    if (ANNOTATION_PAGE_KIND === 'cell' && !cellPatchWorkflow?.patchFocusActive) {
        ['btn-draw-polygon', 'btn-draw-brush', 'btn-draw-rect', 'btn-draw-point', 'btn-cut-polygon',
         'btn-draw-rect-1mm2', 'btn-draw-circle-1mm2'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.disabled = true;
                el.classList.remove('active');
                el.title = 'Labeler role cannot change WSI-level cell annotation setup.';
            }
        });
        if (viewer && viewer.drawMode) viewer.setDrawMode(null);
    }
}

const $viewerContainer = $('#viewer-container');

function _isFileDrag(e) {
    const t = e.dataTransfer && e.dataTransfer.types;
    if (!t) return false;
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

// Minimap
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
    // Minimize: minus icon, expand: plus icon.
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

// View controls
$btnZoomIn.addEventListener('click', () => viewer.zoomIn());
$btnZoomOut.addEventListener('click', () => viewer.zoomOut());
$btnFit.addEventListener('click', () => viewer.fitToWindow());

const drawButtons = {
    polygon: $btnDrawPolygon,
    brush: $btnDrawBrush,
    rectangle: $btnDrawRect,
    point: $btnDrawPoint,
    cut: $btnCutPolygon,
    'rect-1mm2': $btnDrawRect1mm2,
    'circle-1mm2': $btnDrawCircle1mm2,
    ruler: $btnRuler,
};

const CELL_PATCH_HIDDEN_TOOLS = [
    $btnDrawPolygon,
    $btnDrawBrush,
    $btnDrawRect1mm2,
    $btnDrawCircle1mm2,
];

function _setToolHidden(button, hidden) {
    if (!button) return;
    button.hidden = Boolean(hidden);
    button.style.display = hidden ? 'none' : '';
}

function _syncCellPatchAnnotationTools() {
    if (ANNOTATION_PAGE_KIND !== 'cell') return;
    const boolPatchView = Boolean(cellPatchWorkflow?.patchFocusActive);
    const boolCanAnnotatePatch = Boolean(cellPatchWorkflow?.canAnnotateSelectedPatch?.());
    const boolNoSlide = !currentSlideFilename;
    const boolViewer = _isViewerRole();
    const boolLabelerWsiLocked = _isLabelerRole() && !boolPatchView;
    [$btnDrawPoint, $btnCutPolygon].forEach((button) => {
        _setToolHidden(button, true);
        if (button) button.disabled = true;
    });
    if (boolPatchView) {
        CELL_PATCH_HIDDEN_TOOLS.forEach((button) => {
            _setToolHidden(button, true);
            if (!button) return;
            button.disabled = true;
            button.classList.remove('active');
        });
        _setToolHidden($btnDrawRect, false);
        if ($btnDrawRect) {
            $btnDrawRect.disabled = boolViewer || !boolCanAnnotatePatch;
            $btnDrawRect.title = boolCanAnnotatePatch
                ? 'Draw Rectangle'
                : 'Patch annotation is locked for the current role and workflow state.';
            if ($btnDrawRect.disabled) $btnDrawRect.classList.remove('active');
        }
        _setToolHidden($btnRuler, false);
        if ($btnRuler) {
            $btnRuler.disabled = boolNoSlide || boolViewer;
            $btnRuler.title = $btnRuler.dataset.defaultTitle;
            if ($btnRuler.disabled) $btnRuler.classList.remove('active');
        }
        const boolPatchDrawModeAllowed = viewer?.drawMode === 'ruler'
            ? !boolNoSlide && !boolViewer
            : viewer?.drawMode === 'rectangle' && boolCanAnnotatePatch && !boolViewer;
        if (viewer?.drawMode && !boolPatchDrawModeAllowed) {
            viewer.setDrawMode(null);
            Object.values(drawButtons).forEach(button => button?.classList.remove('active'));
        }
        return;
    }
    [...CELL_PATCH_HIDDEN_TOOLS, $btnDrawRect].forEach((button) => {
        _setToolHidden(button, false);
        if (!button) return;
        button.disabled = boolNoSlide || boolViewer || boolLabelerWsiLocked;
        if (boolLabelerWsiLocked) {
            button.title = 'Labeler role cannot change WSI-level cell annotation setup.';
        } else {
            button.title = button.dataset.defaultTitle;
        }
        if (button.disabled) button.classList.remove('active');
    });
    if (viewer?.drawMode && (boolViewer || boolLabelerWsiLocked)) {
        viewer.setDrawMode(null);
        Object.values(drawButtons).forEach(button => button?.classList.remove('active'));
    }
}

function setDrawMode(mode) {
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    if (ANNOTATION_PAGE_KIND === 'cell' && cellPatchWorkflow?.patchFocusActive) {
        const boolCanAnnotatePatch = Boolean(cellPatchWorkflow.canAnnotateSelectedPatch?.());
        if (mode !== 'rectangle' && mode !== 'ruler') {
            _syncCellPatchAnnotationTools();
            setStatus('Cell Annotation patch view supports rectangle annotations and ruler measurements only.');
            return;
        }
        if (mode === 'rectangle' && !boolCanAnnotatePatch) {
            _syncCellPatchAnnotationTools();
            setStatus('Patch annotation is locked for the current role and workflow state.');
            return;
        }
    }
    const newMode = viewer.drawMode === mode ? null : mode;
    viewer.setDrawMode(newMode);
    Object.values(drawButtons).forEach(b => { if (b) b.classList.remove('active'); });
    if (newMode && drawButtons[newMode]) drawButtons[newMode].classList.add('active');
    if (newMode === 'cut') {
        setStatus('Cut: select a polygon, then drag a stroke across its boundary');
    } else if (newMode === 'brush') {
        setStatus('Brush: drag to paint a polygon. Alt + wheel changes brush size');
    }
}

$btnDrawPolygon.addEventListener('click', () => setDrawMode('polygon'));
if ($btnDrawBrush) $btnDrawBrush.addEventListener('click', () => setDrawMode('brush'));
$btnDrawRect.addEventListener('click', () => setDrawMode('rectangle'));
if ($btnDrawPoint) $btnDrawPoint.addEventListener('click', () => setDrawMode('point'));
if ($btnCutPolygon) $btnCutPolygon.addEventListener('click', () => setDrawMode('cut'));
if (ANNOTATION_PAGE_KIND !== 'cell') {
    bindFixedAreaTools(viewer, $btnDrawRect1mm2, $btnDrawCircle1mm2, setDrawMode);
} else {
    if ($btnDrawRect1mm2) $btnDrawRect1mm2.addEventListener('click', () => setDrawMode('rect-1mm2'));
if ($btnDrawCircle1mm2) $btnDrawCircle1mm2.addEventListener('click', () => setDrawMode('circle-1mm2'));
}
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

viewer.onDrawModeChange = (mode) => {
    Object.values(drawButtons).forEach(b => { if (b) b.classList.remove('active'); });
    if (mode && drawButtons[mode]) drawButtons[mode].classList.add('active');
};

// Annotation panel.
const $annList = $('#annotation-list');
const $annStylePanel = $('#annotation-style-panel');
const $annStyleControls = $annStylePanel?.querySelector('.annotation-style-controls');
const $annStyleEmpty = $annStylePanel?.querySelector('.annotation-style-empty');
const $annStrokeWidth = $('#ann-stroke-width');
const $annStrokeWidthValue = $('#ann-stroke-width-value');
const $annFillOpacity = $('#ann-fill-opacity');
const $annFillOpacityValue = $('#ann-fill-opacity-value');
const $btnAnnClear = $('#btn-ann-clear');
const $btnAnnSave = $('#btn-ann-save');
const $btnAnnLoad = $('#btn-ann-load');
const $classList = $('#annotation-class-list');
const $btnClassAdd = $('#btn-class-add');
const $btnClassApply = $('#btn-class-apply');
const $btnClassSetting = $('#btn-class-setting');
const $btnClassDone = $('#btn-class-done');
const $btnClassVisibilityAll = $('#btn-class-visibility-all');

const _DEFAULT_ANNOTATION_CLASSES = [
    { id: 'default', name: 'Default', color: [0, 255, 0] },
];
let _annotationClasses = _DEFAULT_ANNOTATION_CLASSES.map(c => ({ ...c, color: [...c.color] }));
let _activeAnnotationClassId = 'default';
let _classesLoadedForProject = null;
let _classSaveTimer = null;
let _draggingClassId = null;
let _annotationDisplayStyle = { strokeWidth: 2, fillOpacity: 0.1 };
let _classManagementMode = 'apply';
let _hiddenAnnotationClassIds = new Set();
let _annotationListSort = { key: 'id', dir: 'asc' };
let _annotationBulkSelection = new Set();
let _annotationPanelRenderLimit = 300;

function _canManageAnnotationClasses() {
    return window.__currentUserRole === 'doctor' || window.__currentUserRole === 'admin';
}

function _isYoungSeopLeeAccount() {
    return [window.__currentUserLoginId, window.__currentUserName]
        .map(value => String(value || '').trim().toLowerCase())
        .includes('youngseoplee');
}

function _blockClassManageAction() {
    if (_canManageAnnotationClasses()) return false;
    alert('Class management is available to doctor/admin only.');
    return true;
}

function _getAnnotationClass(classId) {
    return _annotationClasses.find(c => c.id === classId) || _annotationClasses[0] || _DEFAULT_ANNOTATION_CLASSES[0];
}

function _annotationClassMetadata(ann) {
    const classId = String(ann?.class_id || ann?.properties?.class_id || '');
    const configured = _annotationClasses.find(cls => cls.id === classId);
    if (configured) return configured;
    return {
        id: classId,
        name: String(ann?.class_name || ann?.properties?.class_name || classId || 'Unknown'),
        color: _normalizeColor(ann?.color),
    };
}

function _syncActiveAnnotationClassToViewer() {
    if (ANNOTATION_PAGE_KIND === 'cell' && cellPatchWorkflow && !cellPatchWorkflow.patchFocusActive) {
        cellPatchWorkflow.syncWsiDrawColor?.();
        return;
    }
    const cls = _getAnnotationClass(_activeAnnotationClassId);
    if (cls) viewer.setAnnotationDrawColor?.(cls.color);
}

window.addEventListener('cellpatch:viewchange', () => {
    _syncAnnotationClassMetadata();
    _syncActiveAnnotationClassToViewer();
    _syncCellPatchAnnotationTools();
    if (cellPatchWorkflow?.patchFocusActive && !cellPatchWorkflow.canAnnotateSelectedPatch?.()) {
        _clearPatchCellBulkSelection({ render: false });
    }
    renderClassManagementPanel();
    renderAnnotationPanel();
});

window.addEventListener('cellpatch:annotationschange', (event) => {
    _mergeAnnotationClasses(event?.detail?.classes);
    renderAnnotationPanel();
});

function _syncHiddenAnnotationClassesToViewer() {
    const validIds = new Set(_annotationClasses.map(cls => cls.id));
    _hiddenAnnotationClassIds = new Set([..._hiddenAnnotationClassIds].filter(id => validIds.has(id)));
    viewer.setHiddenAnnotationClassIds?.([..._hiddenAnnotationClassIds]);
}

function _toggleAnnotationClassVisibility(classId) {
    if (_hiddenAnnotationClassIds.has(classId)) {
        _hiddenAnnotationClassIds.delete(classId);
    } else {
        _hiddenAnnotationClassIds.add(classId);
    }
    _syncHiddenAnnotationClassesToViewer();
    renderClassManagementPanel();
    renderAnnotationPanel();
}

function _toggleAllAnnotationClassVisibility() {
    const allHidden = _annotationClasses.length > 0 &&
        _annotationClasses.every(cls => _hiddenAnnotationClassIds.has(cls.id));
    _hiddenAnnotationClassIds = allHidden
        ? new Set()
        : new Set(_annotationClasses.map(cls => cls.id));
    _syncHiddenAnnotationClassesToViewer();
    renderClassManagementPanel();
    renderAnnotationPanel();
}

$btnClassVisibilityAll?.addEventListener('click', _toggleAllAnnotationClassVisibility);

// Cell Annotation Patch View keyboard shortcuts:
//   Ctrl/Cmd + 1~9/0 — toggle the corresponding class visibility
//   Ctrl/Cmd + `     — toggle visibility for all classes
// The numeric mapping follows the shortcut labels rendered beside each class
// (1-9, then 0 for the tenth class).
window.addEventListener('keydown', (event) => {
    if (ANNOTATION_PAGE_KIND !== 'cell' || !cellPatchWorkflow?.patchFocusActive) return;
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.repeat) return;

    const target = event.target;
    const tag = String(target?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return;

    const isBackquote = event.code === 'Backquote' || event.key === '`';
    if (isBackquote) {
        _toggleAllAnnotationClassVisibility();
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
    }

    const key = String(event.key || '');
    const digit = /^[0-9]$/.test(key) ? Number(key) : null;
    if (digit === null) return;
    const classIndex = digit === 0 ? 9 : digit - 1;
    const cls = _annotationClasses[classIndex];
    if (!cls) return;
    _toggleAnnotationClassVisibility(cls.id);
    event.preventDefault();
    event.stopImmediatePropagation();
}, true);

function _makeClassId(name) {
    const base = String(name || 'Class')
        .trim()
        .toLowerCase()
        .replace(/^_+|_+$/g, '') || 'class';
    let id = base;
    let i = 2;
    while (_annotationClasses.some(c => c.id === id)) {
        id = `${base}_${i++}`;
    }
    return id;
}

function _normalizeAnnotationClass(cls, idx = 1) {
    const name = String(cls?.name || `Class ${idx}`).trim().slice(0, 64) || `Class ${idx}`;
    return {
        id: String(cls?.id || _makeClassId(name)).trim() || _makeClassId(name),
        name,
        color: _normalizeColor(cls?.color),
    };
}

function _mergeAnnotationClasses(classes = []) {
    if (!Array.isArray(classes) || !classes.length) return false;
    const incoming = classes.map((cls, idx) => _normalizeAnnotationClass(cls, idx + 1));
    let changed = false;
    _annotationClasses = _annotationClasses.filter(cls => {
        const replacement = incoming.find(item => item.name.toLowerCase() === cls.name.toLowerCase() && item.id !== cls.id);
        if (replacement) {
            changed = true;
            return false;
        }
        return true;
    });
    const ids = new Set(_annotationClasses.map(cls => cls.id));
    for (const cls of incoming) {
        if (ids.has(cls.id)) continue;
        _annotationClasses.push(cls);
        ids.add(cls.id);
        changed = true;
    }
    if (!changed) return false;
    if (!_annotationClasses.some(cls => cls.id === _activeAnnotationClassId)) {
        _activeAnnotationClassId = _annotationClasses[0]?.id || 'default';
    }
    _hiddenAnnotationClassIds = new Set([..._hiddenAnnotationClassIds].filter(id => ids.has(id)));
    _syncAnnotationClassMetadata();
    renderClassManagementPanel();
    return true;
}

function _applyClassToAnnotation(ann, classId) {
    if (!ann) return;
    const cls = _getAnnotationClass(classId);
    ann.class_id = cls.id;
    ann.class_name = cls.name;
    ann.color = _normalizeColor(cls.color);
    ann.properties = {
        ...(ann.properties || {}),
        class_id: cls.id,
        class_name: cls.name,
    };
}

function _annotationStrokeWidth(value = _annotationDisplayStyle.strokeWidth) {
    const raw = Number(value);
    return Math.max(1, Math.min(12, Number.isFinite(raw) ? raw : 2));
}

function _annotationFillOpacity(value = _annotationDisplayStyle.fillOpacity) {
    const raw = Number(value);
    return Math.max(0, Math.min(0.8, Number.isFinite(raw) ? raw : 0.1));
}

function _applyAnnotationDisplayStyle(style = {}) {
    _annotationDisplayStyle = {
        strokeWidth: _annotationStrokeWidth(style.strokeWidth ?? style.stroke_width ?? _annotationDisplayStyle.strokeWidth),
        fillOpacity: _annotationFillOpacity(style.fillOpacity ?? style.fill_opacity ?? _annotationDisplayStyle.fillOpacity),
    };
    viewer.setAnnotationDisplayStyle?.(_annotationDisplayStyle);
    renderAnnotationStylePanel();
}

function renderAnnotationStylePanel() {
    if (!$annStylePanel || !$annStyleControls || !$annStyleEmpty) return;
    $annStyleControls.hidden = false;
    $annStyleEmpty.hidden = false;
    $annStyleEmpty.textContent = 'Applied to all annotations in this account.';
    const stroke = _annotationStrokeWidth();
    const opacity = _annotationFillOpacity();
    if ($annStrokeWidth) $annStrokeWidth.value = String(stroke);
    if ($annStrokeWidthValue) $annStrokeWidthValue.textContent = `${stroke} px`;
    if ($annFillOpacity) $annFillOpacity.value = String(Math.round(opacity * 100));
    if ($annFillOpacityValue) $annFillOpacityValue.textContent = `${Math.round(opacity * 100)}%`;
}

async function _saveAnnotationDisplayStyle() {
    const payload = {
        annotation_display: {
            stroke_width: _annotationDisplayStyle.strokeWidth,
            fill_opacity: _annotationDisplayStyle.fillOpacity,
        },
    };
    const res = await api.saveUserPreferences(payload);
    const userRaw = localStorage.getItem('user');
    let user = {};
    try { user = userRaw ? JSON.parse(userRaw) : {}; } catch { user = {}; }
    user.dict_preferences = res.dict_preferences || { ...(user.dict_preferences || {}), ...payload };
    localStorage.setItem('user', JSON.stringify(user));
}

function _updateAnnotationDisplayStyle(patch, persist = false) {
    _applyAnnotationDisplayStyle({
        strokeWidth: patch.stroke_width ?? patch.strokeWidth ?? _annotationDisplayStyle.strokeWidth,
        fillOpacity: patch.fill_opacity ?? patch.fillOpacity ?? _annotationDisplayStyle.fillOpacity,
    });
    if (persist) {
        _saveAnnotationDisplayStyle()
            .then(() => setStatus('Annotation display settings saved'))
            .catch(err => setStatus(`Failed to save annotation display settings: ${err.message}`));
    }
}

function _loadAnnotationDisplayStyleFromPreferences(preferences = {}) {
    const style = preferences.annotation_display || preferences.annotationDisplay || {};
    _applyAnnotationDisplayStyle({
        strokeWidth: style.stroke_width ?? style.strokeWidth ?? 2,
        fillOpacity: style.fill_opacity ?? style.fillOpacity ?? 0.1,
    });
}

function _syncAnnotationClassMetadata() {
    for (const ann of viewer.annotations || []) {
        const classId = String(ann.class_id || ann.properties?.class_id || '');
        const cls = _annotationClasses.find(item => item.id === classId);
        // Saved patch classes may outlive the project's current class configuration.
        // Keep their original id/name/color instead of silently moving them to Other.
        if (!cls) continue;
        ann.class_id = cls.id;
        ann.class_name = cls.name;
        ann.color = _normalizeColor(cls.color);
        ann.properties = {
            ...(ann.properties || {}),
            class_id: cls.id,
            class_name: cls.name,
        };
    }
    viewer.requestRender();
}

function _queueSaveAnnotationClasses() {
    if (_classSaveTimer) clearTimeout(_classSaveTimer);
    _classSaveTimer = setTimeout(async () => {
        const projectName = _getCurrentProjectName();
        if (!projectName) return;
        try {
            const res = ANNOTATION_PAGE_KIND === 'cell'
                ? await api.saveCellAnnotationClasses(projectName, _annotationClasses)
                : await api.saveAnnotationClasses(projectName, _annotationClasses);
            if (Array.isArray(res.classes)) {
                _annotationClasses = res.classes.map(_normalizeAnnotationClass);
            }
            setStatus(ANNOTATION_PAGE_KIND === 'cell' ? 'Cell annotation classes saved' : 'Annotation classes saved');
        } catch (err) {
            console.warn('Annotation class save failed:', err);
            setStatus(`Class save failed: ${err.message}`);
        }
        renderClassManagementPanel();
        renderAnnotationPanel();
    }, 500);
}

async function _loadAnnotationClassesForCurrentProject(force = false) {
    const projectName = _getCurrentProjectName();
    if (!projectName) {
        _classesLoadedForProject = null;
        _annotationClasses = _DEFAULT_ANNOTATION_CLASSES.map(c => ({ ...c, color: [...c.color] }));
        _activeAnnotationClassId = 'default';
        _syncActiveAnnotationClassToViewer();
        _syncHiddenAnnotationClassesToViewer();
        renderClassManagementPanel();
        renderAnnotationPanel();
        return;
    }
    if (!force && _classesLoadedForProject === projectName) return;
    _classesLoadedForProject = projectName;
    try {
        const res = ANNOTATION_PAGE_KIND === 'cell'
            ? await api.loadCellAnnotationClasses(projectName)
            : await api.loadAnnotationClasses(projectName);
        const list = Array.isArray(res.classes) ? res.classes : _DEFAULT_ANNOTATION_CLASSES;
        _annotationClasses = list.map((cls, idx) => _normalizeAnnotationClass(cls, idx + 1));
        if (!_annotationClasses.some(c => c.id === _activeAnnotationClassId)) {
            _activeAnnotationClassId = _annotationClasses[0]?.id || 'default';
        }
    } catch (err) {
        console.warn('Annotation class load failed:', err);
        _annotationClasses = _DEFAULT_ANNOTATION_CLASSES.map(c => ({ ...c, color: [...c.color] }));
        _activeAnnotationClassId = 'default';
        setStatus(`Class load failed: ${err.message}`);
    }
    _syncActiveAnnotationClassToViewer();
    _syncHiddenAnnotationClassesToViewer();
    _syncAnnotationClassMetadata();
    renderClassManagementPanel();
    renderAnnotationPanel();
}

function renderClassManagementPanel() {
    if (!$classList) return;
    const canManage = _canManageAnnotationClasses();
    const isSettings = canManage && _classManagementMode === 'settings';
    if (!canManage && _classManagementMode !== 'apply') _classManagementMode = 'apply';
    const isCellPatchView = Boolean(cellPatchWorkflow?.patchFocusActive);
    const allClassesHidden = _annotationClasses.length > 0 &&
        _annotationClasses.every(cls => _hiddenAnnotationClassIds.has(cls.id));
    const allClassesVisible = _annotationClasses.length > 0 &&
        _annotationClasses.every(cls => !_hiddenAnnotationClassIds.has(cls.id));
    const lockedCellClassIds = isSettings ? _lockedCellClassIdsForCurrentProject() : new Set();
    if ($btnClassVisibilityAll) {
        const actionLabel = allClassesHidden ? 'Show all classes' : 'Hide all classes';
        $btnClassVisibilityAll.hidden = !isCellPatchView;
        $btnClassVisibilityAll.disabled = !isCellPatchView || _annotationClasses.length === 0;
        $btnClassVisibilityAll.title = actionLabel + ' (Ctrl+`)';
        $btnClassVisibilityAll.setAttribute('aria-label', actionLabel);
        $btnClassVisibilityAll.setAttribute(
            'aria-pressed',
            allClassesVisible ? 'true' : allClassesHidden ? 'false' : 'mixed'
        );
        $btnClassVisibilityAll.innerHTML = _visibilityIcon(!allClassesHidden);
    }
    if ($btnClassApply) {
        $btnClassApply.hidden = isSettings || isCellPatchView;
        $btnClassApply.disabled = _isViewerRole();
        $btnClassApply.title = _isViewerRole() ? 'Viewer role can view annotations only' : 'Apply selected class to selected annotation';
    }
    if ($btnClassSetting) {
        $btnClassSetting.hidden = !canManage || isSettings;
        $btnClassSetting.disabled = !canManage;
        $btnClassSetting.title = canManage ? 'Edit classes' : 'Doctor/Admin only';
    }
    if ($btnClassAdd) {
        $btnClassAdd.hidden = !isSettings;
        $btnClassAdd.disabled = !isSettings;
        $btnClassAdd.title = canManage ? 'Add class' : 'Doctor/Admin only';
    }
    if ($btnClassDone) {
        $btnClassDone.hidden = !isSettings;
        $btnClassDone.disabled = !isSettings;
        $btnClassDone.title = 'Back to apply mode';
    }
    $classList.innerHTML = '';
    for (const cls of _annotationClasses) {
        const [r, g, b] = _normalizeColor(cls.color);
        const classHidden = _hiddenAnnotationClassIds.has(cls.id);
        const classIndex = _annotationClasses.indexOf(cls);
        const classShortcut = classIndex < 9 ? classIndex + 1 : classIndex === 9 ? 0 : null;
        const visibilityTitle = classHidden ? 'Show class' : 'Hide class';
        const visibilityShortcutTitle = classShortcut === null
            ? visibilityTitle
            : `${visibilityTitle} (Ctrl+${classShortcut})`;
        const isOther = String(cls.name || '').trim().toLowerCase() === 'other';
        const isLockedCellClass = isSettings && ANNOTATION_PAGE_KIND === 'cell' && (isOther || lockedCellClassIds.has(cls.id));
        const row = document.createElement('div');
        row.className = 'class-row' + (cls.id === _activeAnnotationClassId ? ' active' : '') + (classHidden ? ' hidden-class' : '') + (isLockedCellClass ? ' locked' : '') + (isSettings ? ' settings' : ' apply');
        row.dataset.classId = cls.id;
        row.draggable = isSettings;
        row.innerHTML = isSettings ? `
            <button type="button" class="class-active-btn" title="Use this class"></button>
            <input type="color" class="class-color-input" value="${rgbToHex(r, g, b)}" title="${isLockedCellClass ? 'AI/required class color is locked' : 'Class color'}"${isLockedCellClass ? ' disabled' : ''}>
            <input type="text" class="class-name-input" value="${_esc(cls.name)}" title="${isLockedCellClass ? 'AI/required class name is locked' : 'Class name'}"${isLockedCellClass ? ' disabled' : ''}>
            <button type="button" class="class-visibility-btn" title="${visibilityShortcutTitle}" aria-label="${visibilityShortcutTitle}">${_visibilityIcon(!classHidden)}</button>
            <button type="button" class="class-delete-btn" title="${isLockedCellClass ? 'AI/required class cannot be deleted' : 'Delete class'}"${isLockedCellClass ? ' disabled' : ''}>Delete</button>
        ` : `
            <button type="button" class="class-active-btn" title="Select class"></button>
            <span class="class-color-chip" style="background:rgb(${r},${g},${b})"></span>
            <span class="class-name-label" title="${_esc(cls.name)}">${_esc(cls.name)}</span>
            <button type="button" class="class-visibility-btn" title="${visibilityShortcutTitle}" aria-label="${visibilityShortcutTitle}">${_visibilityIcon(!classHidden)}</button>
            <span class="class-shortcut-label">${_annotationClasses.indexOf(cls) < 9 ? _annotationClasses.indexOf(cls) + 1 : _annotationClasses.indexOf(cls) === 9 ? 0 : ''}</span>
        `;
        const activeBtn = row.querySelector('.class-active-btn');
        const colorInput = row.querySelector('.class-color-input');
        const nameInput = row.querySelector('.class-name-input');
        const visibilityBtn = row.querySelector('.class-visibility-btn');
        const deleteBtn = row.querySelector('.class-delete-btn');
        if (colorInput) colorInput.disabled = !isSettings || isLockedCellClass;
        if (nameInput) nameInput.disabled = !isSettings || isLockedCellClass;
        if (deleteBtn) {
            deleteBtn.disabled = !isSettings || isLockedCellClass;
            deleteBtn.title = isLockedCellClass
                ? 'AI/required class cannot be deleted'
                : canManage ? 'Delete class' : 'Doctor/Admin only';
        }

        const setActive = () => {
            _activeAnnotationClassId = cls.id;
            _syncActiveAnnotationClassToViewer();
            if (!isSettings && _applyClassToSelectedPatchCellAnnotations(cls.id)) return;
            renderClassManagementPanel();
            renderAnnotationPanel();
        };
        activeBtn.addEventListener('click', setActive);
        visibilityBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            _toggleAnnotationClassVisibility(cls.id);
        });
        row.addEventListener('click', (e) => {
            if (e.target === colorInput || e.target === nameInput || e.target === deleteBtn || e.target === visibilityBtn) return;
            setActive();
        });
        row.addEventListener('dragstart', (e) => {
            if (!isSettings) return;
            _draggingClassId = cls.id;
            row.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', cls.id);
        });
        row.addEventListener('dragend', () => {
            _draggingClassId = null;
            row.classList.remove('dragging');
        });
        row.addEventListener('dragover', (e) => {
            if (!isSettings || !_draggingClassId || _draggingClassId === cls.id) return;
            e.preventDefault();
            row.classList.add('drag-over');
        });
        row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
        row.addEventListener('drop', (e) => {
            row.classList.remove('drag-over');
            if (!isSettings || !_draggingClassId || _draggingClassId === cls.id) return;
            e.preventDefault();
            const from = _annotationClasses.findIndex(c => c.id === _draggingClassId);
            const to = _annotationClasses.findIndex(c => c.id === cls.id);
            if (from < 0 || to < 0 || from === to) return;
            const [moved] = _annotationClasses.splice(from, 1);
            _annotationClasses.splice(to, 0, moved);
            _queueSaveAnnotationClasses();
            renderClassManagementPanel();
            renderAnnotationPanel();
        });
        if (colorInput) {
            colorInput.addEventListener('input', (e) => {
                if (!isSettings || isLockedCellClass) return;
                cls.color = hexToRgb(e.target.value);
                if (_activeAnnotationClassId === cls.id) _syncActiveAnnotationClassToViewer();
                _syncAnnotationClassMetadata();
                renderAnnotationPanel();
                _queueSaveAnnotationClasses();
            });
        }
        if (nameInput) {
            nameInput.addEventListener('change', (e) => {
                if (!isSettings || isLockedCellClass) return;
                cls.name = e.target.value.trim() || cls.name;
                _syncAnnotationClassMetadata();
                renderAnnotationPanel();
                _queueSaveAnnotationClasses();
            });
        }
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => {
                if (!isSettings || isLockedCellClass) return;
                if (_annotationClasses.length <= 1) {
                    alert('At least one class is required.');
                    return;
                }
                if (!confirm(`Delete class "${cls.name}"? Existing annotations will move to the first class.`)) return;
                const fallback = _annotationClasses.find(c => c.id !== cls.id);
                _annotationClasses = _annotationClasses.filter(c => c.id !== cls.id);
                _hiddenAnnotationClassIds.delete(cls.id);
                if (_activeAnnotationClassId === cls.id) _activeAnnotationClassId = fallback.id;
                _syncActiveAnnotationClassToViewer();
                _syncHiddenAnnotationClassesToViewer();
                for (const ann of viewer.annotations) {
                    if ((ann.class_id || ann.properties?.class_id) === cls.id) _applyClassToAnnotation(ann, fallback.id);
                }
                _syncAnnotationClassMetadata();
                _queueSaveAnnotationClasses();
                renderClassManagementPanel();
                renderAnnotationPanel();
            });
        }
        $classList.appendChild(row);
    }
}

let _projectClassModal = null;

function _normalizeProjectClassList(list) {
    const source = Array.isArray(list) && list.length ? list : _DEFAULT_ANNOTATION_CLASSES;
    const seen = new Set();
    return source.map((cls, idx) => {
        const name = String(cls?.name || `Class ${idx + 1}`).trim().slice(0, 64) || `Class ${idx + 1}`;
        const base = String(cls?.id || name)
            .trim()
            .toLowerCase()
            .replace(/^_+|_+$/g, '') || 'class';
        let id = base;
        let n = 2;
        while (seen.has(id)) id = `${base}_${n++}`;
        seen.add(id);
        return { id, name, color: _normalizeColor(cls?.color) };
    });
}

function _mergeProjectClassList(baseList = [], defaultList = []) {
    const base = _normalizeProjectClassList(baseList);
    const defaults = _normalizeProjectClassList(defaultList);
    const defaultNames = new Set(defaults.map(cls => cls.name.toLowerCase()));
    const defaultIds = new Set(defaults.map(cls => cls.id));
    const merged = base.filter(cls => defaultIds.has(cls.id) || !defaultNames.has(cls.name.toLowerCase()));
    const ids = new Set(merged.map(cls => cls.id));
    for (const cls of defaults) {
        if (ids.has(cls.id)) continue;
        merged.push({ ...cls, color: [...cls.color] });
        ids.add(cls.id);
    }
    if (!merged.some(cls => cls.name.toLowerCase() === 'other')) {
        let id = 'other';
        let n = 2;
        while (ids.has(id)) id = `other_${n++}`;
        merged.push({ id, name: 'Other', color: [149, 165, 166] });
    }
    return merged;
}

function _projectClassLockIdsForCellAi(enabled, key) {
    if (!enabled || !key) return new Set(['other']);
    const locked = new Set(['other']);
    for (const cls of _cellAnnotationPresetClasses(key)) {
        locked.add(cls.id);
    }
    return locked;
}

function _currentProjectInfoForClassSettings() {
    const projectName = _getCurrentProjectName();
    if (!projectName) return null;
    return (_projectListCache || []).find(project => (project?.path || project?.name || '') === projectName)?.info || null;
}

function _lockedCellClassIdsForCurrentProject() {
    if (ANNOTATION_PAGE_KIND !== 'cell') return new Set();
    const info = _currentProjectInfoForClassSettings();
    const annotationAi = info?.annotation_ai || {};
    const key = annotationAi.key || '';
    const enabled = Boolean(info?.annotation_ai_enabled && key);
    return _projectClassLockIdsForCellAi(enabled, key);
}

const CELL_ANNOTATION_AI_OPTIONS = [
    { key: 'quanti_he_breast', label: 'Quanti HE-breast', group: 'Inherited AI', inheritClasses: true, preset: 'quanti_he' },
    { key: 'quanti_he_stomach', label: 'Quanti HE-stomach', group: 'Inherited AI', inheritClasses: true, preset: 'quanti_he' },
    { key: 'quanti_he_other', label: 'Quanti HE-other', group: 'Inherited AI', inheritClasses: true, preset: 'quanti_he' },
    { key: 'quanti_pd_l1_stomach', label: 'Quanti PD-L1 - Stomach (CPS)', group: 'Inherited AI', inheritClasses: true, preset: 'pd_l1_stomach' },
    { key: 'quanti_pd_l1_lung', label: 'Quanti PD-L1 - Lung (TPS)', group: 'Inherited AI', inheritClasses: true, preset: 'pd_l1_lung' },
    { key: 'quanti_ihc_her2', label: 'Quanti IHC - HER2', group: 'Inherited AI', inheritClasses: true, preset: 'ihc_her2' },
    { key: 'quanti_ihc_er_pr', label: 'Quanti IHC - ER/PR (Allred)', group: 'Inherited AI', inheritClasses: true, preset: 'ihc_er_pr' },
    { key: 'quanti_ihc_ki_67', label: 'Quanti IHC - KI-67', group: 'Inherited AI', inheritClasses: true, preset: 'ihc_ki_67' },
    { key: 'hne', label: 'HnE', group: 'Non-inherited AI', inheritClasses: false, preset: 'other' },
    { key: 'ihc_membrane', label: 'IHC Membrane', group: 'Non-inherited AI', inheritClasses: false, preset: 'other' },
    { key: 'ihc_nucleus', label: 'IHC Nucleus', group: 'Non-inherited AI', inheritClasses: false, preset: 'other' },
    { key: 'ihc_membrane_breast', label: 'IHC Membrane (Breast)', group: 'Non-inherited AI', inheritClasses: false, preset: 'ihc_breast' },
    { key: 'ihc_nucleus_breast', label: 'IHC Nucleus (Breast)', group: 'Non-inherited AI', inheritClasses: false, preset: 'ihc_breast' },
];

const CELL_ANNOTATION_CLASS_PRESETS = {
    other: [
        { id: 'other', name: 'Other', color: [149, 165, 166] },
    ],
    ihc_breast: [
        { id: 'tumor', name: 'Tumor', color: [231, 76, 60] },
        { id: 'other', name: 'Other', color: [149, 165, 166] },
    ],
    quanti_he: [
        { id: '0', name: 'Neutrophil', color: [255, 69, 0] },
        { id: '1', name: 'Epithelial', color: [0, 255, 0] },
        { id: '2', name: 'Lymphocyte', color: [0, 0, 255] },
        { id: '3', name: 'Plasma', color: [255, 255, 0] },
        { id: '4', name: 'Eosinophil', color: [138, 43, 226] },
        { id: '5', name: 'Stromal cell', color: [128, 128, 128] },
        { id: '6', name: 'Tumor Epithelial', color: [255, 0, 0] },
        { id: '7', name: 'Benign Epithelial', color: [0, 255, 0] },
    ],
    pd_l1_stomach: [
        { id: '0', name: 'Negative Epithelial', color: [30, 132, 73] },
        { id: '1', name: 'Negative Lymphocyte', color: [39, 174, 96] },
        { id: '2', name: 'Negative Macrophage', color: [22, 160, 133] },
        { id: '3', name: 'Positive Epithelial', color: [146, 43, 33] },
        { id: '4', name: 'Positive Lymphocyte', color: [231, 76, 60] },
        { id: '5', name: 'Positive Macrophage', color: [236, 112, 99] },
        { id: '6', name: 'Other', color: [149, 165, 166] },
    ],
    pd_l1_lung: [
        { id: '0', name: 'PD-L1 Negative Tumor', color: [52, 152, 219] },
        { id: '1', name: 'PD-L1 Positive Tumor', color: [231, 76, 60] },
        { id: '2', name: 'Non-Tumor Cell', color: [149, 165, 166] },
    ],
    ihc_her2: [
        { id: '0', name: 'HER2 0+', color: [39, 174, 96] },
        { id: '1', name: 'HER2 1+', color: [241, 196, 15] },
        { id: '2', name: 'HER2 2+', color: [230, 126, 34] },
        { id: '3', name: 'HER2 3+', color: [192, 57, 43] },
        { id: '4', name: 'Other', color: [149, 165, 166] },
    ],
    ihc_er_pr: [
        { id: '0', name: 'ER/PR 0+', color: [39, 174, 96] },
        { id: '1', name: 'ER/PR 1+', color: [241, 196, 15] },
        { id: '2', name: 'ER/PR 2+', color: [230, 126, 34] },
        { id: '3', name: 'ER/PR 3+', color: [192, 57, 43] },
        { id: '4', name: 'Other', color: [149, 165, 166] },
    ],
    ihc_ki_67: [
        { id: '0', name: 'Negative', color: [39, 174, 96] },
        { id: '1', name: 'Positive (1+)', color: [230, 126, 34] },
        { id: '2', name: 'Positive (2+)', color: [231, 76, 60] },
        { id: '3', name: 'Positive (3+)', color: [192, 57, 43] },
        { id: '4', name: 'Other', color: [149, 165, 166] },
    ],
};

function _cellAnnotationPresetClasses(key) {
    const opt = CELL_ANNOTATION_AI_OPTIONS.find(item => item.key === key);
    if (!opt) return [];
    const preset = CELL_ANNOTATION_CLASS_PRESETS[opt.preset] || CELL_ANNOTATION_CLASS_PRESETS.other;
    return preset.map(cls => ({ ...cls, color: [...cls.color] }));
}

function _cellAnnotationAiSelectHtml(currentKey = '') {
    const groups = [];
    for (const opt of CELL_ANNOTATION_AI_OPTIONS) {
        let group = groups.find(item => item.label === opt.group);
        if (!group) {
            group = { label: opt.group, items: [] };
            groups.push(group);
        }
        group.items.push(opt);
    }
    return '<option value="">Select Cell Annotation AI</option>' + groups.map(group => `
        <optgroup label="${_esc(group.label)}">
            ${group.items.map(opt => `<option value="${_esc(opt.key)}"${opt.key === currentKey ? ' selected' : ''}>${_esc(opt.label)}</option>`).join('')}
        </optgroup>
    `).join('');
}

async function _saveProjectCellAnnotationAiSettings(project, enabled, key) {
    const path = project?.path || project?.name || '';
    const info = project?.info || {};
    const payload = {
        title: info.title || project?.name || path,
        institution: info.institution || '',
        department: info.department || '',
        owner: info.owner || '',
        status: info.status || 'active',
        due_date: info.due_date || '',
        description: info.description || '',
        project_ai_enabled: Boolean(info.project_ai_enabled),
        project_ai_tasks: Array.isArray(info.project_ai_tasks) ? info.project_ai_tasks : [],
        annotation_ai_enabled: Boolean(enabled),
        annotation_ai_key: key || '',
    };
    await api.updateProject(path, payload);
    if (project?.info) {
        project.info.annotation_ai_enabled = Boolean(enabled && key);
        const opt = CELL_ANNOTATION_AI_OPTIONS.find(item => item.key === key);
        project.info.annotation_ai = {
            ...(project.info.annotation_ai || {}),
            enabled: Boolean(enabled && key),
            key: enabled ? (key || '') : '',
            label: opt?.label || '',
            group: opt?.group === 'Inherited AI' ? 'inherited' : 'non_inherited',
            inherit_classes: Boolean(opt?.inheritClasses),
        };
    }
}

async function _openProjectClassManager(project) {
    const path = project?.path || project?.name || '';
    if (!path) return;
    if (_blockClassManageAction()) return;

    _projectClassModal?.remove();
    const projectTitle = _projectLabel(project) || path;
    const isCellClassMode = ANNOTATION_PAGE_KIND === 'cell';
    const classTitle = isCellClassMode ? 'Cell Annotation Settings' : 'Class Management';
    const classSubtitle = isCellClassMode ? `${projectTitle} - Cell Annotation` : projectTitle;
    const classSavedMessage = isCellClassMode ? 'Cell annotation settings saved' : 'Project classes saved';
    const annotationAi = project?.info?.annotation_ai || {};
    const annotationAiKey = annotationAi.key || '';
    const annotationAiEnabled = Boolean(project?.info?.annotation_ai_enabled && annotationAiKey);
    let localClasses = _DEFAULT_ANNOTATION_CLASSES.map(c => ({ ...c, color: [...c.color] }));
    let lockedCellClassIds = isCellClassMode
        ? _projectClassLockIdsForCellAi(annotationAiEnabled, annotationAiKey)
        : new Set();
    let draggingProjectClassId = null;

    const modal = document.createElement('div');
    modal.className = 'project-class-modal';
    modal.innerHTML = `
        <div class="project-class-dialog" role="dialog" aria-modal="true" aria-labelledby="project-class-title">
            <div class="project-class-header">
                <div>
                    <h2 id="project-class-title">${_esc(classTitle)}</h2>
                    <p>${_esc(classSubtitle)}</p>
                </div>
                <button type="button" class="project-class-close" aria-label="Close">x</button>
            </div>
            <div class="project-class-body">
                ${isCellClassMode ? `
                <section class="project-class-ai-section">
                    <label class="project-class-ai-enable">
                        <input type="checkbox" class="project-class-ai-enabled"${annotationAiEnabled ? ' checked' : ''}>
                        <span>Cell Annotation AI assistance</span>
                    </label>
                    <p>One model can assist patch-level cell labeling through WSI_Labeling_assistance.json.</p>
                    <select class="project-class-ai-select">${_cellAnnotationAiSelectHtml(annotationAiKey)}</select>
                </section>
                ` : ''}
                <div class="project-class-toolbar">
                    <button type="button" class="small-btn project-class-add">Add Class</button>
                    <span class="project-class-status">Loading...</span>
                </div>
                <div class="project-class-list"></div>
            </div>
            <div class="project-class-footer">
                <button type="button" class="small-btn project-class-cancel">Cancel</button>
                <button type="button" class="small-btn primary project-class-save">Save</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    _projectClassModal = modal;

    const listEl = modal.querySelector('.project-class-list');
    const statusEl = modal.querySelector('.project-class-status');
    const saveBtn = modal.querySelector('.project-class-save');
    const aiEnabledEl = modal.querySelector('.project-class-ai-enabled');
    const aiSelectEl = modal.querySelector('.project-class-ai-select');
    if (aiSelectEl) aiSelectEl.disabled = !annotationAiEnabled;
    const makeLocalClassId = (name) => {
        const base = String(name || 'Class')
            .trim()
            .toLowerCase()
            .replace(/^_+|_+$/g, '') || 'class';
        let id = base;
        let i = 2;
        while (localClasses.some(c => c.id === id)) id = `${base}_${i++}`;
        return id;
    };

    const close = () => {
        modal.remove();
        if (_projectClassModal === modal) _projectClassModal = null;
    };

    const render = () => {
        listEl.innerHTML = '';
        localClasses.forEach((cls, idx) => {
            const [r, g, b] = _normalizeColor(cls.color);
            const isOther = String(cls.name || '').trim().toLowerCase() === 'other';
            const isLocked = isCellClassMode && (isOther || lockedCellClassIds.has(cls.id));
            const row = document.createElement('div');
            row.className = `project-class-row${isLocked ? ' locked' : ''}`;
            row.draggable = true;
            row.dataset.classId = cls.id;
            row.innerHTML = `
                <span class="project-class-drag" title="Drag to reorder">::</span>
                <input type="color" class="project-class-color" value="${rgbToHex(r, g, b)}" title="Class color"${isLocked ? ' disabled' : ''}>
                <input type="text" class="project-class-name" value="${_esc(cls.name)}" title="Class name"${isLocked ? ' disabled' : ''}>
                <button type="button" class="project-class-delete"${isLocked ? ' disabled' : ''}>Delete</button>
            `;
            row.addEventListener('dragstart', (e) => {
                draggingProjectClassId = cls.id;
                row.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', cls.id);
            });
            row.addEventListener('dragend', () => {
                draggingProjectClassId = null;
                row.classList.remove('dragging');
            });
            row.addEventListener('dragover', (e) => {
                if (!draggingProjectClassId || draggingProjectClassId === cls.id) return;
                e.preventDefault();
                row.classList.add('drag-over');
            });
            row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
            row.addEventListener('drop', (e) => {
                row.classList.remove('drag-over');
                if (!draggingProjectClassId || draggingProjectClassId === cls.id) return;
                e.preventDefault();
                const from = localClasses.findIndex(c => c.id === draggingProjectClassId);
                const to = localClasses.findIndex(c => c.id === cls.id);
                if (from < 0 || to < 0 || from === to) return;
                const [moved] = localClasses.splice(from, 1);
                localClasses.splice(to, 0, moved);
                render();
            });
            row.querySelector('.project-class-color').addEventListener('input', (e) => {
                if (isLocked) return;
                cls.color = hexToRgb(e.target.value);
            });
            row.querySelector('.project-class-name').addEventListener('input', (e) => {
                if (isLocked) return;
                cls.name = e.target.value.trim() || `Class ${idx + 1}`;
            });
            row.querySelector('.project-class-delete').addEventListener('click', () => {
                if (isLocked) return;
                if (localClasses.length <= 1) {
                    alert('At least one class is required.');
                    return;
                }
                localClasses.splice(idx, 1);
                render();
            });
            listEl.appendChild(row);
        });
    };

    const applyCellAnnotationAiPreset = () => {
        if (!isCellClassMode) return;
        const enabled = Boolean(aiEnabledEl?.checked);
        const key = aiSelectEl?.value || '';
        if (aiSelectEl) aiSelectEl.disabled = !enabled;
        lockedCellClassIds = _projectClassLockIdsForCellAi(enabled, key);
        if (!enabled || !key) return;
        const presetClasses = _cellAnnotationPresetClasses(key);
        if (!presetClasses.length) return;
        localClasses = _mergeProjectClassList(localClasses, presetClasses);
        const opt = CELL_ANNOTATION_AI_OPTIONS.find(item => item.key === key);
        statusEl.textContent = opt?.preset === 'ihc_breast'
            ? `${localClasses.length} classes (Tumor/Other)`
            : opt?.inheritClasses
                ? `${localClasses.length} classes`
                : `${localClasses.length} classes (Other required)`;
        render();
    };

    aiEnabledEl?.addEventListener('change', applyCellAnnotationAiPreset);
    aiSelectEl?.addEventListener('change', applyCellAnnotationAiPreset);

    modal.querySelector('.project-class-close').addEventListener('click', close);
    modal.querySelector('.project-class-cancel').addEventListener('click', close);
    modal.addEventListener('mousedown', (e) => {
        if (e.target === modal) close();
    });
    modal.querySelector('.project-class-add').addEventListener('click', () => {
        const name = `Class ${localClasses.length + 1}`;
        localClasses.push({ id: makeLocalClassId(name), name, color: [0, 255, 0] });
        render();
    });
    saveBtn.addEventListener('click', async () => {
        saveBtn.disabled = true;
        statusEl.textContent = 'Saving...';
        try {
            localClasses = _normalizeProjectClassList(localClasses);
            const res = isCellClassMode
                ? await api.saveCellAnnotationClasses(path, localClasses)
                : await api.saveAnnotationClasses(path, localClasses);
            if (isCellClassMode) {
                statusEl.textContent = 'Saving settings...';
                await _saveProjectCellAnnotationAiSettings(
                    project,
                    Boolean(aiEnabledEl?.checked),
                    aiSelectEl?.value || ''
                );
            }
            localClasses = _normalizeProjectClassList(res.classes);
            if (_getCurrentProjectName() === path) {
                _annotationClasses = localClasses.map(c => ({ ...c, color: [...c.color] }));
                _classesLoadedForProject = path;
                if (!_annotationClasses.some(c => c.id === _activeAnnotationClassId)) {
                    _activeAnnotationClassId = _annotationClasses[0]?.id || 'default';
                }
                _syncActiveAnnotationClassToViewer();
                _syncAnnotationClassMetadata();
                renderClassManagementPanel();
                renderAnnotationPanel();
            }
            setStatus(classSavedMessage);
            close();
        } catch (err) {
            statusEl.textContent = `Save failed: ${err.message}`;
            saveBtn.disabled = false;
        }
    });

    render();
    try {
        const res = isCellClassMode
            ? await api.loadCellAnnotationClasses(path)
            : await api.loadAnnotationClasses(path);
        localClasses = _normalizeProjectClassList(res.classes);
        statusEl.textContent = `${localClasses.length} classes`;
        render();
    } catch (err) {
        statusEl.textContent = `Load failed: ${err.message}`;
    }
}

$btnClassAdd?.addEventListener('click', () => {
    if (_blockClassManageAction()) return;
    _classManagementMode = 'settings';
    const name = prompt('Class name:', `Class ${_annotationClasses.length + 1}`);
    if (!name || !name.trim()) return;
    const cls = {
        id: _makeClassId(name),
        name: name.trim().slice(0, 64),
        color: [0, 255, 0],
    };
    _annotationClasses.push(cls);
    _activeAnnotationClassId = cls.id;
    _syncActiveAnnotationClassToViewer();
    renderClassManagementPanel();
    renderAnnotationPanel();
    _queueSaveAnnotationClasses();
});

$btnClassSetting?.addEventListener('click', () => {
    if (_blockClassManageAction()) return;
    _classManagementMode = 'settings';
    renderClassManagementPanel();
});

$btnClassDone?.addEventListener('click', () => {
    _classManagementMode = 'apply';
    renderClassManagementPanel();
});

function _applyActiveClassToSelectedAnnotation() {
    if (_applyClassToSelectedPatchCellAnnotations(_activeAnnotationClassId)) return;
    const ann = viewer.annotations.find(a => a.id === viewer.selectedAnnotationId);
    if (!ann) {
        setStatus('Select an annotation first');
        return;
    }
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    const cls = _getAnnotationClass(_activeAnnotationClassId);
    _activeAnnotationClassId = cls.id;
    _syncActiveAnnotationClassToViewer();
    viewer.pushAnnotationUndo?.();
    _applyClassToAnnotation(ann, cls.id);
    if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
    viewer.requestRender();
    renderClassManagementPanel();
    renderAnnotationPanel();
    setStatus(`Annotation ${_annotationDisplayId(ann)} class: ${cls.name}`);
}

$btnClassApply?.addEventListener('click', _applyActiveClassToSelectedAnnotation);

function _selectedPatchCellAnnotationIds() {
    const ids = new Set();
    if (!cellPatchWorkflow?.patchFocusActive) return ids;
    if (viewer._highlightedCellIdxSet instanceof Set) {
        for (const idx of viewer._highlightedCellIdxSet) {
            const ann = viewer.annotations?.[idx];
            if (ann?.id) ids.add(ann.id);
        }
        return ids;
    }
    for (const id of _annotationBulkSelection || []) ids.add(id);
    if (viewer.selectedAnnotationId) ids.add(viewer.selectedAnnotationId);
    const existingIds = new Set((viewer.annotations || []).map(ann => ann.id));
    for (const id of [...ids]) {
        if (!existingIds.has(id)) ids.delete(id);
    }
    return ids;
}

function _canEditSelectedPatchCells() {
    return Boolean(cellPatchWorkflow?.patchFocusActive && cellPatchWorkflow.canAnnotateSelectedPatch?.());
}

function _blockPatchCellEditAction(message = 'Patch cell editing is available only while Annotation is running.') {
    if (_canEditSelectedPatchCells()) return false;
    setStatus(message);
    return true;
}

function _applyClassToSelectedPatchCellAnnotations(classId) {
    if (!cellPatchWorkflow?.patchFocusActive) return false;
    if (_blockPatchCellEditAction()) return true;
    const ids = _selectedPatchCellAnnotationIds();
    if (!ids.size) return false;
    if (_blockViewerAction('Viewer role cannot change cell annotation classes.')) return true;
    const cls = _getAnnotationClass(classId);
    _activeAnnotationClassId = cls.id;
    _syncActiveAnnotationClassToViewer();
    viewer.pushAnnotationUndo?.();
    const changed = [];
    for (const ann of viewer.annotations || []) {
        if (!ids.has(ann.id)) continue;
        _applyClassToAnnotation(ann, cls.id);
        changed.push(ann);
    }
    _syncPatchEditorAfterViewerAnnotationEdit();
    _annotationBulkSelection = new Set(ids);
    _syncPatchCellHighlightFromBulkSelection();
    viewer.requestRender();
    renderClassManagementPanel();
    renderAnnotationPanel();
    setStatus(`Changed ${changed.length.toLocaleString()} cell annotation${changed.length === 1 ? '' : 's'} to ${cls.name}`);
    return true;
}

function _annotationDisplayId(ann) {
    const idx = viewer.annotations.findIndex(item => item === ann || item.id === ann?.id);
    return idx >= 0 ? String(idx + 1) : '-';
}

function _annotationMemo(ann) {
    return String(ann?.memo ?? ann?.properties?.memo ?? '').trim();
}

function _normalizeMemoHistory(value) {
    const list = Array.isArray(value) ? value : [];
    return list
        .map(item => {
            if (typeof item === 'string') return { text: item, answer: '', accepted_at: '' };
            return {
                text: String(item?.text ?? item?.memo ?? '').trim(),
                answer: String(item?.answer ?? item?.reply ?? '').trim(),
                accepted_at: String(item?.accepted_at ?? item?.created_at ?? ''),
            };
        })
        .filter(item => item.text);
}

function _annotationMemoHistory(ann) {
    return _normalizeMemoHistory(ann?.memo_history ?? ann?.properties?.memo_history);
}

function _setAnnotationMemo(ann, memo) {
    if (!ann) return;
    const text = String(memo || '').trim();
    ann.memo = text;
    ann.properties = { ...(ann.properties || {}), memo: text };
}

function _setAnnotationMemoHistory(ann, history) {
    if (!ann) return;
    const list = _normalizeMemoHistory(history);
    ann.memo_history = list;
    ann.properties = { ...(ann.properties || {}), memo_history: list };
}

function _currentSlideHasMemo() {
    return Boolean(String(currentSlideMemo || '').trim() || viewer.annotations.some(ann => _annotationMemo(ann)));
}

function _currentSlideHasMemoHistory() {
    return Boolean(
        _normalizeMemoHistory(currentSlideMemoHistory).length ||
        viewer.annotations.some(ann => _annotationMemoHistory(ann).length)
    );
}

function _syncSlideMemoButton() {
    if (!$btnSlideMemo) return;
    const hasMemo = Boolean(String(currentSlideMemo || '').trim());
    const hasHistory = _normalizeMemoHistory(currentSlideMemoHistory).length > 0;
    $btnSlideMemo.classList.toggle('has-memo', hasMemo);
    $btnSlideMemo.classList.toggle('has-history', !hasMemo && hasHistory);
    $btnSlideMemo.title = hasMemo
        ? 'Slide Memo (current memo exists)'
        : hasHistory
            ? 'Slide Memo (previous memos exist)'
            : 'Slide Memo (Ctrl+M)';
}

function _setSlideListMemoIndicator(filename = currentSlideFilename, hasMemo = _currentSlideHasMemo()) {
    if (!filename || !$slideList) return;
    const item = [...$slideList.querySelectorAll('.slide-list-item:not(.folder-item)')]
        .find(el => el.dataset.filename === filename);
    if (!item) return;
    item.classList.toggle('has-memo', Boolean(hasMemo));
    item.dataset.hasMemo = hasMemo ? '1' : '';
    let badge = item.querySelector('.slide-memo-badge');
    if (hasMemo && !badge) {
        badge = document.createElement('span');
        badge.className = 'slide-memo-badge';
        badge.title = 'Memo exists';
        badge.textContent = 'M';
        item.appendChild(badge);
    } else if (!hasMemo && badge) {
        badge.remove();
    }
}

async function _saveAnnotationsAfterMemoChange(message) {
    renderAnnotationPanel();
    _setSlideListMemoIndicator();
    _syncSlideMemoButton();
    try {
        await _saveAnnotationsToServer();
        if (message) setStatus(message);
    } catch (err) {
        alert(`Failed to save memo: ${err.message}`);
    }
}

function _openMemoDialog({ title, value = '', history = [], onSave, onAccept, onDelete, onDeleteHistory }) {
    const existing = document.querySelector('.memo-modal');
    if (existing) existing.remove();
    const hasCurrentMemo = Boolean(String(value || '').trim());
    const modal = document.createElement('div');
    modal.className = 'memo-modal';
    modal.innerHTML = `
        <div class="memo-dialog" role="dialog" aria-modal="true" aria-labelledby="memo-title">
            <div class="memo-dialog-header">
                <h2 id="memo-title">${_esc(title)}</h2>
                <button type="button" class="memo-close" aria-label="Close">x</button>
            </div>
            <div class="memo-dialog-body">
                <label class="memo-current">
                    <span>${hasCurrentMemo ? 'Current memo' : 'Memo'}</span>
                    <textarea class="memo-textarea" rows="6" placeholder="Write memo..."${hasCurrentMemo ? ' readonly' : ''}>${_esc(value)}</textarea>
                </label>
                <label class="memo-answer" ${hasCurrentMemo ? '' : 'hidden'}>
                    <span>Answer</span>
                    <textarea class="memo-answer-textarea" rows="4" placeholder="Write answer..."${hasCurrentMemo ? '' : ' disabled'}></textarea>
                </label>
                <div class="memo-history">
                    <div class="memo-history-title">Previous memo list</div>
                    <div class="memo-history-list"></div>
                </div>
            </div>
            <div class="memo-dialog-footer">
                <button type="button" class="small-btn memo-delete"${hasCurrentMemo ? ' hidden' : ''}>Delete</button>
                <button type="button" class="small-btn memo-save"${hasCurrentMemo ? ' hidden' : ''}>Save</button>
                <button type="button" class="small-btn primary memo-accept"${hasCurrentMemo ? '' : ' hidden'}>Accept</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    const textarea = modal.querySelector('.memo-textarea');
    const answerTextarea = modal.querySelector('.memo-answer-textarea');
    const listEl = modal.querySelector('.memo-history-list');
    let historyList = _normalizeMemoHistory(history);
    const renderHistory = () => {
        listEl.innerHTML = '';
        if (!historyList.length) {
            const empty = document.createElement('div');
            empty.className = 'memo-history-empty';
            empty.textContent = 'No previous memos';
            listEl.appendChild(empty);
            return;
        }
        historyList.forEach((item, idx) => {
            const row = document.createElement('div');
            row.className = 'memo-history-item';
            row.innerHTML = `
                <div class="memo-history-text">${_esc(item.text)}</div>
                ${item.answer ? `<div class="memo-history-answer"><strong>Answer</strong>${_esc(item.answer)}</div>` : ''}
                <time>${_esc(item.accepted_at || '')}</time>
                <button type="button" class="memo-history-delete" title="Delete previous memo">x</button>
            `;
            row.querySelector('.memo-history-delete').addEventListener('click', async () => {
                if (!confirm('Delete previous memo?')) return;
                const nextHistory = historyList.filter((_, itemIdx) => itemIdx !== idx);
                await onDeleteHistory?.(nextHistory, idx);
                historyList = nextHistory;
                renderHistory();
            });
            listEl.appendChild(row);
        });
    };
    const close = () => modal.remove();
    modal.querySelector('.memo-close').addEventListener('click', close);
    modal.addEventListener('mousedown', (e) => { if (e.target === modal) close(); });
    modal.querySelector('.memo-save').addEventListener('click', async () => {
        await onSave?.(textarea.value.trim());
        close();
    });
    modal.querySelector('.memo-accept').addEventListener('click', async () => {
        await onAccept?.(textarea.value.trim(), answerTextarea?.value.trim() || '');
        close();
    });
    modal.querySelector('.memo-delete').addEventListener('click', async () => {
        if (!textarea.value.trim() && !value) return close();
        if (!confirm('Delete current memo?')) return;
        await onDelete?.();
        close();
    });
    renderHistory();
    const focusTarget = hasCurrentMemo ? answerTextarea : textarea;
    focusTarget?.focus();
    focusTarget?.select();
}

function _editAnnotationMemo(ann) {
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    const displayId = _annotationDisplayId(ann);
    _openMemoDialog({
        title: `Annotation memo - ${displayId}`,
        value: _annotationMemo(ann),
        history: _annotationMemoHistory(ann),
        onSave: async (text) => {
            viewer.pushAnnotationUndo?.();
            _setAnnotationMemo(ann, text);
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
            await _saveAnnotationsAfterMemoChange(text ? `Memo saved: annotation ${displayId}` : `Memo cleared: annotation ${displayId}`);
        },
        onAccept: async (text, answer) => {
            viewer.pushAnnotationUndo?.();
            const list = _annotationMemoHistory(ann);
            if (text) list.unshift({ text, answer, accepted_at: new Date().toISOString() });
            _setAnnotationMemo(ann, '');
            _setAnnotationMemoHistory(ann, list);
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
            await _saveAnnotationsAfterMemoChange(`Memo accepted: annotation ${displayId}`);
        },
        onDelete: async () => {
            viewer.pushAnnotationUndo?.();
            _setAnnotationMemo(ann, '');
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
            await _saveAnnotationsAfterMemoChange(`Memo deleted: annotation ${displayId}`);
        },
        onDeleteHistory: async (nextHistory) => {
            viewer.pushAnnotationUndo?.();
            _setAnnotationMemoHistory(ann, nextHistory);
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
            await _saveAnnotationsAfterMemoChange(`Previous memo deleted: annotation ${displayId}`);
        },
    });
}

function _editSlideMemo() {
    if (!currentSlideId) {
        setStatus('Open a slide before adding a memo');
        return;
    }
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    _openMemoDialog({
        title: `Slide memo - ${currentSlideFilename || currentSlideId}`,
        value: currentSlideMemo || '',
        history: currentSlideMemoHistory,
        onSave: async (text) => {
            currentSlideMemo = text;
            await _saveAnnotationsAfterMemoChange(text ? 'Slide memo saved' : 'Slide memo cleared');
        },
        onAccept: async (text, answer) => {
            if (text) currentSlideMemoHistory = [{ text, answer, accepted_at: new Date().toISOString() }, ..._normalizeMemoHistory(currentSlideMemoHistory)];
            currentSlideMemo = '';
            await _saveAnnotationsAfterMemoChange('Slide memo accepted');
        },
        onDelete: async () => {
            currentSlideMemo = '';
            await _saveAnnotationsAfterMemoChange('Slide memo deleted');
        },
        onDeleteHistory: async (nextHistory) => {
            currentSlideMemoHistory = _normalizeMemoHistory(nextHistory);
            await _saveAnnotationsAfterMemoChange('Previous slide memo deleted');
        },
    });
}

function _editCurrentMemo() {
    if (ANNOTATION_PAGE_KIND === 'cell' && cellPatchWorkflow?.patchFocusActive) {
        if (_isLabelerRole()) {
            setStatus('Labeler role cannot change patch memo.');
            return;
        }
        const selected = cellPatchWorkflow.selectedPatch;
        const patch = cellPatchWorkflow._findPatchRecord?.(selected) || selected;
        if (!patch) {
            setStatus('Select a patch before adding a memo');
            return;
        }
        cellPatchWorkflow.editPatchMemo?.(patch);
        return;
    }
    _editSlideMemo();
}

$btnSlideMemo?.addEventListener('click', _editCurrentMemo);

function _visibilityIcon(visible) {
    return visible
        ? `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.5 10s2.8-5 7.5-5 7.5 5 7.5 5-2.8 5-7.5 5-7.5-5-7.5-5z"/><circle cx="10" cy="10" r="2.4"/></svg>`
        : `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l14 14"/><path d="M7.4 5.6A7.2 7.2 0 0 1 10 5c4.7 0 7.5 5 7.5 5a12.8 12.8 0 0 1-2.1 2.6"/><path d="M12.1 12.1A2.8 2.8 0 0 1 7.9 7.9"/><path d="M5.4 7.4A12.8 12.8 0 0 0 2.5 10s2.8 5 7.5 5c1 0 1.9-.2 2.7-.6"/></svg>`;
}

const _ANNOTATION_LIST_COLUMNS = [
    { key: 'id', label: 'ID' },
    { key: 'class', label: 'Class' },
    { key: 'memo', label: 'Memo' },
    { key: 'visual', label: 'Visual' },
    { key: 'del', label: 'Del' },
];

function _annotationSortValue(ann, index, key) {
    if (key === 'id' || key === 'del') return index + 1;
    if (key === 'class') {
        return _annotationClassMetadata(ann).name.toLowerCase();
    }
    if (key === 'memo') {
        const memo = _annotationMemo(ann);
        if (memo) return `2:${memo.toLowerCase()}`;
        const hasAnsweredMemo = _annotationMemoHistory(ann).some(item => item.answer);
        return hasAnsweredMemo ? '1:history' : '0:';
    }
    if (key === 'visual') return ann.visible !== false ? 1 : 0;
    return index + 1;
}

function _sortedAnnotationEntries() {
    const key = _annotationListSort.key;
    const dir = _annotationListSort.dir === 'desc' ? -1 : 1;
    if (key === 'id' || key === 'del') {
        const entries = viewer.annotations.map((ann, index) => ({ ann, index }));
        return dir === 1 ? entries : entries.reverse();
    }
    return viewer.annotations
        .map((ann, index) => ({ ann, index }))
        .sort((a, b) => {
            const av = _annotationSortValue(a.ann, a.index, key);
            const bv = _annotationSortValue(b.ann, b.index, key);
            let result = 0;
            if (typeof av === 'number' && typeof bv === 'number') {
                result = av - bv;
            } else {
                result = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' });
            }
            return result ? result * dir : a.index - b.index;
        });
}

function _syncPatchCellHighlightFromBulkSelection() {
    if (!cellPatchWorkflow?.patchFocusActive) return;
    const selectedIds = new Set(_annotationBulkSelection || []);
    const indices = [];
    (viewer.annotations || []).forEach((ann, idx) => {
        if (selectedIds.has(ann.id)) indices.push(idx);
        ann.selected = false;
    });
    viewer.selectedAnnotationId = null;
    viewer._highlightedCellIdx = -1;
    viewer._highlightedHiddenCellIdxSet = null;
    viewer._highlightedCellIdxSet = indices.length ? new Set(indices) : null;
    viewer.requestRender?.();
}

function renderAnnotationPanel() {
    if (!$annList) return;
    if (cellPatchWorkflow && !cellPatchWorkflow.patchFocusActive) {
        cellPatchWorkflow.renderPatchList();
        return;
    }
    $annList.innerHTML = '';
    const isCellPatchView = Boolean(cellPatchWorkflow?.patchFocusActive);
    const canEditPatchCells = isCellPatchView && _canEditSelectedPatchCells();
    const currentIds = new Set((viewer.annotations || []).map(ann => ann.id));
    _annotationBulkSelection = new Set([..._annotationBulkSelection].filter(id => currentIds.has(id)));
    if (!isCellPatchView) _annotationPanelRenderLimit = 300;
    if (isCellPatchView) {
        const bulk = document.createElement('div');
        bulk.className = 'cell-ann-bulk-bar';
        const selectedCount = _annotationBulkSelection.size;
        bulk.innerHTML = `
            <label class="cell-ann-select-all">
                <input type="checkbox" ${selectedCount > 0 && selectedCount === currentIds.size ? 'checked' : ''} ${canEditPatchCells ? '' : 'disabled'}>
                <span>${selectedCount ? `${selectedCount} selected` : 'Select'}</span>
            </label>
            <select class="cell-ann-bulk-class" ${selectedCount && canEditPatchCells ? '' : 'disabled'} title="Apply class to selected cells">
                <option value="">Class</option>
                ${_annotationClasses.map(cls => `<option value="${_esc(cls.id)}">${_esc(cls.name)}</option>`).join('')}
            </select>
            <button type="button" class="cell-ann-bulk-delete" ${selectedCount && canEditPatchCells ? '' : 'disabled'}>Del</button>
        `;
        bulk.querySelector('.cell-ann-select-all input')?.addEventListener('change', (event) => {
            if (_blockPatchCellEditAction()) {
                event.target.checked = false;
                return;
            }
            _annotationBulkSelection = event.target.checked
                ? new Set((viewer.annotations || []).map(ann => ann.id))
                : new Set();
            _syncPatchCellHighlightFromBulkSelection();
            renderAnnotationPanel();
        });
        bulk.querySelector('.cell-ann-bulk-class')?.addEventListener('change', (event) => {
            const classId = event.target.value;
            if (!classId) return;
            if (_blockPatchCellEditAction()) {
                event.target.value = '';
                return;
            }
            const selected = _selectedPatchCellAnnotationIds();
            if (!selected.size) return;
            if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
            viewer.pushAnnotationUndo?.();
            for (const ann of viewer.annotations || []) {
                if (!selected.has(ann.id)) continue;
                _applyClassToAnnotation(ann, classId);
            }
            _syncPatchEditorAfterViewerAnnotationEdit();
            _annotationBulkSelection = selected;
            _syncPatchCellHighlightFromBulkSelection();
            viewer.requestRender();
            renderClassManagementPanel();
            renderAnnotationPanel();
        });
        bulk.querySelector('.cell-ann-bulk-delete')?.addEventListener('click', () => {
            if (!_annotationBulkSelection.size) return;
            if (_blockPatchCellEditAction()) return;
            if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
            viewer.pushAnnotationUndo?.();
            const selected = new Set(_annotationBulkSelection);
            const removed = (viewer.annotations || []).filter(ann => selected.has(ann.id));
            viewer.annotations = (viewer.annotations || []).filter(ann => !selected.has(ann.id));
            if (selected.has(viewer.selectedAnnotationId)) viewer.selectedAnnotationId = null;
            _removePatchLabelsForAnnotations(removed);
            _annotationBulkSelection = new Set();
            viewer.requestRender();
            renderClassManagementPanel();
            renderAnnotationPanel();
        });
        $annList.appendChild(bulk);
    }
    const sortedEntries = _sortedAnnotationEntries();
    const renderEntries = isCellPatchView
        ? sortedEntries.slice(0, Math.min(_annotationPanelRenderLimit, sortedEntries.length))
        : sortedEntries;
    const header = document.createElement('div');
    header.className = 'ann-list-header' + (isCellPatchView ? ' cell-ann-list-header' : '');
    if (isCellPatchView) {
        const cell = document.createElement('span');
        cell.textContent = '';
        header.appendChild(cell);
    }
    _ANNOTATION_LIST_COLUMNS.forEach(({ key, label }) => {
        const cell = document.createElement('span');
        cell.className = 'ann-sort-header' + (_annotationListSort.key === key ? ' active' : '');
        cell.dataset.sortKey = key;
        const sortIcon = _annotationListSort.key === key ? (_annotationListSort.dir === 'asc' ? ' \u2191' : ' \u2193') : '';
        cell.textContent = `${label}${sortIcon}`;
        cell.title = `Sort by ${label}`;
        cell.addEventListener('click', () => {
            if (_annotationListSort.key === key) {
                _annotationListSort = { key, dir: _annotationListSort.dir === 'asc' ? 'desc' : 'asc' };
            } else {
                _annotationListSort = { key, dir: 'asc' };
            }
            renderAnnotationPanel();
        });
        header.appendChild(cell);
    });
    $annList.appendChild(header);
    for (const { ann } of renderEntries) {
        const annClass = _annotationClassMetadata(ann);
        const classOptions = _annotationClasses.some(cls => cls.id === annClass.id)
            ? _annotationClasses
            : [annClass, ..._annotationClasses];
        const displayId = _annotationDisplayId(ann);
        const memo = _annotationMemo(ann);
        const memoHistory = _annotationMemoHistory(ann);
        const hasAnsweredMemo = memoHistory.some(item => item.answer);
        const memoLabel = memo ? 'M' : (hasAnsweredMemo ? 'H' : '-');
        const memoTitle = memo ? memo : (memoHistory.length ? `${memoHistory.length} previous memo(s)` : 'No memo');
        const memoClass = memo ? ' has-memo' : (hasAnsweredMemo ? ' has-history' : '');
        const el = document.createElement('div');
        el.className = 'ann-item' + (ann.selected ? ' selected' : '') + (_annotationBulkSelection.has(ann.id) ? ' bulk-selected' : '') + (isCellPatchView ? ' cell-ann-item' : '');
        el.dataset.id = ann.id;
        el.innerHTML = `
            ${isCellPatchView ? `<label class="cell-ann-check" title="Select cell"><input type="checkbox" ${_annotationBulkSelection.has(ann.id) ? 'checked' : ''} ${_canEditSelectedPatchCells() ? '' : 'disabled'}></label>` : ''}
            <span class="ann-id" title="Double-click to center">${_esc(displayId)}</span>
            <span class="ann-class-wrap" style="--ann-class-color: rgb(${_normalizeColor(annClass.color).join(',')})">
                <select class="ann-class-select" title="Annotation class">
                    ${classOptions.map(cls => `<option value="${_esc(cls.id)}"${cls.id === annClass.id ? ' selected' : ''}>${_esc(cls.name)}</option>`).join('')}
                </select>
            </span>
            <button class="ann-btn-memo${memoClass}" title="${_esc(memoTitle)}">${memoLabel}</button>
            <button class="ann-btn-vis" title="${ann.visible ? 'Hide annotation' : 'Show annotation'}">${_visibilityIcon(ann.visible !== false)}</button>
            <button class="ann-btn-del" title="Delete">Del</button>
        `;
        const areaLabel = viewer.getAnnotationAreaLabel(ann);
        if (areaLabel) {
            const area = document.createElement('span');
            area.className = 'ann-area';
            area.textContent = areaLabel;
            el.append(area);
        }
        const annDeleteButton = el.querySelector('.ann-btn-del');
        if (_isViewerRole()) {
            const readOnlyTitle = 'Viewer role can view annotations only';
            el.querySelector('.ann-class-select').disabled = true;
            el.querySelector('.ann-class-select').title = readOnlyTitle;
            if (annDeleteButton) {
                annDeleteButton.disabled = true;
                annDeleteButton.title = readOnlyTitle;
            }
        }
        if (isCellPatchView && !canEditPatchCells) {
            const patchReadOnlyTitle = 'Cell editing is available only while Annotation is running';
            el.querySelector('.ann-class-select').disabled = true;
            el.querySelector('.ann-class-select').title = patchReadOnlyTitle;
            if (annDeleteButton) {
                annDeleteButton.disabled = true;
                annDeleteButton.title = patchReadOnlyTitle;
            }
        }
        el.querySelector('.cell-ann-check input')?.addEventListener('change', (e) => {
            e.stopPropagation();
            if (_blockPatchCellEditAction()) {
                e.target.checked = _annotationBulkSelection.has(ann.id);
                return;
            }
            if (e.target.checked) _annotationBulkSelection.add(ann.id);
            else _annotationBulkSelection.delete(ann.id);
            _syncPatchCellHighlightFromBulkSelection();
            renderAnnotationPanel();
        });
        el.addEventListener('click', (e) => {
            if (e.target.closest('.ann-btn-memo') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') ||
                e.target.closest('.ann-class-select') ||
                e.target.closest('.cell-ann-check')) return;
            if (isCellPatchView && _blockPatchCellEditAction()) return;
            viewer.selectAnnotation(ann.id);
        });
        el.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            if (isCellPatchView && _blockPatchCellEditAction()) return;
            viewer.selectAnnotation(ann.id);
            _editAnnotationMemo(ann);
        });
        el.addEventListener('dblclick', (e) => {
            if (e.target.closest('.ann-btn-memo') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') ||
                e.target.closest('.ann-class-select')) return;
            e.preventDefault();
            if (isCellPatchView && _blockPatchCellEditAction()) return;
            viewer.selectAnnotation(ann.id);
            if (typeof viewer.centerOnAnnotation === 'function') {
                viewer.centerOnAnnotation(ann);
                setStatus(`Centered on annotation ${displayId}`);
            }
        });
        el.querySelector('.ann-btn-memo').addEventListener('click', (e) => {
            e.stopPropagation();
            if (isCellPatchView && _blockPatchCellEditAction()) return;
            viewer.selectAnnotation(ann.id);
            _editAnnotationMemo(ann);
        });
        el.querySelector('.ann-class-select').addEventListener('change', (e) => {
            e.stopPropagation();
            if (isCellPatchView && _blockPatchCellEditAction()) {
                e.target.value = annClass.id;
                return;
            }
            if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
            viewer.pushAnnotationUndo?.();
            _applyClassToAnnotation(ann, e.target.value);
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
            renderAnnotationPanel();
        });
        el.querySelector('.ann-btn-vis').addEventListener('click', (e) => {
            e.stopPropagation();
            ann.visible = !ann.visible;
            viewer.requestRender();
            renderAnnotationPanel();
        });
        el.querySelector('.ann-btn-del').addEventListener('click', (e) => {
            e.stopPropagation();
            if (isCellPatchView && _blockPatchCellEditAction()) return;
            if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
            viewer.deleteAnnotation(ann.id);
        });
        $annList.appendChild(el);
    }
    if (isCellPatchView && renderEntries.length < sortedEntries.length) {
        const more = document.createElement('button');
        more.type = 'button';
        more.className = 'cell-ann-load-more';
        more.textContent = `Show more (${renderEntries.length.toLocaleString()} / ${sortedEntries.length.toLocaleString()})`;
        more.addEventListener('click', () => {
            _annotationPanelRenderLimit = Math.min(sortedEntries.length, _annotationPanelRenderLimit + 300);
            renderAnnotationPanel();
        });
        $annList.appendChild(more);
    }
    renderAnnotationStylePanel();
}

if ($annStrokeWidth) {
    $annStrokeWidth.addEventListener('input', (e) => {
        const value = Number(e.target.value);
        _updateAnnotationDisplayStyle({ stroke_width: value });
    });
    $annStrokeWidth.addEventListener('change', (e) => {
        const value = Number(e.target.value);
        _updateAnnotationDisplayStyle({ stroke_width: value }, true);
    });
}
if ($annFillOpacity) {
    $annFillOpacity.addEventListener('input', (e) => {
        const value = Number(e.target.value) / 100;
        _updateAnnotationDisplayStyle({ fill_opacity: value });
    });
    $annFillOpacity.addEventListener('change', (e) => {
        const value = Number(e.target.value) / 100;
        _updateAnnotationDisplayStyle({ fill_opacity: value }, true);
    });
}

function rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}
function hexToRgb(hex) {
    const m = hex.match(/^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [0, 255, 0];
}

function _classShortcutIndexFromKey(e) {
    if (/^Digit[0-9]$/.test(e.code)) {
        const n = Number(e.code.slice(5));
        return n === 0 ? 9 : n - 1;
    }
    if (/^Numpad[0-9]$/.test(e.code)) {
        const n = Number(e.code.slice(6));
        return n === 0 ? 9 : n - 1;
    }
    if (/^[0-9]$/.test(e.key)) {
        const n = Number(e.key);
        return n === 0 ? 9 : n - 1;
    }
    return -1;
}

function _assignSelectedAnnotationClassByShortcut(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || (e.target && e.target.isContentEditable)) return false;
    if (_projectClassModal) return false;
    const idx = _classShortcutIndexFromKey(e);
    if (idx < 0 || idx >= _annotationClasses.length) return false;
    const cls = _annotationClasses[idx];
    if (cellPatchWorkflow?.patchFocusActive) {
        _activeAnnotationClassId = cls.id;
        _syncActiveAnnotationClassToViewer();
        if (_applyClassToSelectedPatchCellAnnotations(cls.id)) {
            e.preventDefault();
            return true;
        }
        renderClassManagementPanel();
        renderAnnotationPanel();
        e.preventDefault();
        return true;
    }
    const ann = viewer.annotations.find(a => a.id === viewer.selectedAnnotationId);
    if (!ann) return false;
    if (_blockViewerAction('Viewer role cannot change annotation classes.')) return true;
    _activeAnnotationClassId = cls.id;
    _syncActiveAnnotationClassToViewer();
    viewer.pushAnnotationUndo?.();
    _applyClassToAnnotation(ann, cls.id);
    if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
    viewer.requestRender();
    renderClassManagementPanel();
    renderAnnotationPanel();
    setStatus(`Annotation ${_annotationDisplayId(ann)} class: ${cls.name}`);
    e.preventDefault();
    return true;
}

function _syncPatchEditorAfterViewerAnnotationEdit() {
    if (cellPatchWorkflow?.patchFocusActive) {
        cellPatchWorkflow.syncPatchLabelsFromViewerAnnotations?.();
    }
}

function _removePatchLabelsForAnnotations(annotations = []) {
    const list = Array.isArray(annotations) ? annotations.filter(Boolean) : [];
    if (!list.length) return false;
    if (cellPatchWorkflow?.patchFocusActive) {
        cellPatchWorkflow.removePatchLabelsFromAnnotations?.(list);
        return true;
    }
    list.forEach(ann => viewer.onAnnotationDeleted?.(ann));
    return true;
}

function _deleteSelectedCellPatchAnnotationsByShortcut(e) {
    const key = String(e.key || '').toLowerCase();
    const isDeleteKey = key === 'delete' || key === 'backspace' || key === 'd';
    if (!isDeleteKey || e.ctrlKey || e.metaKey || e.altKey) return false;
    if (!cellPatchWorkflow?.patchFocusActive) return false;
    if (_cellEditCtx || _projectClassModal) return false;
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || (e.target && e.target.isContentEditable)) return false;
    if (_blockPatchCellEditAction()) {
        e.preventDefault();
        e.stopImmediatePropagation();
        return true;
    }
    if (_blockViewerAction('Viewer role cannot delete cell annotations.')) {
        e.preventDefault();
        e.stopImmediatePropagation();
        return true;
    }

    const ids = new Set();
    for (const id of _annotationBulkSelection || []) ids.add(id);
    if (viewer.selectedAnnotationId) ids.add(viewer.selectedAnnotationId);
    if (viewer._highlightedCellIdxSet instanceof Set) {
        for (const idx of viewer._highlightedCellIdxSet) {
            const ann = viewer.annotations?.[idx];
            if (ann?.id) ids.add(ann.id);
        }
    }
    if (!ids.size) return false;

    const existingIds = new Set((viewer.annotations || []).map(ann => ann.id));
    for (const id of [...ids]) {
        if (!existingIds.has(id)) ids.delete(id);
    }
    if (!ids.size) return false;

    viewer.pushAnnotationUndo?.();
    const removed = [];
    viewer.annotations = (viewer.annotations || []).filter((ann) => {
        if (!ids.has(ann.id)) return true;
        removed.push(ann);
        return false;
    });
    if (ids.has(viewer.selectedAnnotationId)) viewer.selectedAnnotationId = null;
    if (viewer._highlightedCellIdxSet) viewer._highlightedCellIdxSet = null;
    viewer._highlightedCellIdx = -1;
    _annotationBulkSelection = new Set();
    _removePatchLabelsForAnnotations(removed);
    viewer.onAnnotationSelected?.(null);
    viewer.requestRender();
    renderClassManagementPanel();
    renderAnnotationPanel();
    setStatus(`Deleted ${removed.length.toLocaleString()} cell annotation${removed.length === 1 ? '' : 's'}`);
    e.preventDefault();
    e.stopImmediatePropagation();
    return true;
}

window.addEventListener('keydown', (e) => {
    if (_deleteSelectedCellPatchAnnotationsByShortcut(e)) return;
    _assignSelectedAnnotationClassByShortcut(e);
}, true);

viewer.onAnnotationCreated = (ann) => {
    if (cellPatchWorkflow) {
        if (cellPatchWorkflow.patchFocusActive) {
            if (!cellPatchWorkflow.canAnnotateSelectedPatch?.()) {
                viewer.annotations = viewer.annotations.filter(item => item.id !== ann.id);
                viewer.selectedAnnotationId = null;
                renderAnnotationPanel();
                viewer.requestRender();
                setStatus('Patch annotation is locked for the current role and workflow state.');
                return;
            }
            _applyClassToAnnotation(ann, _activeAnnotationClassId);
            ann.source = 'patch_cell_annotation';
            ann.properties = {
                ...(ann.properties || {}),
                source: 'patch_cell_annotation',
            };
            _syncActiveAnnotationClassToViewer();
            renderAnnotationPanel();
            viewer.requestRender();
            cellPatchWorkflow.addPatchLabelFromAnnotation(ann)
                .then(() => renderAnnotationPanel())
                .catch((err) => {
                    setStatus(`Patch label failed: ${err.message}`);
                });
            return;
        }
        const bool_can_manage_required = window.__currentUserRole === 'admin' || window.__currentUserRole === 'doctor';
        if (!bool_can_manage_required) {
            viewer.deleteAnnotation?.(ann.id);
            setStatus('Only admin or doctor users can create required regions');
            return;
        }
        viewer.annotations = viewer.annotations.filter(item => item.id !== ann.id);
        viewer.selectedAnnotationId = null;
        renderAnnotationPanel();
        viewer.requestRender();
        cellPatchWorkflow.addRequiredRegionFromAnnotation(ann).catch((err) => {
            setStatus(`Patch region queue failed: ${err.message}`);
        });
        return;
    }
    _applyClassToAnnotation(ann, _activeAnnotationClassId);
    _syncActiveAnnotationClassToViewer();
    setStatus(`Annotation ${_annotationDisplayId(ann)} created`);
    renderAnnotationPanel();
};
viewer.onAnnotationSelected = (ann) => {
    if (ann && cellPatchWorkflow?.patchFocusActive && !cellPatchWorkflow.canAnnotateSelectedPatch?.()) {
        _clearPatchCellBulkSelection({ render: false });
        renderClassManagementPanel();
        renderAnnotationPanel();
        return;
    }
    if (!ann) {
        _clearPatchCellBulkSelection({ render: false });
    }
    if (ann?.class_id || ann?.properties?.class_id) {
        const classId = ann.class_id || ann.properties?.class_id;
        const cls = _annotationClasses.find(item => item.id === classId);
        if (cls) {
            _activeAnnotationClassId = cls.id;
            _syncActiveAnnotationClassToViewer();
        }
    }
    renderClassManagementPanel();
    renderAnnotationPanel();
};
viewer.onAnnotationDeleted = (ann) => {
    if (cellPatchWorkflow?.patchFocusActive) {
        cellPatchWorkflow.removePatchLabelFromAnnotation?.(ann);
    }
    renderAnnotationPanel();
    _setSlideListMemoIndicator();
};
viewer.onAnnotationChanged = (ann) => {
    if (cellPatchWorkflow?.patchFocusActive) {
        cellPatchWorkflow.updatePatchLabelFromAnnotation?.(ann);
    }
};
viewer.onAnnotationContextMenu = (ann) => {
    _editAnnotationMemo(ann);
};

const _origDelete = viewer.deleteAnnotation.bind(viewer);
viewer.deleteAnnotation = (id) => {
    const ann = viewer.annotations.find(a => a.id === id);
    _origDelete(id);
    _annotationBulkSelection.delete(id);
    if (ann && viewer.onAnnotationDeleted) viewer.onAnnotationDeleted(ann);
};

// Cell edit popup (Alt+Click)
let _cellEditPopupEl = null;

function _clearPatchCellBulkSelection({ render = true } = {}) {
    if (!cellPatchWorkflow?.patchFocusActive) return false;
    const hadSelection = Boolean(
        _annotationBulkSelection.size ||
        viewer.selectedAnnotationId ||
        viewer._highlightedCellIdxSet ||
        viewer._highlightedHiddenCellIdxSet
    );
    _annotationBulkSelection = new Set();
    viewer.selectedAnnotationId = null;
    viewer.annotations?.forEach(ann => { ann.selected = false; });
    if (viewer._highlightedCellIdxSet) viewer._highlightedCellIdxSet = null;
    if (viewer._highlightedHiddenCellIdxSet) viewer._highlightedHiddenCellIdxSet = null;
    viewer._highlightedCellIdx = -1;
    if (render && hadSelection) {
        viewer.requestRender?.();
        renderClassManagementPanel();
        renderAnnotationPanel();
    }
    return hadSelection;
}

function _closeCellEditPopup(options = {}) {
    const bool_clear_patch_selection = options.clearPatchSelection !== false;
    if (_cellEditPopupEl) {
        _cellEditPopupEl.remove();
        _cellEditPopupEl = null;
    }
    if (bool_clear_patch_selection && _cellEditCtx?.patchAnnotations) {
        _clearPatchCellBulkSelection({ render: false });
    }
    if (bool_clear_patch_selection) {
        viewer.clearCellHighlight();
        viewer.clearMultiCellHighlight();
        viewer.clearHiddenCellHighlight?.();
    }
    _cellEditCtx = null;
    document.removeEventListener('mousedown', _outsideCellEditClick, true);
    document.removeEventListener('keydown', _cellEditKeydown, true);
    if (bool_clear_patch_selection) {
        renderClassManagementPanel();
        renderAnnotationPanel();
    }
}

function _outsideCellEditClick(e) {
    if (_cellEditPopupEl && !_cellEditPopupEl.contains(e.target)) {
        _closeCellEditPopup({ clearPatchSelection: false });
    }
}

let _cellEditCtx = null; // {idx, classNames, classColors}

function _cellEditKeydown(e) {
    if (!_cellEditCtx) return;
    if (e.key === 'Escape') {
        _closeCellEditPopup({ clearPatchSelection: false });
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
    if (_cellEditCtx.patchAnnotations) {
        if (_blockPatchCellEditAction()) return;
        viewer.pushAnnotationUndo?.();
        const idSet = new Set(_cellEditCtx.annotationIds || []);
        const indices = _cellEditCtx.multi && idSet.size
            ? (viewer.annotations || []).map((ann, idx) => idSet.has(ann.id) ? idx : -1).filter(idx => idx >= 0)
            : _cellEditCtx.multi
            ? [..._cellEditCtx.indices]
            : [_cellEditCtx.idx];
        const removeSet = new Set(indices.filter(idx => idx >= 0 && idx < viewer.annotations.length));
        const removed = (viewer.annotations || []).filter((_, idx) => removeSet.has(idx));
        viewer.annotations = (viewer.annotations || []).filter((_, idx) => !removeSet.has(idx));
        if (removed.some(ann => ann.id === viewer.selectedAnnotationId)) viewer.selectedAnnotationId = null;
        _removePatchLabelsForAnnotations(removed);
        _annotationBulkSelection = new Set();
        viewer.requestRender();
        renderClassManagementPanel();
        renderAnnotationPanel();
        _closeCellEditPopup();
        return;
    }
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
    if (_cellEditCtx.patchAnnotations) {
        if (_blockPatchCellEditAction()) return;
        viewer.pushAnnotationUndo?.();
        const idSet = new Set(_cellEditCtx.annotationIds || []);
        const currentSelectionIds = _selectedPatchCellAnnotationIds();
        const effectiveIds = currentSelectionIds.size ? currentSelectionIds : idSet;
        const annotations = _cellEditCtx.multi && effectiveIds.size
            ? (viewer.annotations || []).filter(ann => effectiveIds.has(ann.id))
            : _cellEditCtx.multi && idSet.size
            ? (viewer.annotations || []).filter(ann => idSet.has(ann.id))
            : (_cellEditCtx.multi ? _cellEditCtx.indices : [_cellEditCtx.idx])
                .map(idx => viewer.annotations[idx])
                .filter(Boolean);
        const selectedIds = new Set(annotations.map(ann => ann.id).filter(Boolean));
        for (const ann of annotations) {
            _applyClassToAnnotation(ann, newClsId);
        }
        _syncPatchEditorAfterViewerAnnotationEdit();
        _annotationBulkSelection = selectedIds;
        _syncPatchCellHighlightFromBulkSelection();
        viewer.requestRender();
        renderClassManagementPanel();
        renderAnnotationPanel();
        _closeCellEditPopup({ clearPatchSelection: false });
        return;
    }
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
    // Refresh panel, cards, and status immediately.
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

    // Header
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
    // Show when Alt is held, a sticky class is available, detection exists, and drawing mode is off.
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

    // Header
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>${listIndices.length} ${isHiddenOther ? 'Other cells selected' : 'cells selected'}</b>`;
    header.appendChild(headerLabel);
    popup.appendChild(header);
    _makeCellEditPopupDraggable(popup, header);

    // Show per-class counts.
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

function _showPatchCellEditPopup(idx, ann, screenX, screenY) {
    if (!cellPatchWorkflow?.patchFocusActive || !cellPatchWorkflow.canAnnotateSelectedPatch?.()) return;
    const selectedId = ann?.id || viewer.annotations?.[idx]?.id;
    _closeCellEditPopup({ clearPatchSelection: false });
    _annotationBulkSelection = selectedId ? new Set([selectedId]) : new Set();
    _syncPatchCellHighlightFromBulkSelection();
    renderClassManagementPanel();
    renderAnnotationPanel();
}

function _showPatchMultiCellEditPopup(indices, annotations, screenX, screenY) {
    if (!cellPatchWorkflow?.patchFocusActive || !cellPatchWorkflow.canAnnotateSelectedPatch?.()) return;
    _closeCellEditPopup({ clearPatchSelection: false });
    if (!Array.isArray(indices) || !indices.length) {
        _annotationBulkSelection = new Set();
        viewer.selectedAnnotationId = null;
        viewer.annotations?.forEach(ann => { ann.selected = false; });
        viewer._highlightedCellIdxSet = null;
        viewer._highlightedHiddenCellIdxSet = null;
        viewer._highlightedCellIdx = -1;
        viewer.requestRender?.();
        renderClassManagementPanel();
        renderAnnotationPanel();
        return;
    }
    const selectedIds = new Set();
    for (const idx of indices) {
        const ann = viewer.annotations?.[idx];
        if (ann?.id) selectedIds.add(ann.id);
    }
    _annotationBulkSelection = selectedIds;
    _syncPatchCellHighlightFromBulkSelection();
    renderClassManagementPanel();
    renderAnnotationPanel();
}

viewer.onPatchCellEditRequested = _showPatchCellEditPopup;
viewer.onPatchCellsMultiEditRequested = _showPatchMultiCellEditPopup;

viewer.onCellEdited = () => {
    if (_lastDetectionResult) {
        _lastDetectionResult.cells = viewer.detectionCells;
        _lastDetectionResult.total_cells = viewer.detectionCells.length;
        _lastDetectionResult.excluded_cells = viewer.hiddenDetectionCells || [];
        buildResultList(_lastDetectionResult);
        _updateResultCounts();
    }
    setStatus(`Cell edited - ${viewer.detectionCells.length} cells`);
    renderAnnotationPanel();
};

// Cell edit undo / redo (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y).
window.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (cellPatchWorkflow && key === 'z' && !e.shiftKey && cellPatchWorkflow.canUndoRequiredRegion?.()) {
        _closeCellEditPopup();
        cellPatchWorkflow.undoLastRequiredRegion().catch((err) => {
            setStatus(`Required region undo failed: ${err.message}`);
        });
        e.preventDefault();
        e.stopImmediatePropagation();
        return;
    }
    if (key === 'z' && !e.shiftKey && viewer.canUndoAnnotationEdit?.()) {
        _closeCellEditPopup();
        viewer.undoAnnotationEdit();
        _syncPatchEditorAfterViewerAnnotationEdit();
        renderAnnotationPanel();
        _setSlideListMemoIndicator();
        setStatus(`Undo - ${viewer.annotations.length} annotations`);
        e.preventDefault();
        e.stopImmediatePropagation();
        return;
    }
    if (((key === 'z' && e.shiftKey) || key === 'y') && viewer.canRedoAnnotationEdit?.()) {
        _closeCellEditPopup();
        viewer.redoAnnotationEdit();
        _syncPatchEditorAfterViewerAnnotationEdit();
        renderAnnotationPanel();
        _setSlideListMemoIndicator();
        setStatus(`Redo - ${viewer.annotations.length} annotations`);
        e.preventDefault();
        e.stopImmediatePropagation();
        return;
    }

    if (!viewer || !viewer.detectionCells || viewer.detectionCells.length === 0 && !viewer.canUndoCellEdit?.()) return;

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
    _setSlideListMemoIndicator();
    setStatus('Annotations cleared');
});

// Annotation save/load (download/upload).
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

function _serializeAnnotations() {
    const sourceAnnotations = (ANNOTATION_PAGE_KIND === 'cell' && cellPatchWorkflow?.patchFocusActive)
        ? []
        : viewer.annotations;
    return sourceAnnotations.map((ann, index) => ({
        id: index + 1,
        type: _TYPE_TO_LABEL[ann.type] || 'Polygon',
        coordinates: (ann.coordinates || []).map(p => [p[0], p[1]]),
        color: _normalizeColor(ann.color),
        class_id: ann.class_id || ann.properties?.class_id || '',
        class_name: ann.class_name || ann.properties?.class_name || '',
        memo: _annotationMemo(ann),
        memo_history: _annotationMemoHistory(ann),
        group: ann.group || 'default',
        visible: ann.visible !== false,
        source: ann.source || ann.properties?.source || '',
        properties: { ...(ann.properties || {}), annotation_id: index + 1 },
    }));
}

function _normalizeLoadedAnnotations(list) {
    const loaded = [];
    let counter = 0;
    for (const item of Array.isArray(list) ? list : []) {
        if (!item) continue;
        if (item.type === '__meta__' || item.kind === 'annotation_meta') continue;
        const source = String(item.source || item.properties?.source || '');
        if (ANNOTATION_PAGE_KIND === 'cell' && /patch.*annotation|manual_patch_annotation/i.test(source)) continue;
        const coords = item.coordinates || item.points;
        if (!Array.isArray(coords)) continue;
        counter++;
        const typeRaw = (item.type || 'polygon').toString().toLowerCase();
        const type = _LABEL_TO_TYPE[typeRaw] || 'polygon';
        const classId = item.class_id || item.classId || item.properties?.class_id || '';
        const cls = classId ? _getAnnotationClass(classId) : null;
        loaded.push({
            id: item.id || crypto.randomUUID?.() || `${Date.now()}_${counter}`,
            name: String(counter),
            type,
            coordinates: coords.map(p => [Number(p[0]), Number(p[1])]),
            color: cls ? _normalizeColor(cls.color) : _normalizeColor(item.color),
            class_id: cls?.id || classId,
            class_name: cls?.name || item.class_name || item.className || item.properties?.class_name || '',
            group: item.group || 'default',
            visible: item.visible !== false,
            selected: false,
            memo: item.memo || item.properties?.memo || '',
            memo_history: _normalizeMemoHistory(item.memo_history || item.memoHistory || item.properties?.memo_history),
            source: item.source || item.properties?.source || '',
            properties: {
                ...(item.properties || {}),
                class_id: cls?.id || classId,
                class_name: cls?.name || item.class_name || item.className || item.properties?.class_name || '',
                memo: item.memo || item.properties?.memo || '',
                memo_history: _normalizeMemoHistory(item.memo_history || item.memoHistory || item.properties?.memo_history),
                source: item.source || item.properties?.source || '',
            },
        });
    }
    return loaded;
}

function _splitAnnotationPayload(payload) {
    if (Array.isArray(payload)) {
        const meta = payload.find(item => item && (item.type === '__meta__' || item.kind === 'annotation_meta')) || {};
        return {
            annotations: payload.filter(item => !(item && (item.type === '__meta__' || item.kind === 'annotation_meta'))),
            slideMemo: String(meta.slide_memo ?? meta.memo ?? meta.properties?.slide_memo ?? '').trim(),
            slideMemoHistory: _normalizeMemoHistory(meta.slide_memo_history || meta.properties?.slide_memo_history),
        };
    }
    return {
        annotations: payload?.annotations || [],
        slideMemo: String(payload?.slide_memo || payload?.memo || '').trim(),
        slideMemoHistory: _normalizeMemoHistory(payload?.slide_memo_history || payload?.memo_history),
    };
}

function _applyLoadedAnnotations(list, label = 'saved annotations') {
    const loaded = _normalizeLoadedAnnotations(list);
    viewer.annotations = loaded;
    viewer._annotationCounter = loaded.length;
    viewer.selectedAnnotationId = null;
    viewer.clearAnnotationUndo?.();
    viewer.requestRender();
    renderAnnotationPanel();
    _setSlideListMemoIndicator();
    _syncSlideMemoButton();
    setStatus(loaded.length ? `Loaded ${loaded.length} ${label}` : 'No saved annotations');
}

async function _saveAnnotationsToServer() {
    if (!currentSlideId) {
        setStatus('Open a slide before saving annotations');
        return;
    }
    if (ANNOTATION_PAGE_KIND === 'cell' && cellPatchWorkflow?.patchFocusActive) {
        await cellPatchWorkflow.saveSelectedPatchAnnotations({ complete: false });
        renderAnnotationPanel();
        _syncAnnotationStatusControl(currentAnnotationStatus);
        return;
    }
    const annotations = _serializeAnnotations();
    const payload = [
        {
            type: '__meta__',
            kind: 'annotation_meta',
            memo: currentSlideMemo || '',
            slide_memo: currentSlideMemo || '',
            slide_memo_history: _normalizeMemoHistory(currentSlideMemoHistory),
            properties: {
                slide_memo: currentSlideMemo || '',
                slide_memo_history: _normalizeMemoHistory(currentSlideMemoHistory),
            },
        },
        ...annotations,
    ];
    await api.saveAnnotations(currentSlideId, payload);
    _setSlideListMemoIndicator();
    setStatus(`Annotations saved internally (${annotations.length} items)`);
}

window.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    if (e.key.toLowerCase() === 'm') {
        e.preventDefault();
        _editCurrentMemo();
        return;
    }
    if (e.key.toLowerCase() !== 's') return;
    e.preventDefault();
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    _saveAnnotationsToServer().catch(err => alert(`Failed to save annotations: ${err.message}`));
}, true);

async function _loadSavedAnnotationsForSlide(slideId) {
    const strSlideId = slideId || currentSlideId;
    if (!strSlideId) return;
    viewer.clearAnnotations();
    renderAnnotationPanel();
    try {
        const payload = await api.loadAnnotations(strSlideId);
        if (currentSlideId !== strSlideId) return;
        const parsed = _splitAnnotationPayload(payload);
        currentSlideMemo = parsed.slideMemo;
        currentSlideMemoHistory = parsed.slideMemoHistory;
        if (ANNOTATION_PAGE_KIND === 'cell') {
            _applyLoadedAnnotations([], 'saved annotations');
            return;
        }
        _applyLoadedAnnotations(parsed.annotations, 'saved annotations');
    } catch (err) {
        if (currentSlideId !== strSlideId) return;
        console.warn('Saved annotation load failed:', err);
        setStatus(`Annotation auto-load failed: ${err.message}`);
    }
}

async function _downloadAnnotations() {
    if (!viewer.annotations.length) {
        setStatus('No annotations to save');
        return;
    }
    const payload = {
        slide_memo: currentSlideMemo || '',
        slide_memo_history: _normalizeMemoHistory(currentSlideMemoHistory),
        annotations: viewer.annotations.map((ann, index) => ({
            id: index + 1,
            type: _TYPE_TO_LABEL[ann.type] || 'Polygon',
            coordinates: (ann.coordinates || []).map(p => [p[0], p[1]]),
            color: _normalizeColor(ann.color),
            class_id: ann.class_id || ann.properties?.class_id || '',
            class_name: ann.class_name || ann.properties?.class_name || '',
            memo: _annotationMemo(ann),
            memo_history: _annotationMemoHistory(ann),
            group: ann.group || 'default',
            visible: ann.visible !== false,
            properties: { ...(ann.properties || {}), annotation_id: index + 1 },
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

            // Fallback to a regular browser download.
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
                const split = _splitAnnotationPayload(parsed);
                const list = split.annotations;
                if (!Array.isArray(list)) {
                    setStatus('Invalid file format.');
                    return;
                }
                currentSlideMemo = split.slideMemo;
                currentSlideMemoHistory = split.slideMemoHistory;
                const loaded = _normalizeLoadedAnnotations(list);
                viewer.annotations = loaded;
                viewer._annotationCounter = loaded.length;
                viewer.selectedAnnotationId = null;
                viewer.requestRender();
                renderAnnotationPanel();
                _setSlideListMemoIndicator();
                setStatus(`ROI loaded: ${file.name} (${loaded.length} items)`);
            } catch (err) {
                setStatus(`Failed to load ROI: ${err.message}`);
            }
        };
        reader.readAsText(file, 'utf-8');
    });
    input.click();
}

$btnAnnSave?.addEventListener('click', async () => {
    if (_blockViewerAction('Viewer role cannot use annotation features.')) return;
    try {
        await _saveAnnotationsToServer();
    } catch (err) {
        alert(`Failed to save annotations: ${err.message}`);
    }
});
if (false) $btnAnnLoad?.addEventListener('click', () => {
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
    if (typeof _lastBrowseData !== 'undefined') {
        const slide = (_lastBrowseData.slides || []).find((item) => item.slide_id === slideId);
        const targetCase = caseName || slide?.case_name || '';
        const listTargets = (_lastBrowseData.slides || []).filter((item) => (
            targetCase ? item.case_name === targetCase : item.slide_id === slideId
        ));
        listTargets.forEach((itemSlide) => {
            itemSlide.clinical_info = clinicalInfo || {};
            itemSlide.has_clinical_info = hasClinical;
        });
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

// Slide information dialog
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

// AI run helpers

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
    // If the task id is still only known by the server and the user cancels:
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
    return true;  // Skip the start flow after the task is queued.
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

        // Polling
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
        // Confidence thresholds use fixed SaMD reproducibility values.
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
                    // Reload the dialog.
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
    if (aiMode === 'Quanti HE') {
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

// Utilities
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

// Left panel resize
const $leftPanel = $('#left-panel');
const $resizer = $('#left-panel-resizer');
const $rightPanel = $('#right-panel');
const $rightResizer = $('#right-panel-resizer');
const LEFT_PANEL_MIN_W = 260;
const LEFT_PANEL_MAX_W = 500;
const LEFT_PANEL_COLLAPSE_W = Math.floor(LEFT_PANEL_MIN_W / 2);
const LEFT_PANEL_DEFAULT_W = 260;
const RIGHT_PANEL_MIN_W = 360;
const RIGHT_PANEL_MAX_W = 600;
const RIGHT_PANEL_COLLAPSE_W = Math.floor(RIGHT_PANEL_MIN_W / 2);
const RIGHT_PANEL_DEFAULT_W = 380;

function _resizeViewerCanvasSoon() {
    if (viewer && typeof viewer._resizeCanvas === 'function') {
        viewer._resizeCanvas();
    }
}

function _setLeftPanelCollapsed(collapsed) {
    document.body.classList.toggle('left-panel-collapsed', !!collapsed);
    localStorage.setItem('leftPanelCollapsed', collapsed ? '1' : '0');
    _resizeViewerCanvasSoon();
}

function _setRightPanelCollapsed(collapsed) {
    document.body.classList.toggle('right-panel-collapsed', !!collapsed);
    localStorage.setItem('rightPanelCollapsed', collapsed ? '1' : '0');
    _resizeViewerCanvasSoon();
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

$resizer.addEventListener('mousedown', (e) => {
    e.preventDefault();
    $resizer.classList.add('dragging');
    const startX = e.clientX;
    const storedW = parseInt(localStorage.getItem('leftPanelWidth') || '', 10);
    const startW = document.body.classList.contains('left-panel-collapsed')
        ? 0
        : ($leftPanel.offsetWidth || (Number.isFinite(storedW) ? storedW : LEFT_PANEL_DEFAULT_W));

    function onMove(ev) {
        const rawW = startW + ev.clientX - startX;
        if (rawW < LEFT_PANEL_COLLAPSE_W) {
            _setLeftPanelCollapsed(true);
            return;
        }
        _setLeftPanelCollapsed(false);
        const w = Math.max(LEFT_PANEL_MIN_W, Math.min(LEFT_PANEL_MAX_W, rawW));
        document.documentElement.style.setProperty('--left-panel-w', `${w}px`);
        localStorage.setItem('leftPanelWidth', String(w));
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

$resizer.addEventListener('dblclick', () => {
    const collapsed = document.body.classList.contains('left-panel-collapsed');
    if (!collapsed) {
        _setLeftPanelCollapsed(true);
        return;
    }
    document.documentElement.style.setProperty('--left-panel-w', `${LEFT_PANEL_DEFAULT_W}px`);
    localStorage.setItem('leftPanelWidth', String(LEFT_PANEL_DEFAULT_W));
    _setLeftPanelCollapsed(false);
});

if ($rightResizer && $rightPanel) {
    $rightResizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        $rightResizer.classList.add('dragging');
        const startX = e.clientX;
        const storedW = parseInt(localStorage.getItem('rightPanelWidth') || '', 10);
        const startW = document.body.classList.contains('right-panel-collapsed')
            ? 0
            : ($rightPanel.offsetWidth || (Number.isFinite(storedW) ? storedW : RIGHT_PANEL_DEFAULT_W));

        function onMove(ev) {
            const int_left_w = $leftPanel ? $leftPanel.offsetWidth : 0;
            const int_max_by_viewport = Math.max(RIGHT_PANEL_MIN_W, window.innerWidth - int_left_w - 360);
            const int_max = Math.min(RIGHT_PANEL_MAX_W, int_max_by_viewport);
            const rawW = startW - (ev.clientX - startX);
            if (rawW < RIGHT_PANEL_COLLAPSE_W) {
                _setRightPanelCollapsed(true);
                return;
            }
            _setRightPanelCollapsed(false);
            const w = Math.max(RIGHT_PANEL_MIN_W, Math.min(int_max, rawW));
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
    $rightResizer.addEventListener('dblclick', () => {
        const collapsed = document.body.classList.contains('right-panel-collapsed');
        if (!collapsed) {
            _setRightPanelCollapsed(true);
            return;
        }
        document.documentElement.style.setProperty('--right-panel-w', `${RIGHT_PANEL_DEFAULT_W}px`);
        localStorage.setItem('rightPanelWidth', String(RIGHT_PANEL_DEFAULT_W));
        _setRightPanelCollapsed(false);
    });
}

let currentBrowsePath = '';  // Path relative to uploads/.
let _projectListCache = [];
let _projectGatePage = 1;
let _projectGateSort = { key: 'name', dir: 'asc' };
const $breadcrumb = $('#folder-breadcrumb');

function _getCurrentProjectName() {
    return (currentBrowsePath || '').split('/').filter(Boolean)[0] || '';
}

function _isPdL1StCellAnnotationProject() {
    if (ANNOTATION_PAGE_KIND !== 'cell') return false;
    const projectPath = _getCurrentProjectName();
    const project = (_projectListCache || []).find(item =>
        (item?.path || item?.name || '') === projectPath
    );
    const title = String(
        project?.info?.title ||
        project?.info?.str_title ||
        project?.title ||
        ''
    ).trim().toLowerCase();
    return title === 'pd-l1(st)' || projectPath === 'IHC(PD-L1)';
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
    if (key === 'annotation') return Number(project.annotation_count ?? project.reviewed_count ?? 0);
    if (key === 'review') return Number(project.review_count ?? project.termination_count ?? 0);
    if (key === 'termination') return Number(project.termination_count || 0);
    if (key === 'folders') return Number(project.folder_count || 0);
    if (key === 'status') return info.status || 'active';
    return '';
}

function _bumpCurrentProjectWorkflowCount(stage) {
    const strProject = _getCurrentProjectName();
    if (!strProject) return;
    const project = _projectListCache.find(p => (p.path || p.name) === strProject);
    if (!project) return;
    const strKey = `${stage}_count`;
    project[strKey] = Number(project[strKey] || 0) + 1;
    if (stage === 'annotation') {
        project.reviewed_count = Math.max(Number(project.reviewed_count || 0), Number(project.annotation_count || 0));
    }
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
            dir: ['slides', 'annotation', 'review', 'termination', 'folders'].includes(key) ? 'desc' : 'asc',
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
        { label: 'Annotation', key: 'annotation' },
        { label: 'Review', key: 'review' },
        { label: 'Termination', key: 'termination' },
        { label: 'Folders', key: 'folders' },
        { label: 'Status', key: 'status' },
        { label: 'Actions', key: '' },
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

        const row = document.createElement('div');
        row.setAttribute('role', 'button');
        row.tabIndex = 0;
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

        const annotationEl = document.createElement('div');
        annotationEl.className = 'project-gate-cell project-gate-number';
        annotationEl.textContent = _projectGateValue(project, 'annotation');

        const reviewEl = document.createElement('div');
        reviewEl.className = 'project-gate-cell project-gate-number';
        reviewEl.textContent = _projectGateValue(project, 'review');

        const terminationEl = document.createElement('div');
        terminationEl.className = 'project-gate-cell project-gate-number';
        terminationEl.textContent = _projectGateValue(project, 'termination');

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
        actionEl.className = 'project-gate-actions';
        const openBtn = document.createElement('button');
        openBtn.type = 'button';
        openBtn.className = 'project-gate-action';
        openBtn.textContent = 'Open';
        const classBtn = document.createElement('button');
        classBtn.type = 'button';
        classBtn.className = 'project-gate-action secondary';
        classBtn.textContent = ANNOTATION_PAGE_KIND === 'cell' ? 'Setting' : 'Classes';
        classBtn.disabled = !_canManageAnnotationClasses();
        classBtn.title = _canManageAnnotationClasses()
            ? (ANNOTATION_PAGE_KIND === 'cell' ? 'Manage Cell Annotation settings' : 'Manage classes')
            : 'Doctor/Admin only';
        actionEl.append(openBtn, classBtn);
        if (ANNOTATION_PAGE_KIND === 'cell' && _isYoungSeopLeeAccount()) {
            const exportBtn = document.createElement('button');
            exportBtn.type = 'button';
            exportBtn.className = 'project-gate-action secondary';
            exportBtn.textContent = 'Download ZIP';
            exportBtn.title = 'Download termination-completed patches and paired JSON files';
            exportBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                exportBtn.disabled = true;
                setStatus('Preparing termination-completed patch ZIP...');
                try {
                    const result = await api.downloadTerminationCompletedCellPatches(path);
                    setStatus(`Downloaded ${result.filename}`);
                } catch (err) {
                    setStatus(`Termination export failed: ${err.message}`);
                } finally {
                    exportBtn.disabled = false;
                }
            });
            actionEl.appendChild(exportBtn);
        }
        actionEl.addEventListener('click', (e) => e.stopPropagation());

        row.append(projectEl, hospitalEl, ownerEl, slidesEl, annotationEl, reviewEl, terminationEl, foldersEl, statusEl, actionEl);
        row.addEventListener('click', () => _enterProjectFromGate(path));
        row.addEventListener('keydown', (e) => {
            if (e.target !== row) return;
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                _enterProjectFromGate(path);
            }
        });
        openBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            _enterProjectFromGate(path);
        });
        classBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            _openProjectClassManager(project);
        });
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
    history.replaceState(null, '', `${ANNOTATION_PAGE_ROUTE}?path=${encodeURIComponent(path)}`);
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
        await _loadAnnotationClassesForCurrentProject();
        const data = await api.browse(currentBrowsePath);
        if (ANNOTATION_PAGE_KIND === 'cell') _cellPatchProjectSummaries.clear();
        $slideList.innerHTML = '';
        _appendAnnotationSlideListHeader();
        _syncProjectSelect();

        if (data.folders.length === 0 && data.slides.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'slide-list-empty';
            empty.textContent = 'Empty';
            $slideList.appendChild(empty);
        }

        for (const f of data.folders) {
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
            item.addEventListener('dragover', (e) => { e.preventDefault(); item.classList.add('drag-over'); });
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

        for (const s of data.slides) {
            const item = document.createElement('div');
            item.className = 'slide-list-item';
            const strRawSlideStatus = ANNOTATION_PAGE_KIND === 'cell'
                ? ''
                : (_browseAnnotationStatus(s) || 'annotation');
            const strSlideStatus = _normalizeAnnotationWorkflowStatus(strRawSlideStatus);
            item.classList.add(`status-${strSlideStatus}`);
            item.dataset.filename = s.filename;
            item.dataset.slideId = s.slide_id;
            item.dataset.status = strRawSlideStatus;
            item.dataset.workflowStatus = strSlideStatus;
            item.dataset.hasMemo = s.annotation_summary?.has_memo ? '1' : '';
            item.classList.toggle('has-memo', Boolean(s.annotation_summary?.has_memo));
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

            item.append(thumb, name);
            if (s.annotation_summary?.has_memo) {
                const memoBadge = document.createElement('span');
                memoBadge.className = 'slide-memo-badge';
                memoBadge.title = 'Memo exists';
                memoBadge.textContent = 'M';
                item.appendChild(memoBadge);
            }

            if (ANNOTATION_PAGE_KIND === 'cell') {
                const summaries = cellPatchWorkflow?.slideId === s.slide_id
                    ? cellPatchWorkflow.getWsiStepSummaries?.()
                    : (s.cell_annotation_summary || _emptyCellPatchWorkflowSummaries());
                _setCellPatchProjectSummary(s.slide_id, summaries, { render: false });
                _renderCellPatchWorkflowCells(item, summaries);
            } else {
                _renderAnnotationWorkflowCells(item, strRawSlideStatus);
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
                    // Shift: range selection
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
                e.dataTransfer.setData('text/filename', selectedFiles[0]); // Compatibility payload
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
    } catch (err) {
        console.error('Slide list load failed:', err);
    }
}

let _aiActivePollTimer = null;
function _startAiActivePolling() {
    if (_isAnnotationPage()) {
        _stopAiActivePolling();
        return;
    }
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
    if (_isAnnotationPage()) {
        $slideList?.querySelectorAll('.slide-ai-active').forEach(el => el.remove());
        return;
    }

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
        } else if (existing) {
            existing.remove();
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
    // Move multiple files
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
    _renderCellPatchProjectProgress();
}

let _openSlideAbortController = null;
let _openSlideSeq = 0;

async function openSavedSlide(filename, itemEl) {
    _openSlideAbortController?.abort();
    const controller = new AbortController();
    _openSlideAbortController = controller;
    const seq = ++_openSlideSeq;
    setStatus('Opening...');
    try {
        const info = await api.openSlide(filename, currentBrowsePath, '', { signal: controller.signal });
        if (seq !== _openSlideSeq || controller.signal.aborted) return;
        if (info.exists) {
            $slideList.querySelectorAll('.slide-list-item').forEach(el => el.classList.remove('active'));
            if (itemEl) itemEl.classList.add('active');
            onSlideLoaded(info.slide_id, info, filename);
        }
    } catch (err) {
        if (err?.name === 'AbortError') return;
        setStatus(`Move failed: ${err.message}`);
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

    menu.append(renameBtn, deleteBtn);
    document.body.appendChild(menu);
    _ctxMenu = menu;
}

function _getSelectedSlideFilenames() {
    return [...$slideList.querySelectorAll('.slide-list-item.selected:not(.folder-item)')]
        .map(el => el.dataset.filename)
        .filter(Boolean);
}

const SLIDE_STATUS_OPTIONS = [
    { value: 'annotation',  label: 'Annotation',  color: '#f4b400' },
    { value: 'review',      label: 'Review',      color: '#2ecc71' },
    { value: 'termination', label: 'Termination', color: '#6c5ce7' },
];

function _annotationWorkflowLabel(status) {
    const strStatus = _normalizeAnnotationWorkflowStatus(status);
    return SLIDE_STATUS_OPTIONS.find(opt => opt.value === strStatus)?.label || strStatus;
}

async function _moveAnnotationWorkflowStatusDirect(strRequestedStatus) {
    const strTargetStatus = _normalizeAnnotationWorkflowStatus(strRequestedStatus || 'annotation');
    const strLabel = _annotationWorkflowLabel(strTargetStatus);
    if (!confirm(`Change annotation status to "${strLabel}"?`)) {
        _syncAnnotationStatusControl(currentAnnotationStatus);
        return;
    }

    const strPrevStatus = currentAnnotationStatus || '';
    const strPrevRunningStep = _annotationRunningStep || '';
    const boolPrevFinished = _annotationWorkflowFinished;
    _annotationStatusSaving = true;
    _syncAnnotationStatusControl(currentAnnotationStatus);
    try {
        const strStorageStatus = _annotationWorkflowStorageStatus(strTargetStatus);
        await _saveAnnotationWorkflowStorageStatus(currentSlideFilename, strStorageStatus);
        currentAnnotationStatus = strTargetStatus;
        _annotationRunningStep = '';
        _annotationWorkflowFinished = false;
        _setSlideListItemAnnotationStatus(currentSlideFilename, strStorageStatus);
        setStatus(`Annotation status changed to ${strLabel}: ${currentSlideFilename}`);
    } catch (err) {
        currentAnnotationStatus = strPrevStatus;
        _annotationRunningStep = strPrevRunningStep;
        _annotationWorkflowFinished = boolPrevFinished;
        alert(`Failed to update annotation status: ${err.message}`);
    } finally {
        _annotationStatusSaving = false;
        _syncAnnotationStatusControl(currentAnnotationStatus);
    }
}

async function _applyAnnotationWorkflowStatusToCurrent(strRequestedStatus) {
    if (!currentSlideFilename) {
        _syncAnnotationStatusControl('');
        return;
    }
    if (_blockViewerAction()) {
        _syncAnnotationStatusControl(currentAnnotationStatus);
        return;
    }
    const strNextStatus = _normalizeAnnotationWorkflowStatus(strRequestedStatus || 'annotation');
    if (_isLabelerRole()) {
        const boolCellWsiLocked = ANNOTATION_PAGE_KIND === 'cell' && !cellPatchWorkflow?.patchFocusActive;
        const strCurrentStatus = _normalizeAnnotationWorkflowStatus(currentAnnotationStatus);
        const boolWorkflowLocked = _annotationRunningStep === 'review' ||
            _annotationRunningStep === 'termination' ||
            strCurrentStatus === 'review' ||
            strCurrentStatus === 'termination' ||
            _annotationWorkflowFinished;
        if (boolCellWsiLocked || strNextStatus !== 'annotation' || boolWorkflowLocked) {
            setStatus('Labeler role can change annotation status only before review or termination starts.');
            _syncAnnotationStatusControl(currentAnnotationStatus);
            return;
        }
    }
    if (strNextStatus !== _normalizeAnnotationWorkflowStatus(currentAnnotationStatus) || _annotationWorkflowFinished) {
        await _moveAnnotationWorkflowStatusDirect(strNextStatus);
        return;
    }
    if (_annotationRunningStep !== strNextStatus) {
        const strRunningStorageStatus = _annotationWorkflowRunningStorageStatus(strNextStatus);
        const strPrevStatus = currentAnnotationStatus || '';
        const strPrevRunningStep = _annotationRunningStep || '';
        const boolPrevFinished = _annotationWorkflowFinished;
        _annotationStatusSaving = true;
        _syncAnnotationStatusControl(currentAnnotationStatus);
        try {
            await _saveAnnotationWorkflowStorageStatus(currentSlideFilename, strRunningStorageStatus);
            currentAnnotationStatus = strRunningStorageStatus;
            _annotationRunningStep = strNextStatus;
            _annotationWorkflowFinished = false;
            _setSlideListItemAnnotationStatus(currentSlideFilename, strRunningStorageStatus);
            setStatus(`Annotation status in progress: ${currentSlideFilename}`);
        } catch (err) {
            currentAnnotationStatus = strPrevStatus;
            _annotationRunningStep = strPrevRunningStep;
            _annotationWorkflowFinished = boolPrevFinished;
            alert(`Failed to update annotation status: ${err.message}`);
        } finally {
            _annotationStatusSaving = false;
            _syncAnnotationStatusControl(currentAnnotationStatus);
        }
        return;
    }
    const strCompletedStatus = strNextStatus;
    const strTargetStatus = _nextAnnotationWorkflowStatus(strCompletedStatus);
    const strNextStorageStatus = _annotationWorkflowCompleteStorageStatus(strCompletedStatus);
    const strPrevStatus = currentAnnotationStatus || '';
    _annotationStatusSaving = true;
    _syncAnnotationStatusControl(currentAnnotationStatus);
    try {
        await _saveAnnotationWorkflowStorageStatus(currentSlideFilename, strNextStorageStatus);
        currentAnnotationStatus = strTargetStatus;
        _annotationRunningStep = '';
        _annotationWorkflowFinished = strCompletedStatus === 'termination';
        _bumpCurrentProjectWorkflowCount(strCompletedStatus);
        _setSlideListItemAnnotationStatus(currentSlideFilename, strNextStorageStatus);
        setStatus(`Annotation status updated: ${currentSlideFilename}`);
    } catch (err) {
        currentAnnotationStatus = strPrevStatus;
        _annotationRunningStep = strCompletedStatus;
        alert(`Failed to update annotation status: ${err.message}`);
    } finally {
        _annotationStatusSaving = false;
        _syncAnnotationStatusControl(currentAnnotationStatus);
    }
}

async function _markAnnotationWorkflowInProgressIfIdle() {
    if (!currentSlideFilename || _isViewerRole() || _annotationStatusSaving) return false;
    const strCurrentStatus = currentAnnotationStatus || 'pending';
    if (_normalizeAnnotationWorkflowStatus(strCurrentStatus) !== 'annotation') return false;
    if (_annotationRunningStep === 'annotation') return false;
    if (_annotationWorkflowFinished) return false;

    const strPrevStatus = currentAnnotationStatus || '';
    const strPrevRunningStep = _annotationRunningStep || '';
    const boolPrevFinished = _annotationWorkflowFinished;
    const strRunningStorageStatus = _annotationWorkflowRunningStorageStatus('annotation');
    _annotationStatusSaving = true;
    _syncAnnotationStatusControl(currentAnnotationStatus);
    try {
        await _saveAnnotationWorkflowStorageStatus(currentSlideFilename, strRunningStorageStatus);
        currentAnnotationStatus = strRunningStorageStatus;
        _annotationRunningStep = 'annotation';
        _annotationWorkflowFinished = false;
        _setSlideListItemAnnotationStatus(currentSlideFilename, strRunningStorageStatus);
        _syncAnnotationStatusControl(currentAnnotationStatus);
        return true;
    } catch (err) {
        currentAnnotationStatus = strPrevStatus;
        _annotationRunningStep = strPrevRunningStep;
        _annotationWorkflowFinished = boolPrevFinished;
        console.warn('Failed to mark annotation workflow in progress:', err);
        return false;
    } finally {
        _annotationStatusSaving = false;
        _syncAnnotationStatusControl(currentAnnotationStatus);
    }
}

$annotationStatusWorkflow?.querySelectorAll('[data-annotation-status]').forEach((btn) => {
    btn.addEventListener('click', () => {
        if ($annotationStatusWorkflow?.dataset.patchWorkflow === '1') return;
        if (ANNOTATION_PAGE_KIND === 'cell' && !cellPatchWorkflow?.patchFocusActive) return;
        if (btn.disabled) return;
        _applyAnnotationWorkflowStatusToCurrent(btn.dataset.annotationStatus);
    });
});

$annotationStatusSelect?.addEventListener('change', () => {
    _applyAnnotationWorkflowStatusToCurrent($annotationStatusSelect.value);
});

async function _applyStatusToSelected(strStatus) {
    const list_filenames = _getSelectedSlideFilenames();
    if (list_filenames.length === 0) return;
    const strWorkflowStatus = _normalizeAnnotationWorkflowStatus(strStatus);
    const strStorageStatus = _annotationWorkflowStorageStatus(strWorkflowStatus);
    try {
        await api.setFileStatus(list_filenames, strStorageStatus, currentBrowsePath, 'annotation');
        if (currentSlideFilename && list_filenames.includes(currentSlideFilename)) {
            currentAnnotationStatus = strWorkflowStatus;
            _annotationRunningStep = '';
            _annotationWorkflowFinished = false;
            _syncAnnotationStatusControl(currentAnnotationStatus);
        }
        setStatus(`Status updated: ${list_filenames.length} slide(s)`);
        loadSlideList();
    } catch (err) {
        alert(`Failed to update status: ${err.message}`);
    }
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

    // Header (selection count)
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
const VS_CELL_FIXED_TARGET_MPP = 0.5;
const VS_DEFAULT_TARGET_MPP = 2.0;
const VS_MPP_CHOICES = ANNOTATION_PAGE_KIND === 'cell'
    ? [{ value: VS_CELL_FIXED_TARGET_MPP, label: '0.5 µm/px (x20)' }]
    : [
        { value: 4.0, label: '4.0 µm/px (x2.5)' },
        { value: 2.0, label: '2.0 µm/px (x5)' },
        { value: 1.0, label: '1.0 µm/px (x10)' },
        { value: 0.5, label: '0.5 µm/px (x20)' },
    ];

async function openFolderAiConfigDialog(folderPath, folderName) {
    // Load existing settings
    let cfg = { enabled: false, tasks: [] };
    try { cfg = await api.getFolderAiConfig(folderPath); }
    catch (err) { console.warn('Folder config load failed:', err); }

    const set_selected = new Set();
    const dict_vs_mpps = {};  // { variant: Set<number> }
    for (const t of (cfg.tasks || [])) {
        if (t.model === 'VS IHC') {
            if (!dict_vs_mpps[t.variant]) dict_vs_mpps[t.variant] = new Set();
            dict_vs_mpps[t.variant].add(Number(t.target_mpp ?? (ANNOTATION_PAGE_KIND === 'cell' ? VS_CELL_FIXED_TARGET_MPP : VS_DEFAULT_TARGET_MPP)));
        } else {
            set_selected.add(`${t.model}::${t.variant}`);
        }
    }

    // Backdrop and card
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
                        const $def = wrap.querySelector(`.ai-cfg-mpp[data-mpp="${ANNOTATION_PAGE_KIND === 'cell' ? '0.5' : '2'}"]`);
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

// VS IHC (Virtual Staining)
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

    const ignoreRoiPolygons = ANNOTATION_PAGE_KIND === 'cell' && Boolean(cellPatchWorkflow?.patchFocusActive);
    const roiAnns = ignoreRoiPolygons
        ? []
        : viewer.annotations.filter(a => a.visible && a.type !== 'point' && a.coordinates.length >= 3);
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
    const tmpp = result.target_mpp || _vsLastTargetMpp || _vsMppFromSlider();
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

    const preservePatchAnnotations = ANNOTATION_PAGE_KIND === 'cell' && Boolean(cellPatchWorkflow?.patchFocusActive);
    if (!preservePatchAnnotations) {
        viewer.clearAnnotations();
        renderAnnotationPanel();
    }

    const tc = result.tissue_count || 0;
    const tot = result.total_patches || 0;
    setProgress(100);
    $progressLabel.textContent = result.cached
        ? 'Virtual staining loaded (cached)'
        : 'Virtual staining complete';
    setStatus(`Virtual staining complete - ${tc}/${tot} tissue patches`);
}

// Map VS IHC target MPP slider indices to labels.
const VS_MPP_VALUES = [4.0, 2.0, 1.0, VS_CELL_FIXED_TARGET_MPP];
const VS_MPP_LABELS = [
    '4.0 µm/px (x2.5)',
    '2.0 µm/px (x5)',
    '1.0 µm/px (x10)',
    '0.5 µm/px (x20)',
];
function _vsMppFromSlider() {
    if (ANNOTATION_PAGE_KIND === 'cell') return VS_CELL_FIXED_TARGET_MPP;
    const el = document.querySelector('#vs-target-mpp');
    const idx = el ? parseInt(el.value, 10) : 1;
    return VS_MPP_VALUES[idx] ?? VS_DEFAULT_TARGET_MPP;
}
const $vsMppSlider = document.querySelector('#vs-target-mpp');
const $vsMppLabel = document.querySelector('#vs-mpp-label');
if (ANNOTATION_PAGE_KIND === 'cell' && $vsMppSlider) {
    $vsMppSlider.value = '0';
    $vsMppSlider.disabled = true;
}
if ($vsMppLabel) {
    $vsMppLabel.textContent = ANNOTATION_PAGE_KIND === 'cell'
        ? VS_MPP_LABELS[3]
        : (VS_MPP_LABELS[parseInt($vsMppSlider?.value ?? '1', 10)] || VS_MPP_LABELS[1]);
}
$vsMppSlider?.addEventListener('input', () => {
    if (!$vsMppLabel) return;
    if (ANNOTATION_PAGE_KIND === 'cell') {
        $vsMppLabel.textContent = VS_MPP_LABELS[3];
        return;
    }
    const idx = parseInt($vsMppSlider.value, 10);
    $vsMppLabel.textContent = VS_MPP_LABELS[idx] || '';
});

const VS_PANEL_COLLAPSED_KEY = `mediauto:${ANNOTATION_PAGE_KIND}:vs-panel-collapsed`;
function _rightPanelSectionStorageKey(sectionKey) {
    if (sectionKey === 'ai') return VS_PANEL_COLLAPSED_KEY;
    return `mediauto:${ANNOTATION_PAGE_KIND}:right-panel-section:${sectionKey}:collapsed`;
}

function _setRightPanelSectionCollapsed(button, collapsed, persist = true) {
    const panel = button?.closest('.panel-group');
    if (!panel || !button) return;
    const sectionKey = button.dataset.panelCollapse || 'panel';
    const label = button.dataset.panelLabel || 'Panel';
    panel.classList.toggle('panel-group-collapsed', !!collapsed);
    if (sectionKey === 'ai') {
        panel.classList.toggle('vs-panel-collapsed', !!collapsed);
    }
    button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    button.title = collapsed ? `Expand ${label}` : `Minimize ${label}`;
    button.setAttribute('aria-label', collapsed ? `Expand ${label}` : `Minimize ${label}`);
    if (persist) {
        localStorage.setItem(_rightPanelSectionStorageKey(sectionKey), collapsed ? '1' : '0');
    }
}

function _initRightPanelSectionToggles() {
    document.querySelectorAll('.panel-minimize-btn[data-panel-collapse]').forEach((button) => {
        const sectionKey = button.dataset.panelCollapse || 'panel';
        const savedState = localStorage.getItem(_rightPanelSectionStorageKey(sectionKey));
        const defaultCollapsed = sectionKey === 'ai';
        _setRightPanelSectionCollapsed(
            button,
            savedState == null ? defaultCollapsed : savedState === '1',
            false,
        );
        button.addEventListener('click', () => {
            const panel = button.closest('.panel-group');
            const collapsed = !panel?.classList.contains('panel-group-collapsed');
            _setRightPanelSectionCollapsed(button, collapsed);
        });
    });
}

_initRightPanelSectionToggles();

$btnVsMembrane?.addEventListener('click', () => startVirtualStain('ihc_membrane'));

// Quanti PD-L1 CPS / TPS.
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

    viewer.setDetectionResults(result.cells, roiPolygons);
    viewer.setHiddenDetectionResults?.(result.excluded_cells || [], roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    if ($pdScoreResult) $pdScoreResult.hidden = false;

    // Status text is calculated from polygon ROI counts.
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
    _updateResultCounts();   // Refresh the score card from polygon ROI counts.
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
    _updateResultCounts();   // Refresh the score card from polygon ROI counts.
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
            active: ANNOTATION_HEADER_ACTIVE,
            user: { ...dict_me, str_role: normalizedRole },
            showAdmin: normalizedRole === 'admin',
            logout: () => {
                _stopAiActivePolling();
                api.logout();
            },
        });
        window.__currentUserRole = normalizedRole;
        window.__currentUserId = String(dict_me._id || '');
        window.__currentUserLoginId = String(dict_me.str_login_id || '');
        window.__currentUserName = String(dict_me.str_name || '');
        _loadAnnotationDisplayStyleFromPreferences(dict_me.dict_preferences || {});
        localStorage.setItem('user', JSON.stringify({ ...dict_me, str_role: normalizedRole }));
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
        history.replaceState(null, '', ANNOTATION_PAGE_ROUTE);
    }
})();
