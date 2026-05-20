/**
 * MeDIAuto Studio SaaS ??메인 ?? * 기존 PyQt5 viewer.py??UI 로직??JS�??�팅
 */

import { api } from './api.js';
import { TileViewer } from './tile-viewer.js?v=20260520-11';
import { showVisualization } from './visualization.js';

// ???? 미로그인 �???????
// ?�큰 ?�는 ?�태?�서 /ai �?직접 ?�어?�면 뷰어 UI �? ?�깐 그려�???api.me()
// ??401 까�? 보고?�야 리다?�렉?��? ?�어??깜빡?�이 ?�긴?? home.js ?? ?�일??// ?�턴?�로 �?줄에??차단. replace() �?history ????broken state �? ???�게.
if (!localStorage.getItem('access_token')) {
    window.location.replace('/login');
    // 모듈 본체??�?navigation ?�로 unload ?��?�? ?�후 코드�? ?�행?�면??발생?�는
    // null 참조�?막기 ?�해 명시?�으�?throw ??콘솔 ?�러 ??줄로 ?�난??
    throw new Error('Not authenticated ??redirecting to /login');
}

// HTML escape ??innerHTML ???�어�??�뢰 불�? 문자??(filename, annotation name,
// vendor ?? ??반드???�과?�켜 stored XSS 차단.
function _esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ???? DOM ?�소 ????
const $ = (sel) => document.querySelector(sel);

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

// ?�용??메뉴
const $userName = $('#user-name');
const $btnLogout = $('#btn-logout');
const $projectUserName = $('#project-user-name');
const $projectUserRole = $('#project-user-role');
const $projectBtnLogout = $('#project-btn-logout');
const $projectLinkAdmin = $('#project-link-admin');

// ?�바 버튼
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
// ?�재 뷰어???�라�?결과??AI 모드 ("Quanti HE" | "Quanti PD-L1" | "Quanti IHC")
let _lastDetectionModel = null;
// 로드??결과�?onXxxComplete �??�투?�할 ???�요??ROI (?�으�?null)
let _lastDetectionRoi = null;

function _isViewerRole() {
    return window.__currentUserRole === 'viewer';
}

function _blockViewerAction(message = 'Viewer 권한?? AI/annotation 기능???�용?????�습?�다.') {
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

// ???? ?�태 ????
let currentSlideId = null;
let currentSlideInfo = null;
let minimapImage = null;
let lastSegData = null;  // segmentation overlay data from epithelial classification

// ???? 뷰어 초기??????
const viewer = new TileViewer($canvas, $overlay);

viewer.onZoomChange = (zoom, mag, mpp) => {
    $zoomInfo.textContent = `${mag.toFixed(1)}x  |  MPP ${mpp.toFixed(3)} μm/px`;
};
viewer.onViewChange = () => updateMinimap();

// ???? ?�라?�드 초기 3-stage ?�리로드 로딩�?????
// ?�로그래??바�? �?리키??것�? **?�라?�언??�?stage 2 ?????�운로드 진행�?* ?�다.
// ?�버??tile_generator 진행률�? ?�로 ?��?�?(�?금�? 미사??, ?�용?��? ?�제�?// "기다리는" ?�간?? ?�버 ?�성 + ?�라?�언??HTTP ?�운로드 ???? 그래??�??�체�?
// ?�라?�언??preload ?�만 매핑?�도�??�두�?
//   - ?��? ???�이 ?�스?�에 ?�는 ?�라?�드: ?�운로드�? 빠르�???�?빠르�?찬다
//   - ?�직 ?�성 중인 ?�라?�드: ?�버 ?�성 ??기로 HTTP �? ?�리�???�??�리�?찬다
// "�?100% = ?�면 �?�??�료" ?�는 직�?�??�치.
const $slideLoadingOverlay = document.getElementById('slide-loading-overlay');
const $slideLoadingBarFill = document.getElementById('slide-loading-bar-fill');
const $slideLoadingPct = document.getElementById('slide-loading-pct');

function _setSlideLoadingProgress(pct) {
    const int_pct = Math.max(0, Math.min(100, Math.round(pct)));
    if ($slideLoadingBarFill) $slideLoadingBarFill.style.width = int_pct + '%';
    if ($slideLoadingPct) $slideLoadingPct.textContent = int_pct + '%';
}

viewer.onPreloadStart = () => {
    if ($slideLoadingOverlay) $slideLoadingOverlay.hidden = false;
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

// ???? 마우??좌표 ?�버?�이 (??좌표 기�? px) ????
const $mousePosOverlay = $('#mouse-pos-overlay');
if ($mousePosOverlay) {
    $canvas.addEventListener('mousemove', (e) => {
        if (!currentSlideId) return;
        const rect = $canvas.getBoundingClientRect();
        const [sx, sy] = viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
        $mousePosOverlay.textContent = `x: ${Math.round(sx)}px, y: ${Math.round(sy)}px`;
    });
    $canvas.addEventListener('mouseleave', () => {
        // 값�? ?��??�되 ?�짝 ?�리�?    });
}

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ???�환
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.disabled) return;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        $(`#${btn.dataset.tab}`).classList.add('active');
    });
});

// ???? AI Analysis ?��?�?(?�재 ??�� 모델 ?�명) ????
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

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ?�용???�증 UI
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??if ($btnLogout) {
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

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ?�일 ?�기 + ?�로??// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ???? ?�로???�업 ????
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

// ?�업?�서 ?�로???�료 ?�림 ?�신
window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'upload-complete') {
        loadSlideList();
        setStatus(`${e.data.count}�??�일 ?�로???�료`);
    }
});

const SLIDE_EXT_PATTERN = /\.(svs|ndpi|tif|tiff|mrxs|vms|vmu|scn)$/i;

// uploadFiles ???�래�????�롭 ?�에???�출 ???�업?�로 ?�달
async function uploadFiles(fileList, _targetPath) {
    const files = [...fileList].filter(f => SLIDE_EXT_PATTERN.test(f.name));
    if (!files.length) {
        setStatus('�??�하???�라?�드 ?�일???�습?�다');
        return;
    }
    openUploadPopup(fileList, _targetPath || currentBrowsePath);
}

// ?�위 ?�환 ??기존 uploadOneFile 참조 방�? (?�용�??�음)
async function uploadOneFile() { /* deprecated ??upload ?�업 ?�용 */ return null; }

// ???? Scanner/Vendor 배�? ????
// openslide vendor string ?? ?�문???�워???�태. ?�라??SVG 로고�?매핑.
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
const $slideScanner = document.querySelector('#slide-scanner');
function _updateScannerBadge(slideInfo) {
    if (!$slideScanner) return;
    const str_vendor = String(slideInfo?.vendor || '').toLowerCase();
    if (!str_vendor || str_vendor === 'unknown') {
        $slideScanner.hidden = true;
        $slideScanner.innerHTML = '';
        return;
    }

    // ?�워??매칭 (openslide ??vendor 값�? 'hamamatsu', 'aperio', 'mirax', ... ??
    let meta = null;
    for (const [key, m] of Object.entries(SCANNER_META)) {
        if (str_vendor.includes(key)) { meta = m; break; }
    }

    const int_mag = slideInfo.objective_power && slideInfo.objective_power !== 'Unknown'
        ? `${slideInfo.objective_power}x` : '';
    const str_mpp = slideInfo.mpp_x ? `${slideInfo.mpp_x.toFixed(3)} µm/px` : '';
    const list_details = [int_mag, str_mpp].filter(Boolean);
    const str_info = list_details.join(' · ');

    // meta.label / meta.svg ??코드 ???�의???�전???�수.
    // slideInfo.vendor ???�라?�드 ?�일 메�? ???�뢰 불�? ??escape.
    if (meta) {
        $slideScanner.innerHTML = `
            <span class="scanner-logo" title="${_esc(meta.label)}">${meta.svg}</span>
            ${str_info ? `<span class="scanner-info">${_esc(str_info)}</span>` : ''}
        `;
        $slideScanner.style.borderLeftColor = meta.color;
    } else {
        // ?�려�?�? ?��? vendor: escape ?????�시
        $slideScanner.innerHTML = `
            <span class="scanner-logo scanner-logo-text">${_esc(slideInfo.vendor)}</span>
            ${str_info ? `<span class="scanner-info">${_esc(str_info)}</span>` : ''}
        `;
        $slideScanner.style.borderLeftColor = '#6c5ce7';
    }
    $slideScanner.hidden = false;
}

// ???? NDP ?�보??toggle (Hamamatsu ?�용) ????
// ?�팅�? γ=1.094, white=247.91, affine 3x4 ??color_match_analysis.ipynb ?�서
// MeDIAuto Studio ?????��? ??NDP.view2 ?��? 5???�합 ??최소?�곱?�로 ?�도.
// RMSE 4.21. color-correction.js ??NDP_FIT ?�서 �?�?
const $btnNdpColor = document.getElementById('btn-ndp-color');
const $ndpColorState = $btnNdpColor ? $btnNdpColor.querySelector('.ndp-color-state') : null;

function _updateNdpColorToggleVisibility(slideInfo) {
    if (!$btnNdpColor) return;
    const str_vendor = String(slideInfo?.vendor || '').toLowerCase();
    const bool_is_hamamatsu = str_vendor === 'hamamatsu';
    $btnNdpColor.hidden = !bool_is_hamamatsu;
    if (bool_is_hamamatsu) {
        // Hamamatsu ?�라?�드: 기본 ON ??NDP.view2 ?�감???��??�고
        // 보정 ?�이 보면 ?�르?�름?�게 보여 ?�용??�??�상???�쁘??
        viewer.setColorCorrectionEnabled(true);
        $btnNdpColor.classList.add('active');
        if ($ndpColorState) $ndpColorState.textContent = 'ON';
    } else {
        // �?Hamamatsu ?�라?�드: ??�� OFF �??�돌�?(?�팅???��? ?�음)
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
    currentSlideInfo = slideInfo;

    // ?�라?�드 ?�환 ???�전 ?�라?�드??sticky ?�래?�는 ?��? ?�음 (class id/?�름 매핑??    // ??detection 결과???�라 ?��? ???�음). HUD ??같이 ?��?.
    _stickyAddClassId = null;
    _hideStickyHud();

    $slideName.textContent = filename;
    _updateScannerBadge(slideInfo);
    _updateNdpColorToggleVisibility(slideInfo);
    setStatus(`Loaded: ${slideInfo.dimensions[0]}x${slideInfo.dimensions[1]} (${slideInfo.level_count} levels)`);

    // 버튼 ?�성??    $btnDetect.disabled = false;
    $btnVsMembrane.disabled = false;
    if ($btnPdScore) $btnPdScore.disabled = false;
    if ($btnIhcHer2) $btnIhcHer2.disabled = false;
    if ($btnIhcErPr) $btnIhcErPr.disabled = false;
    if ($btnIhcKi67) $btnIhcKi67.disabled = false;
    $btnInfo.disabled = false;
    document.querySelectorAll('.toggle-btn').forEach(b => b.disabled = false);
    // tissue-type ?�디?�도 기본 ?�성 ???�후 ?�더 ?�한???�으�???��??
    document.querySelectorAll('input[name="tissue-type"], input[name="pd-tissue-type"]').forEach(el => {
        el.disabled = false;
    });

    // ?�더�?AI ?�동 분석 ?�정???�으�??�당 task �??�성?? ?�머�???disabled.
    if (!_isViewerRole()) {
        _applyFolderAiRestrictions(currentBrowsePath);
    }

    // Viewer ??��?? AI / annotation 기능 ?�면 비활?? ?�더 ?�한보다 ?�선.
    if (_isViewerRole()) {
        _applyViewerRoleRestrictions();
    }

    // 뷰어 로드 (???��? ?�청 ??즉석 ?�성 + 백그?�운???�리?�네?�이??
    viewer.loadSlide(slideId, slideInfo);

    if ($mousePosOverlay) $mousePosOverlay.hidden = false;

    // 미니�?    loadMinimap(slideId);

    // 결과 초기??    clearResults();

    // VS IHC ?�버?�이 초기??    viewer.clearVirtualStainOverlay();
    _setVsToggleState(false, true);
    _setVsSplitState(false, true);

    // annotation?? ?�용?��? Load 버튼?�로 ?�일?�서 불러??(?�버 ?�동 로드 X)

    setProgress(0);
}

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ?�더�?AI ?�동 분석 ?�한
// ????
// ?�더???�동 분석 ?�정?????�돼 ?�으�?(bool_enabled=true AND tasks 존재),
// ?�당 task(model+variant) ???�하�? ?�는 AI 버튼/?�디?��? 모두 disabled �?만든??
// ?�정???�거??enabled=false �??�무것도 ?�한?��? ?�는??(기본 모두 ?�성).
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??
async function _applyFolderAiRestrictions(strFolderPath) {
    if (_isViewerRole()) return;

    let cfg = null;
    try {
        cfg = await api.getFolderAiConfig(strFolderPath || '');
    } catch (err) {
        console.warn('[folder-ai-restrict] load ?�패:', err);
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
        // ?�재 ?�택??것이 ?�용?��? ?�으�?�??�용 ?�션?�로 ?�동 ?�환
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

    // Quanti IHC ??마커�?버튼 ?�위
    if ($btnIhcHer2) $btnIhcHer2.disabled = !set_allowed.has('Quanti IHC::HER2');
    if ($btnIhcErPr) $btnIhcErPr.disabled = !set_allowed.has('Quanti IHC::ER_PR');
    if ($btnIhcKi67) $btnIhcKi67.disabled = !set_allowed.has('Quanti IHC::KI_67');

    // VS IHC ??ihc_membrane 모델??모든 �??�스 처리. target_mpp ???�한 ????
    const bool_vs_any = set_allowed.has('VS IHC::ihc_membrane');
    $btnVsMembrane.disabled = !bool_vs_any;

    // ???? ?�성 모델???�는 ???�체 ?��? ????
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

    // �?번째 보이????�� ?�성??    if (str_first_visible) {
        const el_new_btn = document.querySelector(`.tab-btn[data-tab="${str_first_visible}"]`);
        const el_new_content = document.getElementById(str_first_visible);
        if (el_new_btn) el_new_btn.classList.add('active');
        if (el_new_content) {
            el_new_content.style.display = '';
            el_new_content.classList.add('active');
        }
    }
}

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// Viewer ??�� ?�한 ??AI 기능 / annotation ?�면 비활??// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??function _applyViewerRoleRestrictions() {
    document.body.classList.add('role-viewer');
    _stopAiActivePolling();

    // Annotation 그리�??�구 (?�단 ?�바)
    const list_draw_btns = ['btn-draw-polygon', 'btn-draw-rect',
                            'btn-draw-rect-1mm2', 'btn-draw-circle-1mm2', 'btn-ruler'];
    list_draw_btns.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.classList.remove('active');
            el.title = 'Viewer 권한?? annotation 기능???�용?????�습?�다';
        }
    });
    // 그리�?모드�? 켜져?�었?�면 ?�제
    if (viewer && viewer.drawMode) viewer.setDrawMode(null);

    // AI 분석 버튼 ?�체 비활??    const list_ai_btn_ids = [
        'btn-detect', 'btn-pd-score', 'btn-ihc-her2', 'btn-ihc-erpr',
        'btn-ihc-ki67', 'btn-vs-membrane', 'btn-vs-toggle', 'btn-vs-split',
        'btn-visualize', 'btn-clear-results', 'btn-save-results', 'btn-load-results',
    ];
    list_ai_btn_ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = 'Viewer 권한?? AI 분석 기능???�용?????�습?�다.';
        }
    });

    // AI ?�력 (tissue-type radio ?? 비활??    document.querySelectorAll(
        '#right-panel .panel-group:first-child input, #right-panel .panel-group:first-child button'
    ).forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer 권한?? AI 분석 기능???�용?????�습?�다.';
    });

    // Annotation ?�널??????불러?�기/초기??버튼
    ['btn-ann-clear', 'btn-ann-save', 'btn-ann-load',
     'btn-new-project', 'btn-rename-project', 'btn-delete-project'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = 'Viewer 권한?? annotation 기능???�용?????�습?�다.';
        }
    });

    document.querySelectorAll('.annotation-group button, .annotation-group input').forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer 권한?? annotation 기능???�용?????�습?�다.';
    });
}

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ?�래�????�롭
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??const $viewerContainer = $('#viewer-container');

// OS ?�일 ?�래그만 감�? (뷰어 ?��? ?�소/?�스???�래그는 무시)
function _isFileDrag(e) {
    const t = e.dataTransfer && e.dataTransfer.types;
    if (!t) return false;
    // DOMStringList / Array 모두 �???    if (typeof t.contains === 'function') return t.contains('Files');
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

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// 미니�?// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??async function loadMinimap(slideId) {
    const img = new Image();
    img.onload = () => {
        minimapImage = img;
        $minimapCanvas.width = img.width;
        $minimapCanvas.height = img.height;
        $minimapCanvas.getContext('2d').drawImage(img, 0, 0);
        $minimapContainer.hidden = false;
        $minimapContainer.classList.remove('minimized');
        if ($minimapIcon) $minimapIcon.setAttribute('d', 'M3 7h8');
        const body = document.getElementById('minimap-body');
        if (body) body.style.width = `${img.width}px`;
        updateMinimap();
    };
    img.src = api.thumbnailUrl(slideId, 200);
}

function updateMinimap() {
    if (!minimapImage || !currentSlideInfo) return;
    const vr = viewer.getViewRect();
    if (!vr) return;
    const [imgW, imgH] = currentSlideInfo.dimensions;
    // CSS width 기�? (리사?�즈 ????
    const displayW = $minimapCanvas.clientWidth || $minimapCanvas.width;
    const displayH = $minimapCanvas.clientHeight || $minimapCanvas.height;
    const sx = displayW / imgW;
    const sy = displayH / imgH;
    $minimapViewport.style.left = `${vr.x * sx}px`;
    $minimapViewport.style.top = `${vr.y * sy}px`;
    $minimapViewport.style.width = `${Math.max(4, vr.width * sx)}px`;
    $minimapViewport.style.height = `${Math.max(4, vr.height * sy)}px`;
}

$minimapCanvas.addEventListener('click', (e) => {
    if (!currentSlideInfo) return;
    const rect = $minimapCanvas.getBoundingClientRect();
    const [imgW, imgH] = currentSlideInfo.dimensions;
    viewer.navigateTo(
        ((e.clientX - rect.left) / rect.width) * imgW,
        ((e.clientY - rect.top) / rect.height) * imgH
    );
});

// 미니�?최소???��?
const $minimapToggle = $('#minimap-toggle');
const $minimapIcon = $('#minimap-toggle-icon');
$minimapToggle?.addEventListener('click', (e) => {
    e.stopPropagation();
    const minimized = $minimapContainer.classList.toggle('minimized');
    // minimize: ??icon, expand: + icon
    $minimapIcon.setAttribute('d', minimized ? 'M3 7h8M7 3v8' : 'M3 7h8');
    $minimapToggle.title = minimized ? 'Expand' : 'Minimize';
});

// 미니�?리사?�즈 (?�른�???모서�??�래�????�기 조절)
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

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// �?컨트�?// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??$btnZoomIn.addEventListener('click', () => viewer.zoomIn());
$btnZoomOut.addEventListener('click', () => viewer.zoomOut());
$btnFit.addEventListener('click', () => viewer.fitToWindow());

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// Annotation 그리�??�구
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??const drawButtons = {
    polygon: $btnDrawPolygon,
    rectangle: $btnDrawRect,
    'rect-1mm2': $btnDrawRect1mm2,
    'circle-1mm2': $btnDrawCircle1mm2,
    ruler: $btnRuler,
};

function setDrawMode(mode) {
    if (_blockViewerAction('Viewer 권한?? annotation 기능???�용?????�습?�다.')) return;
    // 같�? 버튼 ?�시 ?�릭 ???�제
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

// ???? UX 기능 ?�명 모달 ????
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

// ???? 모바???�널 ?��? (??00px) ????
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
// 브레?�크?�인???�어�?�?drawer ?�태 ?�리
window.matchMedia('(max-width: 900px)').addEventListener('change', (e) => {
    if (!e.matches) _closeMobilePanels();
});

// ESC ?�으�?drawMode�? �?경될 ??버튼 ?�기??viewer.onDrawModeChange = (mode) => {
    Object.values(drawButtons).forEach(b => { if (b) b.classList.remove('active'); });
    if (mode && drawButtons[mode]) drawButtons[mode].classList.add('active');
};

// ???? Annotation Panel ????
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
        // ann.name ?? ?�용???�블?�릭 rename ?�로 ?�의 문자??�?????반드??escape
        el.innerHTML = `
            <input type="color" class="ann-color-swatch" value="${rgbToHex(r, g, b)}"
                   title="Change color" style="background:rgb(${r},${g},${b})">
            <span class="ann-name" title="Double-click to rename">${_esc(ann.name)}</span>
            <span class="ann-type">${_esc(ann.type)}</span>
            <button class="ann-btn-vis" title="Toggle visibility">${ann.visible ? '?��' : '?��?��?}</button>
            <button class="ann-btn-del" title="Delete">??/button>
        `;
        // ?�릭 ???�택
        el.addEventListener('click', (e) => {
            if (e.target.closest('.ann-color-swatch') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') || e.target.closest('.ann-name-input')) return;
            viewer.selectAnnotation(ann.id);
        });
        // ?�블?�릭 ?�름 ??리네??        el.querySelector('.ann-name').addEventListener('dblclick', (e) => {
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
        // ?�상 �?�?        el.querySelector('.ann-color-swatch').addEventListener('input', (e) => {
            const hex = e.target.value;
            ann.color = hexToRgb(hex);
            e.target.style.background = `rgb(${ann.color[0]},${ann.color[1]},${ann.color[2]})`;
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
        });
        // �??�성 ?��?
        el.querySelector('.ann-btn-vis').addEventListener('click', (e) => {
            e.stopPropagation();
            ann.visible = !ann.visible;
            viewer.requestRender();
            renderAnnotationPanel();
        });
        // ??��
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

// 캔버?????�널 ?�기??viewer.onAnnotationCreated = (ann) => {
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
    // ?��? ?�더�??�청?????�널�?갱신 ?�요 ??};

// deleteAnnotation?�서 콜백 ?�출?�도�??�버?�이??const _origDelete = viewer.deleteAnnotation.bind(viewer);
viewer.deleteAnnotation = (id) => {
    const ann = viewer.annotations.find(a => a.id === id);
    _origDelete(id);
    if (ann && viewer.onAnnotationDeleted) viewer.onAnnotationDeleted(ann);
};

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// Cell Edit ?�업 (Alt+Click)
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??let _cellEditPopupEl = null;

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
    // Delete/D ???????�는 edit/multi 모드?�서�???add/sticky-pick ????�� ?????�음.
    if ((e.key === 'Delete' || e.key.toLowerCase() === 'd') &&
            _cellEditCtx.mode !== 'add' && _cellEditCtx.mode !== 'sticky-pick') {
        _doDeleteCell();
        e.preventDefault();
        return;
    }
    // ?�자??1~9, 0 ???�래???�택. 모드�?분기:
    //   edit/multi ???�래??�?�? add ???�릭 ?�치???? 추�?, sticky-pick ??sticky �?갱신.
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

// ?�을 CSS 문자?�로 ?�규??(hex "#RRGGBB" ?�는 [r,g,b] 모두 �???
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
 * Popup ?�래??버튼???�필(?? ?�집 ?�이콘을 ?�워?�는?? ?�릭 ??�?row �? inline
 * ?�스???�력 + ????취소 모드�?바�?�며, ???�하�?_renameClassLabel �??�파?�고
 * ?�력값이 popup ???�시 ?�스?�에??반영. popup ?�체???��? ?�는??(?�용?��?
 * ?�벨 ?�리 ???�일 popup ?�서 add/change ?�어�????�름).
 */
function _attachClassRenamePencil(btnEl, classId, textSpan) {
    const pencil = document.createElement('span');
    pencil.title = '?�벨 ?�름 ?�집';
    pencil.setAttribute('aria-label', 'rename label');
    pencil.style.cssText = `
        flex:0 0 22px; height:22px; margin-right:6px;
        display:flex; align-items:center; justify-content:center;
        border-radius:3px; cursor:pointer; opacity:0.55;
        font-size:13px; line-height:1;
    `;
    pencil.textContent = '??;
    pencil.onmouseover = () => { pencil.style.opacity = '1'; pencil.style.background = 'rgba(0,0,0,0.08)'; };
    pencil.onmouseout = () => { pencil.style.opacity = '0.55'; pencil.style.background = 'transparent'; };
    pencil.addEventListener('click', (ev) => {
        ev.stopPropagation();   // row ??select ?�작 방�?
        // textSpan ?�리??input + ????취소 버튼 ?�시 배치.
        const original = textSpan.textContent || '';
        // ?�시값에??[N] ?�축??prefix �? ?�으�?그건 빼고 ?�제 ?�벨�??�집.
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
        ok.textContent = '??;
        ok.title = '????(Enter)';
        ok.style.cssText = `
            flex:0 0 22px; height:22px; padding:0;
            background:#27ae60; color:#fff; border:none;
            border-radius:3px; cursor:pointer; font-weight:700;
        `;
        const cancel = document.createElement('button');
        cancel.textContent = '×';
        cancel.title = '취소 (Esc)';
        cancel.style.cssText = `
            flex:0 0 22px; height:22px; padding:0;
            background:#e74c3c; color:#fff; border:none;
            border-radius:3px; cursor:pointer; font-weight:700;
        `;
        wrap.append(input, ok, cancel);

        // textSpan ???�시 wrap ?�로 ??�?
        const parent = textSpan.parentElement;
        parent.removeChild(textSpan);
        // pencil 직전 ?�치??wrap ?�입.
        parent.insertBefore(wrap, pencil);
        pencil.style.display = 'none';

        // popup ?�체???�보???�축??_cellEditKeydown) �? ?�력??�?로채�? 못하?�록
        // input ?�벤?�는 stopPropagation. (Ctrl+Z / ?�자????충돌 방�?)
        input.addEventListener('keydown', (kev) => {
            kev.stopPropagation();
            if (kev.key === 'Enter') { commit(); }
            else if (kev.key === 'Escape') { abort(); }
        });
        // ?��? ?�릭?�로 popup ?�히???�들?�도 ?�시 차단 ??input ?�체 ?�릭?�서.
        input.addEventListener('mousedown', (mev) => mev.stopPropagation());
        ok.addEventListener('click', (mev) => { mev.stopPropagation(); commit(); });
        cancel.addEventListener('click', (mev) => { mev.stopPropagation(); abort(); });

        const restoreText = () => {
            wrap.remove();
            // ?�래 ?�치(pencil 직전)??textSpan ?�시 ?�입.
            parent.insertBefore(textSpan, pencil);
            pencil.style.display = '';
        };
        const abort = () => { restoreText(); };
        const commit = () => {
            const str_new = input.value.trim();
            if (!str_new || str_new === initialName) { restoreText(); return; }
            const ok2 = _renameClassLabel(classId, str_new);
            if (ok2) {
                // popup ???�시 ?�스?�도 ?�기????[N] prefix ?��?.
                textSpan.textContent = m ? `[${m[0].match(/\d/)[0]}] ${str_new}` : str_new;
            }
            restoreText();
        };

        // ?�동 ?�커??+ ?�스???�체 ?�택.
        setTimeout(() => { input.focus(); input.select(); }, 0);
    });
    // ???��?�??�음, ?�스???�에 ?�필 배치 ???�각?�으�??�스???�이 ?�연?�럽??
    btnEl.insertBefore(pencil, textSpan);
}

/**
 * ?�래???�벨 ?�름 �?�???`_lastDetectionResult.class_names[classId]` 갱신 +
 * ?�당 class_id ??모든 ????`class_name` ?�기??+ Result 리스??/ Score 카드
 * 즉시 ?�렌?? 메모리에�?반영 (???��? ROI Save 버튼???�당).
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
    // ?�널 / 카드 / status 즉시 반영.
    buildResultList(_lastDetectionResult);
    _updateResultCounts();
    setStatus(`Class ${classId} renamed to "${str_new}"`);
    return true;
}

function _showCellEditPopup(idx, cell, screenX, screenY) {
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

    // ?�더
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

    // ?�래??버튼??(?�재 ?�래???�외, ?�자??매핑)
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

        // ?�꺼??????(?�쪽 ?�체 ?�이)
        const stripe = document.createElement('span');
        stripe.style.cssText = `flex:0 0 12px;align-self:stretch;
            background:${colorCss};display:block;`;

        // ???��?�?        const sw = document.createElement('span');
        sw.style.cssText = `flex:0 0 16px;height:16px;border-radius:3px;
            background:${colorCss};border:1px solid #333;
            display:inline-block;margin-left:8px;`;

        const text = document.createElement('span');
        text.textContent = keyLabel ? `[${keyLabel}] ${name}` : name;
        text.style.cssText = 'flex:1;padding:6px 10px;';

        btn.append(stripe, sw, text);
        btn.addEventListener('click', () => _doChangeClass(cid));
        // ?�벨 ?�름 ?�집 ??text ?�에 ?�필(?? ?�워 inline rename UI ?�성??
        _attachClassRenamePencil(btn, cid, text);
        popup.appendChild(btn);

        classButtonOrder.push(cid);
        keyIdx++;
    }

    const sep2 = document.createElement('div');
    sep2.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep2);

    // ??�� 버튼
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

    // ?�면 밖으�??��?�? ?�게 ?�치 보정
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

    // ?��? ?�릭/ESC/Del/?�자??    setTimeout(() => {
        document.addEventListener('mousedown', _outsideCellEditClick, true);
        document.addEventListener('keydown', _cellEditKeydown, true);
    }, 0);
}

viewer.onCellEditRequested = _showCellEditPopup;

// ???? Alt+right-click ?? 추�? ????
// Sticky class: �?추�? ???�용?��? popup ?�로 ?�택???�래?��? 기억???�고
// ?�음 Alt+right-click �???popup ?�이 바로 �??�래?�로 추�?.
// ?�측 ?�널???�래???�인 ?�릭?�로 sticky �?�?�???
let _stickyAddClassId = null;

// Alt HUD ??Alt ?�른 ?�안 마우???�상?�에 ?�재 sticky ?�래???�시.
// ?�용?��? ?�떤 ?�래?�로 추�??��? ?�각?�으�?즉시 ?�인 �???
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
    // 마우???�상????cursor ?? ??겹치�?+14 ?�측, -28 ??
    let x = _stickyHudLastMouse.x + 14;
    let y = _stickyHudLastMouse.y - 28;
    // ?�면 �?방�? ??�?�?overflow �?좌측, ?�로 overflow �??�래�??�집??배치.
    const w = _stickyHudEl.offsetWidth;
    if (x + w > window.innerWidth - 4) x = _stickyHudLastMouse.x - w - 14;
    if (y < 4) y = _stickyHudLastMouse.y + 18;
    _stickyHudEl.style.left = `${Math.max(4, x)}px`;
    _stickyHudEl.style.top  = `${Math.max(4, y)}px`;
}

function _showStickyHud() {
    // ?�시 조건: Alt ?�름 + sticky ?�아?�음 + detection 결과 + drawMode ?�님.
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
    _closeCellEditPopup();
    if (!_lastDetectionResult) return;

    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};

    // Sticky �? ?�아 ?�으�?popup ?�이 즉시 추�? ???�래??�?경�? Alt+A ?�축??
    if (_stickyAddClassId != null && classNames[String(_stickyAddClassId)]) {
        const str_name = classNames[String(_stickyAddClassId)];
        viewer.addCell(sx, sy, _stickyAddClassId, str_name);
        setStatus(`Cell added: ${str_name} ??Alt+right-click to add, Alt+A to change`);
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
        text.style.cssText = 'flex:1;padding:6px 10px;';

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
    // _cellEditCtx ??mode='add' �??�시 ???�자 ?�축?�도 ?�동.
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
        // ?�치�?받�? 모드 ???? 추�? + sticky 갱신.
        viewer.addCell(_cellEditCtx.sx, _cellEditCtx.sy, classId, name);
        _stickyAddClassId = classId;
        setStatus(`Sticky class: ${name} ??Alt+right-click to add, Alt+A to change`);
    } else if (_cellEditCtx.mode === 'sticky-pick') {
        // ?�래?�만 �?�?(?? 추�? X) ??Alt+A 진입??popup.
        _stickyAddClassId = classId;
        setStatus(`Sticky class: ${name} ??Alt+right-click to add`);
    }
    _closeCellEditPopup();
}

/**
 * Alt+A ?�축?�로 ?�출 ??sticky ?�래?�만 �?�?(?? 추�? X).
 * popup ?? _showCellAddPopup ?? ?�일???�래??리스??UI �??�사?�하??
 * mode='sticky-pick' 컨텍?�트�??�릭 ??sticky �?갱신.
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
    headerLabel.innerHTML = `<b>Pick Sticky Class</b>  <span style="opacity:0.6">(추�????�래???�택)</span>`;
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
        text.textContent = (keyLabel ? `[${keyLabel}] ` : '') + name + (isCurrent ? '  ?? : '');
        text.style.cssText = 'flex:1;padding:6px 10px;';

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

// Alt+A ??sticky ?�래??�?�?popup. ?�력 ?�젯 ?�커??중이�?무시.
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
    // 마우??마�?�??�치 ?�에 popup ?��? ??viewer ?�에???�르�?�??�치 근처????
    _showStickyClassPickerPopup(_stickyHudLastMouse.x, _stickyHudLastMouse.y);
}, true);

viewer.onCellAddRequested = _showCellAddPopup;

function _showMultiCellEditPopup(listIndices, listCells, screenX, screenY, options = {}) {
    _closeCellEditPopup();
    if (!_lastDetectionResult || !listIndices || listIndices.length === 0) return;

    const isHiddenOther = !!options.hiddenOther;
    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};

    // ?�택?????�의 ?�래?�별 개수 집계
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

    // ?�더
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>${listIndices.length} ${isHiddenOther ? 'Other cells selected' : 'cells selected'}</b>`;
    header.appendChild(headerLabel);
    popup.appendChild(header);
    _makeCellEditPopupDraggable(popup, header);

    // ?�래?�별 집계 ?�시
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

    // 모든 ?�래??버튼
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
        text.style.cssText = 'flex:1;padding:6px 10px;';

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
    // 결과 리스??카운??+ ?�코??갱신
    if (_lastDetectionResult) {
        _lastDetectionResult.cells = viewer.detectionCells;
        _lastDetectionResult.total_cells = viewer.detectionCells.length;
        _lastDetectionResult.excluded_cells = viewer.hiddenDetectionCells || [];
        buildResultList(_lastDetectionResult);
        // ?�코??카드 ?�계??(Allred / HER2 / Quanti PD-L1)
        _updateResultCounts();
    }
    setStatus(`Cell edited ??${viewer.detectionCells.length} cells`);
};

// ???? Cell edit Undo / Redo (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y) ????
window.addEventListener('keydown', (e) => {
    // ?�력 ?�젯 ?�커??중이�?무시
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    if (!viewer || !viewer.detectionCells || viewer.detectionCells.length === 0 && !viewer.canUndoCellEdit?.()) return;

    const key = e.key.toLowerCase();
    if (key === 'z' && !e.shiftKey) {
        if (viewer.canUndoCellEdit && viewer.canUndoCellEdit()) {
            _closeCellEditPopup();
            viewer.undoCellEdit();
            setStatus(`Undo ??${viewer.detectionCells.length} cells`);
            e.preventDefault();
        }
    } else if ((key === 'z' && e.shiftKey) || key === 'y') {
        if (viewer.canRedoCellEdit && viewer.canRedoCellEdit()) {
            _closeCellEditPopup();
            viewer.redoCellEdit();
            setStatus(`Redo ??${viewer.detectionCells.length} cells`);
            e.preventDefault();
        }
    }
}, true);

// Clear All
$btnAnnClear?.addEventListener('click', () => {
    if (_blockViewerAction('Viewer 권한?? annotation 기능???�용?????�습?�다.')) return;
    viewer.clearAnnotations();
    renderAnnotationPanel();
    setStatus('Annotations cleared');
});

// ???? Annotation Save/Load (download/upload) ????
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

    // File System Access API: ?�용?��? ?????�치(?�더 + ?�일�? 직접 ?�택
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
            // 권한 거�? ?????�운로드 fallback
            console.warn('showSaveFilePicker failed, falling back to download', err);
        }
    }

    // Fallback: ?�반 브라?��? ?�운로드
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
    if (_blockViewerAction('Viewer 권한?? annotation 기능???�용?????�습?�다.')) return;
    _downloadAnnotations();
});
$btnAnnLoad?.addEventListener('click', () => {
    if (_blockViewerAction('Viewer 권한?? annotation 기능???�용?????�습?�다.')) return;
    _uploadAnnotations();
});

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ?�라?�드 ?�보 ?�이?�로�?// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??$btnInfo.addEventListener('click', () => {
    if (!currentSlideInfo) return;
    const info = currentSlideInfo;
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
    $slideInfoDialog.showModal();
});
$('#close-slide-info').addEventListener('click', () => $slideInfoDialog.close());

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// AI �?�?// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??
// ?�행 중인 AI task 추적 ??key: 버튼 고유 ??('detect', 'VS IHC_membrane', 'Quanti PD-L1', 'ihc-HER2' ??
//   value: { task_id, buttonEl }
// 같�? 버튼 ?�클�???cancelTask ?�출.
const _runningAiTasks = {};

function _setButtonRunning(btnEl, bool_running) {
    if (!btnEl) return;
    if (bool_running) {
        btnEl.classList.add('ai-btn-running');
        btnEl.dataset.origLabel = btnEl.dataset.origLabel || btnEl.textContent;
        btnEl.textContent = '??Stop';
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
    // task_id �? ?�직 ?�버?�서 ?�아?��? ?�았?�데 ?�클�?�� 경우:
    // pending_cancel ?�래그만 ?�팅 ??start ?�들?��? task_id �?받는 즉시 cancelTask ?�출.
    // (null ??URL ??박아 ?�면 /task/null/cancel �?405/404 ?��?�?금�?)
    if (!entry.task_id) {
        entry.pending_cancel = true;
        setStatus('중�? ?�약 ??task ?�작 직후 취소?�니??..');
        return true;
    }
    try {
        await api.cancelTask(entry.task_id);
        setStatus('중�? ?�청 ?�송 ???�시 ???�리?�니??..');
    } catch (e) {
        console.warn('[cancel] failed', e);
    }
    return true;  // ?�출?�는 start 로직 건너?�기
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
    setStatus('�?�??�작...');

    // AI ?�작 ??그리�?모드 ?�제
    viewer.setDrawMode(null);

    try {
        const tissueType = document.querySelector('input[name="tissue-type"]:checked')?.value || 'Stomach';

        // point ?�외??polygon/rectangle annotation ??ROI�??�달
        const roiAnnotations = viewer.annotations.filter(a => a.visible && a.type !== 'point' && a.coordinates.length >= 3);
        const roiPolygons = roiAnnotations.length > 0 ? roiAnnotations.map(a => a.coordinates) : null;

        const { task_id } = await api.startDetection(currentSlideId, roiPolygons, tissueType);
        if (_runningAiTasks['detect']) {
            _runningAiTasks['detect'].task_id = task_id;
            if (_runningAiTasks['detect'].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
            }
        }

        // ?�링
        while (true) {
            await sleep(1000);
            // ?�른 코드�? _runningAiTasks �?�??�으�?(?? ?�라?�드 �?�? 루프 ?�출
            if (!_runningAiTasks['detect']) return;
            const st = await api.getTaskStatus(task_id);
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);

            // 진행 ?�계???�라 ?�벨 ?�데?�트
            if (st.progress <= 50) {
                $progressLabel.textContent = 'Cell Detection';
            } else if (st.progress < 92) {
                $progressLabel.textContent = 'WSI Segmentation';
            } else if (st.progress < 100) {
                $progressLabel.textContent = 'Epithelial Reclassification';
            }

            if (st.status === 'completed') {
                onDetectionComplete(st.result, roiPolygons, tissueType);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus('Cell Detection 중�?????�?�?결과 ?�리 ?�료');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`�?�??�패: ${err.message}`);
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

    // AI ?�료 ??기존 annotation ?�거 (ROI ??????
    viewer.clearAnnotations();
    renderAnnotationPanel();

    // ?��? ???�용?�로 최신 결과 보존
    _lastDetectionResult = result;
    _lastDetectionTissue = tissueType;
    _lastDetectionModel = 'Quanti HE';
    _lastDetectionRoi = roiPolygons;

    // segmentation ?�이??????(Spatial Heatmap ?�각?�용)
    lastSegData = result.seg_data || null;

    // Quanti HE ?? 기본 CLASS_COLORS ?�용 (override ?�제)
    viewer.classColorOverride = null;
    viewer.defaultConfidence = 0.1;  // 고정 (SaMD ?�현??

    // ROI ?�리�??��? ??�??�터링하???�시
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
}

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// 결과 리스??(기존 resultList ?�현)
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??const CLASS_COLORS = {
    0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
    4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
};

// ???? ?�코??�?차트 ?�틸 ????
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

// ?�재 confidence ?�계값을 반영???�래?�별 카운??계산
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

// "1,234 (45.6%)" ???�래?�별 개수 + ?�체 ??�?비율. total ?? confidence ?�터 ?�과??// 모든 ?�래???? total=0 ?�면 비율 0%.
function _formatCountWithRatio(int_count, int_total) {
    const str_count = int_count.toLocaleString();
    if (!int_total) return `${str_count} (0%)`;
    return `${str_count} (${(int_count / int_total * 100).toFixed(1)}%)`;
}

// 결과 리스?�의 카운???�벨�?갱신 (confidence ?�라?�더 �?�????�출)
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

// Confidence ?�터�? 반영??카운?�로 CPS/TPS ?�계?�하???�코??카드 갱신
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

    // viewer.detectionCells ??ROI ?�리�??��? ??�??�아 ?��?�?(setDetectionResults),
    // confidence ?�계�?미만 ????그�?�?보�??�다 (?�라?�더 조절???�용?�기 ?�해).
    // ?�더�??�각???�코??카드??모두 _computeFilteredCounts (ROI + confidence) �?    // 거치�?�??�널 ?�자??같�? 기�??�로 맞춰???��??�이 ?��??�다.
    let counts, total;
    if (viewer.detectionCells && viewer.detectionCells.length) {
        ({ counts, total } = _computeFilteredCounts(viewer.detectionCells));
    } else {
        // fallback ??viewer �? ?�직 초기???�인 ?��? �??�스 (???�본 직접 로드 ??
        counts = {};
        total = 0;
        for (const cell of (result.cells || [])) {
            counts[cell.class_id] = (counts[cell.class_id] || 0) + 1;
            total++;
        }
    }

    // ?�래?�별 체크박스 참조 ????    const classCbs = {};
    const perClassCountEls = {};

    // �??? ??(?�체 ?��? 체크박스)
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
    // ROI ?�터�?결과(total)?? ?��?????result.total_cells ???�체 ?�라?�드 ?�이??ROI 추론 ???�긋?�다.
    totalCount.textContent = total.toLocaleString();

    totalItem.style.cursor = 'pointer';
    totalItem.addEventListener('click', (e) => {
        if (e.target === totalCb) return;
        totalCb.click();
    });

    totalItem.append(totalCb, totalName, totalCount);
    $resultList.appendChild(totalItem);

    // ?�래?�별 ??�� (체크박스 + ?�상 + ?�름 + 카운??+ 개별 confidence ?�라?�더)
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
            // ?�체 체크박스 ?�기??            const allChecked = Object.values(classCbs).every(c => c.checked);
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
        // confidence ?�계값�? SaMD ?�현?�을 ?�해 고정 ??UI 조절 ?�라?�더 ?�거??    }

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
    // detection 결과�? ?�라�?�?sticky ??무효 ??class_names �? ?�어졌으???��? X.
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
    // ?�재 ?�래?�별 confidence ?�계값을 ?�과????�??�각??    const filtered = viewer.detectionCells.filter(c => {
        const thr = viewer.classConfidence[c.class_id] ?? 0.01;
        return (c.confidence ?? 1.0) >= thr;
    });
    if (filtered.length === 0) {
        setStatus('No cells pass current confidence thresholds');
        return;
    }
    const thumbUrl = currentSlideId ? api.previewUrl(currentSlideId, 4096) : null;
    const slideName = ($slideName.textContent || '').replace(/\.[^.]+$/, '') || 'slide';
    const tissue = _lastDetectionTissue || 'Stomach';
    const slideDims = currentSlideInfo?.dimensions || null;  // [w, h] level-0

    // 모델 ????/ ?�래??메�?
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

// Detection Result ???????�재 로그?�한 ?�용???�용 ?�집본으�?DB ????// (?�본 모델 추론 캐시??건드리�? ?�음)
$btnSaveResults?.addEventListener('click', async () => {
    if (_blockViewerAction('Viewer 권한?? AI 결과 ????기능???�용?????�습?�다.')) return;
    if (!currentSlideId || !_lastDetectionResult) {
        setStatus('No detection result to save');
        return;
    }
    const tissue = _lastDetectionTissue || 'Stomach';
    const aiMode = _lastDetectionModel || 'Quanti HE';
    try {
        $btnSaveResults.disabled = true;
        // 뷰어?�서 ?�집??????결과 객체??반영 (class_id �?�???
        if (viewer?.detectionCells) {
            _lastDetectionResult.cells = viewer.detectionCells;
            _lastDetectionResult.total_cells = viewer.detectionCells.length;
            _lastDetectionResult.excluded_cells = viewer.hiddenDetectionCells || [];
        }
        // confidence ?�계값�? SaMD ?�현?�을 ?�해 고정값만 ?�용.
        // 과거 ???�본과의 ?�환???�해 ?�거???�드?????�하�? ?�음(?�어??로드 ??무시).
        delete _lastDetectionResult.class_confidence;
        delete _lastDetectionResult.default_confidence;
        const r = await api.saveDetectionResult(
            currentSlideId, tissue, _lastDetectionResult, aiMode,
        );
        console.log('[save-result]', r);
        setStatus(`Saved (${aiMode}/${tissue}): ${r.total_cells} cells ??${r.user_name || 'me'}`);
    } catch (err) {
        console.error('[save-result] failed', err);
        setStatus(`Save failed: ${err.message}`);
    } finally {
        $btnSaveResults.disabled = false;
        if (_isViewerRole()) _applyViewerRoleRestrictions();
    }
});

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// Detection Result 로드 ???�른 ?�용???�는 본인)?????�본 ?�택
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??const $loadUserEditDialog = $('#load-user-edit-dialog');
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
    if (_blockViewerAction('Viewer 권한?? AI 결과 로드 기능???�용?????�습?�다.')) return;
    if (!currentSlideId) {
        setStatus('?�라?�드�?먼�? ?�어주세??);
        return;
    }
    if (!_lastDetectionModel || !_lastDetectionTissue) {
        setStatus('먼�? AI 모델???�행?�주?�요 (?�떤 모드�?로드?��? �??�해???�니??');
        return;
    }
    const aiMode = _lastDetectionModel;
    const variant = _lastDetectionTissue;
    $loadUserEditMeta.textContent = `Mode: ${aiMode}  /  Variant: ${variant}`;
    $loadUserEditList.innerHTML = '<div style="padding:12px; color:#888;">Loading??/div>';
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

    // ?�의 ??��: "?�본 모델 추론 결과" (기존 AI 버튼 ?�실?�과 ?�일)
    const originalRow = document.createElement('div');
    originalRow.className = 'result-row';
    originalRow.style.cssText = 'padding:10px 12px; cursor:pointer; border-bottom:1px solid #333;';
    originalRow.innerHTML = `
        <div style="font-weight:600;">Original model inference</div>
        <div style="font-size:11px; color:#888; margin-top:2px;">
            ?�본 모델 추론 ?�실??(${aiMode} / ${variant})
        </div>`;
    originalRow.addEventListener('click', async () => {
        $loadUserEditDialog.close();
        _rerunOriginalInference(aiMode, variant);
    });
    $loadUserEditList.appendChild(originalRow);

    if (users.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding:12px; color:#888; font-size:12px;';
        empty.textContent = '???�된 ?�용???�집본이 ?�습?�다.';
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
                setStatus(`Loading ${displayName}'s analysis??);
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
            del.textContent = '?��';
            del.addEventListener('click', async (ev) => {
                ev.stopPropagation();
                if (!confirm(`Delete your saved ${aiMode} / ${variant} analysis for this slide?`)) return;
                try {
                    del.disabled = true;
                    await api.deleteMyUserAiEdit(currentSlideId, aiMode, variant);
                    setStatus('Deleted your saved analysis');
                    // 모달 ?�시 불러?�기
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
    // ?�거?????�본??class_confidence / default_confidence ?�드�? ?�어??무시.
    // 모든 결과???�재 모델??고정 ?�계값으�??�시?�다 (SaMD ?�현??.
}

function _rerunOriginalInference(aiMode, variant) {
    // 기존 AI 버튼�??�일??경로�??�실?????�버 ?�스??캐시�? ?�으�?즉시 반환??    if (aiMode === 'Quanti HE') {
        // startDetection ?? 버튼 ?�들???��????�으�?�?버튼 ?�릭 ?�리�?        $('#btn-detect')?.click();
    } else if (aiMode === 'Quanti PD-L1') {
        $('#btn-pd-score')?.click();
    } else if (aiMode === 'Quanti IHC') {
        if (variant === 'ER_PR') $('#btn-ihc-erpr')?.click();
        else if (variant === 'KI_67') $('#btn-ihc-ki67')?.click();
        else $('#btn-ihc-her2')?.click();
    }
}

$btnLoadResults?.addEventListener('click', _openLoadUserEditDialog);

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// ?�틸리티
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??function setProgress(pct, statusMsg = '') {
    $progressBar.querySelector('.progress-fill').style.width = `${pct}%`;
    const $text = $('#progress-text');
    if (pct > 0 && pct < 100) {
        $text.textContent = statusMsg || `${pct}%`;
    } else if (pct >= 100) {
        $text.textContent = 'Complete';
    } else {
        $text.textContent = '';
    }
}

function setStatus(msg) {
    $statusText.textContent = msg;
}

function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// 좌측 ?�널 리사?�즈
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??const $leftPanel = $('#left-panel');
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

// Ctrl + ?�로 ?�라?�드 리스???�네???�기 조정 (리스??그리??각각)
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

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// 좌측 ?�라?�드 리스??+ ?�더 ?�색
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??let currentBrowsePath = '';  // uploads/ 기�? ?��?경로
let _projectListCache = [];
let _projectGatePage = 1;
let _projectGateSort = { key: 'name', dir: 'asc' };
const $breadcrumb = $('#folder-breadcrumb');

function _getCurrentProjectName() {
    return (currentBrowsePath || '').split('/').filter(Boolean)[0] || '';
}

function _setProjectControlsEnabled() {
    const hasProject = !!_getCurrentProjectName();
    const canEdit = window.__currentUserRole !== 'viewer';
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
        $slideList.innerHTML = '';
        _syncProjectSelect();

        // �??�더
        if (data.folders.length === 0 && data.slides.length === 0) {
            $slideList.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;text-align:center;">Empty</div>';
        }

        // ?�더 ??��
        for (const f of data.folders) {
            const folderPath = currentBrowsePath ? `${currentBrowsePath}/${f.name}` : f.name;
            const item = document.createElement('div');
            item.className = 'slide-list-item folder-item';
            item.dataset.folderPath = folderPath;

            const icon = document.createElement('span');
            icon.className = 'folder-icon';
            icon.textContent = '?��';

            const name = document.createElement('div');
            name.className = 'slide-list-name';
            name.textContent = f.name;

            item.append(icon, name);

            // ?�블?�릭 ???�더 진입
            item.addEventListener('click', () => navigateToFolder(folderPath));
            // ?�클�???컨텍?�트 메뉴
            item.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                showFolderContextMenu(e, folderPath, f.name);
            });
            // ?�래�?????(?�일???�더???�롭) ??OS ?�일 + ?��? ?�동 모두 �???            item.addEventListener('dragover', (e) => { e.preventDefault(); item.classList.add('drag-over'); });
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

        // ?�라?�드 ??��
        for (const s of data.slides) {
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
            // closure 캡처 ??currentBrowsePath �? ?�중??바�?�어?????�네?��? 처음 경로 ?��?.
            const str_thumb_filename = s.filename;
            const str_thumb_path = currentBrowsePath;
            thumb.src = api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 96);
            // 401 (만료??mt) ?????�켓?�로 1???�시????그래???�패?�면 ?��?.
            api.attachMediaImageRetry(thumb,
                () => api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 96),
                () => { thumb.style.display = 'none'; });

            const name = document.createElement('div');
            name.className = 'slide-list-name';
            name.textContent = s.filename;
            name.title = `${s.filename} (${s.size_mb} MB)`;

            item.append(thumb, name);

            // AI ?�태 배�?
            if (strSlideStatus) {
                const statusMeta = {
                    pending:     { label: '??, color: '#95a5a6', title: 'AI Pending' },
                    in_progress: { label: '??, color: '#3498db', title: 'AI In Progress' },
                    done:        { label: '??, color: '#27ae60', title: 'AI Reviewed' },
                    flagged:     { label: '??, color: '#e74c3c', title: 'AI Flagged' },
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

            // ?�클�? 컨텍?�트 메뉴 (?�태 ?�정 / ??��)
            item.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // ?�재 ?�이?�이 ?�택?�어 ?��? ?�다�??�독 ?�택?�로 ?�환
                if (!item.classList.contains('selected')) {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                }
                showSlideContextMenu(e);
            });

            // ?�릭: Ctrl/Shift ?�중 ?�택, ?�반 ?�릭?? ?�일 ?�택+?�기
            item.addEventListener('click', (e) => {
                if (e.ctrlKey || e.metaKey) {
                    item.classList.toggle('selected');
                } else if (e.shiftKey) {
                    // Shift: 범위 ?�택
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
                    // ?�일 ?�릭 ???�택 초기??+ ?�기
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                    openSavedSlide(s.filename, item);
                }
            });

            // ?�래�? ?�택???�일 ?��? ?�함
            item.addEventListener('dragstart', (e) => {
                // ?�래�??�작???�이?�이 ?�택 ???�어 ?�으�??�독 ?�택
                if (!item.classList.contains('selected')) {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                }
                const selectedFiles = [...$slideList.querySelectorAll('.slide-list-item.selected')]
                    .map(el => el.dataset.filename)
                    .filter(Boolean);
                e.dataTransfer.setData('text/filenames', JSON.stringify(selectedFiles));
                e.dataTransfer.setData('text/filename', selectedFiles[0]); // ?�환
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
        console.error('?�라?�드 목록 로드 ?�패:', err);
    }
}

// ???? AI 진행 �?배�? (auto/manual 공통) ????
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
    // ?�중 ?�일 ?�동
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
        setStatus(`${filenames.length}�??�일 ?�동 ?�료`);
    } catch (err) { setStatus(`?�동 ?�패: ${err.message}`); }
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

// 좌측 ?�라?�드 리스??�??�역??OS ?�일 ?�롭 ???�재 ?�더�??�로??(function _initSlideListOsDrop() {
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
            sep.textContent = '??;
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
    setStatus('?�는 �?..');
    try {
        const info = await api.openSlide(filename, currentBrowsePath);
        if (info.exists) {
            $slideList.querySelectorAll('.slide-list-item').forEach(el => el.classList.remove('active'));
            if (itemEl) itemEl.classList.add('active');
            onSlideLoaded(info.slide_id, info, filename);
        }
    } catch (err) {
        setStatus(`?�기 ?�패: ${err.message}`);
    }
}

// ???? ?�더 ?�성 ????
$('#btn-new-folder').addEventListener('click', async () => {
    if (!_getCurrentProjectName()) {
        alert('Select a project before creating folders.');
        _showProjectGate(_projectListCache);
        return;
    }
    const name = prompt('???�더 ?�름:');
    if (!name || !name.trim()) return;
    try {
        await api.createFolder(currentBrowsePath, name.trim());
        loadSlideList();
    } catch (err) {
        alert(`?�더 ?�성 ?�패: ${err.message}`);
    }
});

// ???? ?�더 ?�클�?컨텍?�트 메뉴 ????
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
        const newName = prompt('???�름:', folderName);
        if (!newName || !newName.trim() || newName.trim() === folderName) return;
        try {
            await api.renameFolder(folderPath, newName.trim());
            loadSlideList();
        } catch (err) { alert(`?�름 �?�??�패: ${err.message}`); }
    });

    const deleteBtn = document.createElement('div');
    deleteBtn.className = 'ctx-menu-item danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', async () => {
        removeCtxMenu();
        if (!confirm(`"${folderName}" ?�더�???��?�시겠습?�까?`)) return;
        try {
            await api.deleteFolder(folderPath);
            loadSlideList();
        } catch (err) { alert(`??�� ?�패: ${err.message}`); }
    });

    const aiCfgBtn = document.createElement('div');
    aiCfgBtn.className = 'ctx-menu-item';
    aiCfgBtn.textContent = 'AI ?�동 분석 ?�정...';
    aiCfgBtn.addEventListener('click', () => {
        removeCtxMenu();
        openFolderAiConfigDialog(folderPath, folderName);
    });

    menu.append(renameBtn, deleteBtn, aiCfgBtn);
    document.body.appendChild(menu);
    _ctxMenu = menu;
}

// ???? ?�라?�드 ?�클�?컨텍?�트 메뉴 ????
function _getSelectedSlideFilenames() {
    return [...$slideList.querySelectorAll('.slide-list-item.selected:not(.folder-item)')]
        .map(el => el.dataset.filename)
        .filter(Boolean);
}

const SLIDE_STATUS_OPTIONS = [
    { value: 'pending',     label: 'AI Pending',     color: '#95a5a6' },
    { value: 'in_progress', label: 'AI In Progress', color: '#3498db' },
    { value: 'done',        label: 'AI Reviewed',    color: '#27ae60' },
    { value: 'flagged',     label: 'AI Flagged',     color: '#e74c3c' },
    { value: '',            label: 'Clear AI Status', color: '' },
];

async function _applyStatusToSelected(strStatus) {
    const list_filenames = _getSelectedSlideFilenames();
    if (list_filenames.length === 0) return;
    try {
        await api.setFileStatus(list_filenames, strStatus, currentBrowsePath, 'ai');
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

    // ?�더 (?�택 개수)
    const header = document.createElement('div');
    header.className = 'ctx-menu-header';
    header.textContent = list_filenames.length === 1
        ? list_filenames[0]
        : `${list_filenames.length} slides selected`;
    menu.appendChild(header);

    // Set Status ?�위 ??��
    const labelStatus = document.createElement('div');
    labelStatus.className = 'ctx-menu-label';
    labelStatus.textContent = 'Set AI Status';
    menu.appendChild(labelStatus);

    for (const opt of SLIDE_STATUS_OPTIONS) {
        const btn = document.createElement('div');
        btn.className = 'ctx-menu-item ctx-menu-status';
        if (opt.color) {
            const dot = document.createElement('span');
            dot.className = 'ctx-menu-status-dot';
            dot.style.background = opt.color;
            btn.appendChild(dot);
        } else {
            const dot = document.createElement('span');
            dot.className = 'ctx-menu-status-dot';
            dot.style.background = 'transparent';
            dot.style.border = '1px dashed #999';
            btn.appendChild(dot);
        }
        const span = document.createElement('span');
        span.textContent = opt.label;
        btn.appendChild(span);
        btn.addEventListener('click', () => {
            removeCtxMenu();
            _applyStatusToSelected(opt.value);
        });
        menu.appendChild(btn);
    }

    const sep = document.createElement('div');
    sep.className = 'ctx-menu-sep';
    menu.appendChild(sep);

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

// ???? ?�라?�드 리스??마키(?�버밴드) ?�래�??�택 ????
(function _initMarqueeSelection() {
    let bool_active = false;
    let int_startX = 0;
    let int_startY = 0;
    let el_rect = null;
    let list_baseline = []; // Ctrl/Shift ??기존 ?�택 ?��?

    $slideList.addEventListener('mousedown', (e) => {
        // ?�쪽 버튼�? ?�크롤바/?�이?????�님
        if (e.button !== 0) return;
        // ?�라?�드 ?�이???�더 ?�이???��? ?�릭?? 무시 (기존 ?�작 ?��?)
        if (e.target.closest('.slide-list-item')) return;
        // ?�네??drag 중에??브라?��? 기본 drag �? 걸릴 ???�어 ?�기?�만 처리
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

        // 교차 ?�정: �??�라?�드 ?�이??rect ?? 교차?�면 selected
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

// ?�라?�드 리스??�??�역 ?�클�?? 컨텍?�트 메뉴 ?��? (기본 방�???불필??
$slideList.addEventListener('contextmenu', (e) => {
    if (!e.target.closest('.slide-list-item')) {
        // ?�택???�라?�드�? ?�으�?메뉴 ?�시
        const list_sel = $slideList.querySelectorAll('.slide-list-item.selected:not(.folder-item)');
        if (list_sel.length > 0) {
            e.preventDefault();
            showSlideContextMenu(e);
        }
    }
});

// ???? ?�더 AI ?�동 분석 ?�정 ?�이?�로�?????
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
    // 기존 ?�정 로드
    let cfg = { enabled: false, tasks: [] };
    try { cfg = await api.getFolderAiConfig(folderPath); }
    catch (err) { console.warn('folder config 로드 ?�패:', err); }

    // ?�반 모델: model::variant key �??�택 ?��? ?�단
    // VS IHC: variant �??�택??mpp set ???�로 �?�?    const set_selected = new Set();
    const dict_vs_mpps = {};  // { variant: Set<number> }
    for (const t of (cfg.tasks || [])) {
        if (t.model === 'VS IHC') {
            if (!dict_vs_mpps[t.variant]) dict_vs_mpps[t.variant] = new Set();
            dict_vs_mpps[t.variant].add(Number(t.target_mpp ?? 2.0));
        } else {
            set_selected.add(`${t.model}::${t.variant}`);
        }
    }

    // 백드�?+ 카드
    const backdrop = document.createElement('div');
    backdrop.className = 'ai-cfg-backdrop';
    backdrop.innerHTML = `
        <div class="ai-cfg-card">
            <div class="ai-cfg-header">
                <span>AI ?�동 분석 ?�정 ??${folderName}</span>
                <button class="ai-cfg-close" type="button">&times;</button>
            </div>
            <div class="ai-cfg-body">
                <label class="ai-cfg-enable">
                    <input type="checkbox" id="ai-cfg-enabled"${cfg.enabled ? ' checked' : ''}>
                    <span>???�더???�동 분석 ?�성??/span>
                </label>
                <div class="ai-cfg-hint">
                    10분간 AI ?�용???�고 ?�로?��? ?�을 ??1분마???�캔?�서
                    ?�래 ?�택??분석???�는 ?�라?�드�??�동 추론?�니??
                </div>
                <div class="ai-cfg-list" id="ai-cfg-list"></div>
            </div>
            <div class="ai-cfg-footer">
                <button type="button" class="ai-cfg-btn ai-cfg-cancel">취소</button>
                <button type="button" class="ai-cfg-btn ai-cfg-save primary">????/button>
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
            // VS IHC: ?�위 체크박스 = ?�택??mpp �? ?�나?�도 ?�으�?checked
            const set_current = dict_vs_mpps[opt.variant] || new Set();
            const bool_parent_checked = set_current.size > 0;
            wrap.innerHTML = `
                <label class="ai-cfg-row">
                    <input type="checkbox" class="ai-cfg-parent"${bool_parent_checked ? ' checked' : ''}>
                    <span>${opt.label}</span>
                </label>
                <div class="ai-cfg-sub"${bool_parent_checked ? '' : ' hidden'}>
                    <div class="ai-cfg-sub-title">배율 ?�택:</div>
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
                    // ?�무것도 체크 ???�어 ?�으�?기본 2.0 체크
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
            setStatus(`AI ?�동 분석 ?�정 ???? ${tasks.length}�??�업`);
            close();
        } catch (err) {
            alert(`?????�패: ${err.message}`);
        }
    });
}

// ???? �??��? (리스??/ 그리?? ????
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

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// VS IHC (Virtual Staining)
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??async function startVirtualStain(stainType) {
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
    setStatus('Virtual staining ?�작...');

    viewer.setDrawMode(null);

    // ROI: polygon/rectangle annotation???�리곤으�??�달
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
        // 결과 로딩 ??같�? mpp�?PNG ?�청
        _vsLastTargetMpp = targetMpp;

        while (true) {
            await sleep(1000);
            if (!_runningAiTasks[str_key]) return;
            const st = await api.getTaskStatus(task_id);
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);

            if (st.status === 'completed') {
                onVirtualStainComplete(st.result);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus('Virtual staining 중�?????�?�?결과 ?�리 ?�료');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`Virtual staining ?�패: ${err.message}`);
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
        roi_polygons: result.roi_polygons || null,  // ?�시 ?�립??(level-0 좌표)
    });
    _setVsToggleState(true, false);
    _setVsSplitState(false, false);  // 분할 모드???�용?��? 켜야 ??
    // AI ?�료: ROI annotation ?�거 (desktop ?�작�??�치)
    viewer.clearAnnotations();
    renderAnnotationPanel();

    const tc = result.tissue_count || 0;
    const tot = result.total_patches || 0;
    setProgress(100);
    $progressLabel.textContent = result.cached
        ? 'Virtual staining loaded (cached)'
        : 'Virtual staining complete';
    setStatus(`Virtual staining complete ??${tc}/${tot} tissue patches`);
}

// VS IHC target mpp slider ??index ??mpp value
const VS_MPP_VALUES = [4.0, 2.0, 1.0, 0.5];
const VS_MPP_LABELS = [
    '4.0 µm/px (x2.5)',
    '??2.0 µm/px (x5)',
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

// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??// Quanti PD-L1 (PD-L1) ??CPS / TPS
// ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═??$btnPdScore?.addEventListener('click', startPdScore);

async function startPdScore() {
    if (_blockViewerAction()) return;
    if (!currentSlideId) return;
    if (await _maybeCancelRunning('pd-score')) return;

    _runningAiTasks['pd-score'] = { task_id: null, buttonEl: $btnPdScore };
    _setButtonRunning($btnPdScore, true);
    if ($pdScoreResult) $pdScoreResult.hidden = true;
    $progressLabel.textContent = 'PD-L1 Detection...';
    setProgress(0);
    setStatus('Quanti PD-L1 ?�작...');

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
                onPdScoreComplete(st.result, roiPolygons, tissueType);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus('Quanti PD-L1 중�?????�?�?결과 ?�리 ?�료');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`Quanti PD-L1 ?�패: ${err.message}`);
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

    // Quanti PD-L1 ?�용 ?�래???�상 override (Stomach CPS: ????계열)
    const colorMap = {};
    if (result.class_colors) {
        for (const [k, v] of Object.entries(result.class_colors)) {
            colorMap[parseInt(k)] = v;
        }
    }
    viewer.classColorOverride = Object.keys(colorMap).length > 0 ? colorMap : null;
    viewer.defaultConfidence = 0.1;  // PD-L1 고정 (SaMD ?�현??

    viewer.setDetectionResults(result.cells, roiPolygons);
    viewer.setHiddenDetectionResults?.(result.excluded_cells || [], roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    // Score 카드??polygon-ROI + confidence ?�터링된 viewer.detectionCells 로만 그린??
    // backend ??result.pd_score ??bbox-ROI 기반?�라 ?�역 그렸?????�긋?????��? ?�용 X.
    // 카드 visibility �?켜고 ?�용?? buildResultList ??_updateResultCounts �?채운??
    if ($pdScoreResult) $pdScoreResult.hidden = false;

    // status bar ?�스?�도 polygon-ROI 카운?�로 계산
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

    // onCellEdited ?? ?�일???�턴 ??_lastDetectionResult.cells �?polygon-?�터링된 ??�?    // ?�렬???�면 buildResultList �? ?�떤 경로�?result.cells �??�더?�도 ?�전.
    _lastDetectionResult.cells = viewer.detectionCells;
    _lastDetectionResult.total_cells = viewer.detectionCells.length;

    buildResultList(_lastDetectionResult);
    _updateResultCounts();   // _updatePdScoreDisplay �? polygon-ROI 기반?�로 카드 채�?
    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
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
    setStatus(`${markerLabel} ?�작...`);

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
                onPreciseIhcComplete(st.result, roiPolygons, marker);
                return;
            } else if (st.status === 'error') {
                throw new Error(st.error);
            } else if (st.status === 'cancelled') {
                setStatus(`${markerLabel} 중�?????�?�?결과 ?�리 ?�료`);
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`${markerLabel} ?�패: ${err.message}`);
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
    viewer.defaultConfidence = (marker === 'ER_PR' || marker === 'KI_67') ? 0.3 : 0.5;  // 고정 (SaMD ?�현??

    viewer.setDetectionResults(result.cells, roiPolygons);
    viewer.setHiddenDetectionResults?.(result.excluded_cells || [], roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    // Score 카드??polygon-ROI + confidence ?�터??viewer.detectionCells 기반?�로�?그린??
    // backend ??result.{her2,allred,ki67}_score ??bbox-ROI 기반?�라 ?�역 그렸????    // ?�널/?�각?��? ?�긋?????��? ?�용 X. visibility �?켜고 _updateResultCounts() �?
    // ?�리�?카운?�로 카드 ?�용 (?�수/막�?/범�?) ??채우?�록 ?�임.
    if ($ihcScoreResult) {
        $ihcScoreResult.hidden = false;
        // 마커�??�벨 ??_updateXxxScoreDisplay �? ?�시 ??��?�기???��?�?�??�레??�??�벨 방�?.
        if (result.her2_score) {
            $ihcScoreLabel.textContent = 'HER2';
        } else if (result.allred_score) {
            $ihcScoreLabel.textContent = `${markerLabel} (Allred)`;
        } else if (result.ki67_score) {
            $ihcScoreLabel.textContent = 'KI-67';
        }
    }

    // status bar ?�스?�도 polygon-ROI 카운?�로 ?�계??(backend ?�수 X).
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
        setStatus(`${markerLabel} Allred: ${ts} (PS ${int_ps} + IS ${int_is}) ??${interp} | ${displayCount.toLocaleString()} cells`);
    } else if (result.ki67_score) {
        const pos = n1 + n2 + n3;
        const tot = n0 + pos;
        const ki67Index = tot === 0 ? 0 : pos / tot * 100;
        const interp = ki67Index >= 14 ? 'High' : 'Low';
        setStatus(`KI-67 Index: ${ki67Index.toFixed(1)}% ??${interp} | ${displayCount.toLocaleString()} cells`);
    }

    // onCellEdited ?? ?�일???�턴?�로 result.cells �?polygon-?�터링된 ????맞춤.
    _lastDetectionResult.cells = viewer.detectionCells;
    _lastDetectionResult.total_cells = viewer.detectionCells.length;

    buildResultList(_lastDetectionResult);
    _updateResultCounts();   // _updateXxxScoreDisplay �? polygon-ROI 기반?�로 카드 채�?
    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
}

// ?????? VS toggle ?�퍼 ??????
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
        ? 'Split View: ON  (??IHC | Virtual H&E ??'
        : 'Split View (IHC | Virtual H&E)';
}

$btnVsToggle?.addEventListener('click', () => {
    if (_blockViewerAction()) return;
    if ($btnVsToggle.disabled) return;
    const next = $btnVsToggle.getAttribute('aria-pressed') !== 'true';
    _setVsToggleState(next, false);
    viewer.setVirtualStainVisible(next);
    // overlay�??�면 split???��?�? ?�으�?�???    if (!next) {
        _setVsSplitState(false, false);
        viewer.setVirtualStainSplitMode(false);
    }
});

$btnVsSplit?.addEventListener('click', () => {
    if (_blockViewerAction()) return;
    if ($btnVsSplit.disabled) return;
    const next = $btnVsSplit.getAttribute('aria-pressed') !== 'true';
    _setVsSplitState(next, false);
    // split??켜면 overlay??강제�?ON
    if (next) {
        _setVsToggleState(true, false);
        viewer.setVirtualStainVisible(true);
    }
    viewer.setVirtualStainSplitMode(next);
});

// ?�이�? 로드 ???�증 ?�인 ???�라?�드 목록 �??�오�?(async () => {
    try {
        const dict_me = await api.me();
        if ($userName && dict_me.str_name) {
            $userName.textContent = dict_me.str_name;
        }
        if ($projectUserName) {
            $projectUserName.textContent = dict_me.str_name || dict_me.str_username || '';
        }
        if ($projectUserRole) {
            $projectUserRole.textContent = dict_me.str_role || 'viewer';
        }
        if (dict_me.str_role === 'admin') {
            const $linkAdmin = document.getElementById('link-admin');
            if ($linkAdmin) $linkAdmin.hidden = false;
            if ($projectLinkAdmin) $projectLinkAdmin.hidden = false;
        }
        window.MediautoHeader?.render({
            active: 'viewer',
            user: dict_me,
            showAdmin: dict_me.str_role === 'admin',
            logout: () => {
                _stopAiActivePolling();
                api.logout();
            },
        });
        window.__currentUserRole = dict_me.str_role || 'viewer';
        window.__currentUserId = String(dict_me._id || '');
        if (window.__currentUserRole === 'viewer') {
            _applyViewerRoleRestrictions();
        }
    } catch (_) {
        // ?�증 ?�패 ??api.js �? 리다?�렉??처리. ?�라?�드/?�링 ?�작 ?�략.
        return;
    }
    // URL ?�라미터�??�라?�드 ?�동 ?�기 (?slide=filename&path=rel_path)
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
        // ?�라?�드 목록 로드 ???�동 ?�기
        openSavedSlide(_paramSlide, null);
        // URL ?�라미터 ?�거 (?�로�?�????�로??방�?)
        history.replaceState(null, '', '/ai');
    }
})();
