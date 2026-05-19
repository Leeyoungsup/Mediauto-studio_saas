/**
 * MeDIAuto Studio SaaS — 메인 앱
 * 기존 PyQt5 viewer.py의 UI 로직을 JS로 포팅
 */

import { api } from './api.js';
import { TileViewer } from './tile-viewer.js?v=20260518-31';
import { showVisualization } from './visualization.js';

// ── 미로그인 가드 ──
// 토큰 없는 상태에서 /ai 로 직접 들어오면 뷰어 UI 가 잠깐 그려진 뒤 api.me()
// 의 401 까지 보고서야 리다이렉트가 일어나 깜빡임이 생긴다. home.js 와 동일한
// 패턴으로 첫 줄에서 차단. replace() 로 history 에 이 broken state 가 안 남게.
if (!localStorage.getItem('access_token')) {
    window.location.replace('/login');
    // 모듈 본체는 곧 navigation 으로 unload 되지만, 이후 코드가 실행되면서 발생하는
    // null 참조를 막기 위해 명시적으로 throw — 콘솔 에러 한 줄로 끝난다.
    throw new Error('Not authenticated — redirecting to /login');
}

// HTML escape — innerHTML 에 들어갈 신뢰 불가 문자열 (filename, annotation name,
// vendor 등) 에 반드시 통과시켜 stored XSS 차단.
function _esc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── DOM 요소 ──
const $ = (sel) => document.querySelector(sel);

function _isAnnotationPage() {
    return true;
}

const ANNOTATION_PAGE_KIND = location.pathname.includes('cell') ? 'cell' : 'tissue';
const ANNOTATION_PAGE_ROUTE = ANNOTATION_PAGE_KIND === 'cell' ? '/cell-annotation' : '/tissue-annotation';
const ANNOTATION_HEADER_ACTIVE = ANNOTATION_PAGE_KIND === 'cell' ? 'cell-annotation' : 'tissue-annotation';

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

// 사용자 메뉴
const $userName = $('#user-name');
const $btnLogout = $('#btn-logout');
const $projectUserName = $('#project-user-name');
const $projectUserRole = $('#project-user-role');
const $projectBtnLogout = $('#project-btn-logout');
const $projectLinkAdmin = $('#project-link-admin');

// 툴바 버튼
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
// 현재 뷰어에 올라간 결과의 AI 모드 ("Quanti HE" | "Quanti PD-L1" | "Quanti IHC")
let _lastDetectionModel = null;
// 로드된 결과를 onXxxComplete 로 재투입할 때 필요한 ROI (없으면 null)
let _lastDetectionRoi = null;

function _isViewerRole() {
    return window.__currentUserRole === 'viewer';
}

function _blockViewerAction(message = 'Viewer 권한은 AI/annotation 기능을 사용할 수 없습니다.') {
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

// ── 상태 ──
let currentSlideId = null;
let currentSlideInfo = null;
let currentSlideFilename = '';
let currentSlideMemo = '';
let currentSlideMemoHistory = [];
let currentAnnotationStatus = '';
let _annotationStatusSaving = false;
let _annotationRunningStep = '';
let _annotationWorkflowFinished = false;
let minimapImage = null;
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

async function _saveAnnotationWorkflowStorageStatus(filename, status) {
    try {
        await api.setFileStatus([filename], status, currentBrowsePath, 'annotation');
    } catch (err) {
        if (status === 'termination') {
            await api.setFileStatus([filename], 'flagged', currentBrowsePath, 'annotation');
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
    if (state === 'complete') return '\u2713';
    if (state === 'running') return '...';
    if (state === 'active') return '\u25b6';
    return '-';
}

function _nextAnnotationWorkflowStatus(status) {
    const int_current = _annotationWorkflowIndex(status);
    return ANNOTATION_WORKFLOW_ORDER[Math.min(int_current + 1, ANNOTATION_WORKFLOW_ORDER.length - 1)];
}

// ── 뷰어 초기화 ──
const viewer = new TileViewer($canvas, $overlay);

viewer.onZoomChange = (zoom, mag, mpp) => {
    $zoomInfo.textContent = `${mag.toFixed(1)}x  |  MPP ${mpp.toFixed(3)} μm/px`;
};
viewer.onViewChange = () => updateMinimap();

// ── 슬라이드 초기 3-stage 프리로드 로딩창 ──
// 프로그래스 바가 가리키는 것은 **클라이언트 측 stage 2 타일 다운로드 진행률** 이다.
// 서버의 tile_generator 진행률은 따로 있지만 (지금은 미사용), 사용자가 실제로
// "기다리는" 시간은 서버 생성 + 클라이언트 HTTP 다운로드 둘 다. 그래서 바 자체가
// 클라이언트 preload 에만 매핑되도록 해두면:
//   - 이미 타일이 디스크에 있는 슬라이드: 다운로드가 빠르게 → 바 빠르게 찬다
//   - 아직 생성 중인 슬라이드: 서버 생성 대기로 HTTP 가 느리게 → 바 느리게 찬다
// "바 100% = 화면 준비 완료" 라는 직관과 일치.
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

// ── 마우스 좌표 오버레이 (씬 좌표 기준 px) ──
const $mousePosOverlay = $('#mouse-pos-overlay');
if ($mousePosOverlay) {
    $canvas.addEventListener('mousemove', (e) => {
        if (!currentSlideId) return;
        const rect = $canvas.getBoundingClientRect();
        const [sx, sy] = viewer.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
        $mousePosOverlay.textContent = `x: ${Math.round(sx)}px, y: ${Math.round(sy)}px`;
    });
    $canvas.addEventListener('mouseleave', () => {
        // 값은 유지하되 살짝 흐리게
    });
}

// ═══════════════════════════
// 탭 전환
// ═══════════════════════════
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (btn.disabled) return;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        $(`#${btn.dataset.tab}`).classList.add('active');
    });
});

// ── AI Analysis 도움말 (현재 탭의 모델 설명) ──
const AI_MODEL_HELP = {
    'hne-tab': {
        title: 'Quanti HE — H&E Cell Detection',
        body: 'H&E 염색 슬라이드에서 개별 세포를 검출하고 8가지 클래스로 분류합니다 (Neutrophil, Epithelial, Lymphocyte, Plasma, Eosinophil, Stromal cell, Tumor Epithelial, Benign Epithelial). Tumor Proportion (Tumor/(Tumor+Benign)) 을 자동 계산합니다. 조직 타입 (Breast/Stomach/Other) 에 따라 전용 가중치를 사용합니다.',
    },
    'vs-tab': {
        title: 'VS IHC — Virtual Staining',
        body: 'IHC 슬라이드를 입력으로 가상의 H&E 이미지를 생성합니다 (Membrane/Nucleus 모델). Target Resolution (µm/px) 가 낮을수록 고배율 상세 이미지이지만 연산 비용이 큽니다 (기본 2.0 µm/px ≈ x5). 결과는 뷰어 오버레이 및 Split view 로 원본과 비교할 수 있습니다.',
    },
    'pd-tab': {
        title: 'Quanti PD-L1 — PD-L1 Scoring',
        body: 'PD-L1 IHC 슬라이드에서 세포를 검출해 PD-L1 점수를 계산합니다. Stomach: CPS = (Positive Tumor + Positive Immune) / Viable Tumor × 100. Lung: TPS = Positive Tumor / (Pos + Neg Tumor) × 100. 검증된 고정 confidence threshold 0.1 이상의 셀만 점수에 반영됩니다 (SaMD 재현성 보장).',
    },
    'ihc-tab': {
        title: 'Quanti IHC — HER2 / ER / PR / KI-67',
        body: 'Quanti IHC 모델은 IHC 슬라이드 상에서 염색 강도 (0+/1+/2+/3+) 로 세포를 분류합니다. HER2 는 Dominant intensity 와 weighted mean (∑(i·nᵢ)/∑nᵢ) 으로, ER/PR 은 Allred Score (Proportion 0–5 + Intensity 0–3 = Total 0–8) 로, KI-67 은 Labeling Index (Positive / Total × 100%) 로 판독합니다.',
    },
};
const $aiHelpIcon = document.querySelector('#ai-help-icon');
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

// ═══════════════════════════
// 사용자 인증 UI
// ═══════════════════════════
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

// ═══════════════════════════
// 파일 열기 + 업로드
// ═══════════════════════════
// ── 업로드 팝업 ──
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

// 팝업에서 업로드 완료 알림 수신
window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'upload-complete') {
        loadSlideList();
        setStatus(`${e.data.count}개 파일 업로드 완료`);
    }
});

const SLIDE_EXT_PATTERN = /\.(svs|ndpi|tif|tiff|mrxs|vms|vmu|scn)$/i;

// uploadFiles — 드래그 앤 드롭 등에서 호출 시 팝업으로 전달
async function uploadFiles(fileList, _targetPath) {
    const files = [...fileList].filter(f => SLIDE_EXT_PATTERN.test(f.name));
    if (!files.length) {
        setStatus('지원하는 슬라이드 파일이 없습니다');
        return;
    }
    openUploadPopup(fileList, _targetPath || currentBrowsePath);
}

// 하위 호환 — 기존 uploadOneFile 참조 방지 (사용처 없음)
async function uploadOneFile() { /* deprecated — upload 팝업 사용 */ return null; }

// ── Scanner/Vendor 배지 ──
// openslide vendor string 은 소문자 키워드 형태. 인라인 SVG 로고로 매핑.
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

    // 키워드 매칭 (openslide 의 vendor 값은 'hamamatsu', 'aperio', 'mirax', ... 등)
    let meta = null;
    for (const [key, m] of Object.entries(SCANNER_META)) {
        if (str_vendor.includes(key)) { meta = m; break; }
    }

    const int_mag = slideInfo.objective_power && slideInfo.objective_power !== 'Unknown'
        ? `${slideInfo.objective_power}x` : '';
    const str_mpp = slideInfo.mpp_x ? `${slideInfo.mpp_x.toFixed(3)} µm/px` : '';
    const list_details = [int_mag, str_mpp].filter(Boolean);
    const str_info = list_details.join(' · ');

    // meta.label / meta.svg 는 코드 내 정의된 안전한 상수.
    // slideInfo.vendor 는 슬라이드 파일 메타 — 신뢰 불가 → escape.
    if (meta) {
        $slideScanner.innerHTML = `
            <span class="scanner-logo" title="${_esc(meta.label)}">${meta.svg}</span>
            ${str_info ? `<span class="scanner-info">${_esc(str_info)}</span>` : ''}
        `;
        $slideScanner.style.borderLeftColor = meta.color;
    } else {
        // 알려지지 않은 vendor: escape 한 뒤 표시
        $slideScanner.innerHTML = `
            <span class="scanner-logo scanner-logo-text">${_esc(slideInfo.vendor)}</span>
            ${str_info ? `<span class="scanner-info">${_esc(str_info)}</span>` : ''}
        `;
        $slideScanner.style.borderLeftColor = '#6c5ce7';
    }
    $slideScanner.hidden = false;
}

// ── NDP 색보정 toggle (Hamamatsu 전용) ──
// 피팅값: γ=1.094, white=247.91, affine 3x4 — color_match_analysis.ipynb 에서
// MeDIAuto Studio 타일 픽셀 ↔ NDP.view2 픽셀 5쌍 정합 후 최소제곱으로 유도.
// RMSE 4.21. color-correction.js 의 NDP_FIT 에서 관리.
const $btnNdpColor = document.getElementById('btn-ndp-color');
const $ndpColorState = $btnNdpColor ? $btnNdpColor.querySelector('.ndp-color-state') : null;

function _updateNdpColorToggleVisibility(slideInfo) {
    if (!$btnNdpColor) return;
    const str_vendor = String(slideInfo?.vendor || '').toLowerCase();
    const bool_is_hamamatsu = str_vendor === 'hamamatsu';
    $btnNdpColor.hidden = !bool_is_hamamatsu;
    if (bool_is_hamamatsu) {
        // Hamamatsu 슬라이드: 기본 ON — NDP.view2 색감이 표준이고
        // 보정 없이 보면 푸르스름하게 보여 사용자 첫 인상이 나쁘다.
        viewer.setColorCorrectionEnabled(true);
        $btnNdpColor.classList.add('active');
        if ($ndpColorState) $ndpColorState.textContent = 'ON';
    } else {
        // 비-Hamamatsu 슬라이드: 항상 OFF 로 되돌림 (피팅이 의미 없음)
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
    currentSlideFilename = filename || slideInfo?.filename || '';
    currentSlideMemo = '';
    currentSlideMemoHistory = [];
    currentAnnotationStatus = _findSlideListStatus(currentSlideFilename);
    _annotationRunningStep = _annotationWorkflowRunningStep(currentAnnotationStatus);
    _annotationWorkflowFinished = _annotationWorkflowRawStatus(currentAnnotationStatus) === 'termination';
    _syncAnnotationStatusControl(currentAnnotationStatus);

    // 슬라이드 전환 — 이전 슬라이드의 sticky 클래스는 의미 없음 (class id/이름 매핑이
    // 새 detection 결과에 따라 다를 수 있음). HUD 도 같이 숨김.
    _stickyAddClassId = null;
    _hideStickyHud();

    $slideName.textContent = filename;
    _updateScannerBadge(slideInfo);
    _updateNdpColorToggleVisibility(slideInfo);
    setStatus(`Loaded: ${slideInfo.dimensions[0]}x${slideInfo.dimensions[1]} (${slideInfo.level_count} levels)`);

    // 버튼 활성화
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
    // tissue-type 라디오도 기본 활성 — 이후 폴더 제한이 있으면 덮어씀
    document.querySelectorAll('input[name="tissue-type"], input[name="pd-tissue-type"]').forEach(el => {
        el.disabled = false;
    });

    // 폴더별 AI 자동 분석 설정이 있으면 해당 task 만 활성화, 나머지는 disabled.
    if (!_isViewerRole() && !_isAnnotationPage()) {
        _applyFolderAiRestrictions(currentBrowsePath);
    }

    // Viewer 역할은 AI / annotation 기능 전면 비활성. 폴더 제한보다 우선.
    if (_isViewerRole()) {
        _applyViewerRoleRestrictions();
    }

    // 뷰어 로드 (타일은 요청 시 즉석 생성 + 백그라운드 프리제네레이션)
    viewer.loadSlide(slideId, slideInfo);

    if ($mousePosOverlay) $mousePosOverlay.hidden = false;

    // 미니맵
    loadMinimap(slideId);

    // 결과 초기화
    clearResults();

    // VS IHC 오버레이 초기화
    viewer.clearVirtualStainOverlay();
    _setVsToggleState(false, true);
    _setVsSplitState(false, true);

    _loadSavedAnnotationsForSlide(slideId);

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
    if ($annotationStatusSelect) {
        $annotationStatusSelect.value = SLIDE_STATUS_OPTIONS.some(opt => opt.value === strStatus)
            ? strStatus
            : 'annotation';
        $annotationStatusSelect.disabled = boolDisabled;
    }
    if (!$annotationStatusWorkflow) return;
    const intCurrent = _annotationWorkflowIndex(strStatus);
    $annotationStatusWorkflow.dataset.status = strStatus;
    $annotationStatusWorkflow.classList.toggle('is-disabled', boolDisabled);
    $annotationStatusWorkflow.classList.toggle('is-running', !!_annotationRunningStep);
    $annotationStatusWorkflow.querySelectorAll('[data-annotation-status]').forEach((btn) => {
        const strTarget = _normalizeAnnotationWorkflowStatus(btn.dataset.annotationStatus);
        const intTarget = _annotationWorkflowIndex(strTarget);
        const boolComplete = intTarget < intCurrent || (_annotationWorkflowFinished && strTarget === 'termination');
        const boolActive = strTarget === strStatus && !_annotationWorkflowFinished;
        const boolRunning = _annotationRunningStep === strTarget;
        const strLabel = SLIDE_STATUS_OPTIONS.find(opt => opt.value === strTarget)?.label || strTarget;
        const strAction = boolComplete ? '완료' : (boolRunning ? '진행중' : (boolActive ? '▶' : '-'));
        btn.textContent = `${strLabel} ${strAction}`;
        btn.classList.toggle('is-active', boolActive);
        btn.classList.toggle('is-complete', boolComplete);
        btn.classList.toggle('is-running', boolRunning);
        btn.disabled = boolDisabled;
        btn.title = boolActive
            ? (boolRunning ? `${strLabel} complete` : `${strLabel} start`)
            : `Move to ${strLabel}`;
    });
    const connectorA = $annotationStatusWorkflow.querySelector('[data-connector="annotation-review"]');
    const connectorB = $annotationStatusWorkflow.querySelector('[data-connector="review-termination"]');
    if (connectorA) connectorA.textContent = intCurrent > 0 ? '✓' : '-';
    if (connectorB) connectorB.textContent = intCurrent > 1 || _annotationWorkflowFinished ? '✓' : '-';
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

// ═══════════════════════════
// 폴더별 AI 자동 분석 제한
// ──
// 폴더에 자동 분석 설정이 저장돼 있으면 (bool_enabled=true AND tasks 존재),
// 해당 task(model+variant) 에 속하지 않는 AI 버튼/라디오를 모두 disabled 로 만든다.
// 설정이 없거나 enabled=false 면 아무것도 제한하지 않는다 (기본 모두 활성).
// ═══════════════════════════

async function _applyFolderAiRestrictions(strFolderPath) {
    if (_isViewerRole()) return;

    let cfg = null;
    try {
        cfg = await api.getFolderAiConfig(strFolderPath || '');
    } catch (err) {
        console.warn('[folder-ai-restrict] load 실패:', err);
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
        // 현재 선택된 것이 허용되지 않으면 첫 허용 옵션으로 자동 전환
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

    // Quanti IHC — 마커별 버튼 단위
    if ($btnIhcHer2) $btnIhcHer2.disabled = !set_allowed.has('Quanti IHC::HER2');
    if ($btnIhcErPr) $btnIhcErPr.disabled = !set_allowed.has('Quanti IHC::ER_PR');
    if ($btnIhcKi67) $btnIhcKi67.disabled = !set_allowed.has('Quanti IHC::KI_67');

    // VS IHC — ihc_membrane 모델이 모든 케이스 처리. target_mpp 는 제한 안 함.
    const bool_vs_any = set_allowed.has('VS IHC::ihc_membrane');
    $btnVsMembrane.disabled = !bool_vs_any;

    // ── 활성 모델이 없는 탭 전체 숨김 ──
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

    // 첫 번째 보이는 탭을 활성화
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

// ═══════════════════════════
// Viewer 역할 제한 — AI 기능 / annotation 전면 비활성
// ═══════════════════════════
function _applyViewerRoleRestrictions() {
    document.body.classList.add('role-viewer');
    _stopAiActivePolling();

    // Annotation 그리기 도구 (상단 툴바)
    const list_draw_btns = ['btn-draw-polygon', 'btn-draw-brush', 'btn-draw-rect', 'btn-draw-point', 'btn-cut-polygon',
                            'btn-draw-rect-1mm2', 'btn-draw-circle-1mm2', 'btn-ruler'];
    list_draw_btns.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.classList.remove('active');
            el.title = 'Viewer 권한은 annotation 기능을 사용할 수 없습니다';
        }
    });
    // 그리기 모드가 켜져있었다면 해제
    if (viewer && viewer.drawMode) viewer.setDrawMode(null);

    // AI 분석 버튼 전체 비활성
    const list_ai_btn_ids = [
        'btn-detect', 'btn-pd-score', 'btn-ihc-her2', 'btn-ihc-erpr',
        'btn-ihc-ki67', 'btn-vs-membrane', 'btn-vs-toggle', 'btn-vs-split',
        'btn-visualize', 'btn-clear-results', 'btn-save-results', 'btn-load-results',
    ];
    list_ai_btn_ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = 'Viewer 권한은 AI 분석 기능을 사용할 수 없습니다.';
        }
    });

    // AI 입력 (tissue-type radio 등) 비활성
    document.querySelectorAll(
        '#right-panel .panel-group:first-child input, #right-panel .panel-group:first-child button'
    ).forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer 권한은 AI 분석 기능을 사용할 수 없습니다.';
    });

    // Annotation 패널의 저장/불러오기/초기화 버튼
    ['btn-ann-clear', 'btn-ann-save',
     'btn-slide-memo',
     'btn-new-project', 'btn-rename-project', 'btn-delete-project'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = true;
            el.title = 'Viewer 권한은 annotation 기능을 사용할 수 없습니다.';
        }
    });

    document.querySelectorAll('.annotation-group button, .annotation-group input, .annotation-group select').forEach(el => {
        el.disabled = true;
        if (!el.title) el.title = 'Viewer 권한은 annotation 기능을 사용할 수 없습니다.';
    });
}

// ═══════════════════════════
// 드래그 앤 드롭
// ═══════════════════════════
const $viewerContainer = $('#viewer-container');

// OS 파일 드래그만 감지 (뷰어 내부 요소/텍스트 드래그는 무시)
function _isFileDrag(e) {
    const t = e.dataTransfer && e.dataTransfer.types;
    if (!t) return false;
    // DOMStringList / Array 모두 지원
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

// ═══════════════════════════
// 미니맵
// ═══════════════════════════
async function loadMinimap(slideId) {
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
    // CSS width 기준 (리사이즈 대응)
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

// 미니맵 최소화 토글
const $minimapToggle = $('#minimap-toggle');
const $minimapIcon = $('#minimap-toggle-icon');
$minimapToggle?.addEventListener('click', (e) => {
    e.stopPropagation();
    const minimized = $minimapContainer.classList.toggle('minimized');
    // minimize: — icon, expand: + icon
    $minimapIcon.setAttribute('d', minimized ? 'M3 7h8M7 3v8' : 'M3 7h8');
    $minimapToggle.title = minimized ? 'Expand' : 'Minimize';
});

// 미니맵 리사이즈 (오른쪽 위 모서리 드래그 → 크기 조절)
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

// ═══════════════════════════
// 줌 컨트롤
// ═══════════════════════════
$btnZoomIn.addEventListener('click', () => viewer.zoomIn());
$btnZoomOut.addEventListener('click', () => viewer.zoomOut());
$btnFit.addEventListener('click', () => viewer.fitToWindow());

// ═══════════════════════════
// Annotation 그리기 도구
// ═══════════════════════════
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

function setDrawMode(mode) {
    if (_blockViewerAction('Viewer 권한은 annotation 기능을 사용할 수 없습니다.')) return;
    // 같은 버튼 다시 클릭 → 해제
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
if ($btnDrawRect1mm2) $btnDrawRect1mm2.addEventListener('click', () => setDrawMode('rect-1mm2'));
if ($btnDrawCircle1mm2) $btnDrawCircle1mm2.addEventListener('click', () => setDrawMode('circle-1mm2'));
if ($btnRuler) $btnRuler.addEventListener('click', () => setDrawMode('ruler'));

// ── UX 기능 설명 모달 ──
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

// ── 모바일 패널 토글 (≤900px) ──
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
// 브레이크포인트 넘어가면 drawer 상태 정리
window.matchMedia('(max-width: 900px)').addEventListener('change', (e) => {
    if (!e.matches) _closeMobilePanels();
});

// ESC 등으로 drawMode가 변경될 때 버튼 동기화
viewer.onDrawModeChange = (mode) => {
    Object.values(drawButtons).forEach(b => { if (b) b.classList.remove('active'); });
    if (mode && drawButtons[mode]) drawButtons[mode].classList.add('active');
};

// ── Annotation Panel ──
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

function _canManageAnnotationClasses() {
    return window.__currentUserRole === 'doctor' || window.__currentUserRole === 'admin';
}

function _blockClassManageAction() {
    if (_canManageAnnotationClasses()) return false;
    alert('Class management is available to doctor/admin only.');
    return true;
}

function _getAnnotationClass(classId) {
    return _annotationClasses.find(c => c.id === classId) || _annotationClasses[0] || _DEFAULT_ANNOTATION_CLASSES[0];
}

function _syncActiveAnnotationClassToViewer() {
    const cls = _getAnnotationClass(_activeAnnotationClassId);
    if (cls) viewer.setAnnotationDrawColor?.(cls.color);
}

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

function _makeClassId(name) {
    const base = String(name || 'Class')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9가-힣_-]+/g, '_')
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
        const classId = ann.class_id || ann.properties?.class_id || _activeAnnotationClassId;
        const cls = _getAnnotationClass(classId);
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
            const res = await api.saveAnnotationClasses(projectName, _annotationClasses);
            if (Array.isArray(res.classes)) {
                _annotationClasses = res.classes.map(_normalizeAnnotationClass);
            }
            setStatus('Annotation classes saved');
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
        const res = await api.loadAnnotationClasses(projectName);
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
    if ($btnClassApply) {
        $btnClassApply.hidden = isSettings;
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
        const row = document.createElement('div');
        row.className = 'class-row' + (cls.id === _activeAnnotationClassId ? ' active' : '') + (classHidden ? ' hidden-class' : '') + (isSettings ? ' settings' : ' apply');
        row.dataset.classId = cls.id;
        row.draggable = isSettings;
        row.innerHTML = isSettings ? `
            <button type="button" class="class-active-btn" title="Use this class"></button>
            <input type="color" class="class-color-input" value="${rgbToHex(r, g, b)}" title="Class color">
            <input type="text" class="class-name-input" value="${_esc(cls.name)}" title="Class name">
            <button type="button" class="class-visibility-btn" title="${classHidden ? 'Show class' : 'Hide class'}">${classHidden ? '◌' : '●'}</button>
            <button type="button" class="class-delete-btn" title="Delete class">Delete</button>
        ` : `
            <button type="button" class="class-active-btn" title="Select class"></button>
            <span class="class-color-chip" style="background:rgb(${r},${g},${b})"></span>
            <span class="class-name-label" title="${_esc(cls.name)}">${_esc(cls.name)}</span>
            <button type="button" class="class-visibility-btn" title="${classHidden ? 'Show class' : 'Hide class'}">${classHidden ? '◌' : '●'}</button>
            <span class="class-shortcut-label">${_annotationClasses.indexOf(cls) < 9 ? _annotationClasses.indexOf(cls) + 1 : _annotationClasses.indexOf(cls) === 9 ? 0 : ''}</span>
        `;
        const activeBtn = row.querySelector('.class-active-btn');
        const colorInput = row.querySelector('.class-color-input');
        const nameInput = row.querySelector('.class-name-input');
        const visibilityBtn = row.querySelector('.class-visibility-btn');
        const deleteBtn = row.querySelector('.class-delete-btn');
        if (colorInput) colorInput.disabled = !isSettings;
        if (nameInput) nameInput.disabled = !isSettings;
        if (deleteBtn) {
            deleteBtn.disabled = !isSettings;
            deleteBtn.title = canManage ? 'Delete class' : 'Doctor/Admin only';
        }

        const setActive = () => {
            _activeAnnotationClassId = cls.id;
            _syncActiveAnnotationClassToViewer();
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
                if (!isSettings) return;
                cls.color = hexToRgb(e.target.value);
                if (_activeAnnotationClassId === cls.id) _syncActiveAnnotationClassToViewer();
                _syncAnnotationClassMetadata();
                renderAnnotationPanel();
                _queueSaveAnnotationClasses();
            });
        }
        if (nameInput) {
            nameInput.addEventListener('change', (e) => {
                if (!isSettings) return;
                cls.name = e.target.value.trim() || cls.name;
                _syncAnnotationClassMetadata();
                renderAnnotationPanel();
                _queueSaveAnnotationClasses();
            });
        }
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => {
                if (!isSettings) return;
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
            .replace(/[^a-z0-9가-힣_-]+/g, '_')
            .replace(/^_+|_+$/g, '') || 'class';
        let id = base;
        let n = 2;
        while (seen.has(id)) id = `${base}_${n++}`;
        seen.add(id);
        return { id, name, color: _normalizeColor(cls?.color) };
    });
}

async function _openProjectClassManager(project) {
    const path = project?.path || project?.name || '';
    if (!path) return;
    if (_blockClassManageAction()) return;

    _projectClassModal?.remove();
    const projectTitle = _projectLabel(project) || path;
    let localClasses = _DEFAULT_ANNOTATION_CLASSES.map(c => ({ ...c, color: [...c.color] }));
    let draggingProjectClassId = null;

    const modal = document.createElement('div');
    modal.className = 'project-class-modal';
    modal.innerHTML = `
        <div class="project-class-dialog" role="dialog" aria-modal="true" aria-labelledby="project-class-title">
            <div class="project-class-header">
                <div>
                    <h2 id="project-class-title">Class Management</h2>
                    <p>${_esc(projectTitle)}</p>
                </div>
                <button type="button" class="project-class-close" aria-label="Close">x</button>
            </div>
            <div class="project-class-body">
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
    const makeLocalClassId = (name) => {
        const base = String(name || 'Class')
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9가-힣_-]+/g, '_')
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
            const row = document.createElement('div');
            row.className = 'project-class-row';
            row.draggable = true;
            row.dataset.classId = cls.id;
            row.innerHTML = `
                <span class="project-class-drag" title="Drag to reorder">::</span>
                <input type="color" class="project-class-color" value="${rgbToHex(r, g, b)}" title="Class color">
                <input type="text" class="project-class-name" value="${_esc(cls.name)}" title="Class name">
                <button type="button" class="project-class-delete">Delete</button>
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
                cls.color = hexToRgb(e.target.value);
            });
            row.querySelector('.project-class-name').addEventListener('input', (e) => {
                cls.name = e.target.value.trim() || `Class ${idx + 1}`;
            });
            row.querySelector('.project-class-delete').addEventListener('click', () => {
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
            const res = await api.saveAnnotationClasses(path, localClasses);
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
            setStatus('Project classes saved');
            close();
        } catch (err) {
            statusEl.textContent = `Save failed: ${err.message}`;
            saveBtn.disabled = false;
        }
    });

    render();
    try {
        const res = await api.loadAnnotationClasses(path);
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
    const ann = viewer.annotations.find(a => a.id === viewer.selectedAnnotationId);
    if (!ann) {
        setStatus('Select an annotation first');
        return;
    }
    if (_blockViewerAction('Viewer role can view annotations only.')) return;
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
    if (!ann || _blockViewerAction('Viewer role can view annotations only.')) return;
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
    if (_blockViewerAction('Viewer role can view annotations only.')) return;
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

$btnSlideMemo?.addEventListener('click', _editSlideMemo);

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
        return _getAnnotationClass(ann.class_id || ann.properties?.class_id).name.toLowerCase();
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

function renderAnnotationPanel() {
    if (!$annList) return;
    $annList.innerHTML = '';
    const header = document.createElement('div');
    header.className = 'ann-list-header';
    _ANNOTATION_LIST_COLUMNS.forEach(({ key, label }) => {
        const cell = document.createElement('span');
        cell.className = 'ann-sort-header' + (_annotationListSort.key === key ? ' active' : '');
        cell.dataset.sortKey = key;
        cell.textContent = `${label}${_annotationListSort.key === key ? (_annotationListSort.dir === 'asc' ? ' ▲' : ' ▼') : ''}`;
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
    for (const { ann } of _sortedAnnotationEntries()) {
        const annClass = _getAnnotationClass(ann.class_id || ann.properties?.class_id);
        const displayId = _annotationDisplayId(ann);
        const memo = _annotationMemo(ann);
        const memoHistory = _annotationMemoHistory(ann);
        const hasAnsweredMemo = memoHistory.some(item => item.answer);
        const memoLabel = memo ? 'M' : (hasAnsweredMemo ? 'H' : '-');
        const memoTitle = memo ? memo : (memoHistory.length ? `${memoHistory.length} previous memo(s)` : 'No memo');
        const memoClass = memo ? ' has-memo' : (hasAnsweredMemo ? ' has-history' : '');
        const el = document.createElement('div');
        el.className = 'ann-item' + (ann.selected ? ' selected' : '');
        el.dataset.id = ann.id;
        // ann.name 은 사용자 더블클릭 rename 으로 임의 문자열 가능 — 반드시 escape
        el.innerHTML = `
            <span class="ann-id" title="Double-click to center">${_esc(displayId)}</span>
            <span class="ann-class-wrap" style="--ann-class-color: rgb(${_normalizeColor(annClass.color).join(',')})">
                <select class="ann-class-select" title="Annotation class">
                    ${_annotationClasses.map(cls => `<option value="${_esc(cls.id)}"${cls.id === annClass.id ? ' selected' : ''}>${_esc(cls.name)}</option>`).join('')}
                </select>
            </span>
            <button class="ann-btn-memo${memoClass}" title="${_esc(memoTitle)}">${memoLabel}</button>
            <button class="ann-btn-vis" title="${ann.visible ? 'Hide annotation' : 'Show annotation'}">${_visibilityIcon(ann.visible !== false)}</button>
            <button class="ann-btn-del" title="Delete">Del</button>
        `;
        // 클릭 → 선택
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
        el.addEventListener('click', (e) => {
            if (e.target.closest('.ann-btn-memo') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') ||
                e.target.closest('.ann-class-select')) return;
            viewer.selectAnnotation(ann.id);
        });
        el.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            viewer.selectAnnotation(ann.id);
            _editAnnotationMemo(ann);
        });
        el.addEventListener('dblclick', (e) => {
            if (e.target.closest('.ann-btn-memo') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') ||
                e.target.closest('.ann-class-select')) return;
            e.preventDefault();
            viewer.selectAnnotation(ann.id);
            if (typeof viewer.centerOnAnnotation === 'function') {
                viewer.centerOnAnnotation(ann);
                setStatus(`Centered on annotation ${displayId}`);
            }
        });
        // 더블클릭 이름 → 리네임
        el.querySelector('.ann-btn-memo').addEventListener('click', (e) => {
            e.stopPropagation();
            viewer.selectAnnotation(ann.id);
            _editAnnotationMemo(ann);
        });
        el.querySelector('.ann-class-select').addEventListener('change', (e) => {
            e.stopPropagation();
            if (_blockViewerAction('Viewer role can view annotations only.')) return;
            viewer.pushAnnotationUndo?.();
            _applyClassToAnnotation(ann, e.target.value);
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
            renderAnnotationPanel();
        });
        // 가시성 토글
        el.querySelector('.ann-btn-vis').addEventListener('click', (e) => {
            e.stopPropagation();
            ann.visible = !ann.visible;
            viewer.requestRender();
            renderAnnotationPanel();
        });
        // 삭제
        el.querySelector('.ann-btn-del').addEventListener('click', (e) => {
            e.stopPropagation();
            if (_blockViewerAction('Viewer role can view annotations only.')) return;
            viewer.deleteAnnotation(ann.id);
        });
        $annList.appendChild(el);
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

// 캔버스 ↔ 패널 동기화
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
    const ann = viewer.annotations.find(a => a.id === viewer.selectedAnnotationId);
    if (!ann) return false;
    if (_blockViewerAction('Viewer 권한은 annotation class를 변경할 수 없습니다.')) return true;
    const cls = _annotationClasses[idx];
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

window.addEventListener('keydown', (e) => {
    _assignSelectedAnnotationClassByShortcut(e);
}, true);

viewer.onAnnotationCreated = (ann) => {
    _applyClassToAnnotation(ann, _activeAnnotationClassId);
    _syncActiveAnnotationClassToViewer();
    setStatus(`Annotation ${_annotationDisplayId(ann)} created`);
    renderAnnotationPanel();
};
viewer.onAnnotationSelected = (ann) => {
    if (ann?.class_id || ann?.properties?.class_id) {
        const cls = _getAnnotationClass(ann.class_id || ann.properties?.class_id);
        if (cls) {
            _activeAnnotationClassId = cls.id;
            _syncActiveAnnotationClassToViewer();
        }
    }
    renderClassManagementPanel();
    renderAnnotationPanel();
};
viewer.onAnnotationDeleted = (ann) => {
    renderAnnotationPanel();
    _setSlideListMemoIndicator();
};
viewer.onAnnotationChanged = (ann) => {
    // 이미 렌더링 요청됨 — 패널만 갱신 필요 시
};
viewer.onAnnotationContextMenu = (ann) => {
    _editAnnotationMemo(ann);
};

// deleteAnnotation에서 콜백 호출되도록 오버라이드
const _origDelete = viewer.deleteAnnotation.bind(viewer);
viewer.deleteAnnotation = (id) => {
    const ann = viewer.annotations.find(a => a.id === id);
    _origDelete(id);
    if (ann && viewer.onAnnotationDeleted) viewer.onAnnotationDeleted(ann);
};

// ═══════════════════════════
// Cell Edit 팝업 (Alt+Click)
// ═══════════════════════════
let _cellEditPopupEl = null;

function _closeCellEditPopup() {
    if (_cellEditPopupEl) {
        _cellEditPopupEl.remove();
        _cellEditPopupEl = null;
    }
    viewer.clearCellHighlight();
    viewer.clearMultiCellHighlight();
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
    // Delete/D 는 셀이 있는 edit/multi 모드에서만 — add/sticky-pick 엔 삭제 대상 없음.
    if ((e.key === 'Delete' || e.key.toLowerCase() === 'd') &&
            _cellEditCtx.mode !== 'add' && _cellEditCtx.mode !== 'sticky-pick') {
        _doDeleteCell();
        e.preventDefault();
        return;
    }
    // 숫자키 1~9, 0 → 클래스 선택. 모드별 분기:
    //   edit/multi → 클래스 변경, add → 클릭 위치에 셀 추가, sticky-pick → sticky 만 갱신.
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
    if (_cellEditCtx.multi) {
        viewer.changeCellsClass(_cellEditCtx.indices, newClsId, name);
    } else {
        viewer.changeCellClass(_cellEditCtx.idx, newClsId, name);
    }
    _closeCellEditPopup();
}

// 색을 CSS 문자열로 정규화 (hex "#RRGGBB" 또는 [r,g,b] 모두 지원)
function _toCssColor(c) {
    if (typeof c === 'string') return c;
    if (Array.isArray(c) && c.length >= 3) return `rgb(${c[0]},${c[1]},${c[2]})`;
    return 'rgb(200,200,200)';
}

/**
 * Popup 클래스 버튼에 연필(✎) 편집 아이콘을 끼워넣는다. 클릭 시 그 row 가 inline
 * 텍스트 입력 + 저장/취소 모드로 바뀌며, 저장하면 _renameClassLabel 로 전파되고
 * 입력값이 popup 의 표시 텍스트에도 반영. popup 자체는 닫지 않는다 (사용자가
 * 라벨 정리 후 동일 popup 에서 add/change 이어가는 흐름).
 */
function _attachClassRenamePencil(btnEl, classId, textSpan) {
    const pencil = document.createElement('span');
    pencil.title = '라벨 이름 편집';
    pencil.setAttribute('aria-label', 'rename label');
    pencil.style.cssText = `
        flex:0 0 22px; height:22px; margin-right:6px;
        display:flex; align-items:center; justify-content:center;
        border-radius:3px; cursor:pointer; opacity:0.55;
        font-size:13px; line-height:1;
    `;
    pencil.textContent = '✎';
    pencil.onmouseover = () => { pencil.style.opacity = '1'; pencil.style.background = 'rgba(0,0,0,0.08)'; };
    pencil.onmouseout = () => { pencil.style.opacity = '0.55'; pencil.style.background = 'transparent'; };
    pencil.addEventListener('click', (ev) => {
        ev.stopPropagation();   // row 의 select 동작 방지
        // textSpan 자리에 input + 저장/취소 버튼 임시 배치.
        const original = textSpan.textContent || '';
        // 표시값에서 [N] 단축키 prefix 가 있으면 그건 빼고 실제 라벨만 편집.
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
        ok.textContent = '✓';
        ok.title = '저장 (Enter)';
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

        // textSpan 을 임시 wrap 으로 대체.
        const parent = textSpan.parentElement;
        parent.removeChild(textSpan);
        // pencil 직전 위치에 wrap 삽입.
        parent.insertBefore(wrap, pencil);
        pencil.style.display = 'none';

        // popup 전체의 키보드 단축키(_cellEditKeydown) 가 입력을 가로채지 못하도록
        // input 이벤트는 stopPropagation. (Ctrl+Z / 숫자키 등 충돌 방지)
        input.addEventListener('keydown', (kev) => {
            kev.stopPropagation();
            if (kev.key === 'Enter') { commit(); }
            else if (kev.key === 'Escape') { abort(); }
        });
        // 외부 클릭으로 popup 닫히는 핸들러도 일시 차단 — input 자체 클릭에서.
        input.addEventListener('mousedown', (mev) => mev.stopPropagation());
        ok.addEventListener('click', (mev) => { mev.stopPropagation(); commit(); });
        cancel.addEventListener('click', (mev) => { mev.stopPropagation(); abort(); });

        const restoreText = () => {
            wrap.remove();
            // 원래 위치(pencil 직전)에 textSpan 다시 삽입.
            parent.insertBefore(textSpan, pencil);
            pencil.style.display = '';
        };
        const abort = () => { restoreText(); };
        const commit = () => {
            const str_new = input.value.trim();
            if (!str_new || str_new === initialName) { restoreText(); return; }
            const ok2 = _renameClassLabel(classId, str_new);
            if (ok2) {
                // popup 의 표시 텍스트도 동기화 — [N] prefix 유지.
                textSpan.textContent = m ? `[${m[0].match(/\d/)[0]}] ${str_new}` : str_new;
            }
            restoreText();
        };

        // 자동 포커스 + 텍스트 전체 선택.
        setTimeout(() => { input.focus(); input.select(); }, 0);
    });
    // 색 스와치 다음, 텍스트 앞에 연필 배치 — 시각적으로 텍스트 옆이 자연스럽다.
    btnEl.insertBefore(pencil, textSpan);
}

/**
 * 클래스 라벨 이름 변경 — `_lastDetectionResult.class_names[classId]` 갱신 +
 * 해당 class_id 의 모든 셀의 `class_name` 동기화 + Result 리스트 / Score 카드
 * 즉시 재렌더. 메모리에만 반영 (저장은 ROI Save 버튼이 담당).
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
    // 패널 / 카드 / status 즉시 반영.
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

    // 헤더
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const swatch = document.createElement('span');
    swatch.style.cssText = `display:inline-block;width:14px;height:14px;border-radius:3px;
        border:1px solid #888;background:${curColorCss};`;
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>${curName}</b>  (conf: ${curConf.toFixed(2)})`;
    header.append(swatch, headerLabel);
    popup.appendChild(header);

    const sep1 = document.createElement('div');
    sep1.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep1);

    const labelChange = document.createElement('div');
    labelChange.textContent = 'Change Class:';
    labelChange.style.cssText = 'margin-bottom:4px;';
    popup.appendChild(labelChange);

    // 클래스 버튼들 (현재 클래스 제외, 숫자키 매핑)
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

        // 두꺼운 색 띠 (왼쪽 전체 높이)
        const stripe = document.createElement('span');
        stripe.style.cssText = `flex:0 0 12px;align-self:stretch;
            background:${colorCss};display:block;`;

        // 색 스와치
        const sw = document.createElement('span');
        sw.style.cssText = `flex:0 0 16px;height:16px;border-radius:3px;
            background:${colorCss};border:1px solid #333;
            display:inline-block;margin-left:8px;`;

        const text = document.createElement('span');
        text.textContent = keyLabel ? `[${keyLabel}] ${name}` : name;
        text.style.cssText = 'flex:1;padding:6px 10px;';

        btn.append(stripe, sw, text);
        btn.addEventListener('click', () => _doChangeClass(cid));
        // 라벨 이름 편집 — text 옆에 연필(✎) 끼워 inline rename UI 활성화.
        _attachClassRenamePencil(btn, cid, text);
        popup.appendChild(btn);

        classButtonOrder.push(cid);
        keyIdx++;
    }

    const sep2 = document.createElement('div');
    sep2.style.cssText = 'height:1px;background:#ddd;margin:6px 0;';
    popup.appendChild(sep2);

    // 삭제 버튼
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

    // 화면 밖으로 나가지 않게 위치 보정
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

    // 외부 클릭/ESC/Del/숫자키
    setTimeout(() => {
        document.addEventListener('mousedown', _outsideCellEditClick, true);
        document.addEventListener('keydown', _cellEditKeydown, true);
    }, 0);
}

viewer.onCellEditRequested = _showCellEditPopup;

// ── Shift+click 셀 추가 ──
// Sticky class: 첫 추가 시 사용자가 popup 으로 선택한 클래스를 기억해 두고
// 다음 Shift+click 부턴 popup 없이 바로 그 클래스로 추가. Ctrl+Shift+click 또는
// 우측 패널의 클래스 라인 클릭으로 sticky 변경 가능.
let _stickyAddClassId = null;

// Shift HUD — Shift 누른 동안 마우스 우상단에 현재 sticky 클래스 표시.
// 사용자가 어떤 클래스로 추가될지 시각적으로 즉시 확인 가능.
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
    // 마우스 우상단 — cursor 와 안 겹치게 +14 우측, -28 위.
    let x = _stickyHudLastMouse.x + 14;
    let y = _stickyHudLastMouse.y - 28;
    // 화면 밖 방지 — 가로 overflow 면 좌측, 위로 overflow 면 아래로 뒤집어 배치.
    const w = _stickyHudEl.offsetWidth;
    if (x + w > window.innerWidth - 4) x = _stickyHudLastMouse.x - w - 14;
    if (y < 4) y = _stickyHudLastMouse.y + 18;
    _stickyHudEl.style.left = `${Math.max(4, x)}px`;
    _stickyHudEl.style.top  = `${Math.max(4, y)}px`;
}

function _showStickyHud() {
    // 표시 조건: Shift 누름 + sticky 살아있음 + detection 결과 + drawMode 아님.
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
    if (e.key === 'Shift' && !_stickyHudShiftHeld) {
        _stickyHudShiftHeld = true;
        _showStickyHud();
    }
}, true);
window.addEventListener('keyup', (e) => {
    if (e.key === 'Shift') {
        _stickyHudShiftHeld = false;
        _hideStickyHud();
    }
}, true);
window.addEventListener('blur', () => {
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

    // Sticky 가 살아 있으면 popup 없이 즉시 추가 — 클래스 변경은 Shift+A 단축키.
    if (_stickyAddClassId != null && classNames[String(_stickyAddClassId)]) {
        const str_name = classNames[String(_stickyAddClassId)];
        viewer.addCell(sx, sy, _stickyAddClassId, str_name);
        setStatus(`Cell added: ${str_name} — press Shift+A to change class`);
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
    // _cellEditCtx 에 mode='add' 로 표시 — 숫자 단축키도 작동.
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
        // 위치를 받은 모드 — 셀 추가 + sticky 갱신.
        viewer.addCell(_cellEditCtx.sx, _cellEditCtx.sy, classId, name);
        _stickyAddClassId = classId;
        setStatus(`Sticky class: ${name} — Shift+click to add, Shift+A to change`);
    } else if (_cellEditCtx.mode === 'sticky-pick') {
        // 클래스만 변경 (셀 추가 X) — Shift+A 진입한 popup.
        _stickyAddClassId = classId;
        setStatus(`Sticky class: ${name} — Shift+click 으로 추가`);
    }
    _closeCellEditPopup();
}

/**
 * Shift+A 단축키로 호출 — sticky 클래스만 변경 (셀 추가 X).
 * popup 은 _showCellAddPopup 와 동일한 클래스 리스트 UI 를 재사용하되,
 * mode='sticky-pick' 컨텍스트로 클릭 시 sticky 만 갱신.
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
    headerLabel.innerHTML = `<b>Pick Sticky Class</b>  <span style="opacity:0.6">(추가할 클래스 선택)</span>`;
    header.appendChild(headerLabel);
    popup.appendChild(header);

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
        text.textContent = (keyLabel ? `[${keyLabel}] ` : '') + name + (isCurrent ? '  ✓' : '');
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

// Shift+A — sticky 클래스 변경 popup. 입력 위젯 포커스 중이면 무시.
window.addEventListener('keydown', (e) => {
    if (e.key !== 'a' && e.key !== 'A') return;
    if (!e.shiftKey) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!_lastDetectionResult) return;
    if (viewer && viewer.drawMode) return;
    e.preventDefault();
    e.stopPropagation();
    // 마우스 마지막 위치 옆에 popup 띄움 — viewer 위에서 누르면 그 위치 근처에 뜸.
    _showStickyClassPickerPopup(_stickyHudLastMouse.x, _stickyHudLastMouse.y);
}, true);

viewer.onCellAddRequested = _showCellAddPopup;

function _showMultiCellEditPopup(listIndices, listCells, screenX, screenY) {
    _closeCellEditPopup();
    if (!_lastDetectionResult || !listIndices || listIndices.length === 0) return;

    const classNames = _lastDetectionResult.class_names || {};
    const classColors = _lastDetectionResult.class_colors || {};

    // 선택된 셀들의 클래스별 개수 집계
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
        font-family: sans-serif; font-size: 12px;
        user-select: none;
    `;

    // 헤더
    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:6px;margin-bottom:6px;';
    const headerLabel = document.createElement('span');
    headerLabel.innerHTML = `<b>${listIndices.length} cells selected</b>`;
    header.appendChild(headerLabel);
    popup.appendChild(header);

    // 클래스별 집계 표시
    const breakdown = document.createElement('div');
    breakdown.style.cssText = 'font-size:11px;color:#666;margin-bottom:6px;max-height:60px;overflow-y:auto;';
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

    // 모든 클래스 버튼
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

viewer.onCellEdited = () => {
    // 결과 리스트 카운트 + 스코어 갱신
    if (_lastDetectionResult) {
        _lastDetectionResult.cells = viewer.detectionCells;
        _lastDetectionResult.total_cells = viewer.detectionCells.length;
        buildResultList(_lastDetectionResult);
        // 스코어 카드 재계산 (Allred / HER2 / Quanti PD-L1)
        _updateResultCounts();
    }
    setStatus(`Cell edited — ${viewer.detectionCells.length} cells`);
};

// ── Cell edit Undo / Redo (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y) ──
window.addEventListener('keydown', (e) => {
    // 입력 위젯 포커스 중이면 무시
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    const key = e.key.toLowerCase();
    if (key === 'z' && !e.shiftKey && viewer.canUndoAnnotationEdit?.()) {
        _closeCellEditPopup();
        viewer.undoAnnotationEdit();
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
            setStatus(`Undo — ${viewer.detectionCells.length} cells`);
            e.preventDefault();
        }
    } else if ((key === 'z' && e.shiftKey) || key === 'y') {
        if (viewer.canRedoCellEdit && viewer.canRedoCellEdit()) {
            _closeCellEditPopup();
            viewer.redoCellEdit();
            setStatus(`Redo — ${viewer.detectionCells.length} cells`);
            e.preventDefault();
        }
    }
}, true);

// Clear All
$btnAnnClear?.addEventListener('click', () => {
    if (_blockViewerAction('Viewer 권한은 annotation 기능을 사용할 수 없습니다.')) return;
    viewer.clearAnnotations();
    renderAnnotationPanel();
    _setSlideListMemoIndicator();
    setStatus('Annotations cleared');
});

// ── Annotation Save/Load (download/upload) ──
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
    return viewer.annotations.map((ann, index) => ({
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
        _editSlideMemo();
        return;
    }
    if (e.key.toLowerCase() !== 's') return;
    e.preventDefault();
    if (_blockViewerAction('Viewer 권한은 annotation 기능을 사용할 수 없습니다.')) return;
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

    // File System Access API: 사용자가 저장 위치(폴더 + 파일명) 직접 선택
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
            // 권한 거부 등 → 다운로드 fallback
            console.warn('showSaveFilePicker failed, falling back to download', err);
        }
    }

    // Fallback: 일반 브라우저 다운로드
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
    if (_blockViewerAction('Viewer 권한은 annotation 기능을 사용할 수 없습니다.')) return;
    try {
        await _saveAnnotationsToServer();
    } catch (err) {
        alert(`Failed to save annotations: ${err.message}`);
    }
});
if (false) $btnAnnLoad?.addEventListener('click', () => {
    if (_blockViewerAction('Viewer 권한은 annotation 기능을 사용할 수 없습니다.')) return;
    _uploadAnnotations();
});

// ═══════════════════════════
// 슬라이드 정보 다이얼로그
// ═══════════════════════════
$btnInfo.addEventListener('click', () => {
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

// ═══════════════════════════
// AI 검출
// ═══════════════════════════

// 실행 중인 AI task 추적 — key: 버튼 고유 키 ('detect', 'VS IHC_membrane', 'Quanti PD-L1', 'ihc-HER2' 등)
//   value: { task_id, buttonEl }
// 같은 버튼 재클릭 시 cancelTask 호출.
const _runningAiTasks = {};

function _setButtonRunning(btnEl, bool_running) {
    if (!btnEl) return;
    if (bool_running) {
        btnEl.classList.add('ai-btn-running');
        btnEl.dataset.origLabel = btnEl.dataset.origLabel || btnEl.textContent;
        btnEl.textContent = '■ Stop';
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
    // task_id 가 아직 서버에서 돌아오지 않았는데 재클릭한 경우:
    // pending_cancel 플래그만 세팅 → start 핸들러가 task_id 를 받는 즉시 cancelTask 호출.
    // (null 을 URL 에 박아 쏘면 /task/null/cancel 로 405/404 나므로 금지)
    if (!entry.task_id) {
        entry.pending_cancel = true;
        setStatus('중지 예약 — task 시작 직후 취소합니다...');
        return true;
    }
    try {
        await api.cancelTask(entry.task_id);
        setStatus('중지 요청 전송 — 잠시 후 정리됩니다...');
    } catch (e) {
        console.warn('[cancel] failed', e);
    }
    return true;  // 호출자는 start 로직 건너뛰기
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
    setStatus('검출 시작...');

    // AI 시작 → 그리기 모드 해제
    viewer.setDrawMode(null);

    try {
        const tissueType = document.querySelector('input[name="tissue-type"]:checked')?.value || 'Stomach';

        // point 제외한 polygon/rectangle annotation → ROI로 전달
        const roiAnnotations = viewer.annotations.filter(a => a.visible && a.type !== 'point' && a.coordinates.length >= 3);
        const roiPolygons = roiAnnotations.length > 0 ? roiAnnotations.map(a => a.coordinates) : null;

        const { task_id } = await api.startDetection(currentSlideId, roiPolygons, tissueType);
        if (_runningAiTasks['detect']) {
            _runningAiTasks['detect'].task_id = task_id;
            if (_runningAiTasks['detect'].pending_cancel) {
                try { await api.cancelTask(task_id); } catch (e) { console.warn('[cancel] failed', e); }
            }
        }

        // 폴링
        while (true) {
            await sleep(1000);
            // 다른 코드가 _runningAiTasks 를 지웠으면 (예: 슬라이드 변경) 루프 탈출
            if (!_runningAiTasks['detect']) return;
            const st = await api.getTaskStatus(task_id);
            const msg = st.status_msg || `${st.progress}%`;
            setProgress(st.progress, msg);
            setStatus(msg);

            // 진행 단계에 따라 라벨 업데이트
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
                setStatus('Cell Detection 중지됨 — 부분 결과 정리 완료');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`검출 실패: ${err.message}`);
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

    // AI 완료 → 기존 annotation 제거 (ROI 저장 후)
    viewer.clearAnnotations();
    renderAnnotationPanel();

    // 내부 저장용으로 최신 결과 보존
    _lastDetectionResult = result;
    _lastDetectionTissue = tissueType;
    _lastDetectionModel = 'Quanti HE';
    _lastDetectionRoi = roiPolygons;

    // segmentation 데이터 저장 (Spatial Heatmap 시각화용)
    lastSegData = result.seg_data || null;

    // Quanti HE 은 기본 CLASS_COLORS 사용 (override 해제)
    viewer.classColorOverride = null;
    viewer.defaultConfidence = 0.1;  // 고정 (SaMD 재현성)

    // ROI 폴리곤 내부 셀만 필터링하여 표시
    viewer.setDetectionResults(result.cells, roiPolygons);

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

// ═══════════════════════════
// 결과 리스트 (기존 resultList 재현)
// ═══════════════════════════
const CLASS_COLORS = {
    0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
    4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
};

// ── 스코어 바 차트 유틸 ──
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

// 현재 confidence 임계값을 반영한 클래스별 카운트 계산
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

// "1,234 (45.6%)" — 클래스별 개수 + 전체 대비 비율. total 은 confidence 필터 통과한
// 모든 클래스 합. total=0 이면 비율 0%.
function _formatCountWithRatio(int_count, int_total) {
    const str_count = int_count.toLocaleString();
    if (!int_total) return `${str_count} (0%)`;
    return `${str_count} (${(int_count / int_total * 100).toFixed(1)}%)`;
}

// 결과 리스트의 카운트 라벨만 갱신 (confidence 슬라이더 변경 시 호출)
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

// Confidence 필터가 반영된 카운트로 CPS/TPS 재계산하여 스코어 카드 갱신
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

    // viewer.detectionCells 는 ROI 폴리곤 내부 셀만 남아 있지만 (setDetectionResults),
    // confidence 임계값 미만 셀도 그대로 보관한다 (슬라이더 조절을 허용하기 위해).
    // 렌더링/시각화/스코어 카드는 모두 _computeFilteredCounts (ROI + confidence) 를
    // 거치므로 패널 숫자도 같은 기준으로 맞춰야 일관성이 유지된다.
    let counts, total;
    if (viewer.detectionCells && viewer.detectionCells.length) {
        ({ counts, total } = _computeFilteredCounts(viewer.detectionCells));
    } else {
        // fallback — viewer 가 아직 초기화 전인 엣지 케이스 (저장본 직접 로드 등)
        counts = {};
        total = 0;
        for (const cell of (result.cells || [])) {
            counts[cell.class_id] = (counts[cell.class_id] || 0) + 1;
            total++;
        }
    }

    // 클래스별 체크박스 참조 저장
    const classCbs = {};
    const perClassCountEls = {};

    // 총 셀 수 (전체 토글 체크박스)
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
    // ROI 필터링 결과(total)와 일관성 — result.total_cells 는 전체 슬라이드 합이라 ROI 추론 시 어긋난다.
    totalCount.textContent = total.toLocaleString();

    totalItem.style.cursor = 'pointer';
    totalItem.addEventListener('click', (e) => {
        if (e.target === totalCb) return;
        totalCb.click();
    });

    totalItem.append(totalCb, totalName, totalCount);
    $resultList.appendChild(totalItem);

    // 클래스별 항목 (체크박스 + 색상 + 이름 + 카운트 + 개별 confidence 슬라이더)
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
            // 전체 체크박스 동기화
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
        // confidence 임계값은 SaMD 재현성을 위해 고정 — UI 조절 슬라이더 제거됨
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
    lastSegData = null;
    _lastDetectionResult = null;
    _lastDetectionTissue = null;
    // detection 결과가 사라지면 sticky 도 무효 — class_names 가 없어졌으니 의미 X.
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
    // 현재 클래스별 confidence 임계값을 통과한 셀만 시각화
    const filtered = viewer.detectionCells.filter(c => {
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

    // 모델 타입 / 클래스 메타
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

// Detection Result 저장 — 현재 로그인한 사용자 전용 편집본으로 DB 저장
// (원본 모델 추론 캐시는 건드리지 않음)
$btnSaveResults?.addEventListener('click', async () => {
    if (_blockViewerAction('Viewer 권한은 AI 결과 저장 기능을 사용할 수 없습니다.')) return;
    if (!currentSlideId || !_lastDetectionResult) {
        setStatus('No detection result to save');
        return;
    }
    const tissue = _lastDetectionTissue || 'Stomach';
    const aiMode = _lastDetectionModel || 'Quanti HE';
    try {
        $btnSaveResults.disabled = true;
        // 뷰어에서 편집된 셀을 결과 객체에 반영 (class_id 변경 등)
        if (viewer?.detectionCells) {
            _lastDetectionResult.cells = viewer.detectionCells;
            _lastDetectionResult.total_cells = viewer.detectionCells.length;
        }
        // confidence 임계값은 SaMD 재현성을 위해 고정값만 사용.
        // 과거 저장본과의 호환을 위해 레거시 필드는 저장하지 않음(있어도 로드 시 무시).
        delete _lastDetectionResult.class_confidence;
        delete _lastDetectionResult.default_confidence;
        const r = await api.saveDetectionResult(
            currentSlideId, tissue, _lastDetectionResult, aiMode,
        );
        console.log('[save-result]', r);
        setStatus(`Saved (${aiMode}/${tissue}): ${r.total_cells} cells → ${r.user_name || 'me'}`);
    } catch (err) {
        console.error('[save-result] failed', err);
        setStatus(`Save failed: ${err.message}`);
    } finally {
        $btnSaveResults.disabled = false;
        if (_isViewerRole()) _applyViewerRoleRestrictions();
    }
});

// ═══════════════════════════
// Detection Result 로드 — 다른 사용자(또는 본인)의 저장본 선택
// ═══════════════════════════
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
    if (_blockViewerAction('Viewer 권한은 AI 결과 로드 기능을 사용할 수 없습니다.')) return;
    if (!currentSlideId) {
        setStatus('슬라이드를 먼저 열어주세요');
        return;
    }
    if (!_lastDetectionModel || !_lastDetectionTissue) {
        setStatus('먼저 AI 모델을 실행해주세요 (어떤 모드를 로드할지 지정해야 합니다)');
        return;
    }
    const aiMode = _lastDetectionModel;
    const variant = _lastDetectionTissue;
    $loadUserEditMeta.textContent = `Mode: ${aiMode}  /  Variant: ${variant}`;
    $loadUserEditList.innerHTML = '<div style="padding:12px; color:#888;">Loading…</div>';
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

    // 편의 항목: "원본 모델 추론 결과" (기존 AI 버튼 재실행과 동일)
    const originalRow = document.createElement('div');
    originalRow.className = 'result-row';
    originalRow.style.cssText = 'padding:10px 12px; cursor:pointer; border-bottom:1px solid #333;';
    originalRow.innerHTML = `
        <div style="font-weight:600;">Original model inference</div>
        <div style="font-size:11px; color:#888; margin-top:2px;">
            원본 모델 추론 재실행 (${aiMode} / ${variant})
        </div>`;
    originalRow.addEventListener('click', async () => {
        $loadUserEditDialog.close();
        _rerunOriginalInference(aiMode, variant);
    });
    $loadUserEditList.appendChild(originalRow);

    if (users.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding:12px; color:#888; font-size:12px;';
        empty.textContent = '저장된 사용자 편집본이 없습니다.';
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
                setStatus(`Loading ${displayName}'s analysis…`);
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
            del.textContent = '🗑';
            del.addEventListener('click', async (ev) => {
                ev.stopPropagation();
                if (!confirm(`Delete your saved ${aiMode} / ${variant} analysis for this slide?`)) return;
                try {
                    del.disabled = true;
                    await api.deleteMyUserAiEdit(currentSlideId, aiMode, variant);
                    setStatus('Deleted your saved analysis');
                    // 모달 다시 불러오기
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
    // 레거시 저장본에 class_confidence / default_confidence 필드가 있어도 무시.
    // 모든 결과는 현재 모델의 고정 임계값으로 표시된다 (SaMD 재현성).
}

function _rerunOriginalInference(aiMode, variant) {
    // 기존 AI 버튼과 동일한 경로로 재실행 — 서버 디스크 캐시가 있으면 즉시 반환됨
    if (aiMode === 'Quanti HE') {
        // startDetection 은 버튼 핸들러 내부에 있으므로 버튼 클릭 트리거
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

// ═══════════════════════════
// 유틸리티
// ═══════════════════════════
function setProgress(pct, statusMsg = '') {
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

// ═══════════════════════════
// 좌측 패널 리사이즈
// ═══════════════════════════
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

// Ctrl + 휠로 슬라이드 리스트 썸네일 크기 조정 (리스트/그리드 각각)
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

// ═══════════════════════════
// 좌측 슬라이드 리스트 + 폴더 탐색
// ═══════════════════════════
let currentBrowsePath = '';  // uploads/ 기준 상대경로
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
        classBtn.textContent = 'Classes';
        classBtn.disabled = !_canManageAnnotationClasses();
        classBtn.title = _canManageAnnotationClasses() ? 'Manage classes' : 'Doctor/Admin only';
        actionEl.append(openBtn, classBtn);
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
        $slideList.innerHTML = '';
        _appendAnnotationSlideListHeader();
        _syncProjectSelect();

        // 빈 폴더
        if (data.folders.length === 0 && data.slides.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'slide-list-empty';
            empty.textContent = 'Empty';
            $slideList.appendChild(empty);
        }

        // 폴더 항목
        for (const f of data.folders) {
            const folderPath = currentBrowsePath ? `${currentBrowsePath}/${f.name}` : f.name;
            const item = document.createElement('div');
            item.className = 'slide-list-item folder-item';
            item.dataset.folderPath = folderPath;

            const icon = document.createElement('span');
            icon.className = 'folder-icon';
            icon.textContent = '📁';

            const name = document.createElement('div');
            name.className = 'slide-list-name';
            name.textContent = f.name;

            item.append(icon, name);

            // 더블클릭 → 폴더 진입
            item.addEventListener('click', () => navigateToFolder(folderPath));
            // 우클릭 → 컨텍스트 메뉴
            item.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                showFolderContextMenu(e, folderPath, f.name);
            });
            // 드래그 대상 (파일을 폴더에 드롭) — OS 파일 + 내부 이동 모두 지원
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

        // 슬라이드 항목
        for (const s of data.slides) {
            const item = document.createElement('div');
            item.className = 'slide-list-item';
            const strRawSlideStatus = s.annotation_status || s.status || 'annotation';
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
            // closure 캡처 — currentBrowsePath 가 나중에 바뀌어도 이 썸네일은 처음 경로 유지.
            const str_thumb_filename = s.filename;
            const str_thumb_path = currentBrowsePath;
            thumb.src = api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 96);
            // 401 (만료된 mt) 시 새 티켓으로 1회 재시도 후 그래도 실패하면 숨김.
            api.attachMediaImageRetry(thumb,
                () => api.thumbnailUrlByName(str_thumb_filename, str_thumb_path, 96),
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

            // Annotation workflow columns
            _renderAnnotationWorkflowCells(item, strRawSlideStatus);

            // 우클릭: 컨텍스트 메뉴 (상태 설정 / 삭제)
            item.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // 현재 아이템이 선택되어 있지 않다면 단독 선택으로 전환
                if (!item.classList.contains('selected')) {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                }
                showSlideContextMenu(e);
            });

            // 클릭: Ctrl/Shift 다중 선택, 일반 클릭은 단일 선택+열기
            item.addEventListener('click', (e) => {
                if (e.ctrlKey || e.metaKey) {
                    item.classList.toggle('selected');
                } else if (e.shiftKey) {
                    // Shift: 범위 선택
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
                    // 단일 클릭 → 선택 초기화 + 열기
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                    openSavedSlide(s.filename, item);
                }
            });

            // 드래그: 선택된 파일 전부 포함
            item.addEventListener('dragstart', (e) => {
                // 드래그 시작한 아이템이 선택 안 되어 있으면 단독 선택
                if (!item.classList.contains('selected')) {
                    $slideList.querySelectorAll('.slide-list-item.selected').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                }
                const selectedFiles = [...$slideList.querySelectorAll('.slide-list-item.selected')]
                    .map(el => el.dataset.filename)
                    .filter(Boolean);
                e.dataTransfer.setData('text/filenames', JSON.stringify(selectedFiles));
                e.dataTransfer.setData('text/filename', selectedFiles[0]); // 호환
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
        console.error('슬라이드 목록 로드 실패:', err);
    }
}

// ── AI 진행 중 배지 (auto/manual 공통) ──
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
    // 다중 파일 이동
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
        setStatus(`${filenames.length}개 파일 이동 완료`);
    } catch (err) { setStatus(`이동 실패: ${err.message}`); }
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

// 좌측 슬라이드 리스트 빈 영역에 OS 파일 드롭 → 현재 폴더로 업로드
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
            sep.textContent = '›';
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
    setStatus('열는 중...');
    try {
        const info = await api.openSlide(filename, currentBrowsePath);
        if (info.exists) {
            $slideList.querySelectorAll('.slide-list-item').forEach(el => el.classList.remove('active'));
            if (itemEl) itemEl.classList.add('active');
            onSlideLoaded(info.slide_id, info, filename);
        }
    } catch (err) {
        setStatus(`열기 실패: ${err.message}`);
    }
}

// ── 폴더 생성 ──
$('#btn-new-folder').addEventListener('click', async () => {
    if (!_getCurrentProjectName()) {
        alert('Select a project before creating folders.');
        _showProjectGate(_projectListCache);
        return;
    }
    const name = prompt('새 폴더 이름:');
    if (!name || !name.trim()) return;
    try {
        await api.createFolder(currentBrowsePath, name.trim());
        loadSlideList();
    } catch (err) {
        alert(`폴더 생성 실패: ${err.message}`);
    }
});

// ── 폴더 우클릭 컨텍스트 메뉴 ──
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
        const newName = prompt('새 이름:', folderName);
        if (!newName || !newName.trim() || newName.trim() === folderName) return;
        try {
            await api.renameFolder(folderPath, newName.trim());
            loadSlideList();
        } catch (err) { alert(`이름 변경 실패: ${err.message}`); }
    });

    const deleteBtn = document.createElement('div');
    deleteBtn.className = 'ctx-menu-item danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', async () => {
        removeCtxMenu();
        if (!confirm(`"${folderName}" 폴더를 삭제하시겠습니까?`)) return;
        try {
            await api.deleteFolder(folderPath);
            loadSlideList();
        } catch (err) { alert(`삭제 실패: ${err.message}`); }
    });

    menu.append(renameBtn, deleteBtn);
    document.body.appendChild(menu);
    _ctxMenu = menu;
}

// ── 슬라이드 우클릭 컨텍스트 메뉴 ──
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
    if (!confirm(`Annotation Status를 "${strLabel}" 단계로 변경할까요?`)) {
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

$annotationStatusWorkflow?.querySelectorAll('[data-annotation-status]').forEach((btn) => {
    btn.addEventListener('click', () => {
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

    // 헤더 (선택 개수)
    const header = document.createElement('div');
    header.className = 'ctx-menu-header';
    header.textContent = list_filenames.length === 1
        ? list_filenames[0]
        : `${list_filenames.length} slides selected`;
    menu.appendChild(header);

    // Set Status 하위 항목
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

// ── 슬라이드 리스트 마키(러버밴드) 드래그 선택 ──
(function _initMarqueeSelection() {
    let bool_active = false;
    let int_startX = 0;
    let int_startY = 0;
    let el_rect = null;
    let list_baseline = []; // Ctrl/Shift 시 기존 선택 유지

    $slideList.addEventListener('mousedown', (e) => {
        // 왼쪽 버튼만, 스크롤바/아이템 위 아님
        if (e.button !== 0) return;
        // 슬라이드 아이템/폴더 아이템 내부 클릭은 무시 (기존 동작 유지)
        if (e.target.closest('.slide-list-item')) return;
        // 썸네일 drag 중에는 브라우저 기본 drag 가 걸릴 수 있어 여기서만 처리
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

        // 교차 판정: 각 슬라이드 아이템 rect 와 교차하면 selected
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

// 슬라이드 리스트 빈 영역 우클릭은 컨텍스트 메뉴 숨김 (기본 방지는 불필요)
$slideList.addEventListener('contextmenu', (e) => {
    if (!e.target.closest('.slide-list-item')) {
        // 선택된 슬라이드가 있으면 메뉴 표시
        const list_sel = $slideList.querySelectorAll('.slide-list-item.selected:not(.folder-item)');
        if (list_sel.length > 0) {
            e.preventDefault();
            showSlideContextMenu(e);
        }
    }
});

// ── 폴더 AI 자동 분석 설정 다이얼로그 ──
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
    // 기존 설정 로드
    let cfg = { enabled: false, tasks: [] };
    try { cfg = await api.getFolderAiConfig(folderPath); }
    catch (err) { console.warn('folder config 로드 실패:', err); }

    // 일반 모델: model::variant key 로 선택 여부 판단
    // VS IHC: variant 별 선택된 mpp set 을 따로 관리
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

    // 백드롭 + 카드
    const backdrop = document.createElement('div');
    backdrop.className = 'ai-cfg-backdrop';
    backdrop.innerHTML = `
        <div class="ai-cfg-card">
            <div class="ai-cfg-header">
                <span>AI 자동 분석 설정 — ${folderName}</span>
                <button class="ai-cfg-close" type="button">&times;</button>
            </div>
            <div class="ai-cfg-body">
                <label class="ai-cfg-enable">
                    <input type="checkbox" id="ai-cfg-enabled"${cfg.enabled ? ' checked' : ''}>
                    <span>이 폴더에 자동 분석 활성화</span>
                </label>
                <div class="ai-cfg-hint">
                    10분간 AI 사용이 없고 업로드가 없을 때 1분마다 스캔해서
                    아래 선택한 분석이 없는 슬라이드를 자동 추론합니다.
                </div>
                <div class="ai-cfg-list" id="ai-cfg-list"></div>
            </div>
            <div class="ai-cfg-footer">
                <button type="button" class="ai-cfg-btn ai-cfg-cancel">취소</button>
                <button type="button" class="ai-cfg-btn ai-cfg-save primary">저장</button>
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
            // VS IHC: 상위 체크박스 = 선택된 mpp 가 하나라도 있으면 checked
            const set_current = dict_vs_mpps[opt.variant] || new Set();
            const bool_parent_checked = set_current.size > 0;
            wrap.innerHTML = `
                <label class="ai-cfg-row">
                    <input type="checkbox" class="ai-cfg-parent"${bool_parent_checked ? ' checked' : ''}>
                    <span>${opt.label}</span>
                </label>
                <div class="ai-cfg-sub"${bool_parent_checked ? '' : ' hidden'}>
                    <div class="ai-cfg-sub-title">배율 선택:</div>
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
                    // 아무것도 체크 안 되어 있으면 기본 2.0 체크
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
            setStatus(`AI 자동 분석 설정 저장: ${tasks.length}개 작업`);
            close();
        } catch (err) {
            alert(`저장 실패: ${err.message}`);
        }
    });
}

// ── 뷰 토글 (리스트 / 그리드) ──
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

// ═══════════════════════════
// VS IHC (Virtual Staining)
// ═══════════════════════════
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
    setStatus('Virtual staining 시작...');

    viewer.setDrawMode(null);

    // ROI: polygon/rectangle annotation을 폴리곤으로 전달
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
        // 결과 로딩 시 같은 mpp로 PNG 요청
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
                setStatus('Virtual staining 중지됨 — 부분 결과 정리 완료');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`Virtual staining 실패: ${err.message}`);
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
        roi_polygons: result.roi_polygons || null,  // 표시 클립용 (level-0 좌표)
    });
    _setVsToggleState(true, false);
    _setVsSplitState(false, false);  // 분할 모드는 사용자가 켜야 함

    // AI 완료: ROI annotation 제거 (desktop 동작과 일치)
    viewer.clearAnnotations();
    renderAnnotationPanel();

    const tc = result.tissue_count || 0;
    const tot = result.total_patches || 0;
    setProgress(100);
    $progressLabel.textContent = result.cached
        ? 'Virtual staining loaded (cached)'
        : 'Virtual staining complete';
    setStatus(`Virtual staining complete — ${tc}/${tot} tissue patches`);
}

// VS IHC target mpp slider — index → mpp value
const VS_MPP_VALUES = [4.0, 2.0, 1.0, 0.5];
const VS_MPP_LABELS = [
    '4.0 µm/px (x2.5)',
    '★ 2.0 µm/px (x5)',
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

// ═══════════════════════════
// Quanti PD-L1 (PD-L1) — CPS / TPS
// ═══════════════════════════
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
    setStatus('Quanti PD-L1 시작...');

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
                setStatus('Quanti PD-L1 중지됨 — 부분 결과 정리 완료');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`Quanti PD-L1 실패: ${err.message}`);
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

    // Quanti PD-L1 전용 클래스 색상 override (Stomach CPS: 녹/적 계열)
    const colorMap = {};
    if (result.class_colors) {
        for (const [k, v] of Object.entries(result.class_colors)) {
            colorMap[parseInt(k)] = v;
        }
    }
    viewer.classColorOverride = Object.keys(colorMap).length > 0 ? colorMap : null;
    viewer.defaultConfidence = 0.1;  // PD-L1 고정 (SaMD 재현성)

    viewer.setDetectionResults(result.cells, roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    // Score 카드는 polygon-ROI + confidence 필터링된 viewer.detectionCells 로만 그린다.
    // backend 의 result.pd_score 는 bbox-ROI 기반이라 영역 그렸을 때 어긋남 — 절대 사용 X.
    // 카드 visibility 만 켜고 내용은 buildResultList → _updateResultCounts 로 채운다.
    if ($pdScoreResult) $pdScoreResult.hidden = false;

    // status bar 텍스트도 polygon-ROI 카운트로 계산
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

    // onCellEdited 와 동일한 패턴 — _lastDetectionResult.cells 를 polygon-필터링된 셀로
    // 정렬해 두면 buildResultList 가 어떤 경로로 result.cells 를 쓰더라도 안전.
    _lastDetectionResult.cells = viewer.detectionCells;
    _lastDetectionResult.total_cells = viewer.detectionCells.length;

    buildResultList(_lastDetectionResult);
    _updateResultCounts();   // _updatePdScoreDisplay 가 polygon-ROI 기반으로 카드 채움
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
    setStatus(`${markerLabel} 시작...`);

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
                setStatus(`${markerLabel} 중지됨 — 부분 결과 정리 완료`);
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`${markerLabel} 실패: ${err.message}`);
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
    viewer.defaultConfidence = (marker === 'ER_PR' || marker === 'KI_67') ? 0.3 : 0.5;  // 고정 (SaMD 재현성)

    viewer.setDetectionResults(result.cells, roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    // Score 카드는 polygon-ROI + confidence 필터된 viewer.detectionCells 기반으로만 그린다.
    // backend 의 result.{her2,allred,ki67}_score 는 bbox-ROI 기반이라 영역 그렸을 때
    // 패널/시각화와 어긋남 — 절대 사용 X. visibility 만 켜고 _updateResultCounts() 가
    // 폴리곤 카운트로 카드 내용 (점수/막대/범례) 을 채우도록 위임.
    if ($ihcScoreResult) {
        $ihcScoreResult.hidden = false;
        // 마커별 라벨 — _updateXxxScoreDisplay 가 다시 덮어쓰기는 하지만 첫 프레임 빈 라벨 방지.
        if (result.her2_score) {
            $ihcScoreLabel.textContent = 'HER2';
        } else if (result.allred_score) {
            $ihcScoreLabel.textContent = `${markerLabel} (Allred)`;
        } else if (result.ki67_score) {
            $ihcScoreLabel.textContent = 'KI-67';
        }
    }

    // status bar 텍스트도 polygon-ROI 카운트로 재계산 (backend 점수 X).
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
        setStatus(`${markerLabel} Allred: ${ts} (PS ${int_ps} + IS ${int_is}) — ${interp} | ${displayCount.toLocaleString()} cells`);
    } else if (result.ki67_score) {
        const pos = n1 + n2 + n3;
        const tot = n0 + pos;
        const ki67Index = tot === 0 ? 0 : pos / tot * 100;
        const interp = ki67Index >= 14 ? 'High' : 'Low';
        setStatus(`KI-67 Index: ${ki67Index.toFixed(1)}% — ${interp} | ${displayCount.toLocaleString()} cells`);
    }

    // onCellEdited 와 동일한 패턴으로 result.cells 를 polygon-필터링된 셀에 맞춤.
    _lastDetectionResult.cells = viewer.detectionCells;
    _lastDetectionResult.total_cells = viewer.detectionCells.length;

    buildResultList(_lastDetectionResult);
    _updateResultCounts();   // _updateXxxScoreDisplay 가 polygon-ROI 기반으로 카드 채움
    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
    if (_isViewerRole()) _applyViewerRoleRestrictions();
}

// ─── VS toggle 헬퍼 ───
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
        ? 'Split View: ON  (← IHC | Virtual H&E →)'
        : 'Split View (IHC | Virtual H&E)';
}

$btnVsToggle?.addEventListener('click', () => {
    if (_blockViewerAction()) return;
    if ($btnVsToggle.disabled) return;
    const next = $btnVsToggle.getAttribute('aria-pressed') !== 'true';
    _setVsToggleState(next, false);
    viewer.setVirtualStainVisible(next);
    // overlay를 끄면 split도 의미가 없으므로 끔
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
    // split을 켜면 overlay도 강제로 ON
    if (next) {
        _setVsToggleState(true, false);
        viewer.setVirtualStainVisible(true);
    }
    viewer.setVirtualStainSplitMode(next);
});

// 페이지 로드 시 인증 확인 후 슬라이드 목록 가져오기
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
            $projectUserRole.textContent = dict_me.str_role || 'viewer';
        }
        if (dict_me.str_role === 'admin') {
            const $linkAdmin = document.getElementById('link-admin');
            if ($linkAdmin) $linkAdmin.hidden = false;
            if ($projectLinkAdmin) $projectLinkAdmin.hidden = false;
        }
        window.MediautoHeader?.render({
            active: ANNOTATION_HEADER_ACTIVE,
            user: dict_me,
            showAdmin: dict_me.str_role === 'admin',
            logout: () => {
                _stopAiActivePolling();
                api.logout();
            },
        });
        window.__currentUserRole = dict_me.str_role || 'viewer';
        window.__currentUserId = String(dict_me._id || '');
        _loadAnnotationDisplayStyleFromPreferences(dict_me.dict_preferences || {});
        localStorage.setItem('user', JSON.stringify(dict_me));
        if (window.__currentUserRole === 'viewer') {
            _applyViewerRoleRestrictions();
        }
    } catch (_) {
        // 인증 실패 — api.js 가 리다이렉트 처리. 슬라이드/폴링 시작 생략.
        return;
    }
    // URL 파라미터로 슬라이드 자동 열기 (?slide=filename&path=rel_path)
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
        // 슬라이드 목록 로드 후 자동 열기
        openSavedSlide(_paramSlide, null);
        // URL 파라미터 제거 (뒤로가기 시 재로드 방지)
        history.replaceState(null, '', ANNOTATION_PAGE_ROUTE);
    }
})();
