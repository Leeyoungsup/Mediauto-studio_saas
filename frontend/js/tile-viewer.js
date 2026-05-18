/**
 * WSI Tile Viewer — Canvas 기반 타일 렌더링 엔진
 * PyQt5 wsi_view_widget.py + wsi_tile_manager.py 로직을 JS로 포팅
 *
 * 좌표계: WSI level-0 픽셀 좌표 (scene 좌표)
 * 렌더링: 현재 zoom에 맞는 OpenSlide level의 타일을 서버에서 로드하여 canvas에 그림
 *
 * 핵심 원리 (PyQt5 원본과 동일):
 *  - 레벨 변경 시 이전 레벨 타일을 스케일해서 먼저 보여줌 (fallback)
 *  - 새 레벨 타일이 로드되면 점차 교체 → 검은 화면 없음
 */

import { api } from './api.js';

const TILE_SIZE = 1024;
// 타일 동시 로딩 상한 — 브라우저 HTTP/1.1 per-origin 제한(6)에 맞춘다.
// 이보다 크게 잡으면 남는 요청이 브라우저 큐에 박혀 abort 불가 상태가 되고,
// 팬/줌으로 더 이상 필요 없어진 좀비 요청들이 _activeLoads 슬롯을 계속 점유해
// 새 타일이 못 나가는 stall 이 발생했다.
const MAX_CONCURRENT_LOADS = 6;

// 3단계 stage 피라미드 — 반드시 backend slide_manager.STAGE_DOWNSAMPLES 와 동일
//   stage 0: level0 1024x1024 그대로   (downsample 1)
//   stage 1: level0 4096x4096 → 1024   (downsample 4)
//   stage 2: level0 8192x8192 → 1024   (downsample 8)
const STAGE_DOWNSAMPLES = [1, 4, 8];

/**
 * 공간 격자 인덱스 — 데스크톱 SpatialGrid와 동일
 * 셀을 grid_size 단위 버킷에 분류하여 뷰포트 영역의 셀만 O(1)에 조회
 */
class SpatialGrid {
    constructor(gridSize = 2048) {
        this.gridSize = gridSize;
        this.grid = new Map();
    }

    build(cells) {
        this.grid.clear();
        const gs = this.gridSize;
        for (let i = 0; i < cells.length; i++) {
            const c = cells[i];
            const key = (Math.floor(c.x / gs) << 16) | (Math.floor(c.y / gs) & 0xFFFF);
            let bucket = this.grid.get(key);
            if (!bucket) { bucket = []; this.grid.set(key, bucket); }
            bucket.push(c);
        }
    }

    query(xMin, yMin, xMax, yMax) {
        const gs = this.gridSize;
        const gxMin = Math.floor(xMin / gs);
        const gyMin = Math.floor(yMin / gs);
        const gxMax = Math.floor(xMax / gs);
        const gyMax = Math.floor(yMax / gs);
        const result = [];
        for (let gx = gxMin; gx <= gxMax; gx++) {
            for (let gy = gyMin; gy <= gyMax; gy++) {
                const key = (gx << 16) | (gy & 0xFFFF);
                const bucket = this.grid.get(key);
                if (!bucket) continue;
                for (const c of bucket) {
                    if (c.x >= xMin && c.x < xMax && c.y >= yMin && c.y < yMax) {
                        result.push(c);
                    }
                }
            }
        }
        return result;
    }
}

export class TileViewer {
    constructor(canvas, overlayCanvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.overlayCanvas = overlayCanvas;
        this.overlayCtx = overlayCanvas.getContext('2d');

        // 슬라이드 상태
        this.slideId = null;
        this.slideInfo = null;

        // 뷰 상태 (scene 좌표계 = level-0 px)
        this.viewCenterX = 0;
        this.viewCenterY = 0;
        this.zoom = 1.0;
        this.minZoom = 0.001;
        this.maxZoom = 40.0;

        // 타일 캐시 — 모든 레벨의 타일을 보관 (fallback용). NDP 토글 시 비우고 재로드.
        this._tileCache = new Map();  // "level/tx/ty" -> HTMLImageElement
        this._tileLoading = new Set();
        // 타일 페이드인 — key → fade start timestamp (ms). 새로 도착한 current-level
        // child 타일을 alpha 0 → 1 로 램프해 OSD 처럼 부드럽게 레이어 전환을 보이게 한다.
        this._tileFadeStart = new Map();
        this._fadeDurationMs = 250;
        this._thumbnailBitmap = null;  // 전역 폴백용 고해상도 썸네일 (slide 열 때 1회 로드)
        // ── NDP 색보정 toggle (Hamamatsu 전용) ──
        // app.js 가 setColorCorrectionEnabled() 로 제어. 기본 OFF.
        // ON 시 타일/썸네일 URL 에 ?ndp=true 또는 /ndp/ 서브경로 사용 — 서버가
        // ndpmatch 변형 JPEG 을 디스크 캐시에 두고 반환. 클라이언트 CPU 부담 없음.
        this._colorCorrectionEnabled = false;
        this._maxCacheTiles = 3000;
        this._loadQueue = [];         // 우선순위 로드 큐
        this._activeLoads = 0;
        // 인플라이트 Image 객체들 — 슬라이드 전환 시 abort 용
        this._inflightImages = new Set();
        // 슬라이드 generation — onload 콜백이 자기 generation 을 기억해 stale 방지
        this._loadGeneration = 0;

        // 3-stage 프리로드 추적 — 슬라이드 열 때 3개 stage level 의 모든 타일이 다
        // 로드될 때까지 앱에서 로딩창을 띄운다.
        this._preloadKeys = null;   // Set<string> of tile keys that belong to initial preload
        this._preloadTotal = 0;
        this._preloadDone = 0;
        this._isPreloading = false;

        // 패닝 상태
        this._isPanning = false;
        this._lastPanX = 0;
        this._lastPanY = 0;

        // 검출 결과
        this.detectionCells = [];
        this.classVisibility = {};   // {class_id: bool}
        this.classColorOverride = null;  // {class_id: '#hex'} — set per AI task to override CLASS_COLORS
        this.classConfidence = {};   // {class_id: float} 클래스별 threshold (기본 defaultConfidence)
        this.defaultConfidence = 0.01;  // 현재 활성 모델의 초기 임계값 (PD-L1/HER2 는 0.1)
        this._spatialGrid = null;    // SpatialGrid for O(1) viewport query
        this._highlightedCellIdx = -1; // Alt+Click 편집 대상 셀
        this._highlightedCellIdxSet = null; // Alt+Drag 다중 선택 셀 Set
        this.onCellEditRequested = null; // (idx, cell, screenX, screenY) callback
        this.onCellsMultiEditRequested = null; // (indices, cells, screenX, screenY) callback
        this.onCellAddRequested = null;  // (sx, sy, screenX, screenY) callback — Shift+click
        this.onCellEdited = null;        // 편집 후 콜백
        // Alt+Drag 라쏘 상태
        this._altPending = null;   // { sx, sy, cx, cy, clientX, clientY }
        // Shift+click 셀 추가 — mousedown 시 위치 기록, mouseup 에서 단일 클릭 확정 시 콜백.
        this._shiftAddPending = null;  // { sx, sy, cx, cy, clientX, clientY }
        this._lassoActive = false;
        this._lassoPoints = [];    // [[sx, sy], ...] scene 좌표
        // Undo/Redo (셀 편집)
        this._undoStack = [];
        this._redoStack = [];
        this._maxUndo = 200;
        this._annotationUndoStack = [];
        this._annotationRedoStack = [];
        this._maxAnnotationUndo = 100;

        // Segmentation 오버레이
        this._segOverlay = null;     // {image, sceneX, sceneY, sceneW, sceneH}
        this.segClassVisibility = {}; // {cls_id: bool}

        // Virtual Stain (VS IHC) 오버레이 — 타일 피라미드 기반
        // meta: {slideId, stainType, targetMpp, originX, originY, sceneW, sceneH,
        //        tileSize, levels: [{level,width,height,nx,ny}...], roiPolygons}
        this._vsOverlay = null;
        this._vsVisible = true;
        this._vsSplitMode = false;   // true: 분할선 기준 우측에만 VS 표시 (좌: 원본 IHC)
        this._vsSplitFrac = 0.5;     // 분할선 위치 (0..1, 캔버스 가로 비율)
        this._vsSplitDragging = false;
        this._vsSplitHandleW = 10;   // 분할선 hit-area (±px)

        // VS 타일 캐시 (level/tx/ty 키)
        this._vsTileCache = new Map();    // key → HTMLImageElement (LRU: Map insertion order)
        this._vsTileLoading = new Set();  // in-flight keys
        this._vsTileMissing = new Set();  // 404 마크 (빈 타일 재요청 방지)
        this._vsLoadQueue = [];           // VS 타일 로딩 큐
        this._vsActiveLoads = 0;          // 현재 진행 중인 VS 타일 로드 수
        this._vsMaxTiles = 512;

        // ── Annotation ──
        this.annotations = [];        // [{id, name, type, coordinates, color, visible, selected, group}]
        this.drawMode = null;         // 'polygon' | 'brush' | 'rectangle' | 'point' | 'cut' | 'rect-1mm2' | 'circle-1mm2' | 'ruler' | null
        this._drawingPoints = [];     // 진행 중인 폴리곤 좌표 (scene)
        this._drawingStart = null;    // 사각형 시작점 (scene)
        this._drawingCurrent = null;  // 사각형/폴리곤 현재 마우스 (scene)
        this._brushSizePx = Number(localStorage.getItem('annotationBrushSizePx') || 28);
        this._brushSizePx = Math.max(4, Math.min(120, this._brushSizePx));
        // Ruler — 일회성 측정. annotation 으로 저장하지 않고 화면에만 남는다.
        // mode 해제 / 새 측정 시작 시 사라짐.
        this._rulerStart = null;      // [sx, sy]
        this._rulerEnd = null;        // [sx, sy] — 마우스 따라가다가 두 번째 클릭 시 고정
        this._rulerFinalized = false; // true 면 두 번째 클릭이 들어와 측정이 고정된 상태
        this._isDrawing = false;
        this._annotationCounter = 0;
        this.selectedAnnotationId = null;
        this._insertVertexPreview = null; // {annId, insertIndex, point:[sx,sy]} Ctrl+polygon edge insert preview
        this._mergeHover = null;       // {annIds:[id,id], scenePoint:[sx,sy]} same-class polygon merge affordance
        this._dragControlPoint = null;  // {annId, pointIndex} 드래그 중인 컨트롤포인트
        this._dragAnnotation = null;    // {annId, startScene} 어노테이션 전체 이동
        this._lastDrawDragScene = null; // 폴리곤 드래그 점 추가용

        // 콜백
        this.onZoomChange = null;
        this.onViewChange = null;
        this.onPreloadStart = null;     // () => {}  3-stage 프리로드 시작
        this.onPreloadProgress = null;  // (done, total) => {}
        this.onPreloadComplete = null;  // () => {}  3-stage 프리로드 완료
        this.onAnnotationCreated = null;   // (annotation) => {}
        this.onAnnotationSelected = null;  // (annotation|null) => {}
        this.onAnnotationDeleted = null;   // (annotation) => {}
        this.onAnnotationChanged = null;   // (annotation) => {}
        this.onDrawModeChange = null;      // (mode) => {}

        // 렌더 루프 제어
        this._renderPending = false;

        this._setupEvents();
        this._resizeCanvas();
        window.addEventListener('resize', () => this._resizeCanvas());
    }

    // ── 슬라이드 로드 ──

    loadSlide(slideId, slideInfo) {
        // 인플라이트 Image 들 abort — onload 가 새 슬라이드 cache 에 옛 픽셀 박는 것 차단
        this._loadGeneration++;
        for (const img of this._inflightImages) {
            try { img.onload = null; img.onerror = null; img.src = ''; } catch (e) {}
        }
        this._inflightImages.clear();

        this.slideId = slideId;
        this.slideInfo = slideInfo;

        this._tileCache.clear();
        this._tileLoading.clear();
        this._tileFadeStart.clear();
        this._loadQueue = [];
        this._activeLoads = 0;
        this._thumbnailBitmap = null;
        this.detectionCells = [];
        this.annotations = [];
        this.selectedAnnotationId = null;
        this._annotationCounter = 0;
        this._annotationUndoStack = [];
        this._annotationRedoStack = [];
        this._thumbnailBitmap = null;

        // 이전 슬라이드의 프리로드 상태 초기화
        this._preloadKeys = null;
        this._preloadTotal = 0;
        this._preloadDone = 0;
        this._isPreloading = false;

        this.fitToWindow();
        // 3 stage level 전체 프리로드 — 완료까지 앱은 로딩창 표시
        this._preloadAllStageLevels();
        // 전역 폴백용 고해상도 썸네일 1회 로드 — 타일/폴백 모두 miss 일 때 최후의 블러 표시
        this._loadThumbnailFallback();
    }

    _loadThumbnailFallback() {
        if (!this.slideId) return;
        const str_slide_id = this.slideId;

        // ndpMatch 상태를 URL 에 반영 — 서버가 ndpmatch 변형을 리턴
        const bool_ndp = !!this._colorCorrectionEnabled;

        // 0단계 — 사이드바가 이미 로드해 놓은 DOM <img> 훔치기 (네트워크 0ms).
        // 사이드바 썸네일은 ndp 보정 안 된 raw 라 색보정 ON 상태라면 사용 안 함.
        const el_sidebar_thumb = document.querySelector(
            `.slide-list-item[data-slide-id="${str_slide_id}"] .slide-thumb`
        );
        if (!bool_ndp && el_sidebar_thumb && el_sidebar_thumb.complete && el_sidebar_thumb.naturalWidth > 0) {
            this._thumbnailBitmap = el_sidebar_thumb;
        }

        // 1단계 — 디스크 캐시된 300px 썸네일 업그레이드
        const img_small = new Image();
        img_small.onload = () => {
            if (this.slideId !== str_slide_id) return;
            if (!this._thumbnailBitmap || this._thumbnailBitmap.naturalWidth <= 300) {
                this._thumbnailBitmap = img_small;
                this.requestRender();
            }
        };
        img_small.onerror = (e) => console.warn('[tile-viewer] small thumb load failed', img_small.src, e);
        img_small.src = api.thumbnailUrl(str_slide_id, 300, bool_ndp);

        // 2단계 — 2048px 고해상도 preview (on-demand, 수 초 가능)
        const img_hi = new Image();
        img_hi.onload = () => {
            if (this.slideId !== str_slide_id) return;
            this._thumbnailBitmap = img_hi;
            this.requestRender();
        };
        img_hi.onerror = (e) => console.warn('[tile-viewer] hi-res preview load failed', img_hi.src, e);
        img_hi.src = api.previewUrl(str_slide_id, 2048, bool_ndp);
    }

    _preloadAllStageLevels() {
        if (!this.slideInfo) return;
        // 초기에는 stage 2 (가장 거친) 만 전체 프리로드.
        // stage 0, 1 은 사용자가 zoom in 할 때 on-demand 로 로드.
        const int_level = 2;
        const [levelW, levelH] = this._stageDimensions(int_level);
        const nx = Math.ceil(levelW / TILE_SIZE);
        const ny = Math.ceil(levelH / TILE_SIZE);

        const set_keys = new Set();
        const list_tasks = [];
        for (let ty = 0; ty < ny; ty++) {
            for (let tx = 0; tx < nx; tx++) {
                const key = `${int_level}/${tx}/${ty}`;
                set_keys.add(key);
                list_tasks.push({ level: int_level, tx, ty });
            }
        }

        this._preloadKeys = set_keys;
        this._preloadTotal = set_keys.size;
        this._preloadDone = 0;
        this._isPreloading = this._preloadTotal > 0;

        if (this._isPreloading && this.onPreloadStart) {
            this.onPreloadStart();
        }
        if (this._preloadTotal === 0) {
            if (this.onPreloadComplete) this.onPreloadComplete();
            return;
        }

        for (const t of list_tasks) {
            this._loadQueue.push(t);
        }
        this._processLoadQueue();
    }

    _markPreloadTileDone(key) {
        if (!this._preloadKeys || !this._preloadKeys.has(key)) return;
        this._preloadKeys.delete(key);
        this._preloadDone++;
        if (this.onPreloadProgress) {
            this.onPreloadProgress(this._preloadDone, this._preloadTotal);
        }
        if (this._preloadDone >= this._preloadTotal) {
            this._isPreloading = false;
            if (this.onPreloadComplete) this.onPreloadComplete();
        }
    }

    fitToWindow() {
        if (!this.slideInfo) return;
        const [imgW, imgH] = this.slideInfo.dimensions;
        const vw = this._viewW;
        const vh = this._viewH;
        this.zoom = Math.min(vw / imgW, vh / imgH);
        this.minZoom = this.zoom;
        this.viewCenterX = imgW / 2;
        this.viewCenterY = imgH / 2;

        const baseMag = (0.25 / this.slideInfo.mpp) * 40.0;
        this.maxZoom = 80.0 / baseMag;

        this._emitZoomChange();
        this.requestRender();
    }

    // ── 좌표 변환 ──

    sceneToCanvas(sx, sy) {
        const cx = (sx - this.viewCenterX) * this.zoom + this._viewW / 2;
        const cy = (sy - this.viewCenterY) * this.zoom + this._viewH / 2;
        return [cx, cy];
    }

    canvasToScene(cx, cy) {
        const sx = (cx - this._viewW / 2) / this.zoom + this.viewCenterX;
        const sy = (cy - this._viewH / 2) / this.zoom + this.viewCenterY;
        return [sx, sy];
    }

    getEffectiveMpp() {
        if (!this.slideInfo || this.zoom <= 0) return Infinity;
        return this.slideInfo.mpp / this.zoom;
    }

    getMagnification() {
        if (!this.slideInfo || this.zoom <= 0) return 0;
        const baseMag = (0.25 / this.slideInfo.mpp) * 40.0;
        return baseMag * this.zoom;
    }

    _getStageLevel(effectiveMpp) {
        // stage index 반환 (0/1/2). level 이 아닌 stage 인덱스 그 자체.
        if (effectiveMpp < 2.0) return 0;
        if (effectiveMpp < 15.0) return 1;
        return 2;
    }

    _getLevelStages() {
        // 3단계 stage 는 항상 [0, 1, 2] — stage index 가 곧 level 변수의 값
        return [0, 1, 2];
    }

    _stageDownsample(stage) {
        return STAGE_DOWNSAMPLES[stage];
    }

    _stageDimensions(stage) {
        // backend 의 stage_dimensions 가 있으면 사용, 없으면 level 0 크기에서 계산
        if (this.slideInfo &&
            Array.isArray(this.slideInfo.stage_dimensions) &&
            this.slideInfo.stage_dimensions[stage]) {
            return this.slideInfo.stage_dimensions[stage];
        }
        const [w0, h0] = this.slideInfo.dimensions;
        const ds = STAGE_DOWNSAMPLES[stage];
        return [Math.max(1, Math.ceil(w0 / ds)), Math.max(1, Math.ceil(h0 / ds))];
    }

    // ── 줌 ──

    setZoom(newZoom, anchorCanvasX = null, anchorCanvasY = null) {
        newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, newZoom));
        if (newZoom === this.zoom) return;

        if (anchorCanvasX !== null && anchorCanvasY !== null) {
            const [sceneX, sceneY] = this.canvasToScene(anchorCanvasX, anchorCanvasY);
            const strength = 0.3;
            this.viewCenterX += (sceneX - this.viewCenterX) * strength;
            this.viewCenterY += (sceneY - this.viewCenterY) * strength;
        }

        this.zoom = newZoom;
        this._clampView();
        this._emitZoomChange();
        this.requestRender();
    }

    zoomIn(anchorX = null, anchorY = null) {
        this.setZoom(this.zoom * 1.1, anchorX, anchorY);
    }

    zoomOut(anchorX = null, anchorY = null) {
        this.setZoom(this.zoom / 1.1, anchorX, anchorY);
    }

    _clampView() {
        if (!this.slideInfo) return;
        const [imgW, imgH] = this.slideInfo.dimensions;
        const halfVW = (this._viewW / this.zoom) / 2;
        const halfVH = (this._viewH / this.zoom) / 2;

        if (imgW > halfVW * 2) {
            this.viewCenterX = Math.max(halfVW, Math.min(this.viewCenterX, imgW - halfVW));
        } else {
            this.viewCenterX = imgW / 2;
        }
        if (imgH > halfVH * 2) {
            this.viewCenterY = Math.max(halfVH, Math.min(this.viewCenterY, imgH - halfVH));
        } else {
            this.viewCenterY = imgH / 2;
        }
    }

    _emitZoomChange() {
        if (this.onZoomChange) {
            this.onZoomChange(this.zoom, this.getMagnification(), this.getEffectiveMpp());
        }
        if (this.onViewChange) {
            this.onViewChange();
        }
    }

    // ── 이벤트 ──

    _setupEvents() {
        // ── 줌 ──
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.altKey && this.drawMode === 'brush') {
                this._adjustBrushSize(e.deltaY < 0 ? 2 : -2);
                return;
            }
            if (!this.slideInfo) return;
            const rect = this.canvas.getBoundingClientRect();
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;
            if (e.deltaY < 0) this.zoomIn(cx, cy);
            else this.zoomOut(cx, cy);
        }, { passive: false });

        // ── 마우스 ──
        this.canvas.addEventListener('mousedown', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;
            const [sx, sy] = this.canvasToScene(cx, cy);

            // VS Split mode: 분할선 핸들 hit-test (최우선)
            if (e.button === 0 && this._vsSplitMode && this._vsOverlay && this._vsVisible) {
                const splitX = this._viewW * this._vsSplitFrac;
                if (Math.abs(cx - splitX) <= this._vsSplitHandleW) {
                    this._vsSplitDragging = true;
                    this.canvas.style.cursor = 'ew-resize';
                    e.preventDefault();
                    return;
                }
            }

            // Alt + 좌클릭/드래그: 셀 편집 (클릭=단일, 드래그=라쏘 다중 선택)
            // mousedown 시점에는 판단 유보 — mousemove로 드래그 여부 감지
            if (e.ctrlKey && e.button === 0 && this._isMergeHoverHit(cx, cy)) {
                this._mergeHoveredPolygons();
                e.preventDefault();
                return;
            }

            if (e.ctrlKey && e.button === 0 && this.drawMode) {
                const hitAnn = this._hitAnnotation(sx, sy);
                if (hitAnn) {
                    this.selectAnnotation(hitAnn.id);
                    e.preventDefault();
                }
            }
            if (e.ctrlKey && e.button === 0 && !this.drawMode) {
                const hitAnn = this._hitAnnotation(sx, sy);
                if (hitAnn) {
                    this.selectAnnotation(hitAnn.id);
                    e.preventDefault();
                }
            }

            if (e.button === 0 && e.altKey && !this.drawMode) {
                const insertHit = this._findPolygonEdgeInsertTarget(sx, sy);
                if (insertHit) {
                    this._insertVertexAtEdge(insertHit);
                    e.preventDefault();
                    return;
                }
            }

            if (e.altKey && e.button === 0 && this.detectionCells.length > 0) {
                this._altPending = {
                    sx, sy, cx, cy,
                    clientX: e.clientX, clientY: e.clientY,
                };
                this._lassoActive = false;
                this._lassoPoints = [];
                e.preventDefault();
                return;
            }

            // Shift + 좌클릭: 새 셀 추가 (drawMode 가 아닌 경우만 — drawMode 는 자체 click 처리).
            // detection 결과가 있을 때만 의미 — class_names 가 결정되어 있어야 클래스 선택 가능.
            // 클래스 변경은 Shift+A 단축키로 별도 처리 (Ctrl 사용 안 함 — Ctrl 은 패닝 modifier).
            if (e.shiftKey && e.button === 0 && !e.ctrlKey && !e.metaKey) {
                const hitAnn = this._hitAnnotation(sx, sy);
                if (hitAnn) {
                    this.pushAnnotationUndo();
                    this.selectAnnotation(hitAnn.id);
                    this._dragAnnotation = {
                        annId: hitAnn.id,
                        startScene: [sx, sy],
                        origCoords: hitAnn.coordinates.map(([x, y]) => [x, y]),
                    };
                    this.canvas.style.cursor = 'move';
                    e.preventDefault();
                    return;
                }
            }

            if (e.shiftKey && e.button === 0 && !e.ctrlKey && !e.metaKey && !this.drawMode &&
                    this.onCellAddRequested && this.detectionCells.length > 0) {
                this._shiftAddPending = {
                    sx, sy, cx, cy,
                    clientX: e.clientX, clientY: e.clientY,
                };
                e.preventDefault();
                return;
            }

            // 그리기 모드
            if (this.drawMode && e.button === 0 && !e.ctrlKey) {
                this._onDrawMouseDown(sx, sy, cx, cy, e);
                return;
            }

            // 컨트롤포인트 드래그 감지 (선택된 annotation의 꼭짓점)
            // Ctrl 누른 상태면 annotation 내부여도 pan 우선 (주석 이동 방지)
            if (e.button === 0 && !this.drawMode && !e.ctrlKey) {
                const cp = this._hitControlPoint(cx, cy);
                if (cp) {
                    this.pushAnnotationUndo();
                    this._dragControlPoint = cp;
                    this.canvas.style.cursor = 'move';
                    return;
                }

                // annotation 클릭 선택 / 이동
                const hitAnn = this._hitAnnotation(sx, sy);
                if (hitAnn) {
                    this.selectAnnotation(hitAnn.id);
                    this.canvas.style.cursor = 'grabbing';
                }

                // 빈 공간 클릭 → 선택 해제
                if (!hitAnn && !e.ctrlKey && this.selectedAnnotationId) {
                    this.selectAnnotation(null);
                }
            }

            // Ctrl+좌클릭 또는 일반 패닝
            if (e.button === 0 || e.button === 1) {
                this._isPanning = true;
                this._lastPanX = e.clientX;
                this._lastPanY = e.clientY;
                this.canvas.style.cursor = 'grabbing';
            }
        });

        window.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;
            const [sx, sy] = this.canvasToScene(cx, cy);

            // Alt+드래그 라쏘 진행
            if (this._altPending) {
                if (!this._lassoActive) {
                    const dx = cx - this._altPending.cx;
                    const dy = cy - this._altPending.cy;
                    if (Math.hypot(dx, dy) > 4) {
                        this._lassoActive = true;
                        this._lassoPoints = [[this._altPending.sx, this._altPending.sy]];
                    }
                }
                if (this._lassoActive) {
                    this._lassoPoints.push([sx, sy]);
                    this.requestRender();
                }
                return;
            }

            // VS Split 분할선 드래그
            if (this._vsSplitDragging) {
                const w = this._viewW;
                let frac = cx / w;
                // 양 끝 여백 (최소 5%)
                frac = Math.max(0.05, Math.min(0.95, frac));
                this._vsSplitFrac = frac;
                this.requestRender();
                return;
            }
            if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation) {
                this._setMergeHover(e.ctrlKey ? this._findMergeHoverTarget(sx, sy) : null);
                if (this._mergeHover) {
                    this.canvas.style.cursor = 'pointer';
                    return;
                }
            }
            if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation && !this.drawMode) {
                this._setInsertVertexPreview(e.altKey ? this._findPolygonEdgeInsertTarget(sx, sy) : null);
                if (this._insertVertexPreview) {
                    this.canvas.style.cursor = 'copy';
                    return;
                }
            }
            // hover 시 cursor 힌트 (드래그/패닝/그리기 중이 아닐 때만)
            if (this._vsSplitMode && this._vsOverlay && this._vsVisible &&
                !this._isPanning && !this._dragControlPoint && !this._dragAnnotation && !this.drawMode) {
                const insideCanvas = cx >= 0 && cy >= 0 &&
                                     cx <= this._viewW && cy <= this._viewH;
                if (insideCanvas) {
                    const splitX = this._viewW * this._vsSplitFrac;
                    if (Math.abs(cx - splitX) <= this._vsSplitHandleW) {
                        this.canvas.style.cursor = 'ew-resize';
                    } else if (this.canvas.style.cursor === 'ew-resize') {
                        this.canvas.style.cursor = 'grab';
                    }
                }
            }
            if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation && !this.drawMode) {
                const insideCanvas = cx >= 0 && cy >= 0 &&
                                     cx <= this._viewW && cy <= this._viewH;
                if (insideCanvas) {
                    const cp = this._hitControlPoint(cx, cy);
                    this.canvas.style.cursor = cp ? 'move' : 'grab';
                }
            }

            // 컨트롤포인트 드래그
            if (this._dragControlPoint) {
                const ann = this.annotations.find(a => a.id === this._dragControlPoint.annId);
                if (ann) {
                    if (ann.type === 'rectangle' && ann.coordinates.length === 4) {
                        this._resizeRectangleFromCorner(ann, this._dragControlPoint.pointIndex, sx, sy);
                    } else {
                        ann.coordinates[this._dragControlPoint.pointIndex] = [sx, sy];
                    }
                    if (this.onAnnotationChanged) this.onAnnotationChanged(ann);
                    this.requestRender();
                }
                return;
            }

            // annotation 전체 이동
            if (this._dragAnnotation) {
                const ann = this.annotations.find(a => a.id === this._dragAnnotation.annId);
                if (ann) {
                    const dx = sx - this._dragAnnotation.startScene[0];
                    const dy = sy - this._dragAnnotation.startScene[1];
                    ann.coordinates = this._dragAnnotation.origCoords.map(([ox, oy]) => [ox + dx, oy + dy]);
                    if (this.onAnnotationChanged) this.onAnnotationChanged(ann);
                    this.requestRender();
                }
                return;
            }

            // 그리기 모드
            if (this.drawMode && this._isDrawing) {
                this._onDrawMouseMove(sx, sy, cx, cy);
                return;
            }
            // 1mm² 고정 크기 모드는 클릭 없이도 커서 따라가는 미리보기 표시
            if (this.drawMode === 'brush') {
                this._drawingCurrent = [sx, sy];
                this.requestRender();
            }
            if (this.drawMode === 'rect-1mm2' || this.drawMode === 'circle-1mm2') {
                this._drawingCurrent = [sx, sy];
                this.requestRender();
            }
            // Ruler — 시작점만 찍힌 상태에선 끝점이 마우스 따라간다 (실시간 길이 미리보기).
            // 수평/수직 ±2° 스냅을 preview 단계에서도 적용해 사용자가 스냅된 길이를 미리 본다.
            if (this.drawMode === 'ruler' && this._rulerStart && !this._rulerFinalized) {
                this._rulerEnd = this._snapRulerEnd(
                    this._rulerStart[0], this._rulerStart[1], sx, sy);
                this.requestRender();
            }

            // 패닝
            if (!this._isPanning) return;
            const dx = e.clientX - this._lastPanX;
            const dy = e.clientY - this._lastPanY;
            this._lastPanX = e.clientX;
            this._lastPanY = e.clientY;
            this.viewCenterX -= dx / this.zoom;
            this.viewCenterY -= dy / this.zoom;
            this._clampView();
            this.requestRender();
            if (this.onViewChange) this.onViewChange();
        });

        window.addEventListener('mouseup', (e) => {
            // Alt+드래그/클릭 종료 처리
            if (this._altPending) {
                const pending = this._altPending;
                this._altPending = null;
                if (this._lassoActive) {
                    this._lassoActive = false;
                    const pts = this._lassoPoints;
                    this._lassoPoints = [];
                    if (pts.length >= 3) {
                        const list_indices = this._findCellsInPolygon(pts);
                        if (list_indices.length > 0) {
                            // 콜백 내부에서 기존 팝업 close가 highlight를 초기화하므로
                            // 팝업을 먼저 연 뒤 새 highlight Set을 설정한다
                            if (this.onCellsMultiEditRequested) {
                                const list_cells = list_indices.map(i => this.detectionCells[i]);
                                this.onCellsMultiEditRequested(list_indices, list_cells, e.clientX, e.clientY);
                            }
                            this._highlightedCellIdx = -1;
                            this._highlightedCellIdxSet = new Set(list_indices);
                        }
                    }
                    this.requestRender();
                } else {
                    // 단일 Alt+클릭: 가장 가까운 셀 편집
                    const hit = this._findNearestCell(pending.sx, pending.sy, 30);
                    if (hit) {
                        if (this.onCellEditRequested) {
                            this.onCellEditRequested(hit.index, hit.cell, pending.clientX, pending.clientY);
                        }
                        this._highlightedCellIdxSet = null;
                        this._highlightedCellIdx = hit.index;
                        this.requestRender();
                    }
                }
                return;
            }

            // Shift+click 종료 — 거의 안 움직였으면 셀 추가 콜백 (드래그면 무시).
            if (this._shiftAddPending) {
                const pending = this._shiftAddPending;
                this._shiftAddPending = null;
                const dx = e.clientX - pending.clientX;
                const dy = e.clientY - pending.clientY;
                if (Math.hypot(dx, dy) <= 4 && this.onCellAddRequested) {
                    this.onCellAddRequested(
                        pending.sx, pending.sy,
                        pending.clientX, pending.clientY,
                    );
                }
                return;
            }

            if (this._vsSplitDragging) {
                this._vsSplitDragging = false;
                this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
                return;
            }
            if (this._dragControlPoint) {
                this._dragControlPoint = null;
                this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
                return;
            }
            if (this._dragAnnotation) {
                this._dragAnnotation = null;
                this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
                return;
            }
            if (this.drawMode && this._isDrawing) {
                const rect = this.canvas.getBoundingClientRect();
                const cx = e.clientX - rect.left;
                const cy = e.clientY - rect.top;
                const [sx, sy] = this.canvasToScene(cx, cy);
                this._onDrawMouseUp(sx, sy);
                return;
            }
            if (this._isPanning) {
                this._isPanning = false;
                this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
            }
        });

        // ── 우클릭: 컨텍스트 메뉴 방지 + 그리기 모드 해제 ──
        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            if (this.drawMode) {
                this.setDrawMode(null);
            }
        });

        // ── 더블클릭: annotation 센터링 ──
        this.canvas.addEventListener('dblclick', (e) => {
            if (!this.drawMode) {
                const rect = this.canvas.getBoundingClientRect();
                const [sx, sy] = this.canvasToScene(e.clientX - rect.left, e.clientY - rect.top);
                const hitAnn = this._hitAnnotation(sx, sy);
                if (hitAnn) this.centerOnAnnotation(hitAnn);
            }
        });

        // ── 키보드 ──
        window.addEventListener('keydown', (e) => {
            if ((e.key === 'Control' || e.key === 'Alt') &&
                    !this._isPanning && !this._dragControlPoint && !this._dragAnnotation &&
                    !this._vsSplitDragging) {
                this.canvas.style.cursor = e.key === 'Alt' ? 'copy' : 'pointer';
                if (e.key === 'Control') this.requestRender();
            }
            if (e.key === 'Escape') {
                if (this._altPending) {
                    this._altPending = null;
                    this._lassoActive = false;
                    this._lassoPoints = [];
                    this.requestRender();
                }
                if (this.drawMode) {
                    this.setDrawMode(null); // 모드 해제
                }
            }
            if (e.key === 'Delete' && this.selectedAnnotationId) {
                this.deleteAnnotation(this.selectedAnnotationId);
            }
            // Shift 누르면 셀 추가 가능 — 십자 커서로 바꿔 클릭 위치를 정확히 보이게.
            // (drawMode/패닝 등 다른 상태가 아닐 때만, 그리고 detectionCells 가 있을 때만.)
            if (e.key === 'Shift' && this.onCellAddRequested && !this.drawMode &&
                    !this._isPanning && this.detectionCells.length > 0) {
                this.canvas.style.cursor = 'crosshair';
            }
        });
        window.addEventListener('keyup', (e) => {
            if (e.key === 'Alt') {
                this._setInsertVertexPreview(null);
            }
            if (e.key === 'Control') {
                this._setMergeHover(null);
            }
            if (e.key === 'Control' || e.key === 'Alt' || e.key === 'Shift') {
                // 다른 cursor 상태 (drawMode/패닝/이동) 가 아니면 grab 으로 복귀.
                if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation &&
                        !this._vsSplitDragging) {
                    this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
                }
            }
        });
        // 창 포커스가 빠진 사이 Shift 가 떼져도 keyup 을 못 받을 수 있어 blur 시 복원.
        window.addEventListener('blur', () => {
            this._setInsertVertexPreview(null);
            if (!this._isPanning && !this._dragControlPoint && !this._dragAnnotation &&
                    !this._vsSplitDragging) {
                this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
            }
        });

        // ── 터치 ──
        let lastTouchDist = 0;
        let lastTouchCenter = null;
        this.canvas.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
                this._isPanning = true;
                this._lastPanX = e.touches[0].clientX;
                this._lastPanY = e.touches[0].clientY;
            } else if (e.touches.length === 2) {
                const dx = e.touches[1].clientX - e.touches[0].clientX;
                const dy = e.touches[1].clientY - e.touches[0].clientY;
                lastTouchDist = Math.sqrt(dx * dx + dy * dy);
                lastTouchCenter = {
                    x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
                    y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
                };
            }
            e.preventDefault();
        }, { passive: false });
        this.canvas.addEventListener('touchmove', (e) => {
            if (e.touches.length === 1 && this._isPanning) {
                const dx = e.touches[0].clientX - this._lastPanX;
                const dy = e.touches[0].clientY - this._lastPanY;
                this._lastPanX = e.touches[0].clientX;
                this._lastPanY = e.touches[0].clientY;
                this.viewCenterX -= dx / this.zoom;
                this.viewCenterY -= dy / this.zoom;
                this._clampView();
                this.requestRender();
            } else if (e.touches.length === 2 && lastTouchDist > 0) {
                const dx = e.touches[1].clientX - e.touches[0].clientX;
                const dy = e.touches[1].clientY - e.touches[0].clientY;
                const dist = Math.sqrt(dx * dx + dy * dy);
                const scale = dist / lastTouchDist;
                const rect = this.canvas.getBoundingClientRect();
                this.setZoom(
                    this.zoom * scale,
                    lastTouchCenter.x - rect.left,
                    lastTouchCenter.y - rect.top
                );
                lastTouchDist = dist;
            }
            e.preventDefault();
        }, { passive: false });
        this.canvas.addEventListener('touchend', () => {
            this._isPanning = false;
            lastTouchDist = 0;
        });

        this.canvas.style.cursor = 'grab';
    }

    _resizeCanvas() {
        const container = this.canvas.parentElement;
        const w = container.clientWidth;
        const h = container.clientHeight;
        const float_dpr = window.devicePixelRatio || 1;
        this._dpr = float_dpr;
        this._viewW = w;
        this._viewH = h;
        // 비트맵을 디바이스 픽셀 해상도로 — 브라우저가 리샘플링 없이 1:1 로 표시
        this.canvas.width = Math.round(w * float_dpr);
        this.canvas.height = Math.round(h * float_dpr);
        this.canvas.style.width = w + 'px';
        this.canvas.style.height = h + 'px';
        this.overlayCanvas.width = Math.round(w * float_dpr);
        this.overlayCanvas.height = Math.round(h * float_dpr);
        this.overlayCanvas.style.width = w + 'px';
        this.overlayCanvas.style.height = h + 'px';
        if (this.slideInfo) {
            this._clampView();
            this.requestRender();
        }
    }

    // ── 렌더링 ──

    requestRender() {
        if (this._renderPending) return;
        this._renderPending = true;
        requestAnimationFrame(() => {
            this._renderPending = false;
            this._render();
        });
    }

    /**
     * child scene 영역을 **덮는 모든 fallback 타일** 을 캐시에서 찾아 리스트로 반환.
     * child 가 parent 격자 경계를 가로지르면 parent 가 최대 2x2 = 4 개 필요.
     * 각 parent 는 child 와 겹치는 부분만 그려지도록 호출자가 clamp 한다.
     *
     * 탐색: **한 level 씩** 차례로 (가까운 stage 먼저), 해당 level 에서 child 를
     * 덮는 parent 들을 수집. 하나라도 cache 에 있으면 그 level 에서 멈춤.
     * (모자란 부분은 더 먼 level 로 떨어지면 섞여 지저분해지므로 그냥 그 level 에서 끝냄)
     */
    _findFallbackTiles(sceneX, sceneY, sceneSize, currentLevel) {
        const list_stages = this._getLevelStages();
        const list_unique = Array.from(new Set(list_stages)).sort((a, b) => a - b);
        const int_idx = list_unique.indexOf(currentLevel);
        const levels = [];
        if (int_idx >= 0) {
            for (let i = int_idx + 1; i < list_unique.length; i++) levels.push(list_unique[i]);
            for (let i = int_idx - 1; i >= 0; i--) levels.push(list_unique[i]);
        } else {
            for (const l of list_unique) if (l !== currentLevel) levels.push(l);
        }

        for (const l of levels) {
            const ds = this._stageDownsample(l);
            const tileScene = TILE_SIZE * ds;
            // child 가 걸치는 parent 타일 격자 범위 (좌상 ~ 우하)
            const int_ptx_min = Math.floor(sceneX / tileScene);
            const int_pty_min = Math.floor(sceneY / tileScene);
            // child 끝에서 살짝 (1e-6) 빼 경계에 걸친 경우 한 칸 더 포함 안 되게
            const int_ptx_max = Math.floor((sceneX + sceneSize - 1e-6) / tileScene);
            const int_pty_max = Math.floor((sceneY + sceneSize - 1e-6) / tileScene);
            const list_hits = [];
            for (let pty = int_pty_min; pty <= int_pty_max; pty++) {
                for (let ptx = int_ptx_min; ptx <= int_ptx_max; ptx++) {
                    const key = `${l}/${ptx}/${pty}`;
                    const img = this._tileCache.get(key);
                    if (img && img.complete && img.naturalWidth > 0) {
                        list_hits.push({
                            img,
                            srcSceneX: ptx * tileScene,
                            srcSceneY: pty * tileScene,
                            srcSceneSize: tileScene,
                            srcPixelSize: TILE_SIZE,
                        });
                    }
                }
            }
            if (list_hits.length > 0) return list_hits;
        }
        return [];
    }

    _render() {
        // 타일 draw 만 identity transform 으로 device pixel 직접 그리기
        // (브라우저별 scale+drawImage 내부 rounding 차이가 격자의 원인).
        // VS overlay 등 기타 CSS 픽셀 기반 코드는 dpr transform 으로 복구 후 실행.
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        if (!this.slideInfo) {
            this.ctx.fillStyle = '#000';
            this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
            return;
        }

        const ctx = this.ctx;
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        ctx.imageSmoothingEnabled = false;

        const effectiveMpp = this.getEffectiveMpp();
        const level = this._getStageLevel(effectiveMpp);
        const downsample = this._stageDownsample(level);
        const [levelW, levelH] = this._stageDimensions(level);

        // 뷰 영역 (scene 좌표)
        const halfVW = this._viewW / this.zoom / 2;
        const halfVH = this._viewH / this.zoom / 2;
        const viewLeft = this.viewCenterX - halfVW;
        const viewTop = this.viewCenterY - halfVH;
        const viewRight = this.viewCenterX + halfVW;
        const viewBottom = this.viewCenterY + halfVH;

        // 타일 범위
        const tileSceneSize = TILE_SIZE * downsample;
        const txMin = Math.max(0, Math.floor(viewLeft / tileSceneSize));
        const tyMin = Math.max(0, Math.floor(viewTop / tileSceneSize));
        const txMax = Math.min(Math.ceil(levelW / TILE_SIZE) - 1, Math.ceil(viewRight / tileSceneSize));
        const tyMax = Math.min(Math.ceil(levelH / TILE_SIZE) - 1, Math.ceil(viewBottom / tileSceneSize));

        // 로드 큐 초기화 (새 프레임마다 현재 뷰 기준으로 재구성)
        // parent / child 분리 — parent 들을 strictly 먼저 다 큐잉한 뒤 child 큐잉.
        // FIFO + MAX_CONCURRENT_LOADS 병렬이라 parent 가 제일 먼저 다 출발해
        // child 보다 빨리 도착할 가능성이 높아진다.
        this._loadQueue = [];
        const list_parent_tasks = [];
        const list_child_tasks = [];
        const set_parent_enqueued = new Set();

        // 현재 stage 의 "바로 위 stage level" — fallback prefetch 대상
        const list_stage_unique = Array.from(new Set(this._getLevelStages())).sort((a, b) => a - b);
        const int_cur_stage_idx = list_stage_unique.indexOf(level);
        const int_parent_stage_level = (int_cur_stage_idx >= 0 && int_cur_stage_idx + 1 < list_stage_unique.length)
            ? list_stage_unique[int_cur_stage_idx + 1]
            : -1;

        // ── Pass 1: 누락된 child 가 있으면 그 영역을 덮을 parent 들을 수집 ──
        // child 마다 parent 를 잘라 그리면 sub-pixel 경계에 격자 artifact 가 생긴다.
        // 대신 parent 는 자기 전체 영역을 **한 번에** 그려, 중복/부분 draw 를 제거한다.
        const map_fallback_parents = new Map(); // key → {img, srcSceneX, srcSceneY, srcSceneSize, srcPixelSize}
        const list_missing_children = []; // {tx, ty, sceneX, sceneY, canvasX, canvasY, canvasSize}
        const list_present_children = []; // {img, canvasX, canvasY, canvasSize, key}
        let bool_any_missing_without_fallback = false;

        for (let ty = tyMin; ty <= tyMax; ty++) {
            for (let tx = txMin; tx <= txMax; tx++) {
                const key = `${level}/${tx}/${ty}`;
                const img = this._tileCache.get(key);

                const sceneX = tx * tileSceneSize;
                const sceneY = ty * tileSceneSize;
                const [canvasX, canvasY] = this.sceneToCanvas(sceneX, sceneY);
                const canvasSize = tileSceneSize * this.zoom;

                if (img && img.complete && img.naturalWidth > 0) {
                    list_present_children.push({ img, canvasX, canvasY, canvasSize, key, sceneX, sceneY });
                    // 아직 페이드 중이면 부모를 아래에 깔아 블랙→타일 블렌딩 깜빡임 방지
                    const float_fs = this._tileFadeStart.get(key);
                    if (float_fs !== undefined && (performance.now() - float_fs) < this._fadeDurationMs) {
                        const list_fbs = this._findFallbackTiles(sceneX, sceneY, tileSceneSize, level);
                        for (const fb of list_fbs) {
                            const str_fb_key = `${fb.srcSceneX}_${fb.srcSceneY}_${fb.srcSceneSize}`;
                            if (!map_fallback_parents.has(str_fb_key)) {
                                map_fallback_parents.set(str_fb_key, fb);
                            }
                        }
                    }
                } else {
                    list_missing_children.push({ tx, ty, sceneX, sceneY, canvasX, canvasY, canvasSize });
                    // 이 child 를 덮는 parent 들을 수집 (중복은 map 이 dedup)
                    const list_fbs = this._findFallbackTiles(sceneX, sceneY, tileSceneSize, level);
                    if (list_fbs.length === 0) {
                        bool_any_missing_without_fallback = true;
                    }
                    for (const fb of list_fbs) {
                        const str_fb_key = `${fb.srcSceneX}_${fb.srcSceneY}_${fb.srcSceneSize}`;
                        if (!map_fallback_parents.has(str_fb_key)) {
                            map_fallback_parents.set(str_fb_key, fb);
                        }
                    }

                    // 바로 위 stage level 부모 타일 프리페치 (parent 큐로 분리).
                    const int_parent_level = int_parent_stage_level;
                    if (int_parent_level >= 0) {
                        const float_parent_ds = this._stageDownsample(int_parent_level);
                        const float_parent_tile_scene = TILE_SIZE * float_parent_ds;
                        const float_cx = sceneX + tileSceneSize / 2;
                        const float_cy = sceneY + tileSceneSize / 2;
                        const int_ptx = Math.floor(float_cx / float_parent_tile_scene);
                        const int_pty = Math.floor(float_cy / float_parent_tile_scene);
                        const str_parent_key = `${int_parent_level}/${int_ptx}/${int_pty}`;
                        if (
                            !set_parent_enqueued.has(str_parent_key) &&
                            !this._tileCache.has(str_parent_key) &&
                            !this._tileLoading.has(str_parent_key)
                        ) {
                            set_parent_enqueued.add(str_parent_key);
                            list_parent_tasks.push({
                                level: int_parent_level,
                                tx: int_ptx,
                                ty: int_pty,
                                key: str_parent_key,
                            });
                        }
                    }

                    // 현재 레벨 child 는 별도 리스트에 모아둔다 — 모든 parent 이후에 큐잉
                    if (!this._tileLoading.has(key)) {
                        list_child_tasks.push({ level, tx, ty, key });
                    }
                }
            }
        }

        // ── device pixel 좌표로 직접 drawImage (transform 미사용) ──
        // CSS px 입력을 device px 정수로 snap. floor(left) + ceil(right) 로 인접 타일
        // 경계가 반드시 공유되거나 겹치게 한다. ceil 은 항상 floor 이상이므로 gap 불가.
        const float_dpr = this._dpr;
        const _drawAligned = (img, sx, sy, sw, sh, dx, dy, dw, dh) => {
            const int_l = Math.floor(dx * float_dpr);
            const int_t = Math.floor(dy * float_dpr);
            const int_r = Math.ceil((dx + dw) * float_dpr);
            const int_b = Math.ceil((dy + dh) * float_dpr);
            const int_w = int_r - int_l;
            const int_h = int_b - int_t;
            if (int_w <= 0 || int_h <= 0) return;
            if (sx == null) {
                ctx.drawImage(img, int_l, int_t, int_w, int_h);
            } else {
                ctx.drawImage(img, sx, sy, sw, sh, int_l, int_t, int_w, int_h);
            }
        };

        // ── Pass 2a: 썸네일 (최후 폴백) 을 뷰 전체에 한 번만 ──
        if (bool_any_missing_without_fallback && this._thumbnailBitmap) {
            const tb = this._thumbnailBitmap;
            const [int_scene_w, int_scene_h] = this.slideInfo.dimensions;
            const [float_thumb_x, float_thumb_y] = this.sceneToCanvas(0, 0);
            _drawAligned(tb, null, null, null, null,
                float_thumb_x, float_thumb_y,
                int_scene_w * this.zoom, int_scene_h * this.zoom);
        }

        // ── Pass 2b: fallback parent 들을 각자 전체 영역에 한 번씩 ──
        for (const fb of map_fallback_parents.values()) {
            const [float_px, float_py] = this.sceneToCanvas(fb.srcSceneX, fb.srcSceneY);
            _drawAligned(fb.img, 0, 0, fb.srcPixelSize, fb.srcPixelSize,
                float_px, float_py,
                fb.srcSceneSize * this.zoom, fb.srcSceneSize * this.zoom);
        }

        // ── Pass 3: 현재 레벨 child 타일 (fade-in) ──
        // 새로 도착한 타일은 alpha 0 → 1 로 램프해 OSD 처럼 레이어가 서서히 올라오게
        // 보이게 한다. 폴백 parent/썸네일은 이미 아래에 깔려있어 빈 공간이 생기지 않는다.
        const float_now_ms = performance.now();
        const float_fade_dur = this._fadeDurationMs;
        let bool_any_fading = false;
        for (const c of list_present_children) {
            this._tileCache.delete(c.key);
            this._tileCache.set(c.key, c.img);
            let float_alpha = 1;
            const float_fade_start = this._tileFadeStart.get(c.key);
            if (float_fade_start !== undefined) {
                const float_elapsed = float_now_ms - float_fade_start;
                if (float_elapsed < float_fade_dur) {
                    float_alpha = float_elapsed / float_fade_dur;
                    bool_any_fading = true;
                } else {
                    this._tileFadeStart.delete(c.key);
                }
            }
            if (float_alpha < 1) {
                ctx.globalAlpha = float_alpha;
                _drawAligned(c.img, null, null, null, null,
                    c.canvasX, c.canvasY, c.canvasSize, c.canvasSize);
                ctx.globalAlpha = 1;
            } else {
                _drawAligned(c.img, null, null, null, null,
                    c.canvasX, c.canvasY, c.canvasSize, c.canvasSize);
            }
        }
        if (bool_any_fading) {
            this.requestRender();
        }

        // 부모 stage 타일을 먼저, 그 다음 현재 레벨 child 타일을 큐에 넣는다.
        // parent 들이 먼저 모두 출발해 child 보다 빠르게 도착,
        // fallback 으로 즉시 사용 가능해진다.
        // child 는 뷰포트 중심에서 가까운 순으로 정렬 — 사용자가 보는 영역이 먼저 로딩.
        const float_center_tx = (txMin + txMax) / 2;
        const float_center_ty = (tyMin + tyMax) / 2;
        list_child_tasks.sort((a, b) => {
            const float_da = (a.tx - float_center_tx) ** 2 + (a.ty - float_center_ty) ** 2;
            const float_db = (b.tx - float_center_tx) ** 2 + (b.ty - float_center_ty) ** 2;
            return float_da - float_db;
        });
        for (const t of list_parent_tasks) this._loadQueue.push(t);
        for (const t of list_child_tasks) this._loadQueue.push(t);

        // 큐에 있는 타일 로딩 시작
        this._processLoadQueue();

        // 여기서부터 CSS 픽셀 기반 코드 — dpr transform 복구
        ctx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);

        // Virtual Stain 오버레이 (메인 캔버스 위에 직접 그림 — 슬라이드를 가림)
        this._renderVirtualStainOverlay(ctx);

        // 오버레이 렌더링 — device pixel 좌표계, dpr scale 로 annotation 그리기
        this.overlayCtx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
        this.overlayCtx.clearRect(0, 0, this._viewW, this._viewH);
        // 주의: annotation/detection 렌더러들은 CSS 픽셀 기준으로 그린다.
        this._renderDetectionOverlay();
        this._renderAnnotations(this.overlayCtx);
    }

    _renderVirtualStainOverlay(ctx) {
        const ov = this._vsOverlay;
        if (!ov || !this._vsVisible) return;
        if (!ov.levels || ov.levels.length === 0) return;

        const canvasW = this._viewW;
        const canvasH = this._viewH;

        // 오버레이 전체 → 캔버스 매핑
        const [cx, cy] = this.sceneToCanvas(ov.originX, ov.originY);
        const cw = ov.sceneW * this.zoom;
        const ch = ov.sceneH * this.zoom;

        // 가시 교집합
        const dx0 = Math.max(0, cx);
        const dy0 = Math.max(0, cy);
        const dx1 = Math.min(canvasW, cx + cw);
        const dy1 = Math.min(canvasH, cy + ch);
        const overlayVisible = (dx1 > dx0 && dy1 > dy0);
        if (!overlayVisible && !this._vsSplitMode) return;

        // ── 레벨 선택: level width 가 화면상 오버레이 폭보다 아주 조금 작거나 같은 것 중 가장 낮은 해상도 ──
        // 화면에 그려질 VS 폭(픽셀)과 각 레벨 이미지 폭을 비교
        let chosenL = 0;
        for (let L = 0; L < ov.levels.length; L++) {
            if (ov.levels[L].width >= cw * 0.8) chosenL = L;
            else break;
        }
        const lvl = ov.levels[chosenL];
        const scaleX = ov.sceneW / lvl.width;    // scene px per level-pixel

        // 업샘플(zoom 이 큼)이면 스무딩 off, 다운샘플이면 low 품질
        const screenPerLvlPx = this.zoom * scaleX;
        if (screenPerLvlPx > 1) {
            ctx.imageSmoothingEnabled = false;
        } else {
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = 'low';
        }

        // 가시 scene 영역
        const [vsx0, vsy0] = this.canvasToScene(0, 0);
        const [vsx1, vsy1] = this.canvasToScene(canvasW, canvasH);
        const xlo = Math.max(ov.originX, vsx0);
        const ylo = Math.max(ov.originY, vsy0);
        const xhi = Math.min(ov.originX + ov.sceneW, vsx1);
        const yhi = Math.min(ov.originY + ov.sceneH, vsy1);
        if (xhi <= xlo || yhi <= ylo) {
            // 오버레이가 가시영역 밖 — split 분할선만 그리고 끝 (아래서 처리)
            if (!this._vsSplitMode) return;
        }

        const TS = ov.tileSize || 512;

        // 특정 레벨의 가시 타일을 draw (요청/로드 분리 옵션 포함)
        // requestMissing: true 면 캐시 miss 시 _getVsTile 로 백그라운드 로드 트리거
        //                 false 면 이미 캐시된 타일만 그림 (fallback 용)
        const drawLevel = (L, requestMissing) => {
            const lv = ov.levels[L];
            const sX = ov.sceneW / lv.width;
            const sY = ov.sceneH / lv.height;
            const tW = TS * sX;
            const tH = TS * sY;
            const a = Math.max(0, Math.floor((xlo - ov.originX) / tW));
            const b = Math.max(0, Math.floor((ylo - ov.originY) / tH));
            const c = Math.min(lv.nx - 1, Math.floor((xhi - ov.originX - 1e-6) / tW));
            const d = Math.min(lv.ny - 1, Math.floor((yhi - ov.originY - 1e-6) / tH));
            for (let ty = b; ty <= d; ty++) {
                for (let tx = a; tx <= c; tx++) {
                    const img = requestMissing
                        ? this._getVsTile(L, tx, ty)
                        : this._peekVsTile(L, tx, ty);
                    if (!img) continue;
                    const tileLvlW = Math.min(TS, lv.width - tx * TS);
                    const tileLvlH = Math.min(TS, lv.height - ty * TS);
                    const sceneX = ov.originX + tx * tW;
                    const sceneY = ov.originY + ty * tH;
                    const [tcx, tcy] = this.sceneToCanvas(sceneX, sceneY);
                    const dw = tileLvlW * sX * this.zoom;
                    const dh = tileLvlH * sY * this.zoom;
                    ctx.drawImage(img, tcx, tcy, dw, dh);
                }
            }
        };

        // ROI 폴리곤 클립
        const roiPolys = ov.roiPolygons;
        const drawWithRoiClip = (drawFn) => {
            if (!roiPolys || roiPolys.length === 0) {
                drawFn();
                return;
            }
            ctx.save();
            ctx.beginPath();
            for (const poly of roiPolys) {
                if (!poly || poly.length < 3) continue;
                const [px0, py0] = this.sceneToCanvas(poly[0][0], poly[0][1]);
                ctx.moveTo(px0, py0);
                for (let i = 1; i < poly.length; i++) {
                    const [pxi, pyi] = this.sceneToCanvas(poly[i][0], poly[i][1]);
                    ctx.lineTo(pxi, pyi);
                }
                ctx.closePath();
            }
            ctx.clip();
            drawFn();
            ctx.restore();
        };

        // drawTiles: 저해상도 레벨 → 선택 레벨 → 더 고해상도 (캐시된 것만) 순으로 레이어링
        //   1) 가장 깊은 레벨(최저해상도)을 배경으로 깔아 빈 영역 제거 (blur pad)
        //   2) 선택 레벨을 덧그림 (로드 트리거)
        //   3) 선택 레벨보다 더 고해상도 (L-1, L-2...) 중 이미 캐시된 타일이 있으면 덧그림
        //      (줌아웃 직후 이전 고해상도 타일이 남아있어 선명도 유지)
        const drawTiles = () => {
            const bgL = ov.levels.length - 1;
            if (bgL !== chosenL) {
                drawLevel(bgL, true);  // 저해상도는 항상 요청 → 거의 항상 캐시됨
            }
            drawLevel(chosenL, true);
            for (let L = chosenL - 1; L >= 0; L--) {
                drawLevel(L, false);  // 더 고해상도는 캐시된 것만 추가로 덧그림
            }
        };

        if (this._vsSplitMode) {
            const splitX = Math.round(canvasW * this._vsSplitFrac);
            if (overlayVisible && xhi > xlo && yhi > ylo) {
                ctx.save();
                ctx.beginPath();
                ctx.rect(splitX, 0, canvasW - splitX, canvasH);
                ctx.clip();
                drawWithRoiClip(drawTiles);
                ctx.restore();
            }

            // 분할선 + 핸들 + 라벨
            ctx.save();
            // 그림자 라인 (가독성)
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.moveTo(splitX, 0);
            ctx.lineTo(splitX, canvasH);
            ctx.stroke();
            // 흰색 라인
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(splitX, 0);
            ctx.lineTo(splitX, canvasH);
            ctx.stroke();

            // 가운데 드래그 핸들 (원형 + 좌우 화살표)
            const handleY = canvasH / 2;
            const handleR = 14;
            ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(splitX, handleY, handleR, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            // 좌우 화살표
            ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
            ctx.beginPath();
            ctx.moveTo(splitX - 7, handleY);
            ctx.lineTo(splitX - 2, handleY - 5);
            ctx.lineTo(splitX - 2, handleY + 5);
            ctx.closePath();
            ctx.fill();
            ctx.beginPath();
            ctx.moveTo(splitX + 7, handleY);
            ctx.lineTo(splitX + 2, handleY - 5);
            ctx.lineTo(splitX + 2, handleY + 5);
            ctx.closePath();
            ctx.fill();

            ctx.font = 'bold 12px sans-serif';
            ctx.textBaseline = 'top';
            const padX = 8, padY = 6;
            const labelL = 'IHC (original)';
            const labelR = 'Virtual H&E';
            const mL = ctx.measureText(labelL);
            const mR = ctx.measureText(labelR);
            const bh = 18;
            // 좌측 라벨
            ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.fillRect(padX, padY, mL.width + 12, bh);
            ctx.fillStyle = '#fff';
            ctx.fillText(labelL, padX + 6, padY + 3);
            // 우측 라벨
            ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.fillRect(canvasW - mR.width - padX - 12, padY, mR.width + 12, bh);
            ctx.fillStyle = '#fff';
            ctx.fillText(labelR, canvasW - mR.width - padX - 6, padY + 3);
            ctx.restore();
        } else {
            if (overlayVisible && xhi > xlo && yhi > ylo) {
                drawWithRoiClip(drawTiles);
            }
        }
    }

    /**
     * VS 타일 캐시 조회만 (로드 트리거 없음). 폴백 드로우용.
     */
    _peekVsTile(level, tx, ty) {
        const key = `${level}/${tx}/${ty}`;
        if (this._vsTileCache.has(key)) {
            const img = this._vsTileCache.get(key);
            // LRU touch
            this._vsTileCache.delete(key);
            this._vsTileCache.set(key, img);
            return img;
        }
        return null;
    }

    /**
     * VS 타일 반환 (LRU 캐시 + 큐 기반 비동기 로드).
     * 없으면 null 리턴하고 큐에 넣어 순차 로드 후 재렌더.
     */
    _getVsTile(level, tx, ty) {
        const key = `${level}/${tx}/${ty}`;
        // LRU touch
        if (this._vsTileCache.has(key)) {
            const img = this._vsTileCache.get(key);
            this._vsTileCache.delete(key);
            this._vsTileCache.set(key, img);
            return img;
        }
        if (this._vsTileMissing.has(key)) return null;
        if (this._vsTileLoading.has(key)) return null;

        const ov = this._vsOverlay;
        if (!ov) return null;

        // 큐에 추가하고 큐 처리 시작
        this._vsTileLoading.add(key);
        this._vsLoadQueue.push({ key, level, tx, ty, ov });
        this._processVsLoadQueue();
        return null;
    }

    _processVsLoadQueue() {
        while (this._vsLoadQueue.length > 0) {
            const task = this._vsLoadQueue.shift();
            this._vsActiveLoads++;

            const img = new Image();
            img.onload = () => {
                this._vsActiveLoads--;
                this._vsTileLoading.delete(task.key);
                // 로드 도중 overlay 가 바뀌었으면 버림
                if (this._vsOverlay !== task.ov) return;
                // LRU 제거
                if (this._vsTileCache.size >= this._vsMaxTiles) {
                    const oldest = this._vsTileCache.keys().next().value;
                    this._vsTileCache.delete(oldest);
                }
                this._vsTileCache.set(task.key, img);
                this.requestRender();
            };
            img.onerror = () => {
                this._vsActiveLoads--;
                this._vsTileLoading.delete(task.key);
                this._vsTileMissing.add(task.key);
            };
            img.src = api.virtualStainTileUrl(
                task.ov.slideId, task.ov.stainType, task.ov.targetMpp,
                task.level, task.tx, task.ty
            );
        }
    }

    setVirtualStainSplitMode(enabled) {
        this._vsSplitMode = !!enabled;
        // split mode에선 항상 overlay가 보여야 의미가 있음
        if (this._vsSplitMode) this._vsVisible = true;
        if (!this._vsSplitMode) {
            this._vsSplitDragging = false;
            this.canvas.style.cursor = this.drawMode ? 'crosshair' : 'grab';
        }
        this.requestRender();
    }

    // ── 타일 로딩 (병렬, 큐 기반) ──

    _processLoadQueue() {
        while (this._loadQueue.length > 0 && this._activeLoads < MAX_CONCURRENT_LOADS) {
            const task = this._loadQueue.shift();
            this._loadTile(task.level, task.tx, task.ty);
        }
    }

    _loadTile(level, tx, ty) {
        const key = `${level}/${tx}/${ty}`;
        if (this._tileLoading.has(key) || this._tileCache.has(key)) return;

        this._tileLoading.add(key);
        this._activeLoads++;

        // 이 로드가 시작된 시점의 generation — 슬라이드 전환되면 이 콜백 무시
        const int_gen = this._loadGeneration;
        const img = new Image();
        this._inflightImages.add(img);
        img.onload = () => {
            this._inflightImages.delete(img);
            this._tileLoading.delete(key);
            this._activeLoads--;
            // 슬라이드가 바뀐 뒤 도착한 응답은 폐기 (이전 슬라이드 픽셀이 새 cache 에
            // 같은 키로 박히는 contamination 차단)
            if (int_gen !== this._loadGeneration) {
                this._processLoadQueue();
                return;
            }
            this._putCache(key, img);
            this._tileFadeStart.set(key, performance.now());
            this._markPreloadTileDone(key);
            this._processLoadQueue();
            this.requestRender();
        };
        img.onerror = () => {
            this._inflightImages.delete(img);
            this._tileLoading.delete(key);
            this._activeLoads--;
            // 실패도 "완료" 로 간주해야 로딩창이 영원히 멈추지 않음
            this._markPreloadTileDone(key);
            this._processLoadQueue();
        };
        img.src = api.tileUrl(this.slideId, level, tx, ty, this._colorCorrectionEnabled);
    }

    _putCache(key, img) {
        // LRU 제거
        if (this._tileCache.size >= this._maxCacheTiles) {
            // 가장 오래된 (Map 첫 번째) 항목 제거
            const oldest = this._tileCache.keys().next().value;
            this._tileCache.delete(oldest);
            this._tileFadeStart.delete(oldest);
        }
        this._tileCache.set(key, img);
    }

    /**
     * NDP 색보정 ON/OFF. Hamamatsu 슬라이드 뷰어의 toggle 버튼에서 호출.
     *
     * 이 토글이 바뀌면 타일/썸네일 URL 이 바뀌므로 (서버가 /ndp/ 경로에서 보정본
     * JPEG 을 디스크 캐시로 반환) 현재 캐시를 비우고 재로드를 트리거한다. 첫 전환
     * 시엔 서버가 보정 타일을 생성하느라 약간 느리지만, 그 이후엔 브라우저
     * HTTP 캐시 + 서버 디스크 캐시 둘 다 활용되어 즉답 수준이 된다.
     */
    setColorCorrectionEnabled(bool_enabled) {
        bool_enabled = !!bool_enabled;
        if (this._colorCorrectionEnabled === bool_enabled) return;
        this._colorCorrectionEnabled = bool_enabled;
        // 이전 URL 로 받은 타일/썸네일은 전부 버리고 현재 flag 기준으로 재로드
        this._loadGeneration++;
        for (const img of this._inflightImages) {
            try { img.onload = null; img.onerror = null; img.src = ''; } catch (e) {}
        }
        this._inflightImages.clear();
        this._tileCache.clear();
        this._tileLoading.clear();
        this._tileFadeStart.clear();
        this._loadQueue = [];
        this._activeLoads = 0;
        this._thumbnailBitmap = null;
        this._loadThumbnailFallback();
        this.requestRender();
    }

    /** 타일 캐시 비우고 다시 렌더 (타일 생성 완료 후 호출) */
    clearCacheAndRender() {
        this._tileCache.clear();
        this._tileLoading.clear();
        this._tileFadeStart.clear();
        this._loadQueue = [];
        this._activeLoads = 0;
        this.requestRender();
    }

    // ── 검출 오버레이 ──

    setDetectionResults(cells, roiPolygons = null) {
        let filtered = cells || [];

        // ROI 폴리곤이 있으면 폴리곤 내부 셀만 필터링
        if (roiPolygons && roiPolygons.length > 0) {
            filtered = filtered.filter(c =>
                roiPolygons.some(poly => this._pointInPolygon(c.x, c.y, poly))
            );
        }

        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._undoStack = [];
        this._redoStack = [];
        this.detectionCells = filtered;
        this.classVisibility = {};
        this.classConfidence = {};
        const defConf = this.defaultConfidence ?? 0.01;
        const classIds = new Set(filtered.map(c => c.class_id));
        classIds.forEach(id => {
            this.classVisibility[id] = true;
            this.classConfidence[id] = defConf;
        });

        // 공간 인덱스 구축 (뷰포트 영역만 O(1) 조회용)
        this._spatialGrid = new SpatialGrid(2048);
        this._spatialGrid.build(filtered);

        this._heatmapDirty = true;
        this._heatmapImage = null;
        this._buildHeatmapCache();
        this.requestRender();
    }

    // ── Cell editing (Alt+Click) ──

    /**
     * 클릭 위치(WSI 좌표)에서 가장 가까운 셀 찾기.
     * @param {number} sx WSI x
     * @param {number} sy WSI y
     * @param {number} maxScreenPx 화면 픽셀 기준 최대 거리
     * @returns {{index, cell}|null}
     */
    _findNearestCell(sx, sy, maxScreenPx = 30) {
        if (!this.detectionCells.length) return null;
        const maxDistWsi = this.zoom > 0 ? maxScreenPx / this.zoom : maxScreenPx;
        const r = maxDistWsi;

        // SpatialGrid로 후보 좁히기
        let candidates;
        if (this._spatialGrid) {
            const cellsInBox = this._spatialGrid.query(sx - r, sy - r, sx + r, sy + r);
            // SpatialGrid는 cell 객체만 반환 → 원본 인덱스 매핑
            candidates = cellsInBox.map(c => ({ cell: c, index: this.detectionCells.indexOf(c) }));
        } else {
            candidates = this.detectionCells.map((c, i) => ({ cell: c, index: i }));
        }

        let bestIdx = -1;
        let bestCell = null;
        let bestDist = Infinity;
        for (const { cell, index } of candidates) {
            // visibility/confidence 필터 (편집 대상은 화면에 보이는 셀만)
            if (this.classVisibility[cell.class_id] === false) continue;
            const thresh = this.classConfidence[cell.class_id] ?? 0.01;
            if ((cell.confidence ?? 1.0) < thresh) continue;

            const dx = cell.x - sx;
            const dy = cell.y - sy;
            const d = Math.hypot(dx, dy);
            if (d < bestDist) {
                bestDist = d;
                bestIdx = index;
                bestCell = cell;
            }
        }

        if (bestIdx >= 0 && bestDist <= maxDistWsi) {
            return { index: bestIdx, cell: bestCell };
        }
        return null;
    }

    /** Ray-casting point-in-polygon (scene 좌표) */
    _pointInPolygon(x, y, poly) {
        let inside = false;
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
            const xi = poly[i][0], yi = poly[i][1];
            const xj = poly[j][0], yj = poly[j][1];
            const intersect = ((yi > y) !== (yj > y)) &&
                (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    /** 라쏘 폴리곤 내부에 포함되는 셀들의 인덱스 리스트 (visibility/confidence 필터 적용) */
    _findCellsInPolygon(poly) {
        if (!this.detectionCells.length || poly.length < 3) return [];
        let xMin = Infinity, yMin = Infinity, xMax = -Infinity, yMax = -Infinity;
        for (const [x, y] of poly) {
            if (x < xMin) xMin = x;
            if (x > xMax) xMax = x;
            if (y < yMin) yMin = y;
            if (y > yMax) yMax = y;
        }

        let candidates;
        if (this._spatialGrid) {
            const cellsInBox = this._spatialGrid.query(xMin, yMin, xMax, yMax);
            candidates = cellsInBox.map(c => ({ cell: c, index: this.detectionCells.indexOf(c) }));
        } else {
            candidates = this.detectionCells.map((c, i) => ({ cell: c, index: i }));
        }

        const list_result = [];
        for (const { cell, index } of candidates) {
            if (index < 0) continue;
            if (this.classVisibility[cell.class_id] === false) continue;
            const thresh = this.classConfidence[cell.class_id] ?? 0.01;
            if ((cell.confidence ?? 1.0) < thresh) continue;
            if (this._pointInPolygon(cell.x, cell.y, poly)) {
                list_result.push(index);
            }
        }
        return list_result;
    }

    _pushUndoOp(op) {
        this._undoStack.push(op);
        if (this._undoStack.length > this._maxUndo) this._undoStack.shift();
        this._redoStack = [];
    }

    deleteCell(cellIdx) {
        if (cellIdx < 0 || cellIdx >= this.detectionCells.length) return;
        this._pushUndoOp({
            type: 'delete',
            items: [{ index: cellIdx, cell: this.detectionCells[cellIdx] }],
        });
        this.detectionCells.splice(cellIdx, 1);
        this._highlightedCellIdx = -1;
        this._refreshAfterCellEdit();
    }

    changeCellClass(cellIdx, newClassId, newClassName = null) {
        if (cellIdx < 0 || cellIdx >= this.detectionCells.length) return;
        const c = this.detectionCells[cellIdx];
        this._pushUndoOp({
            type: 'changeClass',
            items: [{
                index: cellIdx,
                oldClassId: c.class_id,
                oldClassName: c.class_name,
                newClassId,
                newClassName,
            }],
        });
        c.class_id = newClassId;
        if (newClassName) c.class_name = newClassName;
        this._refreshAfterCellEdit();
    }

    /**
     * 새 셀을 detectionCells 끝에 추가 — Shift+click UX 용.
     * confidence 는 1.0 (사용자가 수동으로 추가했으니 max). undo/redo 지원.
     * highlight 는 적용 안 함 — 연속 추가 시 이전 셀이 선택 표시로 덮여 보기 힘들기 때문.
     * 반환: 추가된 셀 객체.
     */
    addCell(sx, sy, classId, className = null) {
        const cell = {
            x: Number(sx),
            y: Number(sy),
            class_id: Number(classId),
            class_name: className || `Class ${classId}`,
            confidence: 1.0,
        };
        const int_index = this.detectionCells.length;
        this._pushUndoOp({
            type: 'add',
            items: [{ index: int_index, cell }],
        });
        this.detectionCells.push(cell);
        // 기존 highlight 가 남아 있을 수 있으므로 명시적으로 해제.
        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._refreshAfterCellEdit();
        return cell;
    }

    /** 여러 셀 일괄 삭제 */
    deleteCells(listIndices) {
        if (!listIndices || listIndices.length === 0) return;
        const list_valid = listIndices
            .filter(i => i >= 0 && i < this.detectionCells.length)
            .sort((a, b) => a - b);
        if (list_valid.length === 0) return;
        this._pushUndoOp({
            type: 'delete',
            items: list_valid.map(i => ({ index: i, cell: this.detectionCells[i] })),
        });
        const set_remove = new Set(list_valid);
        this.detectionCells = this.detectionCells.filter((_, i) => !set_remove.has(i));
        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._refreshAfterCellEdit();
    }

    /** 여러 셀 일괄 클래스 변경 */
    changeCellsClass(listIndices, newClassId, newClassName = null) {
        if (!listIndices || listIndices.length === 0) return;
        const list_items = [];
        for (const i of listIndices) {
            if (i < 0 || i >= this.detectionCells.length) continue;
            const c = this.detectionCells[i];
            list_items.push({
                index: i,
                oldClassId: c.class_id,
                oldClassName: c.class_name,
                newClassId,
                newClassName,
            });
        }
        if (list_items.length === 0) return;
        this._pushUndoOp({ type: 'changeClass', items: list_items });
        for (const it of list_items) {
            const c = this.detectionCells[it.index];
            c.class_id = newClassId;
            if (newClassName) c.class_name = newClassName;
        }
        this._highlightedCellIdxSet = null;
        this._refreshAfterCellEdit();
    }

    /** 직전 셀 편집 되돌리기 */
    undoCellEdit() {
        const op = this._undoStack.pop();
        if (!op) return false;
        if (op.type === 'delete') {
            const sorted = [...op.items].sort((a, b) => a.index - b.index);
            for (const { index, cell } of sorted) {
                const clamped = Math.max(0, Math.min(index, this.detectionCells.length));
                this.detectionCells.splice(clamped, 0, cell);
            }
        } else if (op.type === 'changeClass') {
            for (const it of op.items) {
                if (it.index < 0 || it.index >= this.detectionCells.length) continue;
                const c = this.detectionCells[it.index];
                c.class_id = it.oldClassId;
                c.class_name = it.oldClassName;
            }
        } else if (op.type === 'add') {
            // 추가의 역연산 = 큰 인덱스부터 splice (인덱스 시프트 방지).
            const sortedDesc = [...op.items].sort((a, b) => b.index - a.index);
            for (const { index } of sortedDesc) {
                if (index < 0 || index >= this.detectionCells.length) continue;
                this.detectionCells.splice(index, 1);
            }
        }
        this._redoStack.push(op);
        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._refreshAfterCellEdit();
        return true;
    }

    /** 직전 undo 복구 */
    redoCellEdit() {
        const op = this._redoStack.pop();
        if (!op) return false;
        if (op.type === 'delete') {
            const sortedDesc = [...op.items].sort((a, b) => b.index - a.index);
            for (const { index } of sortedDesc) {
                if (index < 0 || index >= this.detectionCells.length) continue;
                this.detectionCells.splice(index, 1);
            }
        } else if (op.type === 'changeClass') {
            for (const it of op.items) {
                if (it.index < 0 || it.index >= this.detectionCells.length) continue;
                const c = this.detectionCells[it.index];
                c.class_id = it.newClassId;
                c.class_name = it.newClassName;
            }
        } else if (op.type === 'add') {
            const sortedAsc = [...op.items].sort((a, b) => a.index - b.index);
            for (const { index, cell } of sortedAsc) {
                const clamped = Math.max(0, Math.min(index, this.detectionCells.length));
                this.detectionCells.splice(clamped, 0, cell);
            }
        }
        this._undoStack.push(op);
        this._highlightedCellIdx = -1;
        this._highlightedCellIdxSet = null;
        this._refreshAfterCellEdit();
        return true;
    }

    canUndoCellEdit() { return this._undoStack.length > 0; }
    canRedoCellEdit() { return this._redoStack.length > 0; }

    clearMultiCellHighlight() {
        if (this._highlightedCellIdxSet) {
            this._highlightedCellIdxSet = null;
            this.requestRender();
        }
    }

    _cloneAnnotationList(list = this.annotations) {
        return list.map(ann => ({
            ...ann,
            coordinates: (ann.coordinates || []).map(p => [Number(p[0]), Number(p[1])]),
            color: Array.isArray(ann.color) ? [...ann.color] : ann.color,
            properties: ann.properties ? { ...ann.properties } : {},
        }));
    }

    _captureAnnotationState() {
        return {
            annotations: this._cloneAnnotationList(this.annotations),
            selectedAnnotationId: this.selectedAnnotationId,
            annotationCounter: this._annotationCounter,
        };
    }

    _restoreAnnotationState(state) {
        if (!state) return false;
        this.annotations = this._cloneAnnotationList(state.annotations || []);
        this.selectedAnnotationId = state.selectedAnnotationId || null;
        this._annotationCounter = Number(state.annotationCounter || this.annotations.length || 0);
        this.annotations.forEach(a => { a.selected = a.id === this.selectedAnnotationId; });
        if (!this.annotations.some(a => a.id === this.selectedAnnotationId)) {
            this.selectedAnnotationId = null;
            this.annotations.forEach(a => { a.selected = false; });
        }
        if (this.onAnnotationSelected) {
            this.onAnnotationSelected(this.annotations.find(a => a.id === this.selectedAnnotationId) || null);
        }
        this.requestRender();
        return true;
    }

    pushAnnotationUndo() {
        this._annotationUndoStack.push(this._captureAnnotationState());
        if (this._annotationUndoStack.length > this._maxAnnotationUndo) this._annotationUndoStack.shift();
        this._annotationRedoStack = [];
    }

    clearAnnotationUndo() {
        this._annotationUndoStack = [];
        this._annotationRedoStack = [];
    }

    undoAnnotationEdit() {
        const prev = this._annotationUndoStack.pop();
        if (!prev) return false;
        this._annotationRedoStack.push(this._captureAnnotationState());
        return this._restoreAnnotationState(prev);
    }

    redoAnnotationEdit() {
        const next = this._annotationRedoStack.pop();
        if (!next) return false;
        this._annotationUndoStack.push(this._captureAnnotationState());
        return this._restoreAnnotationState(next);
    }

    canUndoAnnotationEdit() { return this._annotationUndoStack.length > 0; }
    canRedoAnnotationEdit() { return this._annotationRedoStack.length > 0; }

    clearCellHighlight() {
        if (this._highlightedCellIdx !== -1) {
            this._highlightedCellIdx = -1;
            this.requestRender();
        }
    }

    _refreshAfterCellEdit() {
        // 새 클래스가 처음 등장할 수 있음
        const cls = new Set(this.detectionCells.map(c => c.class_id));
        cls.forEach(id => {
            if (this.classVisibility[id] === undefined) this.classVisibility[id] = true;
            if (this.classConfidence[id] === undefined) this.classConfidence[id] = this.defaultConfidence ?? 0.01;
        });

        // 공간 인덱스 + 히트맵 캐시 재구축
        this._spatialGrid = new SpatialGrid(2048);
        this._spatialGrid.build(this.detectionCells);
        this._heatmapDirty = true;
        this._heatmapImage = null;
        this._buildHeatmapCache();
        this.requestRender();

        if (this.onCellEdited) this.onCellEdited();
    }

    /**
     * 클래스별 density 그리드 사전 계산 (기존 TiledDetectionOverlay._build_heatmap_cache)
     * 종횡비 유지한 2048 해상도 그리드에 histogram2d
     * confidence 필터링은 클래스별로 적용
     */
    /**
     * 클래스별 density 그리드 사전 계산 — setDetectionResults 시 1회만 실행
     * 데스크톱과 동일: confidence 필터 없이 전체 셀로 density 빌드
     * confidence/visibility 필터링은 렌더 시 클래스 단위로 적용 (재빌드 불필요)
     */
    _buildHeatmapCache() {
        this._heatmapCache = null;
        if (!this.detectionCells.length || !this.slideInfo) return;

        // 셀 범위 계산
        let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
        for (const c of this.detectionCells) {
            if (c.x < xMin) xMin = c.x;
            if (c.x > xMax) xMax = c.x;
            if (c.y < yMin) yMin = c.y;
            if (c.y > yMax) yMax = c.y;
        }
        const spanW = Math.max(xMax - xMin, 1);
        const spanH = Math.max(yMax - yMin, 1);

        const GRID_SIZE = 2048;
        let gw, gh;
        if (spanW >= spanH) {
            gw = GRID_SIZE;
            gh = Math.max(1, Math.round(GRID_SIZE * spanH / spanW));
        } else {
            gh = GRID_SIZE;
            gw = Math.max(1, Math.round(GRID_SIZE * spanW / spanH));
        }

        const sx = gw / spanW;
        const sy = gh / spanH;

        // 클래스별 density 그리드 (confidence 필터 적용)
        const clsDensities = {};
        for (const cell of this.detectionCells) {
            const cls = cell.class_id;
            const threshold = this.classConfidence[cls] ?? 0.01;
            if (cell.confidence < threshold) continue;

            if (!clsDensities[cls]) {
                clsDensities[cls] = new Float32Array(gh * gw);
            }
            const col = Math.min(Math.floor((cell.x - xMin) * sx), gw - 1);
            const row = Math.min(Math.floor((cell.y - yMin) * sy), gh - 1);
            if (col >= 0 && row >= 0) {
                clsDensities[cls][row * gw + col]++;
            }
        }

        this._heatmapCache = { clsDensities, xMin, yMin, xMax, yMax, gw, gh, sx, sy };
        this._heatmapDirty = false;
    }

    /**
     * 가우시안 블러 (5x5 box blur 반복으로 근사)
     * 데스크톱: cv2.GaussianBlur(sigma = max(3.0, w/60)) ≈ sigma 8~9
     * 5x5 box blur × passes 회 → sigma ≈ sqrt(passes * 2) 에 근사
     * passes=18 → sigma ≈ 6, passes=32 → sigma ≈ 8
     */
    _blurGrid(src, w, h, passes) {
        let a = new Float32Array(src);
        let b = new Float32Array(w * h);
        for (let p = 0; p < passes; p++) {
            // 수평 5-tap 블러: [1,2,3,2,1]/9 가중 근사 → 균등 5-tap
            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const x0 = Math.max(0, x - 2);
                    const x1 = Math.max(0, x - 1);
                    const x3 = Math.min(w - 1, x + 1);
                    const x4 = Math.min(w - 1, x + 2);
                    const row = y * w;
                    b[row + x] = (a[row + x0] + a[row + x1] + a[row + x] + a[row + x3] + a[row + x4]) / 5;
                }
            }
            // 수직 5-tap 블러
            for (let y = 0; y < h; y++) {
                const y0 = Math.max(0, y - 2) * w;
                const y1 = Math.max(0, y - 1) * w;
                const yc = y * w;
                const y3 = Math.min(h - 1, y + 1) * w;
                const y4 = Math.min(h - 1, y + 2) * w;
                for (let x = 0; x < w; x++) {
                    a[yc + x] = (b[y0 + x] + b[y1 + x] + b[yc + x] + b[y3 + x] + b[y4 + x]) / 5;
                }
            }
        }
        return a;
    }

    /** jet 컬러맵: 0~1 → [r, g, b] */
    _jetColor(t) {
        t = Math.max(0, Math.min(1, t));
        let r, g, b;
        if (t < 0.25) { r = 0; g = t * 4; b = 1; }
        else if (t < 0.5) { r = 0; g = 1; b = 1 - (t - 0.25) * 4; }
        else if (t < 0.75) { r = (t - 0.5) * 4; g = 1; b = 0; }
        else { r = 1; g = 1 - (t - 0.75) * 4; b = 0; }
        return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
    }

    // ── Segmentation 오버레이 (데스크톱 wsi_view_widget.py 동일) ──
    // 색상: Stroma=빨강, Non_Tumor=초록, Tumor=파랑, alpha=128

    /**
     * Segmentation 마스크 설정
     * @param {Uint8Array} maskData - 클래스 인덱스 배열 (0=BG, 1=Stroma, 2=Non_Tumor, 3=Tumor)
     * @param {number} maskW - 마스크 너비
     * @param {number} maskH - 마스크 높이
     * @param {number} sceneX - WSI level-0 offset X
     * @param {number} sceneY - WSI level-0 offset Y
     * @param {number} sceneW - WSI level-0 영역 너비
     * @param {number} sceneH - WSI level-0 영역 높이
     * @param {string[]} classNames - ['Stroma', 'Non_Tumor', 'Tumor']
     */
    setSegmentationOverlay(maskData, maskW, maskH, sceneX, sceneY, sceneW, sceneH, classNames) {
        // 데스크톱과 동일한 색상: Stroma=빨강, Non_Tumor=초록, Tumor=파랑
        const SEG_COLORS = {
            1: [255, 0, 0, 128],    // Stroma
            2: [0, 255, 0, 128],    // Non_Tumor
            3: [0, 0, 255, 128],    // Tumor
        };

        // RGBA ImageData 생성
        const offscreen = new OffscreenCanvas(maskW, maskH);
        const offCtx = offscreen.getContext('2d');
        const imgData = offCtx.createImageData(maskW, maskH);
        const d = imgData.data;

        for (let i = 0; i < maskData.length; i++) {
            const cls = maskData[i];
            const c = SEG_COLORS[cls];
            if (c) {
                d[i * 4] = c[0]; d[i * 4 + 1] = c[1]; d[i * 4 + 2] = c[2]; d[i * 4 + 3] = c[3];
            }
        }
        offCtx.putImageData(imgData, 0, 0);

        this._segOverlay = { canvas: offscreen, sceneX, sceneY, sceneW, sceneH };
        this.segClassVisibility = {};
        (classNames || []).forEach((name, i) => { this.segClassVisibility[i + 1] = true; });
        this.requestRender();
    }

    /**
     * base64 인코딩된 seg overlay 이미지 설정 (백엔드에서 받은 데이터)
     */
    setSegmentationOverlayFromData(segData) {
        if (!segData || !segData.mask_b64) {
            this._segOverlay = null;
            this.requestRender();
            return;
        }

        const img = new Image();
        img.onload = () => {
            const offscreen = new OffscreenCanvas(img.width, img.height);
            offscreen.getContext('2d').drawImage(img, 0, 0);
            this._segOverlay = {
                canvas: offscreen,
                sceneX: segData.scene_x,
                sceneY: segData.scene_y,
                sceneW: segData.scene_w,
                sceneH: segData.scene_h,
            };
            this.requestRender();
        };
        img.src = `data:image/png;base64,${segData.mask_b64}`;
    }

    clearSegmentationOverlay() {
        this._segOverlay = null;
        this.segClassVisibility = {};
        this.requestRender();
    }

    /**
     * Virtual Stain (VS IHC) 오버레이 설정 — 타일 피라미드 방식.
     * @param {object} meta - {
     *   slide_id, stain_type, target_mpp,
     *   roi_origin: [x,y], canvas_l0_w, canvas_l0_h,
     *   tile_size, levels: [{level,width,height,nx,ny}...],
     *   roi_polygons? (표시 클립용)
     * }
     */
    setVirtualStainOverlay(meta) {
        // 이전 타일 캐시 정리
        this._vsTileCache.clear();
        this._vsTileLoading.clear();
        this._vsTileMissing.clear();
        this._vsLoadQueue.length = 0;
        this._vsActiveLoads = 0;

        if (!meta || !meta.levels || meta.levels.length === 0) {
            console.warn('[viewer] VS overlay: missing tile levels metadata');
            this._vsOverlay = null;
            this.requestRender();
            return;
        }

        const [ox, oy] = meta.roi_origin || [0, 0];
        this._vsOverlay = {
            slideId: meta.slide_id,
            stainType: meta.stain_type || 'ihc_membrane',
            targetMpp: meta.target_mpp || 2.0,
            originX: ox,
            originY: oy,
            sceneW: meta.canvas_l0_w,
            sceneH: meta.canvas_l0_h,
            tileSize: meta.tile_size || 512,
            levels: meta.levels,
            roiPolygons: meta.roi_polygons || null,
        };
        this._vsVisible = true;
        this.requestRender();
    }

    setVirtualStainVisible(visible) {
        this._vsVisible = !!visible;
        this.requestRender();
    }

    clearVirtualStainOverlay() {
        this._vsOverlay = null;
        this._vsVisible = true;
        this._vsSplitMode = false;
        this._vsTileCache.clear();
        this._vsTileLoading.clear();
        this._vsTileMissing.clear();
        this._vsLoadQueue.length = 0;
        this._vsActiveLoads = 0;
        this.requestRender();
    }

    hasVirtualStainOverlay() {
        return !!this._vsOverlay;
    }

    _renderSegmentationOverlay() {
        if (!this._segOverlay) return;
        const { canvas, sceneX, sceneY, sceneW, sceneH } = this._segOverlay;
        const [cx, cy] = this.sceneToCanvas(sceneX, sceneY);
        const cw = sceneW * this.zoom;
        const ch = sceneH * this.zoom;
        const octx = this.overlayCtx;
        octx.imageSmoothingEnabled = true;
        octx.drawImage(canvas, cx, cy, cw, ch);
    }

    _renderDetectionOverlay() {
        const octx = this.overlayCtx;
        if (!this.detectionCells.length) return;

        // effectiveMpp 기준: 화면에 보이는 실제 해상도로 판단
        // mpp < 3.0 → 개별 셀, mpp >= 3.0 → 저배율 → 히트맵
        const effectiveMpp = this.getEffectiveMpp();
        if (effectiveMpp >= 3.0) {
            this._renderHeatmap(octx);
        } else {
            this._renderCells(octx);
        }

        // 편집 대상 셀 하이라이트는 어떤 모드든 항상 표시
        this._renderCellHighlight(octx);
        this._renderMultiCellHighlight(octx);
        this._renderLasso(octx);
    }

    _renderMultiCellHighlight(octx) {
        if (!this._highlightedCellIdxSet || this._highlightedCellIdxSet.size === 0) return;
        const CLASS_COLORS = {
            0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
            4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
        };
        const baseR = Math.max(10, 6 * this.zoom);
        octx.save();
        for (const idx of this._highlightedCellIdxSet) {
            if (idx < 0 || idx >= this.detectionCells.length) continue;
            const c = this.detectionCells[idx];
            const [hx, hy] = this.sceneToCanvas(c.x, c.y);
            const hex = (this.classColorOverride && this.classColorOverride[c.class_id])
                        || CLASS_COLORS[c.class_id] || '#FFFF00';
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);

            octx.strokeStyle = 'rgba(0,0,0,0.85)';
            octx.lineWidth = 4;
            octx.beginPath();
            octx.arc(hx, hy, baseR + 1, 0, Math.PI * 2);
            octx.stroke();

            octx.fillStyle = `rgba(${r},${g},${b},0.30)`;
            octx.beginPath();
            octx.arc(hx, hy, baseR, 0, Math.PI * 2);
            octx.fill();

            octx.strokeStyle = `rgb(${r},${g},${b})`;
            octx.lineWidth = 2;
            octx.beginPath();
            octx.arc(hx, hy, baseR, 0, Math.PI * 2);
            octx.stroke();
        }
        octx.restore();
    }

    _renderLasso(octx) {
        if (!this._lassoActive || this._lassoPoints.length < 2) return;
        octx.save();
        octx.fillStyle = 'rgba(0,255,255,0.12)';
        octx.strokeStyle = '#00FFFF';
        octx.lineWidth = 2;
        octx.setLineDash([6, 4]);
        octx.beginPath();
        const [x0, y0] = this.sceneToCanvas(this._lassoPoints[0][0], this._lassoPoints[0][1]);
        octx.moveTo(x0, y0);
        for (let i = 1; i < this._lassoPoints.length; i++) {
            const [x, y] = this.sceneToCanvas(this._lassoPoints[i][0], this._lassoPoints[i][1]);
            octx.lineTo(x, y);
        }
        octx.closePath();
        octx.fill();
        octx.stroke();
        octx.restore();
    }

    _renderCellHighlight(octx) {
        if (this._highlightedCellIdx < 0 ||
            this._highlightedCellIdx >= this.detectionCells.length) return;
        const hc = this.detectionCells[this._highlightedCellIdx];
        const [hx, hy] = this.sceneToCanvas(hc.x, hc.y);

        const CLASS_COLORS = {
            0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
            4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
        };
        const hexColor = (this.classColorOverride && this.classColorOverride[hc.class_id])
                         || CLASS_COLORS[hc.class_id] || '#FFFF00';
        const r = parseInt(hexColor.slice(1, 3), 16);
        const g = parseInt(hexColor.slice(3, 5), 16);
        const b = parseInt(hexColor.slice(5, 7), 16);

        // 줌과 무관하게 항상 잘 보이는 크기 (최소 18px)
        const baseR = Math.max(18, 12 * this.zoom);

        octx.save();

        // 외곽 어두운 링 (대비)
        octx.strokeStyle = 'rgba(0,0,0,0.85)';
        octx.lineWidth = 6;
        octx.beginPath();
        octx.arc(hx, hy, baseR + 2, 0, Math.PI * 2);
        octx.stroke();

        // 채움
        octx.fillStyle = `rgba(${r},${g},${b},0.25)`;
        octx.beginPath();
        octx.arc(hx, hy, baseR, 0, Math.PI * 2);
        octx.fill();

        // 클래스 색 외곽선
        octx.strokeStyle = `rgb(${r},${g},${b})`;
        octx.lineWidth = 3;
        octx.shadowColor = `rgb(${r},${g},${b})`;
        octx.shadowBlur = 10;
        octx.beginPath();
        octx.arc(hx, hy, baseR, 0, Math.PI * 2);
        octx.stroke();

        // 십자선 (셀 위치 정확히 표시)
        octx.shadowBlur = 0;
        octx.strokeStyle = '#FFFFFF';
        octx.lineWidth = 2;
        const cross = baseR + 8;
        octx.beginPath();
        octx.moveTo(hx - cross, hy);
        octx.lineTo(hx - baseR - 1, hy);
        octx.moveTo(hx + baseR + 1, hy);
        octx.lineTo(hx + cross, hy);
        octx.moveTo(hx, hy - cross);
        octx.lineTo(hx, hy - baseR - 1);
        octx.moveTo(hx, hy + baseR + 1);
        octx.lineTo(hx, hy + cross);
        octx.stroke();

        octx.restore();
    }

    /**
     * 히트맵 렌더링 (기존 create_heatmap_mask와 동일 방식)
     * 1. 가시 클래스 density를 합산
     * 2. 현재 뷰 영역만 crop
     * 3. 가우시안 블러
     * 4. jet 컬러맵 + 알파를 ImageData로 그리기
     */
    _renderHeatmap(octx) {
        const cache = this._heatmapCache;
        if (!cache) return;

        // 가시 클래스 키 — 변경 감지용
        const visKey = Object.keys(cache.clsDensities)
            .filter(k => this.classVisibility[parseInt(k)] !== false)
            .sort()
            .join(',');

        // 캐시된 이미지가 유효하면 그대로 drawImage
        if (!this._heatmapImage || this._heatmapImage.visKey !== visKey) {
            this._heatmapImage = this._buildHeatmapImage(visKey);
        }
        const img = this._heatmapImage;
        if (!img) return;

        const [canvasX, canvasY] = this.sceneToCanvas(img.sceneLeft, img.sceneTop);
        const canvasW = img.sceneW * this.zoom;
        const canvasH = img.sceneH * this.zoom;

        octx.imageSmoothingEnabled = true;
        octx.drawImage(img.canvas, canvasX, canvasY, canvasW, canvasH);
    }

    /**
     * 전체 데이터 범위에 대한 히트맵 이미지를 1회 빌드.
     * 줌/팬 시 재계산 없이 drawImage로 재사용.
     */
    _buildHeatmapImage(visKey) {
        const cache = this._heatmapCache;
        if (!cache) return null;
        const { clsDensities, xMin, yMin, gw, gh, sx, sy } = cache;

        // 가시 클래스 합산 (전체 그리드)
        const total = gw * gh;
        const combined = new Float32Array(total);
        let hasData = false;
        for (const [clsStr, density] of Object.entries(clsDensities)) {
            const cls = parseInt(clsStr);
            if (this.classVisibility[cls] === false) continue;
            for (let i = 0; i < total; i++) {
                const v = density[i];
                if (v > 0) {
                    combined[i] += v;
                    hasData = true;
                }
            }
        }
        if (!hasData) return null;

        // 출력 해상도 (최대 512px)
        const maxDim = 512;
        let outW, outH;
        if (gw >= gh) {
            outW = Math.min(maxDim, gw);
            outH = Math.max(1, Math.round(outW * gh / gw));
        } else {
            outH = Math.min(maxDim, gh);
            outW = Math.max(1, Math.round(outH * gw / gh));
        }

        // 리사이즈 (nearest)
        const resized = new Float32Array(outH * outW);
        const rxScale = gw / outW;
        const ryScale = gh / outH;
        for (let y = 0; y < outH; y++) {
            for (let x = 0; x < outW; x++) {
                const srcX = Math.min(Math.floor(x * rxScale), gw - 1);
                const srcY = Math.min(Math.floor(y * ryScale), gh - 1);
                resized[y * outW + x] = combined[srcY * gw + srcX];
            }
        }

        // 가우시안 블러
        const blurPasses = Math.max(8, Math.round(outW / 20));
        const blurred = this._blurGrid(resized, outW, outH, blurPasses);

        let maxVal = 0;
        for (let i = 0; i < blurred.length; i++) {
            if (blurred[i] > maxVal) maxVal = blurred[i];
        }
        if (maxVal === 0) return null;

        // ImageData → 오프스크린 캔버스
        const offscreen = new OffscreenCanvas(outW, outH);
        const offCtx = offscreen.getContext('2d');
        const imgData = offCtx.createImageData(outW, outH);
        const data = imgData.data;
        const ALPHA_MAX = 180;

        for (let i = 0; i < blurred.length; i++) {
            const norm = blurred[i] / maxVal;
            if (norm < 0.01) { data[i * 4 + 3] = 0; continue; }
            const [r, g, b] = this._jetColor(norm);
            data[i * 4 + 0] = r;
            data[i * 4 + 1] = g;
            data[i * 4 + 2] = b;
            data[i * 4 + 3] = Math.round(norm * ALPHA_MAX);
        }
        offCtx.putImageData(imgData, 0, 0);

        return {
            canvas: offscreen,
            sceneLeft: xMin,
            sceneTop: yMin,
            sceneW: gw / sx,
            sceneH: gh / sy,
            visKey,
        };
    }

    _renderCells(octx) {
        if (!this._spatialGrid) return;

        const halfVW = this._viewW / this.zoom / 2;
        const halfVH = this._viewH / this.zoom / 2;
        const viewLeft = this.viewCenterX - halfVW;
        const viewTop = this.viewCenterY - halfVH;
        const viewRight = this.viewCenterX + halfVW;
        const viewBottom = this.viewCenterY + halfVH;

        // SpatialGrid로 뷰포트 내 셀만 조회 (O(1), 전체 순회 제거)
        const visible = this._spatialGrid.query(viewLeft, viewTop, viewRight, viewBottom);

        // effectiveMpp에 따라 셀 크기/두께 조절
        const effectiveMpp = this.getEffectiveMpp();
        let baseRadius, lineW;
        if (effectiveMpp < 1.0) {
            baseRadius = 8;
            lineW = 2;
        } else {
            baseRadius = 5;
            lineW = 1.2;
        }
        const cellRadius = Math.max(2, baseRadius * this.zoom);

        const CLASS_COLORS = {
            0: '#FF4500', 1: '#00FF00', 2: '#0000FF', 3: '#FFFF00',
            4: '#8A2BE2', 5: '#808080', 6: '#FF0000', 7: '#00FF00',
        };
        const override = this.classColorOverride;

        octx.lineWidth = lineW;
        for (const cell of visible) {
            const threshold = this.classConfidence[cell.class_id] ?? 0.01;
            if (cell.confidence < threshold) continue;
            if (this.classVisibility[cell.class_id] === false) continue;

            const [cx, cy] = this.sceneToCanvas(cell.x, cell.y);
            const color = (override && override[cell.class_id]) || CLASS_COLORS[cell.class_id] || '#FFFFFF';

            octx.beginPath();
            octx.arc(cx, cy, cellRadius, 0, Math.PI * 2);
            octx.strokeStyle = color;
            octx.stroke();
        }

    }

    // ── Annotation 그리기 ──

    setDrawMode(mode) {
        // mode: 'polygon' | 'brush' | 'rectangle' | 'point' | 'cut' | 'rect-1mm2' | 'circle-1mm2' | null
        this._cancelDrawing();
        this.drawMode = mode;
        this.canvas.style.cursor = mode ? 'crosshair' : 'grab';
        if (this.onDrawModeChange) this.onDrawModeChange(mode);
    }

    _adjustBrushSize(deltaPx) {
        this._brushSizePx = Math.max(4, Math.min(120, (this._brushSizePx || 28) + deltaPx));
        localStorage.setItem('annotationBrushSizePx', String(this._brushSizePx));
        this.requestRender();
    }

    _brushRadiusScene() {
        return (this._brushSizePx || 28) / (2 * Math.max(this.zoom, 0.0001));
    }

    /**
     * 슬라이드 좌표계 기준 1mm 가 몇 px 인지. mpp(µm/px) 가 0.25 면 4000 px = 1mm.
     * slideInfo 가 없거나 mpp 가 없으면 null — 호출 측에서 가드 필요.
     */
    _pixelsPerMM() {
        if (!this.slideInfo || !this.slideInfo.mpp) return null;
        return 1000 / this.slideInfo.mpp;  // 1mm = 1000 µm
    }

    /** 중심(cx,cy) 기준 1mm × 1mm 정사각형 4 꼭짓점 (scene 좌표). */
    _makeRect1mm2Coords(cx, cy) {
        const ppm = this._pixelsPerMM();
        if (ppm == null) return null;
        const half = ppm / 2;  // 1mm 변의 절반
        return [
            [cx - half, cy - half],
            [cx + half, cy - half],
            [cx + half, cy + half],
            [cx - half, cy + half],
        ];
    }

    /** 중심(cx,cy) 기준 면적 1mm² 인 원의 64각형 근사 (scene 좌표). */
    _makeCircle1mm2Coords(cx, cy) {
        const ppm = this._pixelsPerMM();
        if (ppm == null) return null;
        // 면적 = π r² = 1mm²  →  r = √(1/π) mm  →  px 로 환산
        const radiusPx = Math.sqrt(1 / Math.PI) * ppm;
        const N = 64;
        const pts = [];
        for (let i = 0; i < N; i++) {
            const t = (i / N) * Math.PI * 2;
            pts.push([cx + Math.cos(t) * radiusPx, cy + Math.sin(t) * radiusPx]);
        }
        return pts;
    }

    _onDrawMouseDown(sx, sy, cx, cy, e) {
        if (this.drawMode === 'polygon') {
            // 누르는 순간 시작, 드래그하면서 점 추가, 떼면 완성
            this._drawingPoints = [[sx, sy]];
            this._isDrawing = true;
            this._drawingCurrent = [sx, sy];
            this._lastDrawDragCanvas = [cx, cy];
            this.requestRender();
        } else if (this.drawMode === 'brush') {
            this._drawingPoints = [[sx, sy]];
            this._isDrawing = true;
            this._drawingCurrent = [sx, sy];
            this._lastDrawDragCanvas = [cx, cy];
            this.requestRender();
        } else if (this.drawMode === 'cut') {
            const hitAnn = this._hitAnnotation(sx, sy);
            if (hitAnn && (hitAnn.type === 'polygon' || hitAnn.type === 'rectangle')) {
                this.selectAnnotation(hitAnn.id);
            }
            if (!this._getEditableSelectedPolygon()) {
                this._cancelDrawing();
                return;
            }
            this._drawingPoints = [[sx, sy]];
            this._isDrawing = true;
            this._drawingCurrent = [sx, sy];
            this._lastDrawDragCanvas = [cx, cy];
            this.requestRender();
        } else if (this.drawMode === 'rectangle') {
            this._drawingStart = [sx, sy];
            this._drawingCurrent = [sx, sy];
            this._isDrawing = true;
        } else if (this.drawMode === 'point') {
            this._createAnnotation('point', [[sx, sy]]);
        } else if (this.drawMode === 'rect-1mm2') {
            // 클릭 위치를 중심으로 1mm × 1mm 정사각형 즉시 배치.
            const coords = this._makeRect1mm2Coords(sx, sy);
            if (coords) this._createAnnotation('rectangle', coords);
        } else if (this.drawMode === 'circle-1mm2') {
            // 면적 1mm² 원 (64각형 근사) — 기존 polygon 파이프라인에 그대로 들어가
            // 편집/ROI 내보내기/저장 모두 자동 동작.
            const coords = this._makeCircle1mm2Coords(sx, sy);
            if (coords) this._createAnnotation('polygon', coords);
        } else if (this.drawMode === 'ruler') {
            // 1차 클릭: 시작점, 2차 클릭: 고정, 3차 클릭: 새 측정 시작.
            // annotation 으로 저장 X — drawMode 해제 시 사라지는 일회성 측정.
            if (!this._rulerStart || this._rulerFinalized) {
                this._rulerStart = [sx, sy];
                this._rulerEnd = [sx, sy];
                this._rulerFinalized = false;
            } else {
                // 수평/수직 ±2° 스냅 — preview 와 동일 규칙으로 고정.
                this._rulerEnd = this._snapRulerEnd(
                    this._rulerStart[0], this._rulerStart[1], sx, sy);
                this._rulerFinalized = true;
            }
            this.requestRender();
        }
    }

    _onDrawMouseMove(sx, sy, cx, cy) {
        this._drawingCurrent = [sx, sy];

        // 폴리곤 드래그로 점 추가 (10px 간격)
        if ((this.drawMode === 'polygon' || this.drawMode === 'brush' || this.drawMode === 'cut') &&
                this._drawingPoints.length > 0 && (cx !== undefined)) {
            if (this._lastDrawDragCanvas) {
                const ddx = cx - this._lastDrawDragCanvas[0];
                const ddy = cy - this._lastDrawDragCanvas[1];
                const step = this.drawMode === 'brush' ? Math.max(3, (this._brushSizePx || 28) * 0.25) : 10;
                if (Math.sqrt(ddx * ddx + ddy * ddy) >= step) {
                    this._drawingPoints.push([sx, sy]);
                    this._lastDrawDragCanvas = [cx, cy];
                }
            }
        }

        this.requestRender();
    }

    _onDrawMouseUp(sx, sy) {
        if (this.drawMode === 'polygon' && this._isDrawing) {
            // 마우스 떼면 폴리곤 완성 (최소 3점)
            if (this._drawingPoints.length >= 3) {
                this._finishPolygon();
            } else {
                this._cancelDrawing();
            }
            return;
        }
        if (this.drawMode === 'brush' && this._isDrawing) {
            const pts = [...this._drawingPoints];
            const last = pts[pts.length - 1];
            if (!last || Math.hypot(last[0] - sx, last[1] - sy) > 1 / Math.max(this.zoom, 0.0001)) {
                pts.push([sx, sy]);
            }
            const brushPolygon = this._makeBrushPolygonFromPath(pts);
            if (brushPolygon && brushPolygon.length >= 3) {
                this._createAnnotation('polygon', brushPolygon);
            }
            this._drawingPoints = [];
            this._drawingCurrent = null;
            this._isDrawing = false;
            this._lastDrawDragCanvas = null;
            this.requestRender();
            return;
        }
        if (this.drawMode === 'cut' && this._isDrawing) {
            const pts = [...this._drawingPoints];
            const last = pts[pts.length - 1];
            if (!last || Math.hypot(last[0] - sx, last[1] - sy) > 1 / Math.max(this.zoom, 0.0001)) {
                pts.push([sx, sy]);
            }
            if (pts.length >= 2) this._applyPolygonCutPath(pts);
            this._drawingPoints = [];
            this._drawingCurrent = null;
            this._isDrawing = false;
            this._lastDrawDragCanvas = null;
            this.requestRender();
            return;
        }
        if (this.drawMode === 'rectangle' && this._drawingStart) {
            const [x0, y0] = this._drawingStart;
            const w = Math.abs(sx - x0);
            const h = Math.abs(sy - y0);
            if (w > 5 / this.zoom && h > 5 / this.zoom) {
                const xMin = Math.min(x0, sx), yMin = Math.min(y0, sy);
                const xMax = Math.max(x0, sx), yMax = Math.max(y0, sy);
                this._createAnnotation('rectangle', [
                    [xMin, yMin], [xMax, yMin], [xMax, yMax], [xMin, yMax]
                ]);
            }
            this._drawingStart = null;
            this._drawingCurrent = null;
            this._isDrawing = false;
            this.requestRender();
        }
    }

    _finishPolygon() {
        if (this._drawingPoints.length >= 3) {
            // 자기교차(self-intersection) 검사 — 닫는 선분 포함
            if (this._isSelfIntersecting(this._drawingPoints)) {
                this._cancelDrawing();
                return;
            }
            this._createAnnotation('polygon', [...this._drawingPoints]);
        }
        this._drawingPoints = [];
        this._drawingCurrent = null;
        this._isDrawing = false;
        this._lastDrawDragCanvas = null;
        this.requestRender();
    }

    /** 폴리곤 선분들이 자기 자신과 교차하는지 검사 */
    _makeCirclePolygon(cx, cy, radius, count = 28) {
        const pts = [];
        for (let i = 0; i < count; i++) {
            const a = (i / count) * Math.PI * 2;
            pts.push([cx + Math.cos(a) * radius, cy + Math.sin(a) * radius]);
        }
        return pts;
    }

    _resampleBrushPath(path, spacing) {
        const clean = this._cleanPolylinePoints(path);
        if (clean.length <= 1) return clean;
        const samples = [clean[0]];
        let carry = 0;
        for (let i = 1; i < clean.length; i++) {
            const a = clean[i - 1];
            const b = clean[i];
            const dx = b[0] - a[0];
            const dy = b[1] - a[1];
            const len = Math.hypot(dx, dy);
            if (len < 1e-9) continue;

            let dist = spacing - carry;
            while (dist <= len) {
                const t = dist / len;
                samples.push([a[0] + dx * t, a[1] + dy * t]);
                dist += spacing;
            }
            carry = len - (dist - spacing);
            if (carry >= spacing || carry < 0) carry = 0;
        }
        const last = clean[clean.length - 1];
        const prev = samples[samples.length - 1];
        if (!prev || Math.hypot(prev[0] - last[0], prev[1] - last[1]) > spacing * 0.35) {
            samples.push(last);
        }
        return samples;
    }

    _makeBrushPolygonFromPath(points) {
        const path = this._cleanPolylinePoints(points);
        const radius = this._brushRadiusScene();
        if (!path.length) return null;
        if (path.length === 1) return this._makeCirclePolygon(path[0][0], path[0][1], radius);

        let stroke = this._resampleBrushPath(path, Math.max(radius * 0.3, 1 / Math.max(this.zoom, 0.0001)));
        if (stroke.length > 900) {
            const stride = Math.ceil(stroke.length / 900);
            stroke = stroke.filter((_, index) => index % stride === 0);
            stroke.push(path[path.length - 1]);
        }
        if (stroke.length < 2) return null;

        const normals = [];
        for (let i = 0; i < stroke.length; i++) {
            const prev = stroke[Math.max(0, i - 1)];
            const next = stroke[Math.min(stroke.length - 1, i + 1)];
            let dx = next[0] - prev[0];
            let dy = next[1] - prev[1];
            const len = Math.hypot(dx, dy);
            if (len < 1e-9) {
                dx = 1;
                dy = 0;
            } else {
                dx /= len;
                dy /= len;
            }
            normals.push([-dy, dx]);
        }

        const left = stroke.map((p, i) => [p[0] + normals[i][0] * radius, p[1] + normals[i][1] * radius]);
        const right = stroke.map((p, i) => [p[0] - normals[i][0] * radius, p[1] - normals[i][1] * radius]);
        const capSteps = 12;
        const polygon = [...left];

        const end = stroke[stroke.length - 1];
        const endNormal = normals[normals.length - 1];
        const endLeftAngle = Math.atan2(endNormal[1], endNormal[0]);
        for (let i = 1; i < capSteps; i++) {
            const a = endLeftAngle - (Math.PI * i) / capSteps;
            polygon.push([end[0] + Math.cos(a) * radius, end[1] + Math.sin(a) * radius]);
        }

        polygon.push(...right.reverse());

        const start = stroke[0];
        const startNormal = normals[0];
        const startRightAngle = Math.atan2(-startNormal[1], -startNormal[0]);
        for (let i = 1; i < capSteps; i++) {
            const a = startRightAngle - (Math.PI * i) / capSteps;
            polygon.push([start[0] + Math.cos(a) * radius, start[1] + Math.sin(a) * radius]);
        }

        return this._cleanPolygonPoints(polygon);
    }

    _isSelfIntersecting(pts) {
        const n = pts.length;
        if (n < 4) return false; // 삼각형은 교차 불가
        // 닫힌 폴리곤의 모든 변(edge) 쌍 검사
        for (let i = 0; i < n; i++) {
            const a = pts[i], b = pts[(i + 1) % n];
            for (let j = i + 2; j < n; j++) {
                if (i === 0 && j === n - 1) continue; // 인접 변 (첫-끝) 건너뛰기
                const c = pts[j], d = pts[(j + 1) % n];
                if (this._segmentsIntersect(a, b, c, d)) return true;
            }
        }
        return false;
    }

    /** 두 선분 (p1-p2, p3-p4) 교차 판정 */
    _segmentsIntersect(p1, p2, p3, p4) {
        const d1 = this._cross(p3, p4, p1);
        const d2 = this._cross(p3, p4, p2);
        const d3 = this._cross(p1, p2, p3);
        const d4 = this._cross(p1, p2, p4);
        if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
            ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true;
        return false;
    }

    _cross(a, b, c) {
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    }

    _cancelDrawing() {
        this._drawingPoints = [];
        this._drawingStart = null;
        this._drawingCurrent = null;
        this._isDrawing = false;
        this._lastDrawDragCanvas = null;
        // Ruler 일회성 측정도 함께 정리 (모드 전환/해제 시 잔상 방지).
        this._rulerStart = null;
        this._rulerEnd = null;
        this._rulerFinalized = false;
        this.requestRender();
    }

    _createAnnotation(type, coordinates) {
        this.pushAnnotationUndo();
        this._annotationCounter++;
        const COLORS = { polygon: [0, 255, 0], rectangle: [255, 0, 0], point: [0, 0, 255] };
        const NAMES = { polygon: 'ROI', rectangle: 'Rectangle', point: 'Point' };
        const ann = {
            id: crypto.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            name: `${NAMES[type]}_${this._annotationCounter}`,
            type,
            coordinates,
            color: COLORS[type],
            visible: true,
            selected: false,
        };
        this.annotations.push(ann);
        this.selectAnnotation(ann.id);
        if (this.onAnnotationCreated) this.onAnnotationCreated(ann);
        this.requestRender();
        return ann;
    }

    selectAnnotation(id) {
        this.annotations.forEach(a => a.selected = (a.id === id));
        this.selectedAnnotationId = id;
        if (this.onAnnotationSelected) {
            this.onAnnotationSelected(this.annotations.find(a => a.id === id) || null);
        }
        this.requestRender();
    }

    deleteAnnotation(id) {
        if (!this.annotations.some(a => a.id === id)) return;
        this.pushAnnotationUndo();
        this.annotations = this.annotations.filter(a => a.id !== id);
        if (this.selectedAnnotationId === id) {
            this.selectedAnnotationId = null;
            if (this.onAnnotationSelected) this.onAnnotationSelected(null);
        }
        this.requestRender();
    }

    clearAnnotations() {
        if (this.annotations.length) this.pushAnnotationUndo();
        this.annotations = [];
        this.selectedAnnotationId = null;
        this._annotationCounter = 0;
        this.requestRender();
    }

    // ── Annotation 렌더링 ──

    _renderAnnotations(octx) {
        // 확정된 annotation
        for (const ann of this.annotations) {
            if (!ann.visible) continue;
            const [r, g, b] = ann.color;
            const strokeColor = `rgb(${r},${g},${b})`;
            const fillColor = `rgba(${r},${g},${b},0.1)`;
            const lineWidth = ann.selected ? 3 : 2;

            if (ann.type === 'polygon') {
                this._drawPolygon(octx, ann.coordinates, strokeColor, fillColor, lineWidth);
                if (ann.selected) this._drawControlPoints(octx, ann.coordinates, strokeColor);
            } else if (ann.type === 'rectangle') {
                this._drawPolygon(octx, ann.coordinates, strokeColor, fillColor, lineWidth);
                if (ann.selected) this._drawControlPoints(octx, ann.coordinates, strokeColor);
            } else if (ann.type === 'point') {
                const [cx, cy] = this.sceneToCanvas(ann.coordinates[0][0], ann.coordinates[0][1]);
                const radius = 6;
                octx.beginPath();
                octx.arc(cx, cy, radius, 0, Math.PI * 2);
                octx.fillStyle = strokeColor;
                octx.fill();
                if (ann.selected) {
                    octx.strokeStyle = '#fff';
                    octx.lineWidth = 2;
                    octx.stroke();
                }
            }
        }

        // 진행 중인 그리기 프리뷰
        this._renderInsertVertexPreview(octx);
        this._renderMergeHover(octx);
        this._renderDrawingPreview(octx);
    }

    _renderMergeHover(octx) {
        if (!this._mergeHover || !this._mergeHover.scenePoint) return;
        const [cx, cy] = this.sceneToCanvas(this._mergeHover.scenePoint[0], this._mergeHover.scenePoint[1]);
        octx.save();
        octx.beginPath();
        octx.arc(cx, cy, 13, 0, Math.PI * 2);
        octx.fillStyle = 'rgba(255,255,255,0.94)';
        octx.fill();
        octx.strokeStyle = 'rgba(108,92,231,0.95)';
        octx.lineWidth = 2;
        octx.stroke();
        octx.strokeStyle = 'rgba(108,92,231,0.95)';
        octx.lineWidth = 2.2;
        octx.lineCap = 'round';
        octx.beginPath();
        octx.arc(cx - 3.5, cy, 4.4, Math.PI * 0.25, Math.PI * 1.75);
        octx.arc(cx + 3.5, cy, 4.4, Math.PI * 1.25, Math.PI * 0.75, true);
        octx.stroke();
        octx.beginPath();
        octx.moveTo(cx - 1.5, cy);
        octx.lineTo(cx + 1.5, cy);
        octx.moveTo(cx, cy - 1.5);
        octx.lineTo(cx, cy + 1.5);
        octx.stroke();
        octx.restore();
    }

    _renderInsertVertexPreview(octx) {
        const preview = this._insertVertexPreview;
        if (!preview || !preview.point) return;
        const ann = this.annotations.find(a => a.id === preview.annId);
        if (!ann || !ann.visible) return;
        const [r, g, b] = ann.color || [0, 255, 0];
        const [cx, cy] = this.sceneToCanvas(preview.point[0], preview.point[1]);
        octx.save();
        octx.beginPath();
        octx.arc(cx, cy, 6, 0, Math.PI * 2);
        octx.fillStyle = `rgba(${r},${g},${b},0.35)`;
        octx.fill();
        octx.strokeStyle = `rgba(${r},${g},${b},0.95)`;
        octx.lineWidth = 2;
        octx.stroke();
        octx.beginPath();
        octx.arc(cx, cy, 2.5, 0, Math.PI * 2);
        octx.fillStyle = 'rgba(255,255,255,0.75)';
        octx.fill();
        octx.restore();
    }

    _drawPolygon(octx, coords, strokeColor, fillColor, lineWidth) {
        if (coords.length < 2) return;
        octx.beginPath();
        const [cx0, cy0] = this.sceneToCanvas(coords[0][0], coords[0][1]);
        octx.moveTo(cx0, cy0);
        for (let i = 1; i < coords.length; i++) {
            const [cx, cy] = this.sceneToCanvas(coords[i][0], coords[i][1]);
            octx.lineTo(cx, cy);
        }
        octx.closePath();
        octx.fillStyle = fillColor;
        octx.fill();
        octx.strokeStyle = strokeColor;
        octx.lineWidth = lineWidth;
        octx.stroke();
    }

    _drawControlPoints(octx, coords, color) {
        for (const [sx, sy] of coords) {
            const [cx, cy] = this.sceneToCanvas(sx, sy);
            octx.beginPath();
            octx.arc(cx, cy, 5, 0, Math.PI * 2);
            octx.fillStyle = '#fff';
            octx.fill();
            octx.strokeStyle = color;
            octx.lineWidth = 2;
            octx.stroke();
        }
    }

    /**
     * scene 좌표 두 점 사이의 실측 거리를 사람이 읽기 좋은 문자열로.
     *  - 1 mm 미만: "342.7 µm (1,370 px)"
     *  - 1 mm 이상: "1.234 mm (4,936 px)"
     * mpp 가 없으면 px 단위만.
     */
    _formatDistance(sx0, sy0, sx1, sy1) {
        const dx = sx1 - sx0, dy = sy1 - sy0;
        const distPx = Math.sqrt(dx * dx + dy * dy);
        const strPx = `${Math.round(distPx).toLocaleString('en-US')} px`;
        const mpp = this.slideInfo && this.slideInfo.mpp;
        if (!mpp) return strPx;
        const distUm = distPx * mpp;
        const strUnit = distUm < 1000
            ? `${distUm.toFixed(1)} µm`
            : `${(distUm / 1000).toFixed(3)} mm`;
        return `${strUnit} (${strPx})`;
    }

    /**
     * 시작점→끝점 각도가 수평/수직 ±2° 이내면 해당 축으로 스냅.
     * 약간의 손떨림 보정용 — 임계값을 너무 키우면 의도된 비스듬 측정이 막혀 답답해진다.
     * 반환: [snappedSx, snappedSy]
     */
    _snapRulerEnd(sx0, sy0, sx1, sy1) {
        const dx = sx1 - sx0;
        const dy = sy1 - sy0;
        if (dx === 0 && dy === 0) return [sx1, sy1];
        const FLOAT_SNAP_DEG = 2;
        const float_tol = FLOAT_SNAP_DEG * Math.PI / 180;
        const float_ang = Math.atan2(dy, dx);  // (-π, π]
        const float_abs = Math.abs(float_ang);
        // 수평: 0 또는 ±π
        if (float_abs < float_tol || Math.abs(float_abs - Math.PI) < float_tol) {
            return [sx1, sy0];
        }
        // 수직: ±π/2
        if (Math.abs(float_abs - Math.PI / 2) < float_tol) {
            return [sx0, sy1];
        }
        return [sx1, sy1];
    }

    _renderRulerPreview(octx) {
        const [sx0, sy0] = this._rulerStart;
        const [sx1, sy1] = this._rulerEnd;
        const [cx0, cy0] = this.sceneToCanvas(sx0, sy0);
        const [cx1, cy1] = this.sceneToCanvas(sx1, sy1);

        const color = this._rulerFinalized ? 'rgba(255,140,0,0.95)' : 'rgba(255,140,0,0.8)';

        // 본 직선
        octx.beginPath();
        octx.moveTo(cx0, cy0);
        octx.lineTo(cx1, cy1);
        octx.strokeStyle = color;
        octx.lineWidth = 2;
        if (!this._rulerFinalized) octx.setLineDash([6, 3]);
        octx.stroke();
        octx.setLineDash([]);

        // 양 끝 점
        for (const [px, py] of [[cx0, cy0], [cx1, cy1]]) {
            octx.beginPath();
            octx.arc(px, py, 4, 0, Math.PI * 2);
            octx.fillStyle = color;
            octx.fill();
            octx.strokeStyle = '#fff';
            octx.lineWidth = 1.5;
            octx.stroke();
        }

        // 길이 라벨 — 직선 가운데에 배경박스 + 텍스트
        const label = this._formatDistance(sx0, sy0, sx1, sy1);
        const midX = (cx0 + cx1) / 2;
        const midY = (cy0 + cy1) / 2;
        octx.font = 'bold 12px ui-monospace, Consolas, monospace';
        octx.textAlign = 'center';
        octx.textBaseline = 'middle';
        const textW = octx.measureText(label).width;
        const padX = 6, padY = 3;
        const boxW = textW + padX * 2;
        const boxH = 18;
        // 라벨이 직선과 겹치지 않게 살짝 위로 (직선 방향 수직 오프셋)
        const ang = Math.atan2(cy1 - cy0, cx1 - cx0);
        const off = 14;
        const ox = midX + Math.sin(ang) * off;
        const oy = midY - Math.cos(ang) * off;
        octx.fillStyle = 'rgba(40,30,10,0.85)';
        octx.fillRect(ox - boxW / 2, oy - boxH / 2, boxW, boxH);
        octx.strokeStyle = color;
        octx.lineWidth = 1;
        octx.strokeRect(ox - boxW / 2, oy - boxH / 2, boxW, boxH);
        octx.fillStyle = '#fff';
        octx.fillText(label, ox, oy + 0.5);
        // 기본값 복구 (다른 렌더러 영향 방지)
        octx.textAlign = 'start';
        octx.textBaseline = 'alphabetic';
    }

    _renderDrawingPreview(octx) {
        if (this.drawMode === 'polygon' && this._drawingPoints.length > 0) {
            octx.beginPath();
            const [cx0, cy0] = this.sceneToCanvas(this._drawingPoints[0][0], this._drawingPoints[0][1]);
            octx.moveTo(cx0, cy0);
            for (let i = 1; i < this._drawingPoints.length; i++) {
                const [cx, cy] = this.sceneToCanvas(this._drawingPoints[i][0], this._drawingPoints[i][1]);
                octx.lineTo(cx, cy);
            }
            if (this._drawingCurrent) {
                const [cx, cy] = this.sceneToCanvas(this._drawingCurrent[0], this._drawingCurrent[1]);
                octx.lineTo(cx, cy);
            }
            octx.strokeStyle = 'rgba(0,255,0,0.8)';
            octx.lineWidth = 2;
            octx.setLineDash([6, 3]);
            octx.stroke();
            octx.setLineDash([]);

            // 시작점 표시
            octx.beginPath();
            octx.arc(cx0, cy0, 6, 0, Math.PI * 2);
            octx.fillStyle = 'rgba(0,255,0,0.6)';
            octx.fill();
            octx.strokeStyle = '#fff';
            octx.lineWidth = 1;
            octx.stroke();

            // 각 점
            for (const [sx, sy] of this._drawingPoints) {
                const [cx, cy] = this.sceneToCanvas(sx, sy);
                octx.beginPath();
                octx.arc(cx, cy, 3, 0, Math.PI * 2);
                octx.fillStyle = '#0f0';
                octx.fill();
            }
        }

        if (this.drawMode === 'brush') {
            if (this._isDrawing && this._drawingPoints.length > 0) {
                octx.save();
                octx.beginPath();
                const [cx0, cy0] = this.sceneToCanvas(this._drawingPoints[0][0], this._drawingPoints[0][1]);
                octx.moveTo(cx0, cy0);
                for (let i = 1; i < this._drawingPoints.length; i++) {
                    const [cx, cy] = this.sceneToCanvas(this._drawingPoints[i][0], this._drawingPoints[i][1]);
                    octx.lineTo(cx, cy);
                }
                if (this._drawingCurrent) {
                    const [cx, cy] = this.sceneToCanvas(this._drawingCurrent[0], this._drawingCurrent[1]);
                    octx.lineTo(cx, cy);
                }
                octx.strokeStyle = 'rgba(0,255,0,0.24)';
                octx.lineWidth = this._brushSizePx || 28;
                octx.lineCap = 'round';
                octx.lineJoin = 'round';
                octx.stroke();
                octx.restore();
            }
            if (this._drawingCurrent) {
                const [cx, cy] = this.sceneToCanvas(this._drawingCurrent[0], this._drawingCurrent[1]);
                octx.save();
                octx.beginPath();
                octx.arc(cx, cy, (this._brushSizePx || 28) / 2, 0, Math.PI * 2);
                octx.fillStyle = 'rgba(0,255,0,0.08)';
                octx.fill();
                octx.strokeStyle = 'rgba(0,255,0,0.78)';
                octx.lineWidth = 1.5;
                octx.setLineDash([4, 3]);
                octx.stroke();
                octx.setLineDash([]);
                octx.restore();
            }
        }

        if (this.drawMode === 'cut' && this._drawingPoints.length > 0) {
            octx.beginPath();
            const [cx0, cy0] = this.sceneToCanvas(this._drawingPoints[0][0], this._drawingPoints[0][1]);
            octx.moveTo(cx0, cy0);
            for (let i = 1; i < this._drawingPoints.length; i++) {
                const [cx, cy] = this.sceneToCanvas(this._drawingPoints[i][0], this._drawingPoints[i][1]);
                octx.lineTo(cx, cy);
            }
            if (this._drawingCurrent) {
                const [cx, cy] = this.sceneToCanvas(this._drawingCurrent[0], this._drawingCurrent[1]);
                octx.lineTo(cx, cy);
            }
            octx.strokeStyle = 'rgba(0,145,255,0.95)';
            octx.lineWidth = 3;
            octx.setLineDash([8, 4]);
            octx.stroke();
            octx.setLineDash([]);
            for (const [sx, sy] of [this._drawingPoints[0], this._drawingCurrent || this._drawingPoints[this._drawingPoints.length - 1]]) {
                const [cx, cy] = this.sceneToCanvas(sx, sy);
                octx.beginPath();
                octx.arc(cx, cy, 4, 0, Math.PI * 2);
                octx.fillStyle = 'rgba(0,145,255,0.85)';
                octx.fill();
                octx.strokeStyle = '#fff';
                octx.lineWidth = 1.5;
                octx.stroke();
            }
        }

        if (this.drawMode === 'rectangle' && this._drawingStart && this._drawingCurrent) {
            const [cx0, cy0] = this.sceneToCanvas(this._drawingStart[0], this._drawingStart[1]);
            const [cx1, cy1] = this.sceneToCanvas(this._drawingCurrent[0], this._drawingCurrent[1]);
            const x = Math.min(cx0, cx1), y = Math.min(cy0, cy1);
            const w = Math.abs(cx1 - cx0), h = Math.abs(cy1 - cy0);
            octx.fillStyle = 'rgba(255,0,0,0.1)';
            octx.fillRect(x, y, w, h);
            octx.strokeStyle = 'rgba(255,0,0,0.8)';
            octx.lineWidth = 2;
            octx.setLineDash([6, 3]);
            octx.strokeRect(x, y, w, h);
            octx.setLineDash([]);
        }

        // Ruler — 일회성 거리 측정. annotation 이 아니라 drawMode 활성 동안만 표시.
        if (this.drawMode === 'ruler' && this._rulerStart && this._rulerEnd) {
            this._renderRulerPreview(octx);
        }

        // 1mm² 고정 크기 미리보기 — 마우스 위치 중심으로 따라간다.
        if ((this.drawMode === 'rect-1mm2' || this.drawMode === 'circle-1mm2')
                && this._drawingCurrent) {
            const [sx, sy] = this._drawingCurrent;
            const coords = this.drawMode === 'rect-1mm2'
                ? this._makeRect1mm2Coords(sx, sy)
                : this._makeCircle1mm2Coords(sx, sy);
            if (coords) {
                const fillColor = this.drawMode === 'rect-1mm2'
                    ? 'rgba(255,0,0,0.10)' : 'rgba(0,128,255,0.10)';
                const strokeColor = this.drawMode === 'rect-1mm2'
                    ? 'rgba(255,0,0,0.85)' : 'rgba(0,128,255,0.85)';
                octx.beginPath();
                const [c0x, c0y] = this.sceneToCanvas(coords[0][0], coords[0][1]);
                octx.moveTo(c0x, c0y);
                for (let i = 1; i < coords.length; i++) {
                    const [cx, cy] = this.sceneToCanvas(coords[i][0], coords[i][1]);
                    octx.lineTo(cx, cy);
                }
                octx.closePath();
                octx.fillStyle = fillColor;
                octx.fill();
                octx.strokeStyle = strokeColor;
                octx.lineWidth = 2;
                octx.setLineDash([6, 3]);
                octx.stroke();
                octx.setLineDash([]);
                // 중심 십자선
                const [ccx, ccy] = this.sceneToCanvas(sx, sy);
                octx.strokeStyle = strokeColor;
                octx.lineWidth = 1;
                octx.beginPath();
                octx.moveTo(ccx - 6, ccy); octx.lineTo(ccx + 6, ccy);
                octx.moveTo(ccx, ccy - 6); octx.lineTo(ccx, ccy + 6);
                octx.stroke();
            }
        }
    }

    // ── Hit Testing ──

    /** 캔버스 좌표에서 선택된 annotation의 컨트롤포인트 히트 테스트 */
    _getEditableSelectedPolygon() {
        const ann = this.annotations.find(a => a.id === this.selectedAnnotationId);
        if (!ann || !ann.visible) return null;
        if ((ann.type !== 'polygon' && ann.type !== 'rectangle') || ann.coordinates.length < 3) return null;
        return ann;
    }

    _resizeRectangleFromCorner(ann, pointIndex, sx, sy) {
        const coords = ann.coordinates;
        if (!coords || coords.length !== 4) return;
        const idx = Math.max(0, Math.min(3, pointIndex | 0));
        const opp = coords[(idx + 2) % 4];
        if (!opp) return;

        if (idx === 0) {
            ann.coordinates = [[sx, sy], [opp[0], sy], [opp[0], opp[1]], [sx, opp[1]]];
        } else if (idx === 1) {
            ann.coordinates = [[opp[0], sy], [sx, sy], [sx, opp[1]], [opp[0], opp[1]]];
        } else if (idx === 2) {
            ann.coordinates = [[opp[0], opp[1]], [sx, opp[1]], [sx, sy], [opp[0], sy]];
        } else {
            ann.coordinates = [[sx, opp[1]], [opp[0], opp[1]], [opp[0], sy], [sx, sy]];
        }
    }

    _applyPolygonCutPath(path) {
        const ann = this._getEditableSelectedPolygon();
        if (!ann || !Array.isArray(path) || path.length < 2) return false;

        const poly = this._cleanPolygonPoints(ann.coordinates);
        const stroke = this._cleanPolylinePoints(path);
        if (poly.length < 3 || stroke.length < 2) return false;

        const hits = this._findPathPolygonIntersections(poly, stroke);
        if (hits.length < 2) return false;

        const first = hits[0];
        const last = hits[hits.length - 1];
        if (Math.hypot(first.point[0] - last.point[0], first.point[1] - last.point[1]) < 1e-6) {
            return false;
        }

        const strokeForward = this._extractStrokeSubpath(stroke, first, last);
        if (strokeForward.length < 2) return false;

        const boundary12 = this._polygonBoundaryPath(poly, first, last);
        const boundary21 = this._polygonBoundaryPath(poly, last, first);
        const candidates = [
            this._cleanPolygonPoints(boundary12.concat([...strokeForward].reverse().slice(1, -1))),
            this._cleanPolygonPoints(boundary21.concat(strokeForward.slice(1, -1))),
        ].filter(points => points.length >= 3 && !this._isSelfIntersecting(points));

        if (!candidates.length) return false;

        const originalArea = Math.abs(this._polygonSignedArea(poly));
        const startInside = this._pointInPolygon(stroke[0][0], stroke[0][1], poly);
        const endInside = this._pointInPolygon(stroke[stroke.length - 1][0], stroke[stroke.length - 1][1], poly);

        let ranked = candidates
            .map(points => ({ points, area: Math.abs(this._polygonSignedArea(points)) }))
            .filter(item => item.area > 1e-6);
        if (!ranked.length) return false;

        if (!(startInside && endInside)) {
            const nonExpanding = ranked.filter(item => item.area <= originalArea * 1.02);
            if (nonExpanding.length) ranked = nonExpanding;
        }

        ranked.sort((a, b) => b.area - a.area);
        const next = ranked[0].points;
        if (!next || next.length < 3) return false;

        this.pushAnnotationUndo();
        ann.type = 'polygon';
        ann.coordinates = next;
        this.selectAnnotation(ann.id);
        if (this.onAnnotationChanged) this.onAnnotationChanged(ann);
        this.requestRender();
        return true;
    }

    _findPathPolygonIntersections(poly, path) {
        const hits = [];
        for (let pi = 0; pi < path.length - 1; pi++) {
            const a = path[pi];
            const b = path[pi + 1];
            if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9) continue;
            for (let ei = 0; ei < poly.length; ei++) {
                const c = poly[ei];
                const d = poly[(ei + 1) % poly.length];
                const hit = this._segmentIntersection(a, b, c, d);
                if (!hit) continue;
                hits.push({
                    point: hit.point,
                    pathSegIndex: pi,
                    pathT: hit.t,
                    pathPos: pi + hit.t,
                    edgeIndex: ei,
                    edgeT: hit.u,
                });
            }
        }

        hits.sort((a, b) => a.pathPos - b.pathPos);
        const deduped = [];
        for (const hit of hits) {
            const prev = deduped[deduped.length - 1];
            if (prev && Math.hypot(prev.point[0] - hit.point[0], prev.point[1] - hit.point[1]) < 1e-5) {
                continue;
            }
            deduped.push(hit);
        }
        return deduped;
    }

    _segmentIntersection(a, b, c, d) {
        const r = [b[0] - a[0], b[1] - a[1]];
        const s = [d[0] - c[0], d[1] - c[1]];
        const denom = r[0] * s[1] - r[1] * s[0];
        if (Math.abs(denom) < 1e-12) return null;
        const qmp = [c[0] - a[0], c[1] - a[1]];
        const t = (qmp[0] * s[1] - qmp[1] * s[0]) / denom;
        const u = (qmp[0] * r[1] - qmp[1] * r[0]) / denom;
        const eps = 1e-9;
        if (t < -eps || t > 1 + eps || u < -eps || u > 1 + eps) return null;
        const tt = Math.max(0, Math.min(1, t));
        const uu = Math.max(0, Math.min(1, u));
        return {
            point: [a[0] + r[0] * tt, a[1] + r[1] * tt],
            t: tt,
            u: uu,
        };
    }

    _extractStrokeSubpath(path, startHit, endHit) {
        const pts = [startHit.point];
        for (let i = startHit.pathSegIndex + 1; i <= endHit.pathSegIndex; i++) {
            if (path[i]) pts.push(path[i]);
        }
        pts.push(endHit.point);
        return this._cleanPolylinePoints(pts);
    }

    _polygonBoundaryPath(poly, startHit, endHit) {
        const n = poly.length;
        const pts = [startHit.point];
        const stop = (endHit.edgeIndex + 1) % n;
        let idx = (startHit.edgeIndex + 1) % n;
        let guard = 0;
        while (guard < n + 1) {
            const sameEdgeWrap = startHit.edgeIndex === endHit.edgeIndex &&
                startHit.edgeT > endHit.edgeT && guard === 0;
            if (idx === stop && !sameEdgeWrap) break;
            pts.push(poly[idx]);
            idx = (idx + 1) % n;
            guard++;
        }
        pts.push(endHit.point);
        return this._cleanPolylinePoints(pts);
    }

    _cleanPolylinePoints(points) {
        const clean = [];
        for (const p of points || []) {
            if (!p || p.length < 2) continue;
            const last = clean[clean.length - 1];
            if (last && Math.hypot(last[0] - p[0], last[1] - p[1]) < 1e-6) continue;
            clean.push([p[0], p[1]]);
        }
        return clean;
    }

    _cleanPolygonPoints(points) {
        const clean = this._cleanPolylinePoints(points);
        if (clean.length > 1) {
            const first = clean[0];
            const last = clean[clean.length - 1];
            if (Math.hypot(first[0] - last[0], first[1] - last[1]) < 1e-6) {
                clean.pop();
            }
        }
        return clean;
    }

    _polygonSignedArea(points) {
        let area = 0;
        for (let i = 0; i < points.length; i++) {
            const a = points[i];
            const b = points[(i + 1) % points.length];
            area += a[0] * b[1] - b[0] * a[1];
        }
        return area / 2;
    }

    _annotationClassKey(ann) {
        return String(ann?.class_id || ann?.properties?.class_id || '');
    }

    _findMergeHoverTarget(sx, sy) {
        const hits = [];
        for (let i = this.annotations.length - 1; i >= 0; i--) {
            const ann = this.annotations[i];
            if (!ann || !ann.visible || ann.type !== 'polygon' || !Array.isArray(ann.coordinates) || ann.coordinates.length < 3) {
                continue;
            }
            if (this._pointInPolygon(sx, sy, ann.coordinates) || this._pointNearPolyline(sx, sy, ann.coordinates, true, Math.max(4, 8 / Math.max(this.zoom, 0.0001)))) {
                hits.push(ann);
            }
        }
        for (let i = 0; i < hits.length; i++) {
            for (let j = i + 1; j < hits.length; j++) {
                if (this._annotationClassKey(hits[i]) !== this._annotationClassKey(hits[j])) continue;
                if (!this._polygonsIntersectOrContain(hits[i].coordinates, hits[j].coordinates)) continue;
                return { annIds: [hits[i].id, hits[j].id], scenePoint: [sx, sy] };
            }
        }
        return null;
    }

    _setMergeHover(target) {
        const prev = this._mergeHover;
        const changed = (!!prev !== !!target) || (!!prev && !!target && (
            prev.annIds[0] !== target.annIds[0] ||
            prev.annIds[1] !== target.annIds[1] ||
            Math.abs(prev.scenePoint[0] - target.scenePoint[0]) > 0.5 / Math.max(this.zoom, 0.0001) ||
            Math.abs(prev.scenePoint[1] - target.scenePoint[1]) > 0.5 / Math.max(this.zoom, 0.0001)
        ));
        this._mergeHover = target;
        if (changed) this.requestRender();
    }

    _isMergeHoverHit(cx, cy) {
        if (!this._mergeHover || !this._mergeHover.scenePoint) return false;
        const [mx, my] = this.sceneToCanvas(this._mergeHover.scenePoint[0], this._mergeHover.scenePoint[1]);
        const dx = cx - mx;
        const dy = cy - my;
        return dx * dx + dy * dy <= 15 * 15;
    }

    _mergeHoveredPolygons() {
        const hover = this._mergeHover;
        if (!hover || !hover.annIds) return false;
        const a = this.annotations.find(ann => ann.id === hover.annIds[0]);
        const b = this.annotations.find(ann => ann.id === hover.annIds[1]);
        if (!a || !b || a.type !== 'polygon' || b.type !== 'polygon') return false;
        if (this._annotationClassKey(a) !== this._annotationClassKey(b)) return false;

        const merged = this._unionPolygonOutlines(a.coordinates, b.coordinates);
        if (!merged || merged.length < 3 || this._isSelfIntersecting(merged)) return false;

        this.pushAnnotationUndo();
        a.coordinates = merged;
        if (!a.name || /^ROI_\d+$/.test(a.name)) a.name = `${a.class_name || 'Merged'} ROI`;
        this.annotations = this.annotations.filter(ann => ann.id !== b.id);
        this._setMergeHover(null);
        this.selectAnnotation(a.id);
        if (this.onAnnotationDeleted) this.onAnnotationDeleted(b);
        if (this.onAnnotationChanged) this.onAnnotationChanged(a);
        this.requestRender();
        return true;
    }

    _polygonsIntersectOrContain(polyA, polyB) {
        for (let i = 0; i < polyA.length; i++) {
            const a1 = polyA[i];
            const a2 = polyA[(i + 1) % polyA.length];
            for (let j = 0; j < polyB.length; j++) {
                const b1 = polyB[j];
                const b2 = polyB[(j + 1) % polyB.length];
                if (this._segmentIntersection(a1, a2, b1, b2)) return true;
            }
        }
        return this._pointInPolygon(polyA[0][0], polyA[0][1], polyB) ||
               this._pointInPolygon(polyB[0][0], polyB[0][1], polyA);
    }

    _unionPolygonOutlines(polyA, polyB) {
        let a = this._cleanPolygonPoints(polyA);
        let b = this._cleanPolygonPoints(polyB);
        if (a.length < 3 || b.length < 3) return null;

        const areaA = this._polygonSignedArea(a);
        const areaB = this._polygonSignedArea(b);
        if (areaA === 0 || areaB === 0) return null;
        if ((areaA > 0) !== (areaB > 0)) b = [...b].reverse();

        const hasIntersections = this._findPathPolygonIntersections(a, b.concat([b[0]])).length > 0;
        if (!hasIntersections) {
            if (this._pointInPolygon(a[0][0], a[0][1], b)) return b;
            if (this._pointInPolygon(b[0][0], b[0][1], a)) return a;
            return null;
        }

        const segments = [
            ...this._outsideBoundarySegments(a, b),
            ...this._outsideBoundarySegments(b, a),
        ];
        const loops = this._segmentsToLoops(segments);
        if (!loops.length) return this._radialUnionFallback(a, b);

        loops.sort((p, q) => Math.abs(this._polygonSignedArea(q)) - Math.abs(this._polygonSignedArea(p)));
        return this._cleanPolygonPoints(loops[0]);
    }

    _outsideBoundarySegments(subject, clip) {
        const segments = [];
        for (let i = 0; i < subject.length; i++) {
            const a = subject[i];
            const b = subject[(i + 1) % subject.length];
            const split = [{ t: 0, point: a }, { t: 1, point: b }];
            for (let j = 0; j < clip.length; j++) {
                const hit = this._segmentIntersection(a, b, clip[j], clip[(j + 1) % clip.length]);
                if (hit && hit.t > 1e-7 && hit.t < 1 - 1e-7) split.push({ t: hit.t, point: hit.point });
            }
            split.sort((p, q) => p.t - q.t);
            const unique = [];
            for (const item of split) {
                const prev = unique[unique.length - 1];
                if (prev && Math.abs(prev.t - item.t) < 1e-7) continue;
                unique.push(item);
            }
            for (let k = 0; k < unique.length - 1; k++) {
                const p = unique[k].point;
                const q = unique[k + 1].point;
                if (Math.hypot(q[0] - p[0], q[1] - p[1]) < 1e-6) continue;
                const mid = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
                if (!this._pointInPolygon(mid[0], mid[1], clip)) {
                    segments.push({ a: p, b: q });
                }
            }
        }
        return segments;
    }

    _segmentsToLoops(segments) {
        const pointKey = (p) => `${Math.round(p[0] * 1000) / 1000},${Math.round(p[1] * 1000) / 1000}`;
        const starts = new Map();
        segments.forEach((seg, idx) => {
            const key = pointKey(seg.a);
            if (!starts.has(key)) starts.set(key, []);
            starts.get(key).push(idx);
        });

        const used = new Set();
        const loops = [];
        for (let i = 0; i < segments.length; i++) {
            if (used.has(i)) continue;
            const loop = [segments[i].a, segments[i].b];
            used.add(i);
            const startKey = pointKey(segments[i].a);
            let endKey = pointKey(segments[i].b);
            let guard = 0;
            while (endKey !== startKey && guard < segments.length + 2) {
                const nextList = starts.get(endKey) || [];
                const nextIdx = nextList.find(idx => !used.has(idx));
                if (nextIdx == null) break;
                used.add(nextIdx);
                loop.push(segments[nextIdx].b);
                endKey = pointKey(segments[nextIdx].b);
                guard++;
            }
            const clean = this._cleanPolygonPoints(loop);
            if (clean.length >= 3 && endKey === startKey) loops.push(clean);
        }
        return loops;
    }

    _radialUnionFallback(polyA, polyB) {
        const points = [...polyA, ...polyB];
        const cx = points.reduce((sum, p) => sum + p[0], 0) / points.length;
        const cy = points.reduce((sum, p) => sum + p[1], 0) / points.length;
        return this._cleanPolygonPoints(points.sort((p, q) =>
            Math.atan2(p[1] - cy, p[0] - cx) - Math.atan2(q[1] - cy, q[0] - cx)
        ));
    }

    _hitControlPoint(cx, cy) {
        const sel = this.annotations.find(a => a.id === this.selectedAnnotationId);
        if (!sel || !sel.visible) return null;
        const HIT_RADIUS = 8;
        for (let i = 0; i < sel.coordinates.length; i++) {
            const [pcx, pcy] = this.sceneToCanvas(sel.coordinates[i][0], sel.coordinates[i][1]);
            const dx = cx - pcx, dy = cy - pcy;
            if (dx * dx + dy * dy <= HIT_RADIUS * HIT_RADIUS) {
                return { annId: sel.id, pointIndex: i };
            }
        }
        return null;
    }

    /** scene 좌표에서 annotation 히트 테스트 (역순: 위에 그려진 것 우선) */
    _hitAnnotation(sx, sy) {
        const threshold = Math.max(4, 8 / Math.max(this.zoom, 0.0001));
        for (let i = this.annotations.length - 1; i >= 0; i--) {
            const ann = this.annotations[i];
            if (!ann.visible) continue;

            if (ann.type === 'point') {
                const pointThreshold = Math.max(threshold, 15 / Math.max(this.zoom, 0.0001));
                const dx = sx - ann.coordinates[0][0];
                const dy = sy - ann.coordinates[0][1];
                if (dx * dx + dy * dy <= pointThreshold * pointThreshold) return ann;
            } else if (ann.type === 'rectangle') {
                const xs = ann.coordinates.map(c => c[0]);
                const ys = ann.coordinates.map(c => c[1]);
                const xMin = Math.min(...xs), xMax = Math.max(...xs);
                const yMin = Math.min(...ys), yMax = Math.max(...ys);
                if (sx >= xMin && sx <= xMax && sy >= yMin && sy <= yMax) return ann;
                if (this._pointNearPolyline(sx, sy, ann.coordinates, true, threshold)) return ann;
            } else if (ann.type === 'polygon') {
                // Ray-casting algorithm
                if (this._pointInPolygon(sx, sy, ann.coordinates)) return ann;
                if (this._pointNearPolyline(sx, sy, ann.coordinates, true, threshold)) return ann;
            }
        }
        return null;
    }

    _findPolygonEdgeInsertTarget(sx, sy) {
        const threshold = Math.max(4, 10 / Math.max(this.zoom, 0.0001));
        const thresholdSq = threshold * threshold;
        let best = null;
        for (let annIdx = this.annotations.length - 1; annIdx >= 0; annIdx--) {
            const ann = this.annotations[annIdx];
            if (!ann.visible || ann.type !== 'polygon' || ann.coordinates.length < 3) continue;
            for (let i = 0; i < ann.coordinates.length; i++) {
                const a = ann.coordinates[i];
                const b = ann.coordinates[(i + 1) % ann.coordinates.length];
                const projection = this._projectPointToSegment(sx, sy, a[0], a[1], b[0], b[1]);
                if (projection.distSq > thresholdSq) continue;
                if (!best || projection.distSq < best.distSq) {
                    best = {
                        annId: ann.id,
                        insertIndex: i + 1,
                        point: [projection.x, projection.y],
                        distSq: projection.distSq,
                    };
                }
            }
        }
        return best;
    }

    _insertVertexAtEdge(target) {
        if (!target) return false;
        const ann = this.annotations.find(a => a.id === target.annId);
        if (!ann || ann.type !== 'polygon') return false;
        this.pushAnnotationUndo();
        ann.coordinates.splice(target.insertIndex, 0, target.point);
        this.selectAnnotation(ann.id);
        this._setInsertVertexPreview(null);
        if (this.onAnnotationChanged) this.onAnnotationChanged(ann);
        this.requestRender();
        return true;
    }

    _setInsertVertexPreview(target) {
        const prev = this._insertVertexPreview;
        const changed = (!!prev !== !!target) || (!!prev && !!target && (
            prev.annId !== target.annId ||
            prev.insertIndex !== target.insertIndex ||
            !prev.point ||
            Math.abs(prev.point[0] - target.point[0]) > 0.01 ||
            Math.abs(prev.point[1] - target.point[1]) > 0.01
        ));
        this._insertVertexPreview = target;
        if (changed) this.requestRender();
    }

    _pointNearPolyline(px, py, points, closed = false, threshold = 8) {
        if (!Array.isArray(points) || points.length < 2) return false;
        const thresholdSq = threshold * threshold;
        const count = closed ? points.length : points.length - 1;
        for (let i = 0; i < count; i++) {
            const a = points[i];
            const b = points[(i + 1) % points.length];
            if (this._distancePointToSegmentSq(px, py, a[0], a[1], b[0], b[1]) <= thresholdSq) {
                return true;
            }
        }
        return false;
    }

    _projectPointToSegment(px, py, ax, ay, bx, by) {
        const dx = bx - ax;
        const dy = by - ay;
        const lenSq = dx * dx + dy * dy;
        if (lenSq <= 0) {
            const ddx = px - ax;
            const ddy = py - ay;
            return { x: ax, y: ay, distSq: ddx * ddx + ddy * ddy };
        }
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq));
        const x = ax + t * dx;
        const y = ay + t * dy;
        const ddx = px - x;
        const ddy = py - y;
        return { x, y, distSq: ddx * ddx + ddy * ddy };
    }

    _distancePointToSegmentSq(px, py, ax, ay, bx, by) {
        return this._projectPointToSegment(px, py, ax, ay, bx, by).distSq;
    }

    /** Ray-casting point-in-polygon test */
    _pointInPolygon(px, py, polygon) {
        let inside = false;
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            const xi = polygon[i][0], yi = polygon[i][1];
            const xj = polygon[j][0], yj = polygon[j][1];
            if ((yi > py) !== (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi) {
                inside = !inside;
            }
        }
        return inside;
    }

    /** annotation 중심으로 뷰 이동 */
    centerOnAnnotation(ann) {
        if (!ann || !ann.coordinates || ann.coordinates.length === 0) return;
        const xs = ann.coordinates.map(c => c[0]);
        const ys = ann.coordinates.map(c => c[1]);
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
        const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
        this.viewCenterX = cx;
        this.viewCenterY = cy;
        this._clampView();
        this.requestRender();
        if (this.onViewChange) this.onViewChange();
    }

    // ── 미니맵 ──

    getViewRect() {
        if (!this.slideInfo) return null;
        const halfVW = this._viewW / this.zoom / 2;
        const halfVH = this._viewH / this.zoom / 2;
        return {
            x: this.viewCenterX - halfVW,
            y: this.viewCenterY - halfVH,
            width: halfVW * 2,
            height: halfVH * 2,
        };
    }

    navigateTo(sceneX, sceneY) {
        this.viewCenterX = sceneX;
        this.viewCenterY = sceneY;
        this._clampView();
        this.requestRender();
        if (this.onViewChange) this.onViewChange();
    }
}
