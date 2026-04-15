/**
 * MeDICus Studio SaaS — 메인 앱
 * 기존 PyQt5 viewer.py의 UI 로직을 JS로 포팅
 */

import { api } from './api.js';
import { TileViewer } from './tile-viewer.js';
import { showVisualization } from './visualization.js';

// ── DOM 요소 ──
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

// 사용자 메뉴
const $userName = $('#user-name');
const $btnLogout = $('#btn-logout');

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
// 현재 뷰어에 올라간 결과의 AI 모드 ("HE-Fit" | "PD-Score" | "Precise-IHC")
let _lastDetectionModel = null;
// 로드된 결과를 onXxxComplete 로 재투입할 때 필요한 ROI (없으면 null)
let _lastDetectionRoi = null;
const $btnDrawPolygon = $('#btn-draw-polygon');
const $btnDrawRect = $('#btn-draw-rect');
const $btnDrawPoint = $('#btn-draw-point');

// VS-IHC
const $btnVsMembrane = $('#btn-vs-membrane');
const $btnVsNucleus = $('#btn-vs-nucleus');
const $btnPdScore = $('#btn-pd-score');
const $pdScoreResult = $('#pd-score-result');
const $pdScoreLabel = $('#pd-score-label');
const $pdScoreValue = $('#pd-score-value');
const $pdScoreDetail = $('#pd-score-detail');
const $btnIhcHer2 = $('#btn-ihc-her2');
const $btnIhcErPr = $('#btn-ihc-erpr');
const $ihcScoreResult = $('#ihc-score-result');
const $ihcScoreLabel = $('#ihc-score-label');
const $ihcScoreValue = $('#ihc-score-value');
const $ihcScoreDetail = $('#ihc-score-detail');
const $btnVsToggle = $('#btn-vs-toggle');
const $btnVsSplit = $('#btn-vs-split');
let _vsRunning = false;
let _vsLastTargetMpp = 2.0;

const $slideList = $('#slide-list');

// ── 상태 ──
let currentSlideId = null;
let currentSlideInfo = null;
let minimapImage = null;
let lastSegData = null;  // segmentation overlay data from epithelial classification

// ── 뷰어 초기화 ──
const viewer = new TileViewer($canvas, $overlay);

viewer.onZoomChange = (zoom, mag, mpp) => {
    $zoomInfo.textContent = `${mag.toFixed(1)}x  |  MPP ${mpp.toFixed(3)} μm/px`;
};
viewer.onViewChange = () => updateMinimap();

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
        title: 'HE-Fit — H&E Cell Detection',
        body: 'H&E 염색 슬라이드에서 개별 세포를 검출하고 8가지 클래스로 분류합니다 (Neutrophil, Epithelial, Lymphocyte, Plasma, Eosinophil, Connective tissue, Tumor Epithelial, Benign Epithelial). Tumor Proportion (Tumor/(Tumor+Benign)) 을 자동 계산합니다. 조직 타입 (Breast/Stomach/Other) 에 따라 전용 가중치를 사용합니다.',
    },
    'vs-tab': {
        title: 'VS-IHC — Virtual Staining',
        body: 'IHC 슬라이드를 입력으로 가상의 H&E 이미지를 생성합니다 (Membrane/Nucleus 모델). Target Resolution (µm/px) 가 낮을수록 고배율 상세 이미지이지만 연산 비용이 큽니다 (기본 2.0 µm/px ≈ x5). 결과는 뷰어 오버레이 및 Split view 로 원본과 비교할 수 있습니다.',
    },
    'pd-tab': {
        title: 'PD-Score — PD-L1 Scoring',
        body: 'PD-L1 IHC 슬라이드에서 세포를 검출해 PD-L1 점수를 계산합니다. Stomach: CPS = (Positive Tumor + Positive Immune) / Viable Tumor × 100. Lung: TPS = Positive Tumor / (Pos + Neg Tumor) × 100. 기본 confidence threshold 0.1 이상의 셀만 점수에 반영됩니다.',
    },
    'ihc-tab': {
        title: 'Precise-IHC — HER2 / ER / PR',
        body: 'Precise-IHC 모델은 IHC 슬라이드 상에서 염색 강도 (0+/1+/2+/3+) 로 세포를 분류합니다. HER2 는 Dominant intensity 와 weighted mean (∑(i·nᵢ)/∑nᵢ) 으로, ER/PR 은 Allred Score (Proportion 0–5 + Intensity 0–3 = Total 0–8) 로 판독합니다. KI-67 은 준비 중입니다.',
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

// ═══════════════════════════
// 파일 열기 + 업로드
// ═══════════════════════════
$btnOpen.addEventListener('click', () => $fileInput.click());
$fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) uploadFiles(e.target.files, currentBrowsePath);
    e.target.value = '';  // 같은 파일 재선택 가능하도록
});

const SLIDE_EXT_PATTERN = /\.(svs|ndpi|tif|tiff|mrxs|vms|vmu|scn)$/i;

async function uploadFiles(fileList, targetPath = currentBrowsePath) {
    const files = [...fileList].filter(f => SLIDE_EXT_PATTERN.test(f.name));
    if (!files.length) {
        setStatus('지원하는 슬라이드 파일이 없습니다');
        return;
    }

    const total = files.length;
    let firstOpened = false;

    for (let idx = 0; idx < total; idx++) {
        const file = files[idx];
        const prefix = total > 1 ? `[${idx + 1}/${total}] ` : '';
        try {
            const info = await uploadOneFile(file, targetPath, prefix);
            // 첫 파일만 자동으로 열기 (현재 폴더에 업로드된 경우)
            if (!firstOpened && info && targetPath === currentBrowsePath) {
                onSlideLoaded(info.slide_id, info, file.name);
                firstOpened = true;
            }
        } catch (err) {
            setStatus(`${prefix}${file.name} 실패: ${err.message}`);
        }
    }

    loadSlideList();
    if (total > 1) setStatus(`${total}개 파일 업로드 완료`);
    setProgress(0);
}

async function uploadOneFile(file, targetPath, prefix = '') {
    $slideName.textContent = file.name;
    setStatus(`${prefix}확인 중...`);

    // 1) 대상 폴더에서 이미 있는지 확인
    const check = await api.openSlide(file.name, targetPath);
    if (check.exists) return check;

    // 2) 없으면 대상 폴더에 업로드
    const CHUNK_SIZE = 5 * 1024 * 1024;
    setStatus(`${prefix}업로드 중...`);
    setProgress(0);

    const { upload_id } = await api.uploadStart(file.name);
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_SIZE;
        const blob = file.slice(start, Math.min(start + CHUNK_SIZE, file.size));
        await api.uploadChunk(upload_id, i, blob);
        setProgress(Math.round(((i + 1) / totalChunks) * 90), `${prefix}Uploading... ${i + 1}/${totalChunks} chunks`);
    }

    setStatus(`${prefix}슬라이드 등록 중...`);
    setProgress(95);
    const info = await api.uploadComplete(upload_id, file.name, totalChunks, targetPath);
    setProgress(100);
    return info;
}

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

    if (meta) {
        $slideScanner.innerHTML = `
            <span class="scanner-logo" title="${meta.label}">${meta.svg}</span>
            ${str_info ? `<span class="scanner-info">${str_info}</span>` : ''}
        `;
        $slideScanner.style.borderLeftColor = meta.color;
    } else {
        // 알려지지 않은 vendor: 원본 문자열을 그대로 표시
        $slideScanner.innerHTML = `
            <span class="scanner-logo scanner-logo-text">${slideInfo.vendor}</span>
            ${str_info ? `<span class="scanner-info">${str_info}</span>` : ''}
        `;
        $slideScanner.style.borderLeftColor = '#6c5ce7';
    }
    $slideScanner.hidden = false;
}

function onSlideLoaded(slideId, slideInfo, filename) {
    currentSlideId = slideId;
    currentSlideInfo = slideInfo;

    $slideName.textContent = filename;
    _updateScannerBadge(slideInfo);
    setStatus(`Loaded: ${slideInfo.dimensions[0]}x${slideInfo.dimensions[1]} (${slideInfo.level_count} levels)`);

    // 버튼 활성화
    $btnDetect.disabled = false;
    $btnVsMembrane.disabled = false;
    $btnVsNucleus.disabled = false;
    if ($btnPdScore) $btnPdScore.disabled = false;
    if ($btnIhcHer2) $btnIhcHer2.disabled = false;
    // ER/PR 은 임시 비활성화 — 준비되면 다시 활성화
    // if ($btnIhcErPr) $btnIhcErPr.disabled = false;
    $btnInfo.disabled = false;
    document.querySelectorAll('.toggle-btn').forEach(b => b.disabled = false);
    // tissue-type 라디오도 기본 활성 — 이후 폴더 제한이 있으면 덮어씀
    document.querySelectorAll('input[name="tissue-type"], input[name="pd-tissue-type"]').forEach(el => {
        el.disabled = false;
    });

    // 폴더별 AI 자동 분석 설정이 있으면 해당 task 만 활성화, 나머지는 disabled.
    _applyFolderAiRestrictions(currentBrowsePath);

    // Viewer 역할은 AI / annotation 기능 전면 비활성. 폴더 제한보다 우선.
    if (window.__currentUserRole === 'viewer') {
        _applyViewerRoleRestrictions();
    }

    // 뷰어 로드 (타일은 요청 시 즉석 생성 + 백그라운드 프리제네레이션)
    viewer.loadSlide(slideId, slideInfo);

    if ($mousePosOverlay) $mousePosOverlay.hidden = false;

    // 미니맵
    loadMinimap(slideId);

    // 결과 초기화
    clearResults();

    // VS-IHC 오버레이 초기화
    viewer.clearVirtualStainOverlay();
    _setVsToggleState(false, true);
    _setVsSplitState(false, true);

    // annotation은 사용자가 Load 버튼으로 파일에서 불러옴 (서버 자동 로드 X)

    setProgress(0);
}

// ═══════════════════════════
// 폴더별 AI 자동 분석 제한
// ──
// 폴더에 자동 분석 설정이 저장돼 있으면 (bool_enabled=true AND tasks 존재),
// 해당 task(model+variant) 에 속하지 않는 AI 버튼/라디오를 모두 disabled 로 만든다.
// 설정이 없거나 enabled=false 면 아무것도 제한하지 않는다 (기본 모두 활성).
// ═══════════════════════════

async function _applyFolderAiRestrictions(strFolderPath) {
    let cfg = null;
    try {
        cfg = await api.getFolderAiConfig(strFolderPath || '');
    } catch (err) {
        console.warn('[folder-ai-restrict] load 실패:', err);
        return;
    }
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

    // HE-Fit
    const bool_hnf_any = _restrictRadios('tissue-type', 'HE-Fit');
    $btnDetect.disabled = !bool_hnf_any;

    // PD-Score
    const bool_pd_any = _restrictRadios('pd-tissue-type', 'PD-Score');
    if ($btnPdScore) $btnPdScore.disabled = !bool_pd_any;

    // Precise-IHC — 마커별 버튼 단위
    if ($btnIhcHer2) $btnIhcHer2.disabled = !set_allowed.has('Precise-IHC::HER2');
    // ER/PR / KI-67 은 원래 disabled — 건드리지 않는다

    // VS-IHC — variant(ihc_membrane / ihc_nucleus) 단위. target_mpp 는 제한 안 함.
    $btnVsMembrane.disabled = !set_allowed.has('VS-IHC::ihc_membrane');
    $btnVsNucleus.disabled = !set_allowed.has('VS-IHC::ihc_nucleus');
}

// ═══════════════════════════
// Viewer 역할 제한 — AI 기능 / annotation 전면 비활성
// ═══════════════════════════
function _applyViewerRoleRestrictions() {
    document.body.classList.add('role-viewer');

    // Annotation 그리기 도구 (상단 툴바)
    const list_draw_btns = ['btn-draw-polygon', 'btn-draw-rect', 'btn-draw-point'];
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
        'btn-vs-membrane', 'btn-vs-nucleus',
    ];
    list_ai_btn_ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = true;
    });

    // AI 입력 (tissue-type radio 등) 비활성
    document.querySelectorAll(
        'input[name="tissue-type"], input[name="pd-tissue-type"]'
    ).forEach(el => { el.disabled = true; });

    // Annotation 패널의 저장/불러오기/초기화 버튼
    ['btn-ann-clear', 'btn-ann-save', 'btn-ann-load'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = true;
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
        updateMinimap();
    };
    img.src = api.thumbnailUrl(slideId, 200);
}

function updateMinimap() {
    if (!minimapImage || !currentSlideInfo) return;
    const vr = viewer.getViewRect();
    if (!vr) return;
    const [imgW, imgH] = currentSlideInfo.dimensions;
    const sx = $minimapCanvas.width / imgW;
    const sy = $minimapCanvas.height / imgH;
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
        ((e.clientX - rect.left) / $minimapCanvas.width) * imgW,
        ((e.clientY - rect.top) / $minimapCanvas.height) * imgH
    );
});

// ═══════════════════════════
// 줌 컨트롤
// ═══════════════════════════
$btnZoomIn.addEventListener('click', () => viewer.zoomIn());
$btnZoomOut.addEventListener('click', () => viewer.zoomOut());
$btnFit.addEventListener('click', () => viewer.fitToWindow());

// ═══════════════════════════
// Annotation 그리기 도구
// ═══════════════════════════
const drawButtons = { polygon: $btnDrawPolygon, rectangle: $btnDrawRect, point: $btnDrawPoint };

function setDrawMode(mode) {
    // 같은 버튼 다시 클릭 → 해제
    const newMode = viewer.drawMode === mode ? null : mode;
    viewer.setDrawMode(newMode);
    Object.values(drawButtons).forEach(b => b.classList.remove('active'));
    if (newMode && drawButtons[newMode]) drawButtons[newMode].classList.add('active');
}

$btnDrawPolygon.addEventListener('click', () => setDrawMode('polygon'));
$btnDrawRect.addEventListener('click', () => setDrawMode('rectangle'));
$btnDrawPoint.addEventListener('click', () => setDrawMode('point'));

// ── UX 기능 설명 모달 ──
const $btnUxHelp = $('#btn-ux-help');
const $uxHelpModal = $('#ux-help-modal');
const $uxHelpClose = $('#ux-help-close');
function _openUxHelp() { if ($uxHelpModal) $uxHelpModal.classList.add('visible'); }
function _closeUxHelp() { if ($uxHelpModal) $uxHelpModal.classList.remove('visible'); }
if ($btnUxHelp) $btnUxHelp.addEventListener('click', _openUxHelp);
if ($uxHelpClose) $uxHelpClose.addEventListener('click', _closeUxHelp);
if ($uxHelpModal) {
    $uxHelpModal.addEventListener('click', (e) => {
        if (e.target === $uxHelpModal) _closeUxHelp();
    });
}
window.addEventListener('keydown', (e) => {
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
    Object.values(drawButtons).forEach(b => b.classList.remove('active'));
    if (mode && drawButtons[mode]) drawButtons[mode].classList.add('active');
};

// ── Annotation Panel ──
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
            <span class="ann-name" title="Double-click to rename">${ann.name}</span>
            <span class="ann-type">${ann.type}</span>
            <button class="ann-btn-vis" title="Toggle visibility">${ann.visible ? '👁' : '👁‍🗨'}</button>
            <button class="ann-btn-del" title="Delete">✕</button>
        `;
        // 클릭 → 선택
        el.addEventListener('click', (e) => {
            if (e.target.closest('.ann-color-swatch') || e.target.closest('.ann-btn-vis') ||
                e.target.closest('.ann-btn-del') || e.target.closest('.ann-name-input')) return;
            viewer.selectAnnotation(ann.id);
        });
        // 더블클릭 이름 → 리네임
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
        // 색상 변경
        el.querySelector('.ann-color-swatch').addEventListener('input', (e) => {
            const hex = e.target.value;
            ann.color = hexToRgb(hex);
            e.target.style.background = `rgb(${ann.color[0]},${ann.color[1]},${ann.color[2]})`;
            if (viewer.onAnnotationChanged) viewer.onAnnotationChanged(ann);
            viewer.requestRender();
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

// 캔버스 ↔ 패널 동기화
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
    // 이미 렌더링 요청됨 — 패널만 갱신 필요 시
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
    if (e.key === 'Delete' || e.key.toLowerCase() === 'd') {
        _doDeleteCell();
        e.preventDefault();
        return;
    }
    // 숫자키 1~9, 0 → 클래스 변경
    if (/^[0-9]$/.test(e.key)) {
        const num = parseInt(e.key, 10);
        const slot = num === 0 ? 9 : num - 1;
        if (_cellEditCtx.classButtonOrder && slot < _cellEditCtx.classButtonOrder.length) {
            const targetCls = _cellEditCtx.classButtonOrder[slot];
            _doChangeClass(targetCls);
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
    // 결과 리스트 카운트 갱신
    if (_lastDetectionResult) {
        _lastDetectionResult.cells = viewer.detectionCells;
        _lastDetectionResult.total_cells = viewer.detectionCells.length;
        buildResultList(_lastDetectionResult);
    }
    setStatus(`Cell edited — ${viewer.detectionCells.length} cells`);
};

// ── Cell edit Undo / Redo (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y) ──
window.addEventListener('keydown', (e) => {
    // 입력 위젯 포커스 중이면 무시
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable)) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    if (!viewer || !viewer.detectionCells || viewer.detectionCells.length === 0 && !viewer.canUndoCellEdit?.()) return;

    const key = e.key.toLowerCase();
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
    viewer.clearAnnotations();
    renderAnnotationPanel();
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

$btnAnnSave?.addEventListener('click', _downloadAnnotations);
$btnAnnLoad?.addEventListener('click', _uploadAnnotations);

// ═══════════════════════════
// 슬라이드 정보 다이얼로그
// ═══════════════════════════
$btnInfo.addEventListener('click', () => {
    if (!currentSlideInfo) return;
    const info = currentSlideInfo;
    const mag = info.objective_power !== 'Unknown' ? `${info.objective_power}x` : '-';
    const physW = info.physical_width_mm?.toFixed(2) ?? '-';
    const physH = info.physical_height_mm?.toFixed(2) ?? '-';

    let html = '<table>';
    html += `<tr><td>Filename</td><td>${info.filename}</td></tr>`;
    html += `<tr><td>Vendor</td><td>${info.vendor}</td></tr>`;
    html += `<tr><td>Magnification</td><td>${mag}</td></tr>`;
    html += `<tr><td>Pixel Size</td><td>${info.dimensions[0].toLocaleString()} × ${info.dimensions[1].toLocaleString()} px</td></tr>`;
    html += `<tr><td>MPP</td><td>${info.mpp_x?.toFixed(4) ?? '-'} × ${info.mpp_y?.toFixed(4) ?? '-'} μm/px</td></tr>`;
    html += `<tr><td>Physical Size</td><td>${physW} × ${physH} mm</td></tr>`;
    html += '</table>';
    $slideInfoContent.innerHTML = html;
    $slideInfoDialog.showModal();
});
$('#close-slide-info').addEventListener('click', () => $slideInfoDialog.close());

// ═══════════════════════════
// AI 검출
// ═══════════════════════════

// 실행 중인 AI task 추적 — key: 버튼 고유 키 ('detect', 'vs-ihc_membrane', 'pd-score', 'ihc-HER2' 등)
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
    _lastDetectionModel = 'HE-Fit';
    _lastDetectionRoi = roiPolygons;

    // segmentation 데이터 저장 (Spatial Heatmap 시각화용)
    lastSegData = result.seg_data || null;

    // HE-Fit 은 기본 CLASS_COLORS 사용 (override 해제)
    viewer.classColorOverride = null;
    viewer.defaultConfidence = 0.01;

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
}

// ═══════════════════════════
// 결과 리스트 (기존 resultList 재현)
// ═══════════════════════════
const CLASS_COLORS = {
    0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
    4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
};

// confidence 슬라이더 debounce용
let _confDebounceTimer = null;
function _debouncedRender() {
    if (_confDebounceTimer) clearTimeout(_confDebounceTimer);
    _confDebounceTimer = setTimeout(() => {
        viewer._buildHeatmapCache();
        viewer.requestRender();
    }, 200);
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

// 결과 리스트의 카운트 라벨만 갱신 (confidence 슬라이더 변경 시 호출)
let _resultCountRefs = null; // {total: el, perClass: {id: el}}
function _updateResultCounts() {
    if (!_resultCountRefs || !_lastDetectionResult) return;
    const { counts, total } = _computeFilteredCounts(viewer.detectionCells);
    _resultCountRefs.total.textContent = total.toLocaleString();
    for (const [idStr, el] of Object.entries(_resultCountRefs.perClass)) {
        const id = parseInt(idStr);
        el.textContent = (counts[id] || 0).toLocaleString();
    }
    _updatePdScoreDisplay(counts);
    _updateHer2ScoreDisplay(counts);
    _updateAllredScoreDisplay(counts);
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
        const viableTumor = (c[0] || 0) + (c[3] || 0);
        const score = viableTumor === 0
            ? 0
            : Math.min(100, (posTumor + posImmune) / viableTumor * 100);
        $pdScoreLabel.textContent = 'CPS';
        $pdScoreValue.textContent = `${score.toFixed(1)}%`;
        $pdScoreDetail.innerHTML =
            `Positive Tumor: ${posTumor} &nbsp;·&nbsp; ` +
            `Positive Immune: ${posImmune}<br>` +
            `Viable Tumor: ${viableTumor}`;
    } else if (scoreType === 'TPS') {
        const posTumor = c[1] || 0;
        const negTumor = c[0] || 0;
        const totalTumor = posTumor + negTumor;
        const score = totalTumor === 0 ? 0 : posTumor / totalTumor * 100;
        $pdScoreLabel.textContent = 'TPS';
        $pdScoreValue.textContent = `${score.toFixed(1)}%`;
        $pdScoreDetail.innerHTML =
            `Positive Tumor: ${posTumor} &nbsp;·&nbsp; ` +
            `Negative Tumor: ${negTumor}<br>` +
            `Total Tumor: ${totalTumor}`;
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
    $ihcScoreDetail.innerHTML =
        `0+: ${n0} &nbsp;·&nbsp; 1+: ${n1}<br>` +
        `2+: ${n2} &nbsp;·&nbsp; 3+: ${n3}<br>` +
        `Total: ${total}`;
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
    $ihcScoreLabel.textContent = `${markerLabel} (Allred)`;
    $ihcScoreValue.textContent = `${a.ts} / 8`;
    $ihcScoreDetail.innerHTML =
        `PS: ${a.ps} &nbsp;·&nbsp; IS: ${a.is_} &nbsp;·&nbsp; <strong>${a.interpretation}</strong><br>` +
        `Positive: ${a.posPct.toFixed(1)}% &nbsp;·&nbsp; Avg int: ${a.avg.toFixed(2)}<br>` +
        `0+: ${a.n0} · 1+: ${a.n1} · 2+: ${a.n2} · 3+: ${a.n3}<br>` +
        `Total: ${a.total}`;
}

function buildResultList(result) {
    $resultList.innerHTML = '';

    // 클래스별 카운트
    const counts = {};
    for (const cell of result.cells) {
        counts[cell.class_id] = (counts[cell.class_id] || 0) + 1;
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
    totalCount.textContent = result.total_cells.toLocaleString();

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
        countSpan.textContent = count.toLocaleString();
        perClassCountEls[id] = countSpan;

        item.append(cb, dot, nameSpan, countSpan);
        $resultList.appendChild(item);

        // 개별 confidence 슬라이더
        const sliderRow = document.createElement('div');
        sliderRow.className = 'class-conf-slider';

        const initConf = viewer.classConfidence[id] ?? viewer.defaultConfidence ?? 0.01;
        const initConfStr = initConf.toFixed(2);

        const sliderLabel = document.createElement('span');
        sliderLabel.className = 'conf-label';
        sliderLabel.textContent = initConfStr;

        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '0';
        slider.max = '1';
        slider.step = '0.01';
        slider.value = initConfStr;
        slider.addEventListener('input', () => {
            const val = parseFloat(slider.value);
            sliderLabel.textContent = val.toFixed(2);
            viewer.classConfidence[id] = val;
            _updateResultCounts();
            _debouncedRender();
        });

        sliderRow.append(slider, sliderLabel);
        $resultList.appendChild(sliderRow);
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
    _lastDetectionModel = null;
    _lastDetectionRoi = null;
}

$btnClearResults.addEventListener('click', clearResults);

$btnVisualize.addEventListener('click', () => {
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
    const isIhc = isHer2 || isAllred;
    const modelType = isIhc ? 'Precise-IHC' : (isPdScore ? 'PD-Score' : 'HE-Fit');
    const scoreType = isHer2
        ? 'HER2'
        : (isAllred ? 'Allred' : (isPdScore ? _lastDetectionResult.pd_score.score_type : null));
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
    if (!currentSlideId || !_lastDetectionResult) {
        setStatus('No detection result to save');
        return;
    }
    const tissue = _lastDetectionTissue || 'Stomach';
    const aiMode = _lastDetectionModel || 'HE-Fit';
    try {
        $btnSaveResults.disabled = true;
        // 뷰어에서 편집된 셀을 결과 객체에 반영 (class_id 변경 등)
        if (viewer?.detectionCells) {
            _lastDetectionResult.cells = viewer.detectionCells;
            _lastDetectionResult.total_cells = viewer.detectionCells.length;
        }
        const r = await api.saveDetectionResult(
            currentSlideId, tissue, _lastDetectionResult, aiMode,
        );
        setStatus(`Saved (${aiMode}/${tissue}): ${r.total_cells} cells → ${r.user_name || 'me'}`);
    } catch (err) {
        setStatus(`Save failed: ${err.message}`);
    } finally {
        $btnSaveResults.disabled = false;
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
    if (!currentSlideId) {
        setStatus('슬라이드를 먼저 열어주세요');
        return;
    }
    // 로드할 AI 모드/variant 결정: 현재 뷰어에 결과가 있으면 그것을, 없으면 기본(HE-Fit/Stomach)
    const aiMode = _lastDetectionModel || 'HE-Fit';
    const variant = _lastDetectionTissue || 'Stomach';
    $loadUserEditMeta.textContent = `Mode: ${aiMode}  /  Variant: ${variant}`;
    $loadUserEditList.innerHTML = '<div style="padding:12px; color:#888;">Loading…</div>';
    $loadUserEditDialog.showModal();

    let users = [];
    try {
        const r = await api.listUserAiEdits(currentSlideId, aiMode, variant);
        users = r.users || [];
    } catch (err) {
        $loadUserEditList.innerHTML = `<div style="padding:12px; color:#c66;">Failed: ${err.message}</div>`;
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

    for (const u of users) {
        const row = document.createElement('div');
        row.className = 'result-row';
        row.style.cssText = 'padding:10px 12px; cursor:pointer; border-bottom:1px solid #333;';
        const displayName = u.str_user_name || u.str_login_id || u.str_user_id;
        row.innerHTML = `
            <div style="font-weight:600;">${escapeHtml(displayName)}</div>
            <div style="font-size:11px; color:#888; margin-top:2px;">
                ${u.int_total_cells.toLocaleString()} cells · ${_fmtDateIso(u.dt_updated_at)}
            </div>`;
        row.addEventListener('click', async () => {
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
    if (aiMode === 'HE-Fit') {
        onDetectionComplete(result, roi, variant);
    } else if (aiMode === 'PD-Score') {
        onPdScoreComplete(result, roi, variant);
    } else if (aiMode === 'Precise-IHC') {
        onPreciseIhcComplete(result, roi, variant);
    }
}

function _rerunOriginalInference(aiMode, variant) {
    // 기존 AI 버튼과 동일한 경로로 재실행 — 서버 디스크 캐시가 있으면 즉시 반환됨
    if (aiMode === 'HE-Fit') {
        // startDetection 은 버튼 핸들러 내부에 있으므로 버튼 클릭 트리거
        $('#btn-detect')?.click();
    } else if (aiMode === 'PD-Score') {
        $('#btn-pd-score')?.click();
    } else if (aiMode === 'Precise-IHC') {
        if (variant === 'ER_PR') $('#btn-ihc-erpr')?.click();
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
    const startW = $leftPanel.offsetWidth;

    function onMove(ev) {
        const w = Math.max(160, Math.min(500, startW + ev.clientX - startX));
        document.documentElement.style.setProperty('--left-panel-w', `${w}px`);
        viewer._resizeCanvas();
    }
    function onUp() {
        $resizer.classList.remove('dragging');
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
    }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
});

// ═══════════════════════════
// 좌측 슬라이드 리스트 + 폴더 탐색
// ═══════════════════════════
let currentBrowsePath = '';  // uploads/ 기준 상대경로
const $breadcrumb = $('#folder-breadcrumb');

async function loadSlideList() {
    try {
        const data = await api.browse(currentBrowsePath);
        $slideList.innerHTML = '';

        // 빈 폴더
        if (data.folders.length === 0 && data.slides.length === 0) {
            $slideList.innerHTML = '<div style="padding:12px;color:var(--text-dim);font-size:11px;text-align:center;">Empty</div>';
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
            if (s.status) item.classList.add(`status-${s.status}`);
            item.dataset.filename = s.filename;
            item.dataset.slideId = s.slide_id;
            item.dataset.status = s.status || '';
            item.draggable = true;

            const thumb = document.createElement('img');
            thumb.className = 'slide-thumb';
            thumb.alt = s.filename;
            thumb.loading = 'lazy';
            thumb.src = api.thumbnailUrlByName(s.filename, currentBrowsePath, 96);
            thumb.onerror = () => { thumb.style.display = 'none'; };

            const name = document.createElement('div');
            name.className = 'slide-list-name';
            name.textContent = s.filename;
            name.title = `${s.filename} (${s.size_mb} MB)`;

            item.append(thumb, name);

            // 리뷰 상태 배지
            if (s.status) {
                const statusMeta = {
                    pending:     { label: '⋯', color: '#95a5a6', title: 'Pending' },
                    in_progress: { label: '▶', color: '#3498db', title: 'In Progress' },
                    done:        { label: '✓', color: '#27ae60', title: 'Done' },
                    flagged:     { label: '⚑', color: '#e74c3c', title: 'Flagged' },
                };
                const m = statusMeta[s.status];
                if (m) {
                    const dot = document.createElement('span');
                    dot.className = 'slide-status-dot';
                    dot.textContent = m.label;
                    dot.style.background = m.color;
                    dot.title = m.title;
                    item.appendChild(dot);
                }
            }

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
    currentBrowsePath = path;
    loadSlideList();
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
    const root = document.createElement('span');
    root.className = 'breadcrumb-item';
    root.textContent = 'Root';
    root.addEventListener('click', () => navigateToFolder(''));
    _makeBreadcrumbDroppable(root, '');
    $breadcrumb.appendChild(root);

    if (currentBrowsePath) {
        const parts = currentBrowsePath.split('/');
        let accumulated = '';
        for (const part of parts) {
            accumulated = accumulated ? `${accumulated}/${part}` : part;
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

    const aiCfgBtn = document.createElement('div');
    aiCfgBtn.className = 'ctx-menu-item';
    aiCfgBtn.textContent = 'AI 자동 분석 설정...';
    aiCfgBtn.addEventListener('click', () => {
        removeCtxMenu();
        openFolderAiConfigDialog(folderPath, folderName);
    });

    menu.append(renameBtn, deleteBtn, aiCfgBtn);
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
    { value: 'pending',     label: 'Pending',     color: '#95a5a6' },
    { value: 'in_progress', label: 'In Progress', color: '#3498db' },
    { value: 'done',        label: 'Done',        color: '#27ae60' },
    { value: 'flagged',     label: 'Flagged',     color: '#e74c3c' },
    { value: '',            label: 'Clear Status', color: '' },
];

async function _applyStatusToSelected(strStatus) {
    const list_filenames = _getSelectedSlideFilenames();
    if (list_filenames.length === 0) return;
    try {
        await api.setFileStatus(list_filenames, strStatus, currentBrowsePath);
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
    const labelStatus = document.createElement('div');
    labelStatus.className = 'ctx-menu-label';
    labelStatus.textContent = 'Set Status';
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
    { model: 'HE-Fit',      variant: 'Stomach', label: 'HE-Fit · Stomach' },
    { model: 'HE-Fit',      variant: 'Breast',  label: 'HE-Fit · Breast' },
    { model: 'HE-Fit',      variant: 'Other',   label: 'HE-Fit · Other' },
    { model: 'PD-Score',    variant: 'Stomach', label: 'PD-Score · Stomach (CPS)' },
    { model: 'PD-Score',    variant: 'Lung',    label: 'PD-Score · Lung (TPS)' },
    { model: 'Precise-IHC', variant: 'HER2',    label: 'Precise-IHC · HER2' },
    // ER/PR 임시 비활성화 — 준비되면 다시 활성화
    // { model: 'Precise-IHC', variant: 'ER_PR',   label: 'Precise-IHC · ER/PR (Allred)' },
    { model: 'VS-IHC',      variant: 'ihc_membrane', label: 'VS-IHC · Membrane (Virtual Stain)', mpp: true },
    { model: 'VS-IHC',      variant: 'ihc_nucleus',  label: 'VS-IHC · Nucleus (Virtual Stain)',  mpp: true },
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
    // VS-IHC: variant 별 선택된 mpp set 을 따로 관리
    const set_selected = new Set();
    const dict_vs_mpps = {};  // { variant: Set<number> }
    for (const t of (cfg.tasks || [])) {
        if (t.model === 'VS-IHC') {
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
            // VS-IHC: 상위 체크박스 = 선택된 mpp 가 하나라도 있으면 checked
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
            if (str_model === 'VS-IHC') {
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
// VS-IHC (Virtual Staining)
// ═══════════════════════════
async function startVirtualStain(stainType) {
    if (!currentSlideId) return;
    const str_key = 'vs-' + stainType;
    if (await _maybeCancelRunning(str_key)) return;

    const btnEl = stainType === 'ihc_nucleus' ? $btnVsNucleus : $btnVsMembrane;
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

// VS-IHC target mpp slider — index → mpp value
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
$btnVsNucleus?.addEventListener('click', () => startVirtualStain('ihc_nucleus'));

// ═══════════════════════════
// PD-Score (PD-L1) — CPS / TPS
// ═══════════════════════════
$btnPdScore?.addEventListener('click', startPdScore);

async function startPdScore() {
    if (!currentSlideId) return;
    if (await _maybeCancelRunning('pd-score')) return;

    _runningAiTasks['pd-score'] = { task_id: null, buttonEl: $btnPdScore };
    _setButtonRunning($btnPdScore, true);
    if ($pdScoreResult) $pdScoreResult.hidden = true;
    $progressLabel.textContent = 'PD-L1 Detection...';
    setProgress(0);
    setStatus('PD-Score 시작...');

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
                setStatus('PD-Score 중지됨 — 부분 결과 정리 완료');
                $progressLabel.textContent = 'Cancelled';
                setProgress(0);
                return;
            }
        }
    } catch (err) {
        setStatus(`PD-Score 실패: ${err.message}`);
    } finally {
        delete _runningAiTasks['pd-score'];
        _setButtonRunning($btnPdScore, false);
        if ($progressLabel.textContent === 'PD-L1 Detection...') {
            $progressLabel.textContent = 'AI Progress';
        }
    }
}

function onPdScoreComplete(result, roiPolygons = null, tissueType = null) {
    $progressLabel.textContent = 'PD-Score Complete';

    viewer.clearAnnotations();
    renderAnnotationPanel();

    _lastDetectionResult = result;
    _lastDetectionTissue = tissueType;
    _lastDetectionModel = 'PD-Score';
    _lastDetectionRoi = roiPolygons;
    lastSegData = null;

    // PD-Score 전용 클래스 색상 override (Stomach CPS: 녹/적 계열)
    const colorMap = {};
    if (result.class_colors) {
        for (const [k, v] of Object.entries(result.class_colors)) {
            colorMap[parseInt(k)] = v;
        }
    }
    viewer.classColorOverride = Object.keys(colorMap).length > 0 ? colorMap : null;
    viewer.defaultConfidence = 0.1;

    viewer.setDetectionResults(result.cells, roiPolygons);

    const displayCount = viewer.detectionCells.length;
    setProgress(100);
    const score = result.pd_score || {};
    const scoreLabel = score.score_type || 'Score';
    const scoreValue = (score.score ?? 0).toFixed(1);
    setStatus(`${scoreLabel}: ${scoreValue}% | ${displayCount.toLocaleString()} cells`);

    if ($pdScoreResult) {
        $pdScoreResult.hidden = false;
        $pdScoreLabel.textContent = scoreLabel;
        $pdScoreValue.textContent = `${scoreValue}%`;
        if (score.score_type === 'CPS') {
            $pdScoreDetail.innerHTML =
                `Positive Tumor: ${score.positive_tumor} &nbsp;·&nbsp; ` +
                `Positive Immune: ${score.positive_immune}<br>` +
                `Viable Tumor: ${score.viable_tumor}`;
        } else {
            $pdScoreDetail.innerHTML =
                `Positive Tumor: ${score.positive_tumor} &nbsp;·&nbsp; ` +
                `Negative Tumor: ${score.negative_tumor}<br>` +
                `Total Tumor: ${score.total_tumor}`;
        }
    }

    buildResultList(result);
    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
}

$btnIhcHer2?.addEventListener('click', () => startPreciseIhc('HER2'));
$btnIhcErPr?.addEventListener('click', () => startPreciseIhc('ER_PR'));

function _setIhcMarkerButtonsDisabled(disabled) {
    if ($btnIhcHer2) $btnIhcHer2.disabled = disabled;
    if ($btnIhcErPr) $btnIhcErPr.disabled = disabled;
}

async function startPreciseIhc(marker) {
    if (!currentSlideId) return;
    const str_key = 'ihc-' + marker;
    if (await _maybeCancelRunning(str_key)) return;

    const btnEl = marker === 'ER_PR' ? $btnIhcErPr : $btnIhcHer2;
    const markerLabel = marker === 'ER_PR' ? 'ER/PR' : marker;
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
    const markerLabel = marker === 'ER_PR' ? 'ER/PR' : marker;
    $progressLabel.textContent = `${markerLabel} Complete`;

    viewer.clearAnnotations();
    renderAnnotationPanel();

    _lastDetectionResult = result;
    _lastDetectionTissue = marker;
    _lastDetectionModel = 'Precise-IHC';
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

    const displayCount = viewer.detectionCells.length;
    setProgress(100);

    if (result.her2_score) {
        const score = result.her2_score;
        const dominant = score.dominant_class ?? 0;
        const weighted = (score.score ?? 0).toFixed(2);
        setStatus(`HER2: ${dominant}+ (${weighted}) | ${displayCount.toLocaleString()} cells`);
        if ($ihcScoreResult) {
            $ihcScoreResult.hidden = false;
            $ihcScoreLabel.textContent = 'HER2';
            $ihcScoreValue.textContent = `${dominant}+ (${weighted})`;
            const cc = score.class_counts || {};
            $ihcScoreDetail.innerHTML =
                `0+: ${cc[0] || 0} &nbsp;·&nbsp; 1+: ${cc[1] || 0}<br>` +
                `2+: ${cc[2] || 0} &nbsp;·&nbsp; 3+: ${cc[3] || 0}<br>` +
                `Total: ${score.total_tumor || 0}`;
        }
    } else if (result.allred_score) {
        const score = result.allred_score;
        const ts = score.total_score ?? 0;
        const ps = score.proportion_score ?? 0;
        const is_ = score.intensity_score ?? 0;
        const interp = score.interpretation || (ts >= 3 ? 'Positive' : 'Negative');
        setStatus(`${markerLabel} Allred: ${ts} (PS ${ps} + IS ${is_}) — ${interp} | ${displayCount.toLocaleString()} cells`);
        if ($ihcScoreResult) {
            $ihcScoreResult.hidden = false;
            $ihcScoreLabel.textContent = `${markerLabel} (Allred)`;
            $ihcScoreValue.textContent = `${ts} / 8`;
            const cc = score.class_counts || {};
            $ihcScoreDetail.innerHTML =
                `PS: ${ps} &nbsp;·&nbsp; IS: ${is_} &nbsp;·&nbsp; <strong>${interp}</strong><br>` +
                `Positive: ${(score.positive_pct ?? 0).toFixed(1)}% &nbsp;·&nbsp; ` +
                `Avg int: ${(score.avg_intensity ?? 0).toFixed(2)}<br>` +
                `0+: ${cc[0] || 0} · 1+: ${cc[1] || 0} · 2+: ${cc[2] || 0} · 3+: ${cc[3] || 0}<br>` +
                `Total: ${score.total_tumor || 0}`;
        }
    }

    buildResultList(result);
    $btnVisualize.disabled = false;
    $btnClearResults.disabled = false;
    $btnSaveResults.disabled = false;
    if ($btnLoadResults) $btnLoadResults.disabled = false;
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
        if (dict_me.str_role === 'admin') {
            const $linkAdmin = document.getElementById('link-admin');
            if ($linkAdmin) $linkAdmin.hidden = false;
        }
        window.__currentUserRole = dict_me.str_role || 'viewer';
        if (window.__currentUserRole === 'viewer') {
            _applyViewerRoleRestrictions();
        }
    } catch (_) {
        // 인증 실패 — api.js 가 리다이렉트 처리. 슬라이드/폴링 시작 생략.
        return;
    }
    loadSlideList();
})();
